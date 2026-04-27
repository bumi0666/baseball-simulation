from datetime import date, datetime

class Player:
    def __init__(self, data):
        self.data = data
        self.team = data.get("team")

        self.id = data["id"]
        self.name = data["name"]
        self.pos = data["pos"]
        self.backnumber = data["backnumber"]

        self.bio = data.get("bio", {})
        self.contract = data.get("contract", {})
        self.status = data.get("status", {})
        self.attr = data.get("attributes", {})
        self.career = data.get("career", [])
        self.awards = data.get("awards", [])
        
        self.recent_log = []
        self.last_report_key = None
        
        self.reset_game_stats()

    def is_pitcher(self):
        return self.pos == "P"

    def is_batter(self):
        return self.pos != "P"

    def birth(self):
        return self.bio.get("birth")

    def age(self):
        if not self.birth():
            return None
        y, m, d = map(int, self.birth().split("-"))
        today = date.today()
        return today.year - y - ((today.month, today.day) < (m, d))

    def height(self):
        return self.bio.get("height")

    def weight(self):
        return self.bio.get("weight")

    def nationality(self):
        return self.bio.get("nationality")

    def salary(self):
        return self.contract.get("salary", 0)

    def contract_begin(self):
        return self.contract.get("begin")

    def contract_end(self):
        return self.contract.get("end")

    def contract_years_left(self):
        if not self.contract_end():
            return 0
        end = datetime.strptime(self.contract_end(), "%Y-%m-%d").date()
        today = date.today()
        return max(0, (end - today).days // 365)

    def is_free_agent(self):
        if not self.contract_end():
            return True
        end = datetime.strptime(self.contract_end(), "%Y-%m-%d").date()
        return date.today() >= end

    def get_attr(self, name, state=None):
        # 1. 원래 가지고 있던 현재 능력치 가져오기
        val = self.attr[name]["cur"]
    
        # 2. 만약 state가 전달되었다면 보너스 계산해서 더하기
        if state:
            val += self.get_bonus(name, state)
        
        return val

    def get_pot(self, name):
        return self.attr[name]["pot"]
    
    def get_health(self):
        return self.status.get("health", 0)
    
    def get_injury_risk(self):
    # 피로도가 80 이상이면 'High Risk'
        if self.status.get("fatigue", 0) > 80:
            return "High"
        elif self.status.get("fatigue", 0) > 50:
            return "Moderate"
        return "Low"
    
    def update_status_after_game(self, innings):
        # 1. 기본 증가량 계산
        if self.pos == "P":
            stamina = self.get_attr("stamina", 100)
            inc = 30 * innings * (100 / stamina)
        elif self.pos == "C":
            inc = 8 * innings
        else:
            inc = 5 * innings

        # 2. 컨디션 페널티 (70 미만일 때 1.5배 가속)
        if self.status["condition"] < 70:
            inc *= 1.5

        # 3. 수치 적용
        self.status["fatigue"] += inc
        self.status["condition"] = min(100, self.status["condition"] + 5) # 경기 후 컨디션 상승
        
    def calculate_ovr(player):
        attr_data = player.attr
    
        target_keys = ["contact", "power", "eye", "run", "defense", 
                   "velocity", "control", "stamina", "stuff"]

        cur_values = [attr_data[k]["cur"] for k in target_keys if k in attr_data]
    
        if not cur_values:
            return 0
        
        # 추출된 값들의 평균 (능력치가 5개라고 가정)
        ovr = sum(cur_values) // len(cur_values)
        return ovr
    
    def reset_game_stats(self):
        # 타자 공통
        self.game_stats = {
        "ab": 0,
        "h": 0,
        "hr": 0,
        "rbi": 0,
        "bb": 0,
        "so": 0,
        "sb": 0
        }

        # 투수
        if self.pos == "P":
            self.game_stats.update({
            "ip_outs": 0,
            "h_allowed": 0,
            "r_allowed": 0,
            "er": 0,
            "bb_p": 0,
            "so_p": 0,
            "is_win": False,
            "is_loss": False,
            "is_save": False,
            "is_hold": False,
            "entry_score_diff": 0,
            "entry_runners": 0,
            "quit_score_diff": 0,
            #"entered_at_inning": 0,
            "is_starter": False
            })
            
    def get_current_season(self, year):
        for c in self.career:
            if c["season"] == year:
                return c
        return None
    
    def current_season(self):
        return self.career[-1]
    
    def get_bonus(self, name, state):
        """보너스 수치 계산 (내 팀 선수일 때만 적용)"""
        # 1. 예외 처리 및 내 팀 확인
        # state.user_team은 사용자가 고른 팀 이름 (예: "Eagles")
        if not hasattr(state, 'staff_slots') or self.team != state.user_team:
            return 0
    
        role = "PC" if self.pos == "P" else "HC"
        staff = state.staff_slots.get(role)

        # 2. 메인 코치 보너스
        if staff and hasattr(staff, 'effect_dict'):
            if name in staff.effect_dict:
                return int(staff.stars * staff.effect_dict[name])
            
        # 3. 수비 코치 보너스
        if name == "defense":
            dc = state.staff_slots.get("DC")
            if dc and "defense" in dc.effect_dict:
                return int(dc.stars * dc.effect_dict["defense"])
            
        return 0
    
    def add_game_log(self):
        """매 경기 종료 후 호출하여 최근 5경기 원천 데이터 저장"""
        if self.is_pitcher():
            log_entry = {
                "er": self.game_stats["er"],
                "so": self.game_stats["so_p"],
                "bb": self.game_stats["bb_p"],
                "ip_outs": self.game_stats["ip_outs"],
                "win": 1 if self.game_stats.get("is_win") else 0,
                "save": 1 if self.game_stats["is_save"] else 0,
                "hold": 1 if self.game_stats["is_hold"] else 0
            }
        else:
            log_entry = {
                "ab": self.game_stats["ab"],
                "h": self.game_stats["h"],
                "hr": self.game_stats["hr"],
                "rbi": self.game_stats["rbi"],
                "so": self.game_stats["so"]
            }
        
        self.recent_log.append(log_entry)
        if len(self.recent_log) > 5:
            self.recent_log.pop(0)
            
    def analyze_recent_performance(self):
        if len(self.recent_log) < 5: return None
        
        logs = self.recent_log
        res = [] # 탐지된 조건 키워드를 담을 리스트

        if self.is_batter():
            
            t_ab = sum(l["ab"] for l in logs)
            if t_ab < 12: return None
            
            t_h = sum(l["h"] for l in logs)
            t_hr = sum(l["hr"] for l in logs)
            t_rbi = sum(l["rbi"] for l in logs)
            t_so = sum(l["so"] for l in logs)
            avg = t_h / t_ab if t_ab > 0 else 0

            # 타자 조건 체크
            if t_hr >= 3: return "BATTER_HOT_HR"
            if t_rbi >= 8: return "BATTER_HOT_RBI"
            if avg >= 0.400: return "BATTER_HOT_AVG"
            if t_so >= 10: return "BATTER_COLD_SO"
            if avg <= 0.100: return "BATTER_COLD_AVG"

        else:
            t_outs = sum(l["ip_outs"] for l in logs)
            t_ip = t_outs / 3.0
            if t_ip < 4.0: return None
            
            t_er = sum(l["er"] for l in logs)
            #t_outs = sum(l["ip_outs"] for l in logs)
            t_so = sum(l["so"] for l in logs)
            t_bb = sum(l["bb"] for l in logs)
            t_win = sum(l["win"] for l in logs)
            
            #t_ip = t_outs / 3.0
            era = (t_er * 9) / t_ip if t_ip > 0 else 99.9
            k9 = (t_so * 9) / t_ip if t_ip > 0 else 0

            # 투수 조건 체크
            if t_win >= 3: return "PITCHER_HOT_WIN"
            if era <= 1.50: return "PITCHER_HOT_ERA"
            if k9 >= 11.0: return "PITCHER_HOT_K9"
            if t_bb >= 15: return "PITCHER_COLD_BB"
            if era >= 7.00: return "PITCHER_COLD_ERA"

        return res

    def expected_salary(self, season_stats):

        base = self.salary()
        mod = 0

        if self.is_pitcher():

            ip = season_stats.get("ip", 0)
            era = season_stats.get("era", 5)
            w = season_stats.get("w", 0)
            sv = season_stats.get("sv", 0)
            hld = season_stats.get("hld", 0)

            # 이닝
            if ip < 50:
                mod -= 0.05
            elif ip >= 120:
                mod += 0.05

            # ERA
            if era >= 5:
                mod -= 0.05
            elif era <= 3.5:
                mod += 0.05

            # 승리
            if w >= 12:
                mod += 0.05

            # 세이브
            if sv >= 15:
                mod += 0.05

            # 홀드
            if hld >= 10:
                mod += 0.05

        else:

            pa = season_stats.get("ab", 0)
            h = season_stats.get("h", 0)
            bb = season_stats.get("bb", 0)
            hr = season_stats.get("hr", 0)
            rbi = season_stats.get("rbi", 0)
            sb = season_stats.get("sb", 0)

            # OPS 계산
            ops = (h + bb) / max(pa,1)

            # 타석
            if pa < 200:
                mod -= 0.05
            elif pa >= 400:
                mod += 0.05

            # OPS
            if ops < 0.7:
                mod -= 0.05
            elif ops >= 0.9:
                mod += 0.05

            # 타점
            if rbi < 40:
                mod -= 0.05
            elif rbi >= 90:
                mod += 0.05

            # 홈런
            if hr >= 15:
                mod += 0.05

            # 도루
            if sb >= 15:
                mod += 0.05

        mod = max(-0.25, min(0.25, mod))

        return int(base * (1 + mod))