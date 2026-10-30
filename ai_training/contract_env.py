"""계약 연수·방출 정책 학습 환경 (맥락 밴딧).

행동: 0=방출(만료 시 재계약 안 함), 1..max_years=계약 기간. 2군 선수(farm)는 1군에서 뛰는 가치가 없고
(능력이 주전 수준 STARTER_OVR를 넘는 만큼만 득점 가치) 부상 대비 가치는 P_OUT × 벤치(BENCH_OVR)보다 나은 만큼이다.
상수는 모두 측정값이다(아래 주석).
계약이 남은 선수(rem>0)는 '방출'(데드머니 부담) 또는 '남은 기간 유지'(y=rem)만 고를 수 있다.


한 샘플 = 선수 한 명 + 구단 맥락. 정책은 계약 기간 y∈{1..max_years}를 고른다.
정책이 보는 것: 나이, OVR, 잠재력 여력, 계약 연봉, 부족 인원(need), 임금 여유, 구단 성향(sal_w, youth, max_years).
보상(점/경기, 5년 지평, 연 할인 0.9)은 정책이 모르는 '실현된 미래'로 계산한다:
  · OVR은 게임의 성장·노쇠 규칙(projected_ovr)에 해마다 무작위 오차가 더해진다.
  · 계약 중에는 연봉이 고정이다. 가치가 연봉보다 낮아져도 방출하면 남은 연봉의 DEAD_FRAC를 데드머니로 낸다.
  · 계약 후에는 시장가로 재계약하되(가치가 비용보다 클 때만), 재계약 때 선수를 잃을 확률 LEAVE_P가 있다.
따라서 '오르는 선수는 길게 묶고, 꺾이는 선수·비싼 선수는 짧게'가 규칙 없이 보상에서 나온다.
"""
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OVR_RUNS, REPL_OVR, REPL_SALARY = 0.03, 70.0, 60_000.0
NEED_RUNS = 0.0        # 측정: P_OUT(0.081) × (FA 최고 - 다른 포지션 벤치 대체 시 득실차 +0.59) = 0.048 (ai_team_manager.NEED_RUNS와 같다)
GAMMA = 0.9
H = 6                 # 평가 지평(년)
MAX_Y = 5
DEAD_FRAC = 0.5       # 계약 중 방출 시 남은 연봉 중 부담 비율 (ai_team_manager.DEAD_FRAC와 같다)
LEAVE_P = 0.15        # 재계약 협상에서 선수를 놓칠 확률
NOISE = 1.3           # 연 OVR 오차 표준편차
SHOCK_P, SHOCK = 0.04, 5.0   # 큰 부진·부상 후유증: 해마다 SHOCK_P(+나이 28세 초과분 연 1%p) 확률로 OVR이 SHOCK만큼 영구 하락
N_IN = 16
STARTER_OVR = 74.4     # 측정: AI 구단 야수 주전 평균 OVR (2군 선수가 주전 가치를 내기 시작하는 OVR)
BENCH_OVR = 68.9       # 측정: AI 구단 야수 벤치 평균 OVR (부상 대비 가치의 기준)
P_OUT = 0.0            # 측정: AI 1군 선수 중 부상 중인 비율 (엔진 1시즌)
FARM_SALARY = 50_000   # 2군 선수 연봉 비용의 기준(최저 연봉)
FARM_P = 0.35          # 샘플 중 2군 선수 비율
STYLES = {            # sal_w, youth, max_years (ai_team_manager.STYLES와 같은 값)
    "WinNow": (0.7, 0.3, 3), "Youth": (1.0, 1.6, 5), "Balanced": (1.0, 0.8, 4),
    "BigSpender": (0.5, 0.5, 5), "Frugal": (1.8, 0.8, 2),
}


def farm_value(o):
    """2군 선수가 OVR o일 때 연 가치(점/경기): 주전 수준을 넘는 만큼의 득점 + 부상 대비(벤치보다 나은 만큼 × 부상 확률)"""
    return OVR_RUNS * np.maximum(0.0, o - STARTER_OVR) + P_OUT * OVR_RUNS * np.maximum(0.0, np.minimum(o, STARTER_OVR) - BENCH_OVR)


def load_players():
    return np.load(os.path.join(HERE, "data", "player_dist.npz"))["X"]


def proj_path(ovr, age, gap, n):
    """projected_ovr(1..n)의 벡터판 (ovr, age, gap은 같은 길이 배열)"""
    ovr = ovr.copy(); age = age.copy(); left = np.maximum(0.0, gap)
    out = []
    for _ in range(n):
        g = np.where(age <= 32, 0.9, np.where(age <= 34, 0.45, np.where(age <= 36, 0.1, -0.1)))   # 실측한 연간 변화 (models/player.projected_ovr)
        g = np.where(g > 0, np.minimum(g, left), g)
        ovr = ovr + g; left = left - np.maximum(g, 0.0)
        age = age + 1
        out.append(ovr.copy())
    return np.stack(out, 1)


def age_pot_factor(age, gap):
    f = np.ones_like(age)
    f = np.where(age <= 25, f + np.minimum(0.25, 0.02 * gap), f)
    f = np.where(age >= 31, f - np.minimum(0.30, 0.03 * (age - 30)), f)
    return np.clip(f, 0.7, 1.3)


def sample(n, rng, P):
    """n개 샘플: 선수 특징 + 맥락 + 정책이 모르는 미래 오차"""
    farm = rng.random(n) < FARM_P
    low = np.nonzero(P[:, 1] <= 71)[0]
    i = np.where(farm, low[rng.integers(len(low), size=n)], rng.integers(len(P), size=n))
    rem = np.where(farm & (rng.random(n) < 0.5), rng.integers(1, 4, size=n), 0)
    age, ovr, gap, sal = P[i, 0], P[i, 1], P[i, 2], P[i, 3]
    names = list(STYLES)
    st = rng.integers(len(names), size=n)
    sal_w = np.array([STYLES[names[k]][0] for k in st]); youth = np.array([STYLES[names[k]][1] for k in st])
    maxy = np.array([STYLES[names[k]][2] for k in st])
    need = np.where(rng.random(n) < 0.25, rng.integers(1, 3, size=n), 0).astype(float)
    cap = 3.0e6 * rng.uniform(0.9, 1.15, n)
    room = cap * rng.uniform(0.03, 0.27, n)
    s0 = np.clip(sal * rng.uniform(0.9, 1.2, n), 50_000, 125_000)      # 이번 계약 연봉(재계약·FA 프리미엄 포함)
    noise = rng.normal(0, NOISE, (n, H)).cumsum(1)
    shock = (rng.random((n, H)) < (SHOCK_P + 0.01 * np.maximum(age - 28, 0))[:, None]) * SHOCK
    noise = noise - shock.cumsum(1)
    return dict(farm=farm.astype(float), rem=rem.astype(float), age=age, ovr=ovr, gap=gap, s0=s0, sal_w=sal_w, youth=youth, maxy=maxy.astype(float),
                need=need, room=room, noise=noise)


def features(s):
    path = proj_path(s["ovr"], s["age"], s["gap"], MAX_Y) - s["ovr"][:, None]
    return np.column_stack([
        (s["age"] - 27) / 5, (s["ovr"] - 72) / 6, s["gap"] / 10, path / 3,
        (s["s0"] - 85_000) / 25_000, s["need"] / 2, s["room"] / 5e5,
        s["sal_w"] - 1.0, s["youth"] - 1.0, (s["maxy"] - 3) / 1.5, s["farm"], s["rem"] / 3,
    ])


def returns(s):
    """각 샘플 × 행동(0=방출, 1..MAX_Y=계약기간)의 실현 보상 (n, MAX_Y+1). 불가능한 행동은 NaN"""
    n = len(s["age"])
    farm = s["farm"][:, None] > 0
    true_o = proj_path(s["ovr"], s["age"], s["gap"], H) + s["noise"]          # (n,H)
    boost = ((s["farm"] > 0) & (s["age"] <= 26))[:, None] * 0.45 * np.arange(1, H + 1)[None, :]   # 2군 육성: 젊은 2군 선수는 경험치 +50% (baseball.process_day)
    true_o = true_o + np.minimum(boost, np.maximum(0.0, s["gap"][:, None] - (true_o - s["ovr"][:, None])))
    ages = s["age"][:, None] + np.arange(1, H + 1)[None, :]
    f0 = age_pot_factor(s["age"], s["gap"])[:, None]
    f_t = age_pot_factor(ages, np.maximum(0.0, s["gap"][:, None] - 0.4 * np.arange(1, H + 1)[None, :]))
    market = np.clip(s["s0"][:, None] * (1 + 0.04 * (true_o - s["ovr"][:, None])) * f_t / f0, 50_000, 125_000)
    need = NEED_RUNS * np.minimum(s["need"], 2)[:, None]
    value = np.where(farm, farm_value(true_o),
                     OVR_RUNS * (true_o - REPL_OVR) + need)
    base = np.where(s["farm"] > 0, FARM_SALARY, REPL_SALARY)[:, None]
    cost = lambda sal: 0.10 * (sal - base) / 50_000 * s["sal_w"][:, None]
    rem = s["rem"].astype(int)
    out = np.full((n, MAX_Y + 1), np.nan)
    # 방출: 계약이 남았다면 남은 연봉의 DEAD_FRAC를 rem년간 부담
    dead_unit = 0.10 * DEAD_FRAC * s["s0"] / 50_000 * s["sal_w"]
    out[:, 0] = -np.array([sum(GAMMA ** k for k in range(r)) for r in rem]) * dead_unit
    for y in range(1, MAX_Y + 1):
        tot = np.zeros(n)
        for t in range(1, H + 1):
            disc = GAMMA ** (t - 1)
            stay = value[:, t - 1] - cost(s["s0"][:, None])[:, 0]
            dead = -0.10 * DEAD_FRAC * s["s0"] / 50_000 * s["sal_w"]
            u_in = np.maximum(stay, dead)                                         # 계약 중: 유지 또는 방출(데드머니)
            keep = value[:, t - 1] - cost(market[:, t - 1:t])[:, 0]
            u_out = np.maximum(0.0, keep) * (1 - LEAVE_P)                         # 계약 후: 시장가 재계약
            tot += disc * (u_in if t <= y else u_out)
        out[:, y] = tot
    mid = rem > 0
    ys = np.arange(MAX_Y + 1)[None, :]
    out[mid[:, None] & (ys != 0) & (ys != rem[:, None])] = np.nan                 # 계약 중에는 방출 또는 남은 기간 유지만
    return out
