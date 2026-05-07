from asyncio import events

from models import player
from scenes.base_scene import Scene
from ui.button import Button
from config import *
import pygame, random, math
from simulation import PitchSim, FieldSim

# ════════════════════════════════════════════════════════
#  화면 좌표 변환 헬퍼
#
#  Simulation 좌표 (정사각형):
#    HOME=[0,0]  1B=[30,0]  2B=[30,30]  3B=[0,30]
#
#  화면 배치 (마름모 / 실제 야구장):
#         2루 (위)
#    3루       1루
#         홈  (아래)
#         포수 (더 아래)
#
#  변환 공식:
#    screen_x = OX + (sx - sy) * S
#    screen_y = OY + (-(sx + sy - 30)) * S
#    → HOME(0,0):  x'=0,  y'=+30 → (OX,        OY+30*S)  하단
#    → 1B(30,0):   x'=+30, y'=0  → (OX+30*S,   OY)       오른쪽 중간
#    → 2B(30,30):  x'=0,  y'=-30 → (OX,        OY-30*S)  상단
#    → 3B(0,30):   x'=-30, y'=0  → (OX-30*S,   OY)       왼쪽 중간
# ════════════════════════════════════════════════════════

# 중앙 상자: [400, 220, 650, 470]
# 1루↔3루 가로폭 = 2 * 30 * S,  홈↔2루 세로폭 = 2 * 30 * S
# S=6.5 → 내야폭 390px, 중앙 기준점(OX,OY) = 상자 가로중심, 상하중심
_SIM_OX = 725   # 마름모 중심 x
_SIM_OY = 520   # 마름모 중심 y
_SIM_S  = 5.0   # 1유닛 = 5.0px (내야 한 변 30유닛 → 212px)




def sim_to_screen(sx, sy):
    """Simulation 좌표 → 화면 픽셀 좌표 (마름모 변환)
    HOME(0,0)은 하단, 2B(30,30)은 상단, 1B 오른쪽, 3B 왼쪽.
    """
    xr =  (sx - sy)           # 회전된 x
    yr = -(sx + sy - 30)      # 회전된 y (+30 오프셋: 중심이 마름모 정중앙)
    return (int(_SIM_OX + xr * _SIM_S),
            int(_SIM_OY + yr * _SIM_S))

def draw_radar_chart_game(surface, player, cx, cy, radius=28):
        """
        오각형 레이더 차트를 그립니다.
        cx, cy: 차트 중심 좌표
        radius: 최대값(100) 기준 반지름
        """
        if player.is_pitcher():
            keys   = ["velocity", "control", "stamina", "stuff", "defense"]
            labels = ["VEL", "CON", "STA", "STF", "DEF"]
            color  = (100, 180, 255)   # 파란 계열
        else:
            keys   = ["contact", "power", "eye", "run", "defense"]
            labels = ["CTC", "POW", "EYE", "RUN", "DEF"]
            color  = (100, 255, 160)   # 초록 계열

    

        n = len(keys)
    # 각도: 위쪽(-90도)부터 시계방향
        angles = [math.radians(-90 + i * 360 / n) for i in range(n)]
        label_font = pygame.font.SysFont(None, 16)

    # 배경 오각형 (최대값 기준)
        bg_pts = [(cx + radius * math.cos(a), cy + radius * math.sin(a)) for a in angles]
        pygame.draw.polygon(surface, (50, 50, 60), bg_pts)
        pygame.draw.polygon(surface, (80, 80, 90), bg_pts, 1)

        label_inset = radius * 0.6
        for label, angle in zip(labels, angles):
            lx = cx + label_inset * math.cos(angle)
            ly = cy + label_inset * math.sin(angle)
            label_surf = label_font.render(label, True, (180, 180, 180))
            surface.blit(label_surf, (lx - label_surf.get_width() // 2, ly - label_surf.get_height() // 2))

   
    # 능력치 오각형
        vals = []
        for k in keys:
            if k in player.attr:
                vals.append(player.get_attr(k))
            else:
                vals.append(0)

        stat_pts = [
            (cx + (v / 100) * radius * math.cos(a),
            cy + (v / 100) * radius * math.sin(a))
            for v, a in zip(vals, angles)
        ]
        # 반투명 채우기
        stat_surf = pygame.Surface((radius * 2 + 10, radius * 2 + 10), pygame.SRCALPHA)
        offset = radius + 5
        local_pts = [(p[0] - cx + offset, p[1] - cy + offset) for p in stat_pts]
        pygame.draw.polygon(stat_surf, (*color, 80), local_pts)
        pygame.draw.polygon(stat_surf, (*color, 220), local_pts, 1)
        surface.blit(stat_surf, (cx - offset, cy - offset))

    # 꼭짓점 점
        for pt in stat_pts:
            pygame.draw.circle(surface, color, (int(pt[0]), int(pt[1])), 2)



        label_offset = radius + 1  # 꼭짓점에서 얼마나 더 바깥에 쓸지
        for i, (label, val, angle) in enumerate(zip(labels, vals, angles)):
            lx = cx + label_offset * math.cos(angle)
            ly = cy + label_offset * math.sin(angle)

            text = f"{val}"
            surf = label_font.render(text, True, color)

        # 각도에 따라 텍스트 정렬 (왼쪽/오른쪽/가운데)
            cos_a = math.cos(angle)
            if cos_a > 0.3:        # 오른쪽
                tx = lx
            elif cos_a < -0.3:     # 왼쪽
                tx = lx - surf.get_width()
            else:                  # 위/아래 중앙
                tx = lx - surf.get_width() // 2

            sin_a = math.sin(angle)
            if sin_a < -0.3:       # 위
                ty = ly - surf.get_height()
            else:                  # 아래 or 옆
                ty = ly - surf.get_height() // 2

            surface.blit(surf, (tx, ty))


class GameScene(Scene):
    def __init__(self, players, state):
        self.players = players
        self.state = state
        
        date_str = state.get_current_date_str()
        self.opponent_team = state.schedule[date_str]["opponent"]
        opp_players = state.team_rosters[self.opponent_team]

        self.opp_lineup, self.opp_order = self.make_ai_lineup(opp_players)
        
        self.FONT = pygame.font.SysFont("malgungothic", 30)
        self.smallFONT = pygame.font.SysFont("malgungothic", 24)
        self.verysmallFONT = pygame.font.SysFont("malgungothic", 16)
        
        self.my_lineup = state.lineup
        self.my_order = state.batting_order
        
        self.inning = 1
        self.half = "TOP"
        
        self.strike = 0
        self.ball = 0
        self.out = 0
        
        self.my_score = 0
        self.opp_score = 0

        self.my_bat_idx = 0
        self.opp_bat_idx = 0
        
        self.my_hit = 0
        self.opp_hit = 0

        self.bases = [None, None, None]  # 1루, 2루, 3루
        self.last_event = ""
        
        self.my_inning_runs = [0] * 12
        self.opp_inning_runs = [0] * 12
        
        self.is_game_over = False
        self.game_result = None
        
        self.pitchers_used = [self.my_lineup["P"]]
        self.opp_pitchers_used = [self.opp_lineup["P"]]

        self.instant_btn = Button((1100, 650, 100, 40), "Finish", self.simulate_to_end)
        
        for p in self.my_order + self.opp_order + self.pitchers_used + self.state.bullpen + ([self.opp_lineup["P"]] if self.opp_lineup.get("P") else []):
            if p:
                p.reset_game_stats()
                p.game_stats = {
                "ab": 0, "h": 0, "2b": 0, "3b": 0, "hr": 0, "rbi": 0, "bb": 0, "so": 0, "sb": 0,
                "ip_outs": 0, "h_allowed": 0, "r_allowed": 0, "er": 0,
                "so_p": 0, "bb_p": 0, "is_win": False, "is_loss": False,
                "is_save": False, "is_hold": False, "entry_score_diff": 0,
                "entry_runners": 0, "quit_score_diff": 0,
                }
        self.starter = self.my_lineup["P"]
        self.finisher = None

        self.oppstarter = self.opp_lineup["P"]
        self.oppfinisher = None
        
        self.win_candidates = {
            "my": None,
            "opp": None
        }
        
        self.show_bullpen = False
        self.bullpen_btns = []
    
        self.change_p_btn = Button((1100, 600, 100, 40), "Bullpen", self.toggle_bullpen)
        
        self.winning_pitcher = None
        self.losing_pitcher = None

        self.opp_bullpen = [
            p for p in opp_players
            if p.pos == "P" and p != self.opp_lineup["P"]
        ]

        # ── 시뮬레이션 상태 ──────────────────────────────────
        self.pitch_sim  = None   # PitchSim 인스턴스
        self.field_sim  = None   # FieldSim 인스턴스

        # 투구 결과 + 처리에 필요한 pending 데이터
        self._pending_result  = None
        self._pending_batter  = None
        self._pending_pitcher = None
        self._pending_my_team = None
        self._pending_walk    = False

    def staff_trait_bonus(self, role, trait_name):
        staff = getattr(self.state, "staff_slots", {}).get(role)
        if not staff or not hasattr(staff, "get_trait_bonus"):
            return 0
        return staff.get_trait_bonus(trait_name)

    def apply_game_fatigue_staff_bonus(self, player, fatigue_inc):
        if player.team != self.state.user_team:
            return fatigue_inc

        bonus = self.staff_trait_bonus("HD", "game_fatigue_reduction")
        return fatigue_inc * max(0.50, 1 - bonus * 0.05)

    def apply_injury_risk_staff_bonus(self, player, injury_chance):
        if player.team != self.state.user_team:
            return injury_chance

        bonus = self.staff_trait_bonus("DR", "injury_risk_reduction")
        return injury_chance * max(0.50, 1 - bonus * 0.06)

    def apply_injury_days_staff_bonus(self, player, injury_days):
        if player.team != self.state.user_team:
            return injury_days

        bonus = self.staff_trait_bonus("DR", "injury_days_reduction")
        return max(1, int(injury_days * max(0.50, 1 - bonus * 0.06)))

    def apply_rest_fatigue_staff_bonus(self, player, fatigue_recovery):
        if player.team != self.state.user_team:
            return fatigue_recovery

        bonus = self.staff_trait_bonus("HD", "rest_fatigue_recovery")
        return fatigue_recovery + bonus * 8

        # 항상 표시할 야수 위치 (FieldSim 없을 때)
        # FieldSim의 INITIAL_FIELDERS를 그대로 사용
        from simulation import INITIAL_FIELDERS
        self._fielder_display = {k: list(v) for k, v in INITIAL_FIELDERS.items()}

    # ════════════════════════════════════════════════════════
    #  시뮬레이션 연동
    # ════════════════════════════════════════════════════════

    


    def check_special_achievements(self, date_str):
        """완봉/퍼펙트/사이클링히트 체크 후 메시지 전송"""
    
    # 1. 완봉 / 퍼펙트게임 (내 팀 선발 투수)
        starter = self.starter
        if starter:
            g = starter.game_stats
            total_outs = self.inning * 3 - (3 - self.out) if not self.is_game_over else g["ip_outs"]
            is_complete_game = g["ip_outs"] >= 27  # 9이닝 = 27아웃
        
            if is_complete_game and g["r_allowed"] == 0:
                if g["h_allowed"] == 0 and g["bb_p"] == 0:
                    # 퍼펙트게임
                    self.state.inbox.append({
                        "date": date_str,
                        "subject": f"🏆 PERFECT GAME - {starter.name}!",
                        "body": (
                            f"{starter.name} has thrown a PERFECT GAME!\n\n"
                            f"27 batters faced, 27 outs.\n"
                            f"Not a single baserunner allowed.\n"
                            f"A historic performance!"
                        ),
                        "read": False
                    })
                elif g["h_allowed"] == 0:
                    # 노히터
                    self.state.inbox.append({
                        "date": date_str,
                        "subject": f"⭐ NO-HITTER - {starter.name}!",
                        "body": (
                            f"{starter.name} has thrown a NO-HITTER!\n\n"
                            f"{g['ip_outs']//3} innings pitched, 0 hits allowed.\n"
                            f"{g['so_p']} strikeouts, {g['bb_p']} walks."
                        ),
                        "read": False
                    })
                else:
                    # 완봉
                    self.state.inbox.append({
                        "date": date_str,
                        "subject": f"✅ Shutout - {starter.name}",
                        "body": (
                            f"{starter.name} pitched a complete game shutout!\n\n"
                            f"{g['ip_outs']//3} IP, {g['h_allowed']}H, "
                            f"{g['so_p']}K, {g['bb_p']}BB, 0 ER."
                        ),
                        "read": False
                    })

        # 2. 사이클링히트 (내 팀 타자)
        for p in self.my_order:
            if not p:
                continue
            g = p.game_stats
            has_1b = (g["h"] - g.get("2b",0) - g.get("3b",0) - g.get("hr",0)) > 0
            has_2b = g.get("2b", 0) > 0
            has_3b = g.get("3b", 0) > 0
            has_hr = g.get("hr", 0) > 0
        
            if has_1b and has_2b and has_3b and has_hr:
                self.state.inbox.append({
                    "date": date_str,
                    "subject": f"🎯 Hitting for the Cycle - {p.name}!",
                    "body": (
                        f"{p.name} hit for the cycle today!\n\n"
                        f"1B, 2B, 3B, and HR all in one game.\n"
                        f"Final line: {g['ab']}AB {g['h']}H "
                        f"{g['hr']}HR {g['rbi']}RBI."
                    ),
                    "read": False
                })

        # 3. 상대팀 퍼펙트/노히터/완봉 (우리가 당한 경우)
        opp_starter = self.oppstarter
        if opp_starter:
            g = opp_starter.game_stats
            is_complete_game = g["ip_outs"] >= 27

            if is_complete_game and g["r_allowed"] == 0:
                if g["h_allowed"] == 0 and g["bb_p"] == 0:
                    self.state.inbox.append({
                        "date": date_str,
                        "subject": f"😔 Perfect Game Against Us - {opp_starter.name}",
                        "body": (
                            f"{opp_starter.name} ({self.opponent_team}) threw a perfect game against us.\n\n"
                            f"We couldn't get a single baserunner."
                        ),
                        "read": False
                    })
                elif g["h_allowed"] == 0:
                    self.state.inbox.append({
                        "date": date_str,
                        "subject": f"😔 No-Hitter Against Us - {opp_starter.name}",
                        "body": (
                            f"{opp_starter.name} ({self.opponent_team}) no-hit us today.\n\n"
                            f"{g['so_p']}K, {g['bb_p']}BB."
                        ),
                        "read": False
                    })

    def simulate_to_end(self):
        """현재 상태에서 게임을 즉시 완료."""
        # 진행 중인 애니메이션 클리어
        self.pitch_sim  = None
        self.field_sim  = None
        self._pending_result = self._pending_batter = None
        self._pending_pitcher = self._pending_my_team = None
        self._pending_walk = False

        max_iter = 10000  # 무한루프 방지
        count = 0

        while not self.is_game_over and count < max_iter:
            count += 1

            # AI 투수 교체 판단 (BOT 이닝일 때)
            if self.half == "BOT":
                role_flag = self.ai_should_change_pitcher()
                if role_flag:
                    self.ai_replace_pitcher(role_flag)
            elif self.half == "TOP":
                role_flag = self.my_should_change_pitcher()
                if role_flag:
                    self.my_replace_pitcher(role_flag)

            batter  = self.get_current_batter()
            pitcher = self.get_current_pitcher()
            is_my_team = (self.half == "BOT")

            result = self.simulate_pitch(pitcher, batter)

            if result == "COUNT":
                # 볼넷
                if self.ball >= 4:
                    pitcher.game_stats["bb_p"] += 1
                    batter.game_stats["bb"]    += 1
                    if all(self.bases):
                        pitcher.game_stats["r_allowed"] += 1
                        pitcher.game_stats["er"]        += 1
                        batter.game_stats["rbi"] += 1
                        if is_my_team:
                            self.my_score += 1
                            self.my_inning_runs[self.inning - 1] += 1
                        else:
                            self.opp_score += 1
                            self.opp_inning_runs[self.inning - 1] += 1
                    self.bases = [batter, self.bases[0], self.bases[1]]
                    if is_my_team: self.my_bat_idx  += 1
                    else:          self.opp_bat_idx += 1
                    self.reset_count()
                    self.check_inning()

                # 삼진
                elif self.strike >= 3:
                    pitcher.game_stats["so_p"]    += 1
                    pitcher.game_stats["ip_outs"] += 1
                    batter.game_stats["ab"] += 1
                    batter.game_stats["so"] += 1
                    self.out += 1
                    if is_my_team: self.my_bat_idx  += 1
                    else:          self.opp_bat_idx += 1
                    self.reset_count()
                    self.check_inning()

            elif result.startswith("IN_PLAY"):
                if result == "IN_PLAY_HR":
                    hit_result = "HR"
                elif result == "IN_PLAY_OUT":
                    hit_result = "OUT"
                elif result == "IN_PLAY_1B":
                    hit_result = "1B"
                elif result == "IN_PLAY_2B":
                    hit_result = "2B"
                elif result == "IN_PLAY_3B":
                    hit_result = "3B"
                else:
                    hit_result = "OUT"

                if hit_result == "OUT":
                    pitcher.game_stats["ip_outs"] += 1
                    batter.game_stats["ab"]       += 1
                    self.out += 1
                else:
                    self.apply_hit(hit_result, batter, is_my_team)

                if is_my_team: self.my_bat_idx  += 1
                else:          self.opp_bat_idx += 1
                self.reset_count()
                self.check_inning()

            if self.is_game_over:
                break

    def _start_pitch_sim(self, pitch_result, batter, pitcher, is_my_team):
        """투구 애니메이션 시작."""
        self._pending_result  = pitch_result
        self._pending_batter  = batter
        self._pending_pitcher = pitcher
        self._pending_my_team = is_my_team
        self.pitch_sim = PitchSim(pitch_result)

    def _on_pitch_sim_done(self):
        """PitchSim 완료 → 결과 처리 or FieldSim 시작."""
        result    = self._pending_result
        batter    = self._pending_batter
        pitcher   = self._pending_pitcher
        is_my_team = self._pending_my_team

        self.pitch_sim = None

        if result.startswith("IN_PLAY"):
            # 인플레이 → FieldSim 생성
            runners_on = [b is not None for b in self.bases]
            def_lineup = self.my_lineup if is_my_team else self.opp_lineup

            def _def(pos):
                p = def_lineup.get(pos)
                if p:
                    try:
                        return p.get_attr("defense", self.state) / 50
                    except Exception:
                        return 1.0
                return 1.0

            def_stats = {pos: _def(pos) for pos in
                         ["P","C","1B","2B","SS","3B","LF","CF","RF"]}
            run_stats  = {}
            if hasattr(batter, "get_attr"):
                run_stats["B"] = batter.get_attr("run", self.state) / 50
            # 기존 주자들 run 능력치
            for i, key in enumerate(("R1", "R2", "R3")):
                p = self.bases[i]
                if p and hasattr(p, "get_attr"):
                    try:
                        run_stats[key] = p.get_attr("run", self.state) / 50
                    except Exception:
                        run_stats[key] = 1.0

            self.field_sim = FieldSim(
                runners_on=runners_on,
                def_stats=def_stats,
                run_stats=run_stats,
                is_hr=(result == "IN_PLAY_HR"),
            )
        else:
            # COUNT(볼/스트/헛스윙) → 볼넷/삼진 체크 후 끝
            self._apply_count_result()

    def _apply_count_result(self):
        """볼/스트라이크 카운트 누적 후 볼넷/삼진 처리."""
        batter     = self._pending_batter
        pitcher    = self._pending_pitcher
        is_my_team = self._pending_my_team

        # 볼넷
        if self.ball >= 4:
            pitcher.game_stats["bb_p"] += 1
            batter.game_stats["bb"]    += 1
            self.last_event = f"{batter.name} draws a walk!"
            runners_on = [b is not None for b in self.bases]
            walk_run_stats = {}
            if hasattr(batter, "get_attr"):
                walk_run_stats["B"] = batter.get_attr("run", self.state) / 50
            for i, key in enumerate(("R1", "R2", "R3")):
                p = self.bases[i]
                if p and hasattr(p, "get_attr"):
                    try:
                        walk_run_stats[key] = p.get_attr("run", self.state) / 50
                    except Exception:
                        walk_run_stats[key] = 1.0
            self.field_sim = FieldSim(
                runners_on=runners_on,
                is_walk=True,
                run_stats=walk_run_stats,
            )
            self._pending_walk = True
            return

        # 볼넷 아니면 클리어
        self._pending_result = self._pending_batter = None
        self._pending_pitcher = self._pending_my_team = None

        # 삼진
        if self.strike >= 3:
            pitcher.game_stats["so_p"]    += 1
            pitcher.game_stats["ip_outs"] += 1
            batter.game_stats["ab"] += 1
            batter.game_stats["so"] += 1
            self.out += 1
            self.last_event = f"Strike Three! {pitcher.name} fans {batter.name}!"
            if self.half == "TOP":
                self.opp_bat_idx += 1
            else:
                self.my_bat_idx += 1
            self.reset_count()
            self.check_inning()

    def _on_field_sim_done(self):
        """FieldSim 완료 → 결과 처리."""
        from simulation import INITIAL_FIELDERS
        self._fielder_display = {k: list(v) for k, v in INITIAL_FIELDERS.items()}

        pending    = self._pending_result
        batter     = self._pending_batter
        pitcher    = self._pending_pitcher
        is_my_team = self._pending_my_team
        is_walk    = getattr(self, '_pending_walk', False)

        # field_sim 클리어 전에 결과 읽기
        sim_result   = self.field_sim.get_result()
        runner_outs  = self.field_sim.get_runner_outs()
        out_indices  = self.field_sim.get_out_runner_indices()

        self.field_sim     = None
        self._pending_walk = False
        self._pending_result = self._pending_batter = None
        self._pending_pitcher = self._pending_my_team = None

        # ── 볼넷 완료 ──
        if is_walk:
            if all(self.bases):  # 만루였으면 득점
                if pitcher:
                    pitcher.game_stats["r_allowed"] += 1
                    pitcher.game_stats["er"]        += 1
                batter.game_stats["rbi"] += 1
                if is_my_team:
                    self.my_score += 1
                    self.my_inning_runs[self.inning - 1] += 1
                else:
                    self.opp_score += 1
                    self.opp_inning_runs[self.inning - 1] += 1
            self.bases = [batter, self.bases[0], self.bases[1]]
            if is_my_team:
                self.my_bat_idx += 1
            else:
                self.opp_bat_idx += 1
            self.reset_count()
            self.check_inning()
            return

        # ── 인플레이 완료 ──
        final = "HR" if pending == "IN_PLAY_HR" else sim_result

        # 아웃된 주자를 bases에서 먼저 제거 (apply_hit 전에 해야 득점 계산 정확)
        for idx in out_indices:
            self.bases[idx] = None

        if runner_outs > 0:
            self.out += runner_outs
            pitcher.game_stats["ip_outs"] += runner_outs

        if final == "OUT":
            pitcher.game_stats["ip_outs"] += 1
            batter.game_stats["ab"]       += 1
            self.out += 1
            if runner_outs > 0:
                self.last_event = f"Double play! {batter.name} is out!"
            else:
                self.last_event = f"{batter.name} is out!"
        else:
            self.apply_hit(final, batter, is_my_team)
            self.last_event = f"{batter.name} hits a {final}!"

        if is_my_team:
            self.my_bat_idx += 1
        else:
            self.opp_bat_idx += 1

        self.reset_count()
        self.check_inning()

    # ════════════════════════════════════════════════════════
    #  기존 메서드 (변경 없음)
    # ════════════════════════════════════════════════════════

    def process_sim_result(self, res):
        if res == "OUT":
            self.out += 1
        elif res == "1B":
            if self.bases[2]: self.my_score += 1
            self.bases = [True, self.bases[0], self.bases[1]]
        elif res == "2B":
            if self.bases[2]: self.my_score += 1
            if self.bases[1]: self.my_score += 1
            self.bases = [False, True, self.bases[0]]
        elif res == "3B":
            if self.bases[2]: self.my_score += 1
            if self.bases[1]: self.my_score += 1
            if self.bases[0]: self.my_score += 1
            self.bases = [False, False, True]
        self.strike = 0
        self.ball = 0

    def my_should_change_pitcher(self):
        pitcher = self.my_lineup["P"]
        score_diff = self.my_score - self.opp_score
        if pitcher.status["health"] < 200:
            if score_diff > 0:    return "STRONG"
            elif score_diff < -5: return "WEAK"
            else:                 return "MIDDLE"
        if pitcher.game_stats["r_allowed"] >= 4:
            if score_diff < -5: return "WEAK"
            return "MIDDLE"
        if self.inning >= 9 and score_diff > 0:
            return "STRONG"
        return None

    def my_replace_pitcher(self, role_flag):
        available = [
            p for p in self.state.bullpen
            if p is not None
            and p not in self.pitchers_used
            and not p.status.get("is_injured")
        ]
        if not available:
            return
        available.sort(key=lambda p: p.calculate_ovr(), reverse=True)
        if role_flag == "STRONG":
            new_pitcher = available[0]
        elif role_flag == "WEAK":
            new_pitcher = available[-1]
        else:
            mid = len(available) // 2
            new_pitcher = available[mid]

        old_pitcher = self.my_lineup["P"]
        score_diff = self.my_score - self.opp_score
        old_pitcher.game_stats["quit_score_diff"] = score_diff
        new_pitcher.game_stats["entry_score_diff"] = score_diff
        new_pitcher.game_stats["entry_runners"] = sum(1 for b in self.bases if b)
        self.my_lineup["P"] = new_pitcher
        self.pitchers_used.append(new_pitcher)

    def ai_replace_pitcher(self, role_flag):
        available = [
            p for p in self.opp_bullpen
            if p is not None 
            and p not in self.opp_pitchers_used
            and not p.status.get("is_injured")
        ]
        if not available:
            return
        available.sort(key=lambda p: p.calculate_ovr(), reverse=True)
        if role_flag == "STRONG":
            new_pitcher = available[0]
        elif role_flag == "WEAK":
            new_pitcher = available[-1]
        else:
            mid = len(available) // 2
            new_pitcher = available[mid]

        old_pitcher = self.opp_lineup["P"]
        score_diff = self.opp_score - self.my_score
        old_pitcher.game_stats["quit_score_diff"] = score_diff
        new_pitcher.game_stats["entry_score_diff"] = score_diff
        new_pitcher.game_stats["entry_runners"] = sum(1 for b in self.bases if b)
        self.opp_lineup["P"] = new_pitcher
        self.opp_pitchers_used.append(new_pitcher)
        self.last_event = f"{self.opponent_team} brings in {new_pitcher.name}!"

    def ai_should_change_pitcher(self):
        pitcher = self.opp_lineup["P"]
        score_diff = self.opp_score - self.my_score
        if pitcher.status["health"] < 200:
            if score_diff > 0:   return "STRONG"
            elif score_diff < -5: return "WEAK"
            else:                 return "MIDDLE"
        if pitcher.game_stats["r_allowed"] >= 4:
            if score_diff < -5: return "WEAK"
            return "MIDDLE"
        if self.inning >= 9 and score_diff > 0:
            return "STRONG"
        return None
    
    def update_win_candidates(self):
        score_diff = self.my_score - self.opp_score
        if score_diff > 0 and self.win_candidates["my"] is None:
            self.win_candidates["my"] = self.my_lineup["P"]
            self.win_candidates["opp"] = None
            self.losing_pitcher = self.opp_lineup["P"]
        elif score_diff < 0 and self.win_candidates["opp"] is None:
            self.win_candidates["opp"] = self.opp_lineup["P"]
            self.win_candidates["my"] = None
            self.losing_pitcher = self.my_lineup["P"]
        elif score_diff == 0:
            self.win_candidates["my"] = None
            self.win_candidates["opp"] = None
            self.losing_pitcher = None
    
    def update_season_stat(self, player, key):
        from datetime import date, timedelta
        y, m, d = self.state.base_date
        current_game_year = (date(y, m, d) + timedelta(days=self.state.current_day - 1)).year
        s_entry = next((c for c in player.career if c.get("season") == current_game_year), None)
        if s_entry:
            s_entry["stats"][key] = s_entry["stats"].get(key, 0) + 1
    
    def gamso(self, health):
        if health <= 100: return 0.5
        elif health <= 200: return 0.65
        elif health <= 300: return 0.8
        elif health <= 500: return 0.9
        return 1
        
    def toggle_bullpen(self):
        self.show_bullpen = not self.show_bullpen
        if self.show_bullpen:
            self.setup_bullpen_popup()

    def setup_bullpen_popup(self):
        self.bullpen_btns = []
        for i, p in enumerate(self.state.bullpen):
            if p:
                is_used = p in self.pitchers_used
                ovr = p.calculate_ovr()
                btn_text = f"{p.backnumber}. {p.name} ({ovr})"
                if is_used:
                    btn_text = f"[OUT] {p.name}"
                btn = Button((380, 150 + (i * 55), 250, 50), btn_text,
                             lambda pitcher=p: self.replace_pitcher(pitcher))
                if is_used:
                    btn.base_color  = (50, 50, 50)
                    btn.hover_color = (50, 50, 50)
                    btn.callback    = lambda: None
                btn.player_ref = p
                self.bullpen_btns.append(btn)
                
    def replace_pitcher(self, new_pitcher):
        old_pitcher = self.my_lineup["P"]
        old_pitcher.game_stats["quit_score_diff"] = self.my_score - self.opp_score
        if old_pitcher == new_pitcher:
            self.show_bullpen = False
            return
        new_pitcher.game_stats["entry_score_diff"] = self.my_score - self.opp_score
        new_pitcher.game_stats["entry_runners"] = sum(1 for p in self.bases if p is not None) + 1
        self.my_lineup["P"] = new_pitcher
        if new_pitcher not in self.pitchers_used:
            self.pitchers_used.append(new_pitcher)
        self.show_bullpen = False

    def make_ai_lineup(self, players):
        lineup = {}
        pos_map = {}
        for p in players:
            pos_map.setdefault(p.pos, []).append(p)
        for pos in ["P","C","1B","2B","3B","SS","LF","CF","RF","DH"]:
            candidates = pos_map.get(pos, [])
            lineup[pos] = max(candidates, key=lambda p: p.calculate_ovr()) if candidates else None
        hitters = [p for p in lineup.values() if p and p.pos != "P"]
        hitters.sort(key=lambda p: p.calculate_ovr(), reverse=True)
        batting_order = hitters[:9]
        return lineup, batting_order
    
    def get_current_batter(self):
        if self.half == "TOP":
            return self.opp_order[self.opp_bat_idx % 9]
        else:
            return self.my_order[self.my_bat_idx % 9]

    def get_current_pitcher(self):
        if self.half == "TOP":
            return self.my_lineup["P"]
        else:
            return self.opp_lineup["P"]
        
    def check_game_end(self):
        if self.inning == 9 and self.half == "BOT" and self.my_score > self.opp_score:
            self.end_game("WIN")
            return True
        if self.inning > 9 or (self.inning == 9 and self.half == "TOP"):
            if self.my_score > self.opp_score:
                self.end_game("WIN")
            elif self.my_score < self.opp_score:
                self.end_game("LOSS")
            else:
                return False
            return True
        return False

    # ════════════════════════════════════════════════════════
    #  그리기
    # ════════════════════════════════════════════════════════
    
    def draw_scoreboard(self, screen):
        move = 350
        pygame.draw.rect(screen, white, [100, 50, 750+move, 150], 2)
        pygame.draw.line(screen, white, [100, 50+50], [850+move, 50+50], 2)
        pygame.draw.line(screen, white, [100, 50+100], [850+move, 50+100], 2)
        
        screen.blit(self.smallFONT.render(self.opponent_team, True, white), (110, 155 - 50))
        screen.blit(self.smallFONT.render(self.state.user_team, True, white), (110, 205 - 50))
        
        highlight_y = 150 - 50 if self.half == "TOP" else 200 - 50
        highlight_x = move + 100 + 50 * (self.inning - 1)
        if self.inning <= 12:
            pygame.draw.rect(screen, (80, 80, 0), [highlight_x, highlight_y, 50, 50])
        
        for i in range(16):
            pygame.draw.line(screen, white, [move+100+50*i, 100-50], [move+100+50*i, 250-50], 2)
        for i in range(12):
            txt = self.FONT.render(str(i+1), True, "white")
            screen.blit(txt, (move+110+50*i, 105-50))
            
        screen.blit(self.FONT.render("TEAMS", True, "white"), (110, 105-50))
        screen.blit(self.FONT.render("R", True, "white"), (move+110+50*12, 105-50))
        screen.blit(self.FONT.render("H", True, "white"), (move+110+50*13, 105-50))
        screen.blit(self.FONT.render("E", True, "white"), (move+110+50*14, 105-50))
        
        for i in range(12):
            x = move + 110 + 50 * i
            screen.blit(self.smallFONT.render(str(self.opp_inning_runs[i]), True, white), (x, 155-50))
            screen.blit(self.smallFONT.render(str(self.my_inning_runs[i]),  True, white), (x, 205-50))
            
        screen.blit(self.smallFONT.render(str(self.opp_score), True, white), (move+110+50*12, 155-50))
        screen.blit(self.smallFONT.render(str(self.my_score),  True, white), (move+110+50*12, 205-50))
        screen.blit(self.smallFONT.render(str(self.opp_hit),   True, white), (move+110+50*13, 155-50))
        screen.blit(self.smallFONT.render(str(self.my_hit),    True, white), (move+110+50*13, 205-50))
        
    def outs_to_ip(self, outs):
        return f"{outs // 3}.{outs % 3}"

    def draw_field(self, screen):
        """중앙 상자 안에 야구장 + 야수/주자/공을 항상 표시."""
        # 상자 테두리 (더 크게)
        BOX = [400, 220, 650, 470]
        pygame.draw.rect(screen, white, BOX, 3)

        # ── 베이스 ──────────────────────────────────────────
        BASE_COLOR = (200, 200, 100)
        bases_draw = {
            "HOME": sim_to_screen(0,  0),
            "1B":   sim_to_screen(30, 0),
            "2B":   sim_to_screen(30, 30),
            "3B":   sim_to_screen(0,  30),
            "P":    sim_to_screen(15, 15),
        }
        for name, (bx, by) in bases_draw.items():
            if name == "HOME":
                pygame.draw.polygon(screen, BASE_COLOR,
                    [(bx, by-16),(bx+16,by),(bx,by+16),(bx-16,by)])
                pygame.draw.polygon(screen, white,
                    [(bx, by-16),(bx+16,by),(bx,by+16),(bx-16,by)], 1)
            elif name == "P":
                pygame.draw.circle(screen, (120, 120, 120), (bx, by), 10)
            else:
                pygame.draw.rect(screen, BASE_COLOR, (bx-12, by-12, 24, 24))
                pygame.draw.rect(screen, white, (bx-12, by-12, 24, 24), 1)

        # ── 베이스 위 주자 표시 (bases 리스트 기반, FieldSim 없을 때) ──
        if not self.field_sim:
            RUNNER_BASE = ["1B", "2B", "3B"]
            for i, runner in enumerate(self.bases):
                if runner is not None:
                    bx, by = bases_draw[RUNNER_BASE[i]]
                    pygame.draw.circle(screen, (255, 80, 80), (bx, by), 14)
                    if hasattr(runner, "name"):
                        name_surf = self.verysmallFONT.render(runner.name, True, (255, 180, 180))
                        screen.blit(name_surf, (bx - name_surf.get_width() // 2, by - 28))
            batter = self.get_current_batter()
            if batter:
                hx, hy = bases_draw["HOME"]
                pygame.draw.circle(screen, (255, 80, 80), (hx, hy), 14)
                name_surf = self.verysmallFONT.render(batter.name, True, (255, 180, 180))
                screen.blit(name_surf, (hx - name_surf.get_width() // 2, hy + 18))

        # ── 야수 ─────────────────────────────────────────────
        # FieldSim 진행 중이면 sim 야수 위치, 아니면 기본 위치
        if self.field_sim:
            fielders_pos = self.field_sim.fielders
        else:
            fielders_pos = self._fielder_display

        FIELDER_COLOR = (80, 160, 255)
        # 수비 라인업: TOP이면 내 팀 수비, BOT이면 상대팀 수비
        def_lineup = self.my_lineup if self.half == "TOP" else self.opp_lineup
        for pos_key, pos in fielders_pos.items():
            fx, fy = sim_to_screen(pos[0], pos[1])
            pygame.draw.circle(screen, FIELDER_COLOR, (fx, fy), 13)
            player = def_lineup.get(pos_key)
            label_text = player.name if player and hasattr(player, "name") else pos_key
            label = self.verysmallFONT.render(label_text, True, (200, 200, 200))
            screen.blit(label, (fx - label.get_width() // 2, fy - 26))

        # ── FieldSim 주자 이동 ────────────────────────────────
        if self.field_sim:
            # key → bases 인덱스 / 타자 매핑
            key_to_player = {
                "B":  self._pending_batter,
                "R1": self.bases[0] if len(self.bases) > 0 else None,
                "R2": self.bases[1] if len(self.bases) > 1 else None,
                "R3": self.bases[2] if len(self.bases) > 2 else None,
            }
            for key, pos in self.field_sim.runners.items():
                if pos:
                    rx, ry = sim_to_screen(pos[0], pos[1])
                    pygame.draw.circle(screen, (255, 80, 80), (rx, ry), 14)
                    player = key_to_player.get(key)
                    if player and hasattr(player, "name"):
                        name_surf = self.verysmallFONT.render(player.name, True, (255, 180, 180))
                        screen.blit(name_surf, (rx - name_surf.get_width() // 2, ry - 28))

        # ── 공 ───────────────────────────────────────────────
        ball_pos = None
        if self.pitch_sim:
            ball_pos = self.pitch_sim.ball_pos
        elif self.field_sim:
            ball_pos = self.field_sim.ball_pos

        if ball_pos:
            bx, by = sim_to_screen(ball_pos[0], ball_pos[1])
            pygame.draw.circle(screen, (255, 255, 0), (bx, by), 9)

    def draw_board(self, screen):
        # 중앙 필드 박스 → draw_field 로 위임
        self.draw_field(screen)

        # BSO 박스 (오른쪽)
        pygame.draw.rect(screen, white, [900+100+100, 350-140, 150, 150+40], 3)

        inning_text = f"{self.inning}"
        txt = self.FONT.render(inning_text, True, white)
        center_x = 900+10+100+100+8
        screen.blit(txt, (center_x - txt.get_width()//2, 260-50))
        text_x = center_x - txt.get_width()//2
        text_y = 350+5-100-50+7
        tri_x = text_x + txt.get_width() + 15
        tri_y = text_y + txt.get_height()//2
        size = 10
        if self.half == "TOP":
            points = [(tri_x, tri_y+size),(tri_x+size, tri_y-size),(tri_x+size*2, tri_y+size)]
        else:
            points = [(tri_x, tri_y-size),(tri_x+size, tri_y+size),(tri_x+size*2, tri_y-size)]
        pygame.draw.polygon(screen, white, points)
        
        screen.blit(self.FONT.render("B", True, "white"), (900+10+100+100, 350+5-100))
        for i in range(3):
            if i < self.ball:
                pygame.draw.circle(screen, white, [900+15+35*i+40+100+100, 350+5+20-100], 15)
            else:
                pygame.draw.circle(screen, white, [900+15+35*i+40+100+100, 350+5+20-100], 15, 2)
        
        screen.blit(self.FONT.render("S", True, "white"), (900+10+100+100, 350+5+50-100))
        for i in range(2):
            if i < self.strike:
                pygame.draw.circle(screen, white, [900+15+35*i+40+100+100, 350+5+20+50-100], 15)
            else:
                pygame.draw.circle(screen, white, [900+15+35*i+40+100+100, 350+5+20+50-100], 15, 2)
        
        screen.blit(self.FONT.render("O", True, "white"), (900+10+100+100, 350+5+50*2-100))
        for i in range(2):
            if i < self.out:
                pygame.draw.circle(screen, white, [900+15+35*i+40+100+100, 350+5+20+50*2-100], 15)
            else:
                pygame.draw.circle(screen, white, [900+15+35*i+40+100+100, 350+5+20+50*2-100], 15, 2)

        # 투수 박스
        pygame.draw.rect(screen, white, [100-50, 300-50, 350-50, 150], 3)
        pitcher = self.get_current_pitcher()
        if pitcher:
            y = 310-50
            screen.blit(self.smallFONT.render(f"Pitcher: {pitcher.name}", True, white), (110-50, y))
            hp = pitcher.get_health() / 20
            xx = 110+50+100+30+10+10-50+5
            pygame.draw.rect(screen, (0,0,0), [xx-2, y-2+10, 54, 18])
            pygame.draw.rect(screen, (255,0,0), [xx, y+10, 50, 14])
            pygame.draw.rect(screen, (0,255,0), [xx, y+10, hp, 14])
            g = pitcher.game_stats
            ip_str = self.outs_to_ip(g["ip_outs"])
            screen.blit(self.smallFONT.render(
                f"{ip_str}IP {g['h_allowed']}H {g['r_allowed']}R {g['so_p']}K",
                True, (200,200,0)), (110-50, y+25))
            y += 55
            if pitcher.is_pitcher():
                for i, (label, attr) in enumerate([("VEL","velocity"),("CON","control"),
                                                    ("STU","stuff"),("STA","stamina"),("DEF","defense")]):
                    val   = pitcher.get_attr(attr, self.state)
                    bonus = pitcher.get_bonus(attr, self.state)
                    col, row = i%2, i//2
                    cx = 110+(col*110)-50
                    cy = y+(row*25)
                    surf = self.smallFONT.render(f"{label}: {val-bonus}", True, white)
                    screen.blit(surf, (cx, cy))
                    if bonus > 0:
                        screen.blit(self.smallFONT.render(f" (+{bonus})", True, (0,255,100)),
                                    (cx+surf.get_width(), cy))

        # 타자 박스
        pygame.draw.rect(screen, white, [100-50, 500-50, 350-50, 150], 3)
        batter = self.get_current_batter()
        if batter:
            y = 510-50
            screen.blit(self.smallFONT.render(f"Batter: {batter.name}", True, white), (110-50, y))
            hp = batter.get_health() / 20
            xx = 110+50+100+30+10+10-50+5
            pygame.draw.rect(screen, (0,0,0), [xx-2, y-2+10, 54, 18])
            pygame.draw.rect(screen, (255,0,0), [xx, y+10, 50, 14])
            pygame.draw.rect(screen, (0,255,0), [xx, y+10, hp, 14])
            g = batter.game_stats
            screen.blit(self.smallFONT.render(
                f"{g['ab']}AB {g['h']}H {g['hr']}HR {g['rbi']}RBI",
                True, (200,200,0)), (110-50, y+25))
            y += 55
            for i, (label, attr) in enumerate([("CON","contact"),("POW","power"),
                                                ("EYE","eye"),("RUN","run"),("DEF","defense")]):
                val   = batter.get_attr(attr, self.state)
                bonus = batter.get_bonus(attr, self.state)
                col, row = i%2, i//2
                cx = 110+(col*110)-50
                cy = y+(row*25)
                surf = self.smallFONT.render(f"{label}: {val-bonus}", True, white)
                screen.blit(surf, (cx, cy))
                if bonus > 0:
                    screen.blit(self.smallFONT.render(f" (+{bonus})", True, (0,255,100)),
                                (cx+surf.get_width(), cy))

        if self.last_event:
            surf = self.smallFONT.render(self.last_event, True, (255, 220, 80))
            screen.blit(surf, (screen.get_width() // 2 - surf.get_width() // 2,
                               screen.get_height() - 30))

    # ════════════════════════════════════════════════════════
    #  simulate_pitch: COUNT 결과도 명확히 반환
    # ════════════════════════════════════════════════════════

    def simulate_pitch(self, pitcher, batter):
        control  = pitcher.get_attr("control",  self.state) * self.gamso(pitcher.status["health"])
        velocity = pitcher.get_attr("velocity", self.state) * self.gamso(pitcher.status["health"])
        stuff    = pitcher.get_attr("stuff",    self.state) * self.gamso(pitcher.status["health"])
        contact  = batter.get_attr("contact",   self.state) * self.gamso(batter.status["health"])
        power    = batter.get_attr("power",     self.state) * self.gamso(batter.status["health"])
        eye      = batter.get_attr("eye",       self.state) * self.gamso(batter.status["health"])

        pitcher.status["health"] = max(0, pitcher.status["health"] - 10)
        batter.status["health"]  = max(0, batter.status["health"]  - 10)

        strike_prob = 0.5 + (control - eye) / 200
        is_strike   = random.random() < strike_prob
        swing_prob  = 0.5 + (50 - eye) / 150
        swing       = random.random() < swing_prob if is_strike else random.random() < 0.2

        if not swing:
            if is_strike:
                self.strike += 1
                self.last_event = f"Strike! {batter.name} takes it for a called strike."
            else:
                self.ball += 1
                self.last_event = f"Ball! {batter.name} didn't bite on that one."
            return "COUNT"

        contact_score = contact - (velocity + stuff) * 0.3 + random.randint(-20, 20)
        if contact_score < 20:
            self.strike += 1
            self.last_event = f"Swing and a miss! {batter.name} was way off the timing."
            return "COUNT"

        # 인플레이
        hit_roll    = random.random()
        power_bonus = (power - 50) / 200
        if hit_roll < 0.60:
            return "IN_PLAY_OUT"
        elif hit_roll < 0.80 - power_bonus:
            return "IN_PLAY_1B"
        elif hit_roll < 0.92 - power_bonus:
            return "IN_PLAY_2B"
        elif hit_roll < 0.97:
            return "IN_PLAY_3B"
        else:
            return "IN_PLAY_HR"

    def apply_hit(self, result, batter, is_my_team):
        runs = 0
        pitcher = self.opp_lineup["P"] if is_my_team else self.my_lineup["P"]

        if result == "1B":
            if is_my_team: self.my_hit += 1
            else:          self.opp_hit += 1
            if self.bases[2]: runs += 1
            self.bases = [batter, self.bases[0], self.bases[1]]
            batter.game_stats["ab"] += 1
            batter.game_stats["h"]  += 1
            if runs > 0:
                batter.game_stats["rbi"] += runs

        elif result in ("2B", "3B", "HR"):
            if is_my_team: self.my_hit += 1
            else:          self.opp_hit += 1
            if result == "2B":
                if self.bases[2]: runs += 1
                if self.bases[1]: runs += 1
                self.bases = [False, batter, self.bases[0]]
            elif result == "3B":
                for r in self.bases:
                    if r: runs += 1
                self.bases = [False, False, batter]
            elif result == "HR":
                for r in self.bases:
                    if r: runs += 1
                runs += 1
                self.bases = [None, None, None]
            batter.game_stats["ab"]  += 1
            batter.game_stats["h"]   += 1
            if result == "2B":
                batter.game_stats["2b"] = batter.game_stats.get("2b", 0) + 1
            elif result == "3B":
                batter.game_stats["3b"] = batter.game_stats.get("3b", 0) + 1
            elif result == "HR":
                batter.game_stats["hr"] += 1
            batter.game_stats["rbi"] += runs

        inning_idx = self.inning - 1
        if is_my_team:
            self.my_score += runs
            if runs > 0 and pitcher:
                self.my_inning_runs[inning_idx] += runs
                self.update_win_candidates()
            if self.half == "BOT" and self.inning >= 9 and self.my_score > self.opp_score:
                self.end_game("WIN")
                return
        else:
            self.opp_score += runs
            if runs > 0:
                self.opp_inning_runs[inning_idx] += runs
                self.update_win_candidates()
        if pitcher:
            pitcher.game_stats["r_allowed"] += runs
            pitcher.game_stats["er"]        += runs

    def process_pitch(self):
        if self.half == "TOP":
            batter     = self.opp_order[self.opp_bat_idx % 9]
            pitcher    = self.my_lineup["P"]
            is_my_team = False
        else:
            role_flag = self.ai_should_change_pitcher()
            if role_flag:
                self.ai_replace_pitcher(role_flag)
            batter     = self.my_order[self.my_bat_idx % 9]
            pitcher    = self.opp_lineup["P"]
            is_my_team = True

        result = self.simulate_pitch(pitcher, batter)
        # 투구 애니메이션 시작 → 결과 처리는 애니메이션 완료 후
        self._start_pitch_sim(result, batter, pitcher, is_my_team)

    def reset_count(self):
        self.ball = 0
        self.strike = 0
        
    def check_inning(self):
        if self.out < 3:
            return
        finished_half   = self.half
        finished_inning = self.inning
        self.out   = 0
        self.bases = [None, None, None]
        if self.half == "TOP":
            self.half = "BOT"
        else:
            self.half = "TOP"
            self.inning += 1
        if finished_inning == 9 and finished_half == "TOP":
            if self.my_score > self.opp_score:
                self.end_game("WIN")
                return
        if finished_inning >= 9 and finished_half == "BOT":
            if self.my_score != self.opp_score:
                self.end_game("WIN" if self.my_score > self.opp_score else "LOSS")
                return
        if finished_inning == 12 and finished_half == "BOT":
            if self.my_score == self.opp_score:
                self.end_game("DRAW")
                return

    # ════════════════════════════════════════════════════════
    #  draw / update
    # ════════════════════════════════════════════════════════
        
    def draw(self, screen):
        screen.fill((20, 20, 20))
        screen.blit(self.FONT.render("Press Space to continue", True, (255,255,255)), (50, 640+20))
        self.draw_scoreboard(screen)
        self.draw_board(screen)
        self.instant_btn.draw(screen)

        if self.half == "TOP":
            self.change_p_btn.draw(screen)
        if self.show_bullpen:
            overlay = pygame.Surface((width, height), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            screen.blit(overlay, (0, 0))
            title = self.FONT.render("BULLPEN", True, (255,255,255))
            screen.blit(title, (width//2 - title.get_width()//2, 100))
            for btn in self.bullpen_btns:
                btn.draw(screen)
                p = getattr(btn, "player_ref", None)
                if not p: continue
                bx, by, bw, bh = btn.rect
                cond = p.status.get("condition", 50)
                cond_color = (0,255,0) if cond>70 else (255,255,0) if cond>40 else (255,0,0)
                pygame.draw.circle(screen, cond_color, (bx+15, by+23), 6)
                health    = p.status.get("health", 0)
                bar_x, bar_y = bx+35, by+bh-12
                pygame.draw.rect(screen, (60,60,60), (bar_x, bar_y, 100, 6))
                h_color = (0,200,255) if health>50 else (255,100,0)
                pygame.draw.rect(screen, h_color, (bar_x, bar_y, 100*(min(1000,health)/1000), 6))
                screen.blit(self.verysmallFONT.render(f"{int(health/10)}%", True, (200,200,200)),
                            (bar_x+105, bar_y-5))
                chart_cx = bx + bw + 50  # 버튼 오른쪽에 여백 두고
                chart_cy = by + bh // 2
                draw_radar_chart_game(screen, p, cx=chart_cx, cy=chart_cy, radius=30)
        
    def update(self, events):
        # ── 1. 투구 애니메이션 진행 ────────────────────────────
        if self.pitch_sim:
            self.pitch_sim.update()
            if self.pitch_sim.is_done:
                self._on_pitch_sim_done()
            return  # 애니메이션 중 입력 차단

        # ── 2. 인플레이 시뮬레이션 진행 ───────────────────────
        if self.field_sim:
            self.field_sim.update()
            if self.field_sim.is_over:
                try:
                    self._on_field_sim_done()
                except Exception as e:
                    print(f"[ERROR] _on_field_sim_done: {e}")
                    import traceback; traceback.print_exc()
                    self.field_sim = None
                    self._pending_result = self._pending_batter = None
                    self._pending_pitcher = self._pending_my_team = None
            return

        # ── 3. 불펜 팝업 ──────────────────────────────────────
        mouse_pos = pygame.mouse.get_pos()
        if self.show_bullpen:
            for btn in self.bullpen_btns:
                btn.update_hover(mouse_pos)
            for e in events:
                if e.type == pygame.MOUSEBUTTONDOWN:
                    clicked_any = False
                    for btn in self.bullpen_btns:
                        res = btn.handle_event(e)
                        if res is not None:
                            clicked_any = True
                            return res
                    if not clicked_any:
                        self.show_bullpen = False
            return None

        # ── 4. 일반 입력 ──────────────────────────────────────
        if self.half == "TOP":
            self.change_p_btn.update_hover(mouse_pos)
            for e in events:
                if e.type == pygame.MOUSEBUTTONDOWN:
                    self.change_p_btn.handle_event(e)

        for e in events:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
                if not self.is_game_over:
                    self.process_pitch()   # 항상 투구 애니메이션으로 시작
        self.instant_btn.update_hover(mouse_pos)
        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN:
                self.instant_btn.handle_event(e)

        if self.is_game_over:
            return ("result", self.game_result)

    # ════════════════════════════════════════════════════════
    #  기존 통계/종료 메서드 (변경 없음)
    # ════════════════════════════════════════════════════════

    def apply_game_stats_to_players(self):
        from datetime import date, timedelta
        y, m, d = self.state.base_date
        current_game_year = (date(y, m, d) + timedelta(days=self.state.current_day - 1)).year
        date_str = (date(y, m, d) + timedelta(days=self.state.current_day - 1)).strftime("%m/%d")
        
        all_participants = self.my_order + self.opp_order + self.pitchers_used + self.opp_pitchers_used
        if self.opp_lineup.get("P"):
            all_participants.append(self.opp_lineup["P"])
        all_participants = list(set(p for p in all_participants if p is not None))

        for p in all_participants:
            if not p: continue
            season_entry = next((c for c in p.career if c.get("season") == current_game_year), None)
            if not season_entry:
                season_entry = {
                    "season": current_game_year,
                    "team": self.state.user_team if p in (self.my_order + self.pitchers_used) else "Opponent",
                    "stats": {
                        "g":0,"ab":0,"h":0,"2b":0,"3b":0,"hr":0,"rbi":0,"bb":0,"so":0,"sb":0,
                        "obp":0.0,"slg":0.0,"ops":0.0,
                        "w":0,"l":0,"era":0.0,"ip_outs":0,"ip":0.0,
                        "h_allowed":0,"bb_allowed":0,"er":0,"whip":0.0
                    }
                }
                p.career.append(season_entry)
            season = season_entry["stats"]
            game   = p.game_stats
            if game.get("ab", 0) > 0 or game.get("bb", 0) > 0:
                if game.get("ab", 0) > 0:
                    season["g"]   = season.get("g", 0) + 1
                season["ab"]  += game.get("ab",  0)
                season["h"]   += game.get("h",   0)
                season["2b"]  = season.get("2b", 0) + game.get("2b", 0)
                season["3b"]  = season.get("3b", 0) + game.get("3b", 0)
                season["hr"]  += game.get("hr",  0)
                season["rbi"] += game.get("rbi", 0)
                season["bb"]  += game.get("bb",  0)
                season["so"]  += game.get("so",  0)
                season["sb"]  += game.get("sb",  0)
                # OBP = (H + BB) / (AB + BB)
                pa = season["ab"] + season["bb"]
                if pa > 0:
                    season["obp"] = round((season["h"] + season["bb"]) / pa, 3)
                # SLG = (1B + 2×2B + 3×3B + 4×HR) / AB
                if season["ab"] > 0:
                    singles = season["h"] - season.get("2b",0) - season.get("3b",0) - season["hr"]
                    tb = singles + 2*season.get("2b",0) + 3*season.get("3b",0) + 4*season["hr"]
                    season["slg"] = round(tb / season["ab"], 3)
                season["ops"] = round(season.get("obp", 0) + season.get("slg", 0), 3)
            if game.get("ip_outs", 0) > 0 or game.get("so_p", 0) > 0:
                if game.get("ab", 0) == 0:
                    season["g"] = season.get("g", 0) + 1
                season["ip_outs"]   += game.get("ip_outs", 0)
                season["so"]        = season.get("so", 0) + game.get("so_p", 0)
                season["h_allowed"] += game.get("h_allowed", 0)
                season["bb_allowed"]+= game.get("bb_p", 0)
                season["er"]        += game.get("er", 0)
                total_ip = season["ip_outs"] / 3
                season["ip"] = (season["ip_outs"]//3) + (season["ip_outs"]%3 * 0.1)
                if total_ip > 0:
                    season["era"]  = round((season["er"] * 9) / total_ip, 2)
                    season["whip"] = round((season["h_allowed"] + season["bb_allowed"]) / total_ip, 2)

        active_players = [p for p in self.my_order + self.pitchers_used if p is not None]
        for p in active_players:
            if not p.status.get("is_injured"):
                health_loss = max(0, 1000 - p.status.get("health", 1000))
                p.status["exp"] = p.status.get("exp", 0) + health_loss * 2
                inc = (2.7 * health_loss) * (100 / getattr(p, 'stamina', 100)) / 10 if p.pos == "P" else (8*9 if p.pos == "C" else 5*9)
                if p.status.get("condition", 100) < 70: inc *= 1.3
                inc = self.apply_game_fatigue_staff_bonus(p, inc)
                p.status["fatigue"]   += inc - 10
                p.status["condition"] = min(100, p.status["condition"] + random.randint(5, 10))
                if p.status["fatigue"] > 200:
                    injury_chance = min(0.5, ((p.status["fatigue"]-200)**2)/40000 + 0.05)
                    injury_chance = self.apply_injury_risk_staff_bonus(p, injury_chance)
                    if random.random() < injury_chance:
                        p.status["is_injured"]   = True
                        p.status["injury_days"]  = self.apply_injury_days_staff_bonus(p, random.randint(3, 30))
                        self.state.inbox.append({
                            "date": date_str, "subject": f"Injury Report: {p.name}",
                            "body": f"Unfortunately, {p.name} suffered an injury. \nExpected recovery will be {p.status['injury_days']} days.",
                            "read": False
                        })
        user_players  = self.state.team_rosters.get(self.state.user_team, [])
        bench_players = [p for p in user_players if p not in active_players]
        for p in bench_players:
            if not p.status.get("is_injured"):
                p.status["fatigue"]   = max(0, p.status["fatigue"] - self.apply_rest_fatigue_staff_bonus(p, 30))
                p.status["condition"] = max(0, p.status["condition"] - 2)

    def update_team_record(self):
        my  = self.state.user_team
        opp = self.opponent_team
        current_date = self.state.get_current_date_str()
        schedule_entry = self.state.schedule.get(current_date, {})

        if schedule_entry.get("stage") == "postseason":
            winner = my if self.my_score > self.opp_score else opp
            loser = opp if winner == my else my
            if current_date in self.state.schedule:
                self.state.schedule[current_date]["score"] = f"{self.my_score} : {self.opp_score}"

            ps = getattr(self.state, "postseason", {})
            series = ps.get("current_series")
            if ps.get("active") and series and not series.get("winner"):
                series["wins"][winner] += 1
                series["results"].append({
                    "date": current_date,
                    "winner": winner,
                    "loser": loser,
                    "score": f"{self.my_score}:{self.opp_score}"
                })
                series["game_no"] += 1
                if series["wins"][winner] >= series["wins_needed"]:
                    series["winner"] = winner
            return

        if self.my_score > self.opp_score:
            self.state.team_stats[my]["win"]   += 1
            self.state.team_stats[opp]["loss"] += 1
        else:
            self.state.team_stats[my]["loss"]  += 1
            self.state.team_stats[opp]["win"]  += 1
        self.state.team_stats[my]["games"]  += 1
        self.state.team_stats[opp]["games"] += 1
        if current_date in self.state.schedule:
            self.state.schedule[current_date]["score"] = f"{self.my_score} : {self.opp_score}"

    def end_game(self, result):
        from datetime import date, timedelta
        y, m, d = self.state.base_date
        current_game_year = (date(y, m, d) + timedelta(days=self.state.current_day - 1)).year

        self.apply_game_stats_to_players()
        self.state.todaygamedone = True

        date_str = self.state.get_current_date_str()
        self.check_special_achievements(date_str)

        finisher    = self.my_lineup["P"]
        oppfinisher = self.opp_lineup["P"]
        participants = self.my_order + self.pitchers_used + self.opp_order + self.opp_pitchers_used

        self.update_team_record()

        self.game_result = {
            "result": result, "my_score": self.my_score, "opp_score": self.opp_score,
            "my_inning_runs": self.my_inning_runs, "opp_inning_runs": self.opp_inning_runs,
            "opponent": self.opponent_team,
            "my_players":  self.my_order  + self.pitchers_used,
            "opp_players": self.opp_order + self.opp_pitchers_used
        }

        date_str = self.state.get_current_date_str()
        self.state.inbox.append({
            "date": date_str, "subject": f"[{result}] vs {self.opponent_team}",
            "body": f"Final score: {self.my_score}:{self.opp_score}.\n", "read": False
        })

        my_p  = self.starter
        opp_p = self.oppstarter

        if result in ("WIN", "LOSS") and self.losing_pitcher:
            self.update_season_stat(self.losing_pitcher, "l")

        if result == "WIN":
            winner = self.win_candidates["my"]
            if winner:
                if my_p.game_stats["ip_outs"] >= 15 and my_p == winner:
                    self.update_season_stat(my_p, "w")
                else:
                    self.update_season_stat(winner, "w")
            if finisher != winner:
                if (finisher.game_stats["ip_outs"]>=9 or
                    (finisher.game_stats["ip_outs"]>=3 and 0 < finisher.game_stats["entry_score_diff"]<=3) or
                    finisher.game_stats["entry_runners"] >= finisher.game_stats["entry_score_diff"]):
                    self.update_season_stat(finisher, "sv")
            for p in self.pitchers_used:
                if p in (winner, finisher): continue
                if p.game_stats["ip_outs"]>=1 and p.game_stats["entry_score_diff"]<=3 and p.game_stats["quit_score_diff"]>0:
                    self.update_season_stat(p, "hld")

        elif result == "LOSS":
            winner = self.win_candidates["opp"]
            if winner:
                if opp_p and opp_p.game_stats["ip_outs"]>=15 and opp_p==winner:
                    self.update_season_stat(opp_p, "w")
                else:
                    self.update_season_stat(winner, "w")
            if oppfinisher != winner:
                if (oppfinisher.game_stats["ip_outs"]>=9 or
                    (oppfinisher.game_stats["ip_outs"]>=3 and 0 < oppfinisher.game_stats["entry_score_diff"]<=3) or
                    oppfinisher.game_stats["entry_runners"] >= oppfinisher.game_stats["entry_score_diff"]):
                    self.update_season_stat(oppfinisher, "sv")
            for p in self.opp_pitchers_used:
                if p in (winner, oppfinisher): continue
                if p.game_stats["ip_outs"]>=1 and p.game_stats["entry_score_diff"]<=3 and p.game_stats["quit_score_diff"]>0:
                    self.update_season_stat(p, "hld")

        w_team = self.state.user_team if result=="WIN" else self.opponent_team
        l_team = self.opponent_team   if result=="WIN" else self.state.user_team
        if result in ("WIN","LOSS"):
            for t, r in [(w_team,"W"),(l_team,"L")]:
                if t in self.state.team_data:
                    form = self.state.team_data[t].get("recent_form",[])
                    form.append(r)
                    if len(form)>5: form.pop(0)
                    self.state.team_data[t]["recent_form"] = form
        else:
            for t in (self.state.user_team, self.opponent_team):
                if t in self.state.team_data:
                    form = self.state.team_data[t].get("recent_form",[])
                    form.append("D")
                    if len(form)>5: form.pop(0)
                    self.state.team_data[t]["recent_form"] = form

        perf_messages = {
            "BATTER_HOT_AVG":"is on fire! Crushing the league right now!",
            "BATTER_HOT_HR":"Power Surge! Clearing the fences with ease.",
            "BATTER_HOT_RBI":"The RBI machine! A nightmare with RISP.",
            "BATTER_COLD_AVG":"bat goes cold. Time for a benching?",
            "BATTER_COLD_SO":"Swing and a miss... Lost at the plate.",
            "PITCHER_HOT_ERA":"Lights out! Putting up a clinic on the mound.",
            "PITCHER_HOT_WIN":"The Winning Formula: A lock for a victory.",
            "PITCHER_HOT_K9":"Born to K!! Overpowers hitters!",
            "PITCHER_COLD_ERA":"Batting practice? Opponents are teeing off.",
            "PITCHER_COLD_BB":"Unfortunately, suffering from control issues."
        }
        for p in list(set(p for p in participants if p)):
            has_played = (p.game_stats["ab"]>0) if not p.is_pitcher() else (p.game_stats["ip_outs"]>0)
            if has_played:
                p.add_game_log()
                key = p.analyze_recent_performance()
                if key and key != p.last_report_key and key in perf_messages:
                    self.state.inbox.append({
                        "date": date_str, "subject": f"Report: {p.name}",
                        "body": f"{p.name} {perf_messages[key]}", "read": False
                    })
                    p.last_report_key = key
                elif not key:
                    p.last_report_key = None

        date_str = self.state.get_current_date_str()
        if date_str in self.state.schedule:
            self.state.schedule[date_str]["played"] = True

        self.is_game_over = True
