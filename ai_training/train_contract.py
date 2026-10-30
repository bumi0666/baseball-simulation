"""사용법: python ai_training/train_contract.py [반복수=3000]
계약 정책: MLP가 각 행동(0=방출, 1..max_years=계약기간)의 기대 보상 Q(a)를 예측하도록 학습하고, 가장 큰 Q의 행동을 고른다.
환경이 모든 행동의 실현 보상을 계산해 주므로(완전 정보) 정책 기울기 대신 Q 회귀(MSE)를 쓴다 — 소프트맥스 포화로 행동이 죽는 문제가 없고,
'방출하고 싶은 정도'가 Q(방출) - Q(유지)라는 점/경기 단위의 값이 된다. ai_contract_policy.npz로 저장한다."""
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_training import contract_env as CE

HID = 24
BETA = 12.0      # 보상(점/경기) 차이를 로짓으로
NA = CE.MAX_Y + 1


def valid_mask(s):
    ys = np.arange(NA)[None, :]
    rem = s["rem"][:, None]; maxy = s["maxy"][:, None]
    return (ys == 0) | ((rem == 0) & (ys <= maxy)) | ((rem > 0) & (ys == rem))


def init(rng):
    return {"W1": rng.normal(0, 0.3, (CE.N_IN, HID)), "b1": np.zeros(HID),
            "W2": rng.normal(0, 0.1, (HID, NA)), "b2": np.zeros(NA)}


def forward(p, F, ok):
    h = np.tanh(F @ p["W1"] + p["b1"])
    q = h @ p["W2"] + p["b2"]
    pr = np.zeros_like(q); pr[np.arange(len(q)), np.where(ok, q, -1e9).argmax(1)] = 1.0     # 평가용: 최대 Q 행동
    return pr, h, q


def old_rule(s):
    """예전 규칙을 같은 환경에서 비교하기 위해 재현: 1군/신규 계약은 choose_years, 2군은 '전망 부족이면 방출, 아니면 2년'"""
    from ai_team_manager import STYLES, OVR_RUNS, YEAR_DISCOUNT, REPL_OVR, REPL_SALARY, NEED_RUNS
    risk = {(v["sal_w"], v["youth"]): v["risk"] for v in STYLES.values()}
    path = CE.proj_path(s["ovr"], s["age"], s["gap"], CE.MAX_Y)
    out = np.ones(len(s["age"]), dtype=int)
    for i in range(len(out)):
        if s["farm"][i] > 0:
            out[i] = int(s["rem"][i]) if s["rem"][i] > 0 else (0 if s["ovr"][i] + 0.5 * s["gap"][i] < REPL_OVR else min(2, int(s["maxy"][i])))
            continue
        r = risk.get((round(s["sal_w"][i], 1), round(s["youth"][i], 1)), 0.05)
        yrs = 1
        for t in range(1, int(s["maxy"][i]) + 1):
            v = OVR_RUNS * (path[i, t - 1] - REPL_OVR) + NEED_RUNS * min(s["need"][i], 2)
            c = 0.10 * (s["s0"][i] - REPL_SALARY) / 50_000
            u = (YEAR_DISCOUNT ** (t - 1)) * (v - c)
            if t == 1: continue
            if u > r * (t - 1): yrs = t
            else: break
        out[i] = yrs
    return out


def evaluate(p, s, R):
    ok = valid_mask(s)
    pr, _, _ = forward(p, CE.features(s), ok)
    a = pr.argmax(1); n = len(a); idx = np.arange(n)
    Rm = np.where(ok, R, -1e9); rule = old_rule(s)
    f = s["farm"] > 0
    res = {}
    for name, m in (("1군", ~f), ("2군", f)):
        res[name] = dict(policy=R[idx, a][m].mean(), rule=R[idx, rule][m].mean(), oracle=Rm.max(1)[m].mean(),
                         release=(a[m] == 0).mean(), rule_release=(rule[m] == 0).mean())
    res["dist"] = np.bincount(a, minlength=NA) / n
    return res


if __name__ == "__main__":
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    P = CE.load_players()
    rng = np.random.default_rng(1)
    perm = rng.permutation(len(P)); tr, te = P[perm[: int(len(P) * 0.8)]], P[perm[int(len(P) * 0.8):]]   # 선수 단위 분할
    p = init(rng); m = {k: np.zeros_like(v) for k, v in p.items()}; v = {k: np.zeros_like(x) for k, x in p.items()}
    ts = CE.sample(20000, np.random.default_rng(99), te); Rt = CE.returns(ts)
    lr, B1, B2 = 0.003, 0.9, 0.999; t0 = time.time()
    for it in range(1, iters + 1):
        s = CE.sample(4096, rng, tr); R = CE.returns(s); F = CE.features(s); ok = valid_mask(s)
        _, h, q = forward(p, F, ok)
        err = np.where(ok, q - np.where(ok, R, 0.0), 0.0)
        dz = -2 * err / ok.sum()      # 아래 갱신식이 += 이므로 손실의 음의 기울기
        g = {"W2": h.T @ dz, "b2": dz.sum(0)}
        dh = (dz @ p["W2"].T) * (1 - h ** 2)
        g["W1"] = F.T @ dh; g["b1"] = dh.sum(0)
        for k in p:
            m[k] = B1 * m[k] + (1 - B1) * g[k]; v[k] = B2 * v[k] + (1 - B2) * g[k] ** 2
            p[k] += lr * (m[k] / (1 - B1 ** it)) / (np.sqrt(v[k] / (1 - B2 ** it)) + 1e-8)
        if it % 500 == 0 or it == iters:
            e = evaluate(p, ts, Rt)
            f = lambda d: " ".join(f"{k} {x:+.4f}" if k in ("policy", "rule", "oracle") else f"{k} {x:.2f}" for k, x in d.items())
            print(f"it {it} 1군[{f(e['1군'])}] 2군[{f(e['2군'])}] dist {e['dist'].round(2)} | {time.time()-t0:.0f}s", flush=True)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ai_contract_policy.npz")
    np.savez(out, beta=BETA, **p)
    print("saved", out)
