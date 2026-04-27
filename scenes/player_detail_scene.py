from scenes.base_scene import Scene
from ui.button import Button
from config import *
from ui.layout import get_common_buttons, draw_common_ui
from scenes.contract_scene import ContractScene
import pygame

def attr_color(val):
    if val >= 80:   return (60, 180, 75)
    elif val >= 70: return (240, 200, 80)
    elif val >= 60: return (230, 150, 60)
    else:           return (200, 80, 80)

def draw_attr_bar(screen, x, y, label, cur_val, pot_val):
    BAR_W = 160
    BAR_H = 14
    bar_x = x + 100

    label_surf = pygame.font.SysFont(None, 26).render(label, True, black)
    screen.blit(label_surf, (x, y))

    bg_rect = pygame.Rect(bar_x, y, BAR_W, BAR_H)
    pygame.draw.rect(screen, (200, 200, 200), bg_rect)

    pot_w   = int(BAR_W * (pot_val / 100))
    pot_rect = pygame.Rect(bar_x, y, pot_w, BAR_H)
    pygame.draw.rect(screen, (170, 170, 170), pot_rect)

    cur_w   = int(BAR_W * (cur_val / 100))
    cur_rect = pygame.Rect(bar_x, y, cur_w, BAR_H)
    pygame.draw.rect(screen, attr_color(cur_val), cur_rect)

    pygame.draw.rect(screen, (80, 80, 80), bg_rect, 1)

    val_str  = f"{cur_val}/{pot_val}"
    val_surf = pygame.font.SysFont(None, 28).render(val_str, True, black)
    screen.blit(val_surf, (bar_x + BAR_W + 10, y))


class PlayerDetailScene(Scene):
    def __init__(self, player, state):
        self.player = player
        self.state  = state
        self.buttons = [
            Button((width - 160, height - 80, 120, 50), "BACK",     self.back),
            Button((width - 320, height - 80, 140, 50), "CONTRACT", self.go_contract)
        ]
        self.SMALL_FONT = pygame.font.SysFont(None, 24)

    def back(self):
        return self.state.prevscene if self.state.prevscene else "team"

    # ── 헬퍼 ──────────────────────────────────────────────
    def _calc_batter_rates(self, s):
        ab  = s.get("ab", 0)
        h   = s.get("h",  0)
        bb  = s.get("bb", 0)
        hr  = s.get("hr", 0)
        d2  = s.get("2b", 0)
        d3  = s.get("3b", 0)
        avg = h / ab if ab > 0 else 0.0
        pa  = ab + bb
        obp = (h + bb) / pa if pa > 0 else 0.0
        singles = max(0, h - d2 - d3 - hr)
        tb  = singles + 2*d2 + 3*d3 + 4*hr
        slg = tb / ab if ab > 0 else 0.0
        ops = obp + slg
        return avg, obp, slg, ops

    # ── draw ──────────────────────────────────────────────
    def draw(self, screen):
        screen.fill((20, 20, 20))

        face_rect = pygame.Rect(MARGIN, 15, 60, 60)
        pygame.draw.rect(screen, (150, 150, 150), face_rect)

        try:
            salary_str = f"${int(self.player.salary()):,}"
        except:
            salary_str = str(self.player.salary())

        title_str = f"{self.player.backnumber}. {self.player.name} | {self.player.pos} | Age {self.player.age()}"
        sub_title  = f"Salary {salary_str} ({self.player.contract_begin()}~{self.player.contract_end()})"

        screen.blit(FONT.render(title_str, True, white),            (face_rect.right + 20, 20))
        screen.blit(self.SMALL_FONT.render(sub_title, True, white), (face_rect.right + 20, 55))

        BOX_W = (width - (MARGIN * 2) - (GAP * 2)) // 3

        # ── 왼쪽 상단: Bio ──
        lt_rect = pygame.Rect(MARGIN, CONTENT_TOP, BOX_W, TOP_H)
        pygame.draw.rect(screen, (215, 215, 215), lt_rect)
        pygame.draw.rect(screen, (140, 140, 140), lt_rect, 2)

        bio_info = [
            f"Birth: {self.player.birth()}",
            f"Height: {self.player.height()}cm",
            f"Weight: {self.player.weight()}kg",
            f"Nationality: {self.player.nationality()}",
            f"Contract: {self.player.contract_years_left()} Yrs"
        ]
        for i, line in enumerate(bio_info):
            screen.blit(FONT.render(line, True, black), (lt_rect.x + 15, lt_rect.y + 20 + i * 32))

        # ── 중앙 상단: Attributes ──
        ct_rect = pygame.Rect(lt_rect.right + GAP, CONTENT_TOP, BOX_W, TOP_H)
        pygame.draw.rect(screen, (215, 215, 215), ct_rect)
        pygame.draw.rect(screen, (140, 140, 140), ct_rect, 2)
        screen.blit(self.SMALL_FONT.render("Attributes (Cur / Pot)", True, (50, 50, 50)),
                    (ct_rect.x + 10, ct_rect.y + 5))

        attrs = (["contact", "power", "eye", "run", "defense"]
                 if self.player.is_batter()
                 else ["velocity", "control", "stuff", "stamina", "defense"])

        for i, attr in enumerate(attrs):
            if attr in self.player.attr:
                cur = self.player.get_attr(attr)
                pot = self.player.get_pot(attr)
                draw_attr_bar(screen, ct_rect.x + 10, ct_rect.y + 35 + i * 34,
                              attr.capitalize(), cur, pot)

        # ── 오른쪽 상단: Status ──
        rt_rect = pygame.Rect(ct_rect.right + GAP, CONTENT_TOP, BOX_W, TOP_H)
        pygame.draw.rect(screen, (210, 220, 210), rt_rect)
        pygame.draw.rect(screen, (140, 150, 140), rt_rect, 2)

        fatigue = self.player.status.get("fatigue", 0)
        cond_icon = "Exhausted" if fatigue >= 200 else ("Worn" if fatigue >= 100 else "Free")
        is_injured   = self.player.status.get("is_injured", False)
        health_text  = "INJURED" if is_injured else "HEALTHY"
        health_color = (200, 50, 50) if is_injured else (50, 120, 50)

        st_info = [
            ("Health",    f"{int(self.player.status.get('health', 0) / 10)}%"),
            ("Condition", f"{self.player.status.get('condition', 0)}%"),
            ("Fatigue",   cond_icon),
            ("Status",    health_text)
        ]
        for i, (label, val) in enumerate(st_info):
            screen.blit(FONT.render(f"{label}:", True, black),
                        (rt_rect.x + 20, rt_rect.y + 30 + i * 45))
            screen.blit(FONT.render(val, True, health_color if label == "Status" else black),
                        (rt_rect.x + 160, rt_rect.y + 30 + i * 45))

        # ── 좌측 하단: Live Stats ──
        lb_rect = pygame.Rect(MARGIN, lt_rect.bottom + GAP, LEFT_W, BOTTOM_H)
        pygame.draw.rect(screen, (215, 215, 215), lb_rect)
        pygame.draw.rect(screen, (140, 140, 140), lb_rect, 2)

        from datetime import date, timedelta
        y, m, d = self.state.base_date
        current_date_obj  = date(y, m, d) + timedelta(days=self.state.current_day - 1)
        current_game_year = current_date_obj.year

        curr_season = next((c for c in self.player.career
                            if c.get("season") == current_game_year), None)

        if curr_season:
            s           = curr_season.get("stats", {})
            season_year = curr_season.get("season", "2024")

            title_surf = self.SMALL_FONT.render(f"LIVE STATS - {season_year}", True, (30, 30, 30))
            screen.blit(title_surf, (lb_rect.x + 15, lb_rect.y + 12))
            pygame.draw.line(screen, (180, 180, 180),
                             (lb_rect.x + 10, lb_rect.y + 35),
                             (lb_rect.right - 10, lb_rect.y + 35), 1)

            if self.player.is_batter():
                avg, obp, slg, ops = self._calc_batter_rates(s)
                live_data = [
                    ("G / AB",   f"{s.get('g',0)} / {s.get('ab',0)}"),
                    ("HITS",     f"{s.get('h',0)}"),
                    ("HR / RBI", f"{s.get('hr',0)} / {s.get('rbi',0)}"),
                    ("BB / SO",  f"{s.get('bb',0)} / {s.get('so',0)}"),
                    ("AVG / OBP",f"{avg:.3f} / {obp:.3f}"),
                    ("SLG / OPS",f"{slg:.3f} / {ops:.3f}"),
                    ("SB",       f"{s.get('sb',0)}"),
                ]
            else:
                live_data = [
                    ("W - L",   f"{s.get('w',0)} - {s.get('l',0)}"),
                    ("ERA",     f"{s.get('era',0.0):.2f}"),
                    ("G / IP",  f"{s.get('g',0)} / {s.get('ip',0.0):.1f}"),
                    ("H / BB",  f"{s.get('h_allowed',0)} / {s.get('bb_allowed',0)}"),
                    ("SO",      f"{s.get('so',0)}"),
                    ("WHIP",    f"{s.get('whip', 0.0):.2f}"),
                    ("HLD / SV",f"{s.get('hld',0)} / {s.get('sv',0)}"),
                ]

            for i, (label, val) in enumerate(live_data):
                lbl_surf = self.SMALL_FONT.render(label, True, (100, 100, 100))
                screen.blit(lbl_surf, (lb_rect.x + 20, lb_rect.y + 50 + i * 32))
                val_surf = FONT.render(val, True, black)
                screen.blit(val_surf, (lb_rect.x + 140, lb_rect.y + 48 + i * 32))
        else:
            screen.blit(FONT.render("Season Live Stat", True, (160, 160, 160)),
                        (lb_rect.x + 80, lb_rect.y + 100))

        # ── 우측 하단: Career ──
        rb_rect = pygame.Rect(lb_rect.right + GAP, lt_rect.bottom + GAP,
                              width - LEFT_W - MARGIN * 2 - GAP, BOTTOM_H)
        pygame.draw.rect(screen, (215, 215, 215), rb_rect)
        pygame.draw.rect(screen, (140, 140, 140), rb_rect, 2)

        if self.player.is_batter():
            headers    = ["Year", "Team", "G", "AB", "H", "HR", "RBI", "BB", "SO", "AVG", "OBP", "SLG", "OPS"]
            col_widths = [45, 70, 35, 40, 35, 35, 40, 35, 35, 52, 52, 52, 52]
        else:
            headers    = ["Year", "Team", "W", "L", "ERA", "G", "GS", "IP", "H", "ER", "SO", "WHIP"]
            col_widths = [45, 70, 30, 30, 50, 30, 35, 50, 35, 35, 40, 50]

        col_x = []
        x = rb_rect.x + 10
        for w_col in col_widths:
            col_x.append(x)
            x += w_col

        # 헤더
        for h_label, cx in zip(headers, col_x):
            screen.blit(self.SMALL_FONT.render(h_label, True, (80, 80, 80)), (cx, rb_rect.y + 12))

        # 행
        y_ptr = rb_rect.y + 45
        for c in self.player.career[-9:][::-1]:
            s = c.get("stats", {})
            if self.player.is_batter():
                avg, obp, slg, ops = self._calc_batter_rates(s)
                row = [
                    c.get("season"), c.get("team"),
                    s.get("g"), s.get("ab"), s.get("h"),
                    s.get("hr"), s.get("rbi"), s.get("bb"), s.get("so"),
                    f"{avg:.3f}", f"{obp:.3f}", f"{slg:.3f}", f"{ops:.3f}"
                ]
            else:
                row = [
                    c.get("season"), c.get("team"),
                    s.get("w", 0), s.get("l", 0),
                    f"{s.get('era',0):.2f}",
                    s.get("g", 0), s.get("gs", 0),
                    f"{s.get('ip',0):.1f}",
                    s.get("h_allowed", 0), s.get("er", 0), s.get("so", 0),
                    f"{s.get('whip',0):.2f}"
                ]

            for item, cx in zip(row, col_x):
                screen.blit(self.SMALL_FONT.render(str(item), True, black), (cx, y_ptr))
            y_ptr += 28

        for btn in self.buttons:
            btn.draw(screen)

    def go_contract(self):
        return ("contract", ContractScene(self.player, self.state))

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update_hover(mouse_pos)
        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 1:
                    for btn in self.buttons:
                        res = btn.handle_event(e)
                        if res: return res
        return None