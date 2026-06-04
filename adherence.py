"""Чистый расчёт соблюдения режима (adherence): окно периода + проценты по лекарствам.

Извлечено из handlers/stats.py (F10-D). Потребитель — reports.py (PDF-отчёты).
Без telegram/IO: только даты и арифметика.
"""
from datetime import datetime, timedelta
import pytz

from schedule_utils import count_due_by_medication

_ADHERENCE_DAYS = 30


def adherence_window(user_tz):
    """Окно расчёта: (today_local, start_day_local, start_utc, end_utc) за _ADHERENCE_DAYS дней."""
    today = datetime.now(user_tz).date()
    start_day = today - timedelta(days=_ADHERENCE_DAYS - 1)
    start_local = user_tz.localize(datetime(start_day.year, start_day.month, start_day.day))
    end_local = user_tz.localize(datetime(today.year, today.month, today.day)) + timedelta(days=1)
    start_utc = start_local.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
    end_utc = end_local.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
    return today, start_day, start_utc, end_utc


def compute_adherence(rules, taken: dict, start_day, today, user_tz):
    """Считает соблюдение по лекарствам. Возвращает (items, total_taken, total_planned).

    items — список dict {pct, taken, due, name, dep, mid}, отсортирован «худшие сверху».
    name/dep — сырые (без экранирования): рендер сам экранирует под HTML/PDF.
    Знаменатель — положенные приёмы по расписанию с клампом по created_at каждого лекарства.
    """
    meta: dict = {}
    created_dates: dict = {}
    for r in rules:
        mid = r["medication_id"]
        if mid in meta:
            continue
        try:
            cd = (datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S")
                  .replace(tzinfo=pytz.utc).astimezone(user_tz).date())
        except (ValueError, TypeError):
            cd = start_day
        created_dates[mid] = cd
        meta[mid] = {"name": r["name"], "dep": r["dependent_name"]}

    planned = count_due_by_medication(rules, start_day, today, created_dates)
    items = []
    total_taken = 0
    total_planned = 0
    for mid, due in planned.items():
        if due <= 0:
            continue
        tk = taken.get(mid, 0)
        pct = min(100, round(tk / due * 100))
        total_taken += min(tk, due)
        total_planned += due
        items.append({"pct": pct, "taken": tk, "due": due,
                      "name": meta[mid]["name"], "dep": meta[mid]["dep"], "mid": mid})
    items.sort(key=lambda x: (x["pct"], x["mid"]))  # худшие сверху
    return items, total_taken, total_planned
