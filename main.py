"""Street Fighter — Python Edition. Entry point.

Run:  python python/main.py
"""
import pygame

from sf import config
from sf.assets import Assets
from sf.scenes import MenuScene


class Game:
    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        # SCALED + vsync: crisp integer-friendly scaling and tear-free frames
        self.screen = pygame.display.set_mode(
            (config.CANVAS_W, config.CANVAS_H),
            pygame.SCALED | pygame.RESIZABLE, vsync=1)
        pygame.display.set_caption("Street Fighter — Python Edition")
        self.assets = Assets()
        icon = self.assets.images.get("logo")
        if icon:
            pygame.display.set_icon(icon)
        self.scene = MenuScene(self)
        self.clock = pygame.time.Clock()
        self.running = True

    def change(self, scene):
        self.scene = scene

    def run(self):
        while self.running:
            events = pygame.event.get()
            for e in events:
                if e.type == pygame.QUIT:
                    self.running = False
            held = pygame.key.get_pressed()
            self.scene.handle(events, held)
            self.scene.update()
            self.scene.draw(self.screen)
            pygame.display.flip()
            self.clock.tick(config.FPS)
        pygame.quit()


if __name__ == "__main__":
    Game().run()
