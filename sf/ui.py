"""Fight HUD: health bars with damage trails, round timer, round pips,
combo counters and animated center-screen announcements."""
import pygame

from . import config


def outlined(font, text, color, outline=(10, 10, 20), px=2):
    base = font.render(text, True, color)
    out = font.render(text, True, outline)
    surf = pygame.Surface((base.get_width() + px * 2, base.get_height() + px * 2),
                          pygame.SRCALPHA)
    for dx in (-px, 0, px):
        for dy in (-px, 0, px):
            if dx or dy:
                surf.blit(out, (px + dx, px + dy))
    surf.blit(base, (px, px))
    return surf


def ease_out_back(t):
    c1, c3 = 1.70158, 2.70158
    t -= 1
    return 1 + c3 * t * t * t + c1 * t * t


def health_color(pct):
    if pct > 0.5:
        return (90 + int((1 - pct) * 2 * 165), 220, 70)   # green -> yellow
    return (255, int(220 * pct * 2), 50)                   # yellow -> red


class HealthBar:
    W, H = 330, 26

    def __init__(self, side, name):
        self.side = side            # 0 = left (P1), 1 = right (P2)
        self.name = name
        self.trail = float(config.MAX_HEALTH)

    def update(self, health):
        if self.trail > health:
            self.trail = max(health, self.trail - 6)  # red trail drains slowly

    def draw(self, surf, font, health):
        x = 30 if self.side == 0 else config.CANVAS_W - 30 - self.W
        y = 24
        pct = max(0.0, health / config.MAX_HEALTH)
        trail_pct = max(0.0, self.trail / config.MAX_HEALTH)

        pygame.draw.rect(surf, (12, 12, 24), (x - 4, y - 4, self.W + 8, self.H + 8), border_radius=6)
        pygame.draw.rect(surf, (40, 20, 20), (x, y, self.W, self.H), border_radius=4)

        def fill(p, color):
            w = int(self.W * p)
            if w <= 0:
                return
            rx = x if self.side == 0 else x + self.W - w  # drains toward center
            pygame.draw.rect(surf, color, (rx, y, w, self.H), border_radius=4)

        fill(trail_pct, (200, 40, 40))
        fill(pct, health_color(pct))
        # subtle top shine
        shine = pygame.Surface((int(self.W * pct) or 1, self.H // 2), pygame.SRCALPHA)
        shine.fill((255, 255, 255, 45))
        surf.blit(shine, (x if self.side == 0 else x + self.W - shine.get_width(), y))
        pygame.draw.rect(surf, (230, 230, 240), (x - 4, y - 4, self.W + 8, self.H + 8),
                         width=2, border_radius=6)

        label = outlined(font, self.name, (255, 255, 255))
        lx = x if self.side == 0 else x + self.W - label.get_width()
        surf.blit(label, (lx, y + self.H + 8))


class Announcer:
    """Center-screen text with a springy scale-in and fade-out."""

    def __init__(self, assets):
        self.assets = assets
        self.items = []  # dicts: text, color, age, life, size, y

    def say(self, text, color=(255, 220, 60), life=75, size=42, y=None):
        self.items.append({"text": text, "color": color, "age": 0,
                           "life": life, "size": size,
                           "y": y if y is not None else config.CANVAS_H // 2 - 60})

    def clear(self):
        self.items.clear()

    def update(self):
        for it in self.items:
            it["age"] += 1
        self.items = [it for it in self.items if it["age"] < it["life"]]

    def draw(self, surf):
        for it in self.items:
            t_in = min(1.0, it["age"] / 14)
            scale = max(0.05, ease_out_back(t_in))
            fade_start = it["life"] - 18
            alpha = 255 if it["age"] < fade_start else int(255 * (it["life"] - it["age"]) / 18)
            font = self.assets.font(it["size"])
            text = outlined(font, it["text"], it["color"], px=3)
            if scale != 1.0:
                w = max(1, int(text.get_width() * scale))
                h = max(1, int(text.get_height() * scale))
                text = pygame.transform.smoothscale(text, (w, h))
            text.set_alpha(alpha)
            surf.blit(text, (config.CANVAS_W / 2 - text.get_width() / 2,
                             it["y"] - text.get_height() / 2))


class HUD:
    def __init__(self, assets, names):
        self.assets = assets
        self.bars = [HealthBar(0, names[0] + "  P1"), HealthBar(1, names[1] + "  P2")]
        self.combo = [0, 0]
        self.combo_pop = [0, 0]

    def set_combo(self, player, count):
        self.combo[player] = count
        if count >= 2:
            self.combo_pop[player] = 12

    def update(self, fighters):
        for bar, f in zip(self.bars, fighters):
            bar.update(f.health)
        self.combo_pop = [max(0, c - 1) for c in self.combo_pop]

    def draw(self, surf, fighters, timer_seconds, wins, round_num):
        small = self.assets.font(12)
        for bar, f in zip(self.bars, fighters):
            bar.draw(surf, small, f.health)

        # timer
        t_font = self.assets.font(30)
        color = (255, 255, 255) if timer_seconds > 10 else (255, 80, 60)
        timer = outlined(t_font, f"{max(0, timer_seconds):02d}", color, px=3)
        surf.blit(timer, (config.CANVAS_W / 2 - timer.get_width() / 2, 20))
        rn = outlined(small, f"ROUND {round_num}", (255, 220, 120))
        surf.blit(rn, (config.CANVAS_W / 2 - rn.get_width() / 2, 62))

        # round win pips
        for side in (0, 1):
            for i in range(config.ROUNDS_TO_WIN):
                cx = (config.CANVAS_W / 2 - 84 - i * 26) if side == 0 else \
                     (config.CANVAS_W / 2 + 84 + i * 26)
                won = wins[side] > i
                pygame.draw.circle(surf, (255, 210, 60) if won else (60, 60, 70),
                                   (int(cx), 36), 9)
                pygame.draw.circle(surf, (240, 240, 250), (int(cx), 36), 9, width=2)

        # combo counters
        for side in (0, 1):
            if self.combo[side] >= 2:
                pop = 1 + self.combo_pop[side] / 24
                font = self.assets.font(22)
                text = outlined(font, f"{self.combo[side]} HITS!", (255, 160, 40), px=3)
                w = int(text.get_width() * pop)
                h = int(text.get_height() * pop)
                text = pygame.transform.smoothscale(text, (w, h))
                x = 60 if side == 0 else config.CANVAS_W - 60 - w
                surf.blit(text, (x, 120))
