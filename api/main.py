"""FastAPI-приложение Med Bot API.

Запуск (из корня проекта):
    uvicorn api.main:app --reload

⚠️ APScheduler запускается только в bot.py — здесь не стартуем,
   иначе будут дубли напоминаний.
"""
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
import database as _db
from database import init_pool, close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    owned = _db._pool is None   # не закрывать пул, если он создан снаружи (тесты)
    init_pool()
    yield
    if owned:
        close_pool()


app = FastAPI(title="Med Bot API", version="1.0.0", lifespan=lifespan)

from api.routers import medications, today, stats, stock, dependents, settings, export

app.include_router(medications.router)
app.include_router(today.router)
app.include_router(stats.router)
app.include_router(stock.router)
app.include_router(dependents.router)
app.include_router(settings.router)
app.include_router(export.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
