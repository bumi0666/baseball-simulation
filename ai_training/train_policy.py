"""사용법: python ai_training/train_policy.py [반복수=1500]
REINFORCE로 거래 정책(후보 점수망 + 유지 로짓)을 학습해 ai_gm_policy.npz로 저장한다."""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_training import policy_env as PE

H = 16
BETA = 10.0          # 로짓 스케일 (득실차 0.1점 차이 ≈ 로짓 1)
V_KEYS = ("mu", "sd", "W1", "b1", "W2", "b2", "W3", "b3", "ys")


def _v_net(vm, X):
    """가치망(ai_model.npz): 후보 특징 -> 예상 득실차 이득(점/경기)"""
    x = (X - vm["mu"]) / vm["sd"]
    h = np.tanh(np.tanh(x @ vm["W1"] + vm["b1"]) @ vm["W2"] + vm["b2"])
    return ((h @ vm["W3"] + vm["b3"]) * vm["ys"]).reshape(len(X))


class Policy:
    """점수 = BETA * (가치망 예측 + 학습되는 잔차망(후보 특징+비용 맥락)),
    유지 로짓 = BETA * (nw · [1, 임금 여유, 남은 횟수]). 가치망 위에 REINFORCE로 정책을 학습한다."""

    def __init__(self, rng=None, mu=None, sd=None, vm=None):
        r = rng or np.random.default_rng(0)
        self.p = {
            "W1": r.normal(0, 0.3, (PE.N_IN, H)), "b1": np.zeros(H),
            "w2": np.zeros(H), "b2": np.zeros(1),
            "nw": np.array([0.2, 0.0, 0.0, 0.0, 0.0]),       # 처음엔 현행 규칙처럼 '이득 0.2 넘으면 영입'
        }
        self.mu = np.zeros(PE.N_IN) if mu is None else mu
        self.sd = np.ones(PE.N_IN) if sd is None else sd
        if vm is None:
            d = np.load(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ai_model.npz"))
            vm = {k: d[k] for k in V_KEYS}
        self.vm = vm

    def scores(self, F):
        Z = (F - self.mu) / self.sd
        h = np.tanh(Z @ self.p["W1"] + self.p["b1"])
        v = _v_net(self.vm, F[:, :PE.N_FEAT])
        return BETA * (v + h @ self.p["w2"] + self.p["b2"][0]), Z, h

    def noop_logit(self, room, moves_left, sal_w=1.0, move_w=1.0):
        g = np.array([1.0, room / 1e6, moves_left / PE.MAX_MOVES, sal_w - 1.0, move_w - 1.0])
        return BETA * float(g @ self.p["nw"]), g

    def logits(self, F, room, moves_left, sal_w=1.0, move_w=1.0):
        s, Z, h = self.scores(F)
        n, g = self.noop_logit(room, moves_left, sal_w, move_w)
        return np.concatenate([[n], s]), (Z, h, g)

    def save(self, path):
        np.savez(path, mu=self.mu, sd=self.sd, beta=BETA,
                 **{"v_" + k: self.vm[k] for k in V_KEYS}, **self.p)

    @classmethod
    def load(cls, path):
        d = np.load(path)
        pol = cls(mu=d["mu"], sd=d["sd"], vm={k: d["v_" + k] for k in V_KEYS})
        pol.p = {k: d[k] for k in ("W1", "b1", "w2", "b2", "nw")}
        return pol


def rollout(pol, ep, rng, greedy=False, record=None, chosen=None):
    """에피소드를 돌려 총 보상, 이동 횟수를 돌려준다. record가 리스트면 (스텝 정보)를 쌓는다."""
    used = set()
    payroll, total, moves = ep.payroll, 0.0, 0
    for t in range(ep.max_moves):
        ok = np.array([ep.slot[i] not in used and payroll - ep.inc_sal[i] + ep.demand[i] <= ep.cap
                       for i in range(len(ep.rows))])
        idx = np.nonzero(ok)[0]
        if len(idx) == 0:
            break
        left = ep.max_moves - t
        ctx = PE.context(ep, ep.demand[idx], ep.inc_sal[idx], payroll, left, ep.need[idx], ep.dead[idx])
        F = np.hstack([ep.X[idx], ctx])
        z, cache = pol.logits(F, ep.cap - payroll, left, ep.sal_w, ep.move_w)
        pr = np.exp(z - z.max()); pr /= pr.sum()
        a = int(np.argmax(pr)) if greedy else int(rng.choice(len(pr), p=pr))
        if record is not None:
            record.append((cache, pr, a))
        if a == 0:
            break
        i = idx[a - 1]
        total += PE.move_reward(ep.reward_vec[i], ep.demand[i], ep.inc_sal[i], ep.sal_w, ep.move_w, ep.dead[i])
        payroll += ep.demand[i] - ep.inc_sal[i]
        used.add(int(ep.slot[i]))
        moves += 1
        if chosen is not None:
            chosen.append(int(i))
    return total, moves


def grads(pol, rec, adv, ent_coef):
    """한 에피소드의 sum_t adv * grad log pi(a_t) (+엔트로피) 를 누적한 그래디언트"""
    g = {k: np.zeros_like(v) for k, v in pol.p.items()}
    for (Z, h, gg), pr, a in rec:
        dz = -pr.copy(); dz[a] += 1.0                       # d log pi / d logits
        logp = np.log(pr + 1e-12)
        ent = -(pr * logp).sum()
        dz = adv * dz + ent_coef * (-pr * (logp + ent))     # 엔트로피 보너스 기울기
        g["nw"] += BETA * dz[0] * gg
        ds = BETA * dz[1:]
        if len(ds):
            g["w2"] += h.T @ ds
            g["b2"] += ds.sum()
            dh = np.outer(ds, pol.p["w2"]) * (1 - h ** 2)
            g["W1"] += Z.T @ dh
            g["b1"] += dh.sum(0)
    return g


_NN = None


def nn_gain(X):
    """게임이 쓰는 가치망(ai_model.npz)의 예상 득실차 이득"""
    global _NN
    if _NN is None:
        _NN = np.load(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ai_model.npz"))
    m = _NN
    x = (X - m["mu"]) / m["sd"]
    h = np.tanh(np.tanh(x @ m["W1"] + m["b1"]) @ m["W2"] + m["b2"])
    return ((h @ m["W3"] + m["b3"]) * m["ys"]).reshape(len(X))


def rule_rollout(ep, thr=0.30, chosen=None):
    """현행 규칙: 가치망 예측이 thr을 넘는 최고 후보를 순서대로 영입 (비용은 고려하지 않음)"""
    V = nn_gain(ep.X)
    used = set(); payroll = ep.payroll; total = 0.0; moves = 0
    for _ in range(ep.max_moves):
        best = None
        for i in range(len(V)):
            if ep.slot[i] in used or payroll - ep.inc_sal[i] + ep.demand[i] > ep.cap:
                continue
            if V[i] > thr and (best is None or V[i] > V[best]):
                best = i
        if best is None:
            break
        total += PE.move_reward(ep.reward_vec[best], ep.demand[best], ep.inc_sal[best], ep.sal_w, ep.move_w, ep.dead[best])
        payroll += ep.demand[best] - ep.inc_sal[best]; used.add(int(ep.slot[best])); moves += 1
        if chosen is not None:
            chosen.append(int(best))
    return total, moves


def evaluate_all(pol, X, Y, groups, n=2000, seed=123):
    rng = np.random.default_rng(seed)
    out = {"policy": [0, 0], "rule": [0, 0]}
    for _ in range(n):
        ep = PE.Episode(X, Y, groups, rng)
        r, m = rollout(pol, ep, rng, greedy=True); out["policy"][0] += r; out["policy"][1] += m
        r, m = rule_rollout(ep, thr=0.10 if PE.SWAP else 0.30); out["rule"][0] += r; out["rule"][1] += m
    return {k: (round(v[0] / n, 3), round(v[1] / n, 2)) for k, v in out.items()}


def evaluate(pol, X, Y, groups, n=1500, seed=123):
    rng = np.random.default_rng(seed)
    tot = mv = 0.0
    for _ in range(n):
        ep = PE.Episode(X, Y, groups, rng)
        r, m = rollout(pol, ep, rng, greedy=True)
        tot += r; mv += m
    return tot / n, mv / n


if __name__ == "__main__":
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    PE.SWAP = os.environ.get("MODE") == "swap"
    OUT_NAME = "ai_swap_policy.npz" if PE.SWAP else "ai_gm_policy.npz"
    X, Y, groups = PE.load("train")
    Xv, Yv, vgroups = PE.load("val")                 # 학습·가치망에 쓰지 않은 구단(Giants): 체크포인트 선택용
    Xt, Yt, gt = PE.load("test")                     # 또 다른 미사용 구단(Heroes): 최종 시험용
    print("train samples", len(X), "groups", len(groups), "| val", len(Xv), len(vgroups), "| test", len(Xt), len(gt), flush=True)
    base = np.hstack([X, np.column_stack([np.full(len(X), 0.8), np.zeros(len(X)), np.full(len(X), 0.6), np.full(len(X), 0.6), np.full(len(X), 3.0), np.full(len(X), 1.0), np.full(len(X), 1.0), np.zeros(len(X)), np.zeros(len(X))])])
    mu0, sd0 = base.mean(0), base.std(0) + 1e-6
    mu0[PE.N_FEAT:] = [0.8, 0.3, 0.6, 0.6, 3.0, 1.0, 1.0, 0.3, 0.3]            # 비용 맥락은 상수로 만든 base 대신 실제 범위로 정규화
    sd0[PE.N_FEAT:] = [0.2, 0.5, 0.3, 0.3, 0.4, 0.4, 0.3, 0.6, 0.5]
    pol = Policy(mu=mu0, sd=sd0)
    _out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), OUT_NAME)
    if os.environ.get("RESUME"):
        pol = Policy.load(_out)
    rng = np.random.default_rng(int(os.environ.get("SEED", 1)))
    m = {k: np.zeros_like(v) for k, v in pol.p.items()}
    v = {k: np.zeros_like(x) for k, x in pol.p.items()}
    lr, B1, B2 = float(os.environ.get('LR', 0.003)), 0.9, 0.999
    t0 = time.time(); bsz = 128; baseline = 0.0; best = (-9, None)
    for it in range(1, iters + 1):
        recs, rets = [], []
        for _ in range(bsz):
            ep = PE.Episode(X, Y, groups, rng)
            rec = []
            r, _ = rollout(pol, ep, rng, record=rec)
            recs.append(rec); rets.append(r)
        rets = np.array(rets)
        baseline = 0.9 * baseline + 0.1 * rets.mean() if it > 1 else rets.mean()
        adv = (rets - baseline)
        adv = adv / (rets.std() + 1e-6)
        grad = {k: np.zeros_like(x) for k, x in pol.p.items()}
        for rec, a in zip(recs, adv):
            g = grads(pol, rec, a, 0.01)
            for k in grad: grad[k] += g[k] / bsz
        for k in pol.p:
            m[k] = B1 * m[k] + (1 - B1) * grad[k]
            v[k] = B2 * v[k] + (1 - B2) * grad[k] ** 2
            pol.p[k] += lr * (m[k] / (1 - B1 ** it)) / (np.sqrt(v[k] / (1 - B2 ** it)) + 1e-8)
        if it % 100 == 0 or it == iters:
            vr, vm = evaluate(pol, Xv, Yv, vgroups, 600, seed=7)
            if vr > best[0]:
                best = (vr, {k: x.copy() for k, x in pol.p.items()})
            print(f"it {it} batch_ret {rets.mean():+.3f} | val greedy ({vr:+.3f}, {vm:.2f} moves) | {time.time() - t0:.0f}s", flush=True)
    pol.p = best[1]
    print("best val", round(best[0], 3))
    for name, (XX, YY, GG) in (("검증 구단(Giants)", (Xv, Yv, vgroups)), ("시험 구단(Heroes)", (Xt, Yt, gt))):
        print(name, evaluate_all(pol, XX, YY, GG, 1500, seed=99))
    out = _out
    pol.save(out)
    print("saved", out)
