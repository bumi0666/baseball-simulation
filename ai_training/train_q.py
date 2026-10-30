"""사용법: python ai_training/train_q.py draft|staff [반복수=3000]
완전 정보 환경(draft_staff_env)에서 Q(행동) 회귀 MLP를 학습해 ai_draft_policy.npz / ai_staff_policy.npz로 저장한다."""
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_training import draft_staff_env as E

HID = 24
mode = sys.argv[1]; iters = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
D = E._dist()
if mode == "draft":
    P = D["rookies"]; sample, feats, rets, n_in, na = E.draft_sample, E.draft_features, lambda s: E.draft_returns(s)[:, None], E.D_IN, 1
else:
    P = D["staff"]; sample, feats, rets, n_in, na = E.staff_sample, E.staff_features, E.staff_returns, E.S_IN, 6
rng = np.random.default_rng(1)
perm = rng.permutation(len(P)); tr, te = P[perm[: int(len(P) * 0.8)]], P[perm[int(len(P) * 0.8):]]
p = {"W1": rng.normal(0, 0.3, (n_in, HID)), "b1": np.zeros(HID), "W2": rng.normal(0, 0.1, (HID, na)), "b2": np.zeros(na)}
m = {k: np.zeros_like(v) for k, v in p.items()}; v = {k: np.zeros_like(x) for k, x in p.items()}
ts = sample(20000, np.random.default_rng(99), te); Rt = rets(ts); Ft = feats(ts)
fwd = lambda F: (np.tanh(F @ p["W1"] + p["b1"]), None)
lr, B1, B2 = 0.003, 0.9, 0.999; t0 = time.time()


def report(it):
    h = np.tanh(Ft @ p["W1"] + p["b1"]); q = h @ p["W2"] + p["b2"]
    mse = ((q - Rt) ** 2).mean(); var = Rt.var()
    if mode == "draft":
        # 선택 품질: 20명 중 1명을 고를 때 정책(Q 최대) vs 무작위 vs 현행 규칙(OVR+잠재력 가중 점수)이 고른 신인의 실현 가치
        r = np.random.default_rng(5); g = r.integers(len(Rt), size=(4000, 20)); y = Rt[:, 0]
        pol = y[g[np.arange(4000), q[g, 0].argmax(1)]].mean(); rnd = y[g[:, 0]].mean()
        w = np.minimum(0.8, 0.3 + 0.25 * ts["youth"])
        rule_score = (1 - w) * ts["obs_ovr"] + w * (ts["obs_ovr"] + ts["obs_gap"]) + 4.0 * np.minimum(ts["need"], 2)
        rule = y[g[np.arange(4000), rule_score[g].argmax(1)]].mean(); orc = y[g].max(1).mean()
        extra = f"20명 중 선택: 정책 {pol:+.4f} 규칙 {rule:+.4f} 무작위 {rnd:+.4f} (사후 최선 {orc:+.4f})"
    else:
        ok = np.arange(6)[None, :] <= ts["maxy"][:, None]
        a = np.where(ok, q, -1e9).argmax(1); idx = np.arange(len(a))
        old = np.ones(len(a), dtype=int)
        for i in range(len(a)):
            yrs = 1
            for t in range(2, int(ts["maxy"][i]) + 1):
                gain = 0.05 * ts["stars"][i] * 0.9 ** (t - 1); pen = 0.02 * max(0, ts["age"][i] + t - 60)
                risk = {0.25: 0.04, 0.4: 0.045, 0.15: 0.02, 0.8: 0.10}.get(round(ts["staff_w"][i], 2), 0.05)
                if gain - pen > risk * (t - 1): yrs = t
                else: break
            old[i] = yrs
        Rm = np.where(ok, Rt, -1e9)
        extra = f"정책 {Rt[idx, a].mean():+.4f} 규칙 {Rt[idx, old].mean():+.4f} 사후 최선 {Rm.max(1).mean():+.4f} 분포 {np.bincount(a, minlength=6) / len(a)}"
    print(f"it {it} 시험 R²={1 - mse / var:.3f} | {extra} | {time.time() - t0:.0f}s", flush=True)


for it in range(1, iters + 1):
    s = sample(4096, rng, tr); R = rets(s); F = feats(s)
    h = np.tanh(F @ p["W1"] + p["b1"]); q = h @ p["W2"] + p["b2"]
    dz = -2 * (q - R) / R.size
    g = {"W2": h.T @ dz, "b2": dz.sum(0)}
    dh = (dz @ p["W2"].T) * (1 - h ** 2)
    g["W1"] = F.T @ dh; g["b1"] = dh.sum(0)
    for k in p:
        m[k] = B1 * m[k] + (1 - B1) * g[k]; v[k] = B2 * v[k] + (1 - B2) * g[k] ** 2
        p[k] += lr * (m[k] / (1 - B1 ** it)) / (np.sqrt(v[k] / (1 - B2 ** it)) + 1e-8)
    if it % 1000 == 0 or it == iters:
        report(it)
out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ai_%s_policy.npz" % mode)
np.savez(out, **p); print("saved", out)
