"""Fighter entity: deterministic physics, input handling, attack state and
hit reactions. All movement is integrated at a fixed 60 Hz tick.

Coordinates: (x, y) is the fighter's feet center; GROUND_Y is the floor line.
"""
from collections import deque

import pygame

from . import config
from .animation import AnimPlayer
from .combat import (ATTACKS, SPECIALS, SHORYUKEN_RISE, SHORYUKEN_DRIFT,
                     SHORYUKEN_LANDING_LAG)

AIR_ANIMS = ("jump", "front_flip", "back_flip", "air_punch", "air_kick", "punch_down")
CROUCH_ANIMS = ("crouch", "crouch_punch", "crouch_attack", "crouch_hit", "crouch_hit_b")
CROUCH_HURTBOX_H = 130   # high attacks whiff over a crouching fighter


class Fighter:
    def __init__(self, name, anims, x, facing, controls, sounds):
        self.name = name
        self.anim = AnimPlayer(anims)
        self.controls = controls
        self.sounds = sounds

        self.start_x = x
        self.start_facing = facing
        self.x = float(x)
        self.y = float(config.GROUND_Y)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = facing
        self.on_ground = True

        self.health = config.MAX_HEALTH
        self.hitstun = 0
        self.blockstun = 0
        self.blocking = False
        self.attack = None
        self.attack_tick = 0
        self.hit_connected = False
        self.flash = 0
        self.dying = False
        self.win_pose = False

        # special-move input buffer: (direction token, age) entries
        self.age = 0
        self.dir_history = deque(maxlen=24)
        self.special = None          # "hadouken" | "shoryuken" while active
        self.fireball_active = False  # set by the scene: own fireball on screen

    # ------------------------------------------------------------------ round
    def reset(self):
        self.x = float(self.start_x)
        self.y = float(config.GROUND_Y)
        self.vx = self.vy = 0.0
        self.facing = self.start_facing
        self.on_ground = True
        self.health = config.MAX_HEALTH
        self.hitstun = self.blockstun = 0
        self.blocking = False
        self.attack = None
        self.attack_tick = 0
        self.hit_connected = False
        self.flash = 0
        self.dying = False
        self.win_pose = False
        self.dir_history.clear()
        self.special = None
        self.fireball_active = False
        self.anim.set("idle", force=True)

    def play_win(self):
        self.win_pose = True
        self.attack = None
        self.anim.set("win", force=True)

    # ----------------------------------------------------------------- update
    def update(self, held, pressed, opponent):
        self.age += 1
        if self.flash:
            self.flash -= 1
        if self.hitstun:
            self.hitstun -= 1
        if self.blockstun:
            self.blockstun -= 1
        if not (self.dying or self.win_pose):
            self._record_direction(held)

        self._physics()

        if self.dying:
            if self.on_ground and self.anim.name == "knockback" and self.anim.finished:
                self.anim.set("dead", force=True)
            self.anim.tick()
            return

        if self.win_pose:
            self.anim.tick()
            return

        if self.hitstun or self.blockstun:
            self.anim.tick()
            return

        # auto-face the opponent while free on the ground
        if self.on_ground and not self.attack:
            self.facing = 1 if opponent.x >= self.x else -1

        c = self.controls
        fwd_key = c["right"] if self.facing > 0 else c["left"]
        back_key = c["left"] if self.facing > 0 else c["right"]

        # ongoing attack locks the fighter (unless a light cancels on hit)
        if self.attack:
            self.attack_tick += 1
            if self.attack.cancel and self.hit_connected:
                self._try_attack(pressed, held)
            # shoryuken holds its final pose until the fighter lands
            if self.special == "shoryuken" and not self.on_ground:
                if not self.anim.finished:
                    self.anim.tick()
                return
            if self.attack and (self.anim.finished or self.anim.name != self.attack.anim):
                self.attack = None
                self.special = None
            if self.attack:
                self.anim.tick()
                return

        # blocking: hold the block key while grounded (frozen guard pose)
        self.blocking = self.on_ground and held[c["block"]]
        if self.blocking:
            self.vx = 0
            self.anim.set("parry_b")
            self.anim.frame_index = 0
            return

        if self._try_attack(pressed, held):
            self.anim.tick()
            return

        # jump — straight, or flip when a direction is held
        if self.on_ground and c["jump"] in pressed:
            self.vy = config.JUMP_FORCE
            self.on_ground = False
            if held[fwd_key]:
                self.anim.set("front_flip", force=True)
                self.vx = self.facing * config.MOVE_SPEED
            elif held[back_key]:
                self.anim.set("back_flip", force=True)
                self.vx = -self.facing * config.MOVE_SPEED
            else:
                self.anim.set("jump", force=True)
                self.vx = 0
            self.sounds.play("jump")
            self.anim.tick()
            return

        if not self.on_ground:
            # limited air drift on straight jumps; flips keep their momentum
            if self.anim.name == "jump":
                self.vx = 0
                if held[c["left"]]:
                    self.vx = -config.AIR_MOVE_SPEED
                if held[c["right"]]:
                    self.vx = config.AIR_MOVE_SPEED
            self.anim.tick()
            return

        # crouch: hold down while grounded
        if held[c["down"]]:
            self.vx = 0
            self.anim.set("crouch")
            self.anim.tick()
            return

        # grounded movement
        self.vx = 0
        if held[c["left"]]:
            self.vx -= config.MOVE_SPEED
        if held[c["right"]]:
            self.vx += config.MOVE_SPEED
        if self.vx:
            forward = (self.vx > 0) == (self.facing > 0)
            self.anim.set("parry_f" if forward else "parry_b")
        else:
            self.anim.set("idle")
        self.anim.tick()

    def _physics(self):
        self.x += self.vx
        self.y += self.vy
        if self.y < config.GROUND_Y:
            self.vy += config.GRAVITY
            self.on_ground = False
        elif not self.on_ground:
            self.y = float(config.GROUND_Y)
            self.vy = 0
            self.on_ground = True
            self._land()
        # knockback slides decay with ground friction
        if self.on_ground and (self.hitstun or self.blockstun or self.dying):
            self.vx *= 0.82
            if abs(self.vx) < 0.3:
                self.vx = 0

    def _land(self):
        if self.dying or self.hitstun:
            return
        if self.special == "shoryuken":
            self.special = None
            self.attack = None
            self.vx = 0
            self.blockstun = SHORYUKEN_LANDING_LAG  # whiffed DPs are punishable
            self.anim.set("idle", force=True)
            return
        if self.anim.name in AIR_ANIMS:
            self.attack = None
            self.vx = 0
            self.anim.set("idle", force=True)

    # ---------------------------------------------------------------- attacks
    def _record_direction(self, held):
        """Track direction changes (relative to facing) for motion inputs."""
        c = self.controls
        fwd = held[c["right"]] if self.facing > 0 else held[c["left"]]
        back = held[c["left"]] if self.facing > 0 else held[c["right"]]
        token = ""
        if held[c["down"]]:
            token += "d"
        if fwd:
            token += "f"
        elif back:
            token += "b"
        token = token or "n"
        if not self.dir_history or self.dir_history[-1][0] != token:
            self.dir_history.append((token, self.age))

    def _has_motion(self, pattern, window):
        """True if `pattern` (e.g. "df") appears in order within `window` ticks.
        A step matches any token containing it, so down-forward counts as both."""
        i = 0
        for token, age in self.dir_history:
            if self.age - age > window:
                continue
            if pattern[i] in token:
                i += 1
                if i == len(pattern):
                    return True
        return False

    def _start_special(self, name):
        atk = SPECIALS[name]
        self.special = name
        self.attack = atk
        self.attack_tick = 0
        self.hit_connected = False
        self.blocking = False
        self.dir_history.clear()
        self.vx = 0
        if name == "shoryuken":
            self.vy = SHORYUKEN_RISE
            self.vx = self.facing * SHORYUKEN_DRIFT
            self.sounds.play("jump", 0.5)
        self.sounds.play("punch", 0.4)
        self.anim.set(atk.anim, force=True)
        return True

    def _try_attack(self, pressed, held):
        c = self.controls
        holding_forward = held[c["right"]] if self.facing > 0 else held[c["left"]]
        holding_down = self.on_ground and held[c["down"]]
        # motion specials take priority over normal punches
        if self.on_ground and (c["lp"] in pressed or c["hp"] in pressed):
            if self._has_motion("fdf", 20):          # forward, down, forward
                return self._start_special("shoryuken")
            if self._has_motion("df", 26) and not self.fireball_active \
                    and not holding_down:
                return self._start_special("hadouken")
        choice = None
        if holding_down:
            if c["lp"] in pressed or c["hp"] in pressed:
                choice = "crouch_punch"
            elif c["lk"] in pressed or c["hk"] in pressed:
                choice = "crouch_attack"   # sweep: knocks down
        elif c["lp"] in pressed:
            choice = "air_punch" if not self.on_ground else "quick_punch"
        elif c["hp"] in pressed:
            if not self.on_ground:
                choice = "punch_down"
            else:
                choice = "uppercut" if holding_forward else "punch"
        elif c["lk"] in pressed:
            choice = "air_kick" if not self.on_ground else "kick_low"
        elif c["hk"] in pressed:
            choice = "air_kick" if not self.on_ground else "upper_kick"
        if not choice:
            return False
        self.attack = ATTACKS[choice]
        self.attack_tick = 0
        self.hit_connected = False
        self.blocking = False
        self.special = None
        if self.on_ground:
            self.vx = 0
        self.anim.set(choice, force=True)
        return True

    def get_hitbox(self):
        """Active hitbox rect, or None outside the active window."""
        atk = self.attack
        if not atk or self.hit_connected:
            return None
        if not (atk.startup <= self.attack_tick < atk.startup + atk.active):
            return None
        x0 = self.x + self.facing * 22
        left = min(x0, x0 + self.facing * atk.reach)
        cy = self.y - atk.y
        return pygame.Rect(int(left), int(cy - atk.h / 2), atk.reach, atk.h)

    @property
    def is_crouching(self):
        return self.anim.name in CROUCH_ANIMS

    def hurtbox(self):
        w, h = config.HURTBOX_W, config.HURTBOX_H
        if self.anim.name == "dead":
            return pygame.Rect(int(self.x - w), int(self.y - 50), w * 2, 50)
        if self.is_crouching:
            h = CROUCH_HURTBOX_H
        return pygame.Rect(int(self.x - w / 2), int(self.y - h), w, h)

    def pushbox(self):
        w = config.PUSHBOX_W
        return pygame.Rect(int(self.x - w / 2), int(self.y - 195), w, 195)

    def take_hit(self, atk, direction):
        """Apply a connecting attack. Returns 'block', 'hit' or 'ko'."""
        if self.blocking and self.on_ground:
            chip = max(1, int(atk.damage * config.BLOCK_CHIP_RATIO))
            self.health = max(1, self.health - chip)   # chip never KOs
            self.blockstun = atk.blockstun
            self.vx = direction * atk.knockback * 0.6
            return "block"

        self.health = max(0, self.health - atk.damage)
        self.flash = 5
        self.vx = direction * atk.knockback
        self.attack = None
        self.special = None
        self.blocking = False

        if self.health <= 0:
            self.dying = True
            self.hitstun = 0
            self.anim.set("knockback", force=True)
            if self.on_ground:
                self.vy = -9  # pop up on the KO blow
                self.on_ground = False
            return "ko"

        if atk.heavy or not self.on_ground:
            self.anim.set("knockback", force=True)
            self.hitstun = 48  # knockdown: knockback -> recover
        elif self.is_crouching:
            self.anim.set("crouch_hit", force=True)
            self.hitstun = atk.hitstun
        else:
            self.anim.set("hit_stand", force=True)
            self.hitstun = atk.hitstun
        return "hit"

    # ------------------------------------------------------------------- draw
    def draw(self, surf, offset=(0, 0)):
        ox, oy = offset
        # soft drop shadow on the floor
        frame = self.anim.frame(self.facing < 0)
        w = frame.get_width()
        shadow_w = max(60, int(w * 0.55))
        shadow = pygame.Surface((shadow_w, 16), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 90), shadow.get_rect())
        surf.blit(shadow, (self.x - shadow_w / 2 + ox, config.GROUND_Y - 6 + oy))

        pos = (int(self.x - w / 2 + ox), int(self.y - frame.get_height() + oy))
        if self.flash:
            lit = frame.copy()
            lit.fill((160, 160, 160), special_flags=pygame.BLEND_RGB_ADD)
            surf.blit(lit, pos)
        else:
            surf.blit(frame, pos)
