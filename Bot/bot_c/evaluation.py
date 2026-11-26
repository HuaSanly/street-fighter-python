"""对实战预测打分，并记录相对通用先验的分布变化。"""
from collections import deque
from dataclasses import dataclass
from math import fsum, log


def kl_divergence(forecast):
    """用同一组合法动作计算 KL(在线混合分布 ∥ 通用先验)，单位为 nat。"""
    value = fsum(p * log(p / q) for p, q in zip(forecast.probabilities, forecast.baseline)
                 if p > 0)
    return max(0.0, value)  # 忽略浮点舍入产生的微小负值。


@dataclass(frozen=True)
class HumanPredictionSummary:
    count: int
    hit_rate: float | None
    gain: float | None
    unmatched: int


class PredictionEvaluation:
    WINDOW = 50
    PROBE_PERIOD = 10

    def __init__(self):
        self.recent = deque(maxlen=self.WINDOW)
        self.unmatched = 0
        self.valid_observations = 0
        self.kl_trend = deque([0.0], maxlen=32)

    def record(self, forecast, action, *, human):
        """使用观察窗口打开时保存的概率，返回是否到了固定情景的采样时点。"""
        self.valid_observations += 1
        if human:
            index = forecast.actions.index(action)
            # 概率并列时保留动作表的顺序，与面板的排序一致。
            first = max(range(len(forecast.actions)), key=forecast.probabilities.__getitem__)
            gain = log(forecast.probabilities[index] / forecast.baseline[index])
            self.recent.append((index == first, gain))
        return self.valid_observations % self.PROBE_PERIOD == 0

    def summarize_human(self):
        count = len(self.recent)
        if not count:
            return HumanPredictionSummary(count, None, None, self.unmatched)
        return HumanPredictionSummary(count, sum(hit for hit, _ in self.recent) / count,
                                      fsum(gain for _, gain in self.recent) / count,
                                      self.unmatched)
