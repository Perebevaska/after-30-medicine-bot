import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import database as db
from api.auth import require_telegram_user

router = APIRouter(prefix="/dependents", tags=["dependents"])


class DependentIn(BaseModel):
    name: str


@router.get("")
async def list_dependents(telegram_id: int = Depends(require_telegram_user)):
    return await asyncio.to_thread(db.get_dependents, telegram_id)


@router.post("", status_code=201)
async def create_dependent(body: DependentIn, telegram_id: int = Depends(require_telegram_user)):
    dep_id = await asyncio.to_thread(db.add_dependent, telegram_id, body.name)
    return {"id": dep_id}


@router.delete("/{dep_id}", status_code=204)
async def delete_dependent(dep_id: int, telegram_id: int = Depends(require_telegram_user)):
    med_ids = await asyncio.to_thread(db.delete_dependent, telegram_id, dep_id)
    if med_ids is None:
        raise HTTPException(404, "Подопечный не найден")
