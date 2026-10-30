"""선발 라인업·선발 투수 가치 모델 학습.
  python ai_training/train_lineup.py collect <시드> <시간초> : 무작위 라인업 두 팀을 엔진에서 붙여 (특징, 양 팀 득점) 수집 -> ~/tmp/lu_<시드>.npz
  python ai_training/train_lineup.py fit [반복]              : 득점 = 공격항(타자·타순) - 상대 수비항(수비수·포지션)·선발 투수 로 회귀 -> ai_lineup_model.npz
  python ai_training/train_lineup.py eval <시드> <시간초>     : 같은 대진에서 원정 팀이 [학습 선택 / 예전 규칙]으로 라인업을 짰을 때 득실차 비교"""
import glob, os, sys, time, random
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np
import pygame
pygame.init(); pygame.display.set_mode((1280, 720))
import baseball as B
import ai_match, ai_lineup as L
from saveload import default_save_data

mode = sys.argv[1]; TMP = os.path.expanduser("~/tmp")


def world():
    state, *_ = B.build_runtime(default_save_data()); B.sync_game_date(state)
    return state, sorted(t for t in state.team_rosters if t not in ("FA", "DRAFT", state.user_team))


def feats(state, lineup, order):
    """한 팀의 (공격항 입력 [9,14], 수비항 입력 [9,11], 투수 입력 [10])"""
    bullpen = [p for p in state._pit if p is not lineup["P"]]
    xo = [L.hit_o(p, state, s) for s, p in enumerate(order)]
    xd = [L.hit_d(lineup[pos], state, pos) for pos in L.POSS]
    return xo, xd, L.pit_x(lineup["P"], state, bullpen)


def rand_lineup(roster, rng, state):
    act = [p for p in roster if p.status.get("roster", "active") == "active" and not p.status.get("is_injured")]
    hit = [p for p in act if p.pos != "P"]; pit = [p for p in act if p.pos == "P"]
    if len(hit) < 9 or not pit: return None
    pick = [hit[i] for i in rng.permutation(len(hit))[:9]]
    perm = rng.permutation(9)
    lineup = {pos: pick[perm[k]] for k, pos in enumerate(L.POSS)}
    order = [pick[i] for i in rng.permutation(9)]
    starter = pit[int(rng.integers(len(pit)))]
    lineup["P"] = starter
    bullpen = sorted((q for q in pit if q is not starter), key=lambda q: -q.calculate_ovr())
    state._pit = pit
    return (lineup, order, bullpen, list(order) + [starter])


if mode == "collect":
    seed = int(sys.argv[2]); budget = float(sys.argv[3])
    rng = np.random.default_rng(seed); random.seed(seed)
    state, teams = world()
    XO, XD, XP, Y = [], [], [], []
    t0 = time.time(); n = 0
    while time.time() - t0 < budget:
        a, h = rng.choice(len(teams), 2, replace=False)
        for t in (teams[a], teams[h]):
            for p in state.team_rosters[t]:
                if rng.random() < 0.3: p.status["health"] = int(rng.integers(500, 1001))
        la = rand_lineup(state.team_rosters[teams[a]], rng, state)
        fa = feats(state, la[0], la[1]) if la else None
        lb = rand_lineup(state.team_rosters[teams[h]], rng, state)
        fb = feats(state, lb[0], lb[1]) if lb else None
        if not la or not lb: continue
        r = ai_match.play(state, teams[a], teams[h], 200, lineups=(la, lb))
        if not r: continue
        XO.append([fa[0], fb[0]]); XD.append([fa[1], fb[1]]); XP.append([fa[2], fb[2]]); Y.append([r[0], r[1]]); n += 1
    np.savez(os.path.join(TMP, "lu_%d.npz" % seed), xo=np.array(XO, np.float32), xd=np.array(XD, np.float32), xp=np.array(XP, np.float32), y=np.array(Y, np.float32))
    print("games", n, "%.0fs" % (time.time() - t0))

elif mode == "fit":
    iters = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
    D = [np.load(f) for f in sorted(glob.glob(os.path.join(TMP, "lu_*.npz")))]
    xo = np.concatenate([d["xo"] for d in D]); xd = np.concatenate([d["xd"] for d in D]); xp = np.concatenate([d["xp"] for d in D]); y = np.concatenate([d["y"] for d in D])
    N = len(y); print("games", N, "평균 득점", y.mean(), "표준편차", y.std())
    rng = np.random.default_rng(1); perm = rng.permutation(N); cut = int(0.9 * N); tr, te = perm[:cut], perm[cut:]
    H = L.HID

    def mk(d_in):
        return {"W1": rng.normal(0, 0.3, (d_in, H)), "b1": np.zeros(H), "W2": rng.normal(0, 0.1, (H, 1)), "b2": np.zeros(1)}
    P = {"fo": mk(xo.shape[-1]), "fd": mk(xd.shape[-1]), "hp": mk(xp.shape[-1])}
    c = np.array([y.mean(), y.mean()])
    M = {k: {q: np.zeros_like(v) for q, v in P[k].items()} for k in P}; V2 = {k: {q: np.zeros_like(v) for q, v in P[k].items()} for k in P}
    mc = np.zeros(2); vc = np.zeros(2)

    def fwd(net, X):
        h = np.tanh(X @ net["W1"] + net["b1"]); return (h @ net["W2"] + net["b2"])[..., 0], h

    def predict(idx):
        o, ho = fwd(P["fo"], xo[idx]); d, hd = fwd(P["fd"], xd[idx]); p_, hp_ = fwd(P["hp"], xp[idx])      # o,d: [B,2,9]  p_: [B,2]
        off = o.sum(-1); dfn = d.sum(-1) + p_                                                              # [B,2]
        pred = np.stack([c[0] + off[:, 0] - dfn[:, 1], c[1] + off[:, 1] - dfn[:, 0]], 1)
        return pred, (ho, hd, hp_)

    lr, B1, B2 = 0.003, 0.9, 0.999; t0 = time.time(); best = (1e9, None)
    for it in range(1, iters + 1):
        b = rng.choice(tr, 2048)
        pred, (ho, hd, hp_) = predict(b)
        e = 2 * (pred - y[b]) / len(b)                       # dL/dpred (손실 = 평균 제곱오차 x 2팀 합)
        g_off = np.stack([e[:, 0], e[:, 1]], 1)              # off 합에 대한 기울기 [B,2]
        g_dfn = np.stack([-e[:, 1], -e[:, 0]], 1)            # dfn 합에 대한 기울기 (상대 팀 득점식에 들어간다)
        grads = {}
        def back(net, X, h, gout):                           # gout: X의 앞 차원과 같은 [..]
            dz = gout[..., None]; Hh = h.reshape(-1, H); Dz = dz.reshape(-1, 1); Xf = X.reshape(-1, X.shape[-1])
            gW2 = Hh.T @ Dz; gb2 = Dz.sum(0); dh = (Dz @ net["W2"].T) * (1 - Hh ** 2)
            return {"W1": Xf.T @ dh, "b1": dh.sum(0), "W2": gW2, "b2": gb2}
        grads["fo"] = back(P["fo"], xo[b], ho, np.repeat(g_off[:, :, None], 9, 2))
        grads["fd"] = back(P["fd"], xd[b], hd, np.repeat(g_dfn[:, :, None], 9, 2))
        grads["hp"] = back(P["hp"], xp[b], hp_, g_dfn)
        gc = e.sum(0)
        for k in P:
            for q in P[k]:
                g = grads[k][q]; M[k][q] = B1 * M[k][q] + (1 - B1) * g; V2[k][q] = B2 * V2[k][q] + (1 - B2) * g * g
                P[k][q] = P[k][q] - lr * (M[k][q] / (1 - B1 ** it)) / (np.sqrt(V2[k][q] / (1 - B2 ** it)) + 1e-8)
        mc = B1 * mc + (1 - B1) * gc; vc = B2 * vc + (1 - B2) * gc * gc
        c = c - lr * (mc / (1 - B1 ** it)) / (np.sqrt(vc / (1 - B2 ** it)) + 1e-8)
        if it % 250 == 0:
            pr, _ = predict(te[:20000]); mse = ((pr - y[te[:20000]]) ** 2).mean(); var = y[te[:20000]].var()
            print(it, "시험 MSE", round(float(mse), 4), "R²", round(1 - float(mse) / float(var), 4), "%.0fs" % (time.time() - t0), flush=True)
            if mse < best[0]: best = (mse, {k: {q: v.copy() for q, v in P[k].items()} for k in P})
    P = best[1]
    out = {}
    for k in P:
        for q in P[k]: out[k + "_" + q] = P[k][q]
    np.savez(os.path.join(ROOT, "ai_lineup_model.npz"), **out)
    print("saved")

else:  # eval
    seed = int(sys.argv[2]); budget = float(sys.argv[3])
    rng = np.random.default_rng(seed + 700); state, teams = world()
    res = {"learned": [], "rule": []}; t0 = time.time(); n = 0
    L._model.clear()
    while time.time() - t0 < budget:
        a, h = rng.choice(len(teams), 2, replace=False); sd = int(rng.integers(1 << 30)); row = []
        for key in res:
            random.seed(sd)
            r = ai_match.play(state, teams[a], teams[h], 200, lmodes=(key, "rule"))
            if not r: row = None; break
            row.append((key, r[0] - r[1]))
        if not row: continue
        for key, d in row: res[key].append(d)
        n += 1
    np.savez(os.path.join(TMP, "lueval_%d.npz" % seed), **{k: np.array(v) for k, v in res.items()})
    print("games", n, "%.0fs" % (time.time() - t0))
