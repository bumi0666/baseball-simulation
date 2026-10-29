"""리그 평균 기록 측정: 경기 N회를 돌려 팀당 경기 평균 H/2B/3B/HR/K/BB/R 출력."""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_training.env import Env, GameScene

def probe(e, n=300, seed0=0):
    tot = dict(h=0, d=0, t=0, hr=0, k=0, bb=0, r=0, ab=0)
    for i in range(n):
        e._restore(); e.state.lineup = dict(e.base_lineup); e.state.batting_order = list(e.base_order)
        e.state.schedule[e._date]["opponent"] = e.teams[i % len(e.teams)]
        random.seed(seed0 + i)
        g = GameScene(e.up, e.state); g.simulate_to_end()
        for p in g.my_order + g.opp_order:
            s = p.game_stats
            tot["h"] += s["h"]; tot["d"] += s["2b"]; tot["t"] += s["3b"]; tot["hr"] += s["hr"]
            tot["k"] += s["so"]; tot["bb"] += s["bb"]; tot["ab"] += s["ab"]
        tot["r"] += g.my_score + g.opp_score
    per = {k: round(v / n / 2, 2) for k, v in tot.items()}      # 팀당 경기 평균
    h = max(1, tot["h"])
    per["2B/H%"] = round(100 * tot["d"] / h, 1); per["3B/H%"] = round(100 * tot["t"] / h, 1)
    per["HR/H%"] = round(100 * tot["hr"] / h, 1)
    return per

if __name__ == "__main__":
    e = Env()
    print(probe(e, int(sys.argv[1]) if len(sys.argv) > 1 else 300))
