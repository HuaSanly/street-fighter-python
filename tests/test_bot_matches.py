import os
import random
import unittest
from unittest.mock import patch

import pygame

from Bot import BOT_NAMES
from Bot.bot_c.tactics import INPUT_SEQUENCE
from main import Game
from sf import config
from sf.combat import ATTACKS
from sf.scenes import CharSelectScene, FightScene, MapSelectScene, MenuScene, NO_KEYS
from sf.ui import BotDebugPanel


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

    def test_adaptive_bot_keeps_learning_across_rounds_and_resets_for_new_match(self):
        for opponent in (None, "Bot-A"):
            with self.subTest(opponent=opponent):
                lineup = ("Bot-C", opponent)
                fight = FightScene(self.game, "ryu", "ken", 1, lineup)
                for _ in range(180):
                    fight.update()
                controller = fight.bots[0].controller
                observations = controller.model.observations
                evaluation = controller.observer.evaluation
                summary = evaluation.summarize_human()
                self.assertGreater(observations, 0)
                self.assertGreater(evaluation.valid_observations, 0)
                self.assertEqual(summary.count > 0, opponent is None)
                fight._next_round()
                self.assertIs(fight.bots[0].controller, controller)
                self.assertIs(controller.observer.evaluation, evaluation)
                self.assertEqual(evaluation.summarize_human(), summary)
                self.assertEqual(controller.model.observations, observations)
                self.assertIsNone(controller.observer.previous)
                rematch = FightScene(self.game, "ryu", "ken", 1, lineup)
                fresh = rematch.bots[0].controller
                self.assertEqual(fresh.model.observations, 0)
                self.assertEqual(fresh.observer.evaluation.summarize_human().count, 0)
                self.assertEqual(tuple(fresh.observer.evaluation.kl_trend), (0.0,))

    def test_debug_panel_follows_each_adaptive_bot_side(self):
        cases = [((None, "Bot-C"), (1,)), (("Bot-C", None), (0,)),
                 (("Bot-C", "Bot-C"), (0, 1)), (("Bot-A", "Bot-B-Hard"), ())]
        for lineup, expected_sides in cases:
            with self.subTest(lineup=lineup):
                fight = FightScene(self.game, "ryu", "ken", 1, lineup)
                fight.state = "fight"
                fight.update()
                with patch("sf.ui.BotDebugPanel.draw", autospec=True) as panel:
                    fight.draw(self.game.screen)
                    self.assertEqual(tuple(call.args[2] for call in panel.call_args_list),
                                     expected_sides)
                    for call in panel.call_args_list:
                        side, debug = call.args[2:]
                        self.assertIs(debug.decision, fight.bots[side].controller.last_decision)
                        self.assertAlmostEqual(sum(debug.forecast.probabilities), 1)
                        self.assertEqual(debug.human_predictions is not None, lineup[1 - side] is None)
                    panel.reset_mock()
                    fight.paused = True
                    fight.draw(self.game.screen)
                    panel.assert_not_called()

    def test_debug_panel_font_covers_chinese_action_and_context_labels(self):
        panel = BotDebugPanel()
        self.assertEqual(panel.MOVES.keys(), INPUT_SEQUENCE.keys())
        characters = set("".join((*panel.MOVES.values(), *panel.PHASES.values(),
                                 *panel.DISTANCES.values(), *panel.MODES.values(),
                                 *panel.SOURCES.values())))
        for character in characters:
            with self.subTest(character=character):
                self.assertIsNotNone(panel.body.metrics(character)[0])

    def test_standing_heavy_punch_leaves_time_to_guard_at_either_wall(self):
        move = ATTACKS["punch"]
        for side in (0, 1):
            for contact_tick in (move.startup, move.startup + move.active - 1):
                with self.subTest(side=side, contact_tick=contact_tick):
                    fight = FightScene(self.game, "ryu", "ken", 1)
                    attacker, victim = fight.fighters[side], fight.fighters[1 - side]
                    edge = config.CANVAS_W - config.STAGE_MARGIN if side == 0 else config.STAGE_MARGIN
                    toward = 1 if side == 0 else -1
                    victim.x = edge
                    attacker.x = edge - 250 * toward
                    first_hit = first_guard = second_hit = None
                    for tick in range(150):
                        if tick == contact_tick:
                            attacker.x = edge - 100 * toward
                        attack_keys = dict.fromkeys(attacker.controls.values(), False)
                        guard_keys = dict.fromkeys(victim.controls.values(), False)
                        guard_keys[victim.controls["block"]] = first_hit is not None
                        pair = [(guard_keys, set())] * 2
                        pair[side] = (attack_keys, {attacker.controls["hp"]})
                        health = victim.health
                        actions = fight.combat.step(pair)
                        if actions and actions[1 - side] == "guard" and first_guard is None:
                            first_guard = tick
                        if victim.health < health:
                            if first_hit is None:
                                first_hit = tick
                            else:
                                second_hit = tick
                                self.assertEqual(attacker.attack_contact, "block")
                                break
                    self.assertEqual(first_hit, contact_tick)
                    self.assertIsNotNone(first_guard)
                    self.assertIsNotNone(second_hit)
                    self.assertLess(first_guard, second_hit)
