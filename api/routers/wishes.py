"""Ф15 v1 — соцмеханика пожеланий (тестовый функционал за тоглом wishes_enabled).

Приём поддержки анонимный: получатель не знает отправителя, отправитель не
знает получателя. Доставка — Mini App inbox (получатель видит всплывашку при
открытии). Только пресеты (нет UGC → не нужна модерация). v1 бесплатно.
"""
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
import database as db
import wish_presets
from api.auth import require_telegram_user, require_db_user, TelegramUser
from utils import get_tz_for_user

router = APIRouter(prefix="/wishes", tags=["wishes"])


class SendWishIn(BaseModel):
    preset_code: str

    @field_validator("preset_code")
    @classmethod
    def _v_code(cls, v):
        # Антифрод: только пресеты из каталога.
        if not wish_presets.is_valid_code(v):
            raise ValueError("неизвестный пресет")
        return v


class ReactWishIn(BaseModel):
    reaction: str

    @field_validator("reaction")
    @classmethod
    def _v_reaction(cls, v):
        if v not in ("helped", "supported"):
            raise ValueError("реакция должна быть helped или supported")
        return v


@router.get("/status")
async def wishes_status(telegram_id: int = Depends(require_telegram_user)):
    """Пресеты по времени суток + готовность пула + остаток дневного лимита."""
    enabled = await asyncio.to_thread(db.is_wishes_enabled, telegram_id)
    user_tz = await asyncio.to_thread(get_tz_for_user, telegram_id)
    hour = datetime.now(user_tz).hour
    pool = await asyncio.to_thread(db.count_wish_pool)
    user = await asyncio.to_thread(db.get_or_create_user, telegram_id)
    sent_today = await asyncio.to_thread(db.count_wishes_sent_today, user)
    acks = await asyncio.to_thread(db.get_wish_ack_summary, user)
    return {
        "enabled": enabled,
        "presets": wish_presets.presets_for_hour(hour),
        "pool_size": pool,
        "pool_ready": pool >= db.WISH_MIN_POOL,
        "sent_today": sent_today,
        "daily_limit": db.WISH_DAILY_LIMIT,
        "ack_helped": acks["helped"],
        "ack_supported": acks["supported"],
    }


@router.post("/send")
async def send_wish(body: SendWishIn, user: TelegramUser = Depends(require_db_user)):
    if not await asyncio.to_thread(db.is_wishes_enabled, user.telegram_id):
        raise HTTPException(403, "Поддержка незнакомцам выключена в настройках")
    pool = await asyncio.to_thread(db.count_wish_pool)
    if pool < db.WISH_MIN_POOL:
        raise HTTPException(400, "Пока мало участников — попробуйте позже")
    sent_today = await asyncio.to_thread(db.count_wishes_sent_today, user.user_id)
    if sent_today >= db.WISH_DAILY_LIMIT:
        raise HTTPException(400, "Лимит поддержки на сегодня исчерпан")
    recipient = await asyncio.to_thread(db.pick_wish_recipient, user.user_id)
    if recipient is None:
        raise HTTPException(400, "Пока некому передать поддержку — попробуйте позже")
    await asyncio.to_thread(db.create_wish, user.user_id, recipient, body.preset_code)
    return {"ok": True}


@router.get("/inbox")
async def wish_inbox(user: TelegramUser = Depends(require_db_user)):
    if not await asyncio.to_thread(db.is_wishes_enabled, user.telegram_id):
        return []
    rows = await asyncio.to_thread(db.get_wish_inbox, user.user_id)
    return [
        {
            "id": r["id"],
            "text": wish_presets.text_for_code(r["preset_code"]) or "Поддержка 🤍",
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.post("/{wish_id}/react", status_code=204)
async def react_wish(
    wish_id: int, body: ReactWishIn, user: TelegramUser = Depends(require_db_user)
):
    # Только фиксируем реакцию. Отправитель узнаёт об отклике in-app (карточка
    # «вашу поддержку оценили» в /wishes/status) и опц. дайджестом 1/день в TG
    # (scheduler, тогл wishes_tg_notify) — без мгновенного пуша на каждую реакцию.
    sender_id = await asyncio.to_thread(
        db.react_to_wish, wish_id, user.user_id, body.reaction
    )
    if sender_id is None:
        raise HTTPException(404, "Пожелание не найдено")
