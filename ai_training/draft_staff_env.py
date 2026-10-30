"""드래프트·스태프 정책 학습 환경 (완전 정보 맥락 밴딧 → Q 회귀).

[드래프트] 행동 = 이 신인을 지명한다. 보상 = 6년 지평(구단 인내심 gamma로 할인)의 실현 가치:
  · 신인은 2군으로 입단(연봉 3만~5만, 3년 계약 후 시장가 재계약), 능력이 주전 수준(STARTER_OVR)을 넘으면 그만큼 득점 가치,
    부상 대비 가치(contract_env.farm_value)가 있고, 부족한 포지션이면 NEED_COVER(=측정한 필요도 NEED_RUNS)가 3년간 더해진다.
  · 성장은 실측한 게임 규칙(연 +0.9, 젊은 2군은 +50%)에 무작위 오차. 정책이 보는 능력치·잠재력은 스카우팅 오차가 섞인 값이다.
[스태프] 행동 = 계약 기간 1..5년. 보상: 별 1개 = 0.05점/경기(기존 효용과 같은 환산), 연봉 비용 = 0.05 × staff_w × 연봉/10만.
  · 60세 이후 해마다 유효 별이 0.25개씩 줄고 은퇴(재계약 불가) 확률이 커진다. 계약 중에는 AI가 내보낼 수 없어(게임 규칙) 연봉이 고정이다.
  · 계약 후 시장가 재계약은 이득일 때만, 협상 실패 확률 LEAVE_P.
"""
import os

import numpy as np

from ai_training.contract_env import (HERE, OVR_RUNS, REPL_OVR, NEED_RUNS, LEAVE_P, FARM_SALARY,
                                      farm_value, proj_path)

H = 6
NEED_COVER = NEED_RUNS
PATIENCE = {"WinNow": 0.80, "Youth": 0.95, "Balanced": 0.90, "BigSpender": 0.90, "Frugal": 0.88}
YOUTH = {"WinNow": 0.3, "Youth": 1.6, "Balanced": 0.8, "BigSpender": 0.5, "Frugal": 0.8}
STAFF_W = {"WinNow": 0.25, "Youth": 0.4, "Balanced": 0.4, "BigSpender": 0.15, "Frugal": 0.8}
MAX_YEARS = {"WinNow": 3, "Youth": 5, "Balanced": 4, "BigSpender": 5, "Frugal": 2}
STAR_RUNS = 0.05
D_IN, S_IN = 7, 8


def _dist():
    return np.load(os.path.join(HERE, "data", "dist2.npz"))


# ---------------- 드래프트 ----------------
def draft_sample(n, rng, R):
    i = rng.integers(len(R), size=n)
    age, ovr, gap, isP = R[i, 0], R[i, 1], R[i, 2], R[i, 3]
    names = list(PATIENCE); st = rng.integers(len(names), size=n)
    gamma = np.array([PATIENCE[names[k]] for k in st]); youth = np.array([YOUTH[names[k]] for k in st])
    need = np.where(rng.random(n) < 0.4, rng.integers(1, 3, size=n), 0).astype(float)
    sal = rng.uniform(30_000, 50_000, n)
    noise = rng.normal(0, 1.0, (n, H)).cumsum(1)
    obs_ovr = ovr + rng.normal(0, 1.5, n); obs_gap = gap + rng.normal(0, 2.0, n)
    return dict(age=age, ovr=ovr, gap=gap, isP=isP, gamma=gamma, youth=youth, need=need, sal=sal, noise=noise,
                obs_ovr=obs_ovr, obs_gap=obs_gap)


def draft_features(s):
    return np.column_stack([(s["obs_ovr"] - 72) / 5, s["obs_gap"] / 10 - 1.5, (s["age"] - 19) / 2, s["isP"],
                            s["need"] / 2, s["youth"] - 1.0, (s["gamma"] - 0.9) * 10])


def draft_returns(s):
    n = len(s["age"]); t = np.arange(1, H + 1)[None, :]
    o = proj_path(s["ovr"], s["age"], s["gap"], H)
    o = o + np.minimum(0.45 * t, np.maximum(0.0, s["gap"][:, None] - (o - s["ovr"][:, None]))) * (s["age"] <= 26)[:, None]
    o = o + s["noise"]
    need_cover = NEED_COVER * np.minimum(s["need"], 2)[:, None] * (t <= 3)
    value = farm_value(o) + need_cover
    cost = lambda sal: 0.10 * (sal - FARM_SALARY) / 50_000
    market = np.clip(s["sal"][:, None] * (1 + 0.04 * (o - s["ovr"][:, None])), 50_000, 125_000)
    tot = np.zeros(n)
    for k in range(1, H + 1):
        if k <= 3:
            u = np.maximum(value[:, k - 1] - cost(s["sal"]), -0.10 * 0.5 * s["sal"] / 50_000)
        else:
            u = np.maximum(0.0, value[:, k - 1] - cost(market[:, k - 1])) * (1 - LEAVE_P)
        tot += s["gamma"] ** (k - 1) * u
    return tot


# ---------------- 스태프 ----------------
def staff_sample(n, rng, S):
    i = rng.integers(len(S), size=n)
    stars, age, dem = S[i, 0], S[i, 1] + rng.integers(-3, 4, size=n), np.clip(S[i, 2], 60_000, 600_000)
    age = np.clip(age, 32, 66)
    names = list(PATIENCE); st = rng.integers(len(names), size=n)
    return dict(stars=stars, age=age, sal=dem * rng.uniform(0.9, 1.15, n),
                staff_w=np.array([STAFF_W[names[k]] for k in st]), maxy=np.array([MAX_YEARS[names[k]] for k in st], float),
                patience=np.array([PATIENCE[names[k]] for k in st]), noise=rng.normal(0, 0.15, (n, H)).cumsum(1),
                cap_frac=rng.uniform(0.3, 1.0, n))


def staff_features(s):
    return np.column_stack([(s["stars"] - 2.5) / 1.5, (s["age"] - 48) / 8, (s["sal"] - 250_000) / 150_000,
                            s["staff_w"] - 0.4, (s["maxy"] - 3) / 1.5, (s["patience"] - 0.9) * 10, s["cap_frac"],
                            (s["sal"] / np.maximum(1.0, s["stars"]) - 100_000) / 60_000])


def staff_returns(s):
    """(n, 6): 행동 0=계약 안 함(0), 1..5=계약 기간의 실현 보상"""
    n = len(s["age"]); t = np.arange(1, H + 1)[None, :]
    ages = s["age"][:, None] + t
    eff = np.maximum(0.0, s["stars"][:, None] - 0.25 * np.maximum(0, ages - 60) + s["noise"])
    ret = np.clip(0.06 * (ages - 60), 0, 0.6)
    alive = np.cumprod(1 - ret, axis=1)
    value = STAR_RUNS * eff
    cost = lambda sal: STAR_RUNS * s["staff_w"][:, None] * sal / 100_000
    af = np.clip(1.08 - 0.012 * np.abs(ages - 50), 0.8, 1.08) / np.clip(1.08 - 0.012 * np.abs(s["age"][:, None] - 50), 0.8, 1.08)
    market = np.clip(s["sal"][:, None] * af, 60_000, 700_000)
    out = np.zeros((n, 6))
    for y in range(1, 6):
        tot = np.zeros(n)
        for k in range(1, H + 1):
            if k <= y:
                u = (value[:, k - 1] - cost(s["sal"][:, None])[:, 0]) * alive[:, k - 1]
            else:
                u = np.maximum(0.0, value[:, k - 1] - cost(market[:, k - 1:k])[:, 0]) * alive[:, k - 1] * (1 - LEAVE_P)
            tot += s["patience"] ** (k - 1) * u
        out[:, y] = tot
    return out
