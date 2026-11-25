"""Tepelekas's CPUController decision rules, adapted to this game's frame data."""

import random

from sf import config
from sf.combat import ATTACKS


# The source fighter walks at 5 pixels per tick. Keep similar approach timing.
DISTANCE_SCALE = config.MOVE_SPEED / 5
PUNCH_RANGE = ATTACKS["punch"].reach + config.HURTBOX_W / 2


class CPUController:
    def __init__(self, difficulty="normal"):
        self.difficulty = ("easy", "normal", "hard").index(difficulty)
        self.action_timer = 0
        self.current_action = None
        self.attack_cooldown = 0
        self.attack_windup = 0
        self.defend_cooldown = 0
        self.jump_cooldown = 0
        self.previous_distance = float("inf")

    def _scale(self, easy, normal, hard):
        return (easy, normal, hard)[self.difficulty]

    def update(self, fighter, opponent):
        self.action_timer -= 1
        self.attack_cooldown = max(0, self.attack_cooldown - 1)
        self.defend_cooldown = max(0, self.defend_cooldown - 1)
        self.jump_cooldown = max(0, self.jump_cooldown - 1)

        if fighter.dying or fighter.hitstun:
            self.current_action = None
            self.action_timer = self.attack_windup = 0
            self.previous_distance = float("inf")
            return ()

        distance = abs(fighter.x - opponent.x)
        attack_distance = PUNCH_RANGE * self._scale(0.86, 0.93, 1.0)
        entered_range = distance < attack_distance <= self.previous_distance
        self.previous_distance = distance
        vertical_distance = abs(fighter.y - opponent.y)
        toward, away = ("right", "left") if opponent.x >= fighter.x else ("left", "right")
        ready = fighter.attack is None and fighter.blockstun == 0
        airborne = not opponent.on_ground or vertical_distance > 80

        # One tick of lookahead lets the guard engage on the first active frame.
        hitbox = opponent.get_hitbox(ahead=1)
        if (ready and fighter.on_ground and self.defend_cooldown == 0 and hitbox
                and distance < self._scale(60, 80, 110) * DISTANCE_SCALE
                and hitbox.colliderect(fighter.hurtbox().inflate(20, 0))
                and random.random() < self._scale(0.3, 0.55, 0.85)):
            self.current_action = "shield"
            self.action_timer = self._scale(15, 20, 25)
            self.defend_cooldown = self._scale(120, 90, 60)
        elif self.action_timer <= 0 or (self.current_action == "approach" and entered_range):
            if (airborne and self.jump_cooldown == 0
                    and random.random() < self._scale(0.2, 0.35, 0.5)):
                self.current_action = "jump"
                self.action_timer = 10
                self.jump_cooldown = self._scale(120, 90, 70)
            elif (distance < attack_distance and self.attack_cooldown == 0
                  and random.random() < self._scale(0.4, 0.7, 0.9)):
                self._start_attack(self._scale(55, 40, 30), self._scale(10, 6, 3))
            elif distance > self._scale(140, 120, 100) * DISTANCE_SCALE:
                self._approach()
            elif (distance < self._scale(70, 90, 110) * DISTANCE_SCALE
                  and random.random() < self._scale(0.3, 0.5, 0.65)):
                self.current_action = "retreat"
                self.action_timer = random.randint(10, 20)
            elif (distance < self._scale(80, 100, 130) * DISTANCE_SCALE and self.attack_cooldown == 0
                  and random.random() < self._scale(0.25, 0.5, 0.7)):
                self._start_attack(35, 0)
            else:
                self._approach()

        if self.current_action == "attack":
            if self.attack_windup > 0:
                self.attack_windup -= 1
            elif ready:
                if not fighter.on_ground:
                    return ("hk",)
                return ("lk",) if opponent.is_crouching else ("hp",)
        elif self.current_action == "shield":
            return ("block",)
        elif self.current_action == "jump" and ready and fighter.on_ground:
            return ("jump",)
        elif self.current_action == "approach":
            return (toward,)
        elif self.current_action == "retreat":
            return (away,)
        return ()

    def _start_attack(self, cooldown, windup):
        self.current_action = "attack"
        self.action_timer = 30
        self.attack_cooldown = cooldown
        self.attack_windup = windup

    def _approach(self):
        self.current_action = "approach"
        self.action_timer = random.randint(15, 30)
