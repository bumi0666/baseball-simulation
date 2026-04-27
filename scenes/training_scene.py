from scenes.base_scene import Scene
from ui.button import Button
from config import *
from ui.layout import get_common_buttons, draw_common_ui # 공통 레이아웃 임포트
import pygame


class TrainingScene(Scene):
    def __init__(self, players, state):
        self.players = players
        self.state = state
        self.common_buttons = get_common_buttons(self)
        self.FONT = FONT
        self.player_buttons = []
        self.smallFONT = pygame.font.SysFont(None, 30)
        
        # --- 스크롤 변수 추가 ---
        self.scroll_y = 0
        self.scroll_speed = 50
        self.content_height = 0
        self.screen_h = 720 # 기본 화면 높이 (실제 설정에 맞게 수정하세요)
        self.list_view_h = 550 # 리스트가 보일 영역의 높이
        # ----------------------
        
        self.setup_ui()

    def setup_ui(self):
        self.player_buttons = []
        cx, cy = 210, 130
        for i, p in enumerate(self.players):
            mode = p.status.get("training_mode", "TRAIN")
        
            # 버튼 텍스트 결정
            if p.status.get("is_injured"):
                btn_txt = "DISABLED"
            elif mode == "TRAIN":
                btn_txt = "TO DOUBLE" # 클릭 시 DOUBLE로 변경됨을 암시
            elif mode == "DOUBLE":
                btn_txt = "TO REST"
            else:
                btn_txt = "TO TRAIN"
            btn = Button(
                (cx + 650 - 10, cy + (i * 40) - 50, 120, 30), 
                btn_txt, 
                lambda player=p: self.toggle_mode(player), font=self.smallFONT
            )
            self.player_buttons.append(btn)
        
        # 전체 콘텐츠 높이 계산 (시작 y축 130 + 선수 인원 * 40px)
        self.content_height = 130 + (len(self.players) * 40)

    def toggle_mode(self, player):
        if player.status.get("is_injured"):
            return
        current = player.status.get("training_mode", "TRAIN")
        if current == "TRAIN":
            player.status["training_mode"] = "DOUBLE"
        elif current == "DOUBLE":
            player.status["training_mode"] = "REST"
        else:
            player.status["training_mode"] = "TRAIN"
        self.setup_ui() 

    def draw(self, screen):
        screen.fill((20, 20, 20))
        draw_common_ui(screen, self.state, self.FONT)
        
        cx, cy = 210, 40
        screen.blit(self.FONT.render("TRAINING CENTER", True, white), (cx, cy))
        
        # 헤더 영역 (헤더는 스크롤되지 않게 고정)
        header_y = cy + 50
        pygame.draw.rect(screen, (50, 50, 50), (cx, header_y, 1000, 30))
        headers = [("NAME", 10 + 10), ("CONDITION", 200 - 50), ("FATIGUE", 350 - 40), ("STATUS", 500 - 20), ("ACTION", 650)]
        for text, x_off in headers:
            screen.blit(self.FONT.render(text, True, white), (cx + x_off, header_y + 5))
        
        # --- 스크롤바 시각화 ---
        if self.content_height > self.list_view_h:
            bar_x = cx + 1010
            bar_w = 8
            # 화면에 표시되는 비율만큼 막대 길이 계산
            bar_h = int(self.list_view_h * (self.list_view_h / self.content_height))
            # 현재 스크롤 위치 비율로 막대 y 위치 계산
            scroll_ratio = -self.scroll_y / (self.content_height - self.list_view_h)
            bar_y = header_y + 40 + int(scroll_ratio * (self.list_view_h - bar_h))
            
            pygame.draw.rect(screen, (40, 40, 40), (bar_x, header_y + 40, bar_w, self.list_view_h))
            pygame.draw.rect(screen, (100, 100, 100), (bar_x, bar_y, bar_w, bar_h))

        # 선수 리스트 출력 (scroll_y 반영)
        for i, p in enumerate(self.players):
            # 스크롤 오프셋 적용
            row_y = 130 + (i * 40) + self.scroll_y
            
            # 화면 영역 밖으로 나간 항목은 그리지 않음 (최적화)
            if row_y < header_y + 30 or row_y > header_y + self.list_view_h + 30:
                continue

            cond_val = p.status.get('condition', 0)
            fatigue_val = p.status.get('fatigue', 0)
            cond_color = (100, 200, 255) if cond_val < 70 else (150, 255, 150)
            fatigue_color = (255, 100, 100) if fatigue_val > 200 else white
            
            screen.blit(self.smallFONT.render(p.name, True, white), (cx + 20, row_y))
            screen.blit(self.smallFONT.render(f"{int(cond_val)}%", True, cond_color), (cx + 200 - 10, row_y))
            screen.blit(self.smallFONT.render(f"{int(fatigue_val)}", True, fatigue_color), (cx + 350, row_y))
            mode = p.status.get("training_mode", "TRAIN")
            if p.status.get("is_injured"):
                status_txt, status_clr = "INJURED", (255, 50, 50)
            elif mode == "DOUBLE":
                status_txt, status_clr = "DOUBLE", (255, 200, 0) # 노란색/금색
            elif mode == "REST":
                status_txt, status_clr = "RESTING", (100, 100, 255) # 파란색
            else:
                status_txt, status_clr = "TRAINING", (200, 200, 200) # 회색
            screen.blit(self.smallFONT.render(status_txt, True, status_clr), (cx + 500 - 20, row_y))
            
            # --- 중요: 버튼의 Rect 위치를 스크롤에 맞춰 업데이트 ---
            self.player_buttons[i].rect.y = row_y - 5
            self.player_buttons[i].draw(screen)

        for btn in self.common_buttons:
            btn.draw(screen)

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        
        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                # 휠 동작 (4: Up, 5: Down)
                if e.button == 4: # 위로 스크롤
                    self.scroll_y = min(0, self.scroll_y + self.scroll_speed)
                elif e.button == 5: # 아래로 스크롤
                    limit = min(0, self.list_view_h - (self.content_height - 130))
                    self.scroll_y = max(limit, self.scroll_y - self.scroll_speed)
                
                if e.button == 1:
                    # 버튼 클릭 처리
                    for btn in self.common_buttons + self.player_buttons:
                        # 버튼이 현재 화면(리스트 영역) 안에 있을 때만 클릭 허용하는 로직을 추가하면 더 정교해집니다.
                        res = btn.handle_event(e)
                        if res: return res
        
        for btn in self.common_buttons + self.player_buttons:
            btn.update_hover(mouse_pos)
            
        return None