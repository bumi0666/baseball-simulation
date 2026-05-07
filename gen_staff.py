import json
import os
import random


TEAMS = [
    "Lions", "Tigers", "Bears", "Wizards", "Eagles",
    "Twins", "Landers", "Dinos", "Heroes", "Giants",
]

LAST_NAMES = [
    "Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon",
    "Smith", "Johnson", "Williams", "Brown", "Taylor", "Moore",
]

ROLE_ARCHETYPES = {
    "HD": [
        {
            "archetype": "conditioning_expert",
            "title": "Conditioning Expert",
            "effect_desc": "Training efficiency, fatigue control, rest recovery.",
            "effects": {},
            "traits": {
                "training_efficiency": 1,
                "game_fatigue_reduction": 1,
                "rest_fatigue_recovery": 1,
            },
        },
        {
            "archetype": "strategist",
            "title": "Strategist",
            "effect_desc": "Training efficiency, strategy success, substitution efficiency.",
            "effects": {},
            "traits": {
                "training_efficiency": 1,
                "strategy_success": 1,
                "pinch_hit_efficiency": 1,
                "defensive_sub_efficiency": 1,
            },
        },
        {
            "archetype": "developer",
            "title": "Developer",
            "effect_desc": "Training efficiency, young growth, veteran decline control.",
            "effects": {},
            "traits": {
                "training_efficiency": 1,
                "young_growth_boost": 1,
                "veteran_decline_slowdown": 1,
            },
        },
    ],
    "HC": [
        {
            "archetype": "hit_maker",
            "title": "Hit Maker",
            "effect_desc": "Contact ++ Eye ++",
            "effects": {"contact": 1, "eye": 1},
            "traits": {},
        },
        {
            "archetype": "slugger",
            "title": "Slugger",
            "effect_desc": "Power ++ Eye ++",
            "effects": {"power": 1, "eye": 1},
            "traits": {},
        },
        {
            "archetype": "small_ball",
            "title": "Small Ball",
            "effect_desc": "Contact ++ Run ++",
            "effects": {"contact": 1, "run": 1},
            "traits": {},
        },
    ],
    "PC": [
        {
            "archetype": "fireball",
            "title": "Doctor K",
            "effect_desc": "Velocity ++ Stuff ++",
            "effects": {"velocity": 1, "stuff": 1},
            "traits": {},
        },
        {
            "archetype": "finesse",
            "title": "Inning Eater",
            "effect_desc": "Control ++ Stuff ++",
            "effects": {"control": 1, "stuff": 1},
            "traits": {},
        },
        {
            "archetype": "manager",
            "title": "Iron Shield",
            "effect_desc": "Stamina ++ Control ++",
            "effects": {"stamina": 1, "control": 1},
            "traits": {},
        },
    ],
    "DC": [
        {
            "archetype": "defensive_specialist",
            "title": "Defensive Specialist",
            "effect_desc": "Defense ++",
            "effects": {"defense": 1},
            "traits": {},
        },
    ],
    "SC": [
        {
            "archetype": "talent_finder",
            "title": "Talent Finder",
            "effect_desc": "Scouting accuracy, hidden info, prospect discovery.",
            "effects": {},
            "traits": {
                "scouting_accuracy": 1,
                "hidden_info": 1,
                "prospect_discovery": 1,
            },
        },
    ],
    "DR": [
        {
            "archetype": "rehab_specialist",
            "title": "Rehab Specialist",
            "effect_desc": "Injury days reduction, injury risk reduction, surprise rehab.",
            "effects": {},
            "traits": {
                "injury_days_reduction": 1,
                "injury_risk_reduction": 1,
                "surprise_rehab": 1,
            },
        },
    ],
}


def calc_market_value(stars):
    base = random.randint(50000, 120000)
    return base * stars * random.randint(8, 14)


def calc_salary(stars):
    return random.randint(40000, 90000) * stars


def generate_staff_member(staff_id, team, role):
    template = random.choice(ROLE_ARCHETYPES[role])
    stars = random.choices([1, 2, 3, 4, 5], weights=[20, 30, 30, 15, 5])[0]
    salary = calc_salary(stars) if team != "FA" else 0

    return {
        "id": staff_id,
        "name": random.choice(LAST_NAMES),
        "role": role,
        "archetype": template["archetype"],
        "title": template["title"],
        "team": team,
        "stars": stars,
        "market_value": calc_market_value(stars),
        "effect_desc": template["effect_desc"],
        "effects": template["effects"],
        "traits": template["traits"],
        "bio": {
            "birth": f"{random.randint(1965, 1990)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "nationality": random.choice(["KOR", "USA", "JPN", "CAN", "DOM"]),
        },
        "contract": {
            "salary": salary,
            "begin": "2023-12-30" if team != "FA" else None,
            "end": "2024-12-30" if team != "FA" else None,
        },
        "status": {
            "roster": "active" if team != "FA" else "fa",
        },
    }


def run_generator():
    staff = []
    staff_id = 5001
    roles = ["HD", "HC", "PC", "DC", "SC", "DR"]

    for team in TEAMS:
        for role in roles:
            staff.append(generate_staff_member(staff_id, team, role))
            staff_id += 1

    for _ in range(200):
        role = random.choice(roles)
        staff.append(generate_staff_member(staff_id, "FA", role))
        staff_id += 1

    data = {
        "roles": roles,
        "staff": staff,
    }

    if not os.path.exists("staff"):
        os.makedirs("staff")

    with open(os.path.join("staff", "staff.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


if __name__ == "__main__":
    run_generator()
