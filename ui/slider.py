import pygame

class Slider:
    def __init__(self, pos, width, val):
        self.rect = pygame.Rect(pos[0], pos[1], width, 10) # 슬라이더 바
        self.val = val # 0.0 ~ 1.0
        self.knob_rect = pygame.Rect(0, 0, 20, 20) # 조절 손잡이
        self.active = False # 드래그 중인지 확인

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.knob_rect.collidepoint(event.pos):
                    self.active = True
            if event.type == pygame.MOUSEBUTTONUP:
                self.active = False
        
        if self.active:
            # 마우스 위치에 따라 값 계산 (범위 제한)
            rel_x = max(0, min(mouse_pos[0] - self.rect.x, self.rect.width))
            self.val = rel_x / self.rect.width

    def draw(self, screen):
        # 바 그리기
        pygame.draw.rect(screen, (180, 180, 180), self.rect)
        # 손잡이 위치 계산 및 그리기
        self.knob_rect.center = (self.rect.x + int(self.val * self.rect.width), self.rect.centery)
        pygame.draw.circle(screen, (50, 50, 255), self.knob_rect.center, 10)

    def get_value(self):
        return self.val