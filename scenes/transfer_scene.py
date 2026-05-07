from scenes.base_scene import Scene
from ui.button import Button
from config import *
from ui.layout import get_common_buttons, draw_common_ui
import pygame


class TransferScene(Scene):
    def __init__(self, state):
        self.state = state
        self.buttons = get_common_buttons(self)

        self.smallFONT = pygame.font.SysFont(None, 23)
        self.headerFONT = pygame.font.SysFont(None, 24)
        self.titleFONT = pygame.font.SysFont(None, 38)

        self.active_tab = "players"
        self.filter_pos = "ALL"
        self.filter_role = "ALL"
        self.selected_player = None
        self.selected_staff = None
        self.scroll_offset = 0

        self.top_area_h = 90
        self.filter_w = 120
        self.row_height = 34
        self.visible_count = 13

        self.list_x = CONTENT_X + self.filter_w + 24
        self.list_y = CONTENT_Y + self.top_area_h
        self.list_w = width - self.list_x - 50
        self.list_h = self.visible_count * self.row_height
        self.filter_x = CONTENT_X
        self.filter_y = self.list_y

        self.tab_buttons = [
            Button((CONTENT_X + 330, CONTENT_Y - 34, 100, 28), "Players", lambda: self.set_tab("players"), self.smallFONT),
            Button((CONTENT_X + 440, CONTENT_Y - 34, 100, 28), "Staff", lambda: self.set_tab("staff"), self.smallFONT),
        ]

        self.position_buttons = []
        for i, pos in enumerate(["ALL", "P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]):
            self.position_buttons.append(
                Button((self.filter_x, self.filter_y + i * 38, 92, 32), pos, lambda p=pos: self.set_pos_filter(p), self.smallFONT)
            )

        self.role_buttons = []
        for i, role in enumerate(["ALL", "HD", "HC", "PC", "DC", "SC", "DR"]):
            self.role_buttons.append(
                Button((self.filter_x, self.filter_y + i * 38, 92, 32), role, lambda r=role: self.set_role_filter(r), self.smallFONT)
            )

    def set_tab(self, tab):
        self.active_tab = tab
        self.scroll_offset = 0
        self.selected_player = None
        self.selected_staff = None

    def set_pos_filter(self, pos):
        self.filter_pos = pos
        self.scroll_offset = 0

    def set_role_filter(self, role):
        self.filter_role = role
        self.scroll_offset = 0

    def get_fa_players(self):
        fa_players = self.state.team_rosters.get("FA", [])
        if self.filter_pos == "ALL":
            return fa_players
        return [p for p in fa_players if p.pos == self.filter_pos]

    def get_fa_staff(self):
        staff_pool = getattr(self.state, "all_staff", [])
        fa_staff = [
            s for s in staff_pool
            if s.team == "FA" or s.status.get("roster") == "fa"
        ]
        if self.filter_role == "ALL":
            return fa_staff
        return [s for s in fa_staff if s.role == self.filter_role]

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

    def _market_value(self, player):
        return self._format_money(player.data.get("market_value", 0))

    def _demand_salary(self, player):
        value = player.data.get("market_value", 0)
        return self._format_money(max(player.salary(), int(value * 0.12)))

    def _staff_value(self, staff):
        return self._format_money(getattr(staff, "market_value", 0))

    def _demand_staff_salary(self, staff):
        salary = staff.salary() if hasattr(staff, "salary") else 0
        if salary <= 0:
            salary = int(getattr(staff, "market_value", 0) * 0.15)
        return self._format_money(salary)

    def _latest_stats(self, player):
        if not player.career:
            return {}
        return player.career[-1].get("stats", {})

    def _key_stat(self, player):
        stats = self._latest_stats(player)
        if not stats:
            return "-"

        if player.is_batter():
            return f"OPS {stats.get('ops', 0.0):.3f} HR {stats.get('hr', 0)}"

        return f"ERA {stats.get('era', 0.0):.2f} WHIP {stats.get('whip', 0.0):.2f}"

    def draw_top_area(self, screen):
        top_rect = pygame.Rect(CONTENT_X, CONTENT_Y - 45, width - CONTENT_X - 40, self.top_area_h - 15)
        pygame.draw.rect(screen, (32, 34, 42), top_rect)
        pygame.draw.rect(screen, (80, 85, 96), top_rect, 1)

        screen.blit(self.titleFONT.render("TRANSFER MARKET", True, white), (top_rect.x + 18, top_rect.y + 16))

        for btn in self.tab_buttons:
            if (btn.text == "Players" and self.active_tab == "players") or (btn.text == "Staff" and self.active_tab == "staff"):
                pygame.draw.rect(screen, (60, 90, 140), btn.rect)
            btn.draw(screen)

        money = self._format_money(getattr(self.state, "money", 0))
        transfer_budget = self._format_money(getattr(self.state, "transfer_budget", 0))
        wage_budget = self._format_money(getattr(self.state, "wage_budget", 0))
        current_wage = self._format_money(getattr(self.state, "current_wage", 0))

        info = f"Cash {money}    Transfer Budget {transfer_budget}    Wage Budget {wage_budget}    Current Wage {current_wage}"
        screen.blit(self.smallFONT.render(info, True, (220, 220, 220)), (top_rect.x + 18, top_rect.y + 52))

    def draw_filters(self, screen):
        title = "POSITION" if self.active_tab == "players" else "ROLE"
        active_value = self.filter_pos if self.active_tab == "players" else self.filter_role
        filter_buttons = self.position_buttons if self.active_tab == "players" else self.role_buttons

        label = self.headerFONT.render(title, True, white)
        screen.blit(label, (self.filter_x, self.filter_y - 30))

        for btn in filter_buttons:
            if btn.text == active_value:
                pygame.draw.rect(screen, (60, 90, 140), btn.rect)
            btn.draw(screen)

    def draw_table(self, screen):
        if self.active_tab == "staff":
            self.draw_staff_table(screen)
            return

        filtered = self.get_fa_players()
        start = self.scroll_offset
        end = min(start + self.visible_count, len(filtered))

        header_y = self.list_y - 30
        columns = [
            ("Name", 8),
            ("Pos", 138),
            ("Age", 188),
            ("OVR", 238),
            ("Demand", 292),
            ("Value", 382),
            ("HP/Con", 472),
            ("Key Stat", 560),
        ]

        for label, offset in columns:
            screen.blit(self.headerFONT.render(label, True, white), (self.list_x + offset, header_y + 4))

        y = self.list_y
        for i in range(start, end):
            player = filtered[i]
            rect = pygame.Rect(self.list_x, y, self.list_w, self.row_height)

            if player == self.selected_player:
                bg_color = (180, 200, 255)
            elif i % 2 == 0:
                bg_color = (250, 250, 250)
            else:
                bg_color = (232, 232, 232)
            pygame.draw.rect(screen, bg_color, rect)

            health = int(player.status.get("health", 0) / 10)
            condition = player.status.get("condition", 0)
            row_data = [
                (self._short_text(player.name, 12), 8),
                (player.pos, 138),
                (str(player.age()), 188),
                (str(player.calculate_ovr()), 238),
                (self._demand_salary(player), 292),
                (self._market_value(player), 382),
                (f"{health}%/{condition}%", 472),
                (self._key_stat(player), 560),
            ]

            for value, offset in row_data:
                screen.blit(self.smallFONT.render(value, True, black), (rect.x + offset, rect.y + 8))

            y += self.row_height

        track_x = self.list_x + self.list_w + 10
        pygame.draw.rect(screen, (200, 200, 200), (track_x, self.list_y, SCROLLBAR_W, self.list_h))
        if len(filtered) > self.visible_count:
            ratio = self.visible_count / len(filtered)
            handle_h = int(self.list_h * ratio)
            max_off = len(filtered) - self.visible_count
            handle_y = self.list_y + int((self.list_h - handle_h) * (self.scroll_offset / max_off))
            pygame.draw.rect(screen, (120, 120, 120), (track_x, handle_y, SCROLLBAR_W, handle_h))

    def draw_staff_table(self, screen):
        filtered = self.get_fa_staff()
        start = self.scroll_offset
        end = min(start + self.visible_count, len(filtered))

        header_y = self.list_y - 30
        columns = [
            ("Name", 8),
            ("Role", 132),
            ("Type", 184),
            ("Stars", 330),
            ("Demand", 410),
            ("Value", 500),
            ("Effect", 590),
        ]

        for label, offset in columns:
            screen.blit(self.headerFONT.render(label, True, white), (self.list_x + offset, header_y + 4))

        y = self.list_y
        for i in range(start, end):
            staff = filtered[i]
            rect = pygame.Rect(self.list_x, y, self.list_w, self.row_height)

            if staff == self.selected_staff:
                bg_color = (180, 200, 255)
            elif i % 2 == 0:
                bg_color = (250, 250, 250)
            else:
                bg_color = (232, 232, 232)
            pygame.draw.rect(screen, bg_color, rect)

            row_data = [
                (self._short_text(staff.name, 12), 8),
                (staff.role, 132),
                (self._short_text(getattr(staff, "title", "-"), 15), 184),
                (staff.get_star_text(), 330),
                (self._demand_staff_salary(staff), 410),
                (self._staff_value(staff), 500),
                (self._short_text(staff.effect_desc, 30), 590),
            ]

            for value, offset in row_data:
                screen.blit(self.smallFONT.render(value, True, black), (rect.x + offset, rect.y + 8))

            y += self.row_height

        track_x = self.list_x + self.list_w + 10
        pygame.draw.rect(screen, (200, 200, 200), (track_x, self.list_y, SCROLLBAR_W, self.list_h))
        if len(filtered) > self.visible_count:
            ratio = self.visible_count / len(filtered)
            handle_h = int(self.list_h * ratio)
            max_off = len(filtered) - self.visible_count
            handle_y = self.list_y + int((self.list_h - handle_h) * (self.scroll_offset / max_off))
            pygame.draw.rect(screen, (120, 120, 120), (track_x, handle_y, SCROLLBAR_W, handle_h))

    def draw(self, screen):
        screen.fill((20, 20, 20))
        draw_common_ui(screen, self.state, FONT)
        self.draw_top_area(screen)
        self.draw_filters(screen)
        self.draw_table(screen)

        for btn in self.buttons:
            btn.draw(screen)

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        filtered = self.get_fa_staff() if self.active_tab == "staff" else self.get_fa_players()
        filter_buttons = self.role_buttons if self.active_tab == "staff" else self.position_buttons

        for btn in self.buttons + self.tab_buttons + filter_buttons:
            btn.update_hover(mouse_pos)

        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 4:
                    self.scroll_offset = max(0, self.scroll_offset - 1)
                elif e.button == 5:
                    max_offset = max(0, len(filtered) - self.visible_count)
                    self.scroll_offset = min(max_offset, self.scroll_offset + 1)

                if e.button == 1:
                    for btn in self.tab_buttons:
                        result = btn.handle_event(e)
                        if result is not None:
                            return result

                    for btn in filter_buttons:
                        result = btn.handle_event(e)
                        if result is not None:
                            return result

                    for i in range(min(self.visible_count, len(filtered) - self.scroll_offset)):
                        idx = self.scroll_offset + i
                        rect = pygame.Rect(self.list_x, self.list_y + i * self.row_height, self.list_w, self.row_height)
                        if rect.collidepoint(e.pos):
                            if self.active_tab == "staff":
                                self.selected_staff = filtered[idx]
                                return ("staff_detail", filtered[idx])
                            self.selected_player = filtered[idx]
                            return ("player_detail", filtered[idx])

                    for btn in self.buttons:
                        result = btn.handle_event(e)
                        if result:
                            return result

        return None
