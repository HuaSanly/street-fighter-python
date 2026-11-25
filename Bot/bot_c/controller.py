"""Bot-C chooses a first action by simulating both sides of a short exchange."""
from dataclasses import dataclass
from random import Random
from time import perf_counter

from sf import config
from sf.combat_round import NEUTRAL_INPUTS

from ..input import encode_actions
from .model import OpponentModel, OpponentObserver
from .tactics import HELD_MOVES, INPUT_SEQUENCE, WINDOW, candidates, commands
from .tactics import context_for, legal_moves, wall_space


@dataclass(frozen=True)
class Decision:
    action: str
    trials: int
    entropy: float | None
    trust: float
    milliseconds: float


class ActionRun:
    def __init__(self):
        self.move = "wait"
        self.age = 0
        self.remaining = 0
        self.mode = None

    def start(self, move, mode, delay=0):
        self.move = move
        self.age = -delay
        self.remaining = delay + (WINDOW if move in HELD_MOVES else len(INPUT_SEQUENCE[move]))
        self.mode = mode

    def ready(self, mode):
        if mode is None:
            self.remaining = 0
            return False
        return self.mode != mode or self.remaining == 0

    def tick(self, fighter, opponent):
        if not self.remaining:
            return ()
        output = () if self.age < 0 else commands(self.move, self.age, fighter, opponent)
        self.age += 1
        self.remaining -= 1
        return output


class AdaptiveController:
    def __init__(self, *, budget_ms=2.0, model_order="auto", search=True, seed=None):
        self.budget_ms = budget_ms
        self.model_order = model_order
        self.search = search
        self.rng = Random(seed)
        self.model = OpponentModel()
        self.observer = OpponentObserver(self.model, order=model_order)
        self.reset_round()

    def reset_round(self):
        self.observer.reset()
        self.plan = ActionRun()
        self.context = None
        self.last_decision = None

    def update(self, world, side):
        self.observer.before_tick(world, 1 - side)
        fighter, opponent = world.fighters[side], world.fighters[1 - side]
        mode = fighter.control_mode()
        ready = self.plan.ready(mode)
        if mode is None:
            self.context = None
            return ()
        context = context_for(world, side, mode)
        changed = (self.context is not None and
                   (context.phase != self.context.phase or (context.danger and not self.context.danger)))
        if ready or changed:
            self.context = context
            moves = candidates(world, side, context, legal_moves(world, side, mode))
            self.last_decision = self._choose(world, side, moves)
            self.plan.start(self.last_decision.action, mode)
        return self.plan.tick(fighter, opponent)

    def observe(self, action):
        self.observer.after_tick(action)

    def _choose(self, world, side, moves):
        started = perf_counter()
        if not self.search or len(moves) == 1:
            return Decision(moves[0], 0, None, 0.0, 0.0)
        deadline = started + self.budget_ms / 1000 if self.budget_ms is not None else float("inf")
        other = 1 - side
        previous = self.observer.previous
        forecasts = {}
        root = None
        mode = world.fighters[other].control_mode()
        if mode is not None:
            root = self._forecast(world, other, mode, previous, forecasts)[1]
        entropy = root.entropy if root else None
        trust = root.trust if root else 0.0
        target_trials = 5 if entropy is not None and entropy > 0.72 else 3
        horizon = 24 if self.context.phase in ("wake", "pressure") else 20
        totals = [0.0] * len(moves)
        trials = 0
        for _ in range(target_trials):
            seed = self.rng.getrandbits(64)
            values = []
            for move in moves:
                score = self._rollout(world, side, move, previous, seed, horizon, deadline, forecasts)
                if score is None:
                    break
                values.append(score)
            if len(values) != len(moves):
                break
            totals = [total + value for total, value in zip(totals, values)]
            trials += 1
            best, second = sorted(totals, reverse=True)[:2]
            if trials >= 2 and best - second >= 12 * trials:
                break
        best = max(range(len(moves)), key=totals.__getitem__)
        if trials == 1 and totals[best] - totals[0] < 2:
            best = 0
        return Decision(moves[best], trials, entropy, trust, (perf_counter() - started) * 1000)

    def _forecast(self, world, side, mode, previous, forecasts):
        context = context_for(world, side, mode)
        legal = legal_moves(world, side, mode)
        key = (context, previous, legal)
        forecast = forecasts.get(key)
        if forecast is None:
            forecast = self.model.predict(context, previous, legal, order=self.model_order)
            forecasts[key] = forecast
        return context, forecast

    def _rollout(self, current, side, first_move, previous, seed, horizon, deadline, forecasts):
        if perf_counter() >= deadline:
            return None
        world = current.fork(viewer=side)
        rng = Random(seed)
        other = 1 - side
        my_run, enemy_run = ActionRun(), ActionRun()
        fighter, enemy = world.fighters[side], world.fighters[other]
        my_run.start(first_move, fighter.control_mode())
        recorded_enemy_move = True
        for tick in range(horizon):
            if tick % 4 == 0 and perf_counter() >= deadline:
                return None
            if world.hitstop:
                world.step()
            else:
                mode = fighter.control_mode()
                if my_run.ready(mode):
                    context = context_for(world, side, mode)
                    move = candidates(world, side, context, legal_moves(world, side, mode))[0]
                    my_run.start(move, mode)
                enemy_mode = enemy.control_mode()
                if enemy_run.ready(enemy_mode):
                    context, forecast = self._forecast(world, other, enemy_mode, previous, forecasts)
                    move = forecast.sample(rng.random())
                    delay = self.model.delay(context, move, forecast.trust)
                    delay = max(0, delay - len(INPUT_SEQUENCE[move]) + 1)
                    enemy_run.start(move, enemy_mode, delay)
                    recorded_enemy_move = False
                own_keys = my_run.tick(fighter, enemy)
                enemy_keys = enemy_run.tick(enemy, fighter)
                inputs = list(NEUTRAL_INPUTS)
                if own_keys:
                    inputs[side] = encode_actions(own_keys, fighter.controls)
                if enemy_keys:
                    inputs[other] = encode_actions(enemy_keys, enemy.controls)
                actions = world.step(inputs)
                if (not recorded_enemy_move and actions[other] is not None
                        and enemy_run.age >= len(INPUT_SEQUENCE[enemy_run.move])):
                    previous = actions[other]
                    recorded_enemy_move = True
            if world.finished:
                if world.winner is None:
                    return 0
                return config.MAX_HEALTH + 1 if world.winner == side else -config.MAX_HEALTH - 1
        return self._score(current, world, side)

    @staticmethod
    def _score(current, world, side):
        other = 1 - side
        start, start_enemy = current.fighters[side], current.fighters[other]
        fighter, enemy = world.fighters[side], world.fighters[other]
        net_damage = (start_enemy.health - enemy.health) - (start.health - fighter.health)
        distance = abs(fighter.x - enemy.x)
        previous_distance = abs(start.x - start_enemy.x)
        approach = previous_distance - distance
        if world.timer <= 8 and start.health > start_enemy.health:
            approach = -approach
        wall_advantage = min(100, wall_space(fighter)) - min(100, wall_space(enemy))
        stun_advantage = min(14, enemy.hitstun) - min(14, fighter.hitstun)
        return net_damage + 0.05 * approach + 0.025 * wall_advantage + 0.2 * stun_advantage
