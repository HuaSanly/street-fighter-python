"""Run paired headless rounds to compare Bot-C's search and opponent models."""
import argparse
from collections import defaultdict
import os
from random import Random, seed as seed_random
from statistics import mean

from main import Game
from sf import config
from sf.scenes import FightScene

from ..input import encode_actions
from .controller import ActionRun, AdaptiveController
from .tactics import JAB_RANGE, LONG_RANGE


VARIANTS = {"rules": (False, None), "prior": (True, None),
            "zero": (True, 0), "first": (True, 1), "auto": (True, "auto")}
RIVALS = ("Bot-A", "Bot-B-Easy", "Bot-B-Normal", "Bot-B-Hard",
          "mash", "mixed", "switch")


class ScriptedInput:
    def __init__(self, style, seed, duration):
        self.style = style
        self.rng = Random(seed)
        self.half = duration / 2
        self.plan = ActionRun()

    def update(self, world, side):
        fighter, opponent = world.fighters[side], world.fighters[1 - side]
        mode = fighter.control_mode()
        if self.plan.ready(mode):
            reach = LONG_RANGE if self.style == "mixed" else JAB_RANGE
            if abs(fighter.x - opponent.x) > reach - 14 and not mode.endswith("cancel"):
                move = "advance"
            elif mode.startswith("air"):
                move = "air_kick"
            elif self.style == "mixed":
                choices = ("guard", "quick_punch", "crouch_attack")
                move = self.rng.choice(choices if not mode.endswith("cancel") else choices[1:])
            elif self.style == "switch" and world.timer <= self.half:
                move = "guard" if not mode.endswith("cancel") else "wait"
            else:
                move = "quick_punch"
            self.plan.start(move, mode)
        return encode_actions(self.plan.tick(fighter, opponent), fighter.controls)

    def observe(self, _):
        pass


def play_round(game, variant, rival_name, seed, side, duration, realtime):
    seed_random(seed)
    lineup = ["Bot-C", "Bot-C"]
    lineup[1 - side] = rival_name if rival_name.startswith("Bot-") else None
    scene = FightScene(game, "ryu", "ken", 1, tuple(lineup))
    search, order = VARIANTS[variant]
    controller = AdaptiveController(search=search, model_order=order,
                                    budget_ms=2.0 if realtime else None, seed=seed)
    scene.bots[side].controller = controller
    if lineup[1 - side] is None:
        scene.bots[1 - side] = ScriptedInput(rival_name, seed, duration)
    scene.state = "fight"
    scene.combat.timer = duration
    previous = None
    decisions = []
    for _ in range(duration * config.FPS):
        scene.update()
        decision = controller.last_decision
        if decision is not None and decision is not previous and decision.milliseconds:
            decisions.append(decision)
        previous = decision
        if scene.combat.finished:
            break
    health = scene.fighters[side].health - scene.fighters[1 - side].health
    winner = scene.combat.winner
    points = 0.5 if winner is None else float(winner == side)
    return points, health, decisions, controller.model.losses


def report(variant, rival, results):
    points, health, decisions, losses = zip(*results)
    searches = [decision for batch in decisions for decision in batch]
    timing = sorted(decision.milliseconds for decision in searches)
    rows = defaultdict(lambda: [0, 0.0, 0.0])
    for match in losses:
        for phase, values in match.items():
            rows[phase] = [total + value for total, value in zip(rows[phase], values)]
    summary = ", ".join(f"{phase} {loss / n:.3f}/{baseline / n:.3f} (n={n})"
                        for phase, (n, loss, baseline) in sorted(rows.items()))
    performance = ""
    if timing:
        p95, p99 = (timing[round((len(timing) - 1) * p)] for p in (0.95, 0.99))
        recovery = sum(decision.trials == 0 for decision in searches) / len(searches)
        performance = f" | p95/p99 {p95:.2f}/{p99:.2f} ms, fallback {recovery:.1%}"
    print(f"{variant:5} vs {rival:12} | points {mean(points):.1%}, HP {mean(health):+.1f}"
          f"{performance} | NLL model/prior {summary}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=2, help="seeds, each run from P1 and P2")
    parser.add_argument("--seconds", type=int, default=15, help="maximum seconds per round")
    parser.add_argument("--rivals", nargs="+", choices=RIVALS, default=RIVALS)
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=tuple(VARIANTS))
    parser.add_argument("--realtime", action="store_true", help="apply the live 2 ms search budget")
    args = parser.parse_args()
    if not (args.pairs > 0 and 1 <= args.seconds <= config.ROUND_TIME):
        parser.error("pairs must be positive and seconds within the normal round duration")

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    game = Game()
    for rival in args.rivals:
        for variant in args.variants:
            results = [play_round(game, variant, rival, seed, side, args.seconds, args.realtime)
                       for seed in range(args.pairs) for side in (0, 1)]
            report(variant, rival, results)


if __name__ == "__main__":
    main()
