"""사용법: python ai_training/gen_data_team.py <shard번호> <기준팀> <시나리오수> [경기수=60] [시간제한(초)]
기준 라인업을 유저 팀이 아니라 지정한 구단(의 OVR 최고 라인업)으로 바꿔 라벨을 만든다.
구단마다 주전 구성이 달라 정책 학습 데이터의 '현 주전' 다양성(그룹 수)이 늘어난다."""
import os
import random
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_training.env import Env, SLOTS
from ai_advisor import make_features

shard, team, n_sc = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
G = int(sys.argv[4]) if len(sys.argv) > 4 else 60
BUDGET = float(sys.argv[5]) if len(sys.argv) > 5 else 1e9
K = int(os.environ.get("GEN_K", 12))

e = Env()
roster = [p for p in e.state.team_rosters[team] if p.status.get("roster", "active") == "active"]
lineup = {}
for pos in SLOTS:
    lineup[pos] = max((p for p in roster if p.pos == pos), key=lambda p: p.calculate_ovr())
bat = [lineup[k] for k in SLOTS if k != "P"]
order = sorted(bat, key=lambda p: -p.calculate_ovr())[:9]
pit = sorted((p for p in roster if p.pos == "P" and p is not lineup["P"]), key=lambda p: -p.calculate_ovr())
e.base_lineup, e.base_order, e.up = dict(lineup), list(order), roster
e.state.bullpen = (pit + [None] * 8)[:8]
e.teams = [t for t in e.teams if t != team]
by_pos = {}
for p in e.fa:
    by_pos.setdefault(p.pos, []).append(p)

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
rng = random.Random(5000 + shard)
X, Y = [], []
t0 = time.time()
for sc in range(n_sc):
    opp = rng.choice(e.teams)
    seed = rng.randrange(10**6)
    base_d, _ = e.run_diff(e.base_lineup, e.base_order, opp, G, seed)
    for _ in range(K):
        slot = "P" if rng.random() < 0.25 else rng.choice(SLOTS[1:])
        cand = rng.choice(by_pos[slot])
        lu, od, old = e.swapped(slot, cand)
        d, _ = e.run_diff(lu, od, opp, G, seed)
        X.append(make_features(cand, old))
        Y.append(d - base_d)
    last = (time.time() - t0 > BUDGET) or sc == n_sc - 1
    if last or (sc + 1) % 2 == 0:
        np.savez(os.path.join(out_dir, f"tshard_{shard}.npz"), X=np.array(X, dtype=np.float32),
                 y=np.array(Y, dtype=np.float32), team=team, games=G)
        print(f"tshard {shard} ({team}): {sc + 1}/{n_sc} scenarios, {len(X)} samples, {time.time() - t0:.0f}s", flush=True)
    if last:
        break
