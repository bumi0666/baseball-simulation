import pygame
import sys, random
from pygame.locals import *
import json, os
from datetime import date

from config import *
from ui.button import Button
from models.player import Player
from models.staff import Staff

from scenes.title_scene import TitleScene
from scenes.hub_scene import HubScene
from scenes.team_scene import TeamScene
from scenes.player_detail_scene import PlayerDetailScene
from scenes.staff_detail_scene import StaffDetailScene
from scenes.option_scene import OptionScene
from scenes.inbox_scene import InboxScene
from scenes.finance_scene import FinanceScene
from scenes.schedule_scene import ScheduleScene
from scenes.medical_scene import MedicalScene
from scenes.training_scene import TrainingScene
from scenes.squad_scene import SquadScene
from scenes.staff_scene import StaffScene
from scenes.lineup_scene import LineupScene
from scenes.game_scene import GameScene
from scenes.result_scene import ResultScene
from scenes.teamdetail_scene import TeamDetailScene
from scenes.reserve_scene import ReserveScene
from scenes.transfer_scene import TransferScene
from scenes.transactions_scene import TransactionsScene
from scenes.draft_scene import DraftScene
import draft as draft_module
from saveload import default_save_data, load_game, save_game
from datetime import date, timedelta

pygame.init()
pygame.font.init()
FONT=pygame.font.SysFont(None, 36)
BIGFONT=pygame.font.SysFont(None, 50)


pygame.display.set_caption('baseball simulator demo')
screen=pygame.display.set_mode((width, height))

#ASSET_PATH = os.path.join(os.path.dirname(__file__), "assets")
ASSET_PATH = resource_path("assets")
icons = pygame.image.load(os.path.join(ASSET_PATH, "icon.png")).convert_alpha()

pygame.display.set_icon(icons)

MUSIC_ENDED = pygame.USEREVENT + 1
pygame.mixer.music.set_endevent(MUSIC_ENDED)

playlist = [
    os.path.join(ASSET_PATH, "bensound-happyrock.mp3"),
    os.path.join(ASSET_PATH, "bensound-elevate.mp3"),
    os.path.join(ASSET_PATH, "bensound-energy.mp3")
]
current_track_index = 0

def play_next_track():
    global current_track_index
    # 다음 곡으로 넘어가되, 마지막 곡이면 다시 처음으로
    current_track_index = (current_track_index + 1) % len(playlist)
    pygame.mixer.music.load(playlist[current_track_index])
    pygame.mixer.music.play() # 한 번만 재생 (어차피 끝나면 이벤트가 발생함)

current_bgm = None

def change_bgm(path, loop=-1): # loop 인자 추가
    global current_bgm 
    if current_bgm != path:
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(path)
            pygame.mixer.music.play(loop) # 지정된 루프 횟수로 재생
            current_bgm = path
        except Exception as e:
            print(f"BGM 로드 실패: {e}")

class GameState:
    def __init__(self, data):
        
        self.fade_alpha = 0          # 현재 투명도 (0~255)
        self.is_fading = False       # 페이드 효과 진행 중 여부
        self.fade_direction = 1      # 1이면 어두워짐(In), -1이면 밝아짐(Out)
        
        self.user_team = data.get("user_team", "Lions")
        self.active_save_slot = data.get("active_save_slot", 1)
        self.team_data = data.get("team_data", {})
        
        self.match_history = data.get("match_history", {
            t: [] for t in ["Lions", "Tigers", "Bears", "Wiz", "Eagles", "Twins", "Landers", "Dinos", "Heroes", "Giants"]
        })
        #self.team = data.get("team")
        self.team_rosters = {}
        
        self.current_day = data.get("current_day", 1)
        self.base_date = data.get("base_date", (2024, 1, 1))
        self.inbox = data.get("inbox", [])
        self.transactions = data.get("transactions", [])   # 다른 구단의 영입/방출/재계약 기록
        self.team_profiles = data.get("team_profiles", {})  # AI 구단별 재정(임금 상한)·성향
        self.draft = data.get("draft")                      # 신인 드래프트 진행 상태
        self.season_history = data.get("season_history", [])  # 지난 시즌 우승팀·최종 순위
        self.season_ended_year = data.get("season_ended_year")  # 시즌 종료를 처음 확인한 연도(다음 시즌 개막 판정용)
        
        self.money = data.get("money", 5000000)
        #self.money = 5000000
        self.stadium_cap = data.get("stadium_cap", 30000) # 경기장 수용 인원
        self.ticket_price = data.get("ticket_price", 40)  # 티켓 가격
        
        self.popularity = data.get("popularity", 50) # 인지도
        self.prevscene = data.get("prevscene", "") # 이전 scene
        
        # 상세 내역 기록 (이번 달 기준)
        self.monthly_income = data.get("monthly_income", {"Tickets": 0, "Player sell": 0, "Sponsor": 0, "TV rights": 0, "Merchandise": 0})
        self.monthly_expense = data.get("monthly_expense", {"Wages": 0, "Player buy": 0, "Facility": 0, "Management": 0, "Tax" : 0})
        
        self.transfer_budget = data.get("transfer_budget", 1000000)
        self.wage_budget = data.get("wage_budget", 3000000)
        self.current_wage = data.get("current_wage", 150000)
        
        # 월별 손익 기록 (최근 5~6개월치 그래프용)
        self.profit_history = data.get("profit_history", [0, 0, 0, 0, 0])
        
        self.finance_history = data.get("finance_history", [self.money])
        #self.schedule = data.get("schedule", {}) # {"05/10": "HOME"} 형식
        
        self.schedule = data.get("schedule", {})
        self.master_schedule = data.get("master_schedule", {})
        self.postseason = data.get("postseason", {})
        self.champion = data.get("champion")
        self.regular_season_ended = data.get("regular_season_ended", False)
        self.season_ended = data.get("season_ended", False)
        self.opponents = ["Tigers", "Bears", "Wizards", "Eagles", "Twins", "Landers", "Dinos", "Heroes", "Giants"]
        
        self.lineup = {
            "P": None, "C": None, "1B": None, "2B": None, 
            "3B": None, "SS": None, "LF": None, "CF": None, "RF": None, "DH": None
        }
        self.batting_order = [None] * 9     
        self.bullpen = [None] * 8
        self.saved_lineup_ids = data.get("lineup_ids", {})
        self.saved_batting_order_ids = data.get("batting_order_ids", [])
        self.saved_bullpen_ids = data.get("bullpen_ids", [])
        self.saved_staff_slot_ids = data.get("staff_slot_ids", {})
        
        self.staff_slots = {
        #"HD": Staff("kim head", "HD", 3, "전체 능력치 소폭 상승"),
        #"HC": Staff("lee hit", "HC", 4, "안타 확률 증가"),
        #"PC": Staff("park pitch", "PC", 3, "선발 투수 스테미너 보정"),
        #"BC": Staff("choi bullpen", "BC", 2, "불펜 투수 구위 상승"),
        #"DC": Staff("jung defense", "DC", 3, "실책 확률 감소")
        }
        self.team_stats = data.get("team_stats", {
            "Tigers":  {"win": 0,  "loss": 0, "draw": 0, "games": 0},
            "Wizards": {"win": 0, "loss": 0, "draw": 0, "games": 0},
            "Eagles": {"win": 0, "loss": 0, "draw": 0,  "games": 0},
            "Twins": {"win": 0, "loss": 0, "draw": 0,  "games": 0},
            "Landers": {"win": 0, "loss": 0, "draw": 0,  "games": 0},
            "Heroes": {"win": 0, "loss": 0, "draw": 0,  "games": 0},
            "Dinos": {"win": 0, "loss": 0, "draw": 0,  "games": 0},
            "Lions":   {"win": 0,  "loss": 0, "draw": 0,  "games": 0},
            "Bears":   {"win": 0,  "loss": 0, "draw": 0,  "games": 0},
            "Giants": {"win": 0,  "loss": 0, "draw": 0,  "games": 0}
        })
        
        self.todaygamenotice = data.get("todaygamenotice", False)
        self.todaygamedone = data.get("todaygamedone", False)
        
        self.salary_paid_this_month = data.get("salary_paid_this_month", False)
        
        #self.status = data.get("status", {})
        # 아래 줄 추가 (기존 데이터가 있으면 가져오고, 없으면 빈 사전 생성)
        #self.stats = data.get("stats", {"hits": 0, "at_bats": 0, "wins": 0, "losses": 0, "era_runs": 0, "era_innings": 0})

    def add_money(self, amount):
        self.money += amount
    
        # 그래프 즉시 반영
        if self.finance_history:
            self.finance_history[-1] = self.money
        else:
            self.finance_history.append(self.money)
        
    def get(self, key, default=None):
        # 기존 dict.get() 코드가 깨지지 않게 호환성 유지
        return getattr(self, key, default)
    
    def get_current_date_str(self):
        y, m, d = self.base_date
        curr = date(y, m, d) + timedelta(days=self.current_day - 1)
        return curr.strftime("%m/%d")
    
    def record_match_result(self, winner, loser, is_draw=False):
        if is_draw:
            self.team_stats[winner]["draw"] += 1
            self.team_stats[loser]["draw"] += 1
        else:
            self.team_stats[winner]["win"] += 1
            self.team_stats[loser]["loss"] += 1
    
        self.team_stats[winner]["games"] += 1
        self.team_stats[loser]["games"] += 1

def load_team_data():
    path = resource_path("teams.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

import random

LEAGUE_TEAMS = ["Lions", "Tigers", "Bears", "Wizards", "Eagles",
                "Twins", "Landers", "Dinos", "Heroes", "Giants"]

def generate_round_robin_rounds(teams):
    rounds = []
    rotating = teams[:]
    team_count = len(rotating)

    for round_idx in range(team_count - 1):
        matches = []
        for i in range(team_count // 2):
            team_a = rotating[i]
            team_b = rotating[team_count - 1 - i]
            if round_idx % 2 == 0:
                matches.append((team_a, team_b))
            else:
                matches.append((team_b, team_a))
        rounds.append(matches)
        rotating = [rotating[0]] + [rotating[-1]] + rotating[1:-1]

    return rounds

def get_next_play_date(current_date):
    current_date += timedelta(days=1)
    while current_date.weekday() == 0:
        current_date += timedelta(days=1)
    return current_date

def get_next_series_start(current_date):
    current_date += timedelta(days=1)
    while current_date.weekday() not in (1, 4):
        current_date += timedelta(days=1)
    return current_date

def add_rest_days_between(state, start_date, end_date):
    rest_date = start_date + timedelta(days=1)
    while rest_date < end_date:
        if rest_date.weekday() == 0:
            date_str = rest_date.strftime("%m/%d")
            state.schedule.setdefault(date_str, {
                "opponent": None,
                "type": "REST",
                "played": True,
                "stage": "rest"
            })
        rest_date += timedelta(days=1)

def add_user_schedule_entry(state, date_str, day_matches, stage="regular", series_info=None):
    my_match = next((m for m in day_matches if state.user_team in m), None)
    if not my_match:
        return

    home_team, away_team = my_match
    opponent = away_team if home_team == state.user_team else home_team
    game_type = "HOME" if home_team == state.user_team else "AWAY"

    entry = {
        "opponent": opponent,
        "type": game_type,
        "played": False,
        "stage": stage
    }
    if series_info:
        entry.update(series_info)

    state.schedule[date_str] = entry

KBO_OPENING_ANCHOR = (3, 21)    # 개막일은 3월 21일 다음의 첫 화/금요일 시리즈 (KBO는 3월 하순 개막)


def generate_season_schedule(state, games_per_pair=16, season_year=None):
    """season_year 시즌의 정규시즌 일정을 만든다. 3월 하순 개막(KBO 기준)이며, 144경기가 9월 말까지 이어진다.
    season_year가 없으면 게임 시작 연도의 시즌을 만든다(시작일이 개막 이후면 시작일부터)."""
    teams = LEAGUE_TEAMS[:]
    base_y, base_m, base_d = state.base_date
    anchor_year = season_year if season_year is not None else base_y
    if season_year is None and date(base_y, base_m, base_d) > date(base_y, *KBO_OPENING_ANCHOR):
        anchor_year = base_y + 1                  # 개막일을 넘겨 시작하면(예: 11월) 다음 해 시즌을 연다
    current_date = date(anchor_year, *KBO_OPENING_ANCHOR)

    state.master_schedule = {}
    state.schedule = {}
    state.postseason = {}

    base_rounds = generate_round_robin_rounds(teams)
    series_lengths = [3, 3, 3, 3, 2, 2]
    if sum(series_lengths) != games_per_pair:
        raise ValueError("series_lengths must add up to games_per_pair")

    series_no = 1
    last_scheduled_date = current_date

    for cycle, series_len in enumerate(series_lengths):
        rounds = base_rounds[:]

        for round_idx, round_matches in enumerate(rounds):
            day_matches = [(away, home) for home, away in round_matches] if cycle % 2 else round_matches[:]
            series_start = get_next_series_start(current_date)
            add_rest_days_between(state, last_scheduled_date, series_start)

            for game_idx in range(series_len):
                current_date = series_start + timedelta(days=game_idx)
                date_str = current_date.strftime("%m/%d")
                series_info = {
                    "series_id": series_no,
                    "series_game": game_idx + 1,
                    "series_len": series_len,
                    "cycle": cycle + 1
                }

                state.master_schedule[date_str] = {
                    "matches": day_matches,
                    "processed": False,
                    "stage": "regular",
                    **series_info
                }
                add_user_schedule_entry(state, date_str, day_matches, "regular", series_info)

            last_scheduled_date = current_date
            series_no += 1
            
# MatchScene에서 경기 종료 시 호출
def apply_daily_results(self):
    date_str = self.state.get_current_date_str()
    today_matches = self.state.master_schedule[date_str]["matches"]
    
    for team_a, team_b in today_matches:
        if team_a == self.state.user_team or team_b == self.state.user_team:
            # 사용자의 경기는 실제 점수로 계산
            winner = self.state.user_team if self.user_score > self.opp_score else self.opponent_team_name
            loser = self.opponent_team_name if winner == self.state.user_team else self.state.user_team
        else:
            # 다른 팀들의 경기는 확률(시뮬레이션)로 계산
            winner, loser = (team_a, team_b) if random.random() > 0.5 else (team_b, team_a)
        
        # 실제 데이터 업데이트
        self.state.record_match_result(winner, loser)


def load_players():
    players_dict = {}
    players_path = os.path.join(resource_path("players"), "players.json")

    if not os.path.exists(players_path):
        return {}

    try:
        with open(players_path, encoding="utf-8") as f:
            data = json.load(f)

        for player in data.get("players", []):
            players_dict[player["id"]] = player

    except (json.JSONDecodeError, KeyError, TypeError):
        print("파일 로드 실패: players.json")
        return {}

    return players_dict

def load_staff():
    staff_dict = {}
    staff_path = os.path.join(resource_path("staff"), "staff.json")

    if not os.path.exists(staff_path):
        return {}

    try:
        with open(staff_path, encoding="utf-8") as f:
            data = json.load(f)

        for staff in data.get("staff", []):
            staff_dict[staff["id"]] = staff

    except (json.JSONDecodeError, KeyError, TypeError):
        print("파일 로드 실패: staff.json")
        return {}

    return staff_dict

def save_player(player_obj):
    
    if hasattr(player_obj, 'raw_data'): # Player 객체인 경우
        p_data = player_obj.raw_data 
    else:
        p_data = player_obj

    p_id = p_data.get("id")
    p_name = p_data.get("name")
    
    filename = f"{p_id}_{p_name}.json"
    path = os.path.join("players", filename)
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(p_data, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: {filename}")
    
def _blank_season_entry(team):
    """선수 시즌 기록 항목 (game_scene이 읽는 'stats' 구조 포함). 신인처럼 career가 비어 있을 때 만든다."""
    from models import player as _pm
    year = (_pm._GAME_DATE or date.today()).year
    return {"season": year, "team": team, "ab": 0, "h": 0, "wins": 0, "losses": 0,
            "stats": {"g": 0, "ab": 0, "h": 0, "2b": 0, "3b": 0, "hr": 0, "rbi": 0, "bb": 0, "so": 0, "sb": 0,
                      "obp": 0.0, "slg": 0.0, "ops": 0.0, "w": 0, "l": 0, "era": 0.0, "ip_outs": 0, "ip": 0.0,
                      "h_allowed": 0, "bb_allowed": 0, "er": 0, "whip": 0.0}}


from ai_fatigue import AI_REST_FATIGUE, AI_HITTER_FATIGUE, AI_PITCHER_FATIGUE


def apply_ai_game_fatigue(roster, playing_given=None):
    """AI 구단의 경기 1회: 라인업(포지션별 야수 + 선발 투수)에 피로가 쌓이고, 200을 넘으면 유저 선수와 같은 식으로 부상을 입는다.
    피로가 높은 주전은 같은 포지션 벤치로 쉬게 하고, 벤치 선수는 피로가 회복된다."""
    import random
    act = [p for p in roster if p.status.get("roster", "active") == "active" and not p.status.get("is_injured")]
    if playing_given is not None:
        playing = playing_given          # 엔진 경기에 실제로 나선 선수들
    else:
        import ai_match
        playing = ai_match.choose_lineup(roster, None, AI_REST_FATIGUE)[3]
    for p in playing:
        w = playing[p] if isinstance(playing, dict) else 1.0        # 교체로 일부만 뛴 선수는 출전 비율만큼만 피로·부상을 받는다 (나머지는 벤치처럼 회복)
        inc = AI_PITCHER_FATIGUE * (100 / max(30, getattr(p, "stamina", 100) or 100)) if p.pos == "P" else (AI_HITTER_FATIGUE * 1.6 if p.pos == "C" else AI_HITTER_FATIGUE)
        p.status["fatigue"] = max(0, p.status.get("fatigue", 0) + w * (inc - 10) - (1 - w) * 30)
        if p.status["fatigue"] > 200:
            chance = min(0.5, ((p.status["fatigue"] - 200) ** 2) / 40000 + 0.05) * w
            if random.random() < chance:
                p.status["is_injured"] = True
                p.status["injury_days"] = random.randint(3, 30)
    for p in act:
        if p not in playing:
            p.status["fatigue"] = max(0, p.status.get("fatigue", 0) - 30)      # 벤치: 경기당 회복 (유저 벤치와 같다)


def simulate_ai_player_stats(winning_roster, losing_roster, win_playing=None, lose_playing=None):
    """AI 팀들간의 경기 후처리. 엔진으로 치른 경기(win_playing이 있음)는 개인 기록이 이미 엔진에서 쌓였으므로 피로·부상만 처리한다.
    엔진을 못 쓴 예외 경기만 간이 확률로 기록한다."""
    if not winning_roster or not losing_roster: return
    apply_ai_game_fatigue(winning_roster, win_playing)
    apply_ai_game_fatigue(losing_roster, lose_playing)
    if win_playing is not None:
        return

    for p in winning_roster + losing_roster:
        # 1. 이번 시즌 기록 주머니(dict) 가져오기
        # 만약 career가 비어있다면 하나 생성
        if not p.career:
            p.career.append(_blank_season_entry(p.team))
        
        season_stat = p.career[-1] # 가장 최근 시즌 기록

        # 2. 타자 기록 업데이트
        if p.pos != "P":
            at_bats = 4
            hits = 0
            hit_chance = (p.calculate_ovr() / 400) + 0.1
            for _ in range(at_bats):
                if random.random() < hit_chance:
                    hits += 1
            
            # career 내의 키값(ab, h 등)에 맞게 누적
            season_stat["ab"] = season_stat.get("ab", 0) + at_bats
            season_stat["h"] = season_stat.get("h", 0) + hits

    # 3. 투수 승패 업데이트
    win_pitchers = [p for p in winning_roster if p.pos == "P"]
    loss_pitchers = [p for p in losing_roster if p.pos == "P"]

    if win_pitchers:
        wp = random.choice(win_pitchers)
        if not wp.career: wp.career.append(_blank_season_entry(wp.team))
        wp.career[-1]["wins"] = wp.career[-1].get("wins", 0) + 1

    if loss_pitchers:
        lp = random.choice(loss_pitchers)
        if not lp.career: lp.career.append(_blank_season_entry(lp.team))
        lp.career[-1]["losses"] = lp.career[-1].get("losses", 0) + 1

import random

tutorial = 0
#day1 = 0

def get_regular_standings(state):
    return sorted(
        state.team_stats.items(),
        key=lambda x: (
            x[1]["win"] / max(x[1]["win"] + x[1]["loss"], 1),
            x[1]["win"],
            -x[1]["loss"]
        ),
        reverse=True
    )

def get_team_win_probability(state, team_a, team_b):
    stats_a = state.team_stats.get(team_a, {})
    stats_b = state.team_stats.get(team_b, {})
    pct_a = stats_a.get("win", 0) / max(stats_a.get("win", 0) + stats_a.get("loss", 0), 1)
    pct_b = stats_b.get("win", 0) / max(stats_b.get("win", 0) + stats_b.get("loss", 0), 1)
    return max(0.35, min(0.65, 0.5 + (pct_a - pct_b) * 0.7))

def simulate_postseason_game(state, team_a, team_b):
    prob_a = get_team_win_probability(state, team_a, team_b)
    winner = team_a if random.random() < prob_a else team_b
    loser = team_b if winner == team_a else team_a
    winner_score = random.randint(2, 9)
    loser_score = random.randint(0, winner_score - 1)
    return winner, loser, winner_score, loser_score

def simulate_series(state, stage, team_a, team_b, wins_needed, initial_wins=None):
    wins = {team_a: 0, team_b: 0}
    if initial_wins:
        wins.update(initial_wins)

    lines = [f"=== {stage}: {team_a} vs {team_b} ==="]
    if initial_wins:
        lines.append(f"Starting series: {team_a} {wins[team_a]} - {wins[team_b]} {team_b}")

    game_no = 1
    while wins[team_a] < wins_needed and wins[team_b] < wins_needed:
        winner, loser, w_score, l_score = simulate_postseason_game(state, team_a, team_b)
        wins[winner] += 1
        lines.append(f"G{game_no}: {winner} {w_score} - {l_score} {loser}  ({wins[team_a]}-{wins[team_b]})")
        game_no += 1

    series_winner = team_a if wins[team_a] >= wins_needed else team_b
    lines.append(f"Winner: {series_winner}\n")
    return series_winner, lines

def simulate_kbo_postseason(state, standings):
    seeds = [team for team, _ in standings[:5]]
    if len(seeds) < 5:
        return "Not enough teams for postseason."

    first, second, third, fourth, fifth = seeds
    report = ["=== KBO STYLE POSTSEASON ===", ""]
    report.append("Seeds:")
    for idx, team in enumerate(seeds, 1):
        report.append(f"{idx}. {team}")
    report.append("")

    wc_winner, lines = simulate_series(
        state, "Wild Card", fourth, fifth, 2,
        initial_wins={fourth: 1, fifth: 0}
    )
    report.extend(lines)

    semi_winner, lines = simulate_series(state, "Semi-Playoff", third, wc_winner, 3)
    report.extend(lines)

    playoff_winner, lines = simulate_series(state, "Playoff", second, semi_winner, 3)
    report.extend(lines)

    champion, lines = simulate_series(state, "Korean Series", first, playoff_winner, 4)
    report.extend(lines)

    state.champion = champion
    state.postseason = {
        "seeds": seeds,
        "wild_card_winner": wc_winner,
        "semi_playoff_winner": semi_winner,
        "playoff_winner": playoff_winner,
        "champion": champion
    }
    report.append(f"CHAMPION: {champion}")
    return "\n".join(report)

def get_next_postseason_date(state, from_date_str):
    base_y, base_m, base_d = state.base_date
    month, day = map(int, from_date_str.split("/"))
    cur_year = (date(base_y, base_m, base_d) + timedelta(days=state.current_day - 1)).year   # 시즌이 진행 중인 해
    current = date(cur_year, month, day)

    while True:
        current += timedelta(days=1)
        if current.weekday() == 0:
            continue
        date_str = current.strftime("%m/%d")
        if date_str not in state.master_schedule:
            return date_str

def has_pending_postseason_game(state):
    for date_str, game in state.schedule.items():
        if game.get("stage") == "postseason" and not game.get("played", False):
            return True

    for day_data in state.master_schedule.values():
        if day_data.get("stage") == "postseason" and not day_data.get("processed", False):
            return True

    return False

def set_current_postseason_series(state, stage, team_a, team_b, wins_needed, initial_wins=None):
    wins = {team_a: 0, team_b: 0}
    if initial_wins:
        wins.update(initial_wins)

    state.postseason["current_series"] = {
        "stage": stage,
        "teams": [team_a, team_b],
        "wins_needed": wins_needed,
        "wins": wins,
        "game_no": 1,
        "results": [],
        "winner": None
    }

def schedule_current_postseason_game(state, from_date_str):
    if has_pending_postseason_game(state):
        return None

    ps = getattr(state, "postseason", {})
    series = ps.get("current_series")
    if not ps.get("active") or ps.get("completed") or not series or series.get("winner"):
        return None

    date_str = get_next_postseason_date(state, from_date_str)
    home_team, away_team = series["teams"]
    if series["game_no"] % 2 == 0:
        home_team, away_team = away_team, home_team

    state.master_schedule[date_str] = {
        "matches": [(home_team, away_team)],
        "processed": False,
        "stage": "postseason",
        "series": series["stage"]
    }

    if state.user_team in (home_team, away_team):
        opponent = away_team if home_team == state.user_team else home_team
        state.schedule[date_str] = {
            "opponent": opponent,
            "type": "HOME" if home_team == state.user_team else "AWAY",
            "played": False,
            "stage": "postseason",
            "series": series["stage"]
        }

    return date_str

def start_kbo_postseason(state, standings, date_str):
    seeds = [team for team, _ in standings[:5]]
    if len(seeds) < 5:
        return None

    state.postseason = {
        "active": True,
        "completed": False,
        "seeds": seeds,
        "round_index": 0,
        "champion": None
    }

    first, second, third, fourth, fifth = seeds
    set_current_postseason_series(
        state,
        "Wild Card",
        fourth,
        fifth,
        2,
        initial_wins={fourth: 1, fifth: 0}
    )
    return schedule_current_postseason_game(state, date_str)

def record_postseason_result(state, winner, loser, date_str, score_text=None):
    ps = getattr(state, "postseason", {})
    series = ps.get("current_series")
    if not ps.get("active") or ps.get("completed") or not series or series.get("winner"):
        return

    series["wins"][winner] += 1
    series["results"].append({
        "date": date_str,
        "winner": winner,
        "loser": loser,
        "score": score_text
    })
    series["game_no"] += 1

    if series["wins"][winner] >= series["wins_needed"]:
        series["winner"] = winner

def advance_postseason_if_needed(state, date_str):
    ps = getattr(state, "postseason", {})
    if not ps.get("active") or ps.get("completed"):
        return None

    series = ps.get("current_series")
    if not series:
        return None

    if series.get("winner"):
        seeds = ps.get("seeds", [])
        winner = series["winner"]
        stage = series["stage"]

        if stage == "Wild Card":
            set_current_postseason_series(state, "Semi-Playoff", seeds[2], winner, 3)
        elif stage == "Semi-Playoff":
            set_current_postseason_series(state, "Playoff", seeds[1], winner, 3)
        elif stage == "Playoff":
            set_current_postseason_series(state, "Korean Series", seeds[0], winner, 4)
        elif stage == "Korean Series":
            ps["completed"] = True
            ps["champion"] = winner
            state.champion = winner
            state.season_ended = True
            state.inbox.append({
                "date": date_str,
                "subject": "Korean Series Champion",
                "body": f"{winner} won the Korean Series.",
                "read": False
            })
            return "CHAMPION"

    return schedule_current_postseason_game(state, date_str)

def sync_game_date(state):
    """선수 나이 등이 게임 날짜를 따르도록 현재 게임 날짜를 Player 모듈에 알린다."""
    from models import player as player_module
    y, m, d = state.base_date
    player_module.set_game_date(date(y, m, d) + timedelta(days=state.current_day - 1))


def start_new_season(state, curr_date, date_str):
    """오프시즌이 지나 새 해가 되면 지난 시즌을 기록하고 새 시즌(순위·일정·포스트시즌)을 연다."""
    year = curr_date.year
    standings = get_regular_standings(state)
    state.season_history.append({
        "year": getattr(state, "season_ended_year", year - 1),
        "champion": state.champion,
        "standings": [[t, s["win"], s["loss"], s.get("draw", 0)] for t, s in standings],
    })
    for s in state.team_stats.values():
        s.update({"win": 0, "loss": 0, "draw": 0, "games": 0})
    state.regular_season_ended = False
    state.season_ended = False
    state.season_ended_year = None
    state.champion = None
    state.todaygamedone = False
    state.todaygamenotice = False
    generate_season_schedule(state, season_year=year)
    first = min((datetime_key(k, year) for k, v in state.master_schedule.items()), default=None)
    state.inbox.append({
        "date": date_str, "subject": "[Season] %d season" % year,
        "body": "The %d season has been scheduled. Opening day: %s." % (
            year, first.strftime("%Y-%m-%d") if first else "-"),
        "read": False})


def start_initial_draft(state, players):
    """새 게임: 시작일(11월)에 첫 신인 드래프트를 연다. 드래프트가 끝나면 다음 해 3월에 시즌이 개막한다."""
    if getattr(state, "draft", None):
        return
    y, m, d = state.base_date
    curr_date = date(y, m, d) + timedelta(days=state.current_day - 1)
    import ai_team_manager
    ai_team_manager.ensure_profiles(state)
    ai_team_manager.stagger_contracts(state, curr_date, include_user=True)      # 새 게임은 유저 구단도 포함해 계약 만료를 분산해 부족 포지션 판단이 현실적이 되게 한다
    draft_module.start_initial(state, players, curr_date, LEAGUE_TEAMS[:])
    draft_module.run_ai_until_user(state, curr_date)
    state.inbox.append({
        "date": curr_date.strftime("%m/%d"), "subject": "[Draft] Rookie Draft is open",
        "body": "The rookie draft has started. Open the Draft menu to make your picks. "
                "It will auto-complete on %s." % state.draft["deadline"], "read": False})


def datetime_key(date_str, year):
    m, d = map(int, date_str.split("/"))
    return date(year, m, d)


def check_season_end(players, state, date_str):
    regular_days = [v for v in state.master_schedule.values() if v.get("stage", "regular") == "regular"]
    regular_user_games = [g for g in state.schedule.values() if g.get("stage", "regular") == "regular"]
    all_processed = all(v.get("processed", False) for v in regular_days)
    my_games_done = all(g.get("played", False) for g in regular_user_games)

    if not (all_processed and my_games_done):
        return False

    if getattr(state, 'regular_season_ended', False):
        return False
    state.regular_season_ended = True

    # 1. 최종 순위
    standings = get_regular_standings(state)
    rank_body = "=== FINAL STANDINGS ===\n\n"
    for i, (team, stats) in enumerate(standings):
        w, l = stats["win"], stats["loss"]
        pct = w / (w + l) if (w + l) > 0 else 0
        marker = " ◀ YOU" if team == state.user_team else ""
        rank_body += f"{i+1}. {team}  {w}W {l}L  ({pct:.3f}){marker}\n"

    state.inbox.append({
        "date": date_str,
        "subject": "🏆 Season Over - Final Standings",
        "body": rank_body,
        "read": False
    })

    # 2. 개인 타이틀
    all_players = [p for roster in state.team_rosters.values() for p in roster]
    from datetime import date, timedelta
    y, m, d = state.base_date
    current_year = (date(y, m, d) + timedelta(days=state.current_day - 1)).year

    def get_stat(p, key):
        s = next((c for c in p.career if c.get("season") == current_year), None)
        return s["stats"].get(key, 0) if s else 0

    batters  = [p for p in all_players if p.is_batter()]
    pitchers = [p for p in all_players if p.is_pitcher()]

    titles = []

    # 타자 타이틀
    if batters:
        hr_king  = max(batters, key=lambda p: get_stat(p, "hr"))
        rbi_king = max(batters, key=lambda p: get_stat(p, "rbi"))
        sb_king  = max(batters, key=lambda p: get_stat(p, "sb"))
        avg_king = max(batters, key=lambda p: get_stat(p, "h") / max(get_stat(p, "ab"), 1))

        titles += [
            f"💪 HR King:      {hr_king.name} ({hr_king.team}) - {get_stat(hr_king, 'hr')} HR",
            f"🏅 RBI King:     {rbi_king.name} ({rbi_king.team}) - {get_stat(rbi_king, 'rbi')} RBI",
            f"💨 SB King:      {sb_king.name} ({sb_king.team}) - {get_stat(sb_king, 'sb')} SB",
            f"🎯 Batting Avg:  {avg_king.name} ({avg_king.team}) - {get_stat(avg_king, 'h') / max(get_stat(avg_king, 'ab'), 1):.3f}",
        ]

    # 투수 타이틀
    if pitchers:
        win_king = max(pitchers, key=lambda p: get_stat(p, "w"))
        sv_king  = max(pitchers, key=lambda p: get_stat(p, "sv"))
        era_king = min(
            [p for p in pitchers if get_stat(p, "ip") >= 10],  # 최소 이닝 조건
            key=lambda p: get_stat(p, "era") if get_stat(p, "era") > 0 else 99,
            default=None
        )
        titles += [
            f"🏆 Win King:     {win_king.name} ({win_king.team}) - {get_stat(win_king, 'w')}W",
            f"🔒 Save King:    {sv_king.name} ({sv_king.team}) - {get_stat(sv_king, 'sv')} SV",
        ]
        if era_king:
            titles.append(f"⚡ ERA King:     {era_king.name} ({era_king.team}) - {get_stat(era_king, 'era'):.2f} ERA")

    title_body = "=== INDIVIDUAL TITLES ===\n\n" + "\n".join(titles)
    state.inbox.append({
        "date": date_str,
        "subject": "🏅 Season Awards",
        "body": title_body,
        "read": False
    })

    postseason_date = start_kbo_postseason(state, standings, date_str)
    postseason_body = "=== KBO POSTSEASON ===\n\nSeeds:\n"
    for idx, (team, _) in enumerate(standings[:5], 1):
        postseason_body += f"{idx}. {team}\n"
    if postseason_date:
        postseason_body += f"\nWild Card starts on {postseason_date}."
    else:
        postseason_body += "\nPostseason could not be scheduled."
    state.inbox.append({
        "date": date_str,
        "subject": "KBO Postseason Begins",
        "body": postseason_body,
        "read": False
    })
    
    # 3. 계약 만료 선수 안내
    '''
    user_players = state.team_rosters.get(state.user_team, [])
    expiring = [p for p in user_players if p.contract_years_left() <= 0]
    if expiring:
        exp_body = "=== CONTRACT EXPIRY ===\n\nThe following players' contracts expire this season:\n\n"
        for p in expiring:
            exp_body += f"- {p.name} ({p.pos})  ${p.salary():,}/yr\n"
        exp_body += "\nPlease negotiate new contracts before next season."
        state.inbox.append({
            "date": date_str,
            "subject": "📋 Expiring Contracts",
            "body": exp_body,
            "read": False
        })
    '''
    return True

def move_player_to_fa(state, player):
    old_team = player.team
    if old_team in state.team_rosters and player in state.team_rosters[old_team]:
        state.team_rosters[old_team].remove(player)

    state.team_rosters.setdefault("FA", [])
    if player not in state.team_rosters["FA"]:
        state.team_rosters["FA"].append(player)

    player.team = "FA"
    player.backnumber = None
    player.contract = {
        "salary": 0,
        "begin": None,
        "end": None
    }
    player.status["roster"] = "fa"

    player.data["team"] = "FA"
    player.data["backnumber"] = None
    player.data["contract"] = player.contract
    player.data["status"] = player.status

def process_user_staff_contracts(state, curr_date, date_str):
    """유저 팀 스태프 계약: 만료 30일 전에 알리고, 만료되면 FA로 내보낸다(담당 슬롯에서도 빠진다)."""
    expiring_soon, expired = [], []
    for s in list(getattr(state, "owned_staff", [])):
        end_text = s.contract_end()
        try:
            end_date = date.fromisoformat(end_text) if end_text else None
        except ValueError:
            end_date = None
        if end_date is None:
            continue
        days_left = (end_date - curr_date).days
        if days_left <= 0:
            expired.append(s)
        elif days_left <= 30 and s.status.get("staff_notice_for") != end_text:
            s.status["staff_notice_for"] = end_text          # 계약이 바뀌면(end가 달라지면) 알림도 다시 나간다
            s.data["status"] = s.status
            expiring_soon.append(s)
    if expiring_soon:
        body = "The following staff contracts expire within 30 days:\n\n"
        for s in expiring_soon:
            body += f"- {s.name} ({s.role})  End: {s.contract_end()}\n"
        state.inbox.append({"date": date_str, "subject": "Staff Contract Expiry Notice", "body": body, "read": False})
    if expired:
        body = "The following staff contracts have expired and they became free agents:\n\n"
        for s in expired:
            body += f"- {s.name} ({s.role})\n"
            s.team = "FA"
            s.contract = {"salary": 0, "begin": None, "end": None}
            s.status["roster"] = "fa"
            s.status.pop("staff_notice_for", None)
            s.data["team"] = "FA"
            s.data["contract"] = s.contract
            s.data["status"] = s.status
            state.owned_staff.remove(s)
            slots = getattr(state, "staff_slots", {})
            if slots.get(s.role) is s:
                del slots[s.role]
                replacement = next((o for o in state.owned_staff if o.role == s.role), None)
                if replacement is not None:
                    slots[s.role] = replacement
        state.inbox.append({"date": date_str, "subject": "Staff Became Free Agents", "body": body, "read": False})
    return bool(expiring_soon or expired)


def process_user_contracts(state, curr_date, date_str):
    user_roster = list(state.team_rosters.get(state.user_team, []))
    expiring_soon = []
    expired = []

    for player in user_roster:
        end_text = player.contract_end()
        if not end_text:
            continue

        try:
            end_date = date.fromisoformat(end_text)
        except ValueError:
            continue

        days_left = (end_date - curr_date).days
        if days_left == 30 and not player.status.get("contract_30day_notice_sent"):
            player.status["contract_30day_notice_sent"] = True
            expiring_soon.append(player)
        elif days_left <= 0 and not player.status.get("contract_expired_notice_sent"):
            player.status["contract_expired_notice_sent"] = True
            expired.append(player)

    if expiring_soon:
        body = "The following players' contracts expire in 30 days:\n\n"
        for player in expiring_soon:
            body += f"- {player.name} ({player.pos})  End: {player.contract_end()}\n"
        state.inbox.append({
            "date": date_str,
            "subject": "Contract Expiry Notice",
            "body": body,
            "read": False
        })

    if expired:
        body = "The following players' contracts have expired and they became free agents:\n\n"
        for player in expired:
            body += f"- {player.name} ({player.pos})\n"
            move_player_to_fa(state, player)
        state.inbox.append({
            "date": date_str,
            "subject": "Players Became Free Agents",
            "body": body,
            "read": False
        })

    return bool(expiring_soon or expired)

def staff_trait_bonus(state, role, trait_name):
    staff = getattr(state, "staff_slots", {}).get(role)
    if not staff or not hasattr(staff, "get_trait_bonus"):
        return 0
    return staff.get_trait_bonus(trait_name)

def apply_training_staff_bonus(state, player, exp_gain):
    if player.team != state.user_team:
        return exp_gain

    bonus = staff_trait_bonus(state, "HD", "training_efficiency")
    age = player.age()
    if age is not None and age <= 25:
        bonus += staff_trait_bonus(state, "HD", "young_growth_boost")

    return int(exp_gain * (1 + bonus * 0.05))

def apply_rest_fatigue_staff_bonus(state, player, fatigue_recovery):
    if player.team != state.user_team:
        return fatigue_recovery

    bonus = staff_trait_bonus(state, "HD", "rest_fatigue_recovery")
    return fatigue_recovery + bonus * 8

def apply_health_recovery_staff_bonus(state, player, health_recovery):
    if player.team != state.user_team:
        return health_recovery

    bonus = staff_trait_bonus(state, "HD", "rest_fatigue_recovery")
    return health_recovery + bonus * 20

def apply_injury_risk_staff_bonus(state, player, injury_chance):
    if player.team != state.user_team:
        return injury_chance

    bonus = staff_trait_bonus(state, "DR", "injury_risk_reduction")
    return injury_chance * max(0.50, 1 - bonus * 0.06)

def apply_injury_days_staff_bonus(state, player, injury_days):
    if player.team != state.user_team:
        return injury_days

    bonus = staff_trait_bonus(state, "DR", "injury_days_reduction")
    return max(1, int(injury_days * max(0.50, 1 - bonus * 0.06)))

def has_surprise_rehab(state, player):
    if player.team != state.user_team:
        return False

    bonus = staff_trait_bonus(state, "DR", "surprise_rehab")
    return bonus > 0 and random.random() < min(0.10, bonus * 0.01)

def apply_veteran_decline_staff_bonus(state, player, decline):
    if player.team != state.user_team:
        return decline

    bonus = staff_trait_bonus(state, "HD", "veteran_decline_slowdown")
    return max(0, int(decline * max(0.50, 1 - bonus * 0.06)))

def process_day(players, state):
    import random
    from datetime import date, timedelta
    
    something = 0
    res = None
    
    base_y, base_m, base_d = state.base_date
    curr_date = date(base_y, base_m, base_d) + timedelta(days=state.current_day - 1)
    date_str = curr_date.strftime("%m/%d")
    sync_game_date(state)
    if getattr(state, "postseason", {}).get("active"):
        advance_postseason_if_needed(state, date_str)
    day_data = state.master_schedule.get(date_str)
    
    all_players = []
    for team, roster in state.team_rosters.items():
        all_players.extend(roster)

    # 시즌이 끝났으면 해가 바뀔 때 새 시즌을 개막한다 (오프시즌: 드래프트·FA·계약)
    if getattr(state, "season_ended", False):
        if getattr(state, "season_ended_year", None) is None:
            state.season_ended_year = curr_date.year
        elif curr_date.year > state.season_ended_year:
            start_new_season(state, curr_date, date_str)
            something = 1
            day_data = state.master_schedule.get(date_str)

    if process_user_contracts(state, curr_date, date_str):
        something = 1
    if process_user_staff_contracts(state, curr_date, date_str):
        something = 1

    # AI 구단의 재계약·방출·FA 영입 (하루 1회)
    if getattr(state, "_ai_tx_day", None) != state.current_day:
        state._ai_tx_day = state.current_day
        import ai_team_manager
        ai_log = ai_team_manager.process_ai_teams(state, curr_date)
        if ai_team_manager.post_news(state, ai_log, date_str):
            something = 1

    # 시즌이 끝나면 신인 드래프트를 열고 진행한다
    if draft_module.process_daily(state, players, curr_date, get_regular_standings(state), date_str):
        something = 1
    
    # 1. 월초 처리 (매달 1일)
    if curr_date.day == 1:
        if not state.salary_paid_this_month:
            last_profit = sum(state.monthly_income.values()) - sum(state.monthly_expense.values())
            state.profit_history.append(last_profit)
            if len(state.profit_history) > 6: state.profit_history.pop(0)
            
            for k in state.monthly_income: state.monthly_income[k] = 0
            for k in state.monthly_expense: state.monthly_expense[k] = 0

            total_annual_salary = sum(p.salary() for p in players)

            monthly_wage = total_annual_salary // 12
            state.add_money(-monthly_wage)
            state.monthly_expense["Wages"] = state.monthly_expense.get("Wages", 0) + monthly_wage
        
            state.inbox.append({
                "date": date_str, "subject": "Monthly Salary Paid",
                "body": f"Paid ${monthly_wage:,} to players.", "read": False
            })
            state.salary_paid_this_month = True
            something=1
        else:
            state.salary_paid_this_month = False
        
    if day_data and not day_data.get("processed", False):
        daily_report = []
        
        for team_a, team_b in day_data["matches"]:
            if team_a == state.user_team or team_b == state.user_team:
                daily_report.append(f"[MY MATCH] {team_a} vs {team_b}")
                continue
            
            import ai_match
            res = ai_match.play(state, team_a, team_b, AI_REST_FATIGUE)      # 사용자 경기와 같은 엔진
            if res:
                score_a, score_b, play_a, play_b = res
            else:                                                            # 라인업을 못 채우는 팀이 있으면 예외적으로 무작위
                score_a, score_b, play_a, play_b = random.randint(0, 13), random.randint(0, 13), None, None
            if score_a == score_b: score_a += 1 # 무승부 방지
            
            winner, loser = (team_a, team_b) if score_a > score_b else (team_b, team_a)
            w_score, l_score = (score_a, score_b) if score_a > score_b else (score_b, score_a)
            
            for t, res in [(winner, "W"), (loser, "L")]:
                if t in state.team_data:
                    form = state.team_data[t].get("recent_form", [])
                    form.append(res)
                    if len(form) > 5: form.pop(0) # 최근 5경기 유지
                    state.team_data[t]["recent_form"] = form
            
            if day_data.get("stage") == "postseason":
                record_postseason_result(state, winner, loser, date_str, f"{w_score}:{l_score}")
            else:
                state.record_match_result(winner, loser)
            pw, pl = (play_a, play_b) if winner == team_a else (play_b, play_a)
            simulate_ai_player_stats(state.team_rosters.get(winner), state.team_rosters.get(loser), pw, pl)
            
            daily_report.append(f"{winner} {w_score} : {l_score} {loser}")

        if daily_report:
            report_body = "Today's League Results:\n\n" + "\n".join(daily_report)
            state.inbox.append({
                "date": date_str,
                "subject": f"League Round-up: {date_str}",
                "body": report_body,
                "read": False
            })
            something = 1
            day_data["processed"] = True

    game = state.schedule.get(date_str)
    #opponent = game.get("opponent", "Unknown Team") if game else "No Opponent"
    
    #is_match_day = game and game["type"] in ["HOME", "AWAY"]
    
    if game and game["type"] == "HOME":
        income = int(state.stadium_cap * random.randint(50, 100) / 100) * state.ticket_price
        state.add_money(income)
        state.monthly_income["Tickets"] = state.monthly_income.get("Tickets", 0) + income
    
    game = state.schedule.get(date_str)
    if game and game["type"] in ["HOME", "AWAY"]:
        if not state.todaygamedone:
            if not state.todaygamenotice:
                state.todaygamenotice = True
                state.inbox.append({
                    "date": date_str, "subject": "Today's Game",
                    "body": f"Tonight's match against {game['opponent']}.", "read": False
                })
                res= "NEW_MESSAGE"
            else:
                res= "GAME"

    for p in all_players: 
        if p.status["fatigue"] > 200 and not p.status.get("is_injured"):
            injury_chance = min(0.5, ((p.status["fatigue"] - 200) ** 2) / 40000 + 0.05)
            injury_chance = apply_injury_risk_staff_bonus(state, p, injury_chance)
            if random.random() < injury_chance: 
                p.status["is_injured"] = True
                p.status["injury_days"] = apply_injury_days_staff_bonus(state, p, random.randint(3, 30))
                if p.team == state.user_team:
                    state.inbox.append({
                    "date": date_str, "subject": f"Injury Report: {p.name}",
                    "body": f"Unfortunately, {p.name} suffered an injury. \nExpected recovery will be {p.status['injury_days']} days.",
                    "read": False
                    })
                    something = 1
                    
        if p.status.get("is_injured"):
            continue

        if p.status.get("training_mode") == "REST":
            recovery = 60 * (getattr(p, 'stamina', 100) / 100)
            recovery = apply_rest_fatigue_staff_bonus(state, p, recovery)
            p.status["fatigue"] = max(0, p.status["fatigue"] - recovery)
            p.status["exp"] += apply_training_staff_bonus(state, p, 5)
        elif p.status.get("training_mode") == "TRAIN":
            if p.status["condition"] < 70:
                p.status["condition"] = min(70, p.status["condition"] + 10)
            p.status["fatigue"] = max(0, p.status["fatigue"] - 20)
            p.status["exp"] += apply_training_staff_bonus(state, p, 30)
        else:
            if p.status["condition"] < 70:
                p.status["condition"] = min(70, p.status["condition"] + 15)
            p.status["fatigue"] = max(0, p.status["fatigue"] - 10)
            p.status["exp"] += apply_training_staff_bonus(state, p, 50)

        if p.status.get("roster") == "inactive" and (p.age() or 30) <= 26:
            p.status["exp"] += 25      # 2군 육성: 젊은 2군 선수는 매일 추가 경험치

    # 휴식일 알림 (선택 사항)
    if game and game["type"] == "REST":
        something = 1
        state.inbox.append({
            "date": date_str, "subject": "[REST] No Game Today",
            "body": "The team had a day off to recover.", "read": False
        })

    # 3. 공통 마무리 (부상 날짜 감소, 날짜 증가, 체력 회복)
    for p in all_players:
        if p.status.get("is_injured"):
            p.status["injury_days"] = max(0, p.status["injury_days"] - 1)
            if has_surprise_rehab(state, p):
                p.status["injury_days"] = 0
            if p.status["injury_days"] == 0:
                p.status["is_injured"] = False
                p.status["health"] = 1000
                p.status["condition"] = 0
                if p.team == state.user_team:
                    something=1
                    state.inbox.append({
                    "date": date_str, "subject": f"Return: {p.name}",
                    "body": f"{p.name} has recovered and is ready to come back.", "read": False
                    })
        if p.status.get("training_mode") == "REST":
            recovery = 400 + (p.get_attr("stamina", state) / 9)*10
        elif p.status.get("training_mode") == "TRAIN":
            recovery = 200
        else:
            recovery = 100
        
        recovery = apply_health_recovery_staff_bonus(state, p, recovery)
            
        p.status["health"] = min(1000, p.status.get("health", 0) + recovery)
        
        age = p.age()
        max_exp = p.status.get("maxexp", 1000)
        grow = 0
        
        if age is not None and age > 32:
            p.status["exp"] -= apply_veteran_decline_staff_bonus(state, p, 10 * (age-32))
            
        if p.status.get("exp", 0) < 0:
            # 음수 경험치는 별도 하락 카운터로 이월(성장 경험치와 분리)
            p.status["decline_exp"] = p.status.get("decline_exp", 0) - p.status["exp"]
            p.status["exp"] = 0
        while p.status.get("decline_exp", 0) >= max_exp:
            p.status["decline_exp"] -= max_exp
            stats_to_decline = list(p.attr.keys())
            
            target_stat = random.choice(stats_to_decline)
            stat_data = p.attr[target_stat]
            
            if stat_data["cur"] > 30:
                stat_data["cur"] -= 1
                stat_data["pot"] -= 1
            else:
                for alternative in stats_to_decline:
                    if p.attr[alternative]["cur"] > 30:
                        target_stat = alternative
                        p.attr[alternative]["cur"] -= 1
                        p.attr[alternative]["pot"] -= 1
                        break    

        while p.status.get("exp", 0) >= max_exp:
            p.status["exp"] -= max_exp
            stats_to_boost = list(p.attr.keys())
            
            target_stat = random.choice(stats_to_boost)
            stat_data = p.attr[target_stat]
            
            
            if stat_data["cur"] < stat_data["pot"]:
                stat_data["cur"] += 1
                grow = 1
            else:
                for alternative in stats_to_boost:
                    if p.attr[alternative]["cur"] < p.attr[alternative]["pot"]:
                        target_stat = alternative
                        grow = 1
                        p.attr[alternative]["cur"] += 1
                        break
        if grow != 0 and p.team == state.user_team:
            something = 1   
            state.inbox.append({
                "date": date_str, "subject": f"Progress for {p.name}",
                "body": f"Our staffs observed remarkable improvement in {p.name}'s performance.", "read": False
            })
                   
    # 부상 보고 등 다른 메시지가 매일 있어도 정규시즌 종료 판정은 건너뛰지 않는다
    if check_season_end(players, state, date_str):
        return "NEW_MESSAGE"
    if res == "NEW_MESSAGE" or something == 1:
        return "NEW_MESSAGE"
    if res == "GAME": return "GAME"
    
    
    if res == None and something==0:
        state.is_fading = True
        state.fade_alpha = 0
        state.fade_direction = 1
    
        state.todaygamedone = False
        state.todaygamenotice = False

        state.finance_history.append(state.money)
        if len(state.finance_history) > 30: state.finance_history.pop(0)
    
    
    if something==1:
        return "NEW_MESSAGE"
    if check_season_end(players, state, date_str):
        return "NEW_MESSAGE"
    return None

def restore_saved_references(state, players, staff_members):
    player_by_id = {p.id: p for p in players}
    staff_by_id = {s.id: s for s in staff_members}

    lineup_ids = getattr(state, "saved_lineup_ids", {})
    if lineup_ids:
        for pos in state.lineup:
            state.lineup[pos] = player_by_id.get(lineup_ids.get(pos))

    order_ids = getattr(state, "saved_batting_order_ids", [])
    if order_ids:
        state.batting_order = [player_by_id.get(pid) for pid in order_ids[:9]]
        while len(state.batting_order) < 9:
            state.batting_order.append(None)

    bullpen_ids = getattr(state, "saved_bullpen_ids", [])
    if bullpen_ids:
        state.bullpen = [player_by_id.get(pid) for pid in bullpen_ids[:8]]
        while len(state.bullpen) < 8:
            state.bullpen.append(None)

    state.all_staff = staff_members
    state.owned_staff = [s for s in staff_members if s.team == state.user_team]

    slot_ids = getattr(state, "saved_staff_slot_ids", {})
    state.staff_slots = {}
    if slot_ids:
        for role, staff_id in slot_ids.items():
            staff = staff_by_id.get(staff_id)
            if staff:
                state.staff_slots[role] = staff
    else:
        for staff in state.owned_staff:
            if staff.role not in state.staff_slots:
                state.staff_slots[staff.role] = staff

def save_current_game(state, players, slot=None):
    """현재 게임을 슬롯에 저장한다. 디스크 용량 부족 등으로 실패하면 False (기존 저장 파일은 그대로 남는다)."""
    slot = slot or getattr(state, "active_save_slot", 1)
    try:
        save_game(state, players, getattr(state, "all_staff", []), slot=slot)
        return True
    except OSError:
        return False


def build_runtime(raw_state):
    state = GameState(raw_state)

    if raw_state.get("players"):
        players = [Player(p) for p in raw_state.get("players", [])]
    else:
        raw_players_dict = load_players()
        players = [Player(p) for p in raw_players_dict.values()]

    if raw_state.get("staff"):
        staff_members = [Staff(s) for s in raw_state.get("staff", [])]
    else:
        raw_staff_dict = load_staff()
        staff_members = [Staff(s) for s in raw_staff_dict.values()]

    if not state.team_data:
        state.team_data = load_team_data()

    state.team_data[state.user_team]

    state.team_rosters = {}
    for p in players:
        team = getattr(p, "team", None)
        if team not in state.team_rosters:
            state.team_rosters[team] = []
        state.team_rosters[team].append(p)

    restore_saved_references(state, players, staff_members)
    user_players = state.team_rosters[state.user_team]
    sync_game_date(state)

    if not state.master_schedule:
        generate_season_schedule(state)
        start_initial_draft(state, players)

    scenes = {
    "title": TitleScene(),
    "hub": HubScene(state),
    "inbox": InboxScene(state),
    "team": TeamScene(user_players,state,state.user_team),
    "finance": FinanceScene(state,user_players),
    "schedule": ScheduleScene(state),
    "medical": MedicalScene(user_players,state),
    "train":TrainingScene(user_players,state),
    "squad":SquadScene(user_players,state),
    "staff":StaffScene(state),
    "lineup":LineupScene(user_players,state),
    "option": OptionScene(state),
    "info": TeamDetailScene(state,state.user_team),
    "reserve": ReserveScene(user_players,state),
    "transfer": TransferScene(state),
    "transactions": TransactionsScene(state),
    "draft": DraftScene(state),
    }

    return state, players, staff_members, user_players, scenes


def main():
    raw_state = default_save_data()
    state = GameState(raw_state)

    #current_day = state["current_day"]
    #base_year, base_month, base_day = state["base_date"]
      
    clock=pygame.time.Clock()

    if raw_state.get("players"):
        players = [Player(p) for p in raw_state.get("players", [])]
    else:
        raw_players_dict = load_players()
        players = [Player(p) for p in raw_players_dict.values()]

    if raw_state.get("staff"):
        staff_members = [Staff(s) for s in raw_state.get("staff", [])]
    else:
        raw_staff_dict = load_staff()
        staff_members = [Staff(s) for s in raw_staff_dict.values()]
    
    if not state.team_data:
        state.team_data = load_team_data()
    
    state.team_data[state.user_team]

    # 팀별 로스터 분리
    state.team_rosters = {}
    for p in players:
        team = getattr(p, "team", None)
        if team not in state.team_rosters:
            state.team_rosters[team] = []
        state.team_rosters[team].append(p)

    restore_saved_references(state, players, staff_members)

    # 내 팀 선수만 따로
    user_players = state.team_rosters[state.user_team]
    sync_game_date(state)

    if not state.master_schedule:
        generate_season_schedule(state)
        start_initial_draft(state, players)

    scenes = {
    "title": TitleScene(),
    "hub": HubScene(state),
    "inbox": InboxScene(state),
    #"game": GameScene(),
    "team": TeamScene(user_players,state,state.user_team),
    "finance": FinanceScene(state,user_players),
    "schedule": ScheduleScene(state),
    "medical": MedicalScene(user_players,state),
    "train":TrainingScene(user_players,state),
    "squad":SquadScene(user_players,state),
    "staff":StaffScene(state),
    "lineup":LineupScene(user_players,state),
    "option": OptionScene(state),
    "info": TeamDetailScene(state,state.user_team),
    "reserve": ReserveScene(user_players,state),
    "transfer": TransferScene(state),
    "transactions": TransactionsScene(state),
    "draft": DraftScene(state),
    }
    current="title"
    
    ts=0
    last=0
    
    base_y, base_m, base_d = state.base_date
    # current_day를 기준으로 오늘 날짜 계산
    curr_date = date(base_y, base_m, base_d) + timedelta(days=state.current_day - 1)
    date_str = curr_date.strftime("%m/%d")
    day_data = state.master_schedule.get(date_str)
    
    global tutorial
    if tutorial == 0:
        state.inbox.append({
            "date": date_str, "subject": "Welcome",
            "body": (
            "Welcome, new manager.\n"
            "We've chosen you as the right person to continue our team's glorious history.\n"
            f"We're happy that you're now a member of {state.user_team}, and expecting much from you.\n"
            "However, please keep in mind that you take full responsibilty for the results.\n"
            "Thank you."
            ),
            "read": False
        })
        tutorial = 1
    
    while True:
        screen.fill(white)
        events=pygame.event.get()
        space_pressed = False
        space_advance = False
        """
        if current == "title":
            target_bgm = os.path.join(ASSET_PATH, "bensound-creativeminds.mp3")
            change_bgm(target_bgm, loop=-1) # 타이틀은 무한 반복
        else:
            title_bgm_path = os.path.join(ASSET_PATH, "bensound-creativeminds.mp3")
            if current_bgm == title_bgm_path or current_bgm is None:
                current_track_index = 0
                target_bgm = playlist[current_track_index]
                change_bgm(target_bgm, loop=0)
        """
        for event in events:
            if event.type==pygame.QUIT:
                if current != "title":                  # 타이틀에서 창을 닫을 때는 저장하지 않는다 (빈 슬롯이 생기지 않게)
                    save_current_game(state, players)
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONUP:
                state.waiting_for_click_release = False

            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                space_pressed = True

            if event.type == pygame.KEYUP and event.key == pygame.K_SPACE:
                state.waiting_for_click_release = False
            
        filtered_events = events
        if state.is_fading:
            filtered_events = [e for e in events if e.type not in [MOUSEBUTTONDOWN, MOUSEBUTTONUP]]
                
            """
            if event.type == MUSIC_ENDED and current!="title":
                play_next_track()
            """
                
        #result = scenes[current].update(events)
        result = scenes[current].update(filtered_events)

        if (
            result is None
            and space_pressed
            and current != "game"
            and current != "title"
            and not state.is_fading
        ):
            result = "advance_time"
            space_advance = True

        # 스페이스바: 허브·받은편지함에서는 읽지 않은 메시지를 오래된 것부터 하나씩 열고,
        # 모두 읽은 뒤에야 다음 날로 넘어간다.
        if (result == "advance_time" and space_advance and current in ("hub", "inbox")
                and not getattr(state, 'waiting_for_click_release', False)):
            unread = [m for m in state.inbox if not m.get("read")]
            if unread:
                mail = unread[0]
                mail["read"] = True
                inbox_scene = scenes["inbox"]
                inbox_scene.selected_mail = mail
                idx = len(state.inbox) - 1 - state.inbox.index(mail)      # 목록은 최신이 위
                max_off = max(0, len(state.inbox) - inbox_scene.visible_rows)
                inbox_scene.scroll_offset = min(idx, max_off) if idx >= inbox_scene.visible_rows else 0
                current = "inbox"
                state.waiting_for_click_release = True
                result = None

        if result == "advance_time":
            if not getattr(state, 'waiting_for_click_release', False): 
                stop_reason = process_day(players, state) 
                state.waiting_for_click_release = True
                
                if stop_reason == "NEW_MESSAGE":
                    current = "inbox" # 암전 없이 즉시 이동
                elif stop_reason == "GAME":
                    scenes["lineup"] = LineupScene(user_players, state)
                    current = "lineup"  # 암전 없이 즉시 이동
                else:
                    # 2. 아무 이벤트가 없을 때만 '암전 연출' 시작
                    state.is_fading = True
                    state.fade_alpha = 0
                    state.fade_direction = 1
                    state.day_incremented_this_fade = False
                    
        elif isinstance(result, tuple):
            key, player = result
            if key == "load_slot":
                state, players, staff_members, user_players, scenes = build_runtime(load_game(slot=player))
                tutorial = 1
                current = "hub"
            elif key == "save_game":
                saved = save_current_game(state, players, slot=player)
                scenes["title"].refresh_slots()
                state.inbox.append({
                    "date": state.get_current_date_str(),
                    "subject": "Game Saved" if saved else "Save Failed",
                    "body": (f"Your game has been saved to slot {player}." if saved else
                             f"Could not save to slot {player} (not enough disk space?). The previous save in that slot is unchanged."),
                    "read": False
                })
                scenes["inbox"] = InboxScene(state)
                current = "inbox"
            elif key == "player_detail":
                state.prevscene = current
                scenes["player_detail"] = PlayerDetailScene(player,state)
                current = "player_detail"
            elif key == "staff_detail":
                state.prevscene = current
                scenes["staff_detail"] = StaffDetailScene(player,state)
                current = "staff_detail"

            elif key == "staff_contract":
                scenes["staff_contract"] = player
                current = "staff_contract"

            elif key == "staff_detail_refresh":
                scenes["staff_detail"] = StaffDetailScene(player,state)
                current = "staff_detail"
                
            elif key == "result":
                scenes["result"] = ResultScene(player, state)
                current = "result"

            elif key == "team_detail":
                scenes["team_detail"] = TeamDetailScene(state, player) 
                current = "team_detail"
            elif key == "view_team":
                target_team = player
    
                target_players = state.team_rosters.get(target_team, [])
                scenes["team"] = TeamScene(target_players, state, player)
                current = "team"

            elif key == "contract":
                scenes["contract"] = player
                current = "contract"
        elif result:
            if result == "save_game":
                save_current_game(state, players)
                scenes["title"].refresh_slots()
                state.inbox.append({
                    "date": state.get_current_date_str(),
                    "subject": "Game Saved",
                    "body": "Your game has been saved.",
                    "read": False
                })
                scenes["inbox"] = InboxScene(state)
                current = "inbox"
            elif result == "game": # LineupScene이 완료되어 "game"을 반환하면
                scenes["game"] = GameScene(user_players, state)
                current = "game"
            elif result in scenes:
                if result == "option":
                    state.prevscene = current
                if result == "team":
                    user_players = state.team_rosters.get(state.user_team, [])
                    scenes["team"] = TeamScene(user_players, state, state.user_team)
                if result == "squad":
                    scenes["squad"] = SquadScene(user_players, state)
                current = result
        scenes[current].draw(screen)
        
        if state.is_fading:
            # 1. 투명도 조절
            state.fade_alpha += (3 * state.fade_direction)
    
            # 2. 완전히 어두워졌을 때 (정점)
            if state.fade_alpha >= 255:
                state.fade_alpha = 255
                state.fade_direction = -1 # 이제 다시 밝아짐
        
                # [수정] 정점에서 날짜를 미리 올림 (중복 실행 방지)
                if not getattr(state, 'day_incremented_this_fade', False):
                    state.current_day += 1
                    sync_game_date(state)
                    save_current_game(state, players)
                    #stop_reason = process_day(players, state)
                    state.day_incremented_this_fade = True
                    
            # 3. 다시 완전히 밝아졌을 때 (종료)
            elif state.fade_alpha <= 0 and state.fade_direction == -1:
                state.fade_alpha = 0
                state.is_fading = False
                # state.current_day += 1  <-- [삭제] 여기서 올리면 밝아진 뒤에 숫자가 바뀜
                state.day_incremented_this_fade = False # 플래그 초기화
    
            # 4. 레이어 및 텍스트 출력
            fade_surface = pygame.Surface((width, height))
            fade_surface.set_alpha(state.fade_alpha)
            fade_surface.fill((0, 0, 0))
            screen.blit(fade_surface, (0, 0))

            if state.fade_alpha > 150:
                date_text = state.get_current_date_str()
                date_surf = BIGFONT.render(f"DAY {state.current_day} - {date_text}", True, (255, 255, 255))
                date_rect = date_surf.get_rect(center=(width//2, height//2))
                screen.blit(date_surf, date_rect)
        pygame.display.flip()

        clock.tick(settings["fps"])
        ts+=1
    
    
if __name__=="__main__":
    main()
