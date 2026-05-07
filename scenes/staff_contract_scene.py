from datetime import date, timedelta

import pygame

from config import *
from scenes.base_scene import Scene
from ui.button import Button


MOOD_LEVELS = [
    (-999, "FURIOUS", (220, 60, 60)),
    (-0.20, "UNHAPPY", (220, 130, 50)),
    (-0.08, "NEUTRAL", (160, 160, 160)),
    (0.00, "INTERESTED", (100, 190, 100)),
    (0.08, "HAPPY", (60, 210, 130)),
    (0.20, "THRILLED", (50, 220, 255)),
]


ROLE_LABELS = {
    "HD": "Head Coach",
    "HC": "Hitting Coach",
    "PC": "Pitching Coach",
    "DC": "Defense Coach",
    "SC": "Scout",
    "DR": "Doctor",
}


def fmt_money(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return "-"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}k"
    return f"${value:,}"


def trait_label(key):
    return str(key).replace("_", " ").title()


def expected_staff_salary(staff):
    current_salary = staff.salary() if hasattr(staff, "salary") else 0
    market_value = getattr(staff, "market_value", 0)
    base = max(current_salary, int(market_value * 0.15))

    stars = max(1, getattr(staff, "stars", 1))
    star_mult = 0.75 + stars * 0.12
    expected = int(base * star_mult)

    if staff.is_free_agent():
        expected = int(expected * 1.10)

    return max(5000, expected)


def get_mood(effective_offer, expected):
    ratio = (effective_offer - expected) / expected if expected > 0 else 0
    result = MOOD_LEVELS[0]
    for threshold, name, color in MOOD_LEVELS:
        if ratio >= threshold:
            result = (threshold, name, color)
    return result


class StaffContractScene(Scene):
    def __init__(self, staff, state):
        self.staff = staff
        self.state = state

        self.FONT = pygame.font.SysFont(None, 28)
        self.SMALL = pygame.font.SysFont(None, 22)
        self.TINY = pygame.font.SysFont(None, 18)

        self.offer_salary = max(staff.salary(), expected_staff_salary(staff))
        self.offer_bonus = 0
        self.salary_step = 5000
        self.bonus_step = 5000
        self.offer_result = None

        self.left = pygame.Rect(30, 120, 310, 540)
        self.mid = pygame.Rect(355, 120, 380, 540)
        self.right = pygame.Rect(750, 120, 500, 540)

        self.buttons = [
            Button((width - 160, height - 60, 120, 45), "BACK", self.back),
        ]
        bx = self.mid.x + 280
        self.buttons.append(Button((bx, self.mid.y + 155, 36, 30), "+", self.increase_salary))
        self.buttons.append(Button((bx + 40, self.mid.y + 155, 36, 30), "-", self.decrease_salary))
        self.buttons.append(Button((bx, self.mid.y + 215, 36, 30), "+", self.increase_bonus))
        self.buttons.append(Button((bx + 40, self.mid.y + 215, 36, 30), "-", self.decrease_bonus))

        self.offer_button = Button(
            (self.mid.x + 20, self.mid.y + 490, 200, 45),
            "MAKE OFFER",
            self.make_offer,
        )
        self.buttons.append(self.offer_button)

    def back(self):
        return ("staff_detail_refresh", self.staff)

    def get_game_date(self):
        y, m, d = self.state.base_date
        return date(y, m, d) + timedelta(days=self.state.current_day - 1)

    def get_total_wage(self):
        return sum(p.salary() for p in self.state.team_rosters.get(self.state.user_team, []))

    def get_available_salary(self):
        return max(0, getattr(self.state, "wage_budget", 0) - self.get_total_wage())

    def increase_salary(self):
        if self.offer_salary + self.salary_step <= self.get_available_salary():
            self.offer_salary += self.salary_step

    def decrease_salary(self):
        if self.offer_salary - self.salary_step >= 0:
            self.offer_salary -= self.salary_step

    def increase_bonus(self):
        if self.offer_bonus + self.bonus_step <= getattr(self.state, "transfer_budget", 0):
            self.offer_bonus += self.bonus_step

    def decrease_bonus(self):
        if self.offer_bonus - self.bonus_step >= 0:
            self.offer_bonus -= self.bonus_step

    def effective_offer(self):
        bonus_value = self.offer_bonus if self.staff.is_free_agent() else 0
        return self.offer_salary + bonus_value

    def make_offer(self):
        expected = expected_staff_salary(self.staff)
        if self.effective_offer() >= expected:
            self.offer_result = "accept"
            self.offer_button.text = "CONFIRM"
            self.offer_button.action = self.confirm_contract
        else:
            self.offer_result = "reject"

    def confirm_contract(self):
        current_date = self.get_game_date()
        begin = current_date.strftime("%Y-%m-%d")
        end = (current_date + timedelta(days=365)).strftime("%Y-%m-%d")

        self.staff.contract["begin"] = begin
        self.staff.contract["end"] = end
        self.staff.contract["salary"] = self.offer_salary

        was_fa = self.staff.is_free_agent()
        self.staff.team = self.state.user_team
        self.staff.status["roster"] = "active"
        self.staff.data["team"] = self.staff.team
        self.staff.data["contract"] = self.staff.contract
        self.staff.data["status"] = self.staff.status

        if was_fa and self.offer_bonus > 0:
            self.state.transfer_budget -= self.offer_bonus
            if hasattr(self.state, "add_money"):
                self.state.add_money(-self.offer_bonus)

        if not hasattr(self.state, "owned_staff"):
            self.state.owned_staff = []
        if self.staff not in self.state.owned_staff:
            self.state.owned_staff.append(self.staff)

        if not hasattr(self.state, "staff_slots"):
            self.state.staff_slots = {}
        if self.staff.role not in self.state.staff_slots:
            self.state.staff_slots[self.staff.role] = self.staff

        return ("staff_detail_refresh", self.staff)

    def draw_mood_bar(self, screen, x, y, bar_w):
        expected = expected_staff_salary(self.staff)
        _, mood_name, mood_color = get_mood(self.effective_offer(), expected)

        screen.blit(self.FONT.render(mood_name, True, mood_color), (x, y))
        seg_w = bar_w // len(MOOD_LEVELS)
        for i, (_, name, color) in enumerate(MOOD_LEVELS):
            rect = pygame.Rect(x + i * seg_w, y + 28, seg_w - 2, 10)
            pygame.draw.rect(screen, color if name == mood_name else (45, 45, 45), rect)
            pygame.draw.rect(screen, (25, 25, 25), rect, 1)

    def draw_effect_lines(self, screen, rect):
        effects = getattr(self.staff, "effects", getattr(self.staff, "effect_dict", {}))
        traits = getattr(self.staff, "traits", {})
        y = rect.y + 55

        if effects:
            screen.blit(self.SMALL.render("Effects", True, (100, 100, 100)), (rect.x + 15, y))
            y += 28
            for key, value in effects.items():
                bonus = self.staff.get_effect_bonus(key) if hasattr(self.staff, "get_effect_bonus") else value
                screen.blit(self.SMALL.render(f"{trait_label(key)} +{bonus}", True, black), (rect.x + 20, y))
                y += 28

        if traits:
            y += 12
            screen.blit(self.SMALL.render("Traits", True, (100, 100, 100)), (rect.x + 15, y))
            y += 28
            for key, value in traits.items():
                bonus = self.staff.get_trait_bonus(key) if hasattr(self.staff, "get_trait_bonus") else value
                screen.blit(self.SMALL.render(f"{trait_label(key)} +{bonus}", True, black), (rect.x + 20, y))
                y += 28

        if not effects and not traits:
            screen.blit(self.FONT.render("No visible effect data", True, (130, 130, 130)), (rect.x + 20, y + 40))

    def draw(self, screen):
        screen.fill((20, 20, 20))

        for rect, fc, bc in [
            (self.left, (215, 215, 215), (140, 140, 140)),
            (self.mid, (215, 215, 215), (140, 140, 140)),
            (self.right, (210, 215, 210), (140, 145, 140)),
        ]:
            pygame.draw.rect(screen, fc, rect)
            pygame.draw.rect(screen, bc, rect, 2)

        expected = expected_staff_salary(self.staff)
        self.draw_mood_bar(screen, self.mid.x + 15, self.mid.y - 60, self.mid.width - 30)

        screen.blit(self.FONT.render("CURRENT CONTRACT", True, black), (self.left.x + 15, self.left.y + 15))
        begin = self.staff.contract.get("begin", "-")
        end = self.staff.contract.get("end", "-")
        current_lines = [
            ("Period", begin),
            ("", f"~ {end}"),
            ("Salary", fmt_money(self.staff.salary())),
            ("Team", getattr(self.staff, "team", "FA")),
        ]
        for i, (label, value) in enumerate(current_lines):
            y = self.left.y + 55 + i * 38
            if label:
                screen.blit(self.SMALL.render(label, True, (100, 100, 100)), (self.left.x + 15, y))
            screen.blit(self.FONT.render(str(value), True, black), (self.left.x + 15, y + 17))

        pygame.draw.line(screen, (180, 180, 180), (self.left.x + 10, self.left.y + 220), (self.left.right - 10, self.left.y + 220), 1)
        screen.blit(self.FONT.render("BUDGET", True, black), (self.left.x + 15, self.left.y + 230))
        remaining_wage = self.get_available_salary() - self.offer_salary
        budget_lines = [
            ("Available Wage", fmt_money(self.get_available_salary())),
            ("After Offer", fmt_money(remaining_wage)),
            ("Transfer Budget", fmt_money(getattr(self.state, "transfer_budget", 0))),
            ("Expected Salary", fmt_money(expected)),
        ]
        for i, (label, value) in enumerate(budget_lines):
            y = self.left.y + 265 + i * 60
            color = (180, 60, 60) if label == "Expected Salary" else black
            screen.blit(self.SMALL.render(label, True, (100, 100, 100)), (self.left.x + 15, y))
            screen.blit(self.FONT.render(value, True, color), (self.left.x + 15, y + 18))

        screen.blit(self.FONT.render("CONTRACT OFFER", True, black), (self.mid.x + 15, self.mid.y + 15))
        screen.blit(self.SMALL.render("Contract Length", True, (100, 100, 100)), (self.mid.x + 20, self.mid.y + 60))
        screen.blit(self.FONT.render("1 year", True, black), (self.mid.x + 20, self.mid.y + 78))
        screen.blit(self.SMALL.render("Annual Salary", True, (100, 100, 100)), (self.mid.x + 20, self.mid.y + 130))
        screen.blit(self.FONT.render(fmt_money(self.offer_salary), True, black), (self.mid.x + 20, self.mid.y + 148))

        is_fa = self.staff.is_free_agent()
        bonus_color = black if is_fa else (160, 160, 160)
        bonus_label = "Signing Bonus" if is_fa else "Signing Bonus  (re-sign only)"
        screen.blit(self.SMALL.render(bonus_label, True, (100, 100, 100)), (self.mid.x + 20, self.mid.y + 190))
        screen.blit(self.FONT.render(fmt_money(self.offer_bonus), True, bonus_color), (self.mid.x + 20, self.mid.y + 208))

        pygame.draw.line(screen, (180, 180, 180), (self.mid.x + 10, self.mid.y + 255), (self.mid.right - 10, self.mid.y + 255), 1)
        screen.blit(self.FONT.render("SUMMARY", True, black), (self.mid.x + 15, self.mid.y + 275))
        summary_lines = [
            f"Role: {ROLE_LABELS.get(self.staff.role, self.staff.role)}",
            f"Stars: {self.staff.get_star_text()}",
            f"Effective Offer: {fmt_money(self.effective_offer())}",
            f"Expected: {fmt_money(expected)}",
        ]
        for i, line in enumerate(summary_lines):
            screen.blit(self.SMALL.render(line, True, black), (self.mid.x + 20, self.mid.y + 315 + i * 32))

        if self.offer_result == "accept":
            screen.blit(self.FONT.render("STAFF ACCEPTS", True, (0, 140, 0)), (self.mid.x + 20, self.mid.y + 455))
        elif self.offer_result == "reject":
            screen.blit(self.FONT.render("STAFF REJECTS", True, (180, 0, 0)), (self.mid.x + 20, self.mid.y + 455))

        screen.blit(self.FONT.render(self.staff.name, True, black), (self.right.x + 15, self.right.y + 15))
        title = getattr(self.staff, "title", "-")
        archetype = getattr(self.staff, "archetype", "-")
        bio = getattr(self.staff, "bio", {})
        profile_lines = [
            f"Role: {ROLE_LABELS.get(self.staff.role, self.staff.role)}",
            f"Type: {title}",
            f"Archetype: {archetype}",
            f"Market Value: {fmt_money(getattr(self.staff, 'market_value', 0))}",
            f"Birth: {bio.get('birth', '-')}",
            f"Nationality: {bio.get('nationality', '-')}",
        ]
        for i, line in enumerate(profile_lines):
            screen.blit(self.SMALL.render(line, True, black), (self.right.x + 15, self.right.y + 55 + i * 28))

        pygame.draw.line(screen, (180, 180, 180), (self.right.x + 10, self.right.y + 235), (self.right.right - 10, self.right.y + 235), 1)
        self.draw_effect_lines(screen, pygame.Rect(self.right.x, self.right.y + 205, self.right.width, self.right.height - 205))

        for btn in self.buttons:
            btn.draw(screen)

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update_hover(mouse_pos)

        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for btn in self.buttons:
                    result = btn.handle_event(event)
                    if result:
                        return result

        return None
