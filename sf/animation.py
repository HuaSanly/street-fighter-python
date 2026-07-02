"""Tick-based animation player.

Unlike the Java version (wall-clock milliseconds), everything counts fixed
60 Hz ticks, so animation, combat frame data and physics stay in lockstep and
never drift.
"""


class AnimPlayer:
    def __init__(self, anims):
        self.anims = anims
        self.name = None
        self.frame_index = 0
        self.timer = 0
        self.finished = False
        self.set("idle", force=True)

    @property
    def meta(self):
        return self.anims[self.name]

    def set(self, name, force=False):
        if name not in self.anims:
            name = "idle"
        if name == self.name and not force:
            return
        self.name = name
        self.frame_index = 0
        self.timer = 0
        self.finished = False

    def tick(self):
        meta = self.meta
        if self.finished and (meta["hold"] or not meta["loop"]):
            # auto-chain to the follow-up animation, if any
            if not meta["hold"] and meta["next"]:
                self.set(meta["next"], force=True)
            return
        self.timer += 1
        if self.timer >= meta["delay"]:
            self.timer = 0
            self.frame_index += 1
            if self.frame_index >= len(meta["frames"]):
                if meta["loop"]:
                    self.frame_index = 0
                else:
                    self.frame_index = len(meta["frames"]) - 1
                    self.finished = True

    def frame(self, mirrored=False):
        key = "mirror" if mirrored else "frames"
        return self.meta[key][self.frame_index]

    @property
    def interruptible(self):
        return self.meta["interruptible"] or self.finished
