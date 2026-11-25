"""Tactical AI based on the behavior of Gothicvania's Bot."""

import math
import random
from collections import deque

from sf import config
from sf.combat import ATTACKS


class TacticalController:
    def __init__(self):
        self.opponent_moves = deque(maxlen=12)
        self.last_move = "idle"
        self.last_attack_landed = False
        self.punish_until = 0
        self.tick = 0
        self.next_decision = 0
        self.next_attack = 0
        self.next_jump = 0
        self.next_rush = 0
        self.rush_until = 0
        self.movement = ()

    def _observe(self, opponent):
        if opponent.attack:
            move = "attack"
            self.last_attack_landed = opponent.hit_connected
        elif not opponent.on_ground:
            move = "airborne"
        elif opponent.is_crouching:
            move = "crouch"
        else:
            move = "idle"

        if move != self.last_move:
            self.opponent_moves.append(self.last_move)
            if self.last_move == "attack" and not self.last_attack_landed and not opponent.hitstun:
                self.punish_until = self.tick + 13
            self.last_move = move

    def update(self, fighter, opponent):
        self.tick += 1
        self._observe(opponent)
        if fighter.dying or fighter.hitstun or fighter.blockstun:
            self.rush_until = 0
            self.movement = ()
            self.next_decision = self.tick
            return ()
        if self.tick < self.next_decision:
            return self.movement

        self.next_decision = self.tick + 3  # Gothicvania's default reaction interval at 60 Hz
        dx = opponent.x - fighter.x
        toward, away = ("right", "left") if dx >= 0 else ("left", "right")
        distance = abs(dx)
        ready = fighter.attack is None and self.tick >= self.next_attack
        stage_right = config.CANVAS_W - config.STAGE_MARGIN
        cornered = min(opponent.x - config.STAGE_MARGIN, stage_right - opponent.x) < 95
        crouch_tendency = self.opponent_moves.count("crouch") >= 3
        attack = opponent.attack
        threatened = (attack is not None and not opponent.hit_connected
                      and opponent.attack_tick < attack.startup + attack.active
                      and dx * opponent.facing <= 0
                      and distance < attack.reach + config.HURTBOX_W / 2 + 22
                      and fighter.y - config.HURTBOX_H < opponent.y - attack.y + attack.h / 2
                      and opponent.y - attack.y - attack.h / 2 < fighter.y)
        self.movement = ()

        if not fighter.on_ground:
            self.movement = (toward,)
            if ready and distance < 145 and -120 < opponent.y - fighter.y < 145:
                return self._strike("hk", toward)
        elif threatened:  # Evade startup or guard an imminent hit.
            self.rush_until = 0
            if (fighter.attack is None and attack.startup - opponent.attack_tick >= 5
                    and self.tick >= self.next_jump):
                self.next_jump = self.tick + random.randint(45, 60)
                self.movement = (toward,)
                return (toward, "jump")
            self.movement = ("block",)
        elif self.tick < self.punish_until and distance < 175:
            if ready:
                return self._strike("hk" if not opponent.is_crouching else "lk")
            self.movement = (toward,) if distance > 105 else ()
        elif not opponent.on_ground and distance < 205:
            height = max(0, config.GROUND_Y - opponent.y)
            ticks_to_land = (math.sqrt(opponent.vy ** 2 + 2 * config.GRAVITY * height)
                             - opponent.vy) / config.GRAVITY
            if ready and opponent.vy > 0 and ticks_to_land <= 8 and distance < 155:
                return self._strike("hp", toward)
            if distance > 100:
                self.movement = (toward,)
            elif distance < 75:
                self.movement = (away,)
        elif (fighter.health < config.MAX_HEALTH * 0.25
              and opponent.health - fighter.health > config.MAX_HEALTH * 0.2
              and distance < 110 and not cornered and random.random() < 0.35):
            self.movement = (away,)
        elif self.tick < self.rush_until or (distance > 170 and self.tick >= self.next_rush):
            # A forward rush into a sweep fills the role of the source game's slide.
            if ready and distance < ATTACKS["crouch_attack"].reach:
                self.rush_until = 0
                return self._strike("hk", "down")
            if self.tick >= self.rush_until:
                self.next_rush = self.tick + random.randint(38, 55)
                self.rush_until = self.tick + 20
            if distance >= 100:
                self.movement = (toward,)
        elif (crouch_tendency and not cornered and distance < 125
              and random.random() < 0.15):
            self.movement = (away,)
        elif ready and distance < 155:
            if opponent.is_crouching or crouch_tendency:
                return self._strike("lk")
            if distance < 105 and random.random() < 0.4:
                return self._strike("lp")
            return self._strike("hk")
        elif cornered or distance > 128:
            self.movement = (toward,)
        elif distance < 80:
            self.movement = (away,)
        return self.movement

    def _strike(self, attack, *held):
        self.next_attack = self.tick + random.randint(10, 14)
        return (*held, attack)
