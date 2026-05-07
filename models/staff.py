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
