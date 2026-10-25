"""경기 화면 연출 모듈: 스트라이크존 투구 표시, 결과 배너/파티클, 투구 로그, 승리확률 그래프.

화면 연출에만 쓰이며 경기 판정에는 영향을 주지 않는다. 연출용 난수는 별도 RNG를 써서
경기 시뮬레이션의 난수열(시드 재현성, 학습 환경)을 건드리지 않는다.
"""
import math
import random

import pygame

# ── 색 ─────────────────────────────────────────────────────
PANEL_BG = (28, 30, 38)
PANEL_LINE = (90, 96, 110)
TXT = (225, 225, 225)
TXT_DIM = (150, 155, 165)
C_STRIKE = (235, 80, 80)      # 루킹 스트라이크
C_BALL = (90, 205, 110)       # 볼
C_MISS = (245, 215, 70)       # 헛스윙
C_INPLAY = (100, 165, 255)    # 인플레이

# 구종: (이름, 구속 보정 km/h, 가로 변화, 세로 변화)  — 변화량은 존 좌표 단위(존 가장자리=±1)
PITCH_KINDS = {
    "FB": ("직구", 0, 0.0, -0.05),
    "SL": ("슬라이더", -10, 0.45, 0.12),
    "CB": ("커브", -22, 0.18, 0.60),
    "CH": ("체인지업", -13, -0.25, 0.30),
}

# 이닝 남은 기대 득점 (주자 000,100,010,110,001,101,011,111 / 아웃 0,1,2)
_RE = [
    [0.50, 0.90, 1.10, 1.45, 1.35, 1.75, 1.95, 2.30],
    [0.27, 0.54, 0.68, 0.95, 0.95, 1.20, 1.40, 1.65],
    [0.10, 0.23, 0.32, 0.45, 0.35, 0.52, 0.60, 0.80],
]


def _norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def win_probability(my_score, opp_score, inning, half, outs, bases):
    """내 팀의 승리확률 (0~1). 점수차 + 남은 이닝 + 현재 주자/아웃 상황의 기대 득점."""
    outs = min(2, outs)
    state = (1 if bases[0] else 0) + (2 if bases[1] else 0) + (4 if bases[2] else 0)
    re = _RE[outs][state]
    cur_frac = (3 - outs) / 3.0
    if inning < 9:
        full_after = (9 - inning) * 2 + (1 if half == "TOP" else 0)
    else:
        full_after = 0 if half == "TOP" else -1       # 9회 TOP은 BOT가 남음, 9회 BOT/연장은 현재가 마지막
        full_after = max(full_after, 1 if half == "TOP" else 0)
    rem = max(0.35, full_after + cur_frac)
    sd = math.sqrt(rem * 1.3)
    batting_mine = (half == "BOT")
    diff = my_score - opp_score + (re if batting_mine else -re)
    return _norm_cdf(diff / sd)


class GameFX:
    ZONE_RECT = pygame.Rect(1068, 408, 197, 188)
    WP_RECT = pygame.Rect(380, 208, 680, 54)
    LOG_RECT = pygame.Rect(50, 606, 300, 108)

    def __init__(self, font_small, font_tiny, font_big):
        self.rng = random.Random()
        self.fs, self.ft, self.fb = font_small, font_tiny, font_big
        self.pitch_counts = {}          # id(투수) → 투구수
        self.pa_pitches = []            # 이번 타석 투구 [{loc,type,kind,speed,swing}]
        self._pa_done = False           # 타석이 끝났으면 다음 투구 때 점을 지운다
        self.cur = None                 # 현재(마지막) 투구
        self.log = []                   # 최근 투구 로그
        self.banners = []               # 결과 배너
        self.floats = []                # 떠오르는 텍스트
        self.particles = []
        self.flash = 0
        self.wp_hist = []               # [(wp, scored_flag)]
        self._wp_sig = None
        self._last_score = (0, 0)

    # ── 투구 생성 ─────────────────────────────────────────
    def begin_pitch(self, result, pitcher):
        r = self.rng
        if self._pa_done:
            self.pa_pitches = []
            self._pa_done = False
        typ = result["type"]
        if typ == "STRIKE":
            x, y = self._inside(0.58)
        elif typ == "BALL":
            x, y = self._outside()
        elif typ == "SWING_MISS":
            x, y = self._edge()
        else:
            x, y = self._inside(0.5)

        vel = 80
        stuff = 65
        try:
            vel = pitcher.get_attr("velocity")
            stuff = pitcher.get_attr("stuff")
        except Exception:
            pass
        w = [("FB", 46), ("SL", 18 + max(0, stuff - 60) * 0.3), ("CB", 12 + max(0, stuff - 60) * 0.2), ("CH", 16)]
        kind = r.choices([k for k, _ in w], [x_ for _, x_ in w])[0]
        name, dv, bx, by = PITCH_KINDS[kind]
        flip = 1 if (hash(getattr(pitcher, "name", "")) & 1) else -1   # 투수별 변화 방향 고정
        speed = int(95 + vel * 0.68 + dv + r.gauss(0, 1.6))
        self.pitch_counts[id(pitcher)] = self.pitch_counts.get(id(pitcher), 0) + 1
        self.cur = {"loc": (x, y), "type": typ, "kind": name, "speed": speed,
                    "brk": (bx * flip, by), "swing": typ in ("SWING_MISS", "IN_PLAY"),
                    "n": len(self.pa_pitches) + 1, "landed": False}

    def _inside(self, sd):
        r = self.rng
        return (max(-0.92, min(0.92, r.gauss(0, sd))), max(-0.92, min(0.92, r.gauss(0, sd))))

    def _outside(self):
        r = self.rng
        while True:
            x, y = r.uniform(-1.75, 1.75), r.uniform(-1.15, 1.2)
            if max(abs(x), abs(y)) > 1.12:
                return (x, y)

    def _edge(self):
        r = self.rng
        while True:
            x, y = r.gauss(0, 0.8), r.gauss(0.35, 0.8)
            if 0.55 < max(abs(x), abs(y)) < 1.5 and -1.15 <= y <= 1.2:
                return (x, y)

    def pitch_landed(self, typ):
        """투구가 포수 미트에 도착했을 때(결과 확정) 호출."""
        if not self.cur or self.cur["landed"]:
            return
        self.cur["landed"] = True
        self.pa_pitches.append(self.cur)
        label = {"STRIKE": "스트라이크", "BALL": "볼", "SWING_MISS": "헛스윙", "IN_PLAY": "타격"}[typ]
        col = {"STRIKE": C_STRIKE, "BALL": C_BALL, "SWING_MISS": C_MISS, "IN_PLAY": C_INPLAY}[typ]
        self.log.append({"kind": self.cur["kind"], "speed": self.cur["speed"], "res": label, "col": col})
        self.log = self.log[-4:]
        self.cur["res"], self.cur["res_col"] = label, col

    def clear_pa(self):
        self._pa_done = True

    # ── 결과 이펙트 ───────────────────────────────────────
    def banner(self, text, color, sub="", life=95):
        self.banners = [{"text": text, "color": color, "sub": sub, "life": life, "max": life}]

    def float_text(self, text, color, pos, life=48):
        self.floats.append({"text": text, "color": color, "x": pos[0], "y": pos[1], "life": life, "max": life})

    def burst(self, pos, n=110):
        for _ in range(n):
            a = self.rng.uniform(0, math.tau)
            s = self.rng.uniform(1.5, 6.5)
            self.particles.append({"x": pos[0], "y": pos[1], "vx": math.cos(a) * s, "vy": math.sin(a) * s - 2.0,
                                   "life": self.rng.randint(40, 85),
                                   "col": self.rng.choice([(255, 215, 80), (255, 120, 80), (120, 220, 255), (255, 255, 255)])})
        self.flash = 14

    @staticmethod
    def exit_info(batted):
        """타구 파라미터 → (타구속도 km/h, 비거리 m 또는 None) 연출용 환산."""
        if batted["trajectory"] == "FLY":
            v = 100 + 55 * (batted.get("fly_speed", 1.2) - 0.9) / 1.1
            return int(v), int(batted["dist"] * 1.22)
        v = 70 + 70 * (batted["speed"] - 0.55) / 1.85
        return int(v), None

    def play_result(self, final, batted, rbi_runs, is_dp, fence_pos):
        """인플레이 최종 결과 배너. final: OUT/1B/2B/3B/HR"""
        sub = ""
        if batted:
            v, d = self.exit_info(batted)
            sub = f"타구속도 {v}km/h" + (f" · 비거리 {d}m" if d else "")
        if final == "HR":
            self.banner("홈  런 !!", (255, 215, 70), sub, 130)
            if fence_pos:
                self.burst(fence_pos)
        elif final == "3B":
            self.banner("3루타!", (255, 170, 60), sub)
        elif final == "2B":
            self.banner("2루타!", (255, 200, 80), sub)
        elif final == "1B":
            self.banner("안  타", (120, 210, 255), sub)
        else:
            if is_dp:
                txt = "병살타"
            elif batted and batted["trajectory"] == "FLY":
                txt = "플라이 아웃" + ("  (희생플라이)" if rbi_runs else "")
            else:
                txt = "땅볼 아웃"
            self.banner(txt, (190, 190, 200), sub, 75)
        if log_entry := (self.log[-1] if self.log else None):
            log_entry["res"] = {"OUT": "아웃", "1B": "안타", "2B": "2루타", "3B": "3루타", "HR": "홈런"}[final]
            log_entry["col"] = (200, 200, 205) if final == "OUT" else (255, 215, 90)

    # ── 승리확률 ──────────────────────────────────────────
    def sample_wp(self, scene):
        sig = (scene.my_score, scene.opp_score, scene.inning, scene.half, scene.out, tuple(bool(b) for b in scene.bases))
        if sig == self._wp_sig:
            return
        self._wp_sig = sig
        if scene.is_game_over:
            wp = 1.0 if scene.my_score > scene.opp_score else (0.0 if scene.my_score < scene.opp_score else 0.5)
        else:
            wp = win_probability(scene.my_score, scene.opp_score, scene.inning, scene.half, scene.out, scene.bases)
        scored = (scene.my_score, scene.opp_score) != self._last_score
        self._last_score = (scene.my_score, scene.opp_score)
        self.wp_hist.append((wp, scored))

    # ── 그리기 ────────────────────────────────────────────
    def _panel(self, screen, rect, title):
        pygame.draw.rect(screen, PANEL_BG, rect, border_radius=6)
        pygame.draw.rect(screen, PANEL_LINE, rect, 1, border_radius=6)
        screen.blit(self.ft.render(title, True, TXT_DIM), (rect.x + 8, rect.y + 5))

    def _zone_px(self, loc, zr):
        """존 좌표(-1..1) → 화면 좌표. zr: 스트라이크존 Rect"""
        return (zr.centerx + loc[0] * zr.w / 2, zr.centery + loc[1] * zr.h / 2)

    def draw_zone(self, screen, scene):
        R = self.ZONE_RECT
        self._panel(screen, R, "투구 (포수 시점)")
        outer = pygame.Rect(0, 0, 128, 134)
        outer.midtop = (R.centerx, R.y + 24)
        zr = outer.inflate(-44, -34)                       # 스트라이크존 84x100
        pygame.draw.rect(screen, (38, 41, 52), outer, border_radius=4)
        pygame.draw.rect(screen, (46, 50, 63), zr)
        for i in (1, 2):
            pygame.draw.line(screen, (80, 86, 100), (zr.x + zr.w * i // 3, zr.y), (zr.x + zr.w * i // 3, zr.bottom), 1)
            pygame.draw.line(screen, (80, 86, 100), (zr.x, zr.y + zr.h * i // 3), (zr.right, zr.y + zr.h * i // 3), 1)
        pygame.draw.rect(screen, (170, 175, 190), zr, 2)
        # 이번 타석의 투구 점
        for p in self.pa_pitches:
            cx, cy = self._zone_px(p["loc"], zr)
            col = {"STRIKE": C_STRIKE, "BALL": C_BALL, "SWING_MISS": C_MISS, "IN_PLAY": C_INPLAY}[p["type"]]
            pygame.draw.circle(screen, col, (int(cx), int(cy)), 8)
            pygame.draw.circle(screen, (20, 20, 20), (int(cx), int(cy)), 8, 1)
            t = self.ft.render(str(p["n"]), True, (15, 15, 15))
            screen.blit(t, (cx - t.get_width() / 2, cy - t.get_height() / 2))

        # 날아가는 공 (릴리스 → 도착, 구종별 변화 + 잔상)
        c = self.cur
        if c and scene.pitch_sim and not c["landed"]:
            ps = scene.pitch_sim
            total = math.dist(ps.PITCHER_POS, ps.HOME_POS)
            t = 1.0 - math.dist(ps.ball_pos, ps.HOME_POS) / total if ps.state == "PITCHING" else 1.0
            t = max(0.0, min(1.0, t))
            start = (0.0, -1.25)
            bx, by = c["brk"]
            for k in range(5, -1, -1):
                tt = max(0.0, t - k * 0.045)
                off = 1 - tt * tt
                lx = start[0] + (c["loc"][0] - start[0]) * tt + bx * off * 1.4
                ly = start[1] + (c["loc"][1] - start[1]) * tt + by * off * 1.4
                cx, cy = self._zone_px((lx, ly), zr)
                pygame.draw.circle(screen, (255, 255, 255) if k == 0 else (110, 112, 125),
                                   (int(cx), int(cy)), max(1, int(2 + 6 * tt - k * 0.5)))
            if c["swing"] and t > 0.8:                      # 스윙 궤적
                ex, ey = self._zone_px(c["loc"], zr)
                s_ = (t - 0.8) / 0.2
                pygame.draw.arc(screen, (240, 200, 120), pygame.Rect(ex - 40, ey - 14, 80, 28), math.pi * (1 - s_), math.pi, 3)

        # 하단: 구종/구속 + 결과
        if c:
            screen.blit(self.ft.render(f"{c['kind']} {c['speed']}km/h", True, TXT), (R.x + 8, R.bottom - 22))
            if c.get("res"):
                t = self.ft.render(c["res"], True, c["res_col"])
                screen.blit(t, (R.right - 8 - t.get_width(), R.bottom - 22))

    def draw_log(self, screen, scene):
        R = self.LOG_RECT
        self._panel(screen, R, "최근 투구")
        y = R.y + 24
        for e in self.log[-4:]:
            screen.blit(self.ft.render(f"{e['kind']} {e['speed']}", True, TXT_DIM), (R.x + 10, y))
            pygame.draw.circle(screen, e["col"], (R.x + 130, y + 8), 5)
            screen.blit(self.ft.render(e["res"], True, e["col"]), (R.x + 142, y))
            y += 20

    def draw_wp(self, screen, scene):
        R = self.WP_RECT
        pygame.draw.rect(screen, PANEL_BG, R, border_radius=6)
        pygame.draw.rect(screen, PANEL_LINE, R, 1, border_radius=6)
        gr = pygame.Rect(R.x + 8, R.y + 6, R.w - 160, R.h - 12)
        pygame.draw.rect(screen, (22, 24, 30), gr)
        pygame.draw.line(screen, (70, 75, 88), (gr.x, gr.centery), (gr.right, gr.centery), 1)
        h = self.wp_hist
        if len(h) >= 2:
            n = len(h)
            pts = [(gr.x + gr.w * i / (n - 1), gr.bottom - gr.h * wp) for i, (wp, _) in enumerate(h)]
            fill = pts + [(pts[-1][0], gr.centery), (pts[0][0], gr.centery)]
            surf = pygame.Surface((gr.w + 4, gr.h + 4), pygame.SRCALPHA)
            pygame.draw.polygon(surf, (90, 200, 120, 55), [(x - gr.x, y - gr.y) for x, y in fill])
            screen.blit(surf, gr.topleft)
            pygame.draw.lines(screen, (120, 230, 150), False, pts, 2)
            for (x, y), (_, sc) in zip(pts, h):
                if sc:
                    pygame.draw.circle(screen, (255, 215, 80), (int(x), int(y)), 3)
        wp = h[-1][0] if h else 0.5
        x0 = gr.right + 12
        screen.blit(self.ft.render("승리확률", True, TXT_DIM), (x0, R.y + 4))
        screen.blit(self.ft.render(f"{scene.state.user_team} {wp * 100:.0f}%", True,
                                   (120, 230, 150) if wp >= 0.5 else (240, 130, 130)), (x0, R.y + 20))
        screen.blit(self.ft.render(f"{scene.opponent_team} {(1 - wp) * 100:.0f}%", True, TXT_DIM), (x0, R.y + 36))

    def draw_effects(self, screen, scene):
        # 파티클
        alive = []
        for p in self.particles:
            p["x"] += p["vx"]; p["y"] += p["vy"]; p["vy"] += 0.16; p["life"] -= 1
            if p["life"] > 0:
                alive.append(p)
                pygame.draw.circle(screen, p["col"], (int(p["x"]), int(p["y"])), 3 if p["life"] > 20 else 2)
        self.particles = alive
        if self.flash > 0:
            ov = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            ov.fill((255, 235, 170, int(32 * self.flash / 14)))
            screen.blit(ov, (0, 0))
            self.flash -= 1
        # 배너
        for b in self.banners:
            b["life"] -= 1
            age = b["max"] - b["life"]
            pop = min(1.0, age / 8.0)
            scale = 0.6 + 0.4 * (1 - (1 - pop) ** 2) + (0.04 if age < 14 else 0)
            alpha = 255 if b["life"] > 25 else int(255 * b["life"] / 25)
            surf = self.fb.render(b["text"], True, b["color"])
            shadow = self.fb.render(b["text"], True, (0, 0, 0))
            w, h = int(surf.get_width() * scale), int(surf.get_height() * scale)
            surf = pygame.transform.smoothscale(surf, (max(1, w), max(1, h)))
            shadow = pygame.transform.smoothscale(shadow, (max(1, w), max(1, h)))
            surf.set_alpha(alpha); shadow.set_alpha(alpha)
            cx, cy = 725, 296
            screen.blit(shadow, (cx - w // 2 + 3, cy - h // 2 + 3))
            screen.blit(surf, (cx - w // 2, cy - h // 2))
            if b["sub"]:
                s = self.fs.render(b["sub"], True, (235, 235, 240))
                s.set_alpha(alpha)
                screen.blit(s, (cx - s.get_width() // 2, cy + h // 2 + 2))
        self.banners = [b for b in self.banners if b["life"] > 0]
        # 떠오르는 텍스트
        for f in self.floats:
            f["life"] -= 1
            f["y"] -= 0.5
            a = int(255 * min(1.0, f["life"] / 18))
            t = self.fs.render(f["text"], True, f["color"])
            t.set_alpha(a)
            screen.blit(t, (f["x"] - t.get_width() // 2, f["y"]))
        self.floats = [f for f in self.floats if f["life"] > 0]
