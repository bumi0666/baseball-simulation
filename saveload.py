import json
import os
import re
from datetime import datetime, date, timedelta


SAVE_VERSION = 1
DEFAULT_SAVE_PATH = "save.json"
SAVE_DIR = "saves"


def _slot_num(slot):
    try:
        return max(1, int(slot))
    except (TypeError, ValueError):
        return 1


def slot_path(slot):
    """저장 슬롯 번호(1 이상, 개수 제한 없음) -> 파일 경로"""
    return os.path.join(SAVE_DIR, f"slot_{_slot_num(slot)}.json")


def meta_path(slot):
    """목록 표시용 요약 파일 (저장 파일이 수십 MB라 목록을 만들 때마다 통째로 읽지 않기 위함)"""
    return os.path.join(SAVE_DIR, f"slot_{_slot_num(slot)}.meta.json")


def existing_slots():
    """저장 파일이 있는 슬롯 번호(오름차순)"""
    try:
        names = os.listdir(SAVE_DIR)
    except OSError:
        return []
    nums = [int(m.group(1)) for n in names for m in [re.fullmatch(r"slot_(\d+)\.json", n)] if m]
    return sorted(nums)


def new_slot_number():
    """비어 있는 다음 슬롯 번호 (가장 큰 번호 + 1)"""
    nums = existing_slots()
    return (nums[-1] + 1) if nums else 1


def delete_slot(slot):
    """슬롯의 저장 파일과 요약 파일을 지운다. 지웠으면 True"""
    removed = False
    for path in (slot_path(slot), meta_path(slot)):
        try:
            os.remove(path)
            removed = removed or path == slot_path(slot)
        except OSError:
            pass
    return removed


def default_save_data():
    return {
        "schema_version": SAVE_VERSION,
        "active_save_slot": new_slot_number(),   # 새 게임은 기존 슬롯을 덮어쓰지 않도록 빈 번호에 저장된다
        "current_day": 1,
        "base_date": (2023, 11, 20),   # 첫 드래프트(11월)로 시작해 다음 해 3월에 시즌 개막
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
        "active_save_slot": getattr(state, "active_save_slot", 1),
        "team_data": getattr(state, "team_data", {}),
        "match_history": getattr(state, "match_history", {}),
        "current_day": state.current_day,
        "base_date": list(state.base_date),
        "inbox": state.inbox,
        "transactions": getattr(state, "transactions", []),
        "team_profiles": getattr(state, "team_profiles", {}),
        "draft": getattr(state, "draft", None),
        "season_history": getattr(state, "season_history", []),
        "season_ended_year": getattr(state, "season_ended_year", None),
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
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "players": [_player_data(player) for player in players],
        "staff": [_staff_data(staff) for staff in staff_members],
    })
    return data


def get_save_path(slot=None, path=None):
    if path is not None:
        return path
    if slot is not None:
        return slot_path(slot)
    return DEFAULT_SAVE_PATH


def summarize_save(data, slot):
    base_date = data.get("base_date", (2024, 1, 1))
    if isinstance(base_date, list):
        base_date = tuple(base_date)
    day = data.get("current_day", 1)
    try:
        game_date = (date(*base_date) + timedelta(days=int(day) - 1)).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        game_date = ""
    return {
        "slot": slot,
        "exists": True,
        "user_team": data.get("user_team", "Lions"),
        "current_day": day,
        "base_date": base_date,
        "game_date": game_date,
        "saved_at": data.get("saved_at", ""),
    }


def _write_meta(data, slot):
    try:
        info = summarize_save(data, slot)
        info["base_date"] = list(info["base_date"])
        with open(meta_path(slot), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False)
    except OSError:
        pass


def list_save_slots():
    """존재하는 모든 저장 슬롯의 요약(번호 오름차순). 요약 파일이 없거나 오래됐으면 저장 파일을 한 번 읽어 만든다."""
    slots = []
    for slot in existing_slots():
        path, mpath = slot_path(slot), meta_path(slot)
        info = None
        try:
            if os.path.exists(mpath) and os.path.getmtime(mpath) >= os.path.getmtime(path):
                with open(mpath, "r", encoding="utf-8") as f:
                    info = json.load(f)
                info["base_date"] = tuple(info.get("base_date", (2024, 1, 1)))
        except (OSError, ValueError):
            info = None
        if info is None:
            data = load_game(slot=slot)
            info = summarize_save(data, slot)
            _write_meta(data, slot)
        try:
            info["size_mb"] = os.path.getsize(path) / (1024 * 1024)
        except OSError:
            info["size_mb"] = 0.0
        slots.append(info)
    return slots


def load_game(path=None, slot=None):
    path = get_save_path(slot=slot, path=path)
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

    if slot is not None:
        data["active_save_slot"] = slot

    return data


def save_game(state, players=None, staff_members=None, path=None, slot=None):
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
        if slot is not None:
            state.active_save_slot = slot
        data = build_save_data(state, players or [], staff_members)

    path = get_save_path(slot=slot, path=path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"                      # 임시 파일에 먼저 쓰고 교체: 디스크가 부족해도 기존 저장이 깨지지 않는다
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    if slot is not None:
        _write_meta(data, slot)
