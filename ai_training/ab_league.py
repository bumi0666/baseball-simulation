"""AI(학습 정책) 대 규칙 구단의 리그 단위 비교.
사용법: python ai_training/ab_league.py <세계 A|B> <pre|sim|eval> [시간제한(초)=130]
  세계 A는 구단 이름순 짝수 번째가 AI·홀수 번째가 규칙, 세계 B는 반대다. 두 세계를 돌리면 모든 구단이 두 방식으로 한 번씩 평가된다.
  pre: 시작 시점 전력 측정 / sim: 730일(2년) 진행(시간제한마다 저장 후 이어서) / eval: 끝 시점 전력·연봉·거래 측정.
전력 = 그 구단 라인업(부상자 포함·제외 두 가지)이 엔진(GameScene)에서 고정 상대(Lions)와 겪는 경기당 득실차."""
import collections
import json
import os
import random
import sys
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np
import pygame
pygame.init(); pygame.display.set_mode((1280, 720))
import ai_training.env  # noqa: F401  (GameScene.end_game을 부작용 없는 버전으로 바꾼다)
import baseball as B
import draft
import ai_team_manager as M
from saveload import default_save_data, load_game, save_game
from scenes.game_scene import GameScene
from datetime import date, timedelta

world, mode = sys.argv[1], sys.argv[2]
BUDGET = float(sys.argv[3]) if len(sys.argv) > 3 else 130
TARGET_DAYS = 730
TAG = os.environ.get("TAG", "")
SEED = int(os.environ.get("SEED", "0"))
TMP = os.path.expanduser("~/tmp/ab%s_%s.json" % (TAG, world))
META = TMP + ".meta"
OUT = os.path.expanduser("~/tmp/ab%s_%s_%s.json" % (TAG, world, "%s"))
SLOTS = ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]

fresh = not os.path.exists(TMP) or mode == "pre"
data = default_save_data() if fresh else load_game(path=TMP)
state, players, staff, up, scenes = B.build_runtime(data)
B.sync_game_date(state)
M.ensure_profiles(state)
teams = sorted(t for t in state.team_rosters if t not in ("FA", "DRAFT", state.user_team))
AI_SET = set(teams[0::2]) if world == "A" else set(teams[1::2])
RULE_SET = set(teams) - AI_SET

# ---- 규칙 구단은 학습 파일이 없는 것처럼 동작시킨다 (구단별로 캐시를 잠시 비움) ----
QN = ["ai_draft_policy.npz", "ai_staff_policy.npz"]


GMRULE = os.environ.get("GMRULE") == "1"     # 진단: 모든 구단의 구단 운영(GM)을 규칙으로(AI는 경기 중 판단만 학습)
FLOOR = os.environ.get("FLOOR") == "1"       # 진단: AI 구단의 연봉·로스터가 하한 미만이면 규칙 방식으로 보충
RULE_GM = set(teams) if GMRULE else RULE_SET


def as_rule(fn, rs=None):
    rs = RULE_GM if rs is None else rs
    def w(state_, team, *a, **k):
        if team not in rs:
            return fn(state_, team, *a, **k)
        sv = (list(M._policy_cache), list(M._contract_cache), list(M._swap_cache), dict(M._qnets))
        M._policy_cache[:] = [None]; M._contract_cache[:] = [None]; M._swap_cache[:] = [None]
        for n in QN: M._qnets[n] = None
        try:
            return fn(state_, team, *a, **k)
        finally:
            M._policy_cache[:] = sv[0]; M._contract_cache[:] = sv[1]; M._swap_cache[:] = sv[2]; M._qnets.clear(); M._qnets.update(sv[3])
    return w


def floored(fn_learned, fn_rule, kind):
    def w(state_, team, *a, **k):
        r = fn_learned(state_, team, *a, **k)
        if team in AI_SET:
            ro = state_.team_rosters[team]
            low = (M._payroll(ro, state_, team) < 0.95 * state_.team_profiles[team]["wage_cap"]) if kind == "pay" else (len(ro) < 41)
            if low:
                fn_rule(state_, team, *a, **k)
        return r
    return w


for name in ("_renew_or_release", "_fill_shortage", "_manage_farm", "_improve", "_manage_staff"):
    _l = getattr(M, name)
    setattr(M, name, as_rule(_l))
    if FLOOR and name in ("_improve", "_manage_farm"):
        _all_rule = as_rule(_l, set(teams))
        setattr(M, name, floored(getattr(M, name), _all_rule, "pay" if name == "_improve" else "size"))
draft.ai_pick = (lambda f: (lambda st, team, avail, key, pick_no: as_rule(lambda s_, t_, *a: f(s_, t_, avail, key, pick_no))(st, team)))(draft.ai_pick)

WINS = collections.Counter(); GAMES = collections.Counter()
_orig_rec = state.record_match_result
def _rec(w, l, *a, **k):
    WINS[w] += 1; GAMES[w] += 1; GAMES[l] += 1
    return _orig_rec(w, l, *a, **k)
state.record_match_result = _rec
import ai_match
_play = ai_match.play
def _play_flags(st, away, home, rest, **k):      # 경기 중 판단(대타·대수비·투수 교체·선발 라인업)은 AI 구단만 학습 정책, 규칙 구단은 예전 규칙/무교체
    aa, hh = away in AI_SET, home in AI_SET
    if os.environ.get("INGAME") == "rule":            # 진단용: AI 구단도 경기 중 판단은 규칙으로(구단 운영만 학습 정책)
        return _play(st, away, home, rest, flags=(False, False), pmodes=("rule", "rule"), lmodes=("rule", "rule"), **k)
    return _play(st, away, home, rest, flags=(aa, hh), pmodes=("policy" if aa else "rule", "policy" if hh else "rule"),
                 lmodes=("learned" if aa else "rule", "learned" if hh else "rule"), **k)
ai_match.play = _play_flags
TX = collections.defaultdict(collections.Counter)
EARLY = collections.Counter()
SIGNED = {}
_orig = M.process_ai_teams


PHANTOM = float(os.environ.get("PHANTOM", "0"))     # 진단: AI 구단의 구단 운영만 '가짜 부상'(경기엔 영향 없음)을 보게 한다. 값은 선수·일당 시작 확률
PH = {}
_phrng = np.random.RandomState(SEED + 17)
_real_out = M._out
if PHANTOM > 0:
    M._out = lambda p: _real_out(p) or PH.get(id(p), 0) > M.LONG_INJURY_DAYS


def _phantom_step(state_):
    for t in AI_SET:
        for p in state_.team_rosters.get(t, []):
            d = PH.get(id(p), 0)
            if d > 0:
                PH[id(p)] = d - 1
            elif p.status.get("roster", "active") == "active" and _phrng.rand() < PHANTOM:
                PH[id(p)] = int(_phrng.randint(3, 31))


def logged(state_, today):
    if PHANTOM > 0:
        _phantom_step(state_)
    log = _orig(state_, today)
    for team, kind, p, why in log:
        if "스태프" in why:
            continue
        TX[team][kind] += 1
        key = (team, p.name, p.pos)
        if kind == "영입":
            SIGNED[key] = today
        elif kind == "방출" and key in SIGNED and (today - SIGNED[key]).days <= 60:
            EARLY[team] += 1
    return log


M.process_ai_teams = logged


def today_date():
    y, m, d = state.base_date
    return date(y, m, d) + timedelta(days=state.current_day - 1)


def strength(team, healthy_only, n=60):
    """team 라인업이 엔진에서 Lions를 상대로 내는 경기당 득실차 (팀 전력의 엔진 측정)"""
    allr = list(state.team_rosters[team])
    pools = [[p for p in allr if p.status.get("roster", "active") == "active" and not (healthy_only and p.status.get("is_injured"))],
             [p for p in allr if p.status.get("roster", "active") == "active"], allr]      # 사람이 모자라면 점점 넓혀 채운다(평가용)
    used = set(); lineup = {}
    for pos in SLOTS:
        for pool in pools:
            c = [p for p in pool if p.pos == pos and id(p) not in used] if pos == "P" else \
                ([p for p in pool if p.pos == pos and id(p) not in used] or [p for p in pool if p.pos != "P" and id(p) not in used])
            if c:
                lineup[pos] = max(c, key=lambda p: p.calculate_ovr()); used.add(id(lineup[pos])); break
    order = sorted((lineup[k] for k in SLOTS if k != "P"), key=lambda p: -p.calculate_ovr())[:9]
    roster = pools[0]
    pit = sorted((p for p in roster if p.pos == "P" and p is not lineup["P"]), key=lambda p: -p.calculate_ovr())
    saved = (state.user_team, state.lineup, state.batting_order, state.bullpen, dict(state.schedule.get(state.get_current_date_str(), {})))
    opp = "Lions" if team != "Lions" else teams[0]
    snap = [(p, dict(p.status)) for t in (team, opp) for p in state.team_rosters[t]]
    ds = state.get_current_date_str()
    state.user_team = team
    state.schedule[ds] = {"opponent": opp}
    diff = 0
    try:
        for i in range(n):
            for p, s in snap: p.status.update(s)
            state.lineup = dict(lineup); state.batting_order = list(order); state.bullpen = (pit + [None] * 8)[:8]
            random.seed(777 * 100003 + i)
            g = GameScene(state.team_rosters[team], state)
            g.simulate_to_end()
            diff += g.my_score - g.opp_score
    finally:
        for p, s in snap: p.status.update(s)
        state.user_team, state.lineup, state.batting_order, state.bullpen = saved[:4]
        if saved[4]: state.schedule[ds] = saved[4]
        else: state.schedule.pop(ds, None)
    return diff / n


def snapshot():
    out = {}
    for t in teams:
        r = state.team_rosters[t]
        out[t] = dict(mode="AI" if t in AI_SET else "RULE", style=state.team_profiles[t]["style"],
                      s_all=strength(t, False), s_healthy=strength(t, True),
                      payroll=M._payroll(r, state, t), cap=state.team_profiles[t]["wage_cap"],
                      size=len(r), injured=sum(1 for p in r if p.status.get("is_injured")),
                      short=sum(1 for pos in set(p.pos for p in r) if M.depth_gap(r, pos) > 0),
                      avg_ovr=float(np.mean([p.calculate_ovr() for p in r])),
                      top14=float(np.mean(sorted([p.calculate_ovr() for p in r], reverse=True)[:14])))
    return out


if mode == "pre":
    json.dump(snapshot(), open(OUT % "pre", "w")); save_game(state, players, getattr(state, "all_staff", []), path=TMP)
    json.dump({"day": state.current_day, "tx": {}, "early": {}, "wins": {}, "games": {}}, open(META, "w")); print("pre done day", state.current_day); sys.exit()

meta = json.load(open(META))
for t, c in meta.get("tx", {}).items(): TX[t].update(c)
EARLY.update(meta.get("early", {})); WINS.update(meta.get("wins", {})); GAMES.update(meta.get("games", {}))
if mode == "sim":
    t0 = time.time(); start = state.current_day
    random.seed(SEED * 1000003 + state.current_day)
    while time.time() - t0 < BUDGET and state.current_day < TARGET_DAYS:
        res = B.process_day(players, state)
        if res == "NEW_MESSAGE" and state.todaygamenotice and not state.todaygamedone:
            continue
        state.todaygamenotice = False; state.todaygamedone = False
        state.current_day += 1; B.sync_game_date(state)
    save_game(state, players, getattr(state, "all_staff", []), path=TMP)
    json.dump({"day": state.current_day, "tx": {t: dict(c) for t, c in TX.items()}, "early": dict(EARLY), "wins": dict(WINS), "games": dict(GAMES)}, open(META, "w"))
    print("world", world, "day", state.current_day, "/", TARGET_DAYS, "date", today_date(), "%.0fs" % (time.time() - t0))
else:
    res = snapshot()
    for t in teams:
        res[t]["tx"] = dict(TX[t]); res[t]["early"] = EARLY[t]; res[t]["wins"] = WINS[t]; res[t]["games"] = GAMES[t]
    json.dump(res, open(OUT % "post", "w")); print("eval done day", state.current_day)
