"""按可行动窗口统计对手的动作，在线预测下一次选择。"""
from dataclasses import dataclass
from math import log

from .evaluation import PredictionEvaluation, kl_divergence
from .tactics import GROUND_MOVES, HELD_MOVES, WINDOW, Context, context_for, legal_moves, prior


# 固定距离、行动权、上一动作和合法动作集，只比较模型随实战观察更新的变化。
KL_PROBE = Context("neutral", "close", "ground", False, False)


@dataclass(frozen=True)
class Forecast:
    """同一次预测的动作及分布。采样使用混合概率，熵基于平滑后的个性化分布。"""

    actions: tuple
    probabilities: tuple
    individual: tuple
    baseline: tuple
    entropy: float
    trust: float
    history: tuple | None

    def sample(self, uniform):
        """用一个位于 [0, 1) 的随机数从混合分布中抽取动作。"""
        for action, probability in zip(self.actions, self.probabilities):
            uniform -= probability
            if uniform < 0:
                return action
        return self.actions[-1]


class OpponentModel:
    """用衰减计数学习对手，按近期预测表现决定是否采用一阶动作历史。"""

    DECAY = 0.993
    PRIOR_STRENGTH = 7

    def __init__(self):
        self.rows = {}
        self.recent_gain = {}
        self.history_gain = {}
        self.delays = {}
        self.losses = {}
        self.observations = 0

    @staticmethod
    def keys(context, previous):
        # 从粗到细依次为情景与行动模式、完整情景特征、再加上一次动作。
        return ((context.phase, context.mode), context, (context, previous))

    def _counts(self, key):
        """按新增观测次数衰减旧计数，在读取时计算衰减倍率。"""
        tick, counts = self.rows.get(key, (self.observations, {}))
        return counts, self.DECAY ** (self.observations - tick)

    def predict(self, context, previous, legal, *, order=1):
        """从通用先验逐层平滑。order=None 只用先验，0 用情景，1 加上动作历史。"""
        baseline = prior(context, legal)
        individual = baseline
        support = 0.0
        history = None
        group = (context.phase, context.mode)
        if order is not None:
            keys = self.keys(context, previous)
            for key in keys[:2] if order == 0 else keys:
                counts, decay = self._counts(key)
                weights = [counts.get(action, 0) * decay for action in legal]
                total = sum(weights)
                # 上一层分布充当伪计数。细分情景样本少时，预测更接近粗粒度分布。
                posterior = tuple((weight + self.PRIOR_STRENGTH * parent)
                                  / (total + self.PRIOR_STRENGTH)
                                  for weight, parent in zip(weights, individual))
                if key == keys[2]:
                    history = (individual, posterior)
                    if order == "auto":
                        # 在相同的近期样本上比较零阶与一阶。历史确有帮助时才提高一阶权重。
                        gain = self.history_gain.get(group, 0.0)
                        weight = max(0.0, min(1.0, 6 * (gain - 0.025)))
                        individual = tuple(p + weight * (q - p) for p, q in zip(*history))
                        support = support + weight * (total - 0.75 * support)
                        continue
                individual = posterior
                support = total + 0.25 * support

        # 可信度结合有效样本量和近期预测表现。上限保证通用先验始终占一定权重。
        gain = self.recent_gain.get(group, 0.0)
        quality = max(0.15, 1.0 + gain)
        trust = min(0.92, support / (support + 8.0) * min(1.0, quality))
        probabilities = tuple(trust * p + (1 - trust) * base
                              for p, base in zip(individual, baseline))
        # 除以 log(合法动作数) 把熵归一化到 [0, 1]，用于衡量动作分布的分散程度。
        entropy = -sum(p * log(p) for p in individual) / log(len(legal)) if len(legal) > 1 else 0.0
        return Forecast(legal, probabilities, individual, baseline, entropy, trust, history)

    def update(self, context, previous, forecast, action, delay):
        """先评估动作发生前的预测，再把这次真实动作计入模型。"""
        index = forecast.actions.index(action)
        group = (context.phase, context.mode)
        gain = log(forecast.individual[index] / forecast.baseline[index])
        self.recent_gain[group] = 0.9 * self.recent_gain.get(group, 0.0) + 0.1 * gain
        if forecast.history is not None:
            zero, first = forecast.history
            gain = log(first[index] / zero[index])
            self.history_gain[group] = 0.9 * self.history_gain.get(group, 0.0) + 0.1 * gain
        # 跑分按情景汇总两套预测在同一批真实动作上的对数损失。
        count, loss, base_loss = self.losses.get(context.phase, (0, 0.0, 0.0))
        self.losses[context.phase] = (count + 1, loss - log(forecast.probabilities[index]),
                                      base_loss - log(forecast.baseline[index]))
        self.observations += 1
        for key in self.keys(context, previous):
            counts, decay = self._counts(key)
            counts = {move: count * decay for move, count in counts.items() if count * decay >= 0.02}
            counts[action] = counts.get(action, 0) + 1
            self.rows[key] = (self.observations, counts)
        timing = (group, action)
        self.delays[timing] = 0.8 * self.delays.get(timing, delay) + 0.2 * delay

    def delay(self, context, action, trust):
        """按模型可信度缩放该情景下观测到的动作延迟。"""
        measured = self.delays.get(((context.phase, context.mode), action), 0)
        return round(trust * measured)


class OpponentObserver:
    """将逐帧生效的输入整理成模型样本，持续按住的动作按窗口计数。"""

    def __init__(self, model, *, order=1):
        self.model = model
        self.order = order
        self.evaluation = PredictionEvaluation()
        self.reset()

    def reset(self):
        self.previous = self.last_visible = self.group = self.pending = None
        self.remaining = self.elapsed = 0
        self.pending_unmatched = False

    def before_tick(self, world, side):
        """战斗推进前确定对手是否拥有决策机会，并为新窗口保存预测。"""
        mode = world.fighters[side].control_mode()
        if mode is None:
            self.group = self.pending = self.last_visible = None
            self.remaining = 0
            return
        context = context_for(world, side, mode)
        group = (context.phase, mode)
        if group != self.group:
            # 进入新情景或获得不同的行动权后，重新打开观察窗口。
            self.group = group
            self.pending = self.last_visible = None
            self.remaining = 0
        if self.remaining == 0:
            legal = legal_moves(world, side, mode)
            self.pending = (context, self.model.predict(context, self.previous, legal,
                                                        order=self.order))
            self.remaining = WINDOW
            self.elapsed = 0
            self.pending_unmatched = False

    def after_tick(self, action, *, human=False):
        """使用战斗引擎确认的动作完成一次观察。"""
        changed = action != self.last_visible
        if action is not None:
            self.last_visible = action
        if self.remaining:
            self.remaining -= 1
        if self.pending is None:
            return
        context, forecast = self.pending
        known = action in forecast.actions
        if not known and action is not None and not self.pending_unmatched:
            self.pending_unmatched = True
            if human and len(forecast.actions) > 1:
                self.evaluation.unmatched += 1
        if known and (changed or action not in HELD_MOVES):
            self._complete(context, forecast, action, self.elapsed, human=human)
            if action in HELD_MOVES:
                # 持续动作可以很快接出招，立即允许下一帧开启新窗口。
                self.remaining = 0
        elif self.remaining == 0:
            # 整个窗口维持原动作时只计一次。没有可归类的动作时记为等待。
            self._complete(context, forecast, action if known else "wait", 0, human=human)
        self.elapsed += 1

    def _complete(self, context, forecast, action, delay, *, human):
        probe_due = False
        # 评分排除动作集不匹配及没有实际选择的窗口。训练仍沿用原来的等待规则。
        if not self.pending_unmatched and len(forecast.actions) > 1:
            probe_due = self.evaluation.record(forecast, action, human=human)
        self.model.update(context, self.previous, forecast, action, delay)
        self.previous = action
        self.pending = None
        if probe_due:
            probe = self.model.predict(KL_PROBE, "wait", GROUND_MOVES, order=self.order)
            self.evaluation.kl_trend.append(kl_divergence(probe))
