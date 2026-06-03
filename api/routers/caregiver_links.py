import asyncio
import os
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

import database as db
from api.auth import require_telegram_user

router = APIRouter(prefix="/caregiver-links", tags=["caregiver-links"])

_CODE_RE = re.compile(r"^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$")


class LinkRequest(BaseModel):
    code: str = Field(min_length=9, max_length=9)

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not _CODE_RE.match(v.upper()):
            raise ValueError("Неверный формат кода (ожидается XXXX-XXXX)")
        return v.upper()


async def _bot_notify(chat_id: int, text: str):
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
    except Exception:
        pass


def _uname(username: str | None, fallback: str) -> str:
    """Отображаемое имя для уведомления: @username или запасной вариант."""
    return f"@{username}" if username else fallback


@router.get("")
async def get_links(telegram_id: int = Depends(require_telegram_user)):
    return await asyncio.to_thread(db.get_caregiver_links, telegram_id)


@router.post("", status_code=201)
async def create_link(body: LinkRequest, telegram_id: int = Depends(require_telegram_user)):
    # F7-3.5: подопечный не может одновременно быть опекуном
    if await asyncio.to_thread(db.is_active_dependent, telegram_id):
        raise HTTPException(403, "Близкий не может привязывать других близких")
    try:
        result = await asyncio.to_thread(db.create_caregiver_link, telegram_id, body.code)
    except db.DatabaseError as e:
        raise HTTPException(400, str(e))
    who = _uname(result.get("caregiver_username"), "Помощник")
    await _bot_notify(
        result["dependent_telegram_id"],
        f"👨‍👩‍👦 {who} хочет стать вашим помощником и видеть ваши приёмы.\n"
        "Откройте приложение, чтобы принять или отклонить.",
    )
    return {"id": result["id"]}


@router.post("/{link_id}/confirm", status_code=204)
async def confirm_link(link_id: int, telegram_id: int = Depends(require_telegram_user)):
    parties = await asyncio.to_thread(db.get_caregiver_link_parties, link_id)
    result = await asyncio.to_thread(db.confirm_caregiver_link, link_id, telegram_id)
    if result == "not_found":
        raise HTTPException(404, "Запрос не найден или уже обработан")
    if result == "limit":
        raise HTTPException(400, "Лимит близких достигнут (максимум 2)")
    if parties and parties.get("caregiver_telegram_id"):
        who = _uname(parties.get("dependent_username"), "Ваш близкий")
        await _bot_notify(
            parties["caregiver_telegram_id"],
            f"✅ {who} подтвердил связь. Теперь вы видите его приёмы в приложении.",
        )


@router.post("/{link_id}/decline", status_code=204)
async def decline_link(link_id: int, telegram_id: int = Depends(require_telegram_user)):
    parties = await asyncio.to_thread(db.get_caregiver_link_parties, link_id)
    ok = await asyncio.to_thread(db.decline_caregiver_link, link_id, telegram_id)
    if not ok:
        raise HTTPException(404, "Запрос не найден или уже обработан")
    if parties and parties.get("caregiver_telegram_id"):
        who = _uname(parties.get("dependent_username"), "Пользователь")
        await _bot_notify(
            parties["caregiver_telegram_id"],
            f"❌ {who} отклонил запрос на подключение помощника.",
        )


@router.post("/{link_id}/request-break", status_code=204)
async def request_break(link_id: int, telegram_id: int = Depends(require_telegram_user)):
    """Подопечный запрашивает разрыв связи. Опекун подтверждает через DELETE."""
    ok = await asyncio.to_thread(db.request_caregiver_link_break, link_id, telegram_id)
    if not ok:
        raise HTTPException(404, "Активная связь не найдена")
    # Notify caregiver
    parties = await asyncio.to_thread(db.get_caregiver_link_parties, link_id)
    if parties and parties.get("caregiver_telegram_id"):
        who = _uname(parties.get("dependent_username"), "Ваш близкий")
        await _bot_notify(
            parties["caregiver_telegram_id"],
            f"⚠️ {who} хочет отключиться. "
            "Откройте приложение → Настройки → Забота для подтверждения.",
        )


@router.delete("/{link_id}", status_code=204)
async def delete_link(link_id: int, telegram_id: int = Depends(require_telegram_user)):
    ok = await asyncio.to_thread(db.delete_caregiver_link, link_id, telegram_id)
    if not ok:
        raise HTTPException(403, "Только помощник может разорвать связь")
