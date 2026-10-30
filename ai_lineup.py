"""AI 감독의 선발 라인업(포지션·타순)과 선발 투수 선택. 규칙이 아니라 엔진 경기에서 학습한 가치 모델(ai_lineup_model.npz)로 고른다.
팀 득점 = 공격항(타자·타순 슬롯) - 상대 수비항(수비수·포지션, 선발 투수)을 선수별 작은 신경망의 합으로 근사해 엔진 경기 결과에 회귀한다.
선택은 그 가치를 최대로 하는 배정(헝가리안)이고, 피로가 높아 부상 확률이 큰 선수는 부상으로 잃을 기대 가치(부상 확률 x 평균 결장 일수 x 하루 경기 수 x 대체선수와의 가치 차)만큼 깎는다."""
import os, sys
import numpy as np

POSS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
HID = 16


def hit_o(p, st, slot):
    """공격항 입력: 타격 능력 + 체력 + 타순 슬롯 원핫"""
    oh = [0.0] * 9; oh[slot] = 1.0
    return [p.get_attr(k, st) / 100 for k in ("contact", "power", "eye", "run")] + [p.status.get("health", 1000) / 1000] + oh


def hit_d(p, st, pos):
    """수비항 입력: 수비력 + 체력 + 포지션 원핫"""
    oh = [0.0] * 9; oh[POSS.index(pos)] = 1.0
    return [p.get_attr("defense", st) / 100, p.status.get("health", 1000) / 1000] + oh


def pit_x(p, st, bullpen):
    """선발 투수 + 남는 불펜 상위 4명 평균"""
    a = lambda q: [q.get_attr(k, st) / 100 for k in ("velocity", "control", "stuff", "stamina")]
    top = sorted(bullpen, key=lambda q: -q.calculate_ovr())[:4]
    bp = np.mean([a(q) for q in top], axis=0).tolist() if top else [0.5] * 4
    return a(p) + [p.status.get("health", 1000) / 1000] + bp


def hungarian_max(M):
    """행>=열 인 직사각 이득 행렬에서 열마다 서로 다른 행을 골라 합을 최대로 한다. (행 인덱스 리스트 반환)"""
    M = np.asarray(M, dtype=float)
    C = (-M).T; R, K = C.shape               # 열 R개를 행 K개 중 서로 다른 하나씩에 배정 (R<=K)
    u = np.zeros(R + 1); v = np.zeros(K + 1); p = np.zeros(K + 1, dtype=int); way = np.zeros(K + 1, dtype=int)
    for i in range(1, R + 1):
        p[0] = i; j0 = 0; minv = np.full(K + 1, np.inf); used = np.zeros(K + 1, dtype=bool)
        while True:
            used[j0] = True; i0 = p[j0]; delta = np.inf; j1 = 0
            for j in range(1, K + 1):
                if not used[j]:
                    cur = C[i0 - 1, j - 1] - u[i0] - v[j]
                    if cur < minv[j]: minv[j] = cur; way[j] = j0
                    if minv[j] < delta: delta = minv[j]; j1 = j
            for j in range(K + 1):
                if used[j]: u[p[j]] += delta; v[j] -= delta
                else: minv[j] -= delta
            j0 = j1
            if p[j0] == 0: break
        while True:
            j1 = way[j0]; p[j0] = p[j1]; j0 = j1
            if j0 == 0: break
    out = [None] * R
    for j in range(1, K + 1):
        if p[j]: out[p[j] - 1] = j - 1
    return out        # out[열] = 행


class Model:
    def __init__(self, path="ai_lineup_model.npz"):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        d = np.load(os.path.join(base, path)); self.d = {k: d[k] for k in d.files}

    def f(self, name, X):
        d = self.d
        return (np.tanh(np.asarray(X, dtype=float) @ d[name + "_W1"] + d[name + "_b1"]) @ d[name + "_W2"] + d[name + "_b2"]).reshape(-1)


_model = []


def model():
    if not _model:
        try:
            _model.append(Model())
        except Exception:
            _model.append(None)
    return _model[0]


def _p_inj(f):
    """경기 후 피로 f에서의 부상 확률 (baseball.apply_ai_game_fatigue와 같은 식)"""
    return min(0.5, ((f - 200) ** 2) / 40000 + 0.05) if f > 200 else 0.0


_adv_cache = {}
_val_cache = {}
GAMMA = 0.99            # 경기당 할인율(한 시즌 약 140경기를 내다본다)
INJ_GAMES = 8           # 부상 평균 16.5일 x 하루 0.46경기


def advantage(inc):
    """한 선수가 '뛰기' vs '쉬기'의 가치 차(뛰어서 얻는 경기당 기여 g에 대한 배수)를 피로 수준 f별로 구한다. (가치 반복으로 풀이)
    뛰면 피로 f+inc-10, 확률 p_inj(f+inc-10)로 부상(INJ_GAMES경기 동안 못 뜀), 쉬면 피로 f-30(최소 0). 가치는 g에 비례하므로 g=1로 푼다.
    반환 배열 A[f]: 1이면 위험 없이 뛰는 이득 전부, 0 이하면 쉬는 편이 낫다."""
    key = int(round(inc))
    if key in _adv_cache:
        return _adv_cache[key]
    F = 700
    f = np.arange(F + 1)
    nxt_play = np.minimum(F, f + key - 10); nxt_rest = np.maximum(0, f - 30)
    p = np.array([_p_inj(x) for x in nxt_play])
    V = np.zeros(F + 1)
    for _ in range(600):
        stay = GAMMA * V[nxt_play]
        play = 1.0 + (1 - p) * stay + p * (GAMMA ** INJ_GAMES) * V[nxt_play]
        rest = GAMMA * V[nxt_rest]
        Vn = np.maximum(play, rest)
        if np.abs(Vn - V).max() < 1e-9: V = Vn; break
        V = Vn
    stay = GAMMA * V[nxt_play]
    play = 1.0 + (1 - p) * stay + p * (GAMMA ** INJ_GAMES) * V[nxt_play]
    A = play - GAMMA * V[nxt_rest]
    _adv_cache[key] = A
    _val_cache[key] = V
    return A


def fatigue_value(inc):
    """가치함수 V[f]: 피로 f인 선수가 앞으로 낼 기여의 합(g=1 단위). 피로가 늘어 V가 줄어든 만큼이 그 경기의 피로·부상 비용이다."""
    advantage(inc)
    return _val_cache[int(round(inc))]


def pitcher_gaps(roster, state):
    """건강한 1군 투수별 '대체 투수보다 경기당 얼마나 낫나'(실점 감소, 점). 6번째로 좋은 투수를 대체 수준으로 본다."""
    m = model()
    pit = [p for p in roster if p.pos == "P" and p.status.get("roster", "active") == "active" and not p.status.get("is_injured")]
    if m is None or len(pit) < 2:
        return {p: 0.1 for p in pit}
    sc = {p: -m.f("hp", [pit_x(p, state, [q for q in pit if q is not p])])[0] for p in pit}
    srt = sorted(sc.values(), reverse=True)
    repl = srt[min(5, len(srt) - 1)]
    return {p: max(0.02, sc[p] - repl) for p in pit}


def usage_cost(gaps, f0, w, inc_fn):
    """경기에서 투수들이 던진 비율 w[p]만큼 피로가 늘어 잃는 기대 가치(점) = g_p x (V(f0) - V(f0 + w x (inc-10)))"""
    tot = 0.0
    for p, wp in w.items():
        if wp <= 0 or p not in gaps:
            continue
        V = fatigue_value(inc_fn(p)); top = len(V) - 1
        a = int(min(top, max(0, round(f0.get(p, 0))))); b = int(min(top, max(0, round(f0.get(p, 0) + wp * (inc_fn(p) - 10)))))
        tot += gaps[p] * max(0.0, V[a] - V[b])
    return tot


def _adv(fatigue, inc):
    A = advantage(inc)
    return float(A[int(min(len(A) - 1, max(0, round(fatigue))))])


def pool(roster):
    """출전 후보: 건강한 1군 선수. 야수가 9명(투수는 1명)에 못 미치면 부상자, 2군 순으로 채워 라인업이 항상 완성되게 한다."""
    act = [p for p in roster if p.status.get("roster", "active") == "active" and not p.status.get("is_injured")]
    hit = [p for p in act if p.pos != "P"]; pit = [p for p in act if p.pos == "P"]
    rest = sorted((p for p in roster if p not in act), key=lambda p: (p.status.get("roster", "active") != "active", -p.calculate_ovr()))
    for p in rest:
        if p.pos != "P" and len(hit) < 9: hit.append(p)
        elif p.pos == "P" and len(pit) < 1: pit.append(p)
    return hit, pit


def choose(roster, state, hitter_inc, pitcher_inc):
    """roster 중 건강한 1군 선수로 (lineup dict, 타순 list, 불펜 list, 출전 선수 list)를 만든다. 모델이 없으면 None.
    hitter_inc(p)/pitcher_inc(p): 이 경기를 뛰면 늘어날 피로(부상 위험 계산용)."""
    m = model()
    if m is None:
        return None
    hit, pit = pool(roster)
    if len(hit) < 9 or not pit:
        return None
    # --- 타자: 포지션 배정(수비항) + 공격 기본가치 ---
    n = len(hit)
    O = np.array([[m.f("fo", [hit_o(p, state, s)])[0] for s in range(9)] for p in hit])           # [n,9] 슬롯별 공격값
    D = np.array([[-m.f("fd", [hit_d(p, state, pos)])[0] for pos in POSS] for p in hit])           # [n,9] 포지션별 (-실점 기여)
    base = O.mean(1)[:, None] + D                                                                  # 포지션 배정용
    val = O.mean(1) + D.mean(1)                                                                    # 선수의 평균 가치
    order_idx = np.argsort(-val)
    repl = val[order_idx[9]] if n > 9 else val.min() - 1.0                                         # 9명 밖 최고 = 대체선수 가치
    risk = np.array([(1 - _adv(p.status.get("fatigue", 0), hitter_inc(p))) * max(0.0, val[i] - repl) for i, p in enumerate(hit)])
    sel = hungarian_max(base - risk[:, None])                                                     # sel[포지션]=선수 인덱스
    lineup = {pos: hit[sel[k]] for k, pos in enumerate(POSS)}
    chosen = [sel[k] for k in range(9)]
    slot = hungarian_max(O[chosen, :])                                                             # slot[타순]=chosen 내 위치
    order = [hit[chosen[slot[s]]] for s in range(9)]
    # --- 선발 투수: 모든 건강한 투수 후보 ---
    sc = []
    for i, p in enumerate(pit):
        rest = [q for q in pit if q is not p]
        sc.append(-m.f("hp", [pit_x(p, state, rest)])[0])
    sc = np.array(sc); srt = np.argsort(-sc); prepl = sc[srt[1]] if len(pit) > 1 else sc[srt[0]] - 1.0
    prisk = np.array([(1 - _adv(p.status.get("fatigue", 0), pitcher_inc(p))) * max(0.0, sc[i] - prepl) for i, p in enumerate(pit)])
    starter = pit[int(np.argmax(sc - prisk))]
    lineup["P"] = starter
    bullpen = sorted((q for q in pit if q is not starter), key=lambda q: -q.calculate_ovr())
    playing = list(order) + [starter]
    return lineup, order, bullpen, playing
