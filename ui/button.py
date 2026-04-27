import pygame
from config import *

class Button:
    def __init__(self, rect, text, action, font=None):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.action = action
        self.hover = False
        self.font = font if font else FONT
        
    def update_hover(self, mouse_pos):
        self.hover = self.rect.collidepoint(mouse_pos)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return self.action()

    def draw(self, screen):
        color = (20,20,20) if self.hover else (0,0,0)
        pygame.draw.rect(screen, color, self.rect)
        
        text_surf = self.font.render(self.text, True, white)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)
