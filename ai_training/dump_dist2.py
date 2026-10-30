"""드래프트·스태프 학습용 분포 저장: 신인(나이, OVR, 잠재력 여력, 투수 여부)과 스태프(별, 나이, 연봉, 직책)"""
import os, sys, random
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pygame
pygame.init(); pygame.display.set_mode((1280, 720))
import baseball as B, draft
from models.player import Player
from saveload import default_save_data
state, players, staff, up, scenes = B.build_runtime(default_save_data())
rnd = random.Random(7); R = []
for i in range(2500):
    raw = draft._make_rookie("r%d" % i, rnd, 2024)
    p = Player(raw)
    R.append((p.age() or 20, p.calculate_ovr(), p.pot_gap(), p.pos == "P"))
R = np.array(R, dtype=float)
roles = ["HD", "HC", "PC", "DC", "SC", "DR"]
S = np.array([(s.stars, s.age() or 50, s.demand_salary(fa=False), roles.index(s.role)) for s in state.all_staff], dtype=float)
np.savez(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dist2.npz"), rookies=R, staff=S)
print("rookies", R.shape, R.mean(0).round(2), R.min(0).round(1), R.max(0).round(1))
print("staff", S.shape, S.mean(0).round(1), S.min(0), S.max(0))
