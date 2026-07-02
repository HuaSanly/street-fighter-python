"""Global configuration: paths, display, physics and gameplay constants.

All speeds/forces are per-tick at a fixed 60 ticks/second, scaled 2x from the
original Java values because sprites render at SPRITE_SCALE = 2.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # repo root
RES = ROOT / "assets"
IMG_DIR = RES / "images"
SND_DIR = RES / "sounds"
MUS_DIR = RES / "music"
FONT_PATH = RES / "fonts" / "PressStart2P-Regular.ttf"
DATA_DIR = ROOT / "sf" / "data"

CANVAS_W, CANVAS_H = 960, 540
FPS = 60
SPRITE_SCALE = 2

# Physics (Java: gravity 0.6, move 4, air 2.5, jump -14 — doubled for 2x scale,
# gravity slightly under 2x so jumps hang a touch longer and feel better)
GROUND_Y = 488
STAGE_MARGIN = 70
GRAVITY = 1.1
MOVE_SPEED = 7.0
AIR_MOVE_SPEED = 4.5
JUMP_FORCE = -26.0

# Gameplay
MAX_HEALTH = 1000
ROUND_TIME = 99
ROUNDS_TO_WIN = 2
BLOCK_CHIP_RATIO = 0.12   # fraction of damage taken while blocking

# Fighter collision boxes (canvas pixels)
PUSHBOX_W = 64
HURTBOX_W = 92
HURTBOX_H = 205
