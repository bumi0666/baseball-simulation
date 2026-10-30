"""AI 구단끼리의 경기를 사용자 경기와 같은 엔진(GameScene)으로 돌려 점수를 얻는다.
화면·인박스·시즌 기록은 건드리지 않는다(피로/부상은 baseball.apply_ai_game_fatigue가 따로 처리)."""
import random
from scenes.game_scene import GameScene, get_korean_font
from ui.game_fx import GameFX

POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")


def choose_lineup(roster, state, rest_fatigue, mode="learned"):
    """'learned': 학습한 가치 모델(ai_lineup), 모델이 없거나 'rule'이면 예전 규칙. 반환은 pick_lineup과 같다."""
    if mode == "learned":
        from ai_fatigue import AI_HITTER_FATIGUE, AI_PITCHER_FATIGUE
        r = __import__("ai_lineup").choose(
            roster, state,
            lambda p: AI_HITTER_FATIGUE * (1.6 if p.pos == "C" else 1.0),
            lambda p: AI_PITCHER_FATIGUE * (100 / max(30, getattr(p, "stamina", 100) or 100)))
        if r is not None:
            return r
    return pick_lineup(roster, rest_fatigue)


def pick_lineup(roster, rest_fatigue):
    """(규칙) 피로가 높지 않은 같은 포지션 선수를 우선 쓰고, 선발 투수는 상위 5명 중 가장 덜 지친 선수."""
    import ai_lineup
    hit0, pit0 = ai_lineup.pool(roster)
    act = hit0 + pit0 + [p for p in roster if p.status.get("roster", "active") == "active" and not p.status.get("is_injured") and p not in hit0 and p not in pit0]
    lineup, playing = {}, []
    for pos in POSITIONS:
        c = [p for p in act if p.pos == pos and p not in playing] or [p for p in act if p.pos != "P" and p not in playing]
        if not c:
            lineup[pos] = None
            continue
        c.sort(key=lambda p: -p.calculate_ovr())
        rested = [p for p in c if p.status.get("fatigue", 0) <= rest_fatigue]
        lineup[pos] = (rested or c)[0]
        playing.append(lineup[pos])
    pit = sorted((p for p in act if p.pos == "P"), key=lambda p: -p.calculate_ovr())
    rot = pit[:5]
    starter = min(rot, key=lambda p: p.status.get("fatigue", 0)) if rot else None
    lineup["P"] = starter
    if starter:
        playing.append(starter)
    order = sorted((p for p in lineup.values() if p and p.pos != "P"), key=lambda p: -p.calculate_ovr())[:9]
    bullpen = [p for p in pit if p is not starter]
    return lineup, order, bullpen, playing


class _Headless(GameScene):
    def end_game(self, result):
        """사용자 경기와 같은 방식으로 개인 기록(타격·투구·승패·세이브·홀드)을 시즌 기록에 쌓는다. 인박스·팀 순위·업적은 건드리지 않는다."""
        from datetime import date, timedelta
        y, m, d = self.state.base_date
        year = (date(y, m, d) + timedelta(days=self.state.current_day - 1)).year
        part = [p for p in self.my_order + self.my_removed + self.pitchers_used + self.opp_order + self.opp_removed + self.opp_pitchers_used if p]
        part = list(set(part))
        for p in part:                                 # 시즌 기록 항목이 없으면 소속 팀 이름으로 만든다
            if not any(c.get("season") == year for c in p.career):
                p.career.append({"season": year, "team": p.team, "stats": {
                    "g": 0, "ab": 0, "h": 0, "2b": 0, "3b": 0, "hr": 0, "rbi": 0, "bb": 0, "so": 0, "sb": 0,
                    "obp": 0.0, "slg": 0.0, "ops": 0.0, "w": 0, "l": 0, "era": 0.0, "ip_outs": 0, "ip": 0.0,
                    "h_allowed": 0, "bb_allowed": 0, "er": 0, "whip": 0.0}})
        self.apply_game_stats_to_players(with_fatigue=False)
        for p in part:
            if (p.game_stats["ab"] > 0) if not p.is_pitcher() else (p.game_stats["ip_outs"] > 0):
                p.add_game_log()
        self._award_pitching(result, self.my_lineup["P"], self.opp_lineup["P"])
        self.is_game_over = True
        self.game_result = result

    def my_replace_pitcher(self, role_flag):          # 사용자 불펜(state.bullpen) 대신 이 경기의 원정 팀 불펜
        saved = self.state.bullpen
        self.state.bullpen = self.my_bullpen
        try:
            GameScene.my_replace_pitcher(self, role_flag)
        finally:
            self.state.bullpen = saved


_fonts = {}


def _make_fx():
    if not _fonts:
        _fonts["f"] = (get_korean_font(20), get_korean_font(15), get_korean_font(64, bold=True))
    return GameFX(*_fonts["f"])


def bench_of(roster, playing):
    return [p for p in roster if p.pos != "P" and p.status.get("roster", "active") == "active"
            and not p.status.get("is_injured") and p not in playing]


def play(state, away, home, rest_fatigue, flags=(True, True), explore=None, detail=False, pmodes=("policy", "policy"), lmodes=("learned", "learned"), lineups=None):
    """away(초 공격)와 home(말 공격)을 엔진으로 경기시킨다. (away_score, home_score, away_playing, home_playing) 반환.
    선수 체력(health)과 game_stats는 경기 전 값으로 되돌린다."""
    ra, rb = state.team_rosters[away], state.team_rosters[home]
    if lineups:
        la, oa, ba, pa = lineups[0]; lb, ob, bb, pb = lineups[1]
    else:
        la, oa, ba, pa = choose_lineup(ra, state, rest_fatigue, lmodes[0])
        lb, ob, bb, pb = choose_lineup(rb, state, rest_fatigue, lmodes[1])
    if not la.get("P") or not lb.get("P") or len(oa) < 9 or len(ob) < 9:
        return None
    g = _Headless.__new__(_Headless)
    # 엔진의 my는 말 공격(홈), opp는 초 공격(원정) 쪽이다
    g.players, g.state, g.opponent_team = rb, state, away
    g.opp_lineup, g.opp_order, g.my_lineup, g.my_order = la, list(oa), dict(lb), list(ob)
    g.my_bullpen, g.opp_bullpen = bb, ba
    g.my_removed, g.opp_removed = [], []
    g.t_in, g.t_out = {}, {}
    g.my_bench, g.opp_bench = bench_of(rb, pb), bench_of(ra, pa)
    g.sub_flags = {"my": bool(flags[1]), "opp": bool(flags[0])}       # flags = (원정, 홈)
    g.sub_explore = explore
    g.headless = True
    g.pitch_mode = {"my": pmodes[1], "opp": pmodes[0]}      # (원정, 홈)
    g.inning, g.half, g.strike, g.ball, g.out = 1, "TOP", 0, 0, 0
    g.my_score = g.opp_score = g.my_bat_idx = g.opp_bat_idx = g.my_hit = g.opp_hit = 0
    g.bases, g.last_event = [None, None, None], ""
    g.my_inning_runs, g.opp_inning_runs = [0] * 12, [0] * 12
    g.is_game_over, g.game_result = False, None
    g.pitchers_used, g.opp_pitchers_used = [lb["P"]], [la["P"]]
    g.starter, g.finisher, g.oppstarter, g.oppfinisher = lb["P"], None, la["P"], None
    g.win_candidates, g.winning_pitcher, g.losing_pitcher = {"my": None, "opp": None}, None, None
    g.pitch_sim = g.field_sim = g._pending_result = g._pending_batter = g._pending_pitcher = g._pending_my_team = None
    g._pending_walk = False
    g._fielder_display, g._ball_trail = {}, []
    g.fx = _make_fx()
    part = oa + ob + [la["P"], lb["P"]] + ba + bb + g.my_bench + g.opp_bench
    saved = [(p, p.status.get("health", 1000)) for p in part]
    g.pitch_f0 = {p: p.status.get("fatigue", 0) for p in ra + rb if p.pos == "P"}      # 경기 시작 시 투수 피로 (피로 비용 계산용)
    for p in part:
        p.reset_game_stats()
        p.game_stats = {"ab": 0, "h": 0, "2b": 0, "3b": 0, "hr": 0, "rbi": 0, "bb": 0, "so": 0, "sb": 0,
                        "ip_outs": 0, "h_allowed": 0, "r_allowed": 0, "er": 0, "so_p": 0, "bb_p": 0,
                        "is_win": False, "is_loss": False, "is_save": False, "is_hold": False,
                        "entry_score_diff": 0, "entry_runners": 0, "quit_score_diff": 0}
    try:
        g.simulate_to_end()
        pw = {p: min(1.0, p.game_stats.get("ip_outs", 0) / 18) for p in g.pitchers_used + g.opp_pitchers_used}   # 투수는 던진 이닝만큼(6이닝=선발 한 번)
        g.pitch_w = pw
    finally:
        for p, h in saved:
            p.status["health"] = h
            p.reset_game_stats()
    def _w(p): return max(0.0, g.t_out.get(p, 1.0) - g.t_in.get(p, 0.0))
    away_played = {p: _w(p) for p in pa + [q for q in g.opp_order if q not in pa]}      # 선수 -> 출전 비율 (교체 선수 포함)
    home_played = {p: _w(p) for p in pb + [q for q in g.my_order if q not in pb]}
    for p in g.opp_pitchers_used: away_played[p] = pw[p]                                  # 투수: 던진 비율 (구원 투수 포함)
    for p in g.pitchers_used: home_played[p] = pw[p]
    if detail:
        return g.opp_score, g.my_score, away_played, home_played, g
    return g.opp_score, g.my_score, away_played, home_played
