"""거래 정책 학습 환경.

한 에피소드 = 구단이 시즌 중 최대 MAX_MOVES번 FA 영입(=슬롯 교체) 기회를 얻는 의사결정 열.
  · 각 시점에서 정책은 {유지(no-op)} ∪ {후보 FA로 해당 슬롯 교체} 중 하나를 고른다.
  · 교체의 보상은 게임 엔진으로 측정한 경기당 득실차 변화(ai_training/data의 라벨)이다.
  · 비용: 영입 1회당 MOVE_COST, 순증가 연봉당 SALARY_COST. 임금 상한을 넘는 교체는 불가능.
후보의 요구 연봉은 게임과 같은 분포(5만~11.5만, 시장가치와 능력치는 독립)에서 뽑는다.
"""
import glob
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_MOVES = 4
MOVE_COST = 0.03            # 영입 1회 마찰 비용 (득실차 점/경기 단위)
SALARY_COST = 0.10          # 순증가 연봉 5만당 비용 (점/경기)
WAGE_CAP = 3_000_000
N_FEAT = 19
N_CTX = 8
NEED_RUNS = 0.50          # 부족한 포지션 1명을 채울 때의 보너스 (점/경기)
P_SHORT = 0.25             # 슬롯의 포지션이 부족한 상태일 확률
N_IN = N_FEAT + N_CTX
CAND_PER_GROUP = 3
# 구단 성향별 비용 가중 (ai_team_manager.STYLES의 sal_w, move_w, signings, cap_mult와 같은 값)
STYLE_TABLE = {
    "WinNow": dict(sal_w=0.7, move_w=0.8, moves=4, cap_mult=1.00),
    "Youth": dict(sal_w=1.0, move_w=1.3, moves=4, cap_mult=1.00),
    "Balanced": dict(sal_w=1.0, move_w=1.0, moves=4, cap_mult=1.00),
    "BigSpender": dict(sal_w=0.5, move_w=0.6, moves=4, cap_mult=1.10),
    "Frugal": dict(sal_w=1.8, move_w=1.5, moves=3, cap_mult=0.90),
}


def load(split):
    """split='train'이면 shard_8* 제외, 'test'면 shard_8*만."""
    X, Y = [], []
    for f in sorted(glob.glob(os.path.join(HERE, "data", "shard_*.npz"))):
        is_test = os.path.basename(f).startswith("shard_8")
        if (split == "test") != is_test:
            continue
        d = np.load(f)
        X.append(d["X"]); Y.append(d["y"])
    X = np.concatenate(X).astype(np.float64)
    Y = np.concatenate(Y).astype(np.float64)
    inc = np.round(X[:, :9] - X[:, 9:18], 3)
    _, gid = np.unique(inc, axis=0, return_inverse=True)
    groups = {}
    for i, g in enumerate(gid):
        groups.setdefault(int(g), []).append(i)
    groups = {g: np.array(v) for g, v in groups.items() if len(v) >= 8}
    return X, Y, groups


class Episode:
    """후보 목록과 비용 맥락을 가진 한 번의 의사결정 열."""

    def __init__(self, X, Y, groups, rng):
        gids = list(groups.keys())
        rng.shuffle(gids)
        self.style = list(STYLE_TABLE)[int(rng.integers(len(STYLE_TABLE)))]
        st = STYLE_TABLE[self.style]
        self.sal_w, self.move_w, self.max_moves = st["sal_w"], st["move_w"], st["moves"]
        budget = rng.uniform(25e6, 50e6)                      # 구단 재정(예산)에 따라 임금 상한이 달라진다
        self.cap = WAGE_CAP * (budget / 37e6) ** 0.5 * st["cap_mult"]
        self.slot, self.rows, self.demand, self.inc_sal, self.need = [], [], [], [], []
        for s, g in enumerate(gids[:10]):
            pool = groups[g]
            draw = pool[rng.choice(len(pool), size=min(40, len(pool)), replace=False)]
            draw = sorted(draw, key=lambda i: -X[i, :9].mean())[:CAND_PER_GROUP]   # 게임처럼 OVR 상위 후보만
            sal = rng.uniform(50_000, 100_000)
            need = 0 if rng.random() > P_SHORT else int(rng.integers(1, 3))   # 포지션 부족 인원: 부족하면 방출 없이 영입
            if need:
                sal = 0.0
            for i in draw:
                self.slot.append(s)
                self.need.append(need)
                self.rows.append(i)
                self.demand.append(rng.uniform(50_000, 115_000) * 1.0)
                self.inc_sal.append(sal)
        self.slot = np.array(self.slot)
        self.need = np.array(self.need, dtype=float)
        self.rows = np.array(self.rows)
        self.demand = np.array(self.demand)
        self.inc_sal = np.array(self.inc_sal)
        self.payroll = self.cap * rng.uniform(0.73, 0.97)   # 임금 상한에 가까운 구단도 포함
        self.reward_vec = Y[self.rows] + NEED_RUNS * self.need
        self.X = X[self.rows]


def context(ep, demand, inc_sal, payroll, moves_left, need):
    room = ep.cap - payroll
    n = len(demand)
    return np.column_stack([
        demand / 1e5,
        (demand - inc_sal) / 5e4,
        np.full(n, room / 1e6),
        np.full(n, moves_left / MAX_MOVES),
        np.full(n, ep.cap / 1e6),
        np.full(n, ep.sal_w),
        np.full(n, ep.move_w),
        need,
    ])


def move_reward(y, demand, inc_sal, sal_w=1.0, move_w=1.0):
    return y - MOVE_COST * move_w - SALARY_COST * sal_w * (demand - inc_sal) / 5e4
