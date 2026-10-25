"""정책 비교: FA 후보 10명 중 1명을 고를 때, 각 방식이 고른 선수의 '실제' 득실차 이득을
시뮬레이션(경기 G회)으로 측정한다.  사용법: python eval_policy.py <shard> <시나리오수> <G> <시간제한초>"""
import os
import random
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_training.env import Env
import ai_advisor as A

shard, n_sc, G, BUDGET = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
e = Env()
rule, nn = A.RuleBasedAdvisor(), A.NNAdvisor()
rng = random.Random(7000 + shard)
POLICIES = ["random", "highest_ovr", "rule", "nn"]
rows = []
t0 = time.time()
pitchers = [p for p in e.fa if p.pos == "P"]
batters = [p for p in e.fa if p.pos != "P"]
for sc in range(n_sc):
    opp, seed = rng.choice(e.teams), rng.randrange(10**6)
    pool = rng.sample(batters, 7) + rng.sample(pitchers, 3)      # 타자 7 + 투수 3
    e.state.lineup, e.state.batting_order = e.base_lineup, e.base_order
    picks = {
        "random": pool[0],
        "highest_ovr": max(pool, key=lambda p: p.calculate_ovr()),
        "rule": max(pool, key=lambda p: rule._gain(e.state, e.up, p, A._worst_starter_ovr(e.up, p.pos))[0]),
        "nn": max(pool, key=lambda p: nn._gain(e.state, e.up, p, A._worst_starter_ovr(e.up, p.pos))[0]),
    }
    base = e.run_diff(e.base_lineup, e.base_order, opp, G, seed)[0]
    cache, row = {}, []
    for pol in POLICIES:
        c = picks[pol]
        if c.id not in cache:
            lu, od, _ = e.swapped(c.pos, c)
            cache[c.id] = e.run_diff(lu, od, opp, G, seed)[0] - base
        row.append(cache[c.id])
    rows.append(row)
    done = time.time() - t0 > BUDGET or sc == n_sc - 1
    np.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", f"eval_{shard}.npy"), np.array(rows))
    print(f"eval {shard}: {sc + 1} scenarios {time.time() - t0:.0f}s", flush=True)
    if done:
        break
