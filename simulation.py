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

# 타구 물리 상수: 비거리 FENCE_DIST 이상으로 뜬 타구는 홈런, 땅볼은
# 초기 구속에서 마찰(GROUND_FRICTION)로 감속하며 굴러간다.
FENCE_DIST       = 90.0
GROUND_FRICTION  = 0.97
ROLL_AFTER_LAND  = 0.55
GROUND_RATIO     = 0.46
GROUND_SPEED_MIN = 0.55
GROUND_SPEED_MAX = 2.4
FLY_DIST_MIN     = 14.0
FLY_DIST_MAX     = 112.0
FLY_SPEED_MIN    = 0.9
FLY_SPEED_MAX    = 2.0


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


def make_batted_ball(hardness):
    """타구 강도(0~1)로부터 타구 하나를 만든다.
    반환: {"trajectory": "GROUND"/"FLY", "angle": 각도(도),
           "dist": 낙하 비거리(FLY) 또는 "speed": 초기 구속(GROUND)}
    결과(아웃/안타/홈런)는 여기서 정하지 않고 FieldSim의 물리가 결정한다."""
    hardness = max(0.0, min(1.0, hardness))
    if random.random() < GROUND_RATIO:
        _, angle, _, _ = pick_zone(GROUND_ZONES)
        speed = GROUND_SPEED_MIN + (GROUND_SPEED_MAX - GROUND_SPEED_MIN) * hardness * random.uniform(0.75, 1.1)
        return {"trajectory": "GROUND", "angle": angle, "speed": speed}
    _, angle, _, _ = pick_zone(FLY_ZONES)
    dist = FLY_DIST_MIN + (FLY_DIST_MAX - FLY_DIST_MIN) * hardness * random.uniform(0.6, 1.05)
    fly_speed = FLY_SPEED_MIN + (FLY_SPEED_MAX - FLY_SPEED_MIN) * hardness * random.uniform(0.7, 1.1)
    return {"trajectory": "FLY", "angle": angle, "dist": dist, "fly_speed": fly_speed}


class FieldSim:
    """타구 이후의 수비/주루를 좌표 기반 물리로 끝까지 계산하는 시뮬레이터.

    타자의 결과(아웃/안타 종류/홈런)는 미리 정해져 있지 않고, 타구의
    성질(batted: 궤적/각도/비거리 또는 구속)과 수비수·주자의 위치와 속도가
    만나서 자연스럽게 결정된다.
      - 뜬공: 낙하 지점에 수비수가 먼저 도착하면 포구(아웃), 아니면 안타
      - 땅볼: 공이 구르는 경로를 수비수가 가로채면 처리, 못 잡으면 안타
      - 비거리가 펜스(FENCE_DIST) 이상이면 홈런
      - 이후의 송구/포스아웃/태그업/추가진루는 모두 위치와 속도 경쟁으로 판정
    """

    FLY_SPEED     = 1.2    # 뜬공 비행 속도 (프레임당)
    HR_FLY_SPEED  = 1.5    # 홈런 타구 비행 속도
    THROW_SPEED   = 2.0    # 송구 속도
    RUN_SPEED     = 0.45   # 주자 기본 속도
    FIELD_SPEED   = 0.50    # 수비수 기본 이동 속도
    CATCH_RADIUS  = 2.0    # 뜬공 포구 가능 반경
    PICKUP_RADIUS = 1.0    # 땅볼/루즈볼 처리 반경
    RELEASE_DELAY = 21     # 포구 후 송구 동작까지 걸리는 프레임
    REACTION_DELAY = 14    # 타구 직후 수비수가 반응하기까지 걸리는 프레임

    def __init__(self, runners_on, def_stats=None, run_stats=None, is_walk=False,
                 batted=None, outs=0):
        """batted: {"trajectory": "GROUND"/"FLY", "angle": 각도(도),
                    "dist": 낙하 비거리(FLY), "speed": 초기 구속(GROUND)}
        None이면 무작위 타구를 만든다. outs: 이 타구 직전의 아웃카운트."""
        self.def_stats = def_stats or DEFAULT_DEF.copy()
        self.run_stats = run_stats or DEFAULT_RUN.copy()
        self._outs_before = outs
        self._extra_base_mult = 1.0
        self._release_wait = 0
        self._t = 0            # 타구 이후 경과 프레임
        self._fly_speed = self.FLY_SPEED
        self._chase_speed = 0.0   # 낙하 후 굴러가는 속도

        self.trajectory   = "FLY"
        self._ball_speed  = 0.0
        self._dir         = (1.0, 0.0)
        self._is_hr       = False
        self.is_outfield  = False
        self.ball_pos     = [0.0, 0.0]
        self.ball_target  = [0.0, 0.0]

        if batted is None and not is_walk:
            batted = make_batted_ball(random.random())
        if batted is not None and not is_walk:
            self.trajectory = batted["trajectory"]
            rad = math.radians(batted["angle"])
            self._dir = (math.cos(rad), math.sin(rad))
            if self.trajectory == "FLY":
                dist = batted["dist"]
                self.ball_target = [dist * self._dir[0], dist * self._dir[1]]
                self._is_hr      = dist >= FENCE_DIST
                self._fly_speed  = batted.get("fly_speed", self.FLY_SPEED)
                self.is_outfield = True
            else:
                self._ball_speed = batted["speed"]

        self.state      = "FLYING" if self.trajectory == "FLY" else "ROLLING"
        self.ball_owner = None
        self.throw_to   = None
        self.throw_type = "BASE"
        self.relay_done = False
        self.is_over    = False

        # 볼넷만 즉시 arrived, 그 외는 수비가 끝나야 arrived
        self._ball_arrived = is_walk
        self._is_walk      = is_walk
        self._out_keys     = set()

        # 병살 관련
        self._dp_throw_to = None
        self._dp_done     = False

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

        if is_walk:
            # 볼넷: 밀리는 주자만 한 칸씩 이동
            r1, r2, r3 = runners_on
            self._runner_target = {
                "R1": "2B" if r1 else None,
                "R2": "3B" if (r1 and r2) else None,
                "R3": "HOME" if (r1 and r2 and r3) else None,
            }
        else:
            self._runner_target = {"R1": "2B", "R2": "3B", "R3": "HOME"}
        self._batter_next = "1B"

        # 뜬공은 낙하/포구 결과를 보고 움직이는 것이 원칙이라 주자가 출발을
        # 미룬다. 단, 2아웃이거나 홈런이면 처음부터 전력 질주한다.
        self._runners_go = (self.trajectory == "GROUND" or outs >= 2
                            or self._is_hr or is_walk)

    # ── 유틸 ──────────────────────────────────────────────

    def _move(self, pos, target, speed):
        d = math.dist(pos, target)
        if d > speed:
            pos[0] += (target[0] - pos[0]) / d * speed
            pos[1] += (target[1] - pos[1]) / d * speed
        else:
            pos[0], pos[1] = float(target[0]), float(target[1])
        return d

    def _ball_loose(self):
        """공이 아직 수비수 손에 들어오지 않은 상태인지."""
        return self.state in ("FLYING", "ROLLING", "CHASING")

    def _closest_fielder(self, point):
        return min(
            self.fielders,
            key=lambda k: math.dist(self.fielders[k], point)
                          / self.def_stats.get(k, 1.0)
        )

    # ── 수비 판단 ─────────────────────────────────────────

    def _pick_throw_base(self):
        """포스 상태인 주자 중 가장 앞선 주자부터 "지금 던지면 아웃시킬 수
        있는지" 확인해 송구한다. 아무도 잡을 수 없으면 타자 쪽으로 던진다."""
        forced = self._force_status()
        target_base = {
            "B":  self._batter_next,
            "R1": "2B",
            "R2": "3B",
            "R3": "HOME",
        }
        priority = ["R3", "R2", "R1", "B"]

        playable = []
        for key in priority:
            if not forced.get(key):
                continue
            if key in self._out_keys:
                continue
            pos = self.runners[key]
            if pos is None:
                continue
            base = target_base[key]
            base_pos = BASE_POS[base]
            ball_time   = math.dist(self.ball_pos, base_pos) / self.THROW_SPEED + self.RELEASE_DELAY
            runner_time = math.dist(pos, base_pos) / (self.RUN_SPEED * self.run_stats.get(key, 1.0))
            if ball_time < runner_time:
                playable.append((key, base, runner_time - ball_time))

        if not playable:
            return self._batter_next

        rank = {"R3": 0, "R2": 1, "R1": 2, "B": 3}
        playable.sort(key=lambda item: (rank[item[0]], -item[2]))
        return playable[0][1]

    def _force_status(self):
        """타자는 항상 포스. 주자는 자신의 뒤 베이스가 채워져 있어야 포스."""
        r1_forced = self.runners["R1"] is not None
        r2_forced = r1_forced and self.runners["R2"] is not None
        r3_forced = r2_forced and self.runners["R3"] is not None
        return {"B": True, "R1": r1_forced, "R2": r2_forced, "R3": r3_forced}

    def _can_beat_throw(self, pos, target_base, speed_mult=1.0):
        """pos의 주자가 target_base까지 그 베이스로 오는 송구보다 먼저
        도착할 수 있는지. 아직 송구 동작 전이면 그 지연도 반영한다."""
        run_speed   = self.RUN_SPEED * speed_mult
        base_pos    = BASE_POS[target_base]
        ball_time   = math.dist(self.ball_pos, base_pos) / self.THROW_SPEED
        if self.state == "CAUGHT":
            ball_time += self._release_wait
        runner_time = math.dist(pos, base_pos) / run_speed
        return runner_time < ball_time

    def _assign_cover(self, catcher):
        self.cover_assignment = {}
        if catcher == "1B":
            self.cover_assignment["P"] = "1B"
        elif catcher in OUTFIELDERS:
            relay = "SS" if catcher in ("LF", "CF") else "2B"
            self.cover_assignment[relay] = "2B"

    def _decide_nonforced_holds(self):
        """공이 수비수 손에 들어온 순간, 포스가 아닌 주자는 다음 베이스까지
        공보다 먼저 도착할 수 있을 때만 계속 뛰고, 아니면 원래 베이스에 남는다."""
        ORIGIN_BASE = {"R1": "1B", "R2": "2B", "R3": "3B"}
        for key in ("R1", "R2", "R3"):
            if self._forced.get(key):
                continue
            pos = self.runners[key]
            target_base = self._runner_target.get(key)
            if pos is None or target_base is None:
                continue
            speed_mult = self.run_stats.get(key, 1.0) * self._extra_base_mult
            if not self._can_beat_throw(pos, target_base, speed_mult):
                self.runners[key] = list(BASE_POS[ORIGIN_BASE[key]])
                self._runner_target[key] = None

    # ── 공의 진행 (상태별) ────────────────────────────────

    def _fielded(self, k):
        """수비수 k가 공을 처리했다 → 송구 단계로."""
        self.ball_owner  = k
        self.ball_pos    = list(self.fielders[k])
        self.is_outfield = k in OUTFIELDERS
        self._assign_cover(k)
        self._decide_nonforced_holds()
        self.state         = "CAUGHT"
        self._release_wait = self.RELEASE_DELAY
        self.throw_to      = self._pick_throw_base()

    @property
    def ball_height(self):
        """타구의 화면상 높이(픽셀). 뜬공이 날아가는 동안만 포물선, 그 외는 0.
        그리기 전용이며 판정에는 쓰이지 않는다."""
        if self.state != "FLYING" or self.trajectory != "FLY":
            return 0.0
        total = math.hypot(self.ball_target[0], self.ball_target[1])
        if total <= 0:
            return 0.0
        t = min(1.0, math.hypot(self.ball_pos[0], self.ball_pos[1]) / total)
        peak = min(110.0, 8.0 + total * 0.9)
        return peak * 4.0 * t * (1.0 - t)

    def _update_flying(self):
        d = self._move(self.ball_pos, self.ball_target, self._fly_speed)
        k = self._closest_fielder(self.ball_target)
        if self._t >= self.REACTION_DELAY:
            self._move(self.fielders[k], self.ball_target,
                       self.FIELD_SPEED * self.def_stats.get(k, 1.0))
        if d < 1:
            self.ball_pos = list(self.ball_target)
            if math.dist(self.fielders[k], self.ball_target) <= self.CATCH_RADIUS:
                self._on_fly_caught(k)
            else:
                self.state = "CHASING"
                self._chase_speed = ROLL_AFTER_LAND * self._fly_speed
                self._runners_go = True

    def _update_rolling(self):
        v = self._ball_speed
        self.ball_pos[0] += self._dir[0] * v
        self.ball_pos[1] += self._dir[1] * v
        self._ball_speed *= GROUND_FRICTION
        remaining = self._ball_speed / (1.0 - GROUND_FRICTION)

        cands = []
        for k, pos in self.fielders.items():
            rx, ry = pos[0] - self.ball_pos[0], pos[1] - self.ball_pos[1]
            t = max(0.0, min(remaining, rx * self._dir[0] + ry * self._dir[1]))
            tgt = (self.ball_pos[0] + self._dir[0] * t, self.ball_pos[1] + self._dir[1] * t)
            cands.append((math.dist(pos, tgt) / self.def_stats.get(k, 1.0), k, tgt))
        cands.sort(key=lambda c: c[0])

        if self._t >= self.REACTION_DELAY:
            for _, k, tgt in cands[:2]:
                self._move(self.fielders[k], tgt, self.FIELD_SPEED * self.def_stats.get(k, 1.0))
        for _, k, _tgt in cands:
            if math.dist(self.fielders[k], self.ball_pos) <= self.PICKUP_RADIUS:
                self._fielded(k)
                return
        if self._ball_speed < 0.12:
            self.ball_target = list(self.ball_pos)
            self.state = "CHASING"

    def _update_chasing(self):
        # 낙하한 타구는 잠시 더 굴러간다 (외야 담장에서 멈춤)
        if self._chase_speed > 0.05:
            nx = self.ball_target[0] + self._dir[0] * self._chase_speed
            ny = self.ball_target[1] + self._dir[1] * self._chase_speed
            if math.hypot(nx, ny) >= FENCE_DIST - 2:
                self._chase_speed = 0.0
            else:
                self.ball_target = [nx, ny]
                self.ball_pos = [nx, ny]
                self._chase_speed *= 0.95
        k = self._closest_fielder(self.ball_target)
        self._move(self.fielders[k], self.ball_target,
                   self.FIELD_SPEED * self.def_stats.get(k, 1.0))
        if math.dist(self.fielders[k], self.ball_target) <= self.PICKUP_RADIUS:
            self.ball_pos = list(self.ball_target)
            self._fielded(k)

    def _on_fly_caught(self, k):
        """뜬공 포구 → 타자 아웃. 주자는 태그업이 가능할 때만 진루한다."""
        ORIGIN_BASE = {"R1": "1B", "R2": "2B", "R3": "3B"}
        self.ball_owner  = k
        self.ball_pos    = list(self.fielders[k])
        self.is_outfield = k in OUTFIELDERS
        self._out_keys.add("B")
        self._assign_cover(k)
        self.state         = "CAUGHT"
        self._release_wait = self.RELEASE_DELAY
        self._runners_go   = True

        deep = self.is_outfield and math.dist(self.ball_pos, (0, 0)) >= 35
        for key in ("R1", "R2", "R3"):
            if self.runners[key] is None:
                continue
            tgt = self._runner_target.get(key)
            if tgt is None:
                continue
            origin = BASE_POS[ORIGIN_BASE[key]]
            mult = self.run_stats.get(key, 1.0)
            if deep and self._can_beat_throw(origin, tgt, mult):
                self.runners[key] = list(origin)   # 태그업: 포구 순간 출발
                continue
            self.runners[key] = list(origin)
            self._runner_target[key] = None

        for key, base in (("R3", "HOME"), ("R2", "3B"), ("R1", "2B")):
            if self.runners[key] is not None and self._runner_target.get(key) == base:
                self.throw_to = base
                return
        self.throw_to = None
        self._ball_arrived = True   # 던질 곳이 없음
        self.state = "DEAD"

    # ── 메인 업데이트 ─────────────────────────────────────

    def update(self):
        if self.is_over:
            return
        self._t += 1

        # 볼넷: 야수·공 로직 없이 주자 이동만
        if self._is_walk:
            self._update_runners()
            self._check_end()
            return

        # 홈런: 공이 담장 밖으로 날아가는 동안 모두 베이스를 순서대로 돈다
        if self._is_hr:
            if not self._ball_arrived:
                d = self._move(self.ball_pos, self.ball_target, self.HR_FLY_SPEED)
                if d < 1:
                    self._ball_arrived = True
            self._update_runners()
            self._check_end()
            return

        if not self._ball_arrived:
            if self.state == "FLYING":
                self._update_flying()
            elif self.state == "ROLLING":
                self._update_rolling()
            elif self.state == "CHASING":
                self._update_chasing()
            elif self.state == "CAUGHT":
                self._do_throw()
        elif self._dp_throw_to and not self._dp_done:
            self._do_throw()

        self._update_runners()
        self._check_end()

    def _do_throw(self):
        catcher     = self.ball_owner
        throw_speed = self.THROW_SPEED * self.def_stats.get(catcher, 1.0)
        run_speed   = 0.6 * self.def_stats.get(catcher, 1.0)

        # ── 두 번째 송구 (병살) ──
        if self._dp_throw_to and not self._dp_done:
            target_pos = BASE_POS[self._dp_throw_to]
            d = self._move(self.ball_pos, target_pos, throw_speed)
            if d < 1:
                self._dp_done = True
                self._judge_at_base(self._dp_throw_to)
            return

        # 포구 직후 송구 동작 시간
        if self._release_wait > 0:
            self._release_wait -= 1
            return

        # ── 첫 번째 송구 ──
        target_pos = BASE_POS[self.throw_to]
        d = self._move(self.ball_pos, target_pos, throw_speed)
        self._move(self.fielders[catcher], target_pos, run_speed)

        if d < 1 and not self._ball_arrived:
            self._ball_arrived = True
            self._judge_at_base(self.throw_to)
            self._try_double_play()

        for cover_fielder, cover_base in self.cover_assignment.items():
            if cover_fielder != catcher:
                self._move(self.fielders[cover_fielder], BASE_POS[cover_base],
                           1.3 * self.def_stats.get(cover_fielder, 1.0))

    def _try_double_play(self):
        """첫 포스아웃 성공 후, 아직 아웃되지 않은 타자를 1루에서 추가로
        잡을 수 있는지 판단한다 (내야 땅볼일 때만)."""
        if self.is_outfield or self.trajectory != "GROUND":
            return
        if self.throw_to == "1B":
            return
        if not any(k in self._out_keys for k in ("R1", "R2", "R3")):
            return
        if "B" in self._out_keys:
            return

        bpos = self.runners["B"]
        ball_time   = math.dist(BASE_POS[self.throw_to], BASE_POS["1B"]) / self.THROW_SPEED
        runner_time = math.dist(bpos, BASE_POS["1B"]) / (self.RUN_SPEED * self.run_stats.get("B", 1.0))
        if ball_time < runner_time:
            self._dp_throw_to = "1B"

    def _judge_at_base(self, base):
        """공이 base에 도달한 순간 해당 베이스로 향하는 주자/타자 OUT 판정."""
        base_pos = BASE_POS[base]
        TOL = 3.0

        # 타자: 이 베이스가 목표이고 아직 도착하지 못했으면 아웃
        if self._batter_next == base:
            if math.dist(self.runners["B"], base_pos) > TOL:
                self._out_keys.add("B")

        runner_base_map = {"R1": "2B", "R2": "3B", "R3": "HOME"}
        for key, force_base in runner_base_map.items():
            if force_base != base:
                continue
            pos = self.runners[key]
            if pos is None:
                continue
            if self._runner_target.get(key) != base:
                continue
            if math.dist(pos, base_pos) > TOL:
                self._out_keys.add(key)

    # ── 주자 이동 ─────────────────────────────────────────

    def _update_runners(self):
        if self._runners_go:
            for k in ("R1", "R2", "R3"):
                if self.runners[k] is None:
                    continue
                self._move_runner(k)
        self._move_batter()

    def _move_runner(self, key):
        NEXT = {"1B": "2B", "2B": "3B", "3B": "HOME", "HOME": None}

        if key in self._out_keys:
            return

        target_base = self._runner_target.get(key)
        if target_base is None:
            return

        pos    = self.runners[key]
        target = BASE_POS[target_base]
        speed  = self.RUN_SPEED * self.run_stats.get(key, 1.0)
        d      = self._move(pos, target, speed)

        if d <= speed:
            if self._ball_arrived and not self._is_hr:
                return   # 공 도착 후 -> 현재 베이스에서 멈춤

            nxt = NEXT.get(target_base)
            if nxt is None:
                return

            if self._is_hr or self._forced.get(key) or self._ball_loose():
                # 홈런/포스/공이 아직 수비수 손에 없으면 계속 달린다
                self._runner_target[key] = nxt
            elif self._can_beat_throw(pos, nxt, self.run_stats.get(key, 1.0) * self._extra_base_mult):
                self._runner_target[key] = nxt

    def _move_batter(self):
        if "B" in self._out_keys:
            return

        pos    = self.runners["B"]
        speed  = self.RUN_SPEED * self.run_stats.get("B", 1.0)
        target = BASE_POS[self._batter_next]
        d      = self._move(pos, target, speed)

        if d <= speed:
            if self._ball_arrived and not self._is_hr:
                return
            nxt = self._decide_advance(self._batter_next)
            if nxt:
                self._batter_next = nxt

    def _decide_advance(self, current_base):
        """타자가 다음 베이스로 계속 뛸지 결정. 홈런이거나 공이 아직 수비수
        손에 없으면 전력 질주, 이후에는 송구보다 먼저 도착할 수 있을 때만."""
        NEXT_MAP = {"1B": "2B", "2B": "3B", "3B": "HOME"}
        nxt = NEXT_MAP.get(current_base)
        if nxt is None:
            return None
        if self._is_hr or self._ball_loose():
            return nxt
        speed_mult = self.run_stats.get("B", 1.0) * self._extra_base_mult
        return nxt if self._can_beat_throw(self.runners["B"], nxt, speed_mult) else None

    # ── 종료 판정 ─────────────────────────────────────────

    def _check_end(self):
        if not self._ball_arrived:
            return

        if self._dp_throw_to and not self._dp_done:
            return

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

        if "B" not in self._out_keys:
            if math.dist(self.runners["B"], BASE_POS[self._batter_next]) > 0.1:
                return

        self.is_over = True

    def get_result(self):
        """타자 결과: OUT / 1B / 2B / 3B / HR (타자가 멈춘 베이스로 판정)"""
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
        return sum(1 for k in ("R1", "R2", "R3") if k in self._out_keys)

    def get_out_runner_indices(self):
        """OUT된 기존 주자의 bases 인덱스 목록 반환. R1=0, R2=1, R3=2."""
        return [i for i, k in enumerate(("R1", "R2", "R3")) if k in self._out_keys]

    def _third_out_blocks_runs(self):
        """이 플레이로 3아웃이 되었고, 타자 아웃 또는 포스아웃이 포함되어
        있으면 득점이 인정되지 않는다 (야구 규칙의 근사)."""
        total_outs = self._outs_before + len(self._out_keys)
        if total_outs < 3:
            return False
        if "B" in self._out_keys:
            return True
        forced = self._force_status()
        return any(k in self._out_keys and forced.get(k) for k in ("R1", "R2", "R3"))

    def get_runner_final_bases(self):
        """OUT되지 않고 살아남은 기존 주자(R1/R2/R3)가 최종 도착한 베이스.
        "HOME"이면 득점. 값이 None이면 출발하지 않고 원래 베이스에 남은 것.
        3아웃으로 득점이 무효가 되는 경우 득점(HOME)은 제외한다."""
        block = self._third_out_blocks_runs()
        result = {}
        for key in ("R1", "R2", "R3"):
            if self.runners[key] is None or key in self._out_keys:
                continue
            base = self._runner_target.get(key)
            if block and base == "HOME":
                base = None
            result[key] = base
        return result


Simulation = FieldSim
