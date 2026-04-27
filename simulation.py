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


class FieldSim:

    def __init__(self, runners_on, def_stats=None, run_stats=None, is_hr=False, is_walk=False):
        self.def_stats = def_stats or DEFAULT_DEF.copy()
        self.run_stats = run_stats or DEFAULT_RUN.copy()

        self.ball_pos = [0.0, 0.0]
        angle = random.uniform(0.05, math.pi / 2 - 0.05)
        dist  = random.uniform(10, 55)
        self.ball_target = [dist * math.cos(angle), dist * math.sin(angle)]
        self.is_outfield = (dist >= 28)

        # 홈런은 공이 훨씬 멀리 날아감
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
        throw_speed = 2.0
        run_speed   = 0.35

        candidates = []

        # 타자: _batter_next 뿐만 아니라 실제 위치 기준으로 가장 가까운 다음 베이스 판단
        batter_pos = self.runners["B"]
        BASE_ORDER = ["1B", "2B", "3B", "HOME"]
    
        # 타자가 현재 어느 베이스를 향하고 있는지 실제 위치로 재계산
        batter_actual_next = self._batter_next
        for base in BASE_ORDER:
            base_pos = BASE_POS[base]
            # 타자가 이미 이 베이스를 지났는지 확인 (베이스까지 거리가 매우 가까우면 지난 것)
            if math.dist(batter_pos, base_pos) < 3.0:
                # 이 베이스에 거의 도달 → 다음 베이스가 실제 목표
                next_idx = BASE_ORDER.index(base) + 1
                if next_idx < len(BASE_ORDER):
                    batter_actual_next = BASE_ORDER[next_idx]
                break
        #    타자가 이 베이스보다 홈에서 더 멀리 있으면 이미 지난 것
            home_to_base = math.dist(BASE_POS["HOME"], base_pos)
            home_to_batter = math.dist(BASE_POS["HOME"], batter_pos)
            if home_to_batter > home_to_base + 3.0:
                continue
            batter_actual_next = base
            break

        candidates.append((batter_actual_next, batter_pos))

        # 기존 주자 포스 아웃
        r1 = self.runners["R1"] is not None
        r2 = self.runners["R2"] is not None
        r3 = self.runners["R3"] is not None

        if r1:
            candidates.append(("2B", self.runners["R1"]))
        if r1 and r2:
            candidates.append(("3B", self.runners["R2"]))
        if r1 and r2 and r3:
            candidates.append(("HOME", self.runners["R3"]))

        best_base = None
        best_base_dist = -1

        for base, runner_pos in candidates:
            base_pos    = BASE_POS[base]
            ball_dist   = math.dist(self.ball_pos, base_pos)
            runner_dist = math.dist(runner_pos, base_pos)
            ball_time   = ball_dist / throw_speed
            runner_time = runner_dist / run_speed

            if ball_time < runner_time:
                if ball_dist > best_base_dist:
                    best_base = base
                    best_base_dist = ball_dist

        return best_base if best_base else batter_actual_next

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

    # ── 메인 업데이트 ──────────────────────────────────────

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
        """첫 번째 아웃 성공 후 병살 가능 여부 판단, 가능하면 1루로 추가 송구 설정."""
        # 외야 타구는 병살 없음
        if self.is_outfield:
            return
        # 첫 번째 아웃이 2루 (R1 포스아웃) 인 경우만 → 1루로 추가 송구
        if self.throw_to != "2B":
            return
        if "R1" not in self._out_keys:
            return
        # 타자가 아직 1루에 가까이 없으면 아웃 가능
        bpos = self.runners["B"]
        ball_dist   = math.dist(BASE_POS["2B"], BASE_POS["1B"])  # 2루→1루 송구 거리
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
        if self._batter_next == base:
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
            return   # OUT → 멈춤

        target_base = self._runner_target.get(key)
        if target_base is None:
            return   # 홈 통과

        pos    = self.runners[key]
        target = BASE_POS[target_base]
        speed  = 0.35 * self.run_stats.get(key, 1.0)
        d      = self._move(pos, target, speed)

        if d <= speed:
            if self._ball_arrived:
                pass   # 공 도착 후 → 현재 베이스에서 멈춤
            else:
                self._runner_target[key] = NEXT.get(target_base)

    def _move_batter(self):
        if "B" in self._out_keys:
            return   # OUT → 멈춤

        pos    = self.runners["B"]
        speed  = 0.35 * self.run_stats.get("B", 1.0)
        target = BASE_POS[self._batter_next]
        d      = self._move(pos, target, speed)

        if d <= speed:
            if self._ball_arrived:
                return
            NEXT_MAP = {"1B": "2B", "2B": "3B", "3B": "HOME"}
            nxt = self._decide_advance(self._batter_next)
            if nxt:
                self._batter_next = nxt

    def _decide_advance(self, current_base):
        """타자가 다음 베이스로 계속 뛸지 결정."""
        NEXT_MAP = {"1B": "2B", "2B": "3B", "3B": "HOME"}
        if self.state != "FLYING":
            if self.is_outfield:
                return NEXT_MAP.get(current_base)
            return None
        return NEXT_MAP.get(current_base)

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


Simulation = FieldSim