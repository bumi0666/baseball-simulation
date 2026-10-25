"""투수 능력치가 타석 결과에 미치는 영향 측정 (같은 타자, 투수 능력치만 변경)."""
import os, random, sys, copy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_training.env import Env, GameScene
from simulation import FieldSim
RV = {"OUT": -0.27, "1B": 0.47, "2B": 0.77, "3B": 1.04, "HR": 1.40}

def probe(e, g, pitcher, batter, n=4000, seed=1):
    random.seed(seed)
    c = {"K": 0, "BB": 0, "OUT": 0, "1B": 0, "2B": 0, "3B": 0, "HR": 0}
    rv = 0.0
    ph, bh = dict(pitcher.status), dict(batter.status)
    for _ in range(n):
        pitcher.status.update(ph); batter.status.update(bh)
        g.strike = g.ball = 0
        while True:
            r = g.simulate_pitch(pitcher, batter)
            if r["type"] == "IN_PLAY":
                f = FieldSim([False] * 3, batted=r["batted"])
                for _ in range(900):
                    if f.is_over: break
                    f.update()
                res = f.get_result(); c[res] += 1; rv += RV[res]; break
            if g.strike >= 3: c["K"] += 1; rv += RV["OUT"]; break
            if g.ball >= 4: c["BB"] += 1; rv += 0.33; break
    return {k: round(100 * v / n, 1) for k, v in c.items()}, round(rv / n, 4)

if __name__ == "__main__":
    import statistics as st
    e = Env(); g = GameScene(e.up, e.state)
    batter = e.base_lineup["CF"]; pitcher = e.base_lineup["P"]
    allp = [q for q in e.players if "velocity" in q.attr]
    mean = {a: st.mean(q.attr[a]["cur"] for q in allp) for a in ("velocity", "control", "stuff", "stamina")}
    sd = {a: st.pstdev(q.attr[a]["cur"] for q in allp) for a in mean}
    print("리그 평균", {a: round(v) for a, v in mean.items()}, "sd", {a: round(v, 1) for a, v in sd.items()})
    def setp(**kw):
        for a in mean: pitcher.attr[a]["cur"] = kw.get(a, mean[a])
    setp(); print("평균 투수", *probe(e, g, pitcher, batter))
    for a in ("velocity", "control", "stuff"):
        for k in (-2, 2):
            setp(**{a: mean[a] + k * sd[a]})
            print(f"{a} {k:+d}sd ({mean[a] + k * sd[a]:.0f})", *probe(e, g, pitcher, batter))
