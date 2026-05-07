from scenes.base_scene import Scene
from ui.button import Button
from config import *
from scenes.staff_contract_scene import StaffContractScene
import pygame


def trait_label(key):
    return str(key).replace("_", " ").title()


class StaffDetailScene(Scene):
    def __init__(self, staff, state):
        self.staff = staff
        self.state = state
        action_text = "HIRE" if staff.is_free_agent() else "CONTRACT"
        self.buttons = [
            Button((width - 160, height - 80, 120, 50), "BACK", self.back),
            Button((width - 320, height - 80, 140, 50), action_text, self.go_contract),
        ]
        self.SMALL_FONT = pygame.font.SysFont(None, 24)
        self.TINY_FONT = pygame.font.SysFont(None, 21)

    def back(self):
        return self.state.prevscene if self.state.prevscene else "transfer"

    def go_contract(self):
        return ("staff_contract", StaffContractScene(self.staff, self.state))

    def _format_money(self, value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return "-"
        return f"${value:,}"

    def _draw_panel(self, screen, rect, title, bg=(215, 215, 215)):
        pygame.draw.rect(screen, bg, rect)
        pygame.draw.rect(screen, (140, 140, 140), rect, 2)
        screen.blit(self.SMALL_FONT.render(title, True, (50, 50, 50)), (rect.x + 12, rect.y + 10))
        pygame.draw.line(screen, (175, 175, 175), (rect.x + 10, rect.y + 38), (rect.right - 10, rect.y + 38), 1)

    def _draw_lines(self, screen, lines, x, y, gap=32):
        for i, line in enumerate(lines):
            screen.blit(self.SMALL_FONT.render(str(line), True, black), (x, y + i * gap))

    def draw(self, screen):
        screen.fill((20, 20, 20))

        face_rect = pygame.Rect(MARGIN, 15, 60, 60)
        pygame.draw.rect(screen, (150, 150, 150), face_rect)

        role = getattr(self.staff, "role", "-")
        title = getattr(self.staff, "title", "-")
        stars = self.staff.get_star_text() if hasattr(self.staff, "get_star_text") else "-"

        title_str = f"{self.staff.name} | {role} | {title}"
        sub_title = f"{stars}  Team {getattr(self.staff, 'team', 'FA')}"
        screen.blit(FONT.render(title_str, True, white), (face_rect.right + 20, 20))
        screen.blit(self.SMALL_FONT.render(sub_title, True, white), (face_rect.right + 20, 55))

        box_w = (width - (MARGIN * 2) - (GAP * 2)) // 3
        top_y = CONTENT_TOP
        panel_h = TOP_H

        bio_rect = pygame.Rect(MARGIN, top_y, box_w, panel_h)
        eff_rect = pygame.Rect(bio_rect.right + GAP, top_y, box_w, panel_h)
        trait_rect = pygame.Rect(eff_rect.right + GAP, top_y, box_w, panel_h)

        self._draw_panel(screen, bio_rect, "Bio / Contract")
        self._draw_panel(screen, eff_rect, "Effects")
        self._draw_panel(screen, trait_rect, "Traits", (210, 220, 210))

        bio = getattr(self.staff, "bio", {})
        contract = getattr(self.staff, "contract", {})
        info_lines = [
            f"ID: {getattr(self.staff, 'id', '-')}",
            f"Birth: {bio.get('birth', '-')}",
            f"Nationality: {bio.get('nationality', '-')}",
            f"Salary: {self._format_money(contract.get('salary', 0))}",
            f"Market: {self._format_money(getattr(self.staff, 'market_value', 0))}",
            f"Contract: {contract.get('begin', '-')} ~ {contract.get('end', '-')}",
        ]
        self._draw_lines(screen, info_lines, bio_rect.x + 15, bio_rect.y + 55, 27)

        effects = getattr(self.staff, "effects", getattr(self.staff, "effect_dict", {}))
        if effects:
            y = eff_rect.y + 58
            for key, value in effects.items():
                bonus = self.staff.get_effect_bonus(key) if hasattr(self.staff, "get_effect_bonus") else self.staff.stars * value
                line = f"{trait_label(key)}  +{bonus}"
                screen.blit(FONT.render(line, True, black), (eff_rect.x + 20, y))
                screen.blit(self.TINY_FONT.render(f"base {value} x stars", True, (90, 90, 90)), (eff_rect.x + 22, y + 30))
                y += 58
        else:
            screen.blit(FONT.render("No direct attribute bonus", True, (120, 120, 120)), (eff_rect.x + 25, eff_rect.y + 95))

        traits = getattr(self.staff, "traits", {})
        if traits:
            y = trait_rect.y + 55
            for key, value in traits.items():
                bonus = self.staff.get_trait_bonus(key) if hasattr(self.staff, "get_trait_bonus") else self.staff.stars * value
                screen.blit(self.SMALL_FONT.render(trait_label(key), True, black), (trait_rect.x + 18, y))
                screen.blit(FONT.render(f"+{bonus}", True, (40, 120, 60)), (trait_rect.right - 75, y - 4))
                y += 30
        else:
            screen.blit(FONT.render("No system trait", True, (120, 120, 120)), (trait_rect.x + 55, trait_rect.y + 95))

        desc_rect = pygame.Rect(MARGIN, bio_rect.bottom + GAP, width - MARGIN * 2, BOTTOM_H)
        self._draw_panel(screen, desc_rect, "Description")

        desc = getattr(self.staff, "effect_desc", "")
        archetype = getattr(self.staff, "archetype", "-")
        desc_lines = [
            f"Archetype: {archetype}",
            desc if desc else "No description.",
            "Use contract controls to hire or renew this staff member.",
        ]
        self._draw_lines(screen, desc_lines, desc_rect.x + 20, desc_rect.y + 58, 36)

        for btn in self.buttons:
            btn.draw(screen)

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update_hover(mouse_pos)
        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 1:
                    for btn in self.buttons:
                        result = btn.handle_event(e)
                        if result:
                            return result
        return None
