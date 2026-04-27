from scenes.base_scene import Scene
from ui.button import Button
from config import *
from datetime import date, timedelta
from ui.layout import get_common_buttons, draw_common_ui
import pygame

class MedicalScene(Scene):
    def __init__(self, players, state):
        self.players = players
        self.state = state
        self.buttons = get_common_buttons(self)
        self.FONT = pygame.font.SysFont("malgungothic", 20) # 한글 깨짐 방지 권장
        self.TITLE_FONT = pygame.font.SysFont("malgungothic", 26, bold=True)
        
        # 스크롤 설정
        self.scroll_y1 = 0  # 부상자 명단용
        self.scroll_y2 = 0  # 혹사 위험군용
        self.row_h = 35     # 행 높이
        self.view_h = 500   # 리스트가 보일 최대 높이
        self.max_rows = self.view_h // self.row_h
        

    def draw_list_section(self, screen, title, data, x, y, scroll_offset, title_color):
        """범용 리스트 드로잉 함수 (스크롤바 포함)"""
        # 타이틀 출력
        screen.blit(self.TITLE_FONT.render(title, True, title_color), (x, y))
        
        # 리스트 영역 배경 (영역 구분을 위해 살짝 어둡게)
        list_rect = pygame.Rect(x, y + 40, 450, self.view_h)
        pygame.draw.rect(screen, (30, 30, 35), list_rect)
        
        # 출력할 데이터 범위 계산
        start_idx = scroll_offset
        end_idx = min(start_idx + self.max_rows, len(data))
        
        # 데이터 렌더링
        for i in range(start_idx, end_idx):
            p = data[i]
            draw_idx = i - start_idx
            item_y = y + 50 + (draw_idx * self.row_h)
            
            if title == "INJURY LIST":
                txt = f"{p.name:<12} ({p.pos}) | Recovery: {p.status['injury_days']} days"
                text_color = (250, 250, 250)
            else:
                f_val = int(p.status.get('fatigue', 0))
                txt = f"{p.name:<12} ({p.pos}) | Fatigue: {f_val} !!"
                text_color = (255, 150, 150)
                
            screen.blit(self.FONT.render(txt, True, text_color), (x + 10, item_y))

        if not data:
            screen.blit(self.FONT.render("No players in this list.", True, (100, 100, 100)), (x + 10, y + 50))

        # 스크롤바 그리기
        if len(data) > self.max_rows:
            bar_x = x + 440
            bar_y = y + 40
            pygame.draw.rect(screen, (50, 50, 50), (bar_x, bar_y, 8, self.view_h))
            
            ratio = self.max_rows / len(data)
            handle_h = max(20, int(self.view_h * ratio))
            scroll_pos = scroll_offset / (len(data) - self.max_rows)
            handle_y = bar_y + int((self.view_h - handle_h) * scroll_pos)
            pygame.draw.rect(screen, (150, 150, 150), (bar_x, handle_y, 8, handle_h))

    def draw(self, screen):
        screen.fill((20, 20, 20))
        draw_common_ui(screen, self.state, FONT)
        
        # 1. 부상자 명단 데이터 준비
        injured = [p for p in self.players if p.status.get("is_injured")]
        # 2. 혹사 위험군 데이터 준비
        overworked = [p for p in self.players if not p.status.get("is_injured") and p.status.get("fatigue", 0) > 200]
        
        # 좌측 섹션 그리기
        self.draw_list_section(screen, "INJURY LIST", injured, 250, 50, self.scroll_y1, (255, 100, 100))
        # 우측 섹션 그리기
        self.draw_list_section(screen, "OVERWORKED (HIGH RISK)", overworked, 750, 50, self.scroll_y2, (255, 50, 50))

        for btn in self.buttons:
            btn.draw(screen)

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update_hover(mouse_pos)
            
        # 리스트 데이터 재계산 (스크롤 한계치 설정을 위해)
        injured_count = len([p for p in self.players if p.status.get("is_injured")])
        overworked_count = len([p for p in self.players if not p.status.get("is_injured") and p.status.get("fatigue", 0) > 200])

        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                # 마우스 위치에 따른 독립 스크롤 처리
                if e.button in [4, 5]: # 휠 업/다운
                    if mouse_pos[0] < 700: # 화면 좌측 절반 (부상자 리스트 영역)
                        if e.button == 4: self.scroll_y1 = max(0, self.scroll_y1 - 1)
                        if e.button == 5: self.scroll_y1 = min(max(0, injured_count - self.max_rows), self.scroll_y1 + 1)
                    else: # 화면 우측 절반 (혹사 위험군 영역)
                        if e.button == 4: self.scroll_y2 = max(0, self.scroll_y2 - 1)
                        if e.button == 5: self.scroll_y2 = min(max(0, overworked_count - self.max_rows), self.scroll_y2 + 1)
                
                if e.button == 1:
                    for btn in self.buttons:
                        res = btn.handle_event(e)
                        if res: return res
        return None