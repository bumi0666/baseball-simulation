import json
import random, os


def generate_full_spec_player(p_id, team, pos, num):
    last_names = [
        "Cooper", "Taylor", "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
        "Miller", "Davis", "Rodriguez", "Martinez", "Wilson", "Robinson", "Harry", "Moore", "Evans", "Thomas"
    ]

    name = random.choice(last_names)

    if pos == "P":
        pot_vel = random.randint(85, 99)
        pot_con = random.randint(80, 99)
        pot_stu = random.randint(75, 99)
        pot_sta = random.randint(85, 99)
        pot_chk = random.randint(70, 99)
        attributes = {
            "velocity": {"cur": random.randint(70, pot_vel), "pot": pot_vel},
            "control": {"cur": random.randint(60, pot_con), "pot": pot_con},
            "stuff": {"cur": random.randint(55, pot_stu), "pot": pot_stu},
            "stamina": {"cur": random.randint(65, pot_sta), "pot": pot_sta},
            "defense": {"cur": random.randint(50, pot_chk), "pot": pot_chk},
        }
    else:
        pot_con = random.randint(80, 99)
        pot_pow = random.randint(75, 99)
        pot_eye = random.randint(75, 99)
        pot_run = random.randint(80, 99)
        pot_def = random.randint(70, 99)
        attributes = {
            "contact": {"cur": random.randint(60, pot_con), "pot": pot_con},
            "power": {"cur": random.randint(50, pot_pow), "pot": pot_pow},
            "eye": {"cur": random.randint(60, pot_eye), "pot": pot_eye},
            "run": {"cur": random.randint(60, pot_run), "pot": pot_run},
            "defense": {"cur": random.randint(55, pot_def), "pot": pot_def},
        }

    career = []
    for year in [2021, 2022, 2023]:
        if pos == "P":
            ip_val = random.randint(120, 200)
            ip_outs = ip_val * 3
            era_val = round(random.uniform(2.5, 6.0), 2)
            er_val = int((era_val * ip_val) / 9)
            whip_val = round(random.uniform(1.1, 1.5), 2)
            h_bb_total = int(whip_val * ip_val)
            h_allowed = random.randint(int(h_bb_total * 0.7), int(h_bb_total * 0.9))
            bb_allowed = h_bb_total - h_allowed

            stats = {
                "g": random.randint(20, 32),
                "gs": random.randint(20, 32),
                "w": random.randint(4, 20),
                "l": random.randint(4, 15),
                "sv": 0,
                "hld": 0,
                "ip": ip_val,
                "ip_outs": ip_outs,
                "h_allowed": h_allowed,
                "bb_allowed": bb_allowed,
                "er": er_val,
                "so": random.randint(100, 220),
                "hbp": random.randint(2, 10),
                "era": era_val,
                "whip": whip_val,
            }
        else:
            ab = random.randint(450, 600)
            h = random.randint(120, 180)
            hr = random.randint(5, 30)
            bb = random.randint(40, 80)
            doubles = random.randint(15, 45)
            triples = random.randint(1, 12)
            singles = max(0, h - doubles - triples - hr)
            doubles = h - singles - triples - hr

            pa = ab + bb
            tb = singles + 2 * doubles + 3 * triples + 4 * hr
            obp = round((h + bb) / pa, 3) if pa > 0 else 0.0
            slg = round(tb / ab, 3) if ab > 0 else 0.0
            ops = round(obp + slg, 3)

            stats = {
                "g": random.randint(120, 144),
                "ab": ab,
                "r": random.randint(40, 100),
                "h": h,
                "2b": doubles,
                "3b": triples,
                "hr": hr,
                "rbi": random.randint(50, 140),
                "bb": bb,
                "so": random.randint(60, 130),
                "sb": random.randint(0, 30),
                "obp": obp,
                "slg": slg,
                "ops": ops,
            }

        career.append({"season": year, "team": team, "stats": stats})

    return {
        "id": p_id,
        "name": name,
        "pos": pos,
        "team": team,
        "backnumber": num,
        "captain": False,
        "market_value": random.randint(100000000, 10000000000),
        "bio": {
            "birth": f"{random.randint(1985, 2005)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "height": random.randint(170, 195),
            "weight": random.randint(65, 105),
            "nationality": random.choice(["USA", "CAN", "DOM", "JPN", "KOR"]),
        },
        "contract": {
            "salary": random.randint(50000, 100000),
            "begin": "2023-12-30",
            "end": "2024-12-30",
        },
        "main_stats": {
            "handed_throw": random.choice(["R", "L"]),
            "handed_hit": random.choice(["R", "L"]),
        },
        "status": {
            "health": 1000,
            "condition": 100,
            "fatigue": 0,
            "is_injured": False,
            "injury_days": 0,
            "exp": 0,
            "maxexp": 10000,
            "level": 1,
            "roster": "active",
        },
        "attributes": attributes,
        "career": career,
    }


def generate_team_players(start_id, teams, positions):
    players = []
    p_id = start_id

    for team in teams:
        back_number = 1
        for pos in positions:
            count = 8 if pos == "P" else 2
            for _ in range(count):
                players.append(generate_full_spec_player(p_id, team, pos, back_number))
                p_id += 1
                back_number += 1

    return players, p_id


def generate_fa_players(start_id, count, positions):
    players = []
    p_id = start_id

    for idx in range(count):
        pos = random.choice(positions)
        player = generate_full_spec_player(p_id, "FA", pos, idx + 1)
        player["team"] = "FA"
        player["backnumber"] = None
        player["contract"] = {
            "salary": 0,
            "begin": None,
            "end": None,
        }
        player["status"]["roster"] = "fa"

        for season in player["career"]:
            season["team"] = "FA"

        players.append(player)
        p_id += 1

    return players, p_id


def run_generator():
    teams = [
        "Lions", "Tigers", "Bears", "Wizards", "Eagles",
        "Twins", "Landers", "Dinos", "Heroes", "Giants",
    ]
    positions = ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]

    team_players, next_id = generate_team_players(2001, teams, positions)
    fa_players, _ = generate_fa_players(next_id, 10000, positions)

    data = {
        "teams": teams,
        "players": team_players + fa_players,
    }

    if not os.path.exists("players"):
        os.makedirs("players")

    path = os.path.join("players", "players.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


if __name__ == "__main__":
    run_generator()