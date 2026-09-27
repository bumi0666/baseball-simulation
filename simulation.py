import math
import random

BASE_POS = {
    "HOME": [0, 0], "1B": [30, 0], "2B": [30, 30], "3B": [0, 30], "P": [15, 15]
}

INITIAL_FIELDERS = {
    "P":  [15, 15],
    "C":  [-2, -2],
    "1B": [28,  3],
    "2B": [33, 27],
    "SS": [22, 35],
    "3B": [ 3, 26],
    "LF": [10, 58],
    "CF": [45, 45],
    "RF": [58, 10],
}

OUTFIELDERS = {"LF", "CF", "RF"}
DEFAULT_DEF = {k: 1.0 for k in INITIAL_FIELDERS}
DEFAULT_RUN = {"B": 1.0, "R1": 1.0, "R2": 1.0, "R3": 1.0}


class PitchSim:
    PITCHER_POS = [15, 15]
    HOME_POS    = [ 0,  0]
    CATCHER_POS = [-2, -2]

    PITCH_SPEED   = 1.0   # 투구 속도
    RETURN_SPEED  = 0.6   # 포수→투수 리턴 속도 (좀 여유있게)

    def __init__(self, pitch_result):
        self.pitch_result = pitch_result
        self.ball_pos  = list(self.PITCHER_POS)
        self.state     = "PITCHING"
        self.is_done   = False

    def update(self):
        if self.is_done:
            return

        if self.state == "PITCHING":
            d = self._move(self.ball_pos, self.HOME_POS, self.PITCH_SPEED)
            if d < 1:
                self.ball_pos = list(self.HOME_POS)
                if self.pitch_result.startswith("IN_PLAY"):
                    self.is_done = True   # 인플레이 → FieldSim이 이어받음
                else:
                    self.state = "TO_CATCHER"

        elif self.state == "TO_CATCHER":
            d = self._move(self.ball_pos, self.CATCHER_POS, self.PITCH_SPEED)
            if d < 1:
                self.ball_pos = list(self.CATCHER_POS)
                self._pause = getattr(self, "_pause", 40)  # 40프레임 대기
                self.state = "PAUSE"

        elif self.state == "PAUSE":
            self._pause -= 1
            if self._pause <= 0:
                self.state = "TO_PITCHER"

        elif self.state == "TO_PITCHER":
            d = self._move(self.ball_pos, self.PITCHER_POS, self.RETURN_SPEED)
            if d < 1:
                self.ball_pos = list(self.PITCHER_POS)
                self.is_done = True

    def _move(self, pos, target, speed):
        d = math.dist(pos, target)
        if d > speed:
            pos[0] += (target[0] - pos[0]) / d * speed
            pos[1] += (target[1] - pos[1]) / d * speed
        else:
            pos[0], pos[1] = float(target[0]), float(target[1])
        return d


# ══════════════════════════════════════════════════════════
#  안타 위치 존 테이블 (기획 스펙 그대로 반영)
#  각 항목: (이름, (각도범위 시작, 끝), 확률 가중치%, 추가진루 배수, 호수비 기준확률)
#  각도는 홈 기준 0도(1루/우익수 방향) ~ 90도(3루/좌익수 방향)
# ══════════════════════════════════════════════════════════
GROUND_ZONES = [
    ("1루수 옆",        (0.0,  4.5), 5,  1.4, 0.03),
    ("1루수-2루수 간",  (4.5, 31.5), 30, 0.9, 0.08),
    ("2루수-유격수 간", (31.5, 58.5), 30, 0.9, 0.08),
    ("유격수-3루수 간", (58.5, 85.5), 30, 0.9, 0.08),
    ("3루수 옆",        (85.5, 90.0), 5,  1.4, 0.03),
]

FLY_ZONES = [
    ("우익수 옆",         (0.0,  9.0), 10, 1.4, 0.02),
    ("중견수-우익수 간",  (9.0, 45.0), 40, 1.0, 0.05),
    ("좌익수-중견수 간",  (45.0, 81.0), 40, 1.0, 0.05),
    ("좌익수 옆",         (81.0, 90.0), 10, 1.4, 0.02),
]

# 안타 종류(+아웃)별 타구 비거리 범위 (존은 방향만, 거리는 여기서)
OUTCOME_DIST_RANGE = {
    ("OUT",  "GROUND"): (8, 24),
    ("OUT",  "FLY"):    (30, 62),
    ("1B",   "GROUND"): (12, 27),
    ("1B",   "FLY"):    (28, 46),
    ("2B",   "FLY"):    (50, 68),
    ("3B",   "FLY"):    (68, 82),
    ("HR",   "FLY"):    (76, 96),
}


def pick_zone(zones):
    """가중치대로 존 하나를 뽑아 (이름, 각도(도), 추가진루배수, 호수비기준확률)을 반환."""
    total = sum(z[2] for z in zones)
    r = random.uniform(0, total)
    upto = 0.0
    for name, (lo, hi), weight, extra_mult, great_play_p in zones:
        upto += weight
        if r <= upto:
            return name, random.uniform(lo, hi), extra_mult, great_play_p
    name, (lo, hi), weight, extra_mult, great_play_p = zones[-1]
    return name, random.uniform(lo, hi), extra_mult, great_play_p


class FieldSim:

    def __init__(self, runners_on, def_stats=None, run_stats=None, is_hr=False, is_walk=False,
                 scripted=None):
        """scripted: {"outcome": "OUT"/"1B"/"2B"/"3B"/"HR", "trajectory": "GROUND"/"FLY"}
        가 주어지면, 타자의 최종 결과는 물리 판정이 아니라 이 값으로 미리 정해지고
        (호수비로 한 번 더 뒤집힐 수 있음), 타구 위치는 스펙의 존 테이블에서 뽑는다.
        기존 주자들의 포스아웃/추가진루 판정은 그대로 물리(레이스) 기반이다."""
        self.def_stats = def_stats or DEFAULT_DEF.copy()
        self.run_stats = run_stats or DEFAULT_RUN.copy()

        self._scripted_outcome = None
        self._scripted_final   = None
        self._scripted_target_base = None
        self._great_play_base  = 0.0
        self._extra_base_mult  = 1.0
        self._zone_name        = None

        if scripted is not None:
            outcome    = scripted["outcome"]
            trajectory = scripted.get("trajectory", "FLY")
            self._scripted_outcome = outcome
            is_hr = False  # 스크립트 모드에서는 아래 존 기반 경로로 통일 처리

            if outcome == "OUT":
                lo, hi = OUTCOME_DIST_RANGE[("OUT", trajectory)]
                angle_deg = random.uniform(0.0, 90.0)
                dist = random.uniform(lo, hi)
            else:
                zones = GROUND_ZONES if trajectory == "GROUND" else FLY_ZONES
                zone_name, angle_deg, extra_mult, great_play_p = pick_zone(zones)
                self._zone_name       = zone_name
                self._extra_base_mult = extra_mult
                self._great_play_base = great_play_p

                key = (outcome, "GROUND") if (outcome == "1B" and trajectory == "GROUND") else (outcome, "FLY")
                lo, hi = OUTCOME_DIST_RANGE.get(key, OUTCOME_DIST_RANGE[(outcome, "FLY")])
                dist = random.uniform(lo, hi)

            rad = math.radians(angle_deg)
            self.ball_pos    = [0.0, 0.0]
            self.ball_target = [dist * math.cos(rad), dist * math.sin(rad)]
            self.is_outfield = (trajectory == "FLY") or (dist >= 28)
        else:
            self.ball_pos = [0.0, 0.0]
            angle = random.uniform(0.05, math.pi / 2 - 0.05)
            dist  = random.uniform(10, 55)
            self.ball_target = [dist * math.cos(angle), dist * math.sin(angle)]
            self.is_outfield = (dist >= 28)

            # 홈런은 공이 훨씬 멀리 날아감 (스크립트 모드가 아닐 때의 구경로)
            if is_hr:
                hr_angle = random.uniform(0.1, math.pi / 2 - 0.1)
                hr_dist  = random.uniform(70, 90)
                self.ball_target = [hr_dist * math.cos(hr_angle), hr_dist * math.sin(hr_angle)]
                self.is_outfield = True

        self.state      = "FLYING"
        self.ball_owner = None
        self.throw_to   = None
        self.throw_type = "BASE"
        self.relay_done = False
        self.is_over    = False

        # 볼넷만 즉시 arrived, HR은 공이 날아간 뒤 arrived
        self._ball_arrived  = is_walk
        self._is_hr         = is_hr
        self._is_walk       = is_walk
        self._out_keys      = set()

        # 병살 관련
        self._dp_throw_to   = None   # 두 번째 송구 목표 베이스
        self._dp_done       = False  # 두 번째 송구 완료 여부

        self.fielders = {k: list(v) for k, v in INITIAL_FIELDERS.items()}
        self.cover_assignment = {}

        self.runners = {
            "B":  [0.0, 0.0],
            "R1": list(BASE_POS["1B"]) if runners_on[0] else None,
            "R2": list(BASE_POS["2B"]) if runners_on[1] else None,
            "R3": list(BASE_POS["3B"]) if runners_on[2] else None,
        }

        # 포스 상태를 미리 계산해둔다 (진루 시 "강제로 뛰어야 하는지" 판단용)
        self._forced = self._force_status()

        if is_hr:
            self._runner_target = {
                "R1": "HOME" if runners_on[0] else None,
                "R2": "HOME" if runners_on[1] else None,
                "R3": "HOME" if runners_on[2] else None,
            }
            self._batter_next = "HOME"
        elif is_walk:
            # 볼넷: 각 주자 한 칸씩만 이동
            # 밀리는 경우만 이동 (1루 주자 있어야 2루 주자 밀림, 1,2루 있어야 3루 밀림)
            r1, r2, r3 = runners_on
            self._runner_target = {
                "R1": "2B" if r1 else None,
                "R2": "3B" if (r1 and r2) else None,
                "R3": "HOME" if (r1 and r2 and r3) else None,
            }
            self._batter_next = "1B"
        elif self._scripted_outcome is not None:
            # 스크립트 모드: 실제 주루처럼 1루→2루→3루→홈 순서로 베이스를
            # 밟으며 달리되, 최종적으로 멈출 베이스(_scripted_target_base)는
            # 미리 정해진 결과를 따른다 (OUT이면 1루까지만 달리다가 잡히면 멈춤)
            self._runner_target = {
                "R1": "2B",
                "R2": "3B",
                "R3": "HOME",
            }
            SCRIPTED_BASE = {"OUT": "1B", "1B": "1B", "2B": "2B", "3B": "3B", "HR": "HOME"}
            self._scripted_target_base = SCRIPTED_BASE[self._scripted_outcome]
            self._batter_next = "1B"
        else:
            self._runner_target = {
                "R1": "2B",
                "R2": "3B",
                "R3": "HOME",
            }
            self._batter_next = "1B"

    # ── 유틸 ──────────────────────────────────────────────

    def _move(self, pos, target, speed):
        d = math.dist(pos, target)
        if d > speed:
            pos[0] += (target[0] - pos[0]) / d * speed
            pos[1] += (target[1] - pos[1]) / d * speed
        else:
            pos[0], pos[1] = float(target[0]), float(target[1])
        return d

    # ── 수비 ──────────────────────────────────────────────

    def _pick_throw_base(self):
        """실제 야구의 수비 판단: 포스 상태인 주자 중 가장 앞선(홈에 가까운)
        주자부터 "지금 던지면 아웃시킬 수 있는지"를 확인하고, 그중 우선순위가
        가장 높은 곳으로 송구한다. 아무도 잡을 수 없으면 타자 쪽(1루)으로 던진다.
        타자의 목표 베이스는 좌표를 다시 추정하지 않고 _move_batter가 계속
        추적해온 self._batter_next를 그대로 신뢰한다."""
        throw_speed = 2.0
        run_speed   = 0.35

        forced = self._force_status()
        target_base = {
            "B":  self._batter_next,
            "R1": "2B",
            "R2": "3B",
            "R3": "HOME",
        }

        # 홈에 가장 가까운(가장 앞선) 주자부터 우선 판단 - 실제 수비가
        # "잡을 수 있는 가장 리드된 주자"를 먼저 노리는 순서와 동일
        priority = ["R3", "R2", "R1", "B"]

        playable = []
        for key in priority:
            if not forced.get(key):
                continue  # 포스 상태가 아니면 태그 없이는 아웃시킬 수 없음
            pos = self.runners[key]
            if pos is None:
                continue
            base = target_base[key]
            base_pos = BASE_POS[base]
            ball_dist   = math.dist(self.ball_pos, base_pos)
            runner_dist = math.dist(pos, base_pos)
            ball_time   = ball_dist / throw_speed
            runner_time = runner_dist / run_speed
            if ball_time < runner_time:
                playable.append((key, base, runner_time - ball_time))

        if not playable:
            # 아무도 잡을 수 없으면 확실한 아웃(타자)을 시도
            return self._batter_next

        # 우선순위가 가장 높은 주자를 선택하고, 동순위면 여유시간이
        # 더 큰(더 확실하게 아웃시킬 수 있는) 쪽을 고른다.
        rank = {"R3": 0, "R2": 1, "R1": 2, "B": 3}
        playable.sort(key=lambda item: (rank[item[0]], -item[2]))
        return playable[0][1]

    def _force_status(self):
        """포스아웃 규칙: 타자는 항상 포스 상태. 주자는 자신의 바로 뒤
        베이스가 채워져 있어야(=뒤 주자가 있어야) 다음 베이스로 뛸 의무가
        생기는 포스 상태가 된다."""
        r1_forced = self.runners["R1"] is not None
        r2_forced = r1_forced and self.runners["R2"] is not None
        r3_forced = r2_forced and self.runners["R3"] is not None
        return {"B": True, "R1": r1_forced, "R2": r2_forced, "R3": r3_forced}


    def _can_beat_throw(self, pos, target_base, speed_mult=1.0):
        """pos에 있는 주자가 target_base까지, 그 베이스로 오는 송구보다
        먼저 도착할 수 있는지 판단한다. 포스가 아닌 주자와 타자의 추가
        진루 판단에 공통으로 쓰인다. speed_mult로 개인 주루 능력치나
        타구 존의 "추가진루 배수"를 반영할 수 있다."""
        throw_speed = 2.0
        run_speed   = 0.35 * speed_mult
        base_pos    = BASE_POS[target_base]
        ball_dist   = math.dist(self.ball_pos, base_pos)
        runner_dist = math.dist(pos, base_pos)
        return (runner_dist / run_speed) < (ball_dist / throw_speed)

    def _assign_fielder(self):
        catcher = min(
            self.fielders,
            key=lambda k: math.dist(self.fielders[k], self.ball_target)
                          / self.def_stats.get(k, 1.0)
        )
        self.ball_owner = catcher
        self._assign_cover(catcher)

    def _assign_cover(self, catcher):
        self.cover_assignment = {}
        if catcher == "1B":
            self.cover_assignment["P"] = "1B"
        elif catcher in OUTFIELDERS:
            relay = "SS" if catcher in ("LF", "CF") else "2B"
            self.cover_assignment[relay] = "2B"

    def _relay_fielder(self, catcher):
        if catcher in ("LF", "CF"): return "SS"
        if catcher == "RF":         return "2B"
        return None

    def _decide_nonforced_holds(self):
        """공이 수비수에게 잡히는 순간의 판단: 포스 상태가 아닌 주자는
        "다음 베이스까지 지금 공보다 먼저 도착할 수 있을 때만" 뛴다.
        (사용자 요청 규칙) 이길 수 없다고 판단되면 애초에 떠나지 않고
        원래 베이스에 머무른다. 타구 존의 추가진루 배수(_extra_base_mult)와
        각자의 주루 능력치(run_stats)를 함께 반영한다."""
        ORIGIN_BASE = {"R1": "1B", "R2": "2B", "R3": "3B"}
        for key in ("R1", "R2", "R3"):
            if self._forced.get(key):
                continue  # 포스 상태면 선택의 여지 없이 무조건 진루
            pos = self.runners[key]
            target_base = self._runner_target.get(key)
            if pos is None or target_base is None:
                continue
            speed_mult = self.run_stats.get(key, 1.0) * self._extra_base_mult
            if not self._can_beat_throw(pos, target_base, speed_mult):
                # 공보다 먼저 도착 못 한다고 판단 -> 애초에 뛰지 않고 원래 베이스에 정지
                self.runners[key] = list(BASE_POS[ORIGIN_BASE[key]])
                self._runner_target[key] = None

    def _resolve_scripted_batter(self):
        """스크립트 모드일 때, 공이 수비수에게 잡히는 순간 타자의 최종
        결과를 확정한다. 안타/홈런이었더라도 낮은 확률로 호수비에 걸려
        아웃으로 뒤집힐 수 있다 (홈런은 훨씬 더 낮은 확률)."""
        if self._scripted_outcome is None:
            return
        outcome = self._scripted_outcome
        if outcome != "OUT":
            catcher  = self.ball_owner
            def_stat = self.def_stats.get(catcher, 1.0)
            gp_chance = self._great_play_base * def_stat
            if outcome == "HR":
                gp_chance *= 0.15  # 홈런 강탈은 훨씬 더 낮은 확률로
            if random.random() < gp_chance:
                outcome = "OUT"
        self._scripted_final = outcome
        if outcome == "OUT":
            self._out_keys.add("B")

    # ── 메인 업데이트    # ── 메인 업데이트 ──────────────────────────────────────

    def update(self):
        if self.is_over:
            return

        # 볼넷: 야수·공 로직 없이 주자 이동만
        if self._is_walk:
            self._update_runners()
            self._check_end()
            return

        # 홈런: 공이 외야까지 날아간 뒤 주자 달리기 시작
        if self._is_hr:
            if not self._ball_arrived:
                d = self._move(self.ball_pos, self.ball_target, 1.5)
                if d < 1:
                    self._ball_arrived = True
            self._update_runners()
            self._check_end()
            return

        # 일반 인플레이
        if not self._ball_arrived:
            if self.state == "FLYING":
                d = self._move(self.ball_pos, self.ball_target, 1.2)
                closest = min(
                    self.fielders,
                    key=lambda k: math.dist(self.fielders[k], self.ball_target)
                                  / self.def_stats.get(k, 1.0)
                )
                self._move(self.fielders[closest], self.ball_target,
                           0.6 * self.def_stats.get(closest, 1.0))
                if d < 1:
                    self._assign_fielder()
                    self.ball_pos = list(self.fielders[self.ball_owner])
                    self._decide_nonforced_holds()
                    self._resolve_scripted_batter()
                    self.state    = "CAUGHT"
                    self.throw_to = self._pick_throw_base()

            elif self.state == "CAUGHT":
                self._do_throw()

        # 병살 두 번째 송구: _ball_arrived 이후에도 진행
        elif self._dp_throw_to and not self._dp_done:
            self._do_throw()

        self._update_runners()
        self._check_end()

    def _do_throw(self):
        catcher     = self.ball_owner
        throw_speed = 2.0 * self.def_stats.get(catcher, 1.0)
        run_speed   = 0.6 * self.def_stats.get(catcher, 1.0)

        # ── 두 번째 송구 (병살) ──
        if self._dp_throw_to and not self._dp_done:
            target_pos = BASE_POS[self._dp_throw_to]
            d = self._move(self.ball_pos, target_pos, throw_speed)
            if d < 1:
                self._dp_done = True
                self._judge_at_base(self._dp_throw_to)
            return

        # ── 첫 번째 송구 ──
        target_pos = BASE_POS[self.throw_to]
        d = self._move(self.ball_pos, target_pos, throw_speed)
        self._move(self.fielders[catcher], target_pos, run_speed)

        if d < 1 and not self._ball_arrived:
            self._ball_arrived = True
            self._judge_at_base(self.throw_to)
            # 병살 시도: 내야 타구이고 첫 아웃이 성공했으면 1루로 추가 송구
            self._try_double_play()

        for cover_fielder, cover_base in self.cover_assignment.items():
            if cover_fielder != catcher:
                self._move(self.fielders[cover_fielder], BASE_POS[cover_base],
                           1.3 * self.def_stats.get(cover_fielder, 1.0))

    def _try_double_play(self):
        """첫 번째 포스아웃 성공 후 병살 가능 여부 판단.
        실제 야구처럼 리드 러너를 먼저 잡은 뒤, 아직 아웃되지 않은 타자를
        1루에서 추가로 잡을 수 있는지 확인한다(2루→1루뿐 아니라 3루/홈에서
        포스아웃을 잡은 경우도 동일하게 시도)."""
        # 외야 타구는 병살 없음
        if self.is_outfield:
            return
        # 이미 1루로 송구했다면(=타자를 직접 노린 것) 추가 송구 없음
        if self.throw_to == "1B":
            return
        # 방금 송구로 주자가 포스아웃되지 않았으면 병살 시도 의미 없음
        if not any(k in self._out_keys for k in ("R1", "R2", "R3")):
            return
        # 타자가 이미 아웃 처리됐으면 추가 송구 불필요
        if "B" in self._out_keys:
            return

        bpos = self.runners["B"]
        ball_dist   = math.dist(BASE_POS[self.throw_to], BASE_POS["1B"])
        runner_dist = math.dist(bpos, BASE_POS["1B"])
        throw_speed = 2.0
        run_speed   = 0.35
        if ball_dist / throw_speed < runner_dist / run_speed:
            self._dp_throw_to = "1B"

    def _judge_at_base(self, base):
        """공이 base에 도달한 순간 해당 베이스로 향하는 주자/타자 OUT 판정."""
        base_pos = BASE_POS[base]
        TOL = 3.0

        # 타자: 공 도달 시점에 이 베이스가 목표일 때만 판정
        # (_batter_next가 이미 다음 베이스면 타자는 이미 이 베이스를 통과한 것)
        if self._scripted_outcome is None and self._batter_next == base:
            if math.dist(self.runners["B"], base_pos) > TOL:
                self._out_keys.add("B")

        # 기존 주자: 포스 베이스 기준 판정
        runner_base_map = {"R1": "2B", "R2": "3B", "R3": "HOME"}
        for key, force_base in runner_base_map.items():
            if force_base != base:
                continue
            pos = self.runners[key]
            if pos is None:
                continue
            # 주자의 현재 target이 이미 다음 베이스면 통과한 것 → 판정 안 함
            if self._runner_target.get(key) != base:
                continue
            if math.dist(pos, base_pos) > TOL:
                self._out_keys.add(key)

    # ── 주자 이동 ──────────────────────────────────────────

    def _update_runners(self):
        for k in ("R1", "R2", "R3"):
            if self.runners[k] is None:
                continue
            self._move_runner(k)
        self._move_batter()

    def _move_runner(self, key):
        NEXT = {"1B": "2B", "2B": "3B", "3B": "HOME", "HOME": None}

        if key in self._out_keys:
            return   # OUT -> 멈춤

        target_base = self._runner_target.get(key)
        if target_base is None:
            return   # 홈 통과

        pos    = self.runners[key]
        target = BASE_POS[target_base]
        speed  = 0.35 * self.run_stats.get(key, 1.0)
        d      = self._move(pos, target, speed)

        if d <= speed:
            if self._ball_arrived:
                return   # 공 도착 후 -> 현재 베이스에서 멈춤

            nxt = NEXT.get(target_base)
            if nxt is None:
                return   # 더 갈 베이스 없음(이미 홈으로 향하던 중)

            if self._forced.get(key) or self.state == "FLYING":
                # 포스 상태면 선택의 여지 없이 계속 진루해야 하고,
                # 공이 아직 날아가는 중이면(수비 위치를 알 수 없으니) 일단 전력 질주
                self._runner_target[key] = nxt
            elif self._can_beat_throw(pos, nxt, self.run_stats.get(key, 1.0) * self._extra_base_mult):
                # 포스가 아니면 실제 주자처럼 "다음 베이스까지 공보다 먼저
                # 도착할 수 있을 때만" 진루를 시도한다
                self._runner_target[key] = nxt
            # else: 그 자리에서 멈춘다 (target_base 그대로 유지)

    def _move_batter(self):
        if "B" in self._out_keys:
            return   # OUT → 멈춤

        pos    = self.runners["B"]
        speed  = 0.35 * self.run_stats.get("B", 1.0)
        target = BASE_POS[self._batter_next]
        d      = self._move(pos, target, speed)

        if d <= speed:
            # 스크립트 모드는 송구 도착 여부와 무관하게 정해진 결과
            # 베이스까지 계속 달린다 (도착 즉시 멈추면 결과와 애니메이션이
            # 어긋난다). 비-스크립트 모드는 기존처럼 송구 도착 시 멈춘다.
            if self._scripted_outcome is None and self._ball_arrived:
                return
            NEXT_MAP = {"1B": "2B", "2B": "3B", "3B": "HOME"}
            nxt = self._decide_advance(self._batter_next)
            if nxt:
                self._batter_next = nxt

    def _decide_advance(self, current_base):
        """타자가 다음 베이스로 계속 뛸지 결정.
        공이 날아가는 중이면 일단 전력 질주하고, 공이 잡힌 뒤에는 다음
        베이스까지 공보다 먼저 도착할 수 있을 때만 계속 뛴다."""
        NEXT_MAP = {"1B": "2B", "2B": "3B", "3B": "HOME"}
        nxt = NEXT_MAP.get(current_base)
        if nxt is None:
            return None
        if self._scripted_outcome is not None:
            # 스크립트 모드: 실제 베이스를 순서대로 밟아가되, 미리 정해진
            # 최종 베이스에 도달하면 멈춘다 (그 이후 판단은 없음)
            BASE_ORDER = {"1B": 1, "2B": 2, "3B": 3, "HOME": 4}
            if BASE_ORDER[current_base] < BASE_ORDER[self._scripted_target_base]:
                return nxt
            return None
        if self.state == "FLYING":
            return nxt
        speed_mult = self.run_stats.get("B", 1.0) * self._extra_base_mult
        return nxt if self._can_beat_throw(self.runners["B"], nxt, speed_mult) else None

    # ── 종료 판정 ──────────────────────────────────────────

    def _check_end(self):
        if not self._ball_arrived:
            return

        # 병살 두 번째 송구 진행 중이면 대기
        if self._dp_throw_to and not self._dp_done:
            return

        # 세이프 주자: 목표 베이스 도달 대기
        for key in ("R1", "R2", "R3"):
            if self.runners[key] is None:
                continue
            if key in self._out_keys:
                continue
            target = self._runner_target.get(key)
            if target is None:
                continue
            if math.dist(self.runners[key], BASE_POS[target]) > 0.1:
                return

        # 세이프 타자: 목표 베이스 도달 대기
        if "B" not in self._out_keys:
            if math.dist(self.runners["B"], BASE_POS[self._batter_next]) > 0.1:
                return

        self.is_over = True

    def get_result(self):
        """타자 결과: OUT / 1B / 2B / 3B / HR"""
        if self._scripted_outcome is not None:
            return self._scripted_final if self._scripted_final is not None else self._scripted_outcome
        if "B" in self._out_keys:
            return "OUT"
        pos = self.runners["B"]
        if math.dist(pos, BASE_POS["HOME"]) < 2.0: return "HR"
        if math.dist(pos, BASE_POS["3B"])   < 2.0: return "3B"
        if math.dist(pos, BASE_POS["2B"])   < 2.0: return "2B"
        if math.dist(pos, BASE_POS["1B"])   < 2.0: return "1B"
        return "OUT"

    def get_runner_outs(self):
        """타자 외 OUT된 주자 수."""
        return sum(1 for k in ("R1","R2","R3") if k in self._out_keys)

    def get_out_runner_indices(self):
        """OUT된 기존 주자의 bases 인덱스 목록 반환. R1=0, R2=1, R3=2."""
        return [i for i, k in enumerate(("R1","R2","R3")) if k in self._out_keys]

    def get_runner_final_bases(self):
        """OUT되지 않고 살아남은 기존 주자(R1/R2/R3)가 최종적으로 도착한
        베이스를 반환한다. 값은 "1B"/"2B"/"3B"/"HOME" 중 하나이며,
        "HOME"이면 득점한 것이다. OUT된 주자나 애초에 없던 주자는
        포함하지 않는다 (호출 측에서 apply_hit의 단순 베이스 shift 대신
        실제 포스/비포스 판단 결과를 반영할 때 사용)."""
        result = {}
        for key in ("R1", "R2", "R3"):
            if self.runners[key] is None or key in self._out_keys:
                continue
            result[key] = self._runner_target.get(key)
        return result


Simulation = FieldSim
