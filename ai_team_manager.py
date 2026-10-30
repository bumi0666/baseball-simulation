"""AI 구단(유저 외 팀)의 영입·방출·재계약 의사결정.

선수 가치 판단은 ai_advisor와 같은 모델(학습된 NN, 없으면 OVR 규칙)을 쓴다.
  - 매일: 계약이 만료된 선수를 재계약하거나 방출(FA)한다.
  - 7일마다(팀별로 요일을 어긋나게): 포지션별로 FA 최고 후보가 현 주전보다
    충분히 낫고 임금 한도 안이면 영입하고, 대신 그 포지션 최하위 선수를 방출한다.
"""
import os
import sys
from datetime import date, timedelta

import numpy as np

import ai_advisor

CYCLE_DAYS = 14             # 팀당 영입 검토 주기
MAX_MOVES_PER_CYCLE = 1     # 한 번에 최대 영입 수
GAIN_THRESHOLD = 0.30       # 득실차(점/경기) 이 이상 좋아질 때만 교체
RENEW_MARGIN = 0.30         # 재계약 시 FA 대안이 이만큼 더 좋으면 방출
MAX_SIGNINGS_PER_YEAR = 4   # 기본 연간 FA 영입 상한(재계약 대체 포함). 구단 성향별로 다름
FA_POOL_PER_POS = 15        # 포지션별로 검토할 FA 후보 수 (OVR 상위)
ROSTER_NEED = {"P": 5}      # 선발 투수 5명, 나머지 포지션은 1명
FA_PREMIUM = 1.15           # 계약 화면의 FA 프리미엄과 같은 값


POLICY_TOP = 3              # 정책에 보여 줄 포지션별 후보 수 (학습 때와 같게 OVR 상위 3명)
BASE_WAGE_CAP = 3_000_000   # 재정이 평균(예산 3,700만)인 구단의 임금 상한
REF_BUDGET = 37_000_000
REPL_OVR = 70               # 대체 선수 수준 OVR (계약 기간 계산용)
REPL_SALARY = 60_000
OVR_RUNS = 0.03             # OVR 1점당 득실차(점/경기) 근사
YEAR_DISCOUNT = 0.9         # 계약 기간 계산 시 연도별 할인율

# 구단 성향: youth=잠재력·젊음 가중, signings=연간 영입 상한, risk=계약 1년 연장당 위험 비용(점/경기),
# noop=영입 문턱(+면 보수적, 규칙 기반 대체용), max_years=최장 계약, cap_mult=임금 상한 보정,
# sal_w=연봉 비용 가중, move_w=영입 1회 비용 가중 (정책 학습 환경과 같은 값, 정책 입력으로 들어간다),
# staff_w=스태프 연봉 10만당 비용(별 1개 가치 대비): 클수록 비싼 스태프를 꺼린다, patience=미래 가치 할인(클수록 먼 미래까지 본다; 드래프트·스태프 정책 입력)
STYLES = {
    "WinNow":     dict(label="즉시 전력", patience=0.80, staff_w=0.25, sal_w=0.7, move_w=0.8, youth=0.3, signings=4, risk=0.04, noop=0.00, max_years=3, cap_mult=1.00),
    "Youth":      dict(label="유망주 육성", patience=0.95, staff_w=0.4, sal_w=1.0, move_w=1.3, youth=1.6, signings=4, risk=0.04, noop=0.03, max_years=5, cap_mult=1.00),
    "Balanced":   dict(label="균형", patience=0.90, staff_w=0.4, sal_w=1.0, move_w=1.0, youth=0.8, signings=4, risk=0.05, noop=0.00, max_years=4, cap_mult=1.00),
    "BigSpender": dict(label="큰손", patience=0.90, staff_w=0.15, sal_w=0.5, move_w=0.6, youth=0.5, signings=5, risk=0.02, noop=-0.05, max_years=5, cap_mult=1.10),
    "Frugal":     dict(label="긴축", patience=0.88, staff_w=0.8, sal_w=1.8, move_w=1.5, youth=0.8, signings=3, risk=0.10, noop=0.12, max_years=2, cap_mult=0.90),
}


def ensure_profiles(state):
    """AI 구단별 재정(임금 상한)과 성향을 한 번 정해 state.team_profiles(저장됨)에 둔다.
    재정은 team_data의 budget·finance_status에서, 성향은 재정 상태와 팀 이름 시드로 정해진다."""
    import random
    book = state.__dict__.setdefault("team_profiles", {})
    for team in state.team_rosters:
        if team in ("FA", "DRAFT", None) or team in book:
            continue
        td = getattr(state, "team_data", {}).get(team, {})
        budget = td.get("budget", REF_BUDGET)
        fin = td.get("finance_status", "Stable")
        rnd = random.Random("profile:" + str(team))
        pool = {"Rich": ["WinNow", "BigSpender", "Balanced"], "Insecure": ["Frugal"]}.get(
            fin, ["Balanced", "Youth", "WinNow"])
        style = rnd.choice(pool)
        cap = BASE_WAGE_CAP * (budget / REF_BUDGET) ** 0.5 * STYLES[style]["cap_mult"]
        book[team] = {"style": style, "wage_cap": int(cap)}
    return book


def stagger_contracts(state, today, include_user=False):
    """초기 데이터에서 AI 구단 선수 계약이 모두 같은 날 끝나는 문제를 풀기 위해, 한 번만 계약 만료를 분산한다.
    선수별 시드로 1~5년을 뽑는다(젊을수록 길고, 노장은 짧다). state.team_profiles['_staggered']에 완료를 기록해 저장·로드 후에도 반복되지 않는다."""
    import random
    book = state.__dict__.setdefault("team_profiles", {})
    if book.get("_staggered"):
        return 0
    n = 0
    for team, roster in state.team_rosters.items():
        if team in ("FA", "DRAFT", None) or (team == state.user_team and not include_user):
            continue
        for p in roster:
            end = p.contract_end()
            try:
                end_d = date.fromisoformat(end) if end else None
            except ValueError:
                end_d = None
            if end_d is None or end_d <= today:
                continue
            age = p.age() or 28
            rnd = random.Random("stagger:%s:%s" % (p.name, getattr(p, "id", "")))
            w = [1, 2, 3, 2, 2] if age <= 25 else [3, 3, 2, 1, 1] if age <= 30 else [5, 3, 1, 0, 0]
            years = rnd.choices([1, 2, 3, 4, 5], weights=w)[0]
            p.contract["end"] = (end_d + timedelta(days=365 * (years - 1))).strftime("%Y-%m-%d")
            p.data["contract"] = p.contract
            n += 1
    for s in getattr(state, "all_staff", []):               # 스태프 계약도 같은 방식으로 분산한다 (보통 길게)
        if s.team in ("FA", None) or (s.team == state.user_team and not include_user):
            continue
        end = s.contract_end()
        try:
            end_d = date.fromisoformat(end) if end else None
        except ValueError:
            end_d = None
        if end_d is None or end_d <= today:
            continue
        rnd = random.Random("stagger-staff:%s" % s.id)
        years = rnd.choices([1, 2, 3, 4], weights=[3, 3, 2, 1])[0]
        s.contract["end"] = (end_d + timedelta(days=365 * (years - 1))).strftime("%Y-%m-%d")
        s.data["contract"] = s.contract
        n += 1
    book["_staggered"] = True
    return n


def team_profile(state, team):
    """구단 프로필(성향 파라미터 + 임금 상한)"""
    prof = ensure_profiles(state).get(team, {"style": "Balanced", "wage_cap": BASE_WAGE_CAP})
    out = dict(STYLES.get(prof.get("style"), STYLES["Balanced"]))
    out["style"] = prof.get("style", "Balanced")
    out["wage_cap"] = prof.get("wage_cap", BASE_WAGE_CAP)
    return out


def _style_adjust(c, inc, prof):
    """성향에 따른 후보 가치 보정(점/경기): 젊고 잠재력 큰 선수 가산, 노장 감산"""
    def pref(p):
        age = p.age() or 27
        v = 0.012 * prof["youth"] * p.pot_gap() if age <= 28 else 0.0
        v -= 0.015 * max(0, age - 32) * max(0.3, 1.3 - prof["youth"])
        return v
    return pref(c) - pref(inc)


NEED_RUNS = 0.0             # 부족한 포지션 1명을 채울 때의 가치(점/경기) — 학습 환경(policy_env.NEED_RUNS)과 같다


class ContractPolicy:
    """ai_training/train_contract.py로 학습한 계약 정책 (numpy 추론만 사용).
    입력: 나이·OVR·잠재력 여력·향후 성장/노쇠 경로·연봉·부족 인원·임금 여유·구단 성향·2군 여부·남은 계약 연수.
    행동: 0=방출(재계약 안 함), 1..max_years=계약 기간 (계약이 남았으면 방출 또는 남은 기간 유지만 가능)."""
    N_YEARS = 5

    def __init__(self, path=None):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        d = np.load(path or os.path.join(base, "ai_contract_policy.npz"))
        self.d = {k: d[k] for k in d.files}

    def logits(self, p, salary, prof, need=0, room=0.0, farm=False, rem=0):
        age = float(p.age() or 27); ovr = float(p.calculate_ovr()); gap = float(max(0.0, p.pot_gap()))
        path = [p.projected_ovr(t) - ovr for t in range(1, self.N_YEARS + 1)]
        x = np.array([(age - 27) / 5, (ovr - 72) / 6, gap / 10] + [v / 3 for v in path]
                     + [(salary - 85_000) / 25_000, min(need, 2) / 2, max(0.0, room) / 5e5,
                        prof["sal_w"] - 1.0, prof["youth"] - 1.0, (prof["max_years"] - 3) / 1.5,
                        1.0 if farm else 0.0, rem / 3])
        h = np.tanh(x @ self.d["W1"] + self.d["b1"])
        z = h @ self.d["W2"] + self.d["b2"]
        ok = np.zeros(len(z), dtype=bool); ok[0] = True
        if rem > 0:
            ok[min(rem, len(z) - 1)] = True
        else:
            ok[1:min(prof["max_years"], self.N_YEARS) + 1] = True
        return np.where(ok, z, -1e9), ok

    def choose(self, p, salary, prof, need=0, room=0.0):
        """새 계약의 기간(1 이상). 방출은 고르지 않는다 (호출하는 쪽이 이미 계약하기로 한 경우)."""
        z, _ = self.logits(p, salary, prof, need, room)
        return int(np.argmax(z[1:])) + 1

    def farm_decision(self, p, salary, prof, rem=0):
        """2군 선수: 0이면 방출, 1 이상이면 그 기간으로 (재)계약/유지"""
        z, _ = self.logits(p, salary, prof, farm=True, rem=rem)
        return int(np.argmax(z))

    def release_pref(self, p, salary, prof, rem=0):
        """방출하고 싶은 정도(클수록 먼저 방출). 방출 로짓 - 유지(또는 최선 계약) 로짓"""
        z, _ = self.logits(p, salary, prof, farm=True, rem=rem)
        return float(z[0] - np.max(z[1:]))


_contract_cache = []


def get_contract_policy():
    if not _contract_cache:
        try:
            _contract_cache.append(ContractPolicy())
        except Exception:
            _contract_cache.append(None)
    return _contract_cache[0]


def choose_years(p, salary, prof, repl_ovr=REPL_OVR, need=0, room=0.0):
    """계약 기간(1~max_years). 학습된 정책이 있으면 정책이, 없으면 규칙(_choose_years_rule)이 정한다."""
    pol = get_contract_policy()
    if pol is not None:
        return pol.choose(p, salary, prof, need=need, room=room)
    return _choose_years_rule(p, salary, prof, repl_ovr, need)


def _choose_years_rule(p, salary, prof, repl_ovr=REPL_OVR, need=0):
    """(정책 파일이 없을 때의 대체) 계약 기간(1~max_years)을 기대효용으로 정한다.
    t년차 효용 = 할인 × (OVR 가치 - 연봉 비용), 1년 연장할 때마다 위험 비용 risk를 치른다.
    한계 효용이 위험 비용보다 큰 동안만 계약을 늘린다 (노쇠하거나 연봉 대비 가치가 낮으면 단기)."""
    years = 1
    for t in range(1, prof["max_years"] + 1):
        value = OVR_RUNS * (p.projected_ovr(t) - repl_ovr) + NEED_RUNS * min(need, 2)   # 부족한 포지션이면 오래 붙잡는다
        cost = 0.10 * (salary - REPL_SALARY) / 50_000
        u = (YEAR_DISCOUNT ** (t - 1)) * (value - cost)
        if t == 1:
            continue
        if u > prof["risk"] * (t - 1):
            years = t
        else:
            break
    return years


class GMPolicy:
    """ai_training/train_policy.py로 학습한 거래 정책 (numpy 추론만 사용).
    입력: 후보 특징 19 + 비용 맥락 4 -> 점수. '유지' 로짓과 함께 softmax의 argmax를 선택한다."""
    V_KEYS = ("mu", "sd", "W1", "b1", "W2", "b2", "W3", "b3", "ys")

    def __init__(self, path=None):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        d = np.load(path or os.path.join(base, "ai_gm_policy.npz"))
        self.d = {k: d[k] for k in d.files}
        self.beta = float(self.d["beta"])
        self.vm = {k: self.d["v_" + k] for k in self.V_KEYS}

    def choose(self, feats, demand, inc_sal, room, moves_left, adjust=None, cap=BASE_WAGE_CAP, sal_w=1.0, move_w=1.0, need=None, dead=None, force=False):
        """후보들 중 영입할 하나의 인덱스를 돌려준다. 영입하지 않으면 None. force=True면 '유지'를 고르지 못하고 최고 후보를 돌려준다.
        구단의 임금 상한·연봉 여유·성향(연봉/영입 비용 가중)이 입력으로 들어간다."""
        d, vm = self.d, self.vm
        F = np.array(feats, dtype=np.float64)
        n = len(F)
        ctx = np.column_stack([np.array(demand) / 1e5, (np.array(demand) - np.array(inc_sal)) / 5e4,
                               np.full(n, room / 1e6), np.full(n, moves_left / float(MAX_SIGNINGS_PER_YEAR)),
                               np.full(n, cap / 1e6), np.full(n, sal_w), np.full(n, move_w),
                               np.zeros(n) if need is None else np.array(need, dtype=float),
                               np.zeros(n) if dead is None else np.array(dead, dtype=float)])
        X = np.hstack([F, ctx])
        Z = (X - d["mu"]) / d["sd"]
        h = np.tanh(Z @ d["W1"] + d["b1"])
        xv = (F - vm["mu"]) / vm["sd"]
        hv = np.tanh(np.tanh(xv @ vm["W1"] + vm["b1"]) @ vm["W2"] + vm["b2"])
        v = ((hv @ vm["W3"] + vm["b3"]) * vm["ys"]).reshape(n)
        scores = self.beta * (v + h @ d["w2"] + d["b2"][0] + (np.array(adjust) if adjust is not None else 0.0))
        g = np.array([1.0, room / 1e6, moves_left / float(MAX_SIGNINGS_PER_YEAR), sal_w - 1.0, move_w - 1.0])
        noop = self.beta * float(g @ d["nw"])
        best = int(np.argmax(scores))
        return best if (force or scores[best] > noop) else None


_policy_cache = []


def get_policy():
    """학습된 정책 파일이 있으면 GMPolicy, 없거나 읽기 실패하면 None(규칙 기반으로 대체)."""
    if not _policy_cache:
        try:
            _policy_cache.append(GMPolicy())
        except Exception:
            _policy_cache.append(None)
    return _policy_cache[0]


POS_TARGET = {"P": 8}       # 포지션별 로스터 목표 인원(1·2군 합계), 그 외 포지션은 2명 (draft.REQUIRED_DEPTH와 같다)


LONG_INJURY_DAYS = 14       # 남은 부상 기간이 이보다 길면 '당분간 못 뛰는 선수'로 보고 그 자리를 비어 있는 것으로 센다


def _out(p):
    """당분간 뛸 수 없는 선수(장기 부상)"""
    return bool(p.status.get("is_injured")) and p.status.get("injury_days", 0) > LONG_INJURY_DAYS


def depth_gap(roster, pos, exclude=None):
    """목표 인원 대비 부족한 인원 수 (0 이상). exclude 선수가 빠진다고 가정한 값을 구할 수 있다.
    장기 부상 선수는 인원에 세지 않으므로, 부상으로 자리가 비면 부족 포지션으로 잡혀 보강(영입·승격)이 일어난다."""
    have = sum(1 for p in roster if p.pos == pos and p is not exclude and not _out(p))
    return max(0, POS_TARGET.get(pos, 2) - have)


def _active(roster, pos):
    return [p for p in roster if p.pos == pos and p.status.get("roster", "active") == "active" and not _out(p)]


class QNet:
    """ai_training/train_q.py로 학습한 Q 회귀망(numpy 추론). 입력 특징 -> 행동별 기대 보상(점/경기)."""

    def __init__(self, name):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        d = np.load(os.path.join(base, name))
        self.W1, self.b1, self.W2, self.b2 = d["W1"], d["b1"], d["W2"], d["b2"]

    def q(self, X):
        return np.tanh(np.asarray(X, dtype=float) @ self.W1 + self.b1) @ self.W2 + self.b2


_qnets = {}


def get_qnet(name):
    """'ai_draft_policy.npz' / 'ai_staff_policy.npz'. 없으면 None(규칙으로 대체)"""
    if name not in _qnets:
        try:
            _qnets[name] = QNet(name)
        except Exception:
            _qnets[name] = None
    return _qnets[name]


_swap_cache = []


def get_swap_policy():
    """2군↔1군 교환 정책(ai_swap_policy.npz). 없으면 None(규칙으로 대체)"""
    if not _swap_cache:
        try:
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            _swap_cache.append(GMPolicy(os.path.join(base, "ai_swap_policy.npz")))
        except Exception:
            _swap_cache.append(None)
    return _swap_cache[0]


def _value_fn():
    """(후보, 비교 대상) -> 득실차 기대 증가량(점/경기). 학습 모델이 없으면 OVR 차이로 근사."""
    try:
        nn = ai_advisor.NNAdvisor()
        return lambda c, i: nn.predict_run_gain(c, i)
    except Exception:
        return lambda c, i: (ai_advisor._ovr(c) - ai_advisor._ovr(i)) * 0.03


def _signings_left(state, team, today):
    """최근 365일 영입 기록을 보고 올해 남은 영입 가능 수를 돌려준다 (상한은 구단 성향별)."""
    book = state.__dict__.setdefault("_ai_signings", {})
    recent = [d for d in book.get(team, []) if (today - d).days < 365]
    book[team] = recent
    return team_profile(state, team)["signings"] - len(recent)


def _note_signing(state, team, today):
    state.__dict__.setdefault("_ai_signings", {}).setdefault(team, []).append(today)


DEAD_FRAC = 0.5             # 계약 중 방출하면 남은 연봉의 이 비율을 계약 만료일까지 계속 부담한다 (학습 환경과 같은 값)


def _dead_list(state, team):
    return ensure_profiles(state).setdefault(team, {}).setdefault("dead", [])      # [[연 금액, 만료일], ...] (저장됨)


def _dead_total(state, team):
    today = getattr(state, "_ai_today", None)
    if today is None:
        return 0
    live = [d for d in _dead_list(state, team) if d[1] > today.strftime("%Y-%m-%d")]
    ensure_profiles(state)[team]["dead"] = live
    return sum(d[0] for d in live)


def _payroll(roster, state=None, team=None):
    """연봉 총액 (state·team을 주면 방출 선수의 데드머니도 포함)"""
    return sum(p.salary() for p in roster) + (_dead_total(state, team) if state is not None and team else 0)


def _rem_years(p, today):
    """남은 계약 연수 (올림). 만료됐거나 계약이 없으면 0"""
    end = p.contract_end()
    try:
        days = (date.fromisoformat(end) - today).days if end else 0
    except ValueError:
        days = 0
    return 0 if days <= 0 else -(-days // 365)


def _demand(p):
    return p.demand_salary(fa=True)      # 기준 연봉 × 나이·잠재력 배율 × FA 프리미엄


def _sign(state, player, team, today, years=1):
    """FA 선수를 team에 입단시킨다."""
    fa = state.team_rosters.get("FA", [])
    if player in fa:
        fa.remove(player)
    roster = state.team_rosters.setdefault(team, [])
    used = {p.backnumber for p in roster}
    number = next((n for n in range(1, 100) if n not in used), None)
    salary = _demand(player)
    roster.append(player)
    player.team = team
    player.backnumber = number
    player.contract = {"salary": salary, "begin": today.strftime("%Y-%m-%d"),
                       "end": (today + timedelta(days=365 * years)).strftime("%Y-%m-%d")}
    player.status["roster"] = "active"
    player.status.pop("contract_expired_notice_sent", None)
    player.data["team"] = team
    player.data["backnumber"] = number
    player.data["contract"] = player.contract
    player.data["status"] = player.status


def _release(state, player):
    """방출: 로스터에서 빼서 FA 풀로 보낸다 (baseball.move_player_to_fa와 같은 처리).
    계약이 남은 선수를 내보내면 남은 연봉의 DEAD_FRAC를 데드머니로 구단이 부담한다."""
    old = player.team
    today = getattr(state, "_ai_today", None)
    if today is not None and player.salary() > 0 and _rem_years(player, today) > 0 and old in state.team_rosters:
        _dead_list(state, old).append([int(DEAD_FRAC * player.salary()), player.contract_end()])
    if old in state.team_rosters and player in state.team_rosters[old]:
        state.team_rosters[old].remove(player)
    fa = state.team_rosters.setdefault("FA", [])
    if player not in fa:
        fa.append(player)
    player.team = "FA"
    player.backnumber = None
    player.contract = {"salary": 0, "begin": None, "end": None}
    player.status["roster"] = "fa"
    player.data["team"] = "FA"
    player.data["backnumber"] = None
    player.data["contract"] = player.contract


def _fa_candidates(state):
    """포지션별 OVR 상위 FA (부상자 제외)."""
    by_pos = {}
    for p in state.team_rosters.get("FA", []):
        if p.status.get("is_injured"):
            continue
        by_pos.setdefault(p.pos, []).append(p)
    return {pos: sorted(lst, key=ai_advisor._ovr, reverse=True)[:FA_POOL_PER_POS]
            for pos, lst in by_pos.items()}


def _weakest(roster, pos):
    """포지션 주전 중 가장 약한 선수(투수는 선발 5명 중). 비교·방출 대상."""
    act = sorted(_active(roster, pos), key=ai_advisor._ovr, reverse=True)
    need = ROSTER_NEED.get(pos, 1)
    if len(act) < need:
        return None
    return act[need - 1]


def _pick(state, team, opts, roster, out_player_salary, value, prof, left, cap, needs=None, dead=None, force=False):
    """(후보, 비교 대상) 목록에서 영입할 하나를 고른다. 학습된 정책이 있으면 정책, 없으면 규칙.
    opts의 각 원소는 (후보, 비교 대상, 방출될 선수의 연봉). 영입하지 않으면 None."""
    adj = [_style_adjust(c, i, prof) for c, i, _ in opts]
    policy = get_policy()
    if policy is not None:
        k = policy.choose([ai_advisor.make_features(c, i) for c, i, _ in opts],
                          [_demand(c) for c, i, _ in opts], [sal for _, _, sal in opts],
                          cap - _payroll(roster, state, team), left, adjust=adj, cap=cap,
                          sal_w=prof["sal_w"], move_w=prof["move_w"], need=needs, dead=dead, force=force)
        return k
    best, best_g = None, (-1e9 if force else GAIN_THRESHOLD + prof["noop"])
    for k, (c, i, _) in enumerate(opts):
        g = value(c, i) + adj[k] + NEED_RUNS * (needs[k] if needs else 0)
        if g > best_g:
            best, best_g = k, g
    return best


def _renew_or_release(state, team, today, value, log, cands):
    roster = state.team_rosters.get(team, [])
    prof = team_profile(state, team)
    cap = prof["wage_cap"]
    for p in list(roster):
        end = p.contract_end()
        if not end:
            continue
        try:
            if date.fromisoformat(end) > today:
                continue
        except ValueError:
            continue
        if p.status.get("roster") == "inactive":
            # 2군 선수: 현재 능력치+잠재력이 대체 수준에 못 미치면 방출, 아니면 짧게 재계약
            cp = get_contract_policy()
            yrs = cp.farm_decision(p, p.salary(), prof) if cp is not None else (
                0 if p.calculate_ovr() + 0.5 * max(0.0, p.pot_gap()) < REPL_OVR else min(2, prof["max_years"]))
            if yrs == 0:
                _release(state, p)
                log.append((team, "방출", p, "2군 계약 만료 · 전망 부족"))
            else:
                p.contract["begin"] = today.strftime("%Y-%m-%d")
                p.contract["end"] = (today + timedelta(days=365 * yrs)).strftime("%Y-%m-%d")
                p.data["contract"] = p.contract
                log.append((team, "재계약", p, "2군 · %d년" % yrs))
            continue
        pool = cands.get(p.pos, [])
        left = _signings_left(state, team, today)
        opts = [(c, p, p.salary()) for c in pool[:POLICY_TOP]
                if _payroll(roster, state, team) - p.salary() + _demand(c) <= cap] if left > 0 else []
        k = _pick(state, team, opts, roster, p.salary(), value, prof, left, cap) if opts else None
        if k is not None:
            best = opts[k][0]
            _release(state, p)
            years = choose_years(best, _demand(best), prof, need=depth_gap(roster, p.pos, exclude=p), room=cap - _payroll(roster, state, team))
            _sign(state, best, team, today, years)
            _note_signing(state, team, today)
            cands[p.pos] = [c for c in pool if c is not best]
            log.append((team, "방출", p, "재계약 대신 %s 영입" % best.name))
            log.append((team, "영입", best, "계약 만료 대체 · %d년 계약" % years))
            continue
        # 재계약: 나이·잠재력을 반영해 연봉을 조정하고, 임금 상한을 넘으면 포기한다
        new_salary = int(p.salary() * (1 + 0.4 * (p.age_pot_factor() - 1)))
        if _payroll(roster, state, team) - p.salary() + new_salary > cap:
            if depth_gap(roster, p.pos, exclude=p) > 0 and _payroll(roster, state, team) <= cap:
                new_salary = p.salary()          # 이 포지션 인원이 모자라면 연봉 인상 없이 붙잡는다
            else:
                _release(state, p)
                log.append((team, "방출", p, "재계약 비용이 임금 상한 초과"))
                continue
        years = choose_years(p, new_salary, prof, need=depth_gap(roster, p.pos, exclude=p), room=cap - _payroll(roster, state, team))
        p.contract["salary"] = new_salary
        p.contract["begin"] = today.strftime("%Y-%m-%d")
        p.contract["end"] = (today + timedelta(days=365 * years)).strftime("%Y-%m-%d")
        p.data["contract"] = p.contract
        log.append((team, "재계약", p, "%d년 · 연봉 %dk" % (years, new_salary // 1000)))


def _fill_shortage(state, team, today, cands, log, value):
    """포지션 인원이 목표에 못 미치면 정책이 FA 후보 중 누구를 영입할지(또는 영입하지 않을지) 고른다.
    게임 규칙상 1군 최소 인원(포지션별 ROSTER_NEED)을 못 채우면 경기를 치를 수 없으므로 그때만 '영입 안 함'을 허용하지 않는다."""
    roster = state.team_rosters.get(team, [])
    prof = team_profile(state, team)
    cap = prof["wage_cap"]
    n = 0
    for pos in sorted(set(p.pos for p in roster) | set(cands)):
        while depth_gap(roster, pos) > 0:
            gap = depth_gap(roster, pos)
            forced = len(_active(roster, pos)) < ROSTER_NEED.get(pos, 1)
            if not forced and _signings_left(state, team, today) <= 0:
                break
            mates = sorted((p for p in roster if p.pos == pos), key=ai_advisor._ovr)
            inc = _weakest(roster, pos) or (mates[0] if mates else None)
            pool = [c for c in cands.get(pos, [])[:POLICY_TOP] if _payroll(roster, state, team) + _demand(c) <= cap]
            if inc is None or not pool:
                if not pool and forced:                       # 상한 안에 후보가 없어도 최소 인원은 채운다 (가장 싼 후보)
                    pool = sorted(cands.get(pos, []), key=_demand)[:1]
                if inc is None or not pool:
                    break
            opts = [(c, inc, 0) for c in pool]
            k = _pick(state, team, opts, roster, 0, value, prof, _signings_left(state, team, today), cap,
                      needs=[min(gap, 2)] * len(opts), dead=[0.0] * len(opts), force=forced)
            if k is None:
                break
            c = opts[k][0]
            years = choose_years(c, _demand(c), prof, need=gap, room=cap - _payroll(roster, state, team))
            _sign(state, c, team, today, years)
            _note_signing(state, team, today)
            cands[pos] = [x for x in cands[pos] if x is not c]
            log.append((team, "영입", c, "%s 포지션 부족 보강 · %d년 계약" % (pos, years)))
            n += 1
    return n


FARM_CAP = 12              # 2군 정원 (이를 넘으면 가치가 가장 낮은 선수 방출)
ACTIVE_TARGET = 26         # 1군 정원
PROMOTE_MARGIN = 0.10      # 2군 선수가 1군 최하위보다 이만큼 나아야 승격


def _prospect_value(p, prof):
    """2군 정원 정리용 가치: 현재 OVR + 성향에 따라 가중된 잠재력"""
    return p.calculate_ovr() + (0.2 + 0.25 * prof["youth"]) * max(0.0, p.pot_gap())


def _manage_farm(state, team, today, value, log):
    """AI 구단의 2군 운영: 정원 정리 → 1군 결원 보충 → 2군 선수가 1군 최하위보다 낫다면 승격(최하위는 강등)."""
    roster = state.team_rosters.get(team, [])
    prof = team_profile(state, team)
    farm = [p for p in roster if p.status.get("roster") == "inactive"]
    cp, sp, cap = get_contract_policy(), get_swap_policy(), prof["wage_cap"]
    while len(farm) > FARM_CAP:                                   # 1) 정원 초과: 방출 선호가 가장 큰 선수를 내보낸다
        if cp is not None:
            worst = max(farm, key=lambda p: cp.release_pref(p, p.salary(), prof, _rem_years(p, today)))
        else:
            worst = min(farm, key=lambda p: _prospect_value(p, prof))
        farm.remove(worst)
        _release(state, worst)
        log.append((team, "방출", worst, "2군 정원 초과"))
    active = [p for p in roster if p.status.get("roster", "active") == "active" and not _out(p)]
    room = cap - _payroll(roster, state, team)

    def swap_pick(opts, force):
        """(2군 후보, 비교 대상) 중 교환할 하나. 정책이 있으면 정책, 없으면 규칙"""
        adj = [_style_adjust(c, i, prof) for c, i in opts]
        if sp is not None:
            return sp.choose([ai_advisor.make_features(c, i) for c, i in opts], [0] * len(opts), [0] * len(opts),
                             room, 2, adjust=adj, cap=cap, sal_w=prof["sal_w"], move_w=prof["move_w"],
                             need=[0] * len(opts), dead=[0.0] * len(opts), force=force)
        gains = [value(c, i) + a for (c, i), a in zip(opts, adj)]
        k = max(range(len(opts)), key=lambda x: gains[x])
        return k if (force or gains[k] > PROMOTE_MARGIN + 0.5 * prof["noop"]) else None

    if len(active) < ACTIVE_TARGET and farm:                      # 2) 1군 결원 보충 (비우지 않는 것은 게임 규칙, 누구를 올릴지는 정책)
        opts = []
        for c in [f for f in farm if not f.status.get("is_injured")]:     # 다친 2군 선수는 올리지 않는다
            mates = sorted((p for p in active if p.pos == c.pos), key=ai_advisor._ovr)
            inc = _weakest(roster, c.pos) or (mates[0] if mates else (sorted(active, key=ai_advisor._ovr)[0] if active else None))
            if inc is not None:
                opts.append((c, inc))
        k = swap_pick(opts, True) if opts else None
        healthy = [f for f in farm if not f.status.get("is_injured")]
        if not opts:
            return 0
        best = opts[k][0] if k is not None else max(healthy, key=lambda p: _prospect_value(p, prof))
        best.status["roster"] = "active"
        best.data["status"] = best.status
        log.append((team, "승격", best, "1군 결원 보충"))
        return 1
    opts = [(c, _weakest(roster, c.pos)) for c in farm if not c.status.get("is_injured") and _weakest(roster, c.pos) is not None]   # 3) 승격·강등 교환
    k = swap_pick(opts, False) if opts else None
    if k is not None:
        c, inc = opts[k]
        gain = value(c, inc) + _style_adjust(c, inc, prof)
        c.status["roster"] = "active"
        inc.status["roster"] = "inactive"
        c.data["status"], inc.data["status"] = c.status, inc.status
        log.append((team, "승격", c, "%s: 예상 %+.2f점/경기" % (prof["label"], gain)))
        log.append((team, "강등", inc, "승격 선수와 교체"))
        return 1
    return 0


def _improve(state, team, today, value, log, cands):
    """FA 영입 검토. 포지션 인원이 모자라면 방출 없이 채우는 선택지(need>0)도 함께 정책에 보여 준다."""
    roster = state.team_rosters.get(team, [])
    prof = team_profile(state, team)
    cap = prof["wage_cap"]
    left = _signings_left(state, team, today)
    if left <= 0:
        return 0
    opts, needs, release, dead = [], [], [], []
    for pos, pool in cands.items():
        gap = depth_gap(roster, pos)
        inc = _weakest(roster, pos)
        if inc is None:                                   # 주전이 모자란 포지션: 이 포지션 최저 선수와 비교
            mates = sorted((p for p in roster if p.pos == pos), key=ai_advisor._ovr)
            inc = mates[0] if mates else None
        if inc is None:
            continue
        for c in pool[:POLICY_TOP]:
            rem = 0 if gap > 0 else _rem_years(inc, today)
            out_sal = 0 if gap > 0 else int(inc.salary() * (1 - DEAD_FRAC)) if rem > 0 else inc.salary()   # 계약이 남았으면 올해 비는 연봉은 일부뿐
            if _payroll(roster, state, team) - out_sal + _demand(c) <= cap:
                opts.append((c, inc, out_sal)); needs.append(min(gap, 2)); release.append(gap == 0)
                dead.append(DEAD_FRAC * inc.salary() * max(rem - 1, 0) / 5e4 if gap == 0 else 0.0)   # 내년 이후 데드머니 (정책 입력)
    if not opts:
        return 0
    k = _pick(state, team, opts, roster, 0, value, prof, left, cap, needs=needs, dead=dead)
    if k is None:
        return 0
    c, inc, _ = opts[k]
    gain = value(c, inc)
    years = choose_years(c, _demand(c), prof, need=needs[k], room=cap - _payroll(roster, state, team))
    if release[k]:
        _release(state, inc)
    _sign(state, c, team, today, years)
    _note_signing(state, team, today)
    cands[c.pos] = [x for x in cands.get(c.pos, []) if x is not c]
    tag = "정책" if get_policy() is not None else "규칙"
    if release[k]:
        log.append((team, "방출", inc, "%s·%s: 전력 보강으로 교체" % (tag, prof["label"])))
        log.append((team, "영입", c, "%s·%s: 예상 %+.2f점/경기 · %d년 계약" % (tag, prof["label"], gain, years)))
    else:
        log.append((team, "영입", c, "%s·%s: %s 포지션 부족 보강 · %d년 계약" % (tag, prof["label"], c.pos, years)))
    return 1


STAFF_CAP_FRAC = 0.30        # 스태프 연봉 총액 상한 = 임금 상한 × 이 비율
STAFF_REPLACE_MARGIN = 0.30  # 대체 후보의 효용이 이만큼 더 커야 교체한다


def _staff_util(s, salary, prof):
    """스태프 효용 = 별 개수 - 성향별 비용 가중 × 연봉(10만 단위)"""
    return s.stars - prof["staff_w"] * salary / 100_000


def choose_staff_years(s, prof):
    """스태프 계약 기간: 별이 많을수록 길게, 구단이 위험을 꺼릴수록(risk) 짧게, 나이가 많을수록(60세 이후) 짧게"""
    years = 1
    age = s.age() or 50
    for t in range(2, min(prof["max_years"], 5) + 1):
        gain = 0.05 * s.stars * (YEAR_DISCOUNT ** (t - 1))
        penalty = 0.02 * max(0, age + t - 60)
        if gain - penalty > prof["risk"] * (t - 1):
            years = t
        else:
            break
    return years


def _staff_view(s, role_note=""):
    """거래 내역(_record)·뉴스(post_news)가 읽는 선수 형태로 스태프를 감싼다 (포지션=직책, OVR=별×20)"""
    from types import SimpleNamespace
    return SimpleNamespace(name=s.name, pos=s.role, calculate_ovr=lambda: s.stars * 20)


def _staff_move(state, s, team, salary, today, years):
    s.team = team
    s.contract = {"salary": salary, "begin": today.strftime("%Y-%m-%d"),
                  "end": (today + timedelta(days=365 * years)).strftime("%Y-%m-%d")} if team != "FA" else \
        {"salary": 0, "begin": None, "end": None}
    s.status["roster"] = "active" if team != "FA" else "fa"
    s.data["team"] = team
    s.data["contract"] = s.contract
    s.data["status"] = s.status


def _staff_q(s, salary, prof, room_frac):
    """스태프 s를 이 연봉으로 쓸 때 행동별(0=안 씀, 1..5=계약 기간) 기대 보상. 학습망이 없으면 None"""
    net = get_qnet("ai_staff_policy.npz")
    if net is None:
        return None
    x = [((s.stars or 1) - 2.5) / 1.5, ((s.age() or 50) - 48) / 8, (salary - 250_000) / 150_000,
         prof["staff_w"] - 0.4, (min(prof["max_years"], 5) - 3) / 1.5, (prof["patience"] - 0.9) * 10,
         min(1.0, max(0.3, room_frac)), (salary / max(1.0, (s.stars or 1)) - 100_000) / 60_000]
    return net.q([x])[0]


def _staff_best(s, salary, prof, room_frac):
    """(기대 보상, 계약 기간): 가능한 기간 중 Q가 가장 큰 것. 학습망이 없으면 예전 효용 규칙."""
    q = _staff_q(s, salary, prof, room_frac)
    if q is None:
        return _staff_util(s, salary, prof), choose_staff_years(s, prof)
    ymax = min(prof["max_years"], 5)
    y = int(np.argmax(q[1:ymax + 1])) + 1
    return float(q[y]), y


def _manage_staff(state, team, today, log, fa_by_role):
    """AI 구단의 스태프 계약: 만료되면 (재계약 vs FA 스태프로 교체) 중 학습된 Q가 큰 쪽을 고르고, 계약 기간도 Q가 정한다."""
    prof = team_profile(state, team)
    staff = [s for s in getattr(state, "all_staff", []) if s.team == team]
    cap = STAFF_CAP_FRAC * prof["wage_cap"]
    for s in staff:
        end = s.contract_end()
        try:
            if not end or date.fromisoformat(end) > today:
                continue
        except ValueError:
            continue
        new_salary = int(s.salary() * (1 + 0.4 * (s.age_factor() - 1)))
        payroll = sum(x.salary() for x in staff)
        keep_q, keep_years = _staff_best(s, new_salary, prof, (cap - payroll) / cap)
        friction = 0.03 * prof["move_w"]                      # 영입 1회 비용 (거래 정책과 같은 값)
        best = None
        for c in fa_by_role.get(s.role, []):
            d = c.demand_salary(fa=True)
            if payroll - s.salary() + d > cap:
                continue
            q, y = _staff_best(c, d, prof, (cap - payroll + s.salary() - d) / cap)
            gain = q - friction - keep_q
            if gain > (STAFF_REPLACE_MARGIN * 0.05 if get_qnet("ai_staff_policy.npz") is None else 0.0) and (best is None or gain > best[0]):
                best = (gain, c, d, y)
        if best:
            _, c, d, years = best
            _staff_move(state, s, "FA", 0, today, 1)
            _staff_move(state, c, team, d, today, years)
            fa_by_role[s.role] = [x for x in fa_by_role[s.role] if x is not c] + [s]
            staff[staff.index(s)] = c
            log.append((team, "방출", _staff_view(s), "스태프 · %s 재계약 대신 %s 영입" % (s.role, c.name)))
            log.append((team, "영입", _staff_view(c), "스태프 · %s · %d년 계약 · 별 %d개 (%s)" % (s.role, years, c.stars, prof["label"])))
        else:
            years = keep_years
            s.contract["salary"] = new_salary
            s.contract["begin"] = today.strftime("%Y-%m-%d")
            s.contract["end"] = (today + timedelta(days=365 * years)).strftime("%Y-%m-%d")
            s.data["contract"] = s.contract
            log.append((team, "재계약", _staff_view(s), "스태프 · %s · %d년 · 연봉 %dk" % (s.role, years, new_salary // 1000)))


MAX_RECORDS = 600            # 거래 내역 보관 상한 (오래된 것부터 삭제)
NEWS_OVR = 80                # 이 OVR 이상 선수의 영입/방출은 받은편지함에도 알린다


def _record(state, today, log):
    """거래 로그를 state.transactions(저장됨)에 누적한다."""
    if not log:
        return
    book = state.__dict__.setdefault("transactions", [])
    for team, kind, p, why in log:
        book.append({"date": today.strftime("%Y-%m-%d"), "team": team, "type": kind,
                     "name": p.name, "pos": p.pos, "ovr": ai_advisor._ovr(p), "reason": why})
    del book[:-MAX_RECORDS]


def post_news(state, log, date_str):
    """주요 선수(OVR 80+)의 영입/방출을 받은편지함에 알리고, 보낸 메일 수를 돌려준다."""
    sent = 0
    for team, kind, p, why in log:
        if kind not in ("영입", "방출") or ai_advisor._ovr(p) < NEWS_OVR:
            continue
        verb = {"영입": "signed", "방출": "released"}[kind]
        state.inbox.append({
            "date": date_str, "subject": "[Transaction] %s %s %s" % (team, verb, p.name),
            "body": "%s %s %s (%s, OVR %d).\n%s" % (team, verb, p.name, p.pos, ai_advisor._ovr(p), why),
            "read": False})
        sent += 1
    return sent


def process_ai_teams(state, today):
    """하루 1회 호출. 유저 팀과 FA 풀을 제외한 모든 구단을 처리하고 거래 로그를 돌려준다."""
    log = []
    state._ai_today = today
    ensure_profiles(state)
    stagger_contracts(state, today)
    value = _value_fn()
    cands = _fa_candidates(state)
    teams = sorted(t for t in state.team_rosters if t not in ("FA", "DRAFT", state.user_team, None))
    fa_by_role = {}
    for s in getattr(state, "all_staff", []):
        if s.team == "FA":
            fa_by_role.setdefault(s.role, []).append(s)
    for idx, team in enumerate(teams):
        _manage_staff(state, team, today, log, fa_by_role)
        _renew_or_release(state, team, today, value, log, cands)
        _fill_shortage(state, team, today, cands, log, value)
        if (state.current_day + idx) % 7 == 3:
            _manage_farm(state, team, today, value, log)
        if (state.current_day + idx) % CYCLE_DAYS == 0:
            for _ in range(MAX_MOVES_PER_CYCLE):
                if not _improve(state, team, today, value, log, cands):
                    break
    _record(state, today, log)
    return log
