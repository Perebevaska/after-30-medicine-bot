"""FastAPI-приложение Med Bot API.

Запуск (из корня проекта):
    uvicorn api.main:app --reload

⚠️ APScheduler запускается только в bot.py — здесь не стартуем,
   иначе будут дубли напоминаний.
"""
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import database as _db
from database import init_pool, close_pool

# ── Rate limiting ────────────────────────────────────────────────────────────

_RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
_counters: dict[str, list[float]] = defaultdict(list)


class _RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        _counters[ip] = [t for t in _counters[ip] if now - t < 60.0]
        if len(_counters[ip]) >= _RATE_LIMIT:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
        _counters[ip].append(now)
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
async def health():
    return {"status": "ok"}
