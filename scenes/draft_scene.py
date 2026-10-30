from datetime import date, timedelta

import pygame

import draft
from scenes.base_scene import Scene
from ui.button import Button
from config import *
from ui.layout import get_common_buttons, draw_common_ui


class DraftScene(Scene):
    """시즌 종료 후 열리는 신인 드래프트."""

    ROW_H = 30
    LIST_X = 210
    LIST_Y = 150
    LOG_X = 880

    def __init__(self, state):
        self.state = state
        self.scroll = 0
        self.selected = None
        self.TITLE = pygame.font.SysFont("malgungothic", 30, bold=True)
        self.F = pygame.font.SysFont("malgungothic", 17)
        self.FB = pygame.font.SysFont("malgungothic", 17, bold=True)
        self.BF = pygame.font.SysFont("malgungothic", 17, bold=True)
        self.buttons = get_common_buttons(self)
        self.pick_btn = Button((self.LIST_X, 664, 170, 40), "DRAFT", self.do_pick, font=self.BF)
        self.auto_btn = Button((self.LIST_X + 180, 664, 170, 40), "AUTO PICK", self.do_auto, font=self.BF)
        self.buttons += [self.pick_btn, self.auto_btn]
        self.msg = ""

    # ── 상태 ──
    def _today(self):
        y, m, d = self.state.base_date
        return date(y, m, d) + timedelta(days=self.state.current_day - 1)

    def _draft(self):
        return getattr(self.state, "draft", None)

    def my_turn(self):
        d = self._draft()
        return bool(d) and d["status"] == "open" and draft.on_the_clock(self.state) == self.state.user_team

    # ── 동작 ──
    def do_pick(self):
        if not self.my_turn():
            self.msg = "Not your turn."
        elif self.selected is None:
            self.msg = "Select a prospect first."
        elif draft.user_pick(self.state, self.selected, self._today()):
            self.msg = "Drafted %s." % self.selected.name
            self.selected = None
        else:
            self.msg = "That prospect is no longer available."
        return None

    def do_auto(self):
        if self.my_turn() and draft.auto_user_pick(self.state, self._today()):
            self.msg = "Auto pick made."
            self.selected = None
        return None

    # ── 입력 ──
    def update(self, events):
        rows = draft.available(self.state)
        vis = self.visible_rows()
        for e in events:
            if e.type == pygame.MOUSEWHEEL:
                self.scroll = max(0, min(max(0, len(rows) - vis), self.scroll - e.y * 3))
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for i, p in enumerate(rows[self.scroll:self.scroll + vis]):
                    r = pygame.Rect(self.LIST_X, self.LIST_Y + i * self.ROW_H, self.LOG_X - self.LIST_X - 20, self.ROW_H)
                    if r.collidepoint(e.pos):
                        self.selected = p
        return super().update(events)

    def visible_rows(self):
        return (660 - self.LIST_Y) // self.ROW_H

    # ── 그리기 ──
    def draw(self, screen):
        screen.fill((20, 20, 20))
        draw_common_ui(screen, self.state, FONT)
        screen.blit(self.TITLE.render("Draft", True, (235, 235, 235)), (self.LIST_X, 22))
        for b in self.buttons:
            b.draw(screen)
        d = self._draft()
        if not d:
            screen.blit(self.F.render("No draft in progress. The rookie draft opens after the season ends.", True, (180, 180, 180)),
                        (self.LIST_X, 90))
            return

        n_teams = len(d["order"]) // draft.ROUNDS
        pick = min(d["pick"], len(d["order"]) - 1)
        if d["status"] == "open":
            clock = d["order"][pick]
            status = "Round %d/%d  ·  Pick %d/%d  ·  On the clock: %s%s  ·  Auto-completes %s" % (
                pick // n_teams + 1, draft.ROUNDS, pick + 1, len(d["order"]), clock,
                " (YOU)" if clock == self.state.user_team else "", d["deadline"])
        else:
            status = "Draft completed. Drafted rookies joined their teams' reserve rosters."
        screen.blit(self.F.render(status, True, (200, 200, 120)), (self.LIST_X, 70))
        if self.msg:
            screen.blit(self.F.render(self.msg, True, (120, 200, 150)), (self.LIST_X + 400, 664 + 10))

        # 신인 목록
        hdr = pygame.Rect(self.LIST_X, self.LIST_Y - 28, self.LOG_X - self.LIST_X - 20, 26)
        pygame.draw.rect(screen, (30, 40, 60), hdr)
        for label, dx in (("NAME", 8), ("POS", 170), ("AGE", 240), ("OVR", 310), ("POT", 380), ("GAP", 450)):
            screen.blit(self.F.render(label, True, (0, 255, 255)), (self.LIST_X + dx, hdr.y + 2))
        rows = draft.available(self.state)
        if d["status"] != "open":
            rows = []
        for i, p in enumerate(rows[self.scroll:self.scroll + self.visible_rows()]):
            y = self.LIST_Y + i * self.ROW_H
            r = pygame.Rect(self.LIST_X, y, hdr.width, self.ROW_H)
            col = (60, 80, 120) if p is self.selected else ((40, 42, 48) if i % 2 == 0 else (30, 32, 38))
            pygame.draw.rect(screen, col, r)
            ovr, gap = p.calculate_ovr(), p.pot_gap()
            for txt, dx in ((p.name, 8), (p.pos, 170), (str(p.age() or "-"), 240), (str(ovr), 310),
                            ("%d" % round(ovr + gap), 380), ("+%d" % round(gap), 450)):
                screen.blit(self.F.render(txt, True, (230, 230, 230)), (self.LIST_X + dx, y + 5))

        # 지명 기록
        screen.blit(self.FB.render("Picks", True, (235, 235, 235)), (self.LOG_X, 70))
        pool = {p.id: p for p in self.state.team_rosters.get("FA", []) + self.state.team_rosters.get("DRAFT", [])}
        for team_list in self.state.team_rosters.values():
            for p in team_list:
                pool.setdefault(p.id, p)
        for i, pk in enumerate(reversed(d["picks"][-9:])):
            p = pool.get(pk["id"])
            mine = pk["team"] == self.state.user_team
            txt = "#%d %s: %s (%s)" % (pk["pick"], pk["team"], p.name if p else "?", p.pos if p else "")
            screen.blit(self.F.render(txt, True, (150, 230, 160) if mine else (200, 200, 200)), (self.LOG_X, 100 + i * 24))

        # 구단별 부족 포지션 (다음 시즌 이후에도 남는 선수 + 이번 지명 기준, 목표 인원 대비)
        ny = 340
        screen.blit(self.FB.render("Team needs (short positions)", True, (235, 235, 235)), (self.LOG_X, ny))
        for i, team in enumerate(d["order"][:n_teams]):
            needs = draft.team_needs(self.state, team)
            txt = "  ".join("%s -%d" % (pos, n) for pos, n in sorted(needs.items(), key=lambda kv: -kv[1])) or "-"
            mine = team == self.state.user_team
            y = ny + 28 + i * 24
            screen.blit(self.F.render(team, True, (150, 230, 160) if mine else (200, 200, 200)), (self.LOG_X, y))
            screen.blit(self.F.render(txt, True, (240, 150, 120) if needs else (120, 120, 120)), (self.LOG_X + 100, y))
