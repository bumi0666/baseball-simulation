"""사용법: python ai_training/eval_policy_engine.py [에피소드수=4] [경기수=100]
학습한 거래 정책을 실제 FA 풀에서 돌려, 게임 엔진으로 라인업 성능(득실차)을 직접 비교한다."""
import os
import random
import sys
import time
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_training.env import Env, SLOTS
from ai_training import policy_env as PE
from ai_training.train_policy import Policy, rollout, rule_rollout
from ai_advisor import make_features

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
n_ep = int(sys.argv[1]) if len(sys.argv) > 1 else 4
G = int(sys.argv[2]) if len(sys.argv) > 2 else 100
pol = Policy.load(os.path.join(ROOT, "ai_gm_policy.npz"))
e = Env()
rng = random.Random(77)
nrng = np.random.default_rng(77)
by_pos = {}
for p in e.fa:
    by_pos.setdefault(p.pos, []).append(p)
payroll = float(os.environ.get('PAYROLL', sum(p.salary() for p in e.state.team_rosters[e.state.user_team])))


def build_episode():
    cands = []
    for s, pos in enumerate(SLOTS):
        inc = e.base_lineup[pos]
        top = sorted(rng.sample(by_pos[pos], 40), key=lambda p: -p.calculate_ovr())[:PE.CAND_PER_GROUP]
        for c in top:
            cands.append((s, c, inc))
    ep = SimpleNamespace(
        slot=np.array([c[0] for c in cands]), rows=np.arange(len(cands)),
        demand=np.array([c[1].base_salary() * 1.15 for c in cands]),
        inc_sal=np.array([c[2].salary() for c in cands], dtype=float),
        payroll=float(payroll), cap=float(os.environ.get('CAP', PE.WAGE_CAP)), sal_w=float(os.environ.get('SAL_W', 1.0)),
        move_w=1.0, max_moves=PE.MAX_MOVES, need=np.zeros(len(cands)), dead=np.zeros(len(cands)),
        X=np.array([make_features(c[1], c[2]) for c in cands]),
        reward_vec=np.zeros(len(cands)))
    return cands, ep


def apply(chosen, cands):
    lineup, order = dict(e.base_lineup), list(e.base_order)
    for i in chosen:
        s, c, inc = cands[i]
        pos = SLOTS[s]
        old = lineup[pos]
        lineup[pos] = c
        order = [c if p is old else p for p in order]
    return lineup, order


tot = {"noop": 0.0, "rule": 0.0, "policy": 0.0}
t0 = time.time()
for k in range(n_ep):
    cands, ep = build_episode()
    ch_p, ch_r = [], []
    rollout(pol, ep, nrng, greedy=True, chosen=ch_p)
    rule_rollout(ep, 0.30, chosen=ch_r)
    res = {}
    for opp in rng.sample(e.teams, 2):
        seed = rng.randrange(10 ** 6)
        base, _ = e.run_diff(e.base_lineup, e.base_order, opp, G, seed)
        for name, ch in (("rule", ch_r), ("policy", ch_p)):
            lu, od = apply(ch, cands)
            d, _ = e.run_diff(lu, od, opp, G, seed)
            res.setdefault(name, []).append(d - base)
    for name in ("rule", "policy"):
        tot[name] += np.mean(res[name])
    net = lambda ch: sum(ep.demand[i] - ep.inc_sal[i] for i in ch) / 1000
    print(f"ep{k}: 규칙 {len(ch_r)}명 Δ{np.mean(res['rule']):+.2f} (순증 연봉 {net(ch_r):+.0f}k) | "
          f"정책 {len(ch_p)}명 Δ{np.mean(res['policy']):+.2f} (순증 연봉 {net(ch_p):+.0f}k) | {time.time() - t0:.0f}s", flush=True)
print({k: round(v / n_ep, 3) for k, v in tot.items()}, "(경기당 득실차 변화, noop=0)")
