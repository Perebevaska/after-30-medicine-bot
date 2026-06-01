import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from api.auth import require_telegram_user
from handlers.export import (
    build_plan_pdf, build_week_stats_pdf,
    build_adherence_pdf, build_doctor_pdf,
)

router = APIRouter(prefix="/export", tags=["export"])


def _stream(buf, filename: str):
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/plan")
async def export_plan(telegram_id: int = Depends(require_telegram_user)):
    buf = await asyncio.to_thread(build_plan_pdf, telegram_id)
    if not buf:
        raise HTTPException(404, "Нет данных для экспорта")
    return _stream(buf, "plan_week.pdf")


@router.get("/week")
async def export_week(telegram_id: int = Depends(require_telegram_user)):
    buf = await asyncio.to_thread(build_week_stats_pdf, telegram_id)
    if not buf:
        raise HTTPException(404, "Нет данных за последние 7 дней")
    return _stream(buf, "history_week.pdf")


@router.get("/adherence")
async def export_adherence_pdf(telegram_id: int = Depends(require_telegram_user)):
    buf = await asyncio.to_thread(build_adherence_pdf, telegram_id)
    if not buf:
        raise HTTPException(404, "Нет активных лекарств")
    return _stream(buf, "adherence.pdf")


@router.get("/doctor")
async def export_doctor(telegram_id: int = Depends(require_telegram_user)):
    buf = await asyncio.to_thread(build_doctor_pdf, telegram_id, f"user_{telegram_id}")
    if not buf:
        raise HTTPException(404, "Нет данных для отчёта")
    return _stream(buf, "doctor_report.pdf")
