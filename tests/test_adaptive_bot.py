import unittest

from Bot.bot_c.controller import AdaptiveController
from Bot.bot_c.model import OpponentModel, OpponentObserver
from Bot.bot_c.tactics import Context, context_for, legal_moves
from sf.combat import ATTACKS

from test_combat_round import inputs, make_round


class AdaptiveBotTests(unittest.TestCase):
    def test_first_order_prediction_learns_alternation_and_adapts_to_change(self):
        model = OpponentModel()
        context = Context("wake", "close", "ground", False, True)
        legal = ("guard", "quick_punch", "jump")
        previous = None
        for index in range(120):
            action = legal[index % 2]
            forecast = model.predict(context, previous, legal)
            model.update(context, previous, forecast, action, 0)
            previous = action
        first = model.predict(context, "guard", legal)
        zero = model.predict(context, "guard", legal, order=0)
        self.assertGreater(first.probabilities[1], 0.75)
        self.assertGreater(first.probabilities[1], zero.probabilities[1])
        self.assertGreater(first.trust, 0.7)

        for _ in range(95):
            forecast = model.predict(context, previous, legal)
            model.update(context, previous, forecast, "jump", 0)
            previous = "jump"
        forecast = model.predict(context, previous, legal)
        self.assertGreater(forecast.probabilities[2], 0.75)

    def test_high_entropy_can_have_high_trust(self):
        model = OpponentModel()
        context = Context("wake", "close", "ground", False, True)
        legal = ("guard", "quick_punch")
        forecast = model.predict(context, None, legal)
        self.assertEqual(forecast.trust, 0)
        for index in range(120):
            model.update(context, None, forecast, legal[index % 2], 0)
            forecast = model.predict(context, None, legal)
        self.assertGreater(forecast.entropy, 0.95)
        self.assertGreater(forecast.trust, 0.7)
        self.assertAlmostEqual(sum(forecast.probabilities), 1)

    def test_auto_order_uses_history_when_it_predicts_better(self):
        model = OpponentModel()
        context = Context("neutral", "close", "ground", False, False)
        legal = ("guard", "quick_punch")
        previous = None
        for index in range(100):
            forecast = model.predict(context, previous, legal, order="auto")
            action = legal[index % 2]
            model.update(context, previous, forecast, action, 0)
            previous = action
        automatic = model.predict(context, "guard", legal, order="auto")
        independent = model.predict(context, "guard", legal, order=0)
        self.assertGreater(automatic.probabilities[1], independent.probabilities[1] + 0.25)

    def test_opportunity_opens_on_the_first_actionable_wake_tick(self):
        fight = make_round()
        fighter = fight.fighters[1]
        fighter.x = 155
        fighter.take_hit(ATTACKS["crouch_attack"], -1)
        observer = OpponentObserver(OpponentModel())
        observer.before_tick(fight, 1)
        self.assertIsNone(observer.pending)

        fighter.hitstun = 1
        self.assertEqual(context_for(fight, 1, "ground").phase, "wake")
        observer.before_tick(fight, 1)
        self.assertEqual(observer.model.observations, 0)
        self.assertEqual(observer.pending[0].phase, "wake")
        actions = fight.step((inputs(), inputs("block")))
        self.assertEqual(actions[1], "guard")
        observer.after_tick(actions[1])
        self.assertEqual(observer.model.observations, 1)
        self.assertIn("wake", observer.model.losses)
        self.assertFalse(fighter.knocked_down)

    def test_guard_hold_is_one_observation_per_window(self):
        fight = make_round()
        observer = OpponentObserver(OpponentModel())
        for _ in range(15):
            observer.before_tick(fight, 1)
            actions = fight.step((inputs(), inputs("block")))
            observer.after_tick(actions[1])
        self.assertEqual(observer.model.observations, 3)
        self.assertEqual(observer.previous, "guard")

    def test_short_walk_does_not_hide_the_following_attack(self):
        fight = make_round()
        observer = OpponentObserver(OpponentModel())
        for action in ("left", "lp"):
            observer.before_tick(fight, 1)
            actions = fight.step((inputs(), inputs(action)))
            observer.after_tick(actions[1])
        self.assertEqual(observer.model.observations, 2)
        self.assertEqual(observer.previous, "quick_punch")

    def test_flip_cannot_drift(self):
        fight = make_round()
        fight.step((inputs("jump", "right"), inputs()))
        mode = fight.fighters[0].control_mode()
        self.assertEqual(mode, "air")
        self.assertNotIn("advance", legal_moves(fight, 0, mode))
        self.assertIn("air_kick", legal_moves(fight, 0, mode))

    def test_search_compares_actions_and_uses_baseline_on_timeout(self):
        fight = make_round()
        enemy = fight.fighters[1]
        enemy.attack = ATTACKS["upper_kick"]
        enemy.attack_tick = enemy.attack.startup - 1
        enemy.anim.set(enemy.attack.anim)
        controller = AdaptiveController(budget_ms=None, seed=13)
        fighter = fight.fighters[0]
        mode = fighter.control_mode()
        controller.context = context_for(fight, 0, mode)
        self.assertIn("guard", legal_moves(fight, 0, mode))
        decision = controller._choose(fight, 0, ("advance", "guard"))
        self.assertEqual(decision.action, "guard")
        self.assertGreaterEqual(decision.trials, 2)
        self.assertEqual(enemy.attack_tick, enemy.attack.startup - 1)

        controller.budget_ms = 0
        decision = controller._choose(fight, 0, ("advance", "guard"))
        self.assertEqual((decision.action, decision.trials), ("advance", 0))
