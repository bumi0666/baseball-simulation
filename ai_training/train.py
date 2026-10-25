"""data/shard_*.npz → 소형 MLP(19→16→8→1) 학습 → ai_model.npz 저장 (numpy만 사용)."""
import glob
import os
import sys

import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
files = sorted(glob.glob(os.path.join(here, "data", "shard_8*.npz")))
X = np.concatenate([np.load(f)["X"] for f in files])
y = np.concatenate([np.load(f)["y"] for f in files])
print("samples", len(X), "label mean/std", y.mean().round(3), y.std().round(3))

rng = np.random.default_rng(0)
idx = rng.permutation(len(X))
n_val = len(X) // 5
va, tr = idx[:n_val], idx[n_val:]
mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
Xn = (X - mu) / sd
ys = y.std()
yn = y / ys

H1, H2 = 16, 8
P = {"W1": rng.normal(0, 0.3, (X.shape[1], H1)), "b1": np.zeros(H1),
     "W2": rng.normal(0, 0.3, (H1, H2)), "b2": np.zeros(H2),
     "W3": rng.normal(0, 0.3, (H2, 1)), "b3": np.zeros(1)}


def fwd(P, x):
    h1 = np.tanh(x @ P["W1"] + P["b1"])
    h2 = np.tanh(h1 @ P["W2"] + P["b2"])
    return h1, h2, (h2 @ P["W3"] + P["b3"])[:, 0]


def train(P, lr=0.01, epochs=600, wd=1e-3, bs=64):
    m = {k: np.zeros_like(v) for k, v in P.items()}
    v = {k: np.zeros_like(v) for k, v in P.items()}
    best, best_P = 1e9, None
    t = 0
    for ep in range(epochs):
        order = rng.permutation(tr)
        for i in range(0, len(order), bs):
            b = order[i:i + bs]
            x, t_ = Xn[b], yn[b]
            h1, h2, o = fwd(P, x)
            g = (2 * (o - t_) / len(b))[:, None]
            G = {}
            G["W3"] = h2.T @ g; G["b3"] = g.sum(0)
            d2 = (g @ P["W3"].T) * (1 - h2 ** 2)
            G["W2"] = h1.T @ d2; G["b2"] = d2.sum(0)
            d1 = (d2 @ P["W2"].T) * (1 - h1 ** 2)
            G["W1"] = x.T @ d1; G["b1"] = d1.sum(0)
            t += 1
            for k in P:                                   # Adam
                gk = G[k] + wd * P[k]
                m[k] = 0.9 * m[k] + 0.1 * gk
                v[k] = 0.999 * v[k] + 0.001 * gk ** 2
                P[k] -= lr * (m[k] / (1 - 0.9 ** t)) / (np.sqrt(v[k] / (1 - 0.999 ** t)) + 1e-8)
        vl = np.mean((fwd(P, Xn[va])[2] - yn[va]) ** 2)
        if vl < best:
            best, best_P = vl, {k: a.copy() for k, a in P.items()}
    return best, best_P


best, P = train(P)
_, _, pv = fwd(P, Xn[va])
corr = np.corrcoef(pv, yn[va])[0, 1]
# 비교 기준: 선형 회귀
A = np.c_[Xn[tr], np.ones(len(tr))]
w = np.linalg.lstsq(A, yn[tr], rcond=None)[0]
lin = np.c_[Xn[va], np.ones(len(va))] @ w
print("val MSE (norm) %.3f  corr %.3f | linear corr %.3f | ovr-diff-only corr %.3f" % (
    best, corr, np.corrcoef(lin, yn[va])[0, 1],
    np.corrcoef(X[va][:, 9:18].mean(1), y[va])[0, 1]))
np.savez(os.path.join(os.path.dirname(here), "ai_model.npz"), mu=mu, sd=sd, ys=ys, **P)
print("saved ai_model.npz")
