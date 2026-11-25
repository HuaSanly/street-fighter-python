"""Online opponent prediction at discrete opportunities to choose an action."""
from dataclasses import dataclass
from math import log

from .tactics import HELD_MOVES, WINDOW, context_for, legal_moves, prior


@dataclass(frozen=True)
class Forecast:
    actions: tuple
    probabilities: tuple
    individual: tuple
    baseline: tuple
    entropy: float
    trust: float
    history: tuple | None

    def sample(self, uniform):
        for action, probability in zip(self.actions, self.probabilities):
            uniform -= probability
            if uniform < 0:
                return action
        return self.actions[-1]


class OpponentModel:
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
        return ((context.phase, context.mode), context, (context, previous))

    def _counts(self, key):
        tick, counts = self.rows.get(key, (self.observations, {}))
        return counts, self.DECAY ** (self.observations - tick)

    def predict(self, context, previous, legal, *, order=1):
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
                posterior = tuple((weight + self.PRIOR_STRENGTH * parent)
                                  / (total + self.PRIOR_STRENGTH)
                                  for weight, parent in zip(weights, individual))
                if key == keys[2]:
                    history = (individual, posterior)
                    if order == "auto":
                        # Compare both predictions on the same recent observations.
                        gain = self.history_gain.get(group, 0.0)
                        weight = max(0.0, min(1.0, 6 * (gain - 0.025)))
                        individual = tuple(p + weight * (q - p) for p, q in zip(*history))
                        support = support + weight * (total - 0.75 * support)
                        continue
                individual = posterior
                support = total + 0.25 * support

        gain = self.recent_gain.get(group, 0.0)
        quality = max(0.15, 1.0 + gain)
        trust = min(0.92, support / (support + 8.0) * min(1.0, quality))
        probabilities = tuple(trust * p + (1 - trust) * base
                              for p, base in zip(individual, baseline))
        entropy = -sum(p * log(p) for p in individual) / log(len(legal)) if len(legal) > 1 else 0.0
        return Forecast(legal, probabilities, individual, baseline, entropy, trust, history)

    def update(self, context, previous, forecast, action, delay):
        index = forecast.actions.index(action)
        group = (context.phase, context.mode)
        gain = log(forecast.individual[index] / forecast.baseline[index])
        self.recent_gain[group] = 0.9 * self.recent_gain.get(group, 0.0) + 0.1 * gain
        if forecast.history is not None:
            zero, first = forecast.history
            gain = log(first[index] / zero[index])
            self.history_gain[group] = 0.9 * self.history_gain.get(group, 0.0) + 0.1 * gain
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
        measured = self.delays.get(((context.phase, context.mode), action), 0)
        return round(trust * measured)


class OpponentObserver:
    def __init__(self, model, *, order=1):
        self.model = model
        self.order = order
        self.reset()

    def reset(self):
        self.previous = self.last_visible = self.group = self.pending = None
        self.remaining = self.elapsed = 0

    def before_tick(self, world, side):
        mode = world.fighters[side].control_mode()
        if mode is None:
            self.group = self.pending = self.last_visible = None
            self.remaining = 0
            return
        context = context_for(world, side, mode)
        group = (context.phase, mode)
        if group != self.group:
            self.group = group
            self.pending = self.last_visible = None
            self.remaining = 0
        if self.remaining == 0:
            legal = legal_moves(world, side, mode)
            self.pending = (context, self.model.predict(context, self.previous, legal,
                                                        order=self.order))
            self.remaining = WINDOW
            self.elapsed = 0

    def after_tick(self, action):
        changed = action != self.last_visible
        if action is not None:
            self.last_visible = action
        if self.remaining:
            self.remaining -= 1
        if self.pending is None:
            return
        context, forecast = self.pending
        if action in forecast.actions and (changed or action not in HELD_MOVES):
            self.model.update(context, self.previous, forecast, action, self.elapsed)
            self.previous = action
            self.pending = None
            if action in HELD_MOVES:
                # A subsequent press can start before this hold's window ends.
                self.remaining = 0
        elif self.remaining == 0:
            # A continued hold counts as one renewal for the whole window.
            action = action if action in forecast.actions else "wait"
            self.model.update(context, self.previous, forecast, action, 0)
            self.previous = action
            self.pending = None
        self.elapsed += 1
