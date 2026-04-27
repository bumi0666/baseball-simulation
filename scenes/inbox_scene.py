from scenes.base_scene import Scene
from ui.button import Button
from config import *
from datetime import date, timedelta
from ui.layout import get_common_buttons, draw_common_ui
import pygame

class InboxScene(Scene):
    def __init__(self, state):
        self.state = state
        self.buttons = get_common_buttons(self)
        
        # 폰트 설정
        self.FONT = pygame.font.SysFont(None, 32)
        self.SMALL_FONT = pygame.font.SysFont(None, 26)
        
        # UI 레이아웃 설정
        self.list_x, self.list_y = 210, 80
        self.list_w, self.list_h = 350, height - 120
        self.content_x = self.list_x + self.list_w + 20
        self.content_w = width - self.content_x - 20
        
        # 스크롤 관련 변수
        self.selected_mail = None
        self.scroll_offset = 0  # 몇 번째 메시지부터 보여줄 것인가
        self.row_height = 60    # 각 메시지 칸의 높이
        self.visible_rows = self.list_h // self.row_height # 한 번에 보이는 개수

    def draw(self, screen):
        screen.fill((20, 20, 20))
        draw_common_ui(screen, self.state, FONT)
        
        messages = self.state.get("inbox", [])
        # 최신 메시지가 위로 오도록 역순 리스트 생성
        rev_messages = list(reversed(messages))
        
        # 1. 메시지 리스트 영역 배경
        list_rect = pygame.Rect(self.list_x, self.list_y, self.list_w, self.list_h)
        pygame.draw.rect(screen, (255, 255, 255), list_rect)
        pygame.draw.rect(screen, (200, 200, 200), list_rect, 2)

        # 2. 메시지 항목 렌더링 (스크롤 오프셋 적용)
        start_idx = self.scroll_offset
        end_idx = min(start_idx + self.visible_rows, len(rev_messages))

        for i in range(start_idx, end_idx):
            mail = rev_messages[i]
            # 그려질 상대 위치 계산 (i - start_idx)
            draw_idx = i - start_idx
            item_y = self.list_y + draw_idx * self.row_height
            item_rect = pygame.Rect(self.list_x, item_y, self.list_w, self.row_height)
            
            # 선택 하이라이트
            if self.selected_mail == mail:
                pygame.draw.rect(screen, (180, 200, 255), item_rect)
            
            pygame.draw.rect(screen, (230, 230, 230), item_rect, 1) # 구분선
            
            # 텍스트 출력
            color = (0, 0, 0) if mail.get("read") else (200, 50, 50)
            date_txt = self.SMALL_FONT.render(mail['date'], True, (120, 120, 120))
            subject_txt = self.FONT.render(mail['subject'], True, color)
            
            screen.blit(date_txt, (item_rect.x + 10, item_rect.y + 8))
            screen.blit(subject_txt, (item_rect.x + 10, item_rect.y + 30))

        # 3. 스크롤바 시각화 (리스트 우측에 얇게 표시)
        if len(rev_messages) > self.visible_rows:
            bar_x = self.list_x + self.list_w - 8
            pygame.draw.rect(screen, (220, 220, 220), (bar_x, self.list_y, 5, self.list_h)) # 트랙
            
            ratio = self.visible_rows / len(rev_messages)
            handle_h = max(20, int(self.list_h * ratio))
            handle_y = self.list_y + int((self.list_h - handle_h) * (self.scroll_offset / (len(rev_messages) - self.visible_rows)))
            pygame.draw.rect(screen, (150, 150, 150), (bar_x, handle_y, 5, handle_h)) # 핸들

        # 4. 메시지 본문 영역 (오른쪽 상자 - 이전과 동일)
        content_rect = pygame.Rect(self.content_x, self.list_y, self.content_w, self.list_h)
        pygame.draw.rect(screen, (252, 252, 252), content_rect)
        pygame.draw.rect(screen, (180, 180, 180), content_rect, 2)

        if self.selected_mail:
            m = self.selected_mail
            screen.blit(self.FONT.render(m['subject'], True, (0, 0, 0)), (self.content_x + 20, self.list_y + 20))
            pygame.draw.line(screen, (220, 220, 220), (self.content_x + 20, self.list_y + 60), (self.content_x + self.content_w - 20, self.list_y + 60))
            
            lines = m['body'].split('\n')
            for j, line in enumerate(lines):
                screen.blit(self.SMALL_FONT.render(line, True, (40, 40, 40)), (self.content_x + 20, self.list_y + 80 + j * 25))
        
        for btn in self.buttons:
            btn.draw(screen)

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        messages = list(reversed(self.state.get("inbox", [])))
        
        for btn in self.buttons:
            btn.update_hover(mouse_pos)

        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                # 마우스 휠 스크롤 처리
                if e.button == 4: # Wheel Up
                    self.scroll_offset = max(0, self.scroll_offset - 1)
                elif e.button == 5: # Wheel Down
                    max_off = max(0, len(messages) - self.visible_rows)
                    self.scroll_offset = min(max_off, self.scroll_offset + 1)
                
                # 왼쪽 클릭 처리
                if e.button == 1:
                    # 현재 화면에 보이는 항목들 중에서 클릭 체크
                    start = self.scroll_offset
                    end = min(start + self.visible_rows, len(messages))
                    
                    for i in range(start, end):
                        draw_idx = i - start
                        item_rect = pygame.Rect(self.list_x, self.list_y + draw_idx * self.row_height, self.list_w, self.row_height)
                        if item_rect.collidepoint(e.pos):
                            self.selected_mail = messages[i]
                            self.selected_mail["read"] = True
                            return None # 선택 완료 시 종료
                    
                    for btn in self.buttons:
                        res = btn.handle_event(e)
                        if res: return res
        return None