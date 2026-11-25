import math
import random

import pygame

HIT_COLORS = [(255, 255, 190), (255, 210, 70), (255, 140, 40), (255, 90, 30)]
BLOCK_COLORS = [(160, 205, 255), (210, 235, 255), (110, 160, 255)]


class _Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size")

    def __init__(self, x, y, heavy, blocked):
        speed = random.uniform(3, 9 if heavy else 6.5)
        angle = random.uniform(0, 6.283)
        self.x, self.y = x, y
        self.vx = speed * random.uniform(0.6, 1.0) * (1 if random.random() < 0.5 else -1)
        self.vy = -abs(speed * random.uniform(0.3, 1.0)) * random.choice((1, -0.4))
        self.max_life = random.randint(10, 22)
        self.life = self.max_life
        self.color = random.choice(BLOCK_COLORS if blocked else HIT_COLORS)
        self.size = random.uniform(2.5, 5.5 if heavy else 4)
        _ = angle  # direction handled above; kept for tweak-ability

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.45
        self.vx *= 0.92
        self.life -= 1

    def draw(self, surf, ox, oy):
        t = self.life / self.max_life
        r = max(1, int(self.size * t))
        pygame.draw.circle(surf, self.color, (int(self.x + ox), int(self.y + oy)), r)


class _Ring:
    def __init__(self, x, y, heavy, blocked):
        self.x, self.y = x, y
        self.age = 0
        self.max_age = 14 if heavy else 10
        self.max_r = 60 if heavy else 38
        self.color = (150, 200, 255) if blocked else (255, 235, 160)

    def update(self):
        self.age += 1

    def draw(self, surf, ox, oy):
        t = self.age / self.max_age
        r = int(self.max_r * t)
        alpha = int(200 * (1 - t))
        if r < 2:
            return
        ring = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(ring, (*self.color, alpha), (r + 2, r + 2), r,
                           width=max(2, int(5 * (1 - t))))
        surf.blit(ring, (self.x - r - 2 + ox, self.y - r - 2 + oy))


class Fireball:
    """Procedurally drawn hadouken projectile: pulsing glow + ember trail."""
    W, H = 48, 36

    def __init__(self, x, y, direction, owner, palette, attack, speed):
        self.x, self.y = float(x), float(y)
        self.direction = direction
        self.owner = owner
        self.palette = palette      # (dark, mid, light)
        self.attack = attack
        self.speed = speed
        self.age = 0

    @property
    def rect(self):
        return pygame.Rect(int(self.x - self.W / 2), int(self.y - self.H / 2),
                           self.W, self.H)

    def update(self, effects=None):
        self.x += self.direction * self.speed
        self.age += 1
        if effects is not None:
            for _ in range(2):
                effects.ember(self.x - self.direction * random.uniform(18, 34),
                              self.y + random.uniform(-11, 11), self.palette)

    def draw(self, surf, offset=(0, 0)):
        ox, oy = offset
        cx, cy = int(self.x + ox), int(self.y + oy)
        pulse = 1 + 0.14 * math.sin(self.age * 0.55)
        glow_r = int(40 * pulse)
        glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*self.palette[0], 90), (glow_r, glow_r), glow_r)
        pygame.draw.circle(glow, (*self.palette[1], 70), (glow_r, glow_r),
                           int(glow_r * 0.72))
        surf.blit(glow, (cx - glow_r, cy - glow_r))
        pygame.draw.circle(surf, self.palette[1], (cx, cy), int(21 * pulse))
        pygame.draw.circle(surf, self.palette[2],
                           (cx + self.direction * 3, cy), int(14 * pulse))
        pygame.draw.circle(surf, (255, 255, 255),
                           (cx + self.direction * 5, cy), max(4, int(7 * pulse)))


class Effects:
    def __init__(self):
        self.particles = []
        self.rings = []
        self.shake_mag = 0.0
        self.shake_ticks = 0

    def hit_spark(self, pos, heavy=False, blocked=False):
        x, y = pos
        count = 8 if blocked else (18 if heavy else 12)
        self.particles += [_Particle(x, y, heavy, blocked) for _ in range(count)]
        self.rings.append(_Ring(x, y, heavy, blocked))

    def ember(self, x, y, palette):
        """Small drifting flame particle (fireball trails, shoryuken rise)."""
        p = _Particle(x, y, False, False)
        p.vx = random.uniform(-1.4, 1.4)
        p.vy = random.uniform(-1.6, 0.4)
        p.color = random.choice(palette[1:])
        p.max_life = random.randint(8, 16)
        p.life = p.max_life
        p.size = random.uniform(2, 4.5)
        self.particles.append(p)

    def shake(self, magnitude, ticks):
        self.shake_mag = max(self.shake_mag, magnitude)
        self.shake_ticks = max(self.shake_ticks, ticks)

    def update(self):
        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if p.life > 0]
        for r in self.rings:
            r.update()
        self.rings = [r for r in self.rings if r.age < r.max_age]
        if self.shake_ticks > 0:
            self.shake_ticks -= 1
            if self.shake_ticks == 0:
                self.shake_mag = 0
            else:
                self.shake_mag *= 0.9

    def offset(self):
        if self.shake_ticks <= 0:
            return 0, 0
        m = self.shake_mag
        return random.uniform(-m, m), random.uniform(-m, m)

    def draw(self, surf, offset=(0, 0)):
        ox, oy = offset
        for r in self.rings:
            r.draw(surf, ox, oy)
        for p in self.particles:
            p.draw(surf, ox, oy)
