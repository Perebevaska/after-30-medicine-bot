import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import database as db
from api.auth import require_telegram_user, require_db_user, TelegramUser
from utils import get_tz_for_user, local_day_bounds_utc
from schedule_utils import _rule_fires_today
from datetime import datetime

router = APIRouter(prefix="/today", tags=["today"])


class IntakeIn(BaseModel):
    medication_id: int
    scheduled_time: str
    status: str   # "taken" | "skipped" | "pending" (undo)


def _build_today_items(rows, statuses, today, now_min, *, linked_user_id=None, linked_user_name=None):
    items = []
    for row in rows:
        if not _rule_fires_today(row, today):
            continue
        mid = row["medication_id"]
        t = row["reminder_time"]
        status = statuses.get((mid, t), "pending")
        try:
            rh, rm = t.split(":")
            is_due = now_min >= int(rh) * 60 + int(rm)
        except (ValueError, AttributeError):
            is_due = False
        item = {
            "medication_id": mid,
            "name": row["name"],
            "dosage": row.get("rule_dosage") or row["med_dosage"],
            "meal_relation": row["meal_relation"],
            "reminder_time": t,
            "status": status,
            "is_due": is_due,
            "dependent_name": row.get("dependent_name"),
        }
        if linked_user_id is not None:
            item["linked_user_id"] = linked_user_id
            item["linked_user_name"] = linked_user_name
        items.append(item)
    return items


@router.get("")
async def get_today(telegram_id: int = Depends(require_telegram_user)):
    user_tz = await asyncio.to_thread(get_tz_for_user, telegram_id)
    now_local = datetime.now(user_tz)
    start_utc, end_utc = local_day_bounds_utc(user_tz, now_local)
    statuses = await asyncio.to_thread(
        db.get_today_intake_statuses, telegram_id, start_utc, end_utc
    )
    rows = await asyncio.to_thread(db.get_schedules_for_user, telegram_id)
    today = now_local.date()
    now_min = now_local.hour * 60 + now_local.minute
    # AX5: is_due считаем по TZ пользователя на сервере
    items = _build_today_items(rows, statuses, today, now_min)
    # F7: append linked dependents' today (read-only for caregiver)
    linked = await asyncio.to_thread(db.get_linked_dependents_for_caregiver, telegram_id)
    for dep in linked:
        dep_tid = dep["telegram_id"]
        dep_tz = await asyncio.to_thread(get_tz_for_user, dep_tid)
        dep_local = datetime.now(dep_tz)
        dep_start, dep_end = local_day_bounds_utc(dep_tz, dep_local)
        dep_statuses = await asyncio.to_thread(
            db.get_today_intake_statuses, dep_tid, dep_start, dep_end
        )
        dep_rows = await asyncio.to_thread(db.get_schedules_for_user, dep_tid)
        dep_today = dep_local.date()
        dep_now_min = dep_local.hour * 60 + dep_local.minute
        dep_name = dep["username"] or f"id{dep_tid}"
        items.extend(_build_today_items(
            dep_rows, dep_statuses, dep_today, dep_now_min,
            linked_user_id=dep["user_id"], linked_user_name=dep_name,
        ))
    return sorted(items, key=lambda x: x["reminder_time"], reverse=True)


@router.post("/intake", status_code=204)
async def log_intake(body: IntakeIn, user: TelegramUser = Depends(require_db_user)):
    if not await asyncio.to_thread(db.get_medication_by_id, body.medication_id, user.user_id):
        raise HTTPException(404, "Лекарство не найдено")
    user_tz = await asyncio.to_thread(get_tz_for_user, user.telegram_id)
    now_local = datetime.now(user_tz)
    start_utc, end_utc = local_day_bounds_utc(user_tz, now_local)
    old_status = await asyncio.to_thread(
        db.log_intake, body.medication_id, body.scheduled_time,
        body.status, start_utc, end_utc,
    )
    await asyncio.to_thread(
        db.apply_intake_stock, body.medication_id, body.status, old_status
    )
    # G1: сердечки — +1 taken / −1 skipped (идемпотентно через old_status).
    await asyncio.to_thread(
        db.apply_intake_hearts, user.user_id, body.status, old_status
    )
