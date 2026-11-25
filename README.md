# 🥊 Street Fighter — Python Edition

A 2D fighting game inspired by Street Fighter, built with **pygame-ce**.
Battles with Ryu and Ken, six animated stages, motion-input
special moves (Hadouken! Shoryuken!), and a combat system with real frame
data, hitboxes, and cancels.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![pygame--ce](https://img.shields.io/badge/pygame--ce-2.5%2B-green)
![License](https://img.shields.io/badge/license-MIT-green)

<p align="center">
  <img src="docs/fight.png" width="420" />
  <img src="docs/hadouken.png" width="420" />
  <img src="docs/shoryuken.png" width="420" />
  <img src="docs/charselect.png" width="420" />
</p>

## 🚀 Quick start

```bash
git clone <this-repo>
cd street-fighter-python
pip install -r requirements.txt
python main.py
```

Requires Python 3.10+. Dependencies: `pygame-ce`, `pillow`.

## ✨ Features

- **Two fighters** — Ryu and Ken, with full sprite animation sets
- **Three match modes** — Player vs Player, AI vs Player, and AI vs AI
- **Special moves** — Hadouken (↓ ↘ → + P) fires a glowing projectile
  (blue for Ryu, orange for Ken); Shoryuken (→ ↓ → + P) is a rising
  knockdown uppercut with landing lag on whiff. Fireballs cancel each other
  when they collide.
- **Real fighting-game combat** — per-attack hitboxes with startup/active
  frames, hitstun/blockstun, chip damage, knockdowns on heavies,
  light-attack cancels into specials, combo counter
- **Crouching** — hold down to crouch: high attacks whiff over you, and
  crouching gives you low punches and a sweep that knocks down
- **Six animated stages** + animated character-select screen
- **Game feel** — hitstop, screen shake, particle hit sparks, KO slow
  motion, health bars with damage trails, springy announcer text
- **Deterministic engine** — fixed 60 Hz tick for physics, animation and
  combat; vsync'd rendering

## Match setup

On the main menu, use Left/Right to choose a mode and Up/Down to move between
settings. Press Enter to continue to fighter and stage selection.

| Mode | Setup |
|------|-------|
| Player vs Player | Both sides use the keyboard and pick their own fighters. |
| AI vs Player | Choose the human side and the other side's bot. |
| AI vs AI | Choose a bot independently for P1 and P2, then watch the match. |

In either AI mode, use Left/Right and Enter to pick P1's fighter, then P2's.
The bot choices are **Bot-A**, **Bot-B-Easy**, **Bot-B-Normal**, and **Bot-B-Hard**.
The fight HUD shows each bot by name. Press **R** after the match to replay the
same setup.

Run `python -m unittest discover -s tests -v` to check the match flows and bot
combat inputs without opening a window.

## 🎮 Controls

|             | Player 1 | Player 2 |
|-------------|----------|----------|
| Move        | A / D    | ← / →    |
| Jump        | W        | ↑        |
| Crouch      | S        | ↓        |
| Light punch | J        | Numpad 4 |
| Heavy punch | K        | Numpad 5 |
| Light kick  | U        | Numpad 1 |
| Heavy kick  | I        | Numpad 2 |
| Block       | L (hold) | Numpad 6 (hold) |

### Moves

| Move | Input |
|------|-------|
| Hadouken | ↓ ↘ → + any punch |
| Shoryuken | → ↓ → + any punch |
| Uppercut | forward + heavy punch |
| Flip jump | jump + direction |
| Low punch | crouch + punch (cancels into specials on hit) |
| Sweep | crouch + kick (knocks down) |
| Air attacks | any attack while airborne |

High punches whiff over crouching opponents — mix in lows! `ESC` pauses and
shows the full move list. After a match: `R` to rematch, `ENTER` for menu.

## 📁 Project structure

```
street-fighter-python/
├── main.py              # window + vsync'd fixed-timestep game loop
├── assets/              # sprites, stages, sounds, music, font
├── Bot/
│   ├── bot_a/           # Gothicvania-inspired tactical controller
│   └── bot_b/           # Tepelekas CPUController and its MIT notice
└── sf/
    ├── config.py        # all tunable constants (speed, damage, health...)
    ├── assets.py        # data-driven sprite sheet loader, GIF stages
    ├── data/characters.json  # every animation: file, frames, timing
    ├── animation.py     # tick-based animation player
    ├── combat.py        # attack frame data + special move definitions
    ├── fighter.py       # physics, input buffer, hit reactions, boxes
    ├── effects.py       # particles, fireballs, screen shake
    ├── ui.py            # health bars, timer, combos, announcer
    └── scenes.py        # menu → char select → stage select → fight
```

Adding a character is data-driven: drop sprite sheets in `assets/images/<name>/`
and describe them in `sf/data/characters.json` — no engine changes needed.


## Acknowledgments

- Inspired by Capcom's Street Fighter series
- Sprite assets from [OpenGameArt](https://opengameart.org/), sounds from
  [FreeSound](https://freesound.org/)
- Originally built in JavaFX by the same authors; this is the Python rewrite
- Bot-A is an independent implementation of the behavior described by
  [Gothicvania's Bot](https://github.com/DvlprHsn/Gothicvania/blob/254ec93732254bdb41456b60484c7343fe979149/entities/bot.py).
  A forward rush into a sweep maps Gothicvania's slide to this game's move set.
- Bot-B adapts [Tepelekas's CPUController](https://github.com/tepelekas/street-fighter-python/blob/5b90aa144fced0652e1036a0cf5205a900ee939c/cpu_controller.py).
  Its MIT notice is included in [Bot/bot_b/LICENSE](Bot/bot_b/LICENSE).

## Authors

- [Kabir](https://github.com/daicarus)
- [Nihan](https://github.com/Nihan2609)
