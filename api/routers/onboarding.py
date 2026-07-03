import asyncio
from fastapi import APIRouter, Depends
import database as db
from api.auth import require_db_user, TelegramUser

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/demo")
async def create_demo(user: TelegramUser = Depends(require_db_user)):
    """Создаёт демо-препарат «Счастьепин» новому юзеру для онбординг-тура.
    Идемпотентно: если у юзера уже есть лекарства — ничего не создаёт."""
    med_id = await asyncio.to_thread(db.create_demo_medication, user.user_id)
    return {"created": med_id is not None, "medication_id": med_id}
