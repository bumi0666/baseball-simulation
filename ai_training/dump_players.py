"""계약 연수 학습용: 게임 선수들의 (나이, OVR, 잠재력 여력, 연봉) 분포를 저장한다."""
import os, sys
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pygame
pygame.init(); pygame.display.set_mode((1280, 720))
import baseball as B
from saveload import default_save_data
state, players, staff, up, scenes = B.build_runtime(default_save_data())
rows = [(p.age() or 27, p.calculate_ovr(), p.pot_gap(), p.salary() or p.base_salary(), p.pos == "P", p.status.get("roster", "active") == "inactive")
        for ps in state.team_rosters.values() for p in ps]
A = np.array(rows, dtype=float)
np.savez(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "player_dist.npz"), X=A)
print(A.shape, A.mean(0).round(2), A.min(0).round(1), A.max(0).round(1))
