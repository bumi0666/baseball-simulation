"""대타·대수비 정책 학습.
  python ai_training/train_sub.py collect <시드> <시간초>   : 탐색(무작위 교체) 경기로 표본 수집 -> ~/tmp/sub_<시드>.npz
  python ai_training/train_sub.py fit [반복]                  : 수집한 표본으로 Q망 회귀 -> ai_ph_policy.npz, ai_dr_policy.npz
  python ai_training/train_sub.py eval <시드> <시간초>        : 같은 대진을 [정책 / 무교체]로 돌려 팀 득실차 비교
행동 0=유지 1=교체, 보상 = 그 시점부터 경기 끝까지의 (우리 득점 - 상대 득점)."""
import glob, os, sys, time, random
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np
import pygame
pygame.init(); pygame.display.set_mode((1280, 720))
import baseball as B
import ai_match, ai_substitution as S, ai_lineup as LU
from ai_fatigue import AI_PITCHER_FATIGUE
pinc = lambda p: AI_PITCHER_FATIGUE * (100 / max(30, getattr(p, "stamina", 100) or 100))


def side_cost(g, gaps_my, gaps_opp):
    """경기에서 각 팀 투수진이 쓴 피로·부상 비용(점). my=홈, opp=원정"""
    w_my = {p: g.pitch_w.get(p, 0.0) for p in g.pitchers_used}; w_opp = {p: g.pitch_w.get(p, 0.0) for p in g.opp_pitchers_used}
    return {"my": LU.usage_cost(gaps_my, g.pitch_f0, w_my, pinc), "opp": LU.usage_cost(gaps_opp, g.pitch_f0, w_opp, pinc)}
from saveload import default_save_data

mode = sys.argv[1]
TMP = os.path.expanduser("~/tmp")


def world():
    state, *_ = B.build_runtime(default_save_data()); B.sync_game_date(state)
    teams = sorted(t for t in state.team_rosters if t not in ("FA", "DRAFT", state.user_team))
    return state, teams


def jitter(state, teams, rng):
    """학습 다양성: 일부 선수의 시작 체력을 낮춘다(실제 경기 체력은 경기 중에 닳는다)."""
    for t in teams:
        for p in state.team_rosters[t]:
            if rng.random() < 0.5:
                p.status["health"] = int(rng.integers(450, 1001))


if mode == "collect":
    seed = int(sys.argv[2]); budget = float(sys.argv[3])
    rng = np.random.default_rng(seed); random.seed(seed)
    state, teams = world()
    TAGS = ("ph", "dr", "pc")
    X = {k: [] for k in TAGS}; A = {k: [] for k in TAGS}; Y = {k: [] for k in TAGS}
    t0 = time.time(); n = 0
    while time.time() - t0 < budget:
        a, h = rng.choice(len(teams), 2, replace=False)
        jitter(state, teams, rng)
        for t in (teams[a], teams[h]):
            for p in state.team_rosters[t]:
                if p.pos == "P": p.status["fatigue"] = float(rng.uniform(0, 260)) if rng.random() < 0.4 else 0.0
        gaps_a = LU.pitcher_gaps(state.team_rosters[teams[a]], state); gaps_h = LU.pitcher_gaps(state.team_rosters[teams[h]], state)
        ex = {"rng": rng, "eps": {"ph": 0.06, "dr": 0.03, "pc": 0.05}, "keep_p": {"ph": 0.6, "dr": 0.6, "pc": 0.3}, "log": []}
        r = ai_match.play(state, teams[a], teams[h], 200, flags=(True, True), explore=ex, detail=True)
        if not r: continue
        away_s, home_s, _, _, g = r
        fin = {"my": g.my_score - g.opp_score, "opp": g.opp_score - g.my_score}
        cost = side_cost(g, gaps_h, gaps_a)
        for tag, x, act, (side, d_my) in ex["log"]:
            d_now = d_my if side == "my" else -d_my
            # 투수 교체 보상 = 남은 경기 득실차 - 그 경기 투수진이 쓴 피로·부상 비용
            X[tag].append(x); A[tag].append(act); Y[tag].append(fin[side] - d_now - (cost[side] if tag == "pc" else 0.0))
        n += 1
    out = {}
    for k in TAGS:
        out[k + "_x"] = np.array(X[k], dtype=np.float32); out[k + "_a"] = np.array(A[k], dtype=np.int8); out[k + "_y"] = np.array(Y[k], dtype=np.float32)
    np.savez(os.path.join(TMP, "sub_%d.npz" % seed), **out)
    print("games", n, {k: (len(X[k]), int(np.sum(A[k]))) for k in X}, "%.0fs" % (time.time() - t0))

elif mode == "fit":
    iters = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
    files = sorted(glob.glob(os.path.join(TMP, "sub_*.npz")))
    D = [np.load(f) for f in files]
    HID = 24
    for k in (sys.argv[3].split(",") if len(sys.argv) > 3 else ("ph", "dr", "pc")):
        if not all((k + "_x") in d.files for d in D): continue
        x = np.concatenate([d[k + "_x"] for d in D]); a = np.concatenate([d[k + "_a"] for d in D]).astype(int); y = np.concatenate([d[k + "_y"] for d in D])
        mu, sd = x.mean(0), np.maximum(x.std(0), 0.02)          # 입력 표준화를 첫 층에 흡수
        xs = (x - mu) / sd
        rng = np.random.default_rng(1); perm = rng.permutation(len(x)); cut = int(0.85 * len(x)); tr, te = perm[:cut], perm[cut:]
        p = {"W1": rng.normal(0, 0.3, (x.shape[1], HID)), "b1": np.zeros(HID), "W2": rng.normal(0, 0.1, (HID, 2)), "b2": np.zeros(2)}
        m = {q: np.zeros_like(v) for q, v in p.items()}; v2 = {q: np.zeros_like(w) for q, w in p.items()}
        lr, B1, B2 = 0.003, 0.9, 0.999
        def mse(idx):
            h = np.tanh(xs[idx] @ p["W1"] + p["b1"]); q = h @ p["W2"] + p["b2"]
            return ((q[np.arange(len(idx)), a[idx]] - y[idx]) ** 2).mean()
        best = (1e9, None)
        for it in range(1, iters + 1):
            b = rng.choice(tr, 4096)
            h = np.tanh(xs[b] @ p["W1"] + p["b1"]); q = h @ p["W2"] + p["b2"]
            dz = np.zeros_like(q); r = np.arange(len(b))
            dz[r, a[b]] = -2 * (q[r, a[b]] - y[b]) / len(b)
            g = {"W2": h.T @ dz, "b2": dz.sum(0)}
            dh = (dz @ p["W2"].T) * (1 - h ** 2); g["W1"] = xs[b].T @ dh; g["b1"] = dh.sum(0)
            for q_ in p:
                m[q_] = B1 * m[q_] + (1 - B1) * g[q_]; v2[q_] = B2 * v2[q_] + (1 - B2) * g[q_] ** 2
                p[q_] = p[q_] + lr * (m[q_] / (1 - B1 ** it)) / (np.sqrt(v2[q_] / (1 - B2 ** it)) + 1e-8)
            if it % 500 == 0:
                e = mse(te); print(k, it, "train", round(mse(tr[:20000]), 4), "test", round(e, 4), flush=True)
                if e < best[0]: best = (e, {q_: w.copy() for q_, w in p.items()})
        p = best[1]
        # 표준화를 가중치에 합친다
        W1 = p["W1"] / sd[:, None]; b1 = p["b1"] - (mu / sd) @ p["W1"]
        np.savez(os.path.join(ROOT, "ai_%s_policy.npz" % k), W1=W1, b1=b1, W2=p["W2"], b2=p["b2"])
        net = S._Net("ai_%s_policy.npz" % k); q = net.q(x[te]); gain = q[:, 1] - q[:, 0]
        print(k, "samples", len(x), "교체표본", int(a.sum()), "| 시험 표본 Δ>0 비율", round(float((gain > 0).mean()), 3), "평균Δ", round(float(gain.mean()), 4), "표준편차", round(float(gain.std()), 4))

elif mode == "evalp":    # 투수 교체: 원정 팀이 [학습 정책 / 예전 규칙 / 교체 없음]을 쓰고, 홈 팀은 항상 예전 규칙. (교체·대타 끄고 투수 교체만 비교)
    seed = int(sys.argv[2]); budget = float(sys.argv[3])
    rng = np.random.default_rng(seed + 900)
    state, teams = world(); S._nets.clear()
    res = {k: [] for k in ("policy", "rule", "none", "policy_cost", "rule_cost", "none_cost")}; t0 = time.time(); n = 0
    while time.time() - t0 < budget:
        a, h = rng.choice(len(teams), 2, replace=False)
        sd = int(rng.integers(1 << 30)); row = []
        for t in (teams[a], teams[h]):
            for p in state.team_rosters[t]:
                if p.pos == "P": p.status["fatigue"] = 0.0
        gaps_a = LU.pitcher_gaps(state.team_rosters[teams[a]], state); gaps_h = LU.pitcher_gaps(state.team_rosters[teams[h]], state)
        for key in ("policy", "rule", "none"):
            random.seed(sd)
            r = ai_match.play(state, teams[a], teams[h], 200, flags=(False, False), pmodes=(key, "rule"), detail=True)
            if not r: row = None; break
            row.append((key, r[0] - r[1], side_cost(r[4], gaps_h, gaps_a)["opp"]))     # 원정 팀 투수진 비용
        if not row: continue
        for key, d, c in row: res[key].append(d); res[key + "_cost"].append(c)
        n += 1
    np.savez(os.path.join(TMP, "pceval_%d.npz" % seed), **{k: np.array(v) for k, v in res.items()})
    print("games", n, "%.0fs" % (time.time() - t0))

else:  # eval
    seed = int(sys.argv[2]); budget = float(sys.argv[3])
    rng = np.random.default_rng(seed + 500)
    state, teams = world()
    res = {"policy": [], "none": [], "both": [], "home": []}
    t0 = time.time(); n = 0
    S._nets.clear()
    while time.time() - t0 < budget:
        a, h = rng.choice(len(teams), 2, replace=False)
        ta, th = teams[a], teams[h]
        sd = int(rng.integers(1 << 30))
        row = []
        # 팀 ta(원정)만 정책 / 아무도 안 씀 / 둘 다 정책
        for key, fl in (("policy", (True, False)), ("none", (False, False)), ("both", (True, True)), ("home", (False, True))):
            random.seed(sd)
            r = ai_match.play(state, ta, th, 200, flags=fl)
            if not r: row = None; break
            row.append((key, r[0] - r[1]))
        if not row: continue
        for key, d in row: res[key].append(d)
        n += 1
    out = os.path.join(TMP, "subeval_%d.npz" % seed)
    np.savez(out, **{k: np.array(v) for k, v in res.items()})
    print("games", n, "%.0fs" % (time.time() - t0))
