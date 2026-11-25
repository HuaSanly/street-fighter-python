"""Translate bot commands to the same held and pressed keys used by fighters."""

from functools import partial

from .bot_a.controller import TacticalController
from .bot_b.controller import CPUController


BOT_FACTORIES = {
    "Bot-A": TacticalController,
    "Bot-B-Easy": partial(CPUController, difficulty="easy"),
    "Bot-B-Normal": partial(CPUController, difficulty="normal"),
    "Bot-B-Hard": partial(CPUController, difficulty="hard"),
}
BOT_NAMES = tuple(BOT_FACTORIES)
PRESS_ACTIONS = {"jump", "lp", "hp", "lk", "hk"}


class BotInput:
    def __init__(self, name, controls):
        self.controller = BOT_FACTORIES[name]()
        self.controls = controls

    def update(self, fighter, opponent):
        actions = self.controller.update(fighter, opponent)
        held = {key: action in actions for action, key in self.controls.items()}
        pressed = {self.controls[action] for action in actions if action in PRESS_ACTIONS}
        return held, pressed
