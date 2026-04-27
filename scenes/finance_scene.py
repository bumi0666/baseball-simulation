import pygame
from scenes.base_scene import Scene
from ui.button import Button
from config import *
from ui.layout import get_common_buttons, draw_common_ui


class FinanceScene(Scene):
    def __init__(self, state, players):
        self.state = state
        self.players = players
        self.buttons = get_common_buttons(self)

        self.TITLE_FONT = pygame.font.SysFont(None, 48)
        self.MONEY_FONT = pygame.font.SysFont(None, 65)
        self.LABEL_FONT = pygame.font.SysFont(None, 28)
        self.SMALL_FONT = pygame.font.SysFont(None, 20)

    def draw_area_chart(self, screen, x, y, w, h, data, color, title):
        left_margin = 70
        chart_x = x + left_margin
        chart_w = w - left_margin

        display_data = data[-12:]
        num_points = len(display_data)

        if "INCOME" in title or "EXPENDITURE" in title:
            current_val = sum(data)
        elif "PROFIT" in title:
            current_val = sum(self.state.monthly_income.values()) - \
                      sum(self.state.monthly_expense.values())
        else:
            current_val = display_data[-1] if display_data else 0

        def format_m(val):
            if abs(val) >= 1_000_000:
                return f"${val/1_000_000:.2f}M"
            elif abs(val) >= 1_000:
                return f"${val/1_000:.1f}k"
            return f"${val:,}"

        def format_axis(val):
            if abs(val) >= 1_000_000:
                return f"${val/1_000_000:.1f}M"
            elif abs(val) >= 1_000:
                return f"${val/1_000:.0f}k"
            return f"${val:,}"

        title_surf = self.SMALL_FONT.render(title, True, (200, 200, 200))
        screen.blit(title_surf, (chart_x, y - 22))

        val_color = (255, 255, 255)
        if "PROFIT" in title:
            val_color = (100, 255, 100) if current_val >= 0 else (255, 100, 100)

        val_surf = self.LABEL_FONT.render(format_m(current_val), True, val_color)
        screen.blit(val_surf,
                (chart_x + chart_w - val_surf.get_width(), y - 28))

        pygame.draw.rect(screen, (30, 30, 30), (chart_x, y, chart_w, h))

        if num_points <= 1:
            return

        actual_max = max(display_data)
        actual_min = min(display_data)
        max_v = max(abs(actual_max), abs(actual_min))

        if max_v > 0:
            zero_line = y + h / 2
            pygame.draw.line(screen, (80, 80, 80),
                         (chart_x, zero_line),
                         (chart_x + chart_w, zero_line), 1)

            top_label = self.SMALL_FONT.render(format_axis(max_v), True, (120,120,120))
            screen.blit(top_label, (chart_x - 60, y - 5))

            zero_label = self.SMALL_FONT.render("$0", True, (120,120,120))
            screen.blit(zero_label, (chart_x - 40, zero_line - 8))

            bottom_label = self.SMALL_FONT.render(format_axis(-max_v), True, (120,120,120))
            screen.blit(bottom_label, (chart_x - 60, y + h - 15))

        points = []
        for i, v in enumerate(display_data):
            px = chart_x + (i * (chart_w / max(1, num_points - 1)))

            if max_v > 0:
                zero_line = y + h / 2
                py = zero_line - (v / max_v) * (h / 2 * 0.8)
            else:
                py = y + h / 2

            points.append((px, py))

        if len(points) >= 2:
            zero_line = y + h / 2 if max_v > 0 else y + h
            fill_pts = [(points[0][0], zero_line)] + points + \
                   [(points[-1][0], zero_line)]

            pygame.draw.polygon(
            screen,
            (color[0]//5, color[1]//5, color[2]//5),
            fill_pts
            )
            pygame.draw.lines(screen, color, False, points, 2)

    # ------------------------------
    # 메인 draw
    # ------------------------------
    def draw(self, screen):
        screen.fill((20, 20, 20))
        draw_common_ui(screen, self.state, FONT)

        cx = 210
        chart_w = 780
        half_w = (chart_w - 20) // 2
        info_x = cx + chart_w + 30
        info_w = 240
        base_y = 60

        h_main = 130
        h_sub = 100

        # TOTAL BALANCE
        self.draw_area_chart(
            screen, cx, base_y,
            chart_w, h_main,
            self.state.finance_history,
            (230, 80, 120),
            "TOTAL BALANCE"
        )

        # PROFIT/LOSS (실시간 계산 반영)
        self.draw_area_chart(
            screen, cx, base_y + 190,
            chart_w, h_main,
            self.state.profit_history,
            (150, 80, 200),
            "MONTHLY PROFIT/LOSS"
        )

        # MONTHLY INCOME
        income_values = list(self.state.monthly_income.values())
        self.draw_area_chart(
            screen,
            cx,
            base_y + 380,
            chart_w // 2 - 10,
            h_sub,
            income_values,
            (140, 140, 140),
            "MONTHLY INCOME"
        )

        # MONTHLY EXPENDITURE
        expense_values = list(self.state.monthly_expense.values())
        self.draw_area_chart(
            screen,
            cx + chart_w // 2 + 10,
            base_y + 380,
            chart_w // 2 - 10,
            h_sub,
            expense_values,
            (80, 150, 80),
            "MONTHLY EXPENDITURE"
        )

        # 오른쪽 예산 박스
        box_rect = (info_x, base_y - 10, info_w, 250)
        pygame.draw.rect(screen, (35, 40, 50),
                         box_rect, border_radius=10)
        pygame.draw.rect(screen, (60, 70, 90),
                         box_rect, 2, border_radius=10)

        y_ptr = base_y + 10
        screen.blit(self.LABEL_FONT.render(
            "BUDGET", True, (0, 255, 255)),
            (info_x + 20, y_ptr))

        self.state.current_wage = sum(p.salary()
                                      for p in self.players)

        y_ptr += 50

        budget_items = [
            ("Transfer", self.state.transfer_budget),
            ("Wage Cap", self.state.wage_budget),
            ("Current Wage", self.state.current_wage)
        ]

        for label, val in budget_items:
            if abs(val) >= 1_000_000:
                v_str = f"${val/1_000_000:.2f}M"
            else:
                v_str = f"${val/1_000:.1f}k"

            screen.blit(self.SMALL_FONT.render(
                label, True, (150, 150, 150)),
                (info_x + 20, y_ptr))

            screen.blit(self.LABEL_FONT.render(
                v_str, True, (255, 255, 255)),
                (info_x + 20, y_ptr + 22))

            y_ptr += 65
            self.draw_detail_texts(screen, cx, info_x, half_w, base_y)

        for btn in self.buttons:
            btn.draw(screen)

    def draw_detail_texts(self, screen, cx, info_x, half_w, base_y):
        def format_m(val):
            if val >= 1_000_000:
                return f"${val/1_000_000:.2f}M"
            elif val >= 1_000:
                return f"${val/1_000:.1f}k"
            return f"${val:,}"

        y_ptr = base_y + 560 + 20 - 40

        # 수입 내역
        for k, v in self.state.monthly_income.items():
            screen.blit(self.SMALL_FONT.render(f"{k}:", True, (180,180,180)), (cx + 70, y_ptr))
            screen.blit(self.SMALL_FONT.render(format_m(v), True, white), (cx + 220, y_ptr))
            y_ptr += 25

        # 지출 내역
        y_ptr = base_y + 560 + 20 - 40
        for k, v in self.state.monthly_expense.items():
            screen.blit(self.SMALL_FONT.render(f"{k}:", True, (180,180,180)), (cx + half_w + 90, y_ptr))
            screen.blit(self.SMALL_FONT.render(format_m(v), True, white), (cx + half_w + 240, y_ptr))
            y_ptr += 25
    