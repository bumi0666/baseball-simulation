# models/staff.py

class Staff:
    def __init__(self, name, role, stars, effect_desc, effect_dict):
        self.name = name
        self.role = role        # "HD", "HC", "PC", "BC", "DC"
        self.stars = stars      # 1~5 정수
        self.effect_desc = effect_desc
        self.effect_dict = effect_dict

    def get_star_text(self):
        return "★" * self.stars + "☆" * (5 - self.stars)

    def __repr__(self):
        return f"<Staff {self.role}: {self.name} ({self.stars} Stars)>"