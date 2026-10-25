"""학습용 환경: 게임 엔진(GameScene.simulate_to_end)으로 '선수 교체 효과'를 측정한다.

선수 한 명을 라인업 슬롯에 넣었을 때, 동일한 난수 시드로 돌린 기준 경기들 대비
경기당 득실차(run differential) 변화를 라벨로 삼는다.
"""
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pygame
pygame.init()
pygame.display.set_mode((1280, 720))

import baseball as B
from saveload import load_game
from scenes.game_scene import GameScene

ATTRS = ["contact", "power", "eye", "run", "defense", "velocity", "control", "stamina", "stuff"]
SLOTS = ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]


def _light_end_game(self, result):
    """학습용: 통계·메일 등 부작용 없이 종료만 표시"""
    self.game_result = {"result": result}
    self.is_game_over = True


GameScene.end_game = _light_end_game


class Env:
    def __init__(self, slot=1):
        self.state, self.players, _, self.up, _ = B.build_runtime(load_game(slot=slot))
        self.fa = self.state.team_rosters["FA"]
        self.teams = [t for t, v in self.state.team_rosters.items()
                      if t not in ("FA", self.state.user_team) and len(v) >= 20]
        self.base_lineup = dict(self.state.lineup)
        self.base_order = list(self.state.batting_order)
        self._status = [(p, dict(p.status)) for p in self.players]   # 상태값은 전부 스칼라
        self._date = self.state.get_current_date_str()

    def _restore(self):
        for p, snap in self._status:
            p.status.update(snap)

    def run_diff(self, lineup, order, opp, n, seed):
        """경기당 득실차 평균과 승률 (같은 seed → 같은 난수열)"""
        self.state.schedule[self._date]["opponent"] = opp
        diff = wins = 0
        for i in range(n):
            self._restore()
            # 게임 안의 투수 교체가 라인업 dict를 직접 바꾸므로 매 경기 복사본을 쓴다
            self.state.lineup = dict(lineup)
            self.state.batting_order = list(order)
            random.seed(seed * 100003 + i)
            g = GameScene(self.up, self.state)
            g.simulate_to_end()
            diff += g.my_score - g.opp_score
            wins += g.my_score > g.opp_score
        return diff / n, wins / n

    def swapped(self, slot, cand):
        """slot 포지션 선수를 cand로 교체한 (라인업, 타순)"""
        lineup = dict(self.base_lineup)
        old = lineup[slot]
        lineup[slot] = cand
        order = [cand if p is old else p for p in self.base_order]
        return lineup, order, old


def attr_vec(p):
    return [p.attr[a]["cur"] if a in p.attr else 0 for a in ATTRS]
