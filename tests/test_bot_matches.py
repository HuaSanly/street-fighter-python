import os
import random
import unittest
from unittest.mock import patch

import pygame

from Bot import BOT_NAMES
from main import Game
from sf import config
from sf.scenes import CharSelectScene, FightScene, MapSelectScene, MenuScene, NO_KEYS


class BotMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        drivers = {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
        with patch.dict(os.environ, drivers):
            cls.game = Game()
        cls.addClassCleanup(pygame.quit)

    def setUp(self):
        self.addCleanup(random.setstate, random.getstate())
        random.seed(23)
        self.game.change(MenuScene(self.game))

    def _press(self, *keys):
        events = [pygame.event.Event(pygame.KEYDOWN, key=key) for key in keys]
        self.game.scene.handle(events, NO_KEYS)

    def _advance(self, ticks):
        for _ in range(ticks):
            self.game.scene.update()

    def _enter_fight(self, pvp=False):
        self.game.scene.draw(self.game.screen)
        self._press(pygame.K_RETURN)
        self.assertIsInstance(self.game.scene, CharSelectScene)
        self.game.scene.draw(self.game.screen)
        if pvp:
            self._press(pygame.K_j, pygame.K_KP4)
        else:
            self._press(pygame.K_RETURN, pygame.K_RETURN)
        self._advance(50)
        self.assertIsInstance(self.game.scene, MapSelectScene)
        self.game.scene.draw(self.game.screen)
        self._press(pygame.K_RIGHT, pygame.K_RETURN)
        self.assertIsInstance(self.game.scene, FightScene)
        self._advance(88)
        self.game.scene.draw(self.game.screen)
        return self.game.scene

    def test_keyboard_only_controls_human_sides(self):
        cases = [
            ((), (None, None)),
            ((pygame.K_RIGHT,), (None, "Bot-B-Normal")),
            ((pygame.K_RIGHT, pygame.K_DOWN, pygame.K_RIGHT), ("Bot-A", None)),
        ]
        for keys, controllers in cases:
            with self.subTest(controllers=controllers):
                self.game.change(MenuScene(self.game))
                self._press(*keys)
                fight = self._enter_fight(pvp=not keys)
                self.assertEqual(fight.controllers, controllers)
                self._press(pygame.K_w, pygame.K_UP)
                self._advance(1)
                self.assertEqual([f.on_ground for f in fight.fighters],
                                 [name is not None for name in controllers])

    def test_spectator_match_finishes_and_rematches_with_same_bots(self):
        self._press(pygame.K_RIGHT, pygame.K_RIGHT)
        self._press(pygame.K_DOWN, pygame.K_DOWN, pygame.K_RIGHT)
        fight = self._enter_fight()
        self.assertEqual(fight.controllers, ("Bot-A", "Bot-B-Hard"))
        self._press(pygame.K_w, pygame.K_UP, pygame.K_j, pygame.K_KP4)
        self._advance(1)
        self.assertTrue(all(f.on_ground and f.attack is None for f in fight.fighters))
        self._press(pygame.K_ESCAPE)
        ages = [f.age for f in fight.fighters]
        self._advance(20)
        self.assertEqual([f.age for f in fight.fighters], ages)
        self._press(pygame.K_ESCAPE)

        for _ in range(5 * config.FPS * (config.ROUND_TIME + 6)):
            fight.update()
            if fight.state == "end":
                break
        self.assertEqual(fight.state, "end")
        self.assertEqual(max(fight.wins), config.ROUNDS_TO_WIN)
        self._press(pygame.K_r)
        rematch = self.game.scene
        self.assertEqual(rematch.controllers, fight.controllers)
        self.assertEqual(rematch.chars, fight.chars)
        self.assertEqual(rematch.map_index, fight.map_index)
        self.assertEqual(rematch.wins, [0, 0])
        self.assertTrue(all(a is not b for a, b in zip(fight.bots, rematch.bots)))

    def test_every_bot_can_move_attack_and_damage_the_opponent_from_either_side(self):
        for name in BOT_NAMES:
            for side in (0, 1):
                with self.subTest(bot=name, side=side + 1):
                    random.seed(23)
                    rival = "Bot-B-Hard" if name == "Bot-A" else "Bot-A"
                    lineup = (name, rival) if side == 0 else (rival, name)
                    fight = FightScene(self.game, "ryu", "ken", 1, lineup)
                    bot, opponent = fight.fighters[side], fight.fighters[1 - side]
                    start_x = bot.x
                    for _ in range(98):
                        fight.update()
                    self.assertNotEqual(bot.x, start_x)
                    attacked = False
                    for _ in range(config.FPS * config.ROUND_TIME):
                        fight.update()
                        attacked |= bot.attack is not None
                        if attacked and opponent.health <= config.MAX_HEALTH - 20:
                            break
                    self.assertTrue(attacked)
                    self.assertLessEqual(opponent.health, config.MAX_HEALTH - 20)
