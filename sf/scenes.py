"""Game scenes: menu -> character select -> map select -> fight."""
import math

import pygame

from Bot import BOT_NAMES, BotInput

from . import config
from .combat_round import CombatRound, NO_KEYS
from .effects import Effects
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

P1_COLOR = (255, 80, 60)
P2_COLOR = (80, 140, 255)
HUMAN = (None, None)


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
    MODES = ("PLAYER VS PLAYER", "AI VS PLAYER", "AI VS AI")

    def __init__(self, game, controllers=HUMAN):
        super().__init__(game)
        bg = self.assets.images.get("LogInBG")
        self.bg = cover(bg, (config.CANVAS_W, config.CANVAS_H)) if bg else None
        dark = pygame.Surface((config.CANVAS_W, config.CANVAS_H), pygame.SRCALPHA)
        dark.fill((0, 0, 10, 150))
        if self.bg:
            self.bg.blit(dark, (0, 0))
        self.tick = 0
        self.mode = sum(name is not None for name in controllers)
        self.human_side = 0 if controllers[0] is None else 1
        defaults = ("Bot-A", "Bot-B-Normal")
        self.bot_choices = [BOT_NAMES.index(name or defaults[i])
                            for i, name in enumerate(controllers)]
        self.focus = 0
        self.assets.music("home.wav", 0.5)

    def _controllers(self):
        return tuple(BOT_NAMES[choice] if self.mode == 2 or
                     (self.mode == 1 and side != self.human_side) else None
                     for side, choice in enumerate(self.bot_choices))

    def _rows(self):
        if self.mode == 1:
            bot_side = 1 - self.human_side
            return [("HUMAN SIDE", f"P{self.human_side + 1}", None),
                    (f"P{bot_side + 1} BOT", BOT_NAMES[self.bot_choices[bot_side]], bot_side)]
        if self.mode == 2:
            return [(f"P{i + 1} BOT", BOT_NAMES[choice], i)
                    for i, choice in enumerate(self.bot_choices)]
        return []

    def handle(self, events, held):
        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.assets.play("Select")
                self.game.change(CharSelectScene(self.game, self._controllers()))
                return
            if e.key in (pygame.K_UP, pygame.K_w, pygame.K_DOWN, pygame.K_s):
                step = -1 if e.key in (pygame.K_UP, pygame.K_w) else 1
                self.focus = (self.focus + step) % (1 + len(self._rows()))
                self.assets.play("Select", 0.4)
            elif e.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                step = -1 if e.key in (pygame.K_LEFT, pygame.K_a) else 1
                if self.focus == 0:
                    self.mode = (self.mode + step) % len(self.MODES)
                else:
                    side = self._rows()[self.focus - 1][2]
                    if side is None:
                        self.human_side ^= 1
                    else:
                        self.bot_choices[side] = (self.bot_choices[side] + step) % len(BOT_NAMES)
                self.assets.play("Select", 0.4)

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
        bob = int(4 * math.sin(self.tick / 30))
        surf.blit(title1, title1.get_rect(midtop=(config.CANVAS_W // 2, 40 + bob)))
        surf.blit(title2, title2.get_rect(midtop=(config.CANVAS_W // 2, 105 + bob)))
        sub = outlined(self.assets.font(14), "PYTHON EDITION", (200, 200, 220))
        surf.blit(sub, sub.get_rect(midtop=(config.CANVAS_W // 2, 181)))

        gold = (255, 220, 60)
        muted = (180, 185, 210)
        for i, mode in enumerate(self.MODES):
            rect = pygame.Rect(102 + i * 256, 233, 244, 48)
            selected = i == self.mode
            pygame.draw.rect(surf, (64, 42, 28) if selected else (22, 22, 42),
                             rect, border_radius=6)
            if selected:
                pygame.draw.rect(surf, gold, rect, 3 if self.focus == 0 else 1, border_radius=6)
            label = outlined(self.assets.font(12), mode, gold if selected else muted)
            surf.blit(label, label.get_rect(center=rect.center))

        for i, (label, value, _) in enumerate(self._rows(), 1):
            rect = pygame.Rect(228, 296 + (i - 1) * 50, 504, 42)
            selected = self.focus == i
            pygame.draw.rect(surf, (22, 22, 42), rect, border_radius=5)
            if selected:
                pygame.draw.rect(surf, gold, rect, 2, border_radius=5)
            desc = outlined(self.assets.font(12), label, muted)
            choice = outlined(self.assets.font(14), f"< {value} >", gold if selected else (255, 255, 255))
            surf.blit(desc, desc.get_rect(midleft=(rect.left + 18, rect.centery)))
            surf.blit(choice, choice.get_rect(midright=(rect.right - 18, rect.centery)))

        hint = ("LEFT/RIGHT: CHANGE    UP/DOWN: SELECT ROW    ENTER: CONTINUE"
                if self.mode else "LEFT/RIGHT: CHANGE MODE    ENTER: CONTINUE")
        text = outlined(self.assets.font(12), hint, (225, 225, 240))
        surf.blit(text, text.get_rect(center=(config.CANVAS_W // 2, 470)))


# CHAR SELECT
class CharSelectScene(Scene):
    CHARS = ["ryu", "ken"]

    def __init__(self, game, controllers=HUMAN, picks=(0, 1)):
        super().__init__(game)
        self.bg = self.assets.char_select_bg()
        self.controllers = controllers
        self.cursor = list(picks)
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
                self.game.change(MenuScene(self.game, self.controllers))
                return
            if self.controllers != HUMAN:
                self._handle_solo_pick(e.key)
                continue
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

    def _handle_solo_pick(self, key):
        if all(self.confirmed):
            return
        side = self.confirmed.index(False)
        if key in (pygame.K_a, pygame.K_d, pygame.K_LEFT, pygame.K_RIGHT):
            self.cursor[side] ^= 1
            self.assets.play("Select", 0.4)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_j, pygame.K_KP4):
            self.confirmed[side] = True
            self.assets.play("Select")

    def update(self):
        self.bg.tick()
        if all(self.confirmed):
            self.done_timer += 1
            if self.done_timer >= 50:
                self.game.change(MapSelectScene(
                    self.game, self.CHARS[self.cursor[0]], self.CHARS[self.cursor[1]],
                    self.controllers))

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
            role = self.controllers[pl] or f"P{pl + 1}"
            label = outlined(self.assets.font(12), role + (" READY" if self.confirmed[pl] else ""),
                             color)
            lx = 60 if side == 0 else config.CANVAS_W - 60 - label.get_width()
            surf.blit(label, (lx, 140))

        if all(self.confirmed):
            vs = outlined(self.assets.font(44), "VS", (255, 80, 40), px=4)
            surf.blit(vs, (config.CANVAS_W / 2 - vs.get_width() / 2, 400))
        else:
            if self.controllers == HUMAN:
                hint = "P1: A/D + J    P2: LEFT/RIGHT + NUM4 OR RSHIFT"
            else:
                side = self.confirmed.index(False)
                hint = f"P{side + 1}  LEFT/RIGHT: CHOOSE    ENTER: CONFIRM"
            text = outlined(self.assets.font(11), hint, (225, 225, 240))
            surf.blit(text, text.get_rect(center=(config.CANVAS_W // 2, config.CANVAS_H - 30)))


# MAP SELECT
class MapSelectScene(Scene):
    THUMB = (250, 130)

    def __init__(self, game, p1_char, p2_char, controllers=HUMAN):
        super().__init__(game)
        self.p1_char, self.p2_char = p1_char, p2_char
        self.controllers = controllers
        self.thumbs = [self.assets.map_thumb(i, self.THUMB) for i in range(1, 7)]
        self.cursor = 0

    def handle(self, events, held):
        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            if e.key == pygame.K_ESCAPE:
                picks = tuple(CharSelectScene.CHARS.index(char) for char in (self.p1_char, self.p2_char))
                self.game.change(CharSelectScene(self.game, self.controllers, picks))
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
                                            self.p2_char, self.cursor + 1, self.controllers))
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
    def __init__(self, game, p1_char, p2_char, map_index, controllers=HUMAN):
        super().__init__(game)
        a = self.assets
        self.map_index = map_index
        self.chars = (p1_char, p2_char)
        self.controllers = controllers
        self.bg = a.stage_bg(map_index)
        self.fighters = [
            Fighter(p1_char, a.characters[p1_char], 280, 1, P1_CONTROLS, a),
            Fighter(p2_char, a.characters[p2_char], config.CANVAS_W - 280, -1, P2_CONTROLS, a),
        ]
        self.bots = [BotInput(name, fighter.controls) if name else None
                     for name, fighter in zip(controllers, self.fighters)]
        labels = [name or f"P{i + 1}" for i, name in enumerate(controllers)]
        self.hud = HUD(a, [f"{char.upper()}  {label}" for char, label in zip(self.chars, labels)])
        self.announcer = Announcer(a)
        self.effects = Effects()
        self.round_num = 1
        self.wins = [0, 0]
        self.combat = CombatRound(self.fighters, effects=self.effects, sounds=a)
        self.state = "intro"
        self.t = 0
        self.paused = False
        self.winner = None
        self.held = NO_KEYS
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
                self.game.change(MenuScene(self.game, self.controllers))
                return
            elif self.state == "end":
                if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.game.change(MenuScene(self.game, self.controllers))
                    return
                if e.key == pygame.K_r:
                    self.game.change(FightScene(self.game, *self.chars, self.map_index,
                                                self.controllers))
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
            self.combat.step_presentation()
            if self.t >= 88:
                self.state = "fight"
                self.t = 0

        elif self.state == "fight":
            self._fight_tick()

        elif self.state == "ko":
            slow = self.t < 50 and self.t % 3 != 0  # brief slow motion
            if self.combat.hitstop:
                self.combat.hitstop -= 1
            elif not slow:
                self.combat.step_presentation(after_ko=True)
            if self.t == 85 and self.winner is not None:
                self.fighters[self.winner].play_win()
            if self.t >= 230:
                self._next_round()

        elif self.state == "end":
            self.combat.step_presentation()

        self.hud.update(self.fighters)

    def _fight_tick(self):
        if self.combat.hitstop:
            self.combat.step()
        else:
            inputs = [bot.update(self.combat, index) if bot else (self.held, self.pressed)
                      for index, bot in enumerate(self.bots)]
            actions = self.combat.step(inputs)
            for index, bot in enumerate(self.bots):
                if bot:
                    bot.observe(self.combat, index, actions, human_opponent=self.bots[1 - index] is None)
        for index, count in enumerate(self.combat.combo):
            if count != self.hud.combo[index]:
                self.hud.set_combo(index, count)
        if self.combat.finished:
            self._show_round_result()

    def _show_round_result(self):
        self.state = "ko"
        self.t = 0
        self.winner = self.combat.winner
        if self.winner is not None:
            self.wins[self.winner] += 1
        self.announcer.clear()
        if self.combat.timed_out:
            self.announcer.say("TIME UP", (255, 220, 60), life=120, size=44)
            if self.winner is None:
                self.announcer.say("DRAW", (200, 200, 220), life=120, size=30,
                                   y=config.CANVAS_H / 2 + 10)
            return
        self.announcer.say("K.O.", (255, 60, 40), life=150, size=68)
        self.assets.play("KO")
        self.assets.play("death", 0.7)
        self.effects.shake(14, 26)

    def _next_round(self):
        if max(self.wins) >= config.ROUNDS_TO_WIN:
            self.state = "end"
            self.t = 0
            w = self.wins.index(max(self.wins))
            self.announcer.clear()
            self.announcer.say(f"P{w + 1} {self.chars[w].upper()} WINS!",
                               P1_COLOR if w == 0 else P2_COLOR,
                               life=10 ** 9, size=40)
            self.assets.play("p1win" if w == 0 else "p2win")
            return
        self.round_num += 1
        self.combat = CombatRound(self.fighters, effects=self.effects, sounds=self.assets)
        self.winner = None
        self.announcer.clear()
        for f in self.fighters:
            f.reset()
        for bot in self.bots:
            if bot:
                bot.reset_round()
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

        for p in self.combat.projectiles:
            p.draw(surf, (int(ox), int(oy)))
        self.effects.draw(surf, (int(ox), int(oy)))
        debug = (None, None)
        if self.state == "fight" and not self.paused:
            debug = tuple(bot.debug_state(self.combat, side, human_opponent=self.bots[1 - side] is None)
                          if bot else None for side, bot in enumerate(self.bots))
        self.hud.draw(surf, self.fighters, self.combat.timer, self.wins, self.round_num, debug)
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
