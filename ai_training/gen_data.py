"""사용법: python ai_training/gen_data.py <shard번호> <시나리오수> [경기수=150]
시나리오 = (상대팀, 시드) 하나당 기준 경기 + 후보 8명 교체 경기를 돌려 라벨을 만든다."""
import os
import random
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_training.env import Env, SLOTS
from ai_advisor import make_features

shard = int(sys.argv[1])
n_sc = int(sys.argv[2])
G = int(sys.argv[3]) if len(sys.argv) > 3 else 150
K = int(os.environ.get("GEN_K", 12))
BUDGET = float(sys.argv[4]) if len(sys.argv) > 4 else 1e9   # 초 단위 시간 제한

e = Env()
rng = random.Random(1000 + shard)
by_pos = {}
for p in e.fa:
    by_pos.setdefault(p.pos, []).append(p)

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(out_dir, exist_ok=True)
X, Y, W = [], [], []
t0 = time.time()
for sc in range(n_sc):
    opp = rng.choice(e.teams)
    seed = rng.randrange(10**6)
    base_d, base_w = e.run_diff(e.base_lineup, e.base_order, opp, G, seed)
    for _ in range(K):
        slot = "P" if rng.random() < 0.25 else rng.choice(SLOTS[1:])   # 투수 교체 샘플 비중 확대
        cand = rng.choice(by_pos[slot])
        lineup, order, old = e.swapped(slot, cand)
        d, w = e.run_diff(lineup, order, opp, G, seed)
        X.append(make_features(cand, old))
        Y.append(d - base_d)
        W.append(w - base_w)
    last = (time.time() - t0 > BUDGET) or sc == n_sc - 1
    if (sc + 1) % 2 == 0 or last:
        np.savez(os.path.join(out_dir, f"shard_{shard}.npz"), X=np.array(X, dtype=np.float32),
                 y=np.array(Y, dtype=np.float32), w=np.array(W, dtype=np.float32), games=G)
        print(f"shard {shard}: {sc + 1}/{n_sc} scenarios, {len(X)} samples, {time.time() - t0:.0f}s", flush=True)
    if last:
        break
