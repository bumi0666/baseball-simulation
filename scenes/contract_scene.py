from scenes.base_scene import Scene
from ui.button import Button
from config import *
import pygame
import random
from datetime import date, timedelta


# ══════════════════════════════════════════════════════════
#  인센티브 정의
# ══════════════════════════════════════════════════════════

PITCHER_INCENTIVES = [
    ("ip",  "ip",  [(50,"D",0.02),(100,"C",0.04),(150,"B",0.06),(200,"A",0.10)], None),
    ("g",   "g",   [(40,"D",0.02),(60,"C",0.04),(80,"B",0.06),(100,"A",0.10)],  None),
    ("w",   "w",   [(5,"D",0.02),(10,"C",0.04),(15,"B",0.06),(20,"A",0.10)],    None),
    ("so",  "so",  [(50,"D",0.02),(100,"C",0.04),(150,"B",0.06),(200,"A",0.10)],None),
    ("sv",  "sv",  [(10,"D",0.02),(20,"C",0.04),(30,"B",0.06),(40,"A",0.10)],   None),
    ("hld", "hld", [(10,"C",0.04),(20,"B",0.06),(30,"A",0.10)],                 None),
    ("ERA", "era", [(2.5,"A",0.10),(3.2,"B",0.06),(4.0,"C",0.04),(5.0,"D",0.02)], ("ip",100)),
]

BATTER_INCENTIVES = [
    ("ab",  "ab",  [(300,"D",0.02),(400,"C",0.04),(500,"B",0.06)],               None),
    ("h",   "h",   [(100,"C",0.04),(140,"B",0.06),(180,"A",0.10)],               None),
    ("g",   "g",   [(50,"D",0.02),(75,"C",0.04),(100,"B",0.06),(125,"A",0.10)],  None),
    ("hr",  "hr",  [(10,"D",0.02),(20,"C",0.04),(30,"B",0.06),(40,"A",0.10)],    None),
    ("rbi", "rbi", [(50,"C",0.04),(75,"B",0.06),(100,"A",0.10)],                 None),
    ("sb",  "sb",  [(10,"D",0.02),(20,"C",0.04),(30,"B",0.06),(40,"A",0.10)],    None),
    ("OPS", "ops", [(0.8,"C",0.04),(0.9,"B",0.06),(1.0,"A",0.10)],               ("ab",300)),
]

GRADE_COLOR = {"A":(200,50,50),"B":(200,120,0),"C":(50,130,200),"D":(100,100,100)}

# 등급별 달성 확률 (높은 등급일수록 달성하기 어려움)
GRADE_PROB = {"A": 0.30, "B": 0.50, "C": 0.70, "D": 0.90}


# ══════════════════════════════════════════════════════════
#  감정 시스템
# ══════════════════════════════════════════════════════════

MOOD_LEVELS = [
    # (최소 비율, 이름, 텍스트 색상)
    (-999,  "FURIOUS",    (220, 60,  60)),
    (-0.20, "UNHAPPY",    (220, 130, 50)),
    (-0.08, "NEUTRAL",    (160, 160, 160)),
    ( 0.00, "INTERESTED", (100, 190, 100)),
    ( 0.08, "HAPPY",      (60,  210, 130)),
    ( 0.20, "THRILLED",   (50,  220, 255)),
]

AGENT_COMMENTS = {
    "FURIOUS": [
        "This is an insult. We're walking away.",
        "My client deserves far better than this.",
        "Don't waste our time with this offer.",
    ],
    "UNHAPPY": [
        "This doesn't reflect his market value.",
        "We expected a more serious offer.",
        "There's a significant gap here.",
    ],
    "NEUTRAL": [
        "It's a starting point, but we need more.",
        "We're listening, but not convinced yet.",
        "Somewhere in the right direction.",
    ],
    "INTERESTED": [
        "Now we're talking. Keep going.",
        "This is getting closer to what we want.",
        "He's paying attention to this offer.",
    ],
    "HAPPY": [
        "This shows real respect for his talent.",
        "We're very close to a deal here.",
        "My client is seriously considering this.",
    ],
    "THRILLED": [
        "He'd sign this today. Outstanding offer.",
        "This is exactly what we were hoping for.",
        "You clearly value him. Let's do this.",
    ],
}


def get_mood(effective_offer, expected):
    ratio = (effective_offer - expected) / expected if expected > 0 else 0
    result = MOOD_LEVELS[0]
    for threshold, name, color in MOOD_LEVELS:
        if ratio >= threshold:
            result = (threshold, name, color)
    return result  # (threshold, name, color)


def draw_mood_bar(screen, font, small_font, effective_offer, expected, x, y, width=320):
    """감정 바 + 에이전트 코멘트를 그립니다."""
    _, mood_name, mood_color = get_mood(effective_offer, expected)

    # 감정 이름
    name_surf = font.render(mood_name, True, mood_color)
    screen.blit(name_surf, (x, y))

    # 6칸 세그먼트 바
    seg_w = width // 6
    for i, (_, name, color) in enumerate(MOOD_LEVELS):
        seg_rect = pygame.Rect(x + i * seg_w, y + 28, seg_w - 2, 10)
        is_active = (name == mood_name)
        pygame.draw.rect(screen, color if is_active else (45, 45, 45), seg_rect)
        pygame.draw.rect(screen, (25, 25, 25), seg_rect, 1)

    # 에이전트 코멘트 (같은 유효 오퍼값이면 항상 같은 코멘트)
    comments = AGENT_COMMENTS.get(mood_name, [])
    if comments:
        random.seed(int(effective_offer))
        comment = random.choice(comments)
        c_surf = small_font.render(f'"{comment}"', True, (170, 170, 170))
        screen.blit(c_surf, (x, y + 46))


# ══════════════════════════════════════════════════════════
#  연봉 계산
# ══════════════════════════════════════════════════════════

def calc_salary_adjustment(player, stats):
    """시즌 성적 기반 연봉 조정 비율 계산 (-25%~+25%)"""
    pct = 0.0
    if player.is_batter():
        ab  = stats.get("ab", 0)
        ops = stats.get("ops", stats.get("obp", 0) + stats.get("slg", 0))
        rbi = stats.get("rbi", 0)
        hr  = stats.get("hr", 0)
        sb  = stats.get("sb", 0)

        if ab < 200:    pct -= 0.05
        elif ab >= 400: pct += 0.05
        if ops < 0.7:   pct -= 0.05
        elif ops >= 0.9: pct += 0.05
        if rbi < 40:    pct -= 0.05
        elif rbi >= 90: pct += 0.05
        if hr >= 15:    pct += 0.05
        if sb >= 15:    pct += 0.05
    else:
        ip  = stats.get("ip", 0)
        era = stats.get("era", 99.0)
        w   = stats.get("w", 0)
        sv  = stats.get("sv", 0)
        hld = stats.get("hld", 0)

        if ip < 50:      pct -= 0.05
        elif ip >= 120:  pct += 0.05
        if era >= 5.0:   pct -= 0.05
        elif era < 3.5:  pct += 0.05
        if w >= 12:      pct += 0.05
        if sv >= 15:     pct += 0.05
        if hld >= 10:    pct += 0.05

    return max(-0.25, min(0.25, pct))


def expected_salary(player, stats):
    """선수가 요구하는 기대 연봉 (FA면 15% 프리미엄)"""
    base = player.salary()
    adj  = calc_salary_adjustment(player, stats)
    exp  = int(base * (1 + adj))

    if player.is_free_agent():
        exp = int(exp * 1.15)  # FA 프리미엄

    return exp


def get_incentive_list(player):
    return PITCHER_INCENTIVES if not player.is_batter() else BATTER_INCENTIVES


def incentive_pct(inc_def, stats):
    """
    선택된 인센티브의 퍼센트 반환.
    현재 성적이 임계값에 못 미쳐도 최고 등급 퍼센트를 반환 (계약 시 약속 기준).
    """
    label, key, thresholds, condition = inc_def

    if condition:
        cond_key, cond_val = condition
        if stats.get(cond_key, 0) < cond_val:
            return 0.0

    if key == "era":
        val = stats.get(key, 99.0)
        for thresh, grade, pct in thresholds:
            if val <= thresh:
                return pct
        # 아직 미달 → 최고 등급(첫 번째) 반환
        return thresholds[0][2]
    else:
        val = stats.get(key, 0)
        result = 0.0
        for thresh, grade, pct in thresholds:
            if val >= thresh:
                result = pct
        # 아직 미달 → 최고 등급(마지막) 반환
        return result if result > 0.0 else thresholds[-1][2]


def calc_effective_offer(player, offer_salary, offer_transfer, selected_incentives, curr_stats):
    """
    유효 오퍼 = 연봉 + 계약금(FA 시) + 인센티브 기대값
    인센티브 기대값 = 연봉 × Σ(최고등급 퍼센트 × 등급별 달성 확률)
    """
    inc_list = get_incentive_list(player)

    inc_value = 0.0
    for i in selected_incentives:
        if i >= len(inc_list):
            continue
        label, key, thresholds, condition = inc_list[i]
        if key == "era":
            grade = thresholds[0][1]
            pct   = thresholds[0][2]
        else:
            grade = thresholds[-1][1]
            pct   = thresholds[-1][2]
        prob = GRADE_PROB.get(grade, 0.5)
        inc_value += offer_salary * pct * prob

    transfer_value = offer_transfer if player.is_free_agent() else 0

    return offer_salary + transfer_value + inc_value


# ══════════════════════════════════════════════════════════
#  ContractScene
# ══════════════════════════════════════════════════════════

class ContractScene(Scene):
    def __init__(self, player, state):
        self.player = player
        self.state  = state

        self.FONT       = pygame.font.SysFont(None, 28)
        self.SMALL      = pygame.font.SysFont(None, 22)
        self.SMALL_FONT = pygame.font.SysFont(None, 22)
        self.TINY       = pygame.font.SysFont(None, 18)

        self.offer_salary   = player.salary()
        self.offer_transfer = 0
        self.salary_step    = 5000
        self.transfer_step  = 5000

        self.selected_incentives = set()

        # 레이아웃
        self.left  = pygame.Rect(30,  120, 310, 540)
        self.mid   = pygame.Rect(355, 120, 380, 540)
        self.right = pygame.Rect(750, 120, 500, 540)

        self.offer_result = None

        # 현재 시즌 스탯
        y, m, d = self.state.base_date
        current_date_obj  = date(y, m, d) + timedelta(days=self.state.current_day - 1)
        current_game_year = current_date_obj.year
        curr_season = next((c for c in self.player.career
                            if c.get("season") == current_game_year), None)
        self.curr_stats = curr_season.get("stats", {}) if curr_season else {}

        # 버튼
        self.buttons = [
            Button((width - 160, height - 60, 120, 45), "BACK", self.back),
        ]
        bx = self.mid.x + 280
        self.buttons.append(Button((bx,      self.mid.y + 155, 36, 30), "+", self.increase_salary))
        self.buttons.append(Button((bx + 40, self.mid.y + 155, 36, 30), "-", self.decrease_salary))
        self.buttons.append(Button((bx,      self.mid.y + 215, 36, 30), "+", self.increase_transfer))
        self.buttons.append(Button((bx + 40, self.mid.y + 215, 36, 30), "-", self.decrease_transfer))

        self.offer_button = Button(
            (self.mid.x + 20, self.mid.y + 490, 200, 45), "MAKE OFFER", self.make_offer)
        self.buttons.append(self.offer_button)

    # ── 버튼 액션 ──────────────────────────────────────────

    def back(self):
        return "player_detail"

    def get_current_wage_total(self):
        return sum(p.salary() for p in self.state.team_rosters[self.state.user_team])

    def increase_salary(self):
        current_total = self.get_current_wage_total()
        available     = self.state.wage_budget - current_total + self.player.salary()
        if self.offer_salary + self.salary_step <= available:
            self.offer_salary += self.salary_step

    def decrease_salary(self):
        if self.offer_salary - self.salary_step >= 0:
            self.offer_salary -= self.salary_step

    def increase_transfer(self):
        if self.offer_transfer + self.transfer_step <= self.state.transfer_budget:
            self.offer_transfer += self.transfer_step

    def decrease_transfer(self):
        if self.offer_transfer - self.transfer_step >= 0:
            self.offer_transfer -= self.transfer_step

    def toggle_incentive(self, idx):
        if idx in self.selected_incentives:
            self.selected_incentives.discard(idx)
        else:
            if len(self.selected_incentives) >= 3:
                return
            self.selected_incentives.add(idx)

    def total_incentive_pct(self):
        inc_list = get_incentive_list(self.player)
        total = sum(incentive_pct(inc_list[i], self.curr_stats)
                    for i in self.selected_incentives if i < len(inc_list))
        return min(total, 0.25)

    def _get_effective(self):
        return calc_effective_offer(
            self.player,
            self.offer_salary,
            self.offer_transfer,
            self.selected_incentives,
            self.curr_stats
        )

    def make_offer(self):
        exp       = expected_salary(self.player, self.curr_stats)
        effective = self._get_effective()
        if effective >= exp:
            self.offer_result = "accept"
            self.offer_button.text   = "CONFIRM"
            self.offer_button.action = self.confirm_contract
        else:
            self.offer_result = "reject"

    def confirm_contract(self):
        y, m, d = self.state.base_date
        current_date_obj = date(y, m, d) + timedelta(days=self.state.current_day - 1)
        begin    = current_date_obj.strftime("%Y-%m-%d")
        end_year = current_date_obj.year + 1  # 1년 고정
        end      = f"{end_year}-12-31"

        self.player.contract["begin"]  = begin
        self.player.contract["end"]    = end
        self.player.contract["salary"] = self.offer_salary

        inc_list = get_incentive_list(self.player)
        self.player.contract["incentives"] = [
            {"label": inc_list[i][0], "pct": incentive_pct(inc_list[i], self.curr_stats)}
            for i in sorted(self.selected_incentives) if i < len(inc_list)
        ]
        return "player_detail"

    # ── draw ──────────────────────────────────────────────

    def draw(self, screen):
        screen.fill((20, 20, 20))

        left  = self.left
        mid   = self.mid
        right = self.right

        for rect, fc, bc in [
            (left,  (215, 215, 215), (140, 140, 140)),
            (mid,   (215, 215, 215), (140, 140, 140)),
            (right, (210, 215, 210), (140, 145, 140)),
        ]:
            pygame.draw.rect(screen, fc, rect)
            pygame.draw.rect(screen, bc, rect, 2)

        def fmt(val):
            if abs(val) >= 1_000_000: return f"${val/1_000_000:.2f}M"
            if abs(val) >= 1_000:     return f"${val/1_000:.1f}k"
            return f"${val:,}"

        # ── LEFT: 현재 계약 & 예산 ──────────────────────────
        screen.blit(self.FONT.render("CURRENT CONTRACT", True, black),
                    (left.x + 15, left.y + 15))

        begin      = self.player.contract.get("begin", "-")
        end        = self.player.contract.get("end",   "-")
        salary     = self.player.salary()
        years_left = self.player.contract_years_left()

        for i, (lbl, val) in enumerate([
            ("Period",     f"{begin}"),
            ("",           f"~ {end}"),
            ("Salary",     fmt(salary)),
            ("Years Left", f"{years_left} yrs"),
        ]):
            if lbl:
                screen.blit(self.SMALL.render(lbl, True, (100, 100, 100)),
                            (left.x + 15, left.y + 55 + i * 38))
            screen.blit(self.FONT.render(val, True, black),
                        (left.x + 15, left.y + 72 + i * 38))

        pygame.draw.line(screen, (180, 180, 180),
                         (left.x + 10, left.y + 220), (left.right - 10, left.y + 220), 1)

        screen.blit(self.FONT.render("BUDGET", True, black), (left.x + 15, left.y + 230))

        current_wage = self.get_current_wage_total()
        rem_transfer = self.state.transfer_budget
        rem_wage     = self.state.wage_budget - current_wage

        adj = calc_salary_adjustment(self.player, self.curr_stats)
        exp = expected_salary(self.player, self.curr_stats)
        fa_label = "  [FA]" if self.player.is_free_agent() else ""

        for i, (lbl, val, color) in enumerate([
            ("Remaining Transfer", fmt(rem_transfer),   black),
            ("Remaining Wage",     fmt(rem_wage),        black),
            ("Expected Salary",    fmt(exp) + fa_label,  (180, 60, 60)),
            ("Adj Rate",           f"{adj*100:+.0f}%",
             (60, 160, 60) if adj >= 0 else (180, 60, 60)),
        ]):
            screen.blit(self.SMALL.render(lbl, True, (100, 100, 100)),
                        (left.x + 15, left.y + 265 + i * 60))
            screen.blit(self.FONT.render(val, True, color),
                        (left.x + 15, left.y + 283 + i * 60))

        # ── MID: 오퍼 조건 ──────────────────────────────────
        screen.blit(self.FONT.render("CONTRACT OFFER", True, black),
                    (mid.x + 15, mid.y + 15))

        # 계약 기간 (1년 고정)
        screen.blit(self.SMALL.render("Contract Length", True, (100, 100, 100)),
                    (mid.x + 20, mid.y + 60))
        screen.blit(self.FONT.render("1 year", True, black),
                    (mid.x + 20, mid.y + 78))

        # 연봉
        screen.blit(self.SMALL.render("Annual Salary", True, (100, 100, 100)),
                    (mid.x + 20, mid.y + 130))
        screen.blit(self.FONT.render(fmt(self.offer_salary), True, black),
                    (mid.x + 20, mid.y + 148))

        # 계약금 (FA일 때만 활성)
        is_fa = self.player.is_free_agent()
        transfer_color = black if is_fa else (160, 160, 160)
        screen.blit(self.SMALL.render(
            "Signing Bonus" + ("" if is_fa else "  (re-sign only)"),
            True, (100, 100, 100)),
            (mid.x + 20, mid.y + 190))
        screen.blit(self.FONT.render(fmt(self.offer_transfer), True, transfer_color),
                    (mid.x + 20, mid.y + 208))

        pygame.draw.line(screen, (180, 180, 180),
                         (mid.x + 10, mid.y + 255), (mid.right - 10, mid.y + 255), 1)

        # 인센티브 선택 섹션
        screen.blit(self.FONT.render("INCENTIVES", True, black),
                    (mid.x + 15, mid.y + 265))

        inc_pct_total = self.total_incentive_pct()
        cap_color = (180, 60, 60) if inc_pct_total >= 0.25 else (60, 130, 60)
        screen.blit(self.SMALL.render(
            f"Selected: {len(self.selected_incentives)}/3  |  "
            f"Total: {inc_pct_total*100:.0f}% (cap 25%)",
            True, cap_color),
            (mid.x + 15, mid.y + 290))

        inc_list = get_incentive_list(self.player)
        for i, inc_def in enumerate(inc_list):
            label, key, thresholds, condition = inc_def
            selected = i in self.selected_incentives
            row_y    = mid.y + 315 + i * 22

            bg_color = (180, 220, 180) if selected else (230, 230, 230)
            pygame.draw.rect(screen, bg_color, (mid.x + 10, row_y - 1, mid.width - 20, 20))

            screen.blit(self.TINY.render(label, True, black), (mid.x + 14, row_y + 1))

            thresh_x = mid.x + 75
            for thresh, grade, pct in thresholds:
                grade_surf = self.TINY.render(
                    f"{thresh}({grade})", True, GRADE_COLOR[grade])
                screen.blit(grade_surf, (thresh_x, row_y + 1))
                thresh_x += 58

            if condition:
                cond_key, cond_val = condition
                screen.blit(self.TINY.render(f"*{cond_val}+{cond_key}",
                    True, (130, 80, 0)), (mid.right - 65, row_y + 1))

        # ── 감정 바 + 에이전트 코멘트 ──────────────────────
        effective = self._get_effective()
        draw_mood_bar(
            screen, self.FONT, self.SMALL,
            effective, exp,
            x=mid.x + 15,
            y=mid.y - 60,
            width=mid.width - 30
        )

        # 오퍼 결과
        if self.offer_result == "accept":
            screen.blit(self.FONT.render("✓ PLAYER ACCEPTS", True, (0, 140, 0)),
                        (mid.x + 20, mid.y + 468))
        elif self.offer_result == "reject":
            screen.blit(self.FONT.render("✗ PLAYER REJECTS", True, (180, 0, 0)),
                        (mid.x + 20, mid.y + 468))

        # ── RIGHT: 능력치 + 시즌 성적 ───────────────────────
        screen.blit(self.FONT.render(self.player.name, True, black),
                    (right.x + 15, right.y + 15))

        attrs = (["contact", "power", "eye", "run", "defense"]
                 if self.player.is_batter()
                 else ["velocity", "control", "stuff", "stamina", "defense"])

        for i, attr in enumerate(attrs):
            if attr in self.player.attr:
                cur = self.player.get_attr(attr)
                pot = self.player.get_pot(attr)
                screen.blit(self.SMALL.render(
                    f"{attr.upper()}: {cur}/{pot}", True, black),
                    (right.x + 15, right.y + 55 + i * 28))

        pygame.draw.line(screen, (180, 180, 180),
                         (right.x + 10, right.y + 205), (right.right - 10, right.y + 205), 1)

        s = self.curr_stats
        screen.blit(self.FONT.render("LIVE STATS", True, black),
                    (right.x + 15, right.y + 215))

        if s:
            if self.player.is_batter():
                ab  = s.get("ab", 0)
                ops = s.get("ops", s.get("obp", 0) + s.get("slg", 0))
                avg = s.get("h", 0) / ab if ab > 0 else 0
                live_data = [
                    ("G / AB",    f"{s.get('g',0)} / {ab}"),
                    ("H / HR",    f"{s.get('h',0)} / {s.get('hr',0)}"),
                    ("RBI / SB",  f"{s.get('rbi',0)} / {s.get('sb',0)}"),
                    ("BB / SO",   f"{s.get('bb',0)} / {s.get('so',0)}"),
                    ("AVG",       f"{avg:.3f}"),
                    ("OBP / SLG", f"{s.get('obp',0):.3f} / {s.get('slg',0):.3f}"),
                    ("OPS",       f"{ops:.3f}"),
                ]
            else:
                live_data = [
                    ("W - L",    f"{s.get('w',0)} - {s.get('l',0)}"),
                    ("ERA",      f"{s.get('era',0.0):.2f}"),
                    ("G / IP",   f"{s.get('g',0)} / {s.get('ip',0.0):.1f}"),
                    ("H / BB",   f"{s.get('h_allowed',0)} / {s.get('bb_allowed',0)}"),
                    ("SO",       f"{s.get('so',0)}"),
                    ("WHIP",     f"{s.get('whip',0.0):.2f}"),
                    ("HLD / SV", f"{s.get('hld',0)} / {s.get('sv',0)}"),
                ]
            for i, (lbl, val) in enumerate(live_data):
                screen.blit(self.SMALL.render(lbl, True, (100, 100, 100)),
                            (right.x + 15, right.y + 248 + i * 36))
                screen.blit(self.FONT.render(val, True, black),
                            (right.x + 160, right.y + 246 + i * 36))
        else:
            screen.blit(self.FONT.render("No live data", True, (160, 160, 160)),
                        (right.x + 15, right.y + 260))

        for btn in self.buttons:
            btn.draw(screen)

    # ── update ────────────────────────────────────────────

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update_hover(mouse_pos)

        inc_list = get_incentive_list(self.player)

        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for i in range(len(inc_list)):
                    row_y    = self.mid.y + 315 + i * 22
                    row_rect = pygame.Rect(self.mid.x + 10, row_y - 1, self.mid.width - 20, 20)
                    if row_rect.collidepoint(e.pos):
                        self.toggle_incentive(i)
                        break
                for btn in self.buttons:
                    res = btn.handle_event(e)
                    if res:
                        return res

        return None