import json
import os


SAVE_VERSION = 1
DEFAULT_SAVE_PATH = "save.json"


def default_save_data():
    return {
        "schema_version": SAVE_VERSION,
        "current_day": 1,
        "base_date": (2024, 1, 1),
        "inbox": [],
        "money": 5000000,
        "finance_history": [5000000],
    }


def _obj_id(obj):
    return getattr(obj, "id", None) if obj is not None else None


def _player_data(player):
    data = dict(getattr(player, "data", {}))
    data["id"] = player.id
    data["name"] = player.name
    data["pos"] = player.pos
    data["team"] = player.team
    data["backnumber"] = player.backnumber
    data["bio"] = player.bio
    data["contract"] = player.contract
    data["main_stats"] = data.get("main_stats", {})
    data["status"] = player.status
    data["attributes"] = player.attr
    data["career"] = player.career
    data["awards"] = getattr(player, "awards", [])
    return data


def _staff_data(staff):
    data = dict(getattr(staff, "data", {}))
    data["id"] = staff.id
    data["name"] = staff.name
    data["role"] = staff.role
    data["team"] = staff.team
    data["archetype"] = staff.archetype
    data["title"] = staff.title
    data["stars"] = staff.stars
    data["effect_desc"] = staff.effect_desc
    data["effects"] = staff.effects
    data["traits"] = staff.traits
    data["bio"] = staff.bio
    data["contract"] = staff.contract
    data["status"] = staff.status
    data["market_value"] = staff.market_value
    return data


def _state_data(state):
    return {
        "user_team": state.user_team,
        "team_data": getattr(state, "team_data", {}),
        "match_history": getattr(state, "match_history", {}),
        "current_day": state.current_day,
        "base_date": list(state.base_date),
        "inbox": state.inbox,
        "money": state.money,
        "stadium_cap": state.stadium_cap,
        "ticket_price": state.ticket_price,
        "popularity": state.popularity,
        "monthly_income": state.monthly_income,
        "monthly_expense": state.monthly_expense,
        "transfer_budget": getattr(state, "transfer_budget", 0),
        "wage_budget": getattr(state, "wage_budget", 0),
        "current_wage": getattr(state, "current_wage", 0),
        "profit_history": state.profit_history,
        "finance_history": state.finance_history,
        "schedule": getattr(state, "schedule", {}),
        "master_schedule": getattr(state, "master_schedule", {}),
        "team_stats": getattr(state, "team_stats", {}),
        "postseason": getattr(state, "postseason", {}),
        "champion": getattr(state, "champion", None),
        "regular_season_ended": getattr(state, "regular_season_ended", False),
        "season_ended": getattr(state, "season_ended", False),
        "todaygamenotice": getattr(state, "todaygamenotice", False),
        "todaygamedone": getattr(state, "todaygamedone", False),
        "salary_paid_this_month": getattr(state, "salary_paid_this_month", False),
        "lineup_ids": {
            pos: _obj_id(player)
            for pos, player in getattr(state, "lineup", {}).items()
        },
        "batting_order_ids": [
            _obj_id(player)
            for player in getattr(state, "batting_order", [])
        ],
        "bullpen_ids": [
            _obj_id(player)
            for player in getattr(state, "bullpen", [])
        ],
        "staff_slot_ids": {
            role: _obj_id(staff)
            for role, staff in getattr(state, "staff_slots", {}).items()
        },
    }


def build_save_data(state, players, staff_members=None):
    staff_members = staff_members or getattr(state, "all_staff", [])
    data = _state_data(state)
    data.update({
        "schema_version": SAVE_VERSION,
        "players": [_player_data(player) for player in players],
        "staff": [_staff_data(staff) for staff in staff_members],
    })
    return data


def load_game(path=DEFAULT_SAVE_PATH):
    if not os.path.exists(path):
        return default_save_data()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return default_save_data()

    if "date" in data and "base_date" not in data:
        old_date = data.get("date", {})
        data["base_date"] = (
            old_date.get("year", 2024),
            old_date.get("month", 1),
            old_date.get("day", 1),
        )

    if isinstance(data.get("base_date"), list):
        data["base_date"] = tuple(data["base_date"])

    try:
        data["current_day"] = max(1, int(data.get("current_day", 1)))
    except (TypeError, ValueError):
        data["current_day"] = 1

    return data


def save_game(state, players=None, staff_members=None, path=DEFAULT_SAVE_PATH):
    if not hasattr(state, "current_day"):
        current_day = state
        base_date = players
        y, m, d = base_date
        data = {
            "schema_version": SAVE_VERSION,
            "current_day": current_day,
            "base_date": [y, m, d],
        }
    else:
        data = build_save_data(state, players or [], staff_members)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
