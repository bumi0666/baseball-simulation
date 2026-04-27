from scenes.base_scene import Scene
from ui.button import Button
from config import *
from ui.layout import get_common_buttons, draw_common_ui
import pygame
import calendar
from datetime import datetime, date


class ScheduleScene(Scene):
    def __init__(self, state):
        self.state = state
        self.buttons = get_common_buttons(self)
        self.FONT       = pygame.font.SysFont("malgungothic", 18)
        self.FONT_SM    = pygame.font.SysFont("malgungothic", 14)
        self.FONT_LG    = pygame.font.SysFont("malgungothic", 22, bold=True)
        self.FONT_DAY   = pygame.font.SysFont("malgungothic", 13)

        # 날짜 형식 자동 감지 및 파싱
        def parse_date_key(d_str):
            """'YYYY-MM-DD' 또는 'MM/DD' 형식 모두 지원"""
            for fmt in ("%Y-%m-%d", "%m/%d", "%m-%d"):
                try:
                    return datetime.strptime(d_str, fmt)
                except ValueError:
                    continue
            return None

        self._date_fmt = None  # 실제 사용 중인 형식 저장
        if self.state.schedule:
            sample = next(iter(self.state.schedule.keys()))
            for fmt in ("%Y-%m-%d", "%m/%d", "%m-%d"):
                try:
                    datetime.strptime(sample, fmt)
                    self._date_fmt = fmt
                    break
                except ValueError:
                    continue

        # 현재 표시할 연/월 결정 (가장 이른 일정 기준)
        if self.state.schedule and self._date_fmt:
            first_date_str = sorted(self.state.schedule.keys())[0]
            first_date = datetime.strptime(first_date_str, self._date_fmt)
            # MM/DD 형식이면 연도가 없으므로 현재 연도 사용
            self.current_year  = first_date.year if "%Y" in self._date_fmt else date.today().year
            self.current_month = first_date.month
        else:
            today = date.today()
            self.current_year  = today.year
            self.current_month = today.month

        # 달력 레이아웃 상수 (왼쪽 공통 메뉴: 0~299px, 콘텐츠: 300px~)
        self.CX       = 310   # 콘텐츠 시작 X
        self.CY       = 55    # 콘텐츠 시작 Y
        self.CAL_W    = 670   # 달력 전체 너비
        self.CELL_W   = self.CAL_W // 7   # 열 너비 (~95)
        self.CELL_H   = 90    # 행 높이
        self.HEADER_H = 30    # 요일 헤더 높이

        # 색상 팔레트 (FM 다크 테마)
        self.C = {
            "bg":           (15,  20,  30),
            "panel":        (25,  32,  45),
            "header_bg":    (18,  24,  38),
            "border":       (45,  58,  80),
            "border_bright":(70,  90, 120),
            "text":         (210, 220, 235),
            "text_dim":     (100, 115, 140),
            "today_bg":     (30,  50,  80),
            "today_border": (80, 160, 255),
            "rest_text":    (80,  90, 110),
            "home_bg":      (20,  45,  25),
            "home_badge":   (50, 180,  80),
            "away_bg":      (45,  20,  20),
            "away_badge":   (220,  70,  70),
            "win":          (60, 220, 100),
            "loss":         (220,  70,  70),
            "draw":         (180, 180, 100),
            "score_text":   (255, 230, 100),
            "month_nav":    (60, 130, 220),
            "month_nav_h":  (100, 170, 255),
            "sat":          (100, 150, 220),
            "sun":          (220, 100, 100),
        }

        # 이전/다음 달 화살표 버튼 영역
        self.btn_prev = pygame.Rect(self.CX,            self.CY + 5, 32, 32)
        self.btn_next = pygame.Rect(self.CX + self.CAL_W - 32, self.CY + 5, 32, 32)
        self.hover_prev = False
        self.hover_next = False

    # ── 내부 헬퍼 ─────────────────────────────────────────────────

    def _get_month_games(self):
        """현재 연/월의 일정만 {day_int: game_dict} 형태로 반환"""
        result = {}
        if not self.state.schedule or not self._date_fmt:
            return result

        for d_str, game in self.state.schedule.items():
            try:
                d = datetime.strptime(d_str, self._date_fmt)
                year_match = (d.year == self.current_year) if "%Y" in self._date_fmt else True
                if year_match and d.month == self.current_month:
                    result[d.day] = game
            except ValueError:
                continue
        return result

    def _result_info(self, score_txt):
        """'3 : 1' 형식 점수 → (label, color)"""
        try:
            my_s, opp_s = map(int, score_txt.split(" : "))
            if my_s > opp_s:   return "W", self.C["win"]
            elif my_s < opp_s: return "L", self.C["loss"]
            else:               return "D", self.C["draw"]
        except:
            return "", self.C["text_dim"]

    def _draw_arrow(self, screen, rect, direction, hover):
        """삼각형 화살표 버튼"""
        color = self.C["month_nav_h"] if hover else self.C["month_nav"]
        cx, cy = rect.centerx, rect.centery
        if direction == "left":
            pts = [(cx+8, cy-8), (cx+8, cy+8), (cx-8, cy)]
        else:
            pts = [(cx-8, cy-8), (cx-8, cy+8), (cx+8, cy)]
        pygame.draw.polygon(screen, color, pts)

    def _draw_badge(self, screen, x, y, text, bg_color, text_color=(255,255,255)):
        """작은 배지 (HOME/AWAY 표시)"""
        surf = self.FONT_DAY.render(text, True, text_color)
        w, h = surf.get_width() + 8, surf.get_height() + 4
        badge_rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(screen, bg_color, badge_rect, border_radius=3)
        screen.blit(surf, (x + 4, y + 2))
        return w  # 배지 너비 반환

    # ── 메인 draw ─────────────────────────────────────────────────

    def draw(self, screen):
        screen.fill(self.C["bg"])
        draw_common_ui(screen, self.state, FONT)

        cx, cy  = self.CX, self.CY
        cal_w   = self.CAL_W
        cell_w  = self.CELL_W
        cell_h  = self.CELL_H
        hdr_h   = self.HEADER_H

        # ── 1. 월 헤더 ──────────────────────────────────────────
        month_names = ["January","February","March","April","May","June",
                       "July","August","September","October","November","December"]
        header_txt = f"{month_names[self.current_month-1]}  {self.current_year}"
        htxt_surf  = self.FONT_LG.render(header_txt, True, self.C["text"])

        # 헤더 배경 바
        pygame.draw.rect(screen, self.C["header_bg"], (cx, cy, cal_w, 42))
        pygame.draw.rect(screen, self.C["border"], (cx, cy, cal_w, 42), 1)

        # 월 텍스트 중앙
        screen.blit(htxt_surf, (cx + (cal_w - htxt_surf.get_width()) // 2, cy + 10))

        # 화살표
        self.btn_prev = pygame.Rect(cx + 8,          cy + 5, 32, 32)
        self.btn_next = pygame.Rect(cx + cal_w - 40, cy + 5, 32, 32)
        self._draw_arrow(screen, self.btn_prev, "left",  self.hover_prev)
        self._draw_arrow(screen, self.btn_next, "right", self.hover_next)

        # ── 2. 요일 헤더 ────────────────────────────────────────
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        day_colors = [self.C["text_dim"]] * 5 + [self.C["sat"], self.C["sun"]]
        hdr_y = cy + 44
        pygame.draw.rect(screen, self.C["panel"], (cx, hdr_y, cal_w, hdr_h))
        for col, (dn, dc) in enumerate(zip(day_names, day_colors)):
            surf = self.FONT_SM.render(dn, True, dc)
            screen.blit(surf, (cx + col * cell_w + (cell_w - surf.get_width()) // 2, hdr_y + 7))

        # ── 3. 달력 셀 ──────────────────────────────────────────
        month_games = self._get_month_games()
        today       = date.today()

        # 이달 1일의 요일(0=Mon) 및 총 일수
        first_weekday, total_days = calendar.monthrange(self.current_year, self.current_month)
        weeks = (first_weekday + total_days + 6) // 7  # 필요한 행 수

        grid_y = hdr_y + hdr_h

        # 전체 그리드 배경
        grid_h = weeks * cell_h
        pygame.draw.rect(screen, self.C["panel"], (cx, grid_y, cal_w, grid_h))

        for week in range(weeks):
            for dow in range(7):  # 0=Mon … 6=Sun
                day_num = week * 7 + dow - first_weekday + 1
                cell_x  = cx + dow * cell_w
                cell_y  = grid_y + week * cell_h

                # 이달 범위 밖이면 빈 셀
                if day_num < 1 or day_num > total_days:
                    pygame.draw.rect(screen, self.C["bg"],
                                     (cell_x, cell_y, cell_w, cell_h))
                    pygame.draw.rect(screen, self.C["border"],
                                     (cell_x, cell_y, cell_w, cell_h), 1)
                    continue

                # 오늘 여부
                is_today = (date(self.current_year, self.current_month, day_num) == today)

                # 경기 정보
                game = month_games.get(day_num)

                # 셀 배경 색상 결정
                if is_today:
                    cell_bg = self.C["today_bg"]
                elif game and game["type"] == "HOME":
                    cell_bg = self.C["home_bg"]
                elif game and game["type"] == "AWAY":
                    cell_bg = self.C["away_bg"]
                else:
                    cell_bg = self.C["panel"]

                pygame.draw.rect(screen, cell_bg, (cell_x, cell_y, cell_w, cell_h))

                # 테두리 (오늘 강조)
                if is_today:
                    pygame.draw.rect(screen, self.C["today_border"],
                                     (cell_x, cell_y, cell_w, cell_h), 2)
                else:
                    pygame.draw.rect(screen, self.C["border"],
                                     (cell_x, cell_y, cell_w, cell_h), 1)

                # 날짜 숫자
                day_color = self.C["sun"] if dow == 6 else \
                            self.C["sat"] if dow == 5 else self.C["text"]
                if is_today:
                    day_color = self.C["today_border"]

                day_surf = self.FONT_SM.render(str(day_num), True, day_color)
                screen.blit(day_surf, (cell_x + 5, cell_y + 4))

                # 경기 없거나 REST
                if not game or game["type"] == "REST":
                    if game and game["type"] == "REST":
                        rest_surf = self.FONT_DAY.render("REST", True, self.C["rest_text"])
                        screen.blit(rest_surf, (cell_x + 5, cell_y + 22))
                    continue

                # ── 경기 있는 셀 내용 ──────────────────────────
                inner_x = cell_x + 5
                badge_y = cell_y + 20

                # HOME/AWAY 배지
                if game["type"] == "HOME":
                    badge_w = self._draw_badge(screen, inner_x, badge_y,
                                               "HOME", self.C["home_badge"])
                else:
                    badge_w = self._draw_badge(screen, inner_x, badge_y,
                                               "AWAY", self.C["away_badge"])

                # 상대팀명
                opponent = game.get("opponent", "Unknown")
                # 셀 너비에 맞게 팀명 잘라내기
                opp_surf = self.FONT_DAY.render(opponent, True, self.C["text"])
                max_w    = cell_w - badge_w - 12
                if opp_surf.get_width() > max_w:
                    # 글자 수 줄이기
                    while len(opponent) > 1 and opp_surf.get_width() > max_w:
                        opponent = opponent[:-1]
                        opp_surf = self.FONT_DAY.render(opponent + "…", True, self.C["text"])
                    opp_surf = self.FONT_DAY.render(opponent + "…", True, self.C["text"])

                screen.blit(opp_surf, (inner_x + badge_w + 4, badge_y + 2))

                # 점수 & 승패
                if "score" in game:
                    score_txt = game["score"]
                    res_label, res_color = self._result_info(score_txt)

                    score_surf = self.FONT_SM.render(score_txt, True, self.C["score_text"])
                    screen.blit(score_surf, (inner_x, cell_y + 42))

                    if res_label:
                        res_surf = self.FONT_SM.render(res_label, True, res_color)
                        # 승패 배경 원
                        res_x = inner_x + score_surf.get_width() + 8
                        res_cy = cell_y + 42 + res_surf.get_height() // 2
                        pygame.draw.circle(screen, res_color, (res_x + 8, res_cy), 9)
                        pygame.draw.circle(screen, (0, 0, 0), (res_x + 8, res_cy), 9, 0)
                        pygame.draw.circle(screen, res_color, (res_x + 8, res_cy), 8)
                        lbl_surf = self.FONT_DAY.render(res_label, True, (15, 15, 15))
                        screen.blit(lbl_surf, (res_x + 8 - lbl_surf.get_width() // 2,
                                               res_cy     - lbl_surf.get_height() // 2))

                # 예정된 경기 (점수 없음)
                else:
                    upcoming_surf = self.FONT_DAY.render("Scheduled", True, self.C["text_dim"])
                    screen.blit(upcoming_surf, (inner_x, cell_y + 42))

        # ── 4. 범례 ─────────────────────────────────────────────
        legend_y = grid_y + grid_h + 12
        items = [
            (self.C["home_badge"], "HOME"),
            (self.C["away_badge"], "AWAY"),
            (self.C["win"],   "Win"),
            (self.C["loss"],  "Loss"),
            (self.C["draw"],  "Draw"),
        ]
        lx = cx
        for color, label in items:
            pygame.draw.rect(screen, color, (lx, legend_y + 3, 12, 12), border_radius=2)
            lbl = self.FONT_DAY.render(label, True, self.C["text_dim"])
            screen.blit(lbl, (lx + 16, legend_y))
            lx += lbl.get_width() + 32

        # ── 5. 공통 버튼 ────────────────────────────────────────
        for btn in self.buttons:
            btn.draw(screen)

    # ── update ────────────────────────────────────────────────────

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()

        for btn in self.buttons:
            btn.update_hover(mouse_pos)

        self.hover_prev = self.btn_prev.collidepoint(mouse_pos)
        self.hover_next = self.btn_next.collidepoint(mouse_pos)

        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                # 이전 달
                if self.btn_prev.collidepoint(e.pos):
                    self.current_month -= 1
                    if self.current_month < 1:
                        self.current_month = 12
                        self.current_year -= 1

                # 다음 달
                elif self.btn_next.collidepoint(e.pos):
                    self.current_month += 1
                    if self.current_month > 12:
                        self.current_month = 1
                        self.current_year += 1

                else:
                    for btn in self.buttons:
                        res = btn.handle_event(e)
                        if res:
                            return res
        return None