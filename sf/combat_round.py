"""Shared round rules for the live match and the bot's forward simulations."""
import random
from collections import deque
from copy import copy

from . import config
from .combat import FIREBALL_SPEED, HITSTOP_BLOCK, HITSTOP_HEAVY, HITSTOP_LIGHT, SPECIALS
from .effects import Fireball


FIRE_COLORS = {"ryu": ((30, 60, 200), (80, 140, 255), (175, 215, 255)),
               "ken": ((200, 60, 10), (255, 145, 45), (255, 220, 150))}


class _NoKeys:
    def __getitem__(self, _):
        return False


class _SilentSounds:
    def play(self, *_):
        pass


NO_KEYS = _NoKeys()
NEUTRAL_INPUT = (NO_KEYS, frozenset())
NEUTRAL_INPUTS = (NEUTRAL_INPUT, NEUTRAL_INPUT)
SILENT_SOUNDS = _SilentSounds()


class CombatRound:
    def __init__(self, fighters, *, effects=None, sounds=None):
        self.fighters = fighters
        self.effects = effects
        self.sounds = sounds
        self.projectiles = []
        self.combo = [0, 0]
        self.timer = config.ROUND_TIME
        self.second_ticks = 0
        self.hitstop = 0
        self.finished = False
        self.timed_out = False
        self.winner = None

    def fork(self, *, viewer=None):
        branch = copy(self)
        branch.effects = branch.sounds = None
        branch.combo = self.combo.copy()
        branch.projectiles = [copy(projectile) for projectile in self.projectiles]
        branch.fighters = [copy(fighter) for fighter in self.fighters]
        for index, fighter in enumerate(branch.fighters):
            fighter.anim = copy(fighter.anim)
            fighter.sounds = SILENT_SOUNDS
            history = fighter.dir_history
            # An opponent's unfinished motion inputs are private.
            fighter.dir_history = deque(history if viewer in (None, index) else (),
                                        maxlen=history.maxlen)
        return branch

    def step(self, inputs=NEUTRAL_INPUTS):
        if self.finished:
            return None
        actions = None
        if self.hitstop:
            self.hitstop -= 1
        else:
            for index, fighter in enumerate(self.fighters):
                fighter.fireball_active = any(p.owner == index for p in self.projectiles)
            actions = self._move(inputs)
            self._resolve_hits()
            if not self.finished:
                self._update_projectiles()
            self._push_apart()
        if not self.finished:
            self._tick_clock()
        for index, count in enumerate(self.combo):
            opponent = self.fighters[1 - index]
            if count and not opponent.hitstun and not opponent.dying:
                self.combo[index] = 0
        return actions

    def step_presentation(self, *, after_ko=False):
        self._move(NEUTRAL_INPUTS)
        if after_ko:
            for projectile in self.projectiles[:]:
                projectile.update(self.effects)
                if self._out_of_bounds(projectile.rect):
                    self.projectiles.remove(projectile)
            self._push_apart()

    def _move(self, inputs):
        first, second = self.fighters
        # The fight has always advanced P1 before P2, even though both inputs
        # are collected from the same pre-update state.
        actions = (first.update(*inputs[0], second), second.update(*inputs[1], first))
        self._clamp_positions()
        return actions

    def _clamp_positions(self):
        for fighter in self.fighters:
            fighter.x = max(config.STAGE_MARGIN,
                            min(config.CANVAS_W - config.STAGE_MARGIN, fighter.x))

    def _push_apart(self):
        first, second = self.fighters
        first_box, second_box = first.pushbox(), second.pushbox()
        if first_box.colliderect(second_box):
            overlap = min(first_box.right, second_box.right) - max(first_box.left, second_box.left)
            shift = overlap / 2 + 0.5
            if first.x > second.x:
                shift = -shift
            first.x -= shift
            second.x += shift
            self._clamp_positions()

    def _resolve_hits(self):
        for index, attacker in enumerate(self.fighters):
            victim = self.fighters[1 - index]
            hitbox = attacker.get_hitbox()
            if not hitbox or victim.dying or not hitbox.colliderect(victim.hurtbox()):
                continue
            attack = attacker.attack
            direction = 1 if victim.x >= attacker.x else -1
            was_stunned = victim.hitstun > 0
            outcome = victim.take_hit(attack, direction)
            attacker.attack_contact = outcome
            position = None
            if self.effects is not None:
                hurtbox = victim.hurtbox()
                position = (max(hurtbox.left, min(hitbox.centerx, hurtbox.right)), hitbox.centery)
            self._impact(index, outcome, was_stunned, position, attack.heavy, attack.sound)

    def _update_projectiles(self):
        for index, fighter in enumerate(self.fighters):
            palette = FIRE_COLORS.get(fighter.name, FIRE_COLORS["ryu"])
            if (fighter.special == "hadouken" and fighter.attack
                    and fighter.attack_tick == fighter.attack.startup and not fighter.fireball_active):
                self.projectiles.append(Fireball(
                    fighter.x + fighter.facing * 62, fighter.y - 128, fighter.facing,
                    index, palette, SPECIALS["hadouken"], FIREBALL_SPEED))
                self._play("punch", 0.5)
                fighter.fireball_active = True
            if (self.effects is not None and fighter.special == "shoryuken"
                    and not fighter.on_ground and fighter.vy < 2):
                for _ in range(2):
                    self.effects.ember(fighter.x + fighter.facing * 20 + random.uniform(-14, 14),
                                       fighter.y - random.uniform(50, 190), palette)

        live = self.projectiles
        if (len(live) >= 2 and live[0].owner != live[1].owner
                and live[0].rect.colliderect(live[1].rect)):
            if self.effects is not None:
                self.effects.hit_spark(live[0].rect.center, heavy=True)
                self.effects.hit_spark(live[1].rect.center)
            self._play("punch", 0.5)
            live.clear()
            for fighter in self.fighters:
                fighter.fireball_active = False
            return

        for projectile in live[:]:
            projectile.update(self.effects)
            box = projectile.rect
            victim = self.fighters[1 - projectile.owner]
            if not victim.dying and box.colliderect(victim.hurtbox()):
                was_stunned = victim.hitstun > 0
                outcome = victim.take_hit(projectile.attack, projectile.direction)
                live.remove(projectile)
                self.fighters[projectile.owner].fireball_active = False
                self._impact(projectile.owner, outcome, was_stunned, box.center, False, "punch")
                if self.finished:
                    return
            elif self._out_of_bounds(box):
                live.remove(projectile)
                self.fighters[projectile.owner].fireball_active = False

    def _impact(self, attacker, outcome, was_stunned, position, heavy, sound):
        if outcome == "block":
            if self.effects is not None:
                self.effects.hit_spark(position, blocked=True)
            self._play("punch", 0.25)
            self.hitstop = HITSTOP_BLOCK
            return

        self._play(sound, 0.6)
        if self.effects is not None:
            self.effects.hit_spark(position, heavy=heavy)
            if heavy:
                self.effects.shake(7, 14)
        self.hitstop = HITSTOP_HEAVY if heavy else HITSTOP_LIGHT
        self.combo[attacker] = self.combo[attacker] + 1 if was_stunned else 1
        if outcome == "ko":
            self.finished = True
            self.winner = attacker
            self.hitstop = 16

    def _play(self, sound, volume):
        if self.sounds is not None:
            self.sounds.play(sound, volume)

    @staticmethod
    def _out_of_bounds(box):
        return box.right < -40 or box.left > config.CANVAS_W + 40

    def _tick_clock(self):
        self.second_ticks += 1
        if self.second_ticks < config.FPS:
            return
        self.second_ticks = 0
        self.timer -= 1
        if self.timer <= 0:
            first, second = self.fighters
            self.finished = self.timed_out = True
            if first.health != second.health:
                self.winner = 0 if first.health > second.health else 1
