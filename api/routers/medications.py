import asyncio
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import database as db
from api.auth import require_telegram_user
from constants import MAX_MEDICATIONS_PER_USER

router = APIRouter(prefix="/medications", tags=["medications"])

_MealRelation = Literal["before", "after", "with", "any"]
_Frequency = Literal["daily", "interval", "weekdays", "monthly"]


class RuleIn(BaseModel):
    reminder_time: str
    frequency: _Frequency = "daily"
    interval_days: Optional[int] = None
    weekdays: Optional[str] = None
    month_day: Optional[int] = None
    anchor_date: Optional[str] = None
    dosage: Optional[str] = None


class MedicationIn(BaseModel):
    name: str
    dosage: str
    meal_relation: _MealRelation
    times_per_day: int
    dependent_id: Optional[int] = None
    rules: list[RuleIn]


class MedicationUpdate(BaseModel):
    name: str
    dosage: str
    meal_relation: _MealRelation
    times_per_day: int
    rules: list[RuleIn]


@router.get("")
async def list_medications(telegram_id: int = Depends(require_telegram_user)):
    user_id = await asyncio.to_thread(db.get_or_create_user, telegram_id)
    meds = await asyncio.to_thread(db.get_user_medications, user_id)
    rules = await asyncio.to_thread(db.get_rules_grouped_for_user, user_id)
    return [
        {**dict(m), "rules": [dict(r) for r in rules.get(m["id"], [])]}
        for m in meds
    ]


@router.post("", status_code=201)
async def create_medication(body: MedicationIn, telegram_id: int = Depends(require_telegram_user)):
    user_id = await asyncio.to_thread(db.get_or_create_user, telegram_id)
    # S2: dependent_id приходит от клиента — проверяем владельца, иначе лекарство
    # можно привязать к чужому подопечному.
    if body.dependent_id is not None:
        deps = await asyncio.to_thread(db.get_dependents, telegram_id)
        if body.dependent_id not in {d["id"] for d in deps}:
            raise HTTPException(404, "Подопечный не найден")
    count = await asyncio.to_thread(db.count_active_medications, user_id, body.dependent_id)
    if count >= MAX_MEDICATIONS_PER_USER:
        raise HTTPException(400, f"Лимит {MAX_MEDICATIONS_PER_USER} лекарств достигнут")
    med_id = await asyncio.to_thread(
        db.add_medication, user_id, body.name, body.dosage,
        body.meal_relation, body.times_per_day, body.dependent_id,
    )
    for rule in body.rules:
        await asyncio.to_thread(
            db.add_schedule_rule, med_id, rule.reminder_time, rule.frequency,
            rule.interval_days, rule.weekdays, rule.month_day,
            rule.anchor_date, rule.dosage,
        )
    return {"id": med_id}


@router.put("/{med_id}")
async def update_medication(
    med_id: int, body: MedicationUpdate,
    telegram_id: int = Depends(require_telegram_user),
):
    user_id = await asyncio.to_thread(db.get_or_create_user, telegram_id)
    if not await asyncio.to_thread(db.get_medication_by_id, med_id, user_id):
        raise HTTPException(404, "Лекарство не найдено")
    await asyncio.to_thread(
        db.update_medication, med_id, user_id,
        body.name, body.dosage, body.meal_relation, body.times_per_day,
        [r.model_dump() for r in body.rules],
    )
    return {"ok": True}


@router.delete("/{med_id}", status_code=204)
async def delete_medication(med_id: int, telegram_id: int = Depends(require_telegram_user)):
    user_id = await asyncio.to_thread(db.get_or_create_user, telegram_id)
    if not await asyncio.to_thread(db.get_medication_by_id, med_id, user_id):
        raise HTTPException(404, "Лекарство не найдено")
    await asyncio.to_thread(db.deactivate_medication, med_id, user_id)


@router.post("/{med_id}/pause", status_code=204)
async def pause_medication(med_id: int, telegram_id: int = Depends(require_telegram_user)):
    user_id = await asyncio.to_thread(db.get_or_create_user, telegram_id)
    if not await asyncio.to_thread(db.get_medication_by_id, med_id, user_id):
        raise HTTPException(404, "Лекарство не найдено")
    await asyncio.to_thread(db.set_medication_paused, med_id, user_id, True)


@router.post("/{med_id}/resume", status_code=204)
async def resume_medication(med_id: int, telegram_id: int = Depends(require_telegram_user)):
    user_id = await asyncio.to_thread(db.get_or_create_user, telegram_id)
    if not await asyncio.to_thread(db.get_medication_by_id, med_id, user_id):
        raise HTTPException(404, "Лекарство не найдено")
    await asyncio.to_thread(db.set_medication_paused, med_id, user_id, False)
