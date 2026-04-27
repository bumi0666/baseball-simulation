import json

DEFAULT_SAVE = {
    "current_day": 0,
    "date": {
        "year": 2024,
        "month": 1,
        "day": 1
    }
}

def load_game(path="save.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            save = json.load(f)
    except FileNotFoundError:
        save = DEFAULT_SAVE.copy()

    current_day = save.get("current_day", 0)

    date = save.get("date", {})
    base_year  = date.get("year", 2024)
    base_month = date.get("month", 1)
    base_day   = date.get("day", 1)

    return {
        "current_day": current_day,
        "base_date": (base_year, base_month, base_day),
        "inbox": [],
        "money": 5000000,        # 현재 보유 금액 (예: 500만 달러)
        "budget": 10000000,      # 이번 시즌 총 예산
        "daily_expenses": 2000,  # 구단 운영비 (구장 관리, 스태프 급여 등)
        "finance_history": save.get("finance_history", [5000000])    # 재정 기록 (그래프나 리스트용)
    }


def save_game(current_day, base_date, path="save.json"):
    y, m, d = base_date
    save = {
        "current_day": current_day,
        "date": {
            "year": y,
            "month": m,
            "day": d
        }
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(save, f, indent=2)
