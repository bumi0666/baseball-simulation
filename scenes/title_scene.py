from scenes.base_scene import Scene
from ui.button import Button
from config import *
from saveload import list_save_slots
import pygame, sys

pygame.mixer.init()

class TitleScene(Scene):
    def __init__(self):
        self.bg = pygame.image.load(resource_path("assets/main.png"))
        self.bg = pygame.transform.scale(self.bg, (1280, 720))
        self.slots = list_save_slots()
        
        self.buttons = [
            Button((520, 240, 240, 56), "New Game", self.new_game),
            Button((520, 320, 240, 50), self.slot_label(1), lambda: self.load_slot(1)),
            Button((520, 380, 240, 50), self.slot_label(2), lambda: self.load_slot(2)),
            Button((520, 440, 240, 50), self.slot_label(3), lambda: self.load_slot(3)),
            Button((520, 510, 240, 50), "Option", self.option),
            Button((520, 570, 240, 50), "Quit", self.quit),
        ]

    def refresh_slots(self):
        self.slots = list_save_slots()
        for idx, btn in enumerate(self.buttons[1:4], 1):
            btn.text = self.slot_label(idx)

    def slot_label(self, slot):
        info = next((s for s in self.slots if s.get("slot") == slot), None)
        if not info or not info.get("exists"):
            return f"Slot {slot}: Empty"
        return f"Slot {slot}: Day {info.get('current_day', 1)}"

    def new_game(self):
        return "hub"

    def load_slot(self, slot):
        info = next((s for s in self.slots if s.get("slot") == slot), None)
        if not info or not info.get("exists"):
            return None
        return ("load_slot", slot)

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
