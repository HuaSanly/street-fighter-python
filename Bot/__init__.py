"""Translate bot commands to the same held and pressed keys used by fighters."""

from functools import partial

from .bot_a.controller import TacticalController
from .bot_b.controller import CPUController
from .bot_c.controller import AdaptiveController
from .input import encode_actions


BOT_FACTORIES = {
    "Bot-A": TacticalController,
    "Bot-B-Easy": partial(CPUController, difficulty="easy"),
    "Bot-B-Normal": partial(CPUController, difficulty="normal"),
    "Bot-B-Hard": partial(CPUController, difficulty="hard"),
    "Bot-C": AdaptiveController,
}
BOT_NAMES = tuple(BOT_FACTORIES)


class BotInput:
    def __init__(self, name, controls):
        self.name = name
        self.controller = BOT_FACTORIES[name]()
        self.controls = controls

    def update(self, world, side):
        if isinstance(self.controller, AdaptiveController):
            actions = self.controller.update(world, side)
        else:
            actions = self.controller.update(world.fighters[side], world.fighters[1 - side])
        return encode_actions(actions, self.controls)

    def observe(self, world, side, actions, *, human_opponent=False):
        if isinstance(self.controller, AdaptiveController):
            self.controller.observe(world, side, actions, human_opponent=human_opponent)

    def debug_state(self, world, side, *, human_opponent=False):
        if isinstance(self.controller, AdaptiveController):
            return self.controller.debug_state(world, side, human_opponent=human_opponent)
        return None

    def reset_round(self):
        if isinstance(self.controller, AdaptiveController):
            self.controller.reset_round()
        else:
            self.controller = BOT_FACTORIES[self.name]()
