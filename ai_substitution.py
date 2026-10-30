"""경기 중 대타·대수비 교체. 교체 여부는 ai_training/train_sub.py로 학습한 Q망(ai_ph_policy.npz, ai_dr_policy.npz)이 정한다.
Q(특징, 행동) = 이 시점부터 경기 끝까지의 (우리 득점 - 상대 득점) 기대값, 행동 0=유지 1=교체.
후보 선수는 벤치에서 OVR(대타) / 수비력(대수비) 상위 CAND명이며, 후보마다 Q(교체)-Q(유지)를 비교해 가장 큰 값이 0보다 크면 교체한다.
학습 파일이 없으면 교체하지 않는다."""
import numpy as np

CAND = 3
MARGIN = float(__import__("os").environ.get("SUB_MARGIN", "0.15"))      # 교체하려면 예측 이득이 이 값(점/경기)보다 커야 한다
DR_POS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")
DR_FROM = 5          # 대수비는 5회부터 고려한다
_STAT = {"ab": 0, "h": 0, "2b": 0, "3b": 0, "hr": 0, "rbi": 0, "bb": 0, "so": 0, "sb": 0,
         "ip_outs": 0, "h_allowed": 0, "r_allowed": 0, "er": 0, "so_p": 0, "bb_p": 0,
         "is_win": False, "is_loss": False, "is_save": False, "is_hold": False,
         "entry_score_diff": 0, "entry_runners": 0, "quit_score_diff": 0}


def init_stats(p):
    p.reset_game_stats()
    p.game_stats = dict(_STAT)


def _bat(p, st):
    return (p.get_attr("contact", st) / 100, p.get_attr("power", st) / 100, p.get_attr("eye", st) / 100)


def _ctx(g, side):
    """(이닝, 아웃, 1루, 2루, 3루, 이 팀 기준 점수차)"""
    d = (g.my_score - g.opp_score) if side == "my" else (g.opp_score - g.my_score)
    b = g.bases
    return [g.inning / 9, g.out / 2, float(b[0] is not None), float(b[1] is not None), float(b[2] is not None), d / 5]


def ph_x(g, side, cur, cand, slot, nbench):
    st = g.state
    c, k = _bat(cur, st), _bat(cand, st)
    return _ctx(g, side) + [cur.calculate_ovr() / 100, cand.calculate_ovr() / 100, (cand.calculate_ovr() - cur.calculate_ovr()) / 10,
                            *c, *k, cur.get_attr("defense", st) / 100, cand.get_attr("defense", st) / 100,
                            cur.status.get("health", 1000) / 1000, cand.status.get("health", 1000) / 1000,
                            cur.status.get("fatigue", 0) / 300, cand.status.get("fatigue", 0) / 300, nbench / 6, slot / 9]


def dr_x(g, side, pos, cur, cand, nbench):
    st = g.state
    oh = [1.0 if pos == q else 0.0 for q in DR_POS]
    cd, kd = cur.get_attr("defense", st) / 100, cand.get_attr("defense", st) / 100
    return _ctx(g, side)[:2] + [_ctx(g, side)[5]] + oh + [cur.calculate_ovr() / 100, cand.calculate_ovr() / 100, cd, kd, (kd - cd) * 10,
                                                          *_bat(cur, st), *_bat(cand, st),
                                                          cur.status.get("health", 1000) / 1000, cand.status.get("health", 1000) / 1000,
                                                          cur.status.get("fatigue", 0) / 300, cand.status.get("fatigue", 0) / 300, nbench / 6]


class _Net:
    def __init__(self, name):
        import os, sys
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        d = np.load(os.path.join(base, name))
        self.W1, self.b1, self.W2, self.b2 = d["W1"], d["b1"], d["W2"], d["b2"]

    def q(self, X):
        return np.tanh(np.asarray(X, dtype=float) @ self.W1 + self.b1) @ self.W2 + self.b2


_nets = {}


def net(name):
    if name not in _nets:
        try:
            _nets[name] = _Net(name)
        except Exception:
            _nets[name] = None
    return _nets[name]


def pc_x(g, side, cur, cand, nbench, is_starter):
    """투수 교체 특징: 수비 팀 기준 상황 + 현재 투수 + 후보 투수"""
    st = g.state
    a = lambda p: [p.get_attr(k, st) / 100 for k in ("velocity", "control", "stuff", "stamina")]
    gs = cur.game_stats
    return _ctx(g, side) + [cur.calculate_ovr() / 100, cur.status.get("health", 1000) / 1000, gs.get("r_allowed", 0) / 5,
                            gs.get("ip_outs", 0) / 27, cur.status.get("fatigue", 0) / 300, *a(cur), cand.calculate_ovr() / 100, cand.status.get("health", 1000) / 1000,
                            cand.status.get("fatigue", 0) / 300, *a(cand), nbench / 8, float(is_starter)]


def _bullpen(g, side):
    if side == "my":
        bp = getattr(g, "my_bullpen", None)
        return bp if bp is not None else g.state.bullpen
    return g.opp_bullpen


def _change_pitcher(g, side, new):
    lineup = g.my_lineup if side == "my" else g.opp_lineup
    used = g.pitchers_used if side == "my" else g.opp_pitchers_used
    old = lineup["P"]
    d = (g.my_score - g.opp_score) if side == "my" else (g.opp_score - g.my_score)
    init_stats(new)
    old.game_stats["quit_score_diff"] = d
    new.game_stats["entry_score_diff"] = d
    new.game_stats["entry_runners"] = sum(1 for b in g.bases if b)
    lineup["P"] = new
    used.append(new)
    g.last_event = f"{new.name} comes in to pitch"


def _pitching(g, side):
    mode = g.pitch_mode[side]
    if mode == "none":
        return
    if mode == "rule":                                       # 비교용: 예전 고정 규칙
        flag = g.my_should_change_pitcher() if side == "my" else g.ai_should_change_pitcher()
        if flag:
            (g.my_replace_pitcher if side == "my" else g.ai_replace_pitcher)(flag)
        return
    lineup = g.my_lineup if side == "my" else g.opp_lineup
    used = g.pitchers_used if side == "my" else g.opp_pitchers_used
    cur = lineup["P"]
    bp = [p for p in _bullpen(g, side) if p is not None and p not in used and not p.status.get("is_injured")]
    av = sorted(bp, key=lambda p: -p.calculate_ovr())[:CAND + 1]
    if not av:
        return
    starter = g.starter if side == "my" else g.oppstarter
    xs = [pc_x(g, side, cur, c, len(bp), cur is starter) for c in av]
    j = _decide(g, "ai_pc_policy.npz", xs, "pc", (side, g.my_score - g.opp_score))
    if j is not None:
        _change_pitcher(g, side, av[j])


def _side_data(g, side):
    if side == "my":
        return g.my_order, g.my_lineup, g.my_bench, g.my_removed
    return g.opp_order, g.opp_lineup, g.opp_bench, g.opp_removed


def _swap(g, side, old, new):
    order, lineup, bench, removed = _side_data(g, side)
    i = order.index(old)
    order[i] = new
    for k, v in lineup.items():
        if v is old:
            lineup[k] = new
    bench.remove(new)
    removed.append(old)
    t = min(1.0, ((g.inning - 1) * 2 + (1 if g.half == "BOT" else 0)) / 18)       # 경기 진행 비율
    g.t_out[old] = t
    g.t_in[new] = t
    init_stats(new)
    g.last_event = f"Substitution: {new.name} replaces {old.name}"


def _avail(bench):
    return [p for p in bench if not p.status.get("is_injured")]


def manage(g):
    """get_current_batter()에서 타석/이닝이 바뀔 때마다 한 번 호출된다 (같은 타석에서는 다시 판단하지 않는다)."""
    if g.is_game_over:
        return
    bat_side = "my" if g.half == "BOT" else "opp"       # 공격 팀: BOT은 my, TOP은 opp (엔진의 get_current_batter와 같다)
    idx = g.my_bat_idx if bat_side == "my" else g.opp_bat_idx
    key = (g.inning, g.half, idx)
    if key == getattr(g, "_sub_key", None):
        return
    g._sub_key = key
    fld_side = "opp" if bat_side == "my" else "my"
    _pitching(g, fld_side)
    dkey = (g.inning, g.half)
    if dkey != getattr(g, "_dr_key", None):
        g._dr_key = dkey
        if g.sub_flags[fld_side] and g.inning >= DR_FROM:
            _defense(g, fld_side)
    if g.sub_flags[bat_side]:
        _pinch(g, bat_side)


def _decide(g, qnet_name, xs, tag, info):
    """xs: 후보별 특징. 반환: 교체할 후보 인덱스 또는 None. g.sub_explore가 있으면 탐색(학습 자료 수집)."""
    ex = getattr(g, "sub_explore", None)
    if ex is not None:
        if ex["rng"].random() < ex["eps"][tag]:
            j = int(ex["rng"].integers(len(xs)))
            ex["log"].append((tag, xs[j], 1, info))
            return j
        kp = ex.get("keep_p", {}).get(tag, 1.0)
        for x in xs:                                   # 유지: 후보별 특징을 유지 표본으로 기록(일부만)
            if kp >= 1.0 or ex["rng"].random() < kp:
                ex["log"].append((tag, x, 0, info))
        return None
    n = net(qnet_name)
    if n is None:
        return None
    X = np.asarray(xs, dtype=float)
    q = n.q(X)
    gain = q[:, 1] - q[:, 0]
    j = int(gain.argmax())
    return j if gain[j] > MARGIN else None


def _pinch(g, side):
    order, lineup, bench, removed = _side_data(g, side)
    idx = g.my_bat_idx if side == "my" else g.opp_bat_idx
    cur = order[idx % 9]
    av = sorted(_avail(bench), key=lambda p: -p.calculate_ovr())[:CAND]
    if not av:
        return
    xs = [ph_x(g, side, cur, c, idx % 9, len(bench)) for c in av]
    j = _decide(g, "ai_ph_policy.npz", xs, "ph", (side, g.my_score - g.opp_score))
    if j is not None:
        _swap(g, side, cur, av[j])


def _defense(g, side):
    order, lineup, bench, removed = _side_data(g, side)
    for pos in DR_POS:
        cur = lineup.get(pos)
        av = sorted(_avail(bench), key=lambda p: -p.get_attr("defense", g.state))[:CAND]
        if cur is None or not av or cur not in order:
            continue
        xs = [dr_x(g, side, pos, cur, c, len(bench)) for c in av]
        j = _decide(g, "ai_dr_policy.npz", xs, "dr", (side, g.my_score - g.opp_score))
        if j is not None:
            _swap(g, side, cur, av[j])
