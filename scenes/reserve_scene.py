from scenes.base_scene import Scene
from ui.button import Button
from config import *
from ui.layout import get_common_buttons, draw_common_ui
import pygame

class ReserveScene(Scene):
    def __init__(self, players, state):
        self.players = players
        self.state = state

        self.smallFONT = pygame.font.SysFont(None, 30)

        self.buttons = get_common_buttons(self)

        filter_y = CONTENT_Y - 80
        self.buttons.extend([
            Button((CONTENT_X,       filter_y, 120, 40), "ALL",      self.show_all),
            Button((CONTENT_X + 130, filter_y, 120, 40), "BATTERS",  self.show_batters),
            Button((CONTENT_X + 260, filter_y, 120, 40), "PITCHERS", self.show_pitchers),
        ])

        self.selected_player = None
        self.scroll_offset   = 0
        self.visible_count   = VISIBLE_ROWS
        self.row_height      = ROW_H
        self.scroll_area_top    = CONTENT_Y
        self.scroll_area_height = self.visible_count * self.row_height
        self.filter_mode = "ALL"

        self._arrow_rects = []

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
        # 2군(inactive) 선수만
        pool = [p for p in self.players if p.status.get("roster", "active") == "inactive"]
        if self.filter_mode == "BATTER":
            return [p for p in pool if p.pos != "P"]
        elif self.filter_mode == "PITCHER":
            return [p for p in pool if p.pos == "P"]
        return pool

    def _draw_up_triangle(self, screen, cx, cy):
        """▲ 삼각형 (1군 올리기)"""
        size = 9
        pts = [(cx, cy - size), (cx - size, cy + size), (cx + size, cy + size)]
        pygame.draw.polygon(screen, (80, 200, 120), pts)

    def draw(self, screen):
        screen.fill((20, 20, 20))
        draw_common_ui(screen, self.state, FONT)

        filtered = self.get_filtered_players()
        start = self.scroll_offset
        end   = min(start + self.visible_count, len(filtered))

        # 타이틀
        total_inactive = len([p for p in self.players if p.status.get("roster", "active") == "inactive"])
        screen.blit(FONT.render("Reserve", True, (255, 180, 80)), (CONTENT_X, CONTENT_Y - 110))
        screen.blit(FONT.render(f"({total_inactive} players)", True, (150, 150, 150)), (CONTENT_X + 180, CONTENT_Y - 110))

        # 헤더
        header_y = CONTENT_Y - 35
        screen.blit(FONT.render("Num",     True, white), (CONTENT_X,       header_y))
        screen.blit(FONT.render("Name",    True, white), (CONTENT_X + 60,  header_y))
        screen.blit(FONT.render("Pos",     True, white), (CONTENT_X + 220, header_y))
        screen.blit(FONT.render("Age",     True, white), (CONTENT_X + 320, header_y))
        screen.blit(FONT.render("Hp/Con",  True, white), (CONTENT_X + 400, header_y))
        screen.blit(FONT.render("Fatigue", True, white), (CONTENT_X + 520, header_y))

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

            screen.blit(self.smallFONT.render(str(p.backnumber), True, black), (rect.x + 10,  rect.y + 8))
            screen.blit(self.smallFONT.render(p.name,            True, black), (rect.x + 50,  rect.y + 8))
            screen.blit(self.smallFONT.render(p.pos,             True, black), (rect.x + 230, rect.y + 8))
            screen.blit(self.smallFONT.render(str(p.age()),      True, black), (rect.x + 330, rect.y + 8))
            screen.blit(self.smallFONT.render(
                f"{int(p.status['health']/10)}%/{p.status['condition']}%", True, black), (rect.x + 390, rect.y + 8))
            screen.blit(self.smallFONT.render(fatigue_str,       True, black), (rect.x + 540, rect.y + 8))

            # ▲ 삼각형 버튼
            arrow_cx = rect.right - 25
            arrow_cy = rect.centery
            self._draw_up_triangle(screen, arrow_cx, arrow_cy)
            arrow_rect = pygame.Rect(arrow_cx - 15, arrow_cy - 15, 30, 30)
            self._arrow_rects.append((arrow_rect, p))

            y += self.row_height

        # 2군 선수가 없을 때
        if not filtered:
            msg = FONT.render("No reserve players.", True, (100, 100, 100))
            screen.blit(msg, (CONTENT_X, CONTENT_Y + 80))

        # 스크롤바
        track_x = CONTENT_X + CONTENT_W + 10
        pygame.draw.rect(screen, (200, 200, 200),
                         (track_x, self.scroll_area_top, SCROLLBAR_W, self.scroll_area_height))
        if len(filtered) > self.visible_count:
            ratio    = self.visible_count / len(filtered)
            handle_h = int(self.scroll_area_height * ratio)
            max_off  = len(filtered) - self.visible_count
            handle_y = self.scroll_area_top + int(
                (self.scroll_area_height - handle_h) * (self.scroll_offset / max_off))
            pygame.draw.rect(screen, (120, 120, 120), (track_x, handle_y, SCROLLBAR_W, handle_h))

        for btn in self.buttons:
            btn.draw(screen)

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        filtered  = self.get_filtered_players()

        for btn in self.buttons:
            btn.update_hover(mouse_pos)

        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 4:
                    self.scroll_offset = max(0, self.scroll_offset - 1)
                elif e.button == 5:
                    self.scroll_offset = min(
                        max(0, len(filtered) - self.visible_count),
                        self.scroll_offset + 1)

                if e.button == 1:
                    # ▲ 삼각형 클릭 → 1군 복귀
                    for arrow_rect, player in self._arrow_rects:
                        if arrow_rect.collidepoint(e.pos):
                            player.status["roster"] = "active"
                            self.scroll_offset = max(
                                0, min(self.scroll_offset,
                                       len(self.get_filtered_players()) - self.visible_count))
                            return None

                    # 선수 행 클릭 → 상세 페이지
                    for i in range(min(self.visible_count, len(filtered) - self.scroll_offset)):
                        idx  = self.scroll_offset + i
                        rect = pygame.Rect(CONTENT_X, CONTENT_Y + i * self.row_height,
                                           CONTENT_W, self.row_height)
                        if rect.collidepoint(e.pos):
                            self.selected_player = filtered[idx]
                            return ("player_detail", filtered[idx])

                    for btn in self.buttons:
                        result = btn.handle_event(e)
                        if result:
                            return result
        return None