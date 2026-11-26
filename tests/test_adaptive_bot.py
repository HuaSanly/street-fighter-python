import unittest

from Bot.bot_c.controller import AdaptiveController
from Bot.bot_c.evaluation import PredictionEvaluation, kl_divergence
from Bot.bot_c.model import Forecast, OpponentModel, OpponentObserver
from Bot.bot_c.tactics import ATTACK_ACTIONS, Context, candidates, context_for, legal_moves
from sf.combat import ATTACKS

from test_combat_round import inputs, make_round


class AdaptiveBotTests(unittest.TestCase):
    def test_prediction_gain_and_kl_measure_different_things(self):
        forecast = Forecast(("guard", "advance"), (0.8, 0.2), (0.8, 0.2), (0.5, 0.5),
                            0.0, 1.0, None)
        evaluation = PredictionEvaluation()
        evaluation.record(forecast, "guard", human=True)
        self.assertEqual(evaluation.summarize_human().hit_rate, 1)
        self.assertAlmostEqual(evaluation.summarize_human().gain, 0.4700036292)
        for _ in range(50):
            evaluation.record(forecast, "advance", human=True)
        summary = evaluation.summarize_human()
        self.assertEqual(summary.count, 50)
        self.assertEqual(summary.hit_rate, 0)
        self.assertAlmostEqual(summary.gain, -0.9162907319)
        self.assertAlmostEqual(kl_divergence(forecast), 0.1927447570)

    def test_live_guard_is_scored_before_learning_and_updates_fixed_kl(self):
        fight = make_round()
        controller = AdaptiveController()
        initial = controller.debug_state(fight, 0, human_opponent=True)
        self.assertEqual(initial.current_kl, 0)
        self.assertIsNone(initial.human_predictions.gain)
        for tick in range(260):
            controller.observer.before_tick(fight, 1)
            actions = fight.step((inputs(), inputs("block")))
            controller.observe(fight, 0, actions, human_opponent=True)
            if tick == 0:
                first = controller.debug_state(fight, 0, human_opponent=True)
                self.assertEqual(first.human_predictions.count, 1)
                self.assertEqual(first.human_predictions.gain, 0)
                self.assertGreater(first.current_kl, 0)

        debug = controller.debug_state(fight, 0, human_opponent=True)
        self.assertEqual(debug.human_predictions.count, 50)
        self.assertGreater(debug.human_predictions.gain, 0)
        self.assertEqual(debug.human_predictions.hit_rate, 1)
        evaluation = controller.observer.evaluation
        self.assertEqual(evaluation.valid_observations, 52)
        self.assertEqual(len(debug.kl_trend), 1 + evaluation.valid_observations // 10)
        self.assertGreater(debug.kl_trend[-1], debug.kl_trend[0])

    def test_unmatched_action_does_not_score_as_wait(self):
        fight = make_round()
        observer = OpponentObserver(OpponentModel())
        observer.before_tick(fight, 1)
        for _ in range(5):
            observer.after_tick("unmapped", human=True)
        summary = observer.evaluation.summarize_human()
        self.assertEqual(summary.unmatched, 1)
        self.assertEqual(summary.count, 0)
        self.assertEqual(observer.evaluation.valid_observations, 0)
        self.assertEqual(observer.model.observations, 1)
        self.assertEqual(observer.previous, "wait")

    def test_ground_cancel_search_uses_only_designated_specials(self):
        fight = make_round()
        fight.step((inputs("lp"), inputs()))
        for _ in range(ATTACKS["quick_punch"].startup):
            fight.step()
        mode = fight.fighters[0].control_mode()
        self.assertEqual(mode, "ground_cancel")
        legal = legal_moves(fight, 0, mode)
        self.assertEqual(set(legal), {"wait", "hadouken", "shoryuken"})
        self.assertEqual(candidates(fight, 0, context_for(fight, 0, mode), legal), legal)
        controller = AdaptiveController()
        context = context_for(fight, 0, mode)
        self.assertEqual(controller._moves(fight, 0, context, fight.fighters[0].age + 22), legal)

    def test_attack_interval_filters_new_attacks_and_counts_only_active_frames(self):
        fight = make_round()
        fighter = fight.fighters[0]
        controller = AdaptiveController(attack_interval=22)
        blocking = inputs("block")
        actions = fight.step((inputs("lp"), blocking))
        controller.observe(fight, 0, actions)
        next_attack = fighter.age + 22
        self.assertEqual(controller.next_attack_tick, next_attack)
        for _ in range(ATTACKS["quick_punch"].startup):
            fight.step((inputs(), blocking))
        self.assertGreater(fight.hitstop, 0)
        age_at_hit = fighter.age
        while fight.hitstop:
            fight.step()
        self.assertEqual(fighter.age, age_at_hit)

        while fighter.age + 1 < next_attack - 1:
            fight.step()
        mode = fighter.control_mode()
        self.assertEqual(mode, "ground")
        context = context_for(fight, 0, mode)
        moves = controller._moves(fight, 0, context, controller.next_attack_tick)
        self.assertIn("guard", moves)
        self.assertFalse(ATTACK_ACTIONS.intersection(moves))
        fight.step()
        self.assertIn("quick_punch", controller._moves(fight, 0, context,
                                                      controller.next_attack_tick))

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
        self.assertEqual(decision.source, "deadline")

    def test_debug_forecast_is_read_only_and_disappears_for_locked_opponent(self):
        fight = make_round()
        controller = AdaptiveController(seed=13)
        before = controller.rng.getstate()
        debug = controller.debug_state(fight, 0)
        enemy_context = context_for(fight, 1, "ground")
        expected = controller.model.predict(enemy_context, None, legal_moves(fight, 1, "ground"),
                                            order=controller.model_order)
        self.assertEqual(debug.forecast, expected)
        self.assertEqual(controller.model.observations, 0)
        self.assertEqual(controller.rng.getstate(), before)
        fight.fighters[1].hitstun = 8
        self.assertIsNone(controller.debug_state(fight, 0).forecast)
