"""사용법: python ai_training/measure_depth.py <분할 0|1> [경기수=100]
주전이 빠졌을 때 대체 선수 종류별 경기당 득실차를 엔진으로 잰다 (슬롯을 짝/홀로 나눠 두 프로세스로 실행 가능).
  a) 같은 포지션 벤치 선수  b) FA 중 해당 포지션 OVR 최고(정책이 후보로 보는 선수)  c) 다른 포지션 벤치 중 최고 OVR
출력: 슬롯별 RD(주전), RD(a), RD(b), RD(c)."""
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_training.env import Env, SLOTS

part = int(sys.argv[1])
G = int(sys.argv[2]) if len(sys.argv) > 2 else 100
e = Env()
rng = random.Random(11)
opps = rng.sample(e.teams, 2)
seeds = [rng.randrange(10 ** 6) for _ in opps]
act = [p for p in e.up if p.status.get("roster", "active") == "active"]
in_lineup = set(id(p) for p in e.base_lineup.values())
by_pos = {}
for p in e.fa:
    by_pos.setdefault(p.pos, []).append(p)


def rd(lineup, order):
    return float(np.mean([e.run_diff(lineup, order, o, G, s)[0] for o, s in zip(opps, seeds)]))


def with_sub(slot, sub):
    lineup = dict(e.base_lineup)
    old = lineup[slot]
    lineup[slot] = sub
    return lineup, [sub if p is old else p for p in e.base_order]


for i, slot in enumerate(SLOTS):
    if i % 2 != part:
        continue
    bench_same = sorted((p for p in act if p.pos == slot and id(p) not in in_lineup), key=lambda p: -p.calculate_ovr())
    bench_other = sorted((p for p in act if p.pos not in (slot, "P") and id(p) not in in_lineup),
                         key=lambda p: -p.calculate_ovr())
    fa_top = max(by_pos[slot], key=lambda p: p.calculate_ovr())
    base = rd(e.base_lineup, e.base_order)
    ra = rd(*with_sub(slot, bench_same[0])) if bench_same else float("nan")
    rb = rd(*with_sub(slot, fa_top))
    rc = rd(*with_sub(slot, bench_other[0])) if (bench_other and slot != "P") else float("nan")
    print("%s starter %.2f | same-pos bench %.2f (OVR %s) | FA best %.2f (OVR %d) | other-pos bench %.2f (OVR %s) | starter OVR %d" % (
        slot, base, ra, bench_same[0].calculate_ovr() if bench_same else "-", rb, fa_top.calculate_ovr(),
        rc, bench_other[0].calculate_ovr() if bench_other and slot != "P" else "-", e.base_lineup[slot].calculate_ovr()), flush=True)
