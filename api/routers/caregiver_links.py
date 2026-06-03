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


async def _notify_dependent(dependent_telegram_id: int):
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return
    text = (
        "👨‍👩‍👦 Вам поступил запрос на подключение опекуна.\n"
        "Откройте приложение, чтобы принять или отклонить."
    )
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": dependent_telegram_id, "text": text},
            )
    except Exception:
        pass


@router.get("")
async def get_links(telegram_id: int = Depends(require_telegram_user)):
    return await asyncio.to_thread(db.get_caregiver_links, telegram_id)


@router.post("", status_code=201)
async def create_link(body: LinkRequest, telegram_id: int = Depends(require_telegram_user)):
    try:
        result = await asyncio.to_thread(db.create_caregiver_link, telegram_id, body.code)
    except db.DatabaseError as e:
        raise HTTPException(400, str(e))
    await _notify_dependent(result["dependent_telegram_id"])
    return {"id": result["id"]}


@router.post("/{link_id}/confirm", status_code=204)
async def confirm_link(link_id: int, telegram_id: int = Depends(require_telegram_user)):
    ok = await asyncio.to_thread(db.confirm_caregiver_link, link_id, telegram_id)
    if not ok:
        raise HTTPException(404, "Запрос не найден или уже обработан")


@router.post("/{link_id}/decline", status_code=204)
async def decline_link(link_id: int, telegram_id: int = Depends(require_telegram_user)):
    ok = await asyncio.to_thread(db.decline_caregiver_link, link_id, telegram_id)
    if not ok:
        raise HTTPException(404, "Запрос не найден или уже обработан")


@router.delete("/{link_id}", status_code=204)
async def delete_link(link_id: int, telegram_id: int = Depends(require_telegram_user)):
    ok = await asyncio.to_thread(db.delete_caregiver_link, link_id, telegram_id)
    if not ok:
        raise HTTPException(403, "Только опекун может разорвать связь")
