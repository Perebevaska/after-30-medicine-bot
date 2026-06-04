import asyncio
import os
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

import database as db
from api.auth import require_telegram_user

router = APIRouter(prefix="/dependent-shares", tags=["dependent-shares"])

_DEP_SHARE_CODE_RE = re.compile(
    r"^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$"
)


class JoinRequest(BaseModel):
    code: str = Field(min_length=14, max_length=14)

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not _DEP_SHARE_CODE_RE.match(v.upper()):
            raise ValueError("Неверный формат кода (ожидается XXXX-XXXX-XXXX)")
        return v.upper()


async def _bot_notify(chat_id: int, text: str, reply_markup: dict | None = None):
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
            )
    except Exception:
        pass


def _uname(username: str | None, fallback: str) -> str:
    """Отображаемое имя для уведомления: @username или запасной вариант."""
    return f"@{username}" if username else fallback


def _confirm_kb(share_id: int) -> dict:
    """Inline-клавиатура подтверждения шаринга близкого (callback ловит bot)."""
    return {"inline_keyboard": [[
        {"text": "✅ Подтвердить", "callback_data": f"depshare:confirm:{share_id}"},
        {"text": "❌ Отклонить", "callback_data": f"depshare:decline:{share_id}"},
    ]]}


@router.post("/{dep_id}/code", status_code=200)
async def get_or_create_share_code(dep_id: int, telegram_id: int = Depends(require_telegram_user)):
    try:
        code = await asyncio.to_thread(db.ensure_dep_share_code, dep_id, telegram_id)
    except db.DatabaseError as e:
        raise HTTPException(404, str(e))
    return {"share_code": code}


@router.post("/join", status_code=201)
async def join_dep_share(body: JoinRequest, telegram_id: int = Depends(require_telegram_user)):
    try:
        result = await asyncio.to_thread(db.request_dep_share, telegram_id, body.code)
    except db.DatabaseError as e:
        raise HTTPException(400, str(e))
    who = _uname(result.get("viewer_username"), "Кто-то")
    # B-1: await вместо create_task — задача fire-and-forget без ссылки могла быть
    # собрана GC до отправки. _bot_notify сам глушит сетевые ошибки (timeout 5с).
    await _bot_notify(
        result["owner_telegram_id"],
        f"🔗 {who} хочет помогать с «{result['dep_name']}».\n"
        f"Подтвердите или отклоните прямо здесь, либо в приложении.",
        reply_markup=_confirm_kb(result["share_id"]),
    )
    return {"ok": True}


@router.post("/{share_id}/confirm", status_code=200)
async def confirm_share(share_id: int, telegram_id: int = Depends(require_telegram_user)):
    try:
        result = await asyncio.to_thread(db.confirm_dep_share, share_id, telegram_id)
    except db.DatabaseError as e:
        raise HTTPException(400, str(e))
    if result.get("viewer_telegram_id"):
        await _bot_notify(
            result["viewer_telegram_id"],
            f"Доступ к «{result['dep_name']}» подтверждён. Откройте приложение."
        )
    return {"ok": True}


@router.post("/{share_id}/decline", status_code=200)
async def decline_share(share_id: int, telegram_id: int = Depends(require_telegram_user)):
    parties = await asyncio.to_thread(db.get_dep_share_parties, share_id)
    ok = await asyncio.to_thread(db.decline_dep_share, share_id, telegram_id)
    if not ok:
        raise HTTPException(404, "Запрос не найден")
    if parties and parties.get("viewer_telegram_id"):
        await _bot_notify(
            parties["viewer_telegram_id"],
            f"❌ Запрос на помощь с «{parties.get('dep_name', '')}» отклонён."
        )
    return {"ok": True}


@router.delete("/{share_id}", status_code=204)
async def revoke_share(share_id: int, telegram_id: int = Depends(require_telegram_user)):
    ok = await asyncio.to_thread(db.revoke_dep_share, share_id, telegram_id)
    if not ok:
        raise HTTPException(404, "Не найдено")


@router.delete("/{share_id}/leave", status_code=204)
async def leave_share(share_id: int, telegram_id: int = Depends(require_telegram_user)):
    ok = await asyncio.to_thread(db.leave_dep_share, share_id, telegram_id)
    if not ok:
        raise HTTPException(404, "Не найдено")
