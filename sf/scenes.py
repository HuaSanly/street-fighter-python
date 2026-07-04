"""Game scenes: menu -> character select -> map select -> fight."""
import random

import pygame

from . import config
from .combat import (HITSTOP_LIGHT, HITSTOP_HEAVY, HITSTOP_BLOCK,
                     SPECIALS, FIREBALL_SPEED)
from .effects import Effects, Fireball
from .fighter import Fighter
from .ui import HUD, Announcer, outlined

P1_CONTROLS = {"left": pygame.K_a, "right": pygame.K_d, "jump": pygame.K_w,
               "down": pygame.K_s,
               "lp": pygame.K_j, "hp": pygame.K_k, "lk": pygame.K_u,
               "hk": pygame.K_i, "block": pygame.K_l}
P2_CONTROLS = {"left": pygame.K_LEFT, "right": pygame.K_RIGHT, "jump": pygame.K_UP,
               "down": pygame.K_DOWN,
               "lp": pygame.K_KP4, "hp": pygame.K_KP5, "lk": pygame.K_KP1,
               "hk": pygame.K_KP2, "block": pygame.K_KP6}

# fireball palettes (dark, mid, light): Ryu blue, Ken orange
FIRE_COLORS = {"ryu": ((30, 60, 200), (80, 140, 255), (175, 215, 255)),
               "ken": ((200, 60, 10), (255, 145, 45), (255, 220, 150))}

P1_COLOR = (255, 80, 60)
P2_COLOR = (80, 140, 255)


class _NoKeys:
    def __getitem__(self, _):
        return False


NO_KEYS = _NoKeys()
NO_PRESSED = frozenset()


def cover(img, size):
    """Scale an image to fully cover `size`, cropping the overflow."""
    w, h = img.get_size()
    scale = max(size[0] / w, size[1] / h)
    scaled = pygame.transform.smoothscale(img, (int(w * scale), int(h * scale)))
    surf = pygame.Surface(size)
    surf.blit(scaled, ((size[0] - scaled.get_width()) // 2,
                       (size[1] - scaled.get_height()) // 2))
    return surf


class Scene:
    def __init__(self, game):
        self.game = game
        self.assets = game.assets

    def handle(self, events, held):
        pass

    def update(self):
        pass

    def draw(self, surf):
        pass


# --- MENU ---
class MenuScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        bg = self.assets.images.get("LogInBG")
        self.bg = cover(bg, (config.CANVAS_W, config.CANVAS_H)) if bg else None
        dark = pygame.Surface((config.CANVAS_W, config.CANVAS_H), pygame.SRCALPHA)
        dark.fill((0, 0, 10, 150))
        if self.bg:
            self.bg.blit(dark, (0, 0))
        self.tick = 0
        self.assets.music("home.wav", 0.5)

    def handle(self, events, held):
        for e in events:
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.assets.play("Select")
                self.game.change(CharSelectScene(self.game))

    def update(self):
        self.tick += 1

    def draw(self, surf):
        if self.bg:
            surf.blit(self.bg, (0, 0))
        else:
            surf.fill((15, 10, 30))

        big = self.assets.font(52)
        title1 = outlined(big, "STREET", (255, 220, 60), px=4)
        title2 = outlined(big, "FIGHTER", (255, 120, 40), px=4)
        # gentle floating bob
        bob = int(4 * __import__("math").sin(self.tick / 30))
        surf.blit(title1, (config.CANVAS_W / 2 - title1.get_width() / 2, 110 + bob))
        surf.blit(title2, (config.CANVAS_W / 2 - title2.get_width() / 2, 175 + bob))
        sub = outlined(self.assets.font(14), "PYTHON EDITION", (200, 200, 220))
        surf.blit(sub, (config.CANVAS_W / 2 - sub.get_width() / 2, 250))

        if (self.tick // 32) % 2 == 0:
            prompt = outlined(self.assets.font(20), "PRESS ENTER", (255, 255, 255), px=3)
            surf.blit(prompt, (config.CANVAS_W / 2 - prompt.get_width() / 2, 370))

        hint = outlined(self.assets.font(10),
                        "P1: WASD + JKUI, L BLOCK    P2: ARROWS + NUMPAD 4/5/1/2, 6 BLOCK",
                        (170, 170, 190))
        surf.blit(hint, (config.CANVAS_W / 2 - hint.get_width() / 2, config.CANVAS_H - 40))


# CHAR SELECT
class CharSelectScene(Scene):
    CHARS = ["ryu", "ken"]

    def __init__(self, game):
        super().__init__(game)
        self.bg = self.assets.char_select_bg()
        self.cursor = [0, 1]
        self.confirmed = [False, False]
        self.done_timer = 0
        self.portraits = {}
        for c in self.CHARS:
            img = self.assets.images.get(f"{c}Select")
            if img:
                self.portraits[c] = pygame.transform.smoothscale(
                    img, (200, int(img.get_height() * 200 / img.get_width())))
        self.names = {c: self.assets.images.get(f"{c}_name") for c in self.CHARS}

    def handle(self, events, held):
        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            if e.key == pygame.K_ESCAPE:
                self.game.change(MenuScene(self.game))
                return
            # P1
            if not self.confirmed[0]:
                if e.key in (pygame.K_a, pygame.K_d):
                    self.cursor[0] ^= 1
                    self.assets.play("Select", 0.4)
                elif e.key == pygame.K_j:
                    self.confirmed[0] = True
                    self.assets.play("Select")
            # P2
            if not self.confirmed[1]:
                if e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    self.cursor[1] ^= 1
                    self.assets.play("Select", 0.4)
                elif e.key in (pygame.K_KP4, pygame.K_KP_ENTER, pygame.K_RSHIFT):
                    self.confirmed[1] = True
                    self.assets.play("Select")

    def update(self):
        self.bg.tick()
        if all(self.confirmed):
            self.done_timer += 1
            if self.done_timer >= 50:
                self.game.change(MapSelectScene(
                    self.game, self.CHARS[self.cursor[0]], self.CHARS[self.cursor[1]]))

    def draw(self, surf):
        surf.blit(self.bg.frame, (0, 0))
        shade = pygame.Surface((config.CANVAS_W, config.CANVAS_H), pygame.SRCALPHA)
        shade.fill((0, 0, 20, 90))
        surf.blit(shade, (0, 0))

        title = outlined(self.assets.font(24), "CHOOSE YOUR FIGHTER", (255, 220, 60), px=3)
        surf.blit(title, (config.CANVAS_W / 2 - title.get_width() / 2, 30))

        # the two selectable slots in the middle
        slot_w, slot_h = 150, 190
        for i, char in enumerate(self.CHARS):
            x = config.CANVAS_W / 2 - slot_w - 20 + i * (slot_w + 40)
            y = 150
            rect = pygame.Rect(int(x), y, slot_w, slot_h)
            pygame.draw.rect(surf, (20, 20, 40), rect, border_radius=8)
            portrait = self.portraits.get(char)
            if portrait:
                p = pygame.transform.smoothscale(
                    portrait, (slot_w - 16, int(portrait.get_height() * (slot_w - 16) / portrait.get_width())))
                surf.blit(p, p.get_rect(center=rect.center))
            pygame.draw.rect(surf, (120, 120, 150), rect, width=2, border_radius=8)
            # player cursors
            for pl, color in ((0, P1_COLOR), (1, P2_COLOR)):
                if self.cursor[pl] == i:
                    grow = 6 + pl * 6
                    r = rect.inflate(grow * 2, grow * 2)
                    pygame.draw.rect(surf, color, r, width=4, border_radius=10)
                    tag = outlined(self.assets.font(12), f"P{pl + 1}", color)
                    ty = r.top - 20 if pl == 0 else r.bottom + 6
                    surf.blit(tag, (r.centerx - tag.get_width() / 2, ty))

        # confirmed picks: big panels on each side
        for pl, color, side in ((0, P1_COLOR, 0), (1, P2_COLOR, 1)):
            char = self.CHARS[self.cursor[pl]]
            portrait = self.portraits.get(char)
            if portrait:
                img = portrait if self.confirmed[pl] else portrait.copy()
                if not self.confirmed[pl]:
                    img.set_alpha(140)
                x = 40 if side == 0 else config.CANVAS_W - 40 - img.get_width()
                surf.blit(img, (x, 170))
                name = self.names.get(char)
                if name:
                    n = pygame.transform.smoothscale(
                        name, (160, int(name.get_height() * 160 / name.get_width())))
                    nx = 60 if side == 0 else config.CANVAS_W - 60 - n.get_width()
                    surf.blit(n, (nx, 170 + img.get_height() + 12))
            label = outlined(self.assets.font(12),
                             "READY!" if self.confirmed[pl] else f"P{pl + 1} SELECT",
                             color)
            lx = 60 if side == 0 else config.CANVAS_W - 60 - label.get_width()
            surf.blit(label, (lx, 140))

        if all(self.confirmed):
            vs = outlined(self.assets.font(44), "VS", (255, 80, 40), px=4)
            surf.blit(vs, (config.CANVAS_W / 2 - vs.get_width() / 2, 400))


# MAP SELECT
class MapSelectScene(Scene):
    THUMB = (250, 130)

    def __init__(self, game, p1_char, p2_char):
        super().__init__(game)
        self.p1_char, self.p2_char = p1_char, p2_char
        self.thumbs = [self.assets.map_thumb(i, self.THUMB) for i in range(1, 7)]
        self.cursor = 0

    def handle(self, events, held):
        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            if e.key == pygame.K_ESCAPE:
                self.game.change(CharSelectScene(self.game))
                return
            col, row = self.cursor % 3, self.cursor // 3
            if e.key in (pygame.K_a, pygame.K_LEFT):
                col = (col - 1) % 3
            elif e.key in (pygame.K_d, pygame.K_RIGHT):
                col = (col + 1) % 3
            elif e.key in (pygame.K_w, pygame.K_UP, pygame.K_s, pygame.K_DOWN):
                row ^= 1
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_j, pygame.K_KP4):
                self.assets.play("Select")
                pygame.mixer.music.fadeout(400)
                self.game.change(FightScene(self.game, self.p1_char,
                                            self.p2_char, self.cursor + 1))
                return
            new = row * 3 + col
            if new != self.cursor:
                self.cursor = new
                self.assets.play("Select", 0.4)

    def update(self):
        self.thumbs[self.cursor].tick()

    def draw(self, surf):
        surf.fill((12, 10, 26))
        title = outlined(self.assets.font(24), "SELECT STAGE", (255, 220, 60), px=3)
        surf.blit(title, (config.CANVAS_W / 2 - title.get_width() / 2, 36))

        tw, th = self.THUMB
        gap_x, gap_y = 40, 44
        grid_w = 3 * tw + 2 * gap_x
        x0 = (config.CANVAS_W - grid_w) / 2
        y0 = 120
        for i, thumb in enumerate(self.thumbs):
            col, row = i % 3, i // 3
            x = x0 + col * (tw + gap_x)
            y = y0 + row * (th + gap_y)
            frame = thumb.frame
            selected = i == self.cursor
            if selected:
                rect = pygame.Rect(int(x) - 6, int(y) - 6, tw + 12, th + 12)
                pygame.draw.rect(surf, (255, 220, 60), rect, border_radius=6)
            surf.blit(frame, (x, y))
            if not selected:
                dim = pygame.Surface((tw, th), pygame.SRCALPHA)
                dim.fill((0, 0, 20, 120))
                surf.blit(dim, (x, y))
            tag = outlined(self.assets.font(11), f"STAGE {i + 1}",
                           (255, 255, 255) if selected else (150, 150, 170))
            surf.blit(tag, (x + tw / 2 - tag.get_width() / 2, y + th + 8))

        hint = outlined(self.assets.font(10), "MOVE: WASD/ARROWS    CONFIRM: ENTER / J",
                        (170, 170, 190))
        surf.blit(hint, (config.CANVAS_W / 2 - hint.get_width() / 2, config.CANVAS_H - 32))


# FIGHT
class FightScene(Scene):
    def __init__(self, game, p1_char, p2_char, map_index):
        super().__init__(game)
        a = self.assets
        self.map_index = map_index
        self.chars = (p1_char, p2_char)
        self.bg = a.stage_bg(map_index)
        self.fighters = [
            Fighter(p1_char, a.characters[p1_char], 280, 1, P1_CONTROLS, a),
            Fighter(p2_char, a.characters[p2_char], config.CANVAS_W - 280, -1, P2_CONTROLS, a),
        ]
        self.hud = HUD(a, [p1_char.upper(), p2_char.upper()])
        self.announcer = Announcer(a)
        self.effects = Effects()
        self.round_num = 1
        self.wins = [0, 0]
        self.combo = [0, 0]
        self.projectiles = []
        self.timer = config.ROUND_TIME
        self.second_ticks = 0
        self.state = "intro"
        self.t = 0
        self.hitstop = 0
        self.paused = False
        self.winner = None
        self.pressed = set()
        self.tick = 0
        a.music("fight_theme.wav", 0.4)

    # Input
    def handle(self, events, held):
        self.held = held
        self.pressed = set()
        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            self.pressed.add(e.key)
            if e.key == pygame.K_ESCAPE and self.state in ("intro", "fight"):
                self.paused = not self.paused
            elif self.paused and e.key == pygame.K_q:
                self.game.change(MenuScene(self.game))
                return
            elif self.state == "end":
                if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.game.change(MenuScene(self.game))
                    return
                if e.key == pygame.K_r:
                    self.game.change(FightScene(self.game, *self.chars, self.map_index))
                    return
        if self.paused:
            self.pressed = set()

    # Update
    def update(self):
        if self.paused:
            return
        self.tick += 1
        self.t += 1
        self.bg.tick()
        self.effects.update()
        self.announcer.update()

        if self.state == "intro":
            if self.t == 12:
                self.announcer.say(f"ROUND {self.round_num}", (255, 220, 60), life=60)
            if self.t == 72:
                self.announcer.say("FIGHT!", (255, 70, 40), life=40, size=54)
                self.assets.play("fightFX")
            self._world(False)
            if self.t >= 88:
                self.state = "fight"
                self.t = 0

        elif self.state == "fight":
            if self.hitstop:
                self.hitstop -= 1
            else:
                for i, f in enumerate(self.fighters):
                    f.fireball_active = any(p.owner == i for p in self.projectiles)
                self._world(True)
                self._resolve_hits()
                self._update_projectiles()
                self._push_apart()
            self._tick_clock()
            self._update_combo()

        elif self.state == "ko":
            slow = self.t < 50 and self.t % 3 != 0  # brief slow motion
            if self.hitstop:
                self.hitstop -= 1
            elif not slow:
                self._world(False)
                self._fly_projectiles()  # round decided: fireballs just fly out
                self._push_apart()
            if self.t == 85 and self.winner is not None:
                self.fighters[self.winner].play_win()
            if self.t >= 230:
                self._next_round()

        elif self.state == "end":
            self._world(False)

        self.hud.update(self.fighters)

    def _world(self, with_inputs):
        f1, f2 = self.fighters
        if with_inputs:
            f1.update(self.held, self.pressed, f2)
            f2.update(self.held, self.pressed, f1)
        else:
            f1.update(NO_KEYS, NO_PRESSED, f2)
            f2.update(NO_KEYS, NO_PRESSED, f1)
        for f in self.fighters:
            f.x = max(config.STAGE_MARGIN, min(config.CANVAS_W - config.STAGE_MARGIN, f.x))

    def _push_apart(self):
        f1, f2 = self.fighters
        r1, r2 = f1.pushbox(), f2.pushbox()
        if r1.colliderect(r2):
            overlap = min(r1.right, r2.right) - max(r1.left, r2.left)
            shift = overlap / 2 + 0.5
            if f1.x <= f2.x:
                f1.x -= shift
                f2.x += shift
            else:
                f1.x += shift
                f2.x -= shift
            for f in self.fighters:
                f.x = max(config.STAGE_MARGIN,
                          min(config.CANVAS_W - config.STAGE_MARGIN, f.x))

    def _resolve_hits(self):
        for i in (0, 1):
            att, vic = self.fighters[i], self.fighters[1 - i]
            hitbox = att.get_hitbox()
            if not hitbox or vic.dying or not hitbox.colliderect(vic.hurtbox()):
                continue
            att.hit_connected = True
            atk = att.attack
            direction = 1 if vic.x >= att.x else -1
            was_stunned = vic.hitstun > 0
            result = vic.take_hit(atk, direction)

            hurt = vic.hurtbox()
            pos = (max(hurt.left, min(hitbox.centerx, hurt.right)), hitbox.centery)

            if result == "block":
                self.effects.hit_spark(pos, blocked=True)
                self.assets.play("punch", 0.25)
                self.hitstop = HITSTOP_BLOCK
                continue

            self.assets.play(atk.sound, 0.6)
            self.effects.hit_spark(pos, heavy=atk.heavy)
            self.hitstop = HITSTOP_HEAVY if atk.heavy else HITSTOP_LIGHT
            if atk.heavy:
                self.effects.shake(7, 14)
            self.combo[i] = self.combo[i] + 1 if was_stunned else 1
            self.hud.set_combo(i, self.combo[i])
            if result == "ko":
                self._ko(i)

    def _fly_projectiles(self):
        for p in self.projectiles[:]:
            p.update(self.effects)
            if p.rect.right < -40 or p.rect.left > config.CANVAS_W + 40:
                self.projectiles.remove(p)

    def _update_projectiles(self):
        # spawn: hadouken releases its fireball on the startup tick,
        # shoryuken leaves an ember trail while rising
        for i, f in enumerate(self.fighters):
            palette = FIRE_COLORS.get(f.name, FIRE_COLORS["ryu"])
            if f.special == "hadouken" and f.attack and \
                    f.attack_tick == f.attack.startup and not f.fireball_active:
                self.projectiles.append(Fireball(
                    f.x + f.facing * 62, f.y - 128, f.facing, i, palette,
                    SPECIALS["hadouken"], FIREBALL_SPEED))
                self.assets.play("punch", 0.5)
                f.fireball_active = True
            if f.special == "shoryuken" and not f.on_ground and f.vy < 2:
                for _ in range(2):
                    self.effects.ember(f.x + f.facing * 20 + random.uniform(-14, 14),
                                       f.y - random.uniform(50, 190), palette)

        # projectile vs projectile: they cancel out in a burst
        live = self.projectiles
        if len(live) >= 2 and live[0].owner != live[1].owner and \
                live[0].rect.colliderect(live[1].rect):
            self.effects.hit_spark(live[0].rect.center, heavy=True)
            self.effects.hit_spark(live[1].rect.center)
            self.assets.play("punch", 0.5)
            self.projectiles.clear()
            return

        for p in self.projectiles[:]:
            p.update(self.effects)
            vic = self.fighters[1 - p.owner]
            if not vic.dying and p.rect.colliderect(vic.hurtbox()):
                was_stunned = vic.hitstun > 0
                result = vic.take_hit(p.attack, p.direction)
                pos = p.rect.center
                self.projectiles.remove(p)
                if result == "block":
                    self.effects.hit_spark(pos, blocked=True)
                    self.assets.play("punch", 0.25)
                    self.hitstop = HITSTOP_BLOCK
                    continue
                self.assets.play("punch", 0.6)
                self.effects.hit_spark(pos)
                self.hitstop = HITSTOP_LIGHT
                self.combo[p.owner] = self.combo[p.owner] + 1 if was_stunned else 1
                self.hud.set_combo(p.owner, self.combo[p.owner])
                if result == "ko":
                    self._ko(p.owner)
            elif p.rect.right < -40 or p.rect.left > config.CANVAS_W + 40:
                self.projectiles.remove(p)

    def _update_combo(self):
        for i in (0, 1):
            opp = self.fighters[1 - i]
            if self.combo[i] and not opp.hitstun and not opp.dying:
                self.combo[i] = 0
                self.hud.set_combo(i, 0)

    def _tick_clock(self):
        self.second_ticks += 1
        if self.second_ticks >= 60:
            self.second_ticks = 0
            self.timer -= 1
            if self.timer <= 0:
                self._time_up()

    def _ko(self, winner):
        self.state = "ko"
        self.t = 0
        self.winner = winner
        self.wins[winner] += 1
        self.announcer.clear()
        self.announcer.say("K.O.", (255, 60, 40), life=150, size=68)
        self.assets.play("KO")
        self.assets.play("death", 0.7)
        self.effects.shake(14, 26)
        self.hitstop = 16

    def _time_up(self):
        h1, h2 = self.fighters[0].health, self.fighters[1].health
        self.state = "ko"
        self.t = 0
        self.announcer.clear()
        self.announcer.say("TIME UP", (255, 220, 60), life=120, size=44)
        if h1 == h2:
            self.winner = None
            self.announcer.say("DRAW", (200, 200, 220), life=120, size=30,
                               y=config.CANVAS_H / 2 + 10)
        else:
            self.winner = 0 if h1 > h2 else 1
            self.wins[self.winner] += 1

    def _next_round(self):
        if max(self.wins) >= config.ROUNDS_TO_WIN:
            self.state = "end"
            self.t = 0
            w = self.wins.index(max(self.wins))
            self.announcer.clear()
            self.announcer.say(f"{self.chars[w].upper()} WINS!",
                               P1_COLOR if w == 0 else P2_COLOR,
                               life=10 ** 9, size=40)
            self.assets.play("p1win" if w == 0 else "p2win")
            return
        self.round_num += 1
        self.timer = config.ROUND_TIME
        self.second_ticks = 0
        self.combo = [0, 0]
        self.winner = None
        self.projectiles.clear()
        self.announcer.clear()
        for f in self.fighters:
            f.reset()
        self.hud.set_combo(0, 0)
        self.hud.set_combo(1, 0)
        self.state = "intro"
        self.t = 0

    # Draw
    def draw(self, surf):
        surf.fill((0, 0, 0))
        ox, oy = self.effects.offset()
        surf.blit(self.bg.frame, (int(ox), int(oy)))

        # attacker draws on top so hits read clearly
        order = sorted(self.fighters, key=lambda f: 1 if f.attack else 0)
        for f in order:
            f.draw(surf, (int(ox), int(oy)))

        for p in self.projectiles:
            p.draw(surf, (int(ox), int(oy)))
        self.effects.draw(surf, (int(ox), int(oy)))
        self.hud.draw(surf, self.fighters, self.timer, self.wins, self.round_num)
        self.announcer.draw(surf)

        if self.state == "intro" and self.t < 24:
            fade = pygame.Surface((config.CANVAS_W, config.CANVAS_H))
            fade.fill((0, 0, 0))
            fade.set_alpha(int(200 * (1 - self.t / 24)))
            surf.blit(fade, (0, 0))

        if self.state == "end" and (self.tick // 32) % 2 == 0:
            prompt = outlined(self.assets.font(14),
                              "ENTER: MENU      R: REMATCH", (255, 255, 255), px=2)
            surf.blit(prompt, (config.CANVAS_W / 2 - prompt.get_width() / 2, 420))

        if self.paused:
            self._draw_pause(surf)

    def _draw_pause(self, surf):
        shade = pygame.Surface((config.CANVAS_W, config.CANVAS_H), pygame.SRCALPHA)
        shade.fill((0, 0, 15, 190))
        surf.blit(shade, (0, 0))
        title = outlined(self.assets.font(36), "PAUSED", (255, 220, 60), px=3)
        surf.blit(title, (config.CANVAS_W / 2 - title.get_width() / 2, 90))
        lines = [
            "P1   MOVE: A/D   JUMP: W   CROUCH: S   BLOCK: L",
            "     PUNCH: J/K   KICK: U/I",
            "",
            "P2   MOVE: ARROWS   JUMP: UP   CROUCH: DOWN   BLOCK: NUM6",
            "     PUNCH: NUM4/NUM5   KICK: NUM1/NUM2",
            "",
            "FWD + HEAVY PUNCH = UPPERCUT     JUMP + DIRECTION = FLIP",
            "CROUCH + PUNCH/KICK = LOW ATTACKS (SWEEP KNOCKS DOWN)",
            "DOWN, FWD + PUNCH = HADOUKEN",
            "FWD, DOWN, FWD + PUNCH = SHORYUKEN",
            "PUNCHES WHIFF OVER CROUCHERS - GO LOW!",
            "",
            "ESC: RESUME      Q: QUIT TO MENU",
        ]
        font = self.assets.font(12)
        y = 170
        for line in lines:
            if line:
                text = outlined(font, line, (220, 220, 235))
                surf.blit(text, (config.CANVAS_W / 2 - text.get_width() / 2, y))
            y += 26
