import pygame
from config import *

class Button:
    def __init__(self, rect, text, action, font=None, active=False):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.action = action
        self.hover = False
        self.font = font if font else FONT
        self.active = active
        
    def update_hover(self, mouse_pos):
        self.hover = self.rect.collidepoint(mouse_pos)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return self.action()

    def draw(self, screen):
        if self.active:
            bg_color = (45, 80, 135)
            border_color = (90, 180, 255)
            text_color = white
        elif self.hover:
            bg_color = (35, 35, 35)
            border_color = (90, 90, 90)
            text_color = white
        else:
            bg_color = (0, 0, 0)
            border_color = (40, 40, 40)
            text_color = white

        pygame.draw.rect(screen, bg_color, self.rect)
        pygame.draw.rect(screen, border_color, self.rect, 2)

        if self.active:
            pygame.draw.rect(screen, (0, 200, 255), (self.rect.x, self.rect.y, 5, self.rect.height))

        text_surf = self.font.render(self.text, True, text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)
