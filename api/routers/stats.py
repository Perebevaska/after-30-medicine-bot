import asyncio
from datetime import datetime, timezone, timedelta, date
import pytz
from fastapi import APIRouter, Depends
import database as db
import analytics
from api.auth import require_db_user, TelegramUser
from schedule_utils import count_due_by_medication
from streak import streaks_by_subject, compute_streak
from utils import get_tz_for_user

router = APIRouter(prefix="/stats", tags=["stats"])

_ADHERENCE_DAYS = 30


def _adherence_window():
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=_ADHERENCE_DAYS)
    return (
        start.strftime("%Y-%m-%d %H:%M:%S"),
        end.strftime("%Y-%m-%d %H:%M:%S"),
    )


@router.get("/week")
async def stats_week(user: TelegramUser = Depends(require_db_user)):
    rows = await asyncio.to_thread(db.get_history_by_days, user.user_id, 7)
    return [dict(r) for r in rows]


@router.get("/adherence")
async def stats_adherence(user: TelegramUser = Depends(require_db_user)):
    start_utc, end_utc = _adherence_window()
    rules = await asyncio.to_thread(db.get_adherence_rules, user.user_id)
    taken = await asyncio.to_thread(db.get_taken_counts, user.user_id, start_utc, end_utc)
    if not rules:
        return {"medications": [], "total_pct": None}
    # count_due_by_medication агрегирует все правила лекарства → {mid: число положенных}
    due_map = count_due_by_medication(
        rules, date.fromisoformat(start_utc[:10]), date.fromisoformat(end_utc[:10])
    )
    # уникальные лекарства, метаданные берём из первого правила каждого mid
    meds_meta: dict[int, dict] = {}
    for rule in rules:
        meds_meta.setdefault(rule["medication_id"], rule)
    result = []
    total_due = total_taken = 0
    for mid, rule in meds_meta.items():
        due = due_map.get(mid, 0)
        t = taken.get(mid, 0)
        pct = round(t / due * 100) if due else 0
        total_due += due
        total_taken += t
        result.append({
            "medication_id": mid,
            "name": rule["name"],
            "dosage": rule["med_dosage"],
            "dependent_name": rule.get("dependent_name"),
            "due": due,
            "taken": t,
            "pct": pct,
        })
    total_pct = round(total_taken / total_due * 100) if total_due else None
    return {"medications": result, "total_pct": total_pct}


@router.get("/overview")
async def stats_overview(user: TelegramUser = Depends(require_db_user)):
    """F11-C (Фаза C-1): сводка по СОБСТВЕННОЙ терапии — серии (текущая+лучшая),
    соблюдение 7/30/90 + график по дням, пунктуальность отметок, нагрузка."""
    user_tz = await asyncio.to_thread(get_tz_for_user, user.telegram_id)
    today = datetime.now(user_tz).date()
    start_day = today - timedelta(days=89)
    start_local = user_tz.localize(datetime(start_day.year, start_day.month, start_day.day))
    end_local = user_tz.localize(datetime(today.year, today.month, today.day)) + timedelta(days=1)
    start_utc = start_local.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
    end_utc = end_local.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")

    rules = await asyncio.to_thread(db.get_streak_rows, user.user_id)
    own_rules = [r for r in rules if r["dependent_id"] is None]
    own_mids = {r["medication_id"] for r in own_rules}
    intakes_all = await asyncio.to_thread(
        db.get_intake_statuses_window, user.user_id, start_utc, end_utc
    )
    intakes = [i for i in intakes_all if i["medication_id"] in own_mids]
    units = await asyncio.to_thread(db.get_own_meds_units, user.user_id)

    # created_dates (локальная дата) по own-лекарствам — кламп знаменателя
    created: dict = {}
    for r in own_rules:
        mid = r["medication_id"]
        if mid in created:
            continue
        try:
            created[mid] = (datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S")
                            .replace(tzinfo=pytz.utc).astimezone(user_tz).date())
        except (ValueError, TypeError):
            created[mid] = None
    created = {m: d for m, d in created.items() if d}

    # status_by_day {date: {(mid, time): status}} + taken_by_day {date: count}
    status_by_day: dict = {}
    taken_by_day: dict = {}
    for i in intakes:
        try:
            d = (datetime.strptime(i["taken_at"], "%Y-%m-%d %H:%M:%S")
                 .replace(tzinfo=pytz.utc).astimezone(user_tz).date())
        except (ValueError, TypeError):
            continue
        status_by_day.setdefault(d, {})[(i["medication_id"], i["scheduled_time"])] = i["status"]
        if i["status"] == "taken":
            taken_by_day[d] = taken_by_day.get(d, 0) + 1

    cd = created or None
    daily = analytics.daily_adherence(own_rules, taken_by_day, created, start_day, today)
    return {
        "streak": {
            "current": compute_streak(own_rules, status_by_day, today, cd),
            "best": analytics.best_streak(own_rules, status_by_day, today, cd),
        },
        "adherence": {
            "windows": {
                "7": analytics.window_pct(daily, 7),
                "30": analytics.window_pct(daily, 30),
                "90": analytics.window_pct(daily, 90),
            },
            "weekly": analytics.weekly_adherence(daily),
        },
        "punctuality": analytics.punctuality(intakes, user_tz),
        "load": analytics.therapy_load(own_rules, units, today),
    }


@router.get("/hearts")
async def stats_hearts(user: TelegramUser = Depends(require_db_user)):
    """G1: счётчик сердечек пользователя."""
    hearts = await asyncio.to_thread(db.get_hearts, user.telegram_id)
    return {"hearts": hearts}


@router.get("/streak")
async def stats_streak(user: TelegramUser = Depends(require_db_user)):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=90)
    start_utc = start.strftime("%Y-%m-%d %H:%M:%S")
    end_utc = end.strftime("%Y-%m-%d %H:%M:%S")
    user_tz = await asyncio.to_thread(get_tz_for_user, user.telegram_id)
    rules = await asyncio.to_thread(db.get_streak_rows, user.user_id)
    intakes = await asyncio.to_thread(db.get_intake_statuses_window, user.user_id, start_utc, end_utc)
    return streaks_by_subject(rules, intakes, user_tz, end.date())
