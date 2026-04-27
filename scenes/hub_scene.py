from scenes.base_scene import Scene
from ui.button import Button
from config import *
from ui.layout import get_common_buttons, draw_common_ui
import pygame


class HubScene(Scene):
    def __init__(self, state):
        self.state = state
        self.buttons = get_common_buttons(self)
        
        self.TITLE_FONT = pygame.font.SysFont("malgungothic", 40, bold=True)
        self.DESC_FONT = pygame.font.SysFont("malgungothic", 25)
        self.SMALL_FONT = pygame.font.SysFont("malgungothic", 18)

        self.team_rects = []

        # 팀 데이터가 없을 경우를 대비한 초기화 (보통 GameState에서 수행)
        if not hasattr(self.state, 'team_stats'):
            self.state.team_stats = {
                "나의 팀": {"win": 12, "loss": 8, "games": 20},
                "라이벌즈": {"win": 15, "loss": 5, "games": 20},
                "타이거즈": {"win": 10, "loss": 10, "games": 20},
                "베어스": {"win": 8, "loss": 12, "games": 20},
                "이글스": {"win": 5, "loss": 15, "games": 20}
            }

    def draw_standings(self, screen, x, y):
        # 1. 데이터 가공 (무승부 포함 승률 계산 및 정렬)
        table_data = []
        for name, s in self.state.team_stats.items():
            win = s.get("win", 0)
            loss = s.get("loss", 0)
            draw = s.get("draw", 0) # 무승부 데이터 가져오기
        
            # KBO 방식 승률: 승 / (승 + 패) -> 무승부는 계산에서 제외
            total_decided = win + loss + draw
            wpct = win / (win + loss) if (win + loss) > 0 else 0.0
        
            table_data.append({
            "name": name, "win": win, "loss": loss, "draw": draw, 
            "games": s.get("games", 0), "wpct": wpct
            })
    
        # 승률 내림차순 -> 승수 내림차순 정렬
        table_data.sort(key=lambda x: (x["wpct"], x["win"], -x["loss"]), reverse=True)

        # 2. 레이아웃 설정 (D 추가, 간격 조정)
        headers = ["RANK", "TEAM", "G", "W", "L", "D", "WPCT", "GB"]
        col_widths = [60, 160, 50, 45, 45, 45, 80, 60] # 컬럼 너비 재조정
        row_height = 45
        total_width = sum(col_widths)

        # 헤더 그리기
        pygame.draw.rect(screen, (30, 40, 60), (x, y, total_width, row_height))
        curr_x = x
        for i, h in enumerate(headers):
            txt = self.SMALL_FONT.render(h, True, (0, 255, 255))
            screen.blit(txt, (curr_x + 15, y + 12))
            curr_x += col_widths[i]

        # 3. 데이터 행 그리기
        top_win, top_loss = table_data[0]["win"], table_data[0]["loss"]
    
        for i, team in enumerate(table_data):
            row_y = y + row_height + (i * row_height)
        
            # 하이라이트 색상 설정 (나의 팀: Lions)
            if team["name"] == "Lions":
                bg_color = (60, 70, 90) # 우리 팀 강조 색상
            else:
                bg_color = (40, 42, 48) if i % 2 == 0 else (30, 32, 38)
        
            pygame.draw.rect(screen, bg_color, (x, row_y, total_width, row_height))
        
            # 게임차(GB) 계산
            gb = ((top_win - team["win"]) + (team["loss"] - top_loss)) / 2.0
            gb_str = "-" if i == 0 else f"{gb:.1f}"

            # 텍스트 데이터 준비 (D 포함)
            row_values = [
            f"{i+1}", team["name"], f"{team['games']}", 
            f"{team['win']}", f"{team['loss']}", f"{team['draw']}", 
            f"{team['wpct']:.3f}", gb_str
            ]

            curr_x = x
            for j, val in enumerate(row_values):
                color = (255, 255, 255)
                if team["name"] == "Lions":
                    color = (255, 215, 0) # 금색 하이라이트
            
                txt = self.SMALL_FONT.render(val, True, color)
                if j == 1:
                # 텍스트가 그려지는 위치와 크기로 영역 생성
                    text_rect = pygame.Rect(curr_x + 15, row_y + 12, col_widths[j], row_height)
                    self.team_rects.append((text_rect, team["name"]))

                screen.blit(txt, (curr_x + 15, row_y + 12))
                curr_x += col_widths[j]

        # 외곽 테두리
        pygame.draw.rect(screen, (100, 100, 100), (x, y, total_width, row_height + len(table_data)*row_height), 1)

    def draw(self, screen):
        screen.fill((20, 20, 20)) # 배경색을 어둡게 변경 (가독성)
        self.team_rects = []
        draw_common_ui(screen, self.state, FONT)
        
        cx, cy = 250, 50
        screen.blit(self.TITLE_FONT.render("SEASON STANDINGS", True, (0, 255, 255)), (cx, cy))
        
        # 순위표 그리기 (X좌표를 왼쪽 메뉴 피해서 배치)
        self.draw_standings(screen, cx, cy + 80)
        
        # 메시지 알림 (재정 정보는 삭제됨)
        unread_count = len([m for m in self.state.inbox if not m.get("read")])
        #if unread_count > 0:
            #msg_str = f"● New messages: {unread_count}"
            #screen.blit(self.DESC_FONT.render(msg_str, True, (255, 100, 100)), (cx, cy + 450))

        for btn in self.buttons:
            btn.draw(screen)
            
    # HubScene의 draw 메서드 내부
    def draw_next_match(self, screen, x, y):
        current_date_str = self.get_current_date_str() # 현재 날짜를 "01/05" 형태로 반환하는 함수
        match_info = self.state.schedule.get(current_date_str)
    
        if match_info:
            opp = match_info['opponent']
            m_type = match_info['type']
        
        # 대진표 텍스트 (예: Dragons VS Tigers)
            match_text = f"NEXT MATCH: {self.state.user_team} vs {opp}"
            loc_text = f"Location: {'Home Ground' if m_type == 'HOME' else 'Away'}"
        
            screen.blit(self.TITLE_FONT.render(match_text, True, (255, 255, 255)), (x, y))
            screen.blit(self.DESC_FONT.render(loc_text, True, (200, 200, 200)), (x, y + 50))
        else:
            screen.blit(self.DESC_FONT.render("No Match Scheduled Today", True, (150, 150, 150)), (x, y))

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update_hover(mouse_pos)

        hovering = False
        for rect, team_name in self.team_rects:
            if rect.collidepoint(mouse_pos):
                hovering = True
                break

        #if hovering:
        #    pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
        #else:
        #    pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 1:

                    for rect, team_name in self.team_rects:
                        if rect.collidepoint(e.pos):
                            # 팀 이름을 담아 Detail Scene으로 전환 요청
                            return ("team_detail", team_name)
                    for btn in self.buttons:
                        res = btn.handle_event(e)
                        if res: return res
        return None