from cmath import rect
from email.mime import text

from models import player
from scenes.base_scene import Scene
from ui.button import Button
from config import *
from ui.layout import get_common_buttons, draw_common_ui
import pygame

class TeamScene(Scene):
    def __init__(self, players, state, team_name):
        self.players = players
        self.state = state
        self.team_name = team_name

        self.is_user_team = (self.team_name == self.state.user_team)
        
        self.smallFONT = pygame.font.SysFont(None, 24)
        self.headerFONT = pygame.font.SysFont(None, 25)
        
        self.buttons = get_common_buttons(self)
        
        filter_y = CONTENT_Y - 80 
        self.buttons.extend([
            Button((CONTENT_X, filter_y, 120, 40), "ALL", self.show_all),
            Button((CONTENT_X + 130, filter_y, 120, 40), "BATTERS", self.show_batters),
            Button((CONTENT_X + 260, filter_y, 120, 40), "PITCHERS", self.show_pitchers)
        ])
        
        self.selected_player = None
        self.scroll_offset = 0
        self.visible_count = VISIBLE_ROWS
        self.row_height = ROW_H
        self.scroll_area_top = CONTENT_Y
        self.scroll_area_height = self.visible_count * self.row_height
        self.filter_mode = "ALL"

        self._arrow_rects = []  # [(rect, player), ...]
        
    def show_all(self):
        self.filter_mode = "ALL"
        self.scroll_offset = 0

    def show_batters(self):
        self.filter_mode = "BATTER"
        self.scroll_offset = 0

    def show_pitchers(self):
        self.filter_mode = "PITCHER"
        self.scroll_offset = 0
        
    def get_filtered_players(self):
        # 1군(active) 선수만 표시
        pool = [p for p in self.players if p.status.get("roster", "active") == "active"]
        if self.filter_mode == "BATTER":
            return [p for p in pool if p.pos != "P"]
        elif self.filter_mode == "PITCHER":
            return [p for p in pool if p.pos == "P"]
        return pool

    def back(self):
        return "hub"
    
    def _short_text(self, text, max_len):
        text = str(text)
        return text if len(text) <= max_len else text[:max_len - 1] + "."

    def _format_money(self, value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return "-"

        if abs(value) >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        if abs(value) >= 1_000:
            return f"${value / 1_000:.0f}k"
        return f"${value}"

    def _contract_end(self, player):
        end = player.contract_end()
        if not end:
            return "FA"
        return str(end)[:4]

    def _latest_stats(self, player):
        if not player.career:
            return {}
        return player.career[-1].get("stats", {})

    def _calc_batter_rates(self, stats):
        ab = stats.get("ab", 0)
        h = stats.get("h", 0)
        bb = stats.get("bb", 0)
        hr = stats.get("hr", 0)
        doubles = stats.get("2b", 0)
        triples = stats.get("3b", 0)

        singles = max(0, h - doubles - triples - hr)
        pa = ab + bb
        tb = singles + 2 * doubles + 3 * triples + 4 * hr

        obp = (h + bb) / pa if pa > 0 else 0.0
        slg = tb / ab if ab > 0 else 0.0

        return obp + slg

    def _key_stat(self, player):
        stats = self._latest_stats(player)
        if not stats:
            return "-"

        if player.is_batter():
            ops = self._calc_batter_rates(stats)
            return f"OPS {ops:.3f} HR {stats.get('hr', 0)}"

        return f"ERA {stats.get('era', 0.0):.2f} WHIP {stats.get('whip', 0.0):.2f}"

    def _draw_down_triangle(self, screen, cx, cy):
        """▼ 삼각형 (2군 내리기)"""
        size = 9
        pts = [(cx, cy + size), (cx - size, cy - size), (cx + size, cy - size)]
        pygame.draw.polygon(screen, (200, 80, 80), pts)
    
    def draw(self, screen):
        screen.fill((20, 20, 20))
        draw_common_ui(screen, self.state, FONT)
        
        filtered = self.get_filtered_players()
        start = self.scroll_offset
        end = min(start + self.visible_count, len(filtered))

        # 헤더
        header_y = CONTENT_Y - 35
        columns = [
        ("#", CONTENT_X + 8),
            ("Name", CONTENT_X + 48),
            ("Pos", CONTENT_X + 178),
            ("Age", CONTENT_X + 228),
            ("OVR", CONTENT_X + 278),
            ("Salary", CONTENT_X + 328),
            ("End", CONTENT_X + 408),
            ("HP/Con", CONTENT_X + 462),
            ("Fat", CONTENT_X + 558),
            ("Key Stat", CONTENT_X + 620),
        ]

        for label, x in columns:
            screen.blit(self.headerFONT.render(label, True, white), (x, header_y + 5))

        self._arrow_rects = []

        y = CONTENT_Y
        for i in range(start, end):
            p = filtered[i]
            rect = pygame.Rect(CONTENT_X, y, CONTENT_W, self.row_height)

            if p == self.selected_player:
                bg_color = (180, 200, 255)
            elif i % 2 == 0:
                bg_color = (255, 255, 255)
            else:
                bg_color = (235, 235, 235)
            pygame.draw.rect(screen, bg_color, rect)

            fatigue_str = ("HIGH" if p.status["fatigue"] >= 200
                           else "MID" if p.status["fatigue"] >= 100
                           else "LOW")

            ovr = p.calculate_ovr()
            salary = self._format_money(p.salary())
            contract_end = self._contract_end(p)
            key_stat = self._key_stat(p)

            screen.blit(self.smallFONT.render(str(p.backnumber), True, black), (rect.x + 8, rect.y + 11))
            screen.blit(self.smallFONT.render(self._short_text(p.name, 12), True, black), (rect.x + 48, rect.y + 11))
            screen.blit(self.smallFONT.render(p.pos, True, black), (rect.x + 178, rect.y + 11))
            screen.blit(self.smallFONT.render(str(p.age()), True, black), (rect.x + 228, rect.y + 11))
            screen.blit(self.smallFONT.render(str(ovr), True, black), (rect.x + 278, rect.y + 11))
            screen.blit(self.smallFONT.render(salary, True, black), (rect.x + 328, rect.y + 11))
            screen.blit(self.smallFONT.render(contract_end, True, black), (rect.x + 408, rect.y + 11))
            screen.blit(self.smallFONT.render(
                f"{int(p.status['health'] / 10)}%/{p.status['condition']}%", True, black), (rect.x + 462, rect.y + 11))
            screen.blit(self.smallFONT.render(fatigue_str, True, black), (rect.x + 558, rect.y + 11))
            screen.blit(self.smallFONT.render(key_stat, True, black), (rect.x + 620, rect.y + 11))


            # ▼ 삼각형 버튼 (내 팀일 때만)
            if self.is_user_team:
                arrow_cx = rect.right - 25
                arrow_cy = rect.centery
                self._draw_down_triangle(screen, arrow_cx, arrow_cy)
                arrow_rect = pygame.Rect(arrow_cx - 15, arrow_cy - 15, 30, 30)
                self._arrow_rects.append((arrow_rect, p))

            y += self.row_height
            
        # 스크롤바
        track_x = CONTENT_X + CONTENT_W + 10
        pygame.draw.rect(screen, (200, 200, 200), (track_x, self.scroll_area_top, SCROLLBAR_W, self.scroll_area_height))
        if len(filtered) > self.visible_count:
            ratio    = self.visible_count / len(filtered)
            handle_h = int(self.scroll_area_height * ratio)
            max_off  = len(filtered) - self.visible_count
            handle_y = self.scroll_area_top + int((self.scroll_area_height - handle_h) * (self.scroll_offset / max_off))
            pygame.draw.rect(screen, (120, 120, 120), (track_x, handle_y, SCROLLBAR_W, handle_h))
            
        for btn in self.buttons:
            btn.draw(screen)

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        filtered = self.get_filtered_players()
        for btn in self.buttons:
            btn.update_hover(mouse_pos)

        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 4:
                    self.scroll_offset = max(0, self.scroll_offset - 1)
                elif e.button == 5:
                    self.scroll_offset = min(max(0, len(filtered) - self.visible_count), self.scroll_offset + 1)
                
                if e.button == 1:
                    # ▼ 삼각형 클릭 체크 (선수 행 클릭보다 먼저)
                    for arrow_rect, player in self._arrow_rects:
                        if arrow_rect.collidepoint(e.pos):
                            player.status["roster"] = "inactive"
                            #print(f"{player.name} roster: {player.status['roster']}")
                            self.scroll_offset = max(
                                0, min(self.scroll_offset,
                                       len(self.get_filtered_players()) - self.visible_count))
                            return None

                    # 선수 행 클릭 → 상세 페이지
                    for i in range(min(self.visible_count, len(filtered) - self.scroll_offset)):
                        idx  = self.scroll_offset + i
                        rect = pygame.Rect(CONTENT_X, CONTENT_Y + i * self.row_height, CONTENT_W, self.row_height)
                        if rect.collidepoint(e.pos):
                            self.selected_player = filtered[idx]
                            return ("player_detail", filtered[idx])

                    for btn in self.buttons:
                        result = btn.handle_event(e)
                        if result:
                            return result
        return None