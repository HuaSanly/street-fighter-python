"""Bot-C 的对战控制器。模拟短时间内双方的交手，每次只执行选中的首个动作。"""
from dataclasses import dataclass
from random import Random
from time import perf_counter

from sf import config
from sf.combat_round import NEUTRAL_INPUTS

from ..input import encode_actions
from .evaluation import HumanPredictionSummary, kl_divergence
from .model import Forecast, OpponentModel, OpponentObserver
from .tactics import ATTACK_ACTIONS, HELD_MOVES, INPUT_SEQUENCE, WINDOW, Context, candidates, commands
from .tactics import context_for, legal_moves, wall_space


@dataclass(frozen=True)
class Decision:
    """一次选招的结果。trials 是所有候选都完成评估的轮数，source 记录选招依据。"""

    action: str
    trials: int
    entropy: float | None
    trust: float
    milliseconds: float
    source: str


@dataclass(frozen=True)
class DebugState:
    """调试面板读取的快照，包含当前预测和最近一次实际选招。"""

    context: Context
    forecast: Forecast | None
    decision: Decision | None
    hitstop: bool
    human_predictions: HumanPredictionSummary | None
    current_kl: float | None
    kl_trend: tuple[float, ...]


class ActionRun:
    """把一个策略动作按帧执行，例如持续防御五帧，或依次输入必杀技指令。"""

    def __init__(self):
        self.move = "wait"
        self.age = 0
        self.remaining = 0
        self.mode = None

    def start(self, move, mode, delay=0):
        self.move = move
        # 用负数表示起手前的等待帧。到第 0 帧才开始发送动作指令。
        self.age = -delay
        self.remaining = delay + (WINDOW if move in HELD_MOVES else len(INPUT_SEQUENCE[move]))
        self.mode = mode

    def ready(self, mode):
        if mode is None:
            # 进入受击等锁定状态时中止旧指令，等恢复行动权后重新选招。
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
    def __init__(self, *, budget_ms=2.0, model_order="auto", search=True, seed=None,
                 attack_interval=22):
        self.budget_ms = budget_ms
        self.model_order = model_order
        self.search = search
        self.attack_interval = attack_interval
        self.rng = Random(seed)
        self.model = OpponentModel()
        self.observer = OpponentObserver(self.model, order=model_order)
        self.reset_round()

    def reset_round(self):
        """清空回合内的输入和观察窗口，保留同一场比赛学到的对手模型。"""
        self.observer.reset()
        self.plan = ActionRun()
        self.context = None
        self.last_decision = None
        self.next_attack_tick = 0

    def update(self, world, side):
        """在战斗推进前更新计划，并返回这一帧的按键指令。"""
        self.observer.before_tick(world, 1 - side)
        fighter, opponent = world.fighters[side], world.fighters[1 - side]
        mode = fighter.control_mode()
        ready = self.plan.ready(mode)
        if mode is None:
            self.context = None
            return ()
        context = context_for(world, side, mode)
        # 持续动作通常按原计划执行，新战术情景或新威胁可以打断它。
        changed = (self.context is not None and
                   (context.phase != self.context.phase or (context.danger and not self.context.danger)))
        gap_ends = mode != "ground_cancel" and fighter.age + 1 == self.next_attack_tick
        if ready or changed or gap_ends:
            self.context = context
            moves = self._moves(world, side, context, self.next_attack_tick)
            self.last_decision = self._choose(world, side, moves)
            self.plan.start(self.last_decision.action, mode)
        return self.plan.tick(fighter, opponent)

    def observe(self, world, side, actions, *, human_opponent=False):
        """记录双方生效的动作。只有引擎接受了我方出招，才开始计间隔。"""
        self.observer.after_tick(actions[1 - side], human=human_opponent)
        if actions[side] in ATTACK_ACTIONS:
            self.next_attack_tick = world.fighters[side].age + self.attack_interval

    @staticmethod
    def _moves(world, side, context, next_attack_tick):
        legal = legal_moves(world, side, context.mode)
        # age 只在有效战斗帧增长。命中取消属于原连段，可以在间隔内接必杀技。
        if context.mode != "ground_cancel" and world.fighters[side].age + 1 < next_attack_tick:
            legal = tuple(move for move in legal if move not in ATTACK_ACTIONS)
        return candidates(world, side, context, legal)

    def debug_state(self, world, side, *, human_opponent=False):
        """按当前局势读取下一次可行动时的预测，供调试面板使用。"""
        mode = world.fighters[side].control_mode()
        context = context_for(world, side, mode or "locked")
        other = 1 - side
        enemy_mode = world.fighters[other].control_mode()
        forecast = None
        if enemy_mode is not None:
            _, forecast = self._forecast(world, other, enemy_mode, self.observer.previous, {})
        evaluation = self.observer.evaluation
        summary = evaluation.summarize_human() if human_opponent else None
        current_kl = kl_divergence(forecast) if forecast is not None else None
        return DebugState(context, forecast, self.last_decision, bool(world.hitstop), summary,
                          current_kl, tuple(evaluation.kl_trend))

    def _choose(self, world, side, moves):
        """在限时内比较候选首招，优先选择模拟平均收益较高的动作。"""
        started = perf_counter()
        if not self.search or len(moves) == 1:
            source = "only_move" if self.search else "rules"
            return Decision(moves[0], 0, None, 0.0, 0.0, source)
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
        # 对手的动作分布越分散，越值得多采样。起身攻防多留几帧观察后续交手。
        target_trials = 5 if entropy is not None and entropy > 0.72 else 3
        horizon = 24 if self.context.phase in ("wake", "pressure") else 20
        totals = [0.0] * len(moves)
        trials = 0
        for _ in range(target_trials):
            # 同一轮的候选使用相同的随机种子，减少抽样运气对动作排名的影响。
            seed = self.rng.getrandbits(64)
            values = []
            for move in moves:
                score = self._rollout(world, side, move, previous, seed, horizon, deadline, forecasts)
                if score is None:
                    break
                values.append(score)
            # 超时留下的半轮结果不计入总分，保证各候选的样本数一致。
            if len(values) != len(moves):
                break
            totals = [total + value for total, value in zip(totals, values)]
            trials += 1
            best, second = sorted(totals, reverse=True)[:2]
            if trials >= 2 and best - second >= 12 * trials:
                break
        # 零轮时总分全相同，默认选第一个规则动作。只有一轮且优势很小时也回退。
        best = max(range(len(moves)), key=totals.__getitem__)
        source = "search" if trials else "deadline"
        if trials == 1 and totals[best] - totals[0] < 2:
            best = 0
            source = "close_scores"
        return Decision(moves[best], trials, entropy, trust, (perf_counter() - started) * 1000,
                        source)

    def _forecast(self, world, side, mode, previous, forecasts):
        """在一次选招内复用相同情景、动作历史和合法动作对应的预测。"""
        context = context_for(world, side, mode)
        legal = legal_moves(world, side, mode)
        key = (context, previous, legal)
        forecast = forecasts.get(key)
        if forecast is None:
            forecast = self.model.predict(context, previous, legal, order=self.model_order)
            forecasts[key] = forecast
        return context, forecast

    def _rollout(self, current, side, first_move, previous, seed, horizon, deadline, forecasts):
        """模拟一个候选首招。后续我方按规则续演，对手按预测动作分布采样。"""
        if perf_counter() >= deadline:
            return None
        # 使用隔离的战斗副本，并隐藏对手尚未完成的指令输入历史。
        world = current.fork(viewer=side)
        rng = Random(seed)
        other = 1 - side
        my_run, enemy_run = ActionRun(), ActionRun()
        fighter, enemy = world.fighters[side], world.fighters[other]
        my_run.start(first_move, fighter.control_mode())
        next_attack_tick = self.next_attack_tick
        recorded_enemy_move = True
        for tick in range(horizon):
            if tick % 4 == 0 and perf_counter() >= deadline:
                return None
            if world.hitstop:
                # 命中停顿仍推进回合时钟，但双方的动作计划不消耗输入帧。
                world.step()
            else:
                mode = fighter.control_mode()
                gap_ends = mode not in (None, "ground_cancel") and fighter.age + 1 == next_attack_tick
                if my_run.ready(mode) or gap_ends:
                    context = context_for(world, side, mode)
                    move = self._moves(world, side, context, next_attack_tick)[0]
                    my_run.start(move, mode)
                enemy_mode = enemy.control_mode()
                if enemy_run.ready(enemy_mode):
                    context, forecast = self._forecast(world, other, enemy_mode, previous, forecasts)
                    move = forecast.sample(rng.random())
                    delay = self.model.delay(context, move, forecast.trust)
                    # 观测延迟以动作生效为终点。扣掉指令占用的帧，得到起手前的等待。
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
                # 双方按键都基于推进前的状态决定，再由战斗引擎统一结算。
                actions = world.step(inputs)
                if actions[side] in ATTACK_ACTIONS:
                    next_attack_tick = fighter.age + self.attack_interval
                # 每个模拟动作只记录一次。必杀技输入完成后，才采用引擎确认的动作。
                if (not recorded_enemy_move and actions[other] is not None
                        and enemy_run.age >= len(INPUT_SEQUENCE[enemy_run.move])):
                    previous = actions[other]
                    recorded_enemy_move = True
            if world.finished:
                # 终局直接按胜负计分，让胜负对搜索结果的影响高于普通局势收益。
                if world.winner is None:
                    return 0
                return config.MAX_HEALTH + 1 if world.winner == side else -config.MAX_HEALTH - 1
        return self._score(current, world, side)

    @staticmethod
    def _score(current, world, side):
        """以净伤害为主，辅以距离、版边空间和受击硬直差评估非终局。"""
        other = 1 - side
        start, start_enemy = current.fighters[side], current.fighters[other]
        fighter, enemy = world.fighters[side], world.fighters[other]
        net_damage = (start_enemy.health - enemy.health) - (start.health - fighter.health)
        distance = abs(fighter.x - enemy.x)
        previous_distance = abs(start.x - start_enemy.x)
        approach = previous_distance - distance
        # 时间将尽且我方领先时，拉开距离有利于保住血量优势。
        if world.timer <= 8 and start.health > start_enemy.health:
            approach = -approach
        wall_advantage = min(100, wall_space(fighter)) - min(100, wall_space(enemy))
        stun_advantage = min(14, enemy.hitstun) - min(14, fighter.hitstun)
        return net_damage + 0.05 * approach + 0.025 * wall_advantage + 0.2 * stun_advantage
