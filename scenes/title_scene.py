from scenes.base_scene import Scene
from ui.button import Button
from config import *
from saveload import load_game
import pygame, sys

pygame.mixer.init()

class TitleScene(Scene):
    def __init__(self):
        self.bg = pygame.image.load(resource_path("assets/main.png"))
        self.bg = pygame.transform.scale(self.bg, (1280, 720))
        
        self.buttons = [
            #Button((520, 260, 240, 60), "Continue", self.continue_game),
            Button((520, 330, 240, 60), "Load Game", self.load_game),
            Button((520, 400, 240, 60), "Option", self.option),
            Button((520, 470, 240, 60), "How", self.how),
            Button((520, 540, 240, 60), "Quit", self.quit),
        ]

    def continue_game(self):
        return "hub"

    def load_game(self):
        load_game()
        return "hub"

    def option(self):
        return "option"
    
    def how(self):
        return "how"

    def quit(self):
        pygame.quit()
        sys.exit()

    def draw(self, screen):
        #screen.fill(black)
        screen.blit(self.bg, (0, 0))
        for btn in self.buttons:
            btn.draw(screen)
