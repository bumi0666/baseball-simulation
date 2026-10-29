"""신인 드래프트: 시즌이 끝나면(한국시리즈 종료) 열리고, 지명된 신인은 해당 구단 2군(inactive)에 들어간다.

흐름: maybe_start() -> (유저 차례까지) AI 지명 자동 진행 -> user_pick() 반복 -> finalize()
  · 지명 순서는 정규시즌 성적 역순이고 ROUNDS라운드 동안 같은 순서를 반복한다.
  · AI 구단은 성향(ai_team_manager.STYLES)에 맞춘 평가함수로 지명한다 (현재 능력치·잠재력·포지션 필요).
  · 유저가 DEADLINE_DAYS일 안에 끝내지 않으면 남은 유저 지명은 자동으로 진행된다.
상태는 state.draft(dict)와 team 이름이 "DRAFT"인 선수 목록(state.team_rosters["DRAFT"])에 저장된다.
"""
import random
from datetime import date, timedelta

from gen_players import generate_full_spec_player
from models.player import Player

ROUNDS = 3
POOL_EXTRA = 15             # 지명 수보다 더 만드는 신인 수
DEADLINE_DAYS = 14
POSITIONS = ["P", "P", "P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]
REQUIRED_DEPTH = {"P": 8}   # 포지션별 로스터 목표 인원 (그 외 2명)
ROOKIE_SALARY = (30_000, 50_000)
ROOKIE_YEARS = 3


def _pool(state):
    return state.team_rosters.setdefault("DRAFT", [])


def current_season_key(curr_date):
    return curr_date.year


def maybe_start(state, players, curr_date, standings):
    """시즌이 끝났고 이번 시즌 드래프트가 아직 없으면 연다. 열었으면 True."""
    if not getattr(state, "season_ended", False):
        return False
    key = current_season_key(curr_date)
    cur = getattr(state, "draft", None)
    if cur and cur.get("season") == key:
        return False
    teams = [t for t, _ in reversed(standings)]            # 꼴찌부터
    n_picks = ROUNDS * len(teams)
    pool_n = n_picks + POOL_EXTRA
    rnd = random.Random(f"draft:{key}")
    next_id = max((p.id for p in players), default=0) + 1
    pool_ids = []
    for k in range(pool_n):
        raw = _make_rookie(next_id + k, rnd, key)
        pl = Player(raw)
        players.append(pl)
        _pool(state).append(pl)
        pool_ids.append(pl.id)
    state.draft = {"season": key, "status": "open", "order": teams * ROUNDS, "pick": 0, "picks": [],
                   "pool_ids": pool_ids, "deadline": (curr_date + timedelta(days=DEADLINE_DAYS)).strftime("%Y-%m-%d")}
    return True


def _make_rookie(pid, rnd, year):
    saved = random.getstate()                               # gen_players가 전역 난수를 쓰므로
    random.seed(rnd.random())                               # 시드를 고정해 만들고, 게임 난수 상태는 되돌린다
    raw = generate_full_spec_player(pid, "DRAFT", rnd.choice(POSITIONS), 0)
    random.setstate(saved)
    for v in raw["attributes"].values():                    # 신인: 잠재치의 75~92% 수준에서 출발
        v["cur"] = max(40, int(v["pot"] * rnd.uniform(0.75, 0.92)))
    raw["bio"]["birth"] = f"{year - rnd.randint(18, 22)}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}"
    raw["career"] = []
    raw["backnumber"] = None
    raw["captain"] = False
    raw["contract"] = {"salary": 0, "begin": None, "end": None}
    raw["status"]["roster"] = "draft"
    return raw


def available(state):
    """아직 지명되지 않은 신인 (OVR 높은 순)"""
    d = getattr(state, "draft", None)
    if not d:
        return []
    taken = {pk["id"] for pk in d["picks"]}
    pool = [p for p in _pool(state) if p.id in set(d["pool_ids"]) and p.id not in taken]
    return sorted(pool, key=lambda p: -p.calculate_ovr())


def on_the_clock(state):
    d = getattr(state, "draft", None)
    if not d or d["status"] != "open" or d["pick"] >= len(d["order"]):
        return None
    return d["order"][d["pick"]]


def _depth(state, team, pos):
    return sum(1 for p in state.team_rosters.get(team, []) if p.pos == pos)


def ai_score(state, team, p, key, pick_no):
    """AI 구단의 신인 평가: 현재 능력치와 잠재력을 성향 가중으로 섞고, 부족한 포지션은 가산"""
    import ai_team_manager as M
    prof = M.team_profile(state, team)
    ovr = p.calculate_ovr()
    gap = max(0.0, p.pot_gap())
    w = min(0.8, 0.3 + 0.25 * prof["youth"])
    score = (1 - w) * ovr + w * (ovr + gap)
    gap = REQUIRED_DEPTH.get(p.pos, 2) - _depth(state, team, p.pos)
    if gap > 0:
        score += 4.0 * min(gap, 2)                  # 부족한 인원 수만큼 가산 (최대 2명분)
    elif gap < 0:
        score -= 1.5 * min(-gap, 2)                 # 이미 넘치는 포지션은 감점
    score += random.Random(f"{key}:{team}:{pick_no}:{p.id}").uniform(-2.0, 2.0)   # 스카우팅 오차
    return score


def _do_pick(state, team, p):
    d = state.draft
    d["picks"].append({"team": team, "id": p.id, "pick": d["pick"] + 1})
    d["pick"] += 1


def run_ai_until_user(state, today):
    """유저 차례(또는 종료)까지 AI 지명을 진행한다. 끝났으면 finalize까지 수행."""
    d = state.draft
    while True:
        team = on_the_clock(state)
        if team is None:
            finalize(state, today)
            return
        if team == state.user_team:
            return
        avail = available(state)
        if not avail:
            d["pick"] = len(d["order"])
            continue
        best = max(avail, key=lambda p: ai_score(state, team, p, d["season"], d["pick"]))
        _do_pick(state, team, best)


def user_pick(state, player, today):
    """유저 차례에 player를 지명한다. 성공하면 True."""
    if on_the_clock(state) != state.user_team or player not in available(state):
        return False
    _do_pick(state, state.user_team, player)
    run_ai_until_user(state, today)
    return True


def auto_user_pick(state, today):
    """유저 차례를 AI 평가로 대신 지명한다(남은 신인 중 최고)."""
    avail = available(state)
    if on_the_clock(state) != state.user_team or not avail:
        return False
    d = state.draft
    best = max(avail, key=lambda p: ai_score(state, state.user_team, p, d["season"], d["pick"]))
    return user_pick(state, best, today)


def finalize(state, today):
    """지명된 신인을 각 구단 2군에 입단시키고, 미지명 신인은 FA로 보낸다."""
    d = state.draft
    if d["status"] == "done":
        return
    pool = {p.id: p for p in _pool(state)}
    start = today.strftime("%Y-%m-%d")
    end = (today + timedelta(days=365 * ROOKIE_YEARS)).strftime("%Y-%m-%d")
    rnd = random.Random(f"salary:{d['season']}")
    drafted = set()
    for pk in d["picks"]:
        p = pool[pk["id"]]
        drafted.add(p.id)
        _assign(state, p, pk["team"], "inactive",
                {"salary": rnd.randint(*ROOKIE_SALARY), "begin": start, "end": end})
    for pid, p in pool.items():
        if pid in d["pool_ids"] and pid not in drafted:
            _assign(state, p, "FA", "fa", {"salary": 0, "begin": None, "end": None})
    state.team_rosters["DRAFT"] = [p for p in _pool(state) if p.id not in set(d["pool_ids"])]
    d["status"] = "done"
    book = state.__dict__.setdefault("transactions", [])           # 거래 내역(News 화면)에도 남긴다
    n_teams = len(d["order"]) // ROUNDS
    for pk in d["picks"]:
        p = pool[pk["id"]]
        book.append({"date": start, "team": pk["team"], "type": "드래프트", "name": p.name, "pos": p.pos,
                     "ovr": p.calculate_ovr(),
                     "reason": "%d라운드 %d순위 (전체 %d번) · 잠재력 %d" % ((pk["pick"] - 1) // n_teams + 1,
                                                          (pk["pick"] - 1) % n_teams + 1, pk["pick"],
                                                          round(p.calculate_ovr() + p.pot_gap()))})
    del book[:-600]


def _assign(state, p, team, roster_flag, contract):
    if p in _pool(state):
        _pool(state).remove(p)
    roster = state.team_rosters.setdefault(team, [])
    roster.append(p)
    p.team = team
    used = {q.backnumber for q in roster if q is not p}
    p.backnumber = next((n for n in range(1, 100) if n not in used), None) if team != "FA" else None
    p.contract = contract
    p.status["roster"] = roster_flag
    p.data["team"] = team
    p.data["backnumber"] = p.backnumber
    p.data["contract"] = p.contract
    p.data["status"] = p.status


def process_daily(state, players, curr_date, standings, date_str):
    """process_day에서 하루 1회 호출. 드래프트 개시·마감 처리 후 유저에게 알릴 메일 수를 돌려준다."""
    sent = 0
    if maybe_start(state, players, curr_date, standings):
        run_ai_until_user(state, curr_date)
        state.inbox.append({
            "date": date_str, "subject": "[Draft] Rookie Draft is open",
            "body": "The rookie draft has started. Open the Draft menu to make your picks. "
                    "It will auto-complete on %s." % state.draft["deadline"], "read": False})
        sent += 1
    d = getattr(state, "draft", None)
    if d and d["status"] == "open":
        if curr_date.strftime("%Y-%m-%d") >= d["deadline"]:
            while d["status"] == "open":
                if on_the_clock(state) == state.user_team:
                    if not auto_user_pick(state, curr_date):
                        d["pick"] += 1
                else:
                    run_ai_until_user(state, curr_date)
            state.inbox.append({"date": date_str, "subject": "[Draft] Draft completed",
                                "body": "The draft deadline passed; remaining picks were made automatically.", "read": False})
            sent += 1
        elif d["status"] == "open" and on_the_clock(state) is None:
            finalize(state, curr_date)
    return sent
