"""FastAPI-приложение Med Bot API.

Запуск (из корня проекта):
    uvicorn api.main:app --reload

⚠️ APScheduler запускается только в bot.py — здесь не стартуем,
   иначе будут дубли напоминаний.
"""
import asyncio
import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

import redis as _redis_lib
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import database as _db
from database import init_pool, close_pool, get_connection

logger = logging.getLogger("api")

# ── Rate limiting ────────────────────────────────────────────────────────────

_RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
# За обратным прокси (Caddy) реальный IP — в X-Forwarded-For. Включать только
# если прокси доверенный, иначе клиент может подделать заголовок.
_TRUST_PROXY = os.getenv("TRUST_PROXY", "").lower() in ("1", "true", "yes")
_counters: dict[str, list[float]] = defaultdict(list)
_sweep_counter = 0


def _client_ip(request: Request) -> str:
    if _TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class _RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        global _sweep_counter
        ip = _client_ip(request)
        now = time.time()
        hits = [t for t in _counters[ip] if now - t < 60.0]
        if len(hits) >= _RATE_LIMIT:
            _counters[ip] = hits
            return JSONResponse({"detail": "Притормози чуть-чуть — слишком много запросов сразу 🙂"}, status_code=429)
        hits.append(now)
        _counters[ip] = hits
        # S4: периодически чистим пустые/протухшие ключи, чтобы dict не рос
        # бесконечно по числу уникальных IP.
        _sweep_counter += 1
        if _sweep_counter % 1000 == 0:
            for k in [k for k, v in _counters.items()
                      if not v or all(now - t >= 60.0 for t in v)]:
                _counters.pop(k, None)
        return await call_next(request)


# ── App ──────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    owned = _db._pool is None   # не закрывать пул, если он создан снаружи (тесты)
    init_pool()
    yield
    if owned:
        close_pool()


app = FastAPI(title="Med Bot API", version="1.0.0", lifespan=lifespan)

# CORS: MINIAPP_ORIGIN через запятую, по умолчанию — все (только для dev)
_cors_origins = [o.strip() for o in os.getenv("MINIAPP_ORIGIN", "*").split(",")]
_allow_credentials = _cors_origins != ["*"]
if _cors_origins == ["*"]:
    # S5: fail-open по умолчанию — в проде обязательно задавать MINIAPP_ORIGIN.
    logger.warning(
        "CORS открыт для всех источников (MINIAPP_ORIGIN не задан). "
        "Для продакшена укажите конкретный домен Mini App."
    )

app.add_middleware(_RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Exception handlers ───────────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError):
    """Нормализует 422: detail всегда строка, а не список."""
    parts = []
    for e in exc.errors():
        loc = ".".join(str(l) for l in e["loc"] if l != "body")
        parts.append(f"{loc}: {e['msg']}" if loc else e["msg"])
    return JSONResponse({"detail": "; ".join(parts)}, status_code=422)

# ── Routers ──────────────────────────────────────────────────────────────────

from api.routers import medications, today, stats, stock, dependents, settings, export

app.include_router(medications.router)
app.include_router(today.router)
app.include_router(stats.router)
app.include_router(stock.router)
app.include_router(dependents.router)
app.include_router(settings.router)
app.include_router(export.router)


@app.get("/health")
async def health(response: Response):
    checks: dict[str, str] = {}

    def _db_check():
        with get_connection() as conn:
            conn.execute("SELECT 1")

    def _redis_check():
        _redis_lib.Redis().ping()

    try:
        await asyncio.to_thread(_db_check)
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"error: {e}"

    try:
        await asyncio.to_thread(_redis_check)
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    ok = all(v == "ok" for v in checks.values())
    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "degraded", **checks}
