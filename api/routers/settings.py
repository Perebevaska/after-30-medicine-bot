import asyncio
import pytz
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from timezonefinder import TimezoneFinder
import database as db
from api.auth import require_telegram_user

router = APIRouter(prefix="/settings", tags=["settings"])

_tf = TimezoneFinder()


class TimezoneIn(BaseModel):
    timezone: str


class LocationIn(BaseModel):
    lat: float
    lng: float


class ReminderModeIn(BaseModel):
    mode: str   # "once" | "repeat"


class PresetIn(BaseModel):
    time: str   # "HH:MM"


class DailyPlanIn(BaseModel):
    enabled: bool
    time: str | None = None


class CaregiverIn(BaseModel):
    enabled: bool


@router.get("")
async def get_settings(telegram_id: int = Depends(require_telegram_user)):
    row = await asyncio.to_thread(db.get_user_settings_row, telegram_id)
    if not row:
        return {}
    return dict(row)


@router.put("/timezone", status_code=204)
async def set_timezone(body: TimezoneIn, telegram_id: int = Depends(require_telegram_user)):
    try:
        pytz.timezone(body.timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        raise HTTPException(400, "Неизвестный часовой пояс")
    await asyncio.to_thread(db.set_user_timezone, telegram_id, body.timezone)


@router.put("/timezone/by-location", status_code=204)
async def set_timezone_by_location(body: LocationIn, telegram_id: int = Depends(require_telegram_user)):
    tz = await asyncio.to_thread(_tf.timezone_at, lat=body.lat, lng=body.lng)
    if not tz:
        raise HTTPException(400, "Не удалось определить часовой пояс по координатам")
    await asyncio.to_thread(db.set_user_timezone, telegram_id, tz)


@router.put("/reminder-mode", status_code=204)
async def set_reminder_mode(body: ReminderModeIn, telegram_id: int = Depends(require_telegram_user)):
    await asyncio.to_thread(db.set_reminder_mode, telegram_id, body.mode)


@router.put("/presets/{slot}", status_code=204)
async def set_preset(slot: str, body: PresetIn, telegram_id: int = Depends(require_telegram_user)):
    await asyncio.to_thread(db.set_user_time_preset, telegram_id, slot, body.time)


@router.put("/daily-plan", status_code=204)
async def set_daily_plan(body: DailyPlanIn, telegram_id: int = Depends(require_telegram_user)):
    await asyncio.to_thread(db.set_daily_plan_enabled, telegram_id, body.enabled)
    if body.time:
        await asyncio.to_thread(db.set_daily_plan_time, telegram_id, body.time)


@router.put("/caregiver", status_code=204)
async def set_caregiver(body: CaregiverIn, telegram_id: int = Depends(require_telegram_user)):
    await asyncio.to_thread(db.set_caregiver_mode, telegram_id, body.enabled)
