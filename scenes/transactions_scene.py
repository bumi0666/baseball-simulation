from scenes.base_scene import Scene
from ui.button import Button
from config import *
from ui.layout import get_common_buttons, draw_common_ui
import pygame

TYPE_COLORS = {"영입": (90, 200, 120), "방출": (230, 100, 100), "재계약": (130, 170, 230),
               "승격": (240, 200, 90), "강등": (200, 140, 90), "드래프트": (200, 130, 230)}
TYPE_FILTERS = ["전체", "영입", "방출", "재계약", "승격", "강등", "드래프트"]


class TransactionsScene(Scene):
    """다른 구단의 영입·방출·재계약 내역 (최신순)."""

    ROW_H = 30
    LIST_X = 210
    LIST_Y = 176

    def __init__(self, state):
        self.state = state
        self.team_filter = "ALL"
        self.type_filter = "전체"
        self.scroll = 0

        self.TITLE = pygame.font.SysFont("malgungothic", 30, bold=True)
        self.F = pygame.font.SysFont("malgungothic", 17)
        self.FB = pygame.font.SysFont("malgungothic", 17, bold=True)
        self.BF = pygame.font.SysFont("malgungothic", 15, bold=True)

        self.nav_buttons = get_common_buttons(self)
        self.filter_buttons = []
        x = self.LIST_X
        for name in ["ALL"] + list(getattr(state, "opponents", [])):
            w = 50 if name == "ALL" else 82
            self.filter_buttons.append((("team", name), Button((x, 70, w, 30), name, lambda n=name: self.set_team(n), font=self.BF)))
            x += w + 6
        x = self.LIST_X
        for name in TYPE_FILTERS:
            self.filter_buttons.append((("type", name), Button((x, 108, 70, 28), name, lambda n=name: self.set_type(n), font=self.BF)))
            x += 76
        self.buttons = self.nav_buttons + [b for _, b in self.filter_buttons]
        self._sync_active()

    # ── 필터 ──
    def set_team(self, name):
        self.team_filter = name
        self.scroll = 0
        self._sync_active()

    def set_type(self, name):
        self.type_filter = name
        self.scroll = 0
        self._sync_active()

    def _sync_active(self):
        for (kind, name), btn in self.filter_buttons:
            btn.active = (name == (self.team_filter if kind == "team" else self.type_filter))

    def rows(self):
        data = getattr(self.state, "transactions", [])
        out = [t for t in reversed(data)
               if (self.team_filter == "ALL" or t.get("team") == self.team_filter)
               and (self.type_filter == "전체" or t.get("type") == self.type_filter)]
        return out

    def visible_rows(self):
        return max(1, (height - self.LIST_Y - 20) // self.ROW_H)

    # ── 입력 ──
    def update(self, events):
        rows = self.rows()
        max_scroll = max(0, len(rows) - self.visible_rows())
        for e in events:
            if e.type == pygame.MOUSEWHEEL:
                self.scroll = max(0, min(max_scroll, self.scroll - e.y * 3))
        self.scroll = min(self.scroll, max_scroll)
        return super().update(events)

    # ── 그리기 ──
    def draw(self, screen):
        screen.fill((20, 20, 20))
        draw_common_ui(screen, self.state, FONT)
        screen.blit(self.TITLE.render("Transactions", True, (235, 235, 235)), (self.LIST_X, 22))
        for b in self.buttons:
            b.draw(screen)

        cols = [("날짜", 0), ("구단", 105), ("구분", 215), ("선수", 300), ("OVR", 520), ("사유", 585)]
        right = width - 20
        hdr = pygame.Rect(self.LIST_X, self.LIST_Y - 28, right - self.LIST_X, 26)
        pygame.draw.rect(screen, (30, 40, 60), hdr)
        for label, dx in cols:
            screen.blit(self.F.render(label, True, (0, 255, 255)), (self.LIST_X + 8 + dx, hdr.y + 2))

        if self.team_filter != "ALL":
            import ai_team_manager as M
            prof = M.team_profile(self.state, self.team_filter)
            payroll = sum(p.salary() for p in self.state.team_rosters.get(self.team_filter, []))
            info = "%s · 성향 %s · 임금 상한 %.2fM · 현재 연봉 총액 %.2fM" % (
                self.team_filter, prof["label"], prof["wage_cap"] / 1e6, payroll / 1e6)
            screen.blit(self.F.render(info, True, (200, 200, 120)), (self.LIST_X + 200, 36))

        rows = self.rows()
        if not rows:
            screen.blit(self.F.render("아직 거래 내역이 없습니다.", True, (160, 160, 160)), (self.LIST_X + 8, self.LIST_Y + 10))
            return
        for i, t in enumerate(rows[self.scroll:self.scroll + self.visible_rows()]):
            y = self.LIST_Y + i * self.ROW_H
            pygame.draw.rect(screen, (40, 42, 48) if i % 2 == 0 else (30, 32, 38),
                             (self.LIST_X, y, right - self.LIST_X, self.ROW_H))
            x0 = self.LIST_X + 8
            color = TYPE_COLORS.get(t.get("type"), (220, 220, 220))
            screen.blit(self.F.render(str(t.get("date", "")), True, (190, 190, 190)), (x0, y + 5))
            screen.blit(self.F.render(str(t.get("team", "")), True, (230, 230, 230)), (x0 + 105, y + 5))
            screen.blit(self.FB.render(str(t.get("type", "")), True, color), (x0 + 215, y + 5))
            screen.blit(self.F.render(f"{t.get('name', '')} ({t.get('pos', '')})", True, (230, 230, 230)), (x0 + 300, y + 5))
            screen.blit(self.F.render(str(t.get("ovr", "")), True, (230, 230, 230)), (x0 + 520, y + 5))
            reason = str(t.get("reason", ""))
            clip = pygame.Rect(x0 + 585, y, right - (x0 + 585) - 6, self.ROW_H)
            screen.set_clip(clip)
            screen.blit(self.F.render(reason, True, (170, 170, 170)), (clip.x, y + 5))
            screen.set_clip(None)

        if len(rows) > self.visible_rows():
            track = pygame.Rect(right - 6, self.LIST_Y, 5, self.visible_rows() * self.ROW_H)
            pygame.draw.rect(screen, (50, 50, 55), track)
            h = max(20, int(track.height * self.visible_rows() / len(rows)))
            max_scroll = len(rows) - self.visible_rows()
            ty = track.y + int((track.height - h) * (self.scroll / max_scroll)) if max_scroll else track.y
            pygame.draw.rect(screen, (120, 130, 150), (track.x, ty, track.width, h))
