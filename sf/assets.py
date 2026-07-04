import json

import pygame
from PIL import Image

from . import config


def load_image(path, alpha=True):
    surf = pygame.image.load(str(path))
    return surf.convert_alpha() if alpha else surf.convert()


def load_gif(path, size=None):
    """Return (frames, durations_in_ticks) for an animated GIF."""
    img = Image.open(path)
    frames, durations = [], []
    n = getattr(img, "n_frames", 1)
    for i in range(n):
        img.seek(i)
        rgba = img.convert("RGBA")
        surf = pygame.image.frombytes(rgba.tobytes(), rgba.size, "RGBA").convert_alpha()
        if size:
            surf = pygame.transform.smoothscale(surf, size)
        frames.append(surf)
        durations.append(max(3, int(img.info.get("duration", 100)) // 16))
    return frames, durations


class AnimatedBG:
    """Ticks through GIF frames at their native durations."""

    def __init__(self, frames, durations):
        self.frames = frames
        self.durations = durations
        self.index = 0
        self.timer = 0

    def tick(self):
        self.timer += 1
        if self.timer >= self.durations[self.index]:
            self.timer = 0
            self.index = (self.index + 1) % len(self.frames)

    @property
    def frame(self):
        return self.frames[self.index]


class Assets:
    """Loads and owns every asset. Create one instance after display init."""

    def __init__(self):
        self.characters = {}   # name -> anim name -> dict(frames, mirror, meta)
        self.sounds = {}
        self.images = {}
        self._fonts = {}
        self._gif_cache = {}
        self._load_characters()
        self._load_sounds()
        self._load_images()

    # Characters
    def _load_characters(self):
        data = json.loads((config.DATA_DIR / "characters.json").read_text())
        for char, cdata in data.items():
            anims = {}
            for name, a in cdata["animations"].items():
                sheet = load_image(config.IMG_DIR / cdata["dir"] / a["file"])
                fw = a["fw"]
                sequence = a.get("sequence", list(range(a["frames"])))
                # slice full-height columns, then trim the shared transparent
                # padding (union bbox) so feet stay aligned across frames
                raw = []
                for col in sequence:
                    rect = pygame.Rect(col * fw, 0, fw, sheet.get_height())
                    raw.append(sheet.subsurface(rect.clip(sheet.get_rect())).copy())
                union = None
                for f in raw:
                    box = f.get_bounding_rect(min_alpha=8)
                    if box.width and box.height:
                        union = box.copy() if union is None else union.union(box)
                frames = []
                for f in raw:
                    if union:
                        f = f.subsurface(union.clip(f.get_rect())).copy()
                    frames.append(pygame.transform.scale_by(f, config.SPRITE_SCALE))
                anims[name] = {
                    "frames": frames,
                    "mirror": [pygame.transform.flip(f, True, False) for f in frames],
                    "delay": a["delay"],
                    "loop": a.get("loop", False),
                    "hold": a.get("hold", False),
                    "next": a.get("next"),
                    "interruptible": a.get("interruptible", False),
                }
            self.characters[char] = anims

    # Sounds
    def _load_sounds(self):
        for wav in config.SND_DIR.glob("*.wav"):
            try:
                self.sounds[wav.stem] = pygame.mixer.Sound(str(wav))
            except pygame.error:
                pass
        for name in ("punch", "kick", "jump"):
            if name in self.sounds:
                self.sounds[name].set_volume(0.55)

    def play(self, name, volume=None):
        snd = self.sounds.get(name)
        if snd:
            if volume is not None:
                snd.set_volume(volume)
            snd.play()

    @staticmethod
    def music(track, volume=0.5, loop=True):
        path = config.MUS_DIR / track
        if path.exists():
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play(-1 if loop else 0)

    # Images
    def _load_images(self):
        for name in ("logo.jpg", "ryuSelect.png", "kenSelect.png",
                     "ryu_name.png", "ken_name.png", "LogInBG.jpg"):
            path = config.IMG_DIR / name
            if path.exists():
                self.images[name.split(".")[0]] = load_image(path)

    def _gif(self, path, size):
        key = (str(path), size)
        if key not in self._gif_cache:
            self._gif_cache[key] = load_gif(path, size)
        return self._gif_cache[key]

    def stage_bg(self, index):
        """Animated stage background scaled to the canvas (1-based index)."""
        frames, durations = self._gif(config.IMG_DIR / f"map{index}.gif",
                                      (config.CANVAS_W, config.CANVAS_H))
        return AnimatedBG(frames, durations)

    def char_select_bg(self):
        frames, durations = self._gif(config.IMG_DIR / "charSelectBG.gif",
                                      (config.CANVAS_W, config.CANVAS_H))
        return AnimatedBG(frames, durations)

    def map_thumb(self, index, size):
        frames, durations = self._gif(config.IMG_DIR / f"map{index}.gif", size)
        return AnimatedBG(frames, durations)

    # Fonts
    def font(self, size):
        if size not in self._fonts:
            self._fonts[size] = pygame.font.Font(str(config.FONT_PATH), size)
        return self._fonts[size]
