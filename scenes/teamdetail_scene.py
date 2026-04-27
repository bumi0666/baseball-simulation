from scenes.base_scene import Scene
from ui.button import Button
from config import *
from ui.layout import get_common_buttons, draw_common_ui
import pygame

class TeamDetailScene(Scene):
    def __init__(self, state, team_name):
        self.state = state
        self.team_name = team_name
        
        # 1. state.team_data(JSON에서 로드된 데이터)에서 팀 정보 가져오기
        #self.team_info = state.team_data.get(team_name, {})
        
        # 2. 승패 기록 및 순위 데이터
        #self.stats = state.team_stats.get(team_name, {"win": 0, "loss": 0, "draw": 0})
        #self.form = self.team_info.get("recent_form", [])[-5:] # 최근 5경기 결과
        
        #self.buttons = [
         #   Button((20, 20, 100, 35), "BACK", self.back)
        #]

        self.commonbuttons = get_common_buttons(self)
        self.roster_btn = Button((230, 30, 150, 40), "View Roster", lambda: ("view_team", self.team_name))

        # 3. 팀 로고 로드 (실제 파일이 없을 경우를 대비해 예외처리)
        try:
            self.logo = pygame.image.load(self.team_info.get("logo_path", ""))
            self.logo = pygame.transform.scale(self.logo, (100, 100))
        except:
            self.logo = None
            
        #self.smallFONT = pygame.font.SysFont(None, 20)    
        self.FONT_NORMAL = pygame.font.SysFont(None, 30)
        self.FONT_SMALL = pygame.font.SysFont(None, 20)

    def draw(self, screen):
        self.team_info = self.state.team_data.get(self.team_name, {})
        self.form = self.team_info.get("recent_form", [])[-5:]
        #stats = self.state.team_stats.get(self.team_name, {"win": 0, "loss": 0, "draw": 0})
        
        screen.fill((20, 20, 20))
        draw_common_ui(screen, self.state, FONT)

        lx, ly, lw, lh = 30 + 200, 80, 300, 500
        self.draw_section(screen, "CLUB INFO", lx, ly, lw, lh)
        
        if self.logo:
            screen.blit(self.logo, (lx + 100, ly + 50))
        else:
            pygame.draw.rect(screen, (60, 60, 60), (lx + 100, ly + 50, 100, 100)) # 로고 없을 시 대용

        y_off = ly + 170
        info_items = [
            f"Name: {self.team_name}",
            f"Attendance: {self.team_info.get('attendance', 0):,}",
            f"Finance: {self.team_info.get('finance_status', 'N/A')}",
            f"Balance: ${self.team_info.get('budget', 0):,}",
            f"Facilities: {self.team_info.get('facilities', 'N/A')}"
        ]
        for item in info_items:
            txt = self.FONT_NORMAL.render(item, True, white)
            screen.blit(txt, (lx + 20, y_off))
            y_off += 40

        # --- [CENTER BOX]: Performance & Venue (스쿼드 요약, 경기장, 최근 전적) ---
        mx, my, mw, mh = 350 + 200, 80, 400, 500
        self.draw_section(screen, "SQUAD & VENUE", mx, my, mw, mh)
        
        # 경기장 정보
        stadium_txt = self.FONT_NORMAL.render(f"Stadium: {self.team_info.get('stadium', 'N/A')}", True, white)
        screen.blit(stadium_txt, (mx + 20, my + 50))
        
        # 최근 전적 (Recent Form) - 동그라미 아이콘으로 표시
        form_label = self.FONT_SMALL.render("RECENT FORM", True, (200, 200, 200))
        screen.blit(form_label, (mx + 20, my + 100))
        for i, res in enumerate(self.form):
            color = (0, 200, 0) if res == "W" else (200, 0, 0) if res == "L" else (200, 200, 0)
            pygame.draw.circle(screen, color, (mx + 40 + (i * 45), my + 140), 18)
            f_txt = self.FONT_SMALL.render(res, True, white)
            screen.blit(f_txt, (mx + 33 + (i * 45), my + 130))

        # --- [RIGHT BOX]: Leadership (감독, 주장) ---
        rx, ry, rw, rh = 770 + 200  , 80, 280, 500
        self.draw_section(screen, "LEADERSHIP", rx, ry, rw, rh)
        
        leaders = [
            ("Manager", self.team_info.get("manager", "Vacant")),
            ("Captain", self.team_info.get("captain", "Vacant"))
        ]
        for i, (title, name) in enumerate(leaders):
            t_surf = self.FONT_SMALL.render(title, True, (200, 200, 200))
            n_surf = self.FONT_NORMAL.render(name, True, white)
            screen.blit(t_surf, (rx + 20, ry + 60 + (i * 100)))
            screen.blit(n_surf, (rx + 20, ry + 90 + (i * 100)))
            
        field_y = my + 180
        field_h = mh - 200
        self.draw_mini_field(screen, mx, field_y, mw, field_h)

        #for btn in self.buttons:
         #   btn.draw(screen)
        self.roster_btn.draw(screen)
        for btn in self.commonbuttons:
            btn.draw(screen)

    def draw_section(self, screen, title, x, y, w, h):
        """FM 스타일의 구획 박스"""
        pygame.draw.rect(screen, (45, 50, 60), (x, y, w, h), border_radius=3)
        pygame.draw.rect(screen, (60, 80, 150), (x, y, w, 30), border_radius=3) # 상단 바
        t_surf = self.FONT_SMALL.render(title, True, white)
        screen.blit(t_surf, (x + 10, y + 5))
        
    def draw_mini_field(self, screen, x, y, w, h):
        """단순화된 사각형 필드와 포지션 마커"""
        # 1. 기본 필드 (단순 녹색 사각형)
        field_rect = (x + 10, y + 10, w - 20, h - 20)
        pygame.draw.rect(screen, (34, 100, 34), field_rect, border_radius=5)
    
        # 2. 중심점 설정 (홈 플레이트 위치)
        cx, cy = x + w // 2, y + h - 60
    
        # 3. 베이스라인 (흰색 다이아몬드 선)
        # 2루를 위로, 1/3루를 양옆으로 하는 마름모
        diamond_pts = [
        (cx, cy - 120), # 2루
        (cx + 90, cy - 30), # 1루
        (cx, cy + 10),  # 홈
        (cx - 90, cy - 30)  # 3루
        ]
        pygame.draw.lines(screen, (200, 200, 200), True, diamond_pts, 2)

        # 4. 포지션별 마커 배치
        # 포지션 이름과 상대 좌표 (cx, cy 기준)
        pos_map = {
        "P":  (cx, cy - 55),
        "C":  (cx, cy + 10),
        "1B": (cx + 90, cy - 30),
        "2B": (cx + 50, cy - 100),
        "3B": (cx - 90, cy - 30),
        "SS": (cx - 50, cy - 100),
        "LF": (cx - 110, cy - 170),
        "CF": (cx, cy - 210),
        "RF": (cx + 110, cy - 170)
        }

        for pos, pos_xy in pos_map.items():
            # 선수 위치 원 (흰색 테두리에 어두운 원)
            pygame.draw.circle(screen, (30, 30, 30), pos_xy, 14)
            pygame.draw.circle(screen, (255, 255, 255), pos_xy, 14, 2)
        
            # 포지션 텍스트 (P, C, 1B 등)
            p_txt = self.FONT_SMALL.render(pos, True, (255, 255, 255))
            txt_rect = p_txt.get_rect(center=pos_xy)
            screen.blit(p_txt, txt_rect)
            
    #def back(self):
    #    return "hub"

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        self.roster_btn.update_hover(mouse_pos)

        for btn in self.commonbuttons:
            btn.update_hover(mouse_pos)

        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                res = self.roster_btn.handle_event(event)
                if res: return res
                
                for btn in self.commonbuttons:
                    res = btn.handle_event(event)
                    if res: return res
        return None