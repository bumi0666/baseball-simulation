# models/staff.py

class Staff:
    def __init__(self, data_or_name, role=None, stars=None, effect_desc=None, effect_dict=None):
        if isinstance(data_or_name, dict):
            data = data_or_name
        else:
            data = {
                "id": None,
                "name": data_or_name,
                "role": role,
                "team": None,
                "stars": stars,
                "effect_desc": effect_desc,
                "effects": effect_dict or {},
                "traits": {},
                "contract": {},
                "status": {},
            }

        self.data = data
        self.id = data.get("id")
        self.name = data.get("name")
        self.role = data.get("role")
        self.team = data.get("team", "FA")
        self.archetype = data.get("archetype", "")
        self.title = data.get("title", "")
        self.stars = data.get("stars", 1)
        self.effect_desc = data.get("effect_desc", "")
        self.effects = data.get("effects", data.get("effect_dict", {}))
        self.effect_dict = self.effects
        self.traits = data.get("traits", {})
        self.bio = data.get("bio", {})
        self.contract = data.get("contract", {})
        self.status = data.get("status", {})
        self.market_value = data.get("market_value", 0)

    def salary(self):
        return self.contract.get("salary", 0)

    def age(self):
        """게임 안의 날짜 기준 나이 (생일 정보가 없으면 None)"""
        from datetime import date
        from models import player as _pm
        try:
            y, m, d = map(int, str(self.bio.get("birth", "")).split("-"))
        except ValueError:
            return None
        today = _pm._GAME_DATE or date.today()
        return today.year - y - ((today.month, today.day) < (m, d))

    def age_factor(self):
        """요구 연봉 배율: 경험이 쌓인 50세 전후가 가장 비싸고, 젊거나(경력 부족) 고령일수록 낮다 (0.8~1.08)"""
        age = self.age() or 50
        return max(0.8, min(1.08, 1.08 - 0.012 * abs(age - 50)))

    def contract_year_pref(self):
        """계약 1년 연장당 유효 오퍼 보정률: 55세 이상은 안정적인 장기 계약 선호(+), 38세 이하는 단기 선호(-)"""
        age = self.age() or 50
        if age >= 55:
            return 0.03
        if age <= 38:
            return -0.03
        return 0.0

    def demand_salary(self, fa=None):
        """요구 연봉: 현재 연봉과 시장가치(15%) 중 큰 값 × 별 배율 × 나이 배율 (FA는 10% 프리미엄)"""
        if fa is None:
            fa = self.is_free_agent()
        base = max(self.salary(), int(self.market_value * 0.15))
        stars = max(1, self.stars or 1)
        value = int(base * (0.75 + stars * 0.12) * self.age_factor())
        if fa:
            value = int(value * 1.10)
        return max(5000, value)

    def contract_begin(self):
        return self.contract.get("begin")

    def contract_end(self):
        return self.contract.get("end")

    def is_free_agent(self):
        return self.team == "FA" or self.status.get("roster") == "fa"

    def get_star_text(self):
        return "*" * self.stars + "-" * (5 - self.stars)

    def get_trait_bonus(self, trait_name):
        return int(self.stars * self.traits.get(trait_name, 0))

    def get_effect_bonus(self, attr_name):
        return int(self.stars * self.effects.get(attr_name, 0))

    def __repr__(self):
        return f"<Staff {self.role}: {self.name} ({self.stars} Stars)>"
