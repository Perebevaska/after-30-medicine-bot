"""Валидация Telegram Mini App initData (HMAC-SHA256).

Алгоритм: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

MAX_AGE = 86_400  # 24 часа


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def verify_init_data(init_data: str, bot_token: str, max_age: int = MAX_AGE) -> int:
    """Валидирует initData, возвращает telegram_id.

    Поднимает ValueError с описанием причины отказа.
    telegram_id извлекается только из проверенной подписи — не принимается от клиента напрямую.
    """
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = params.pop("hash", "")
    if not received_hash:
        raise ValueError("hash missing")

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = _secret_key(bot_token)
    expected_hash = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(received_hash, expected_hash):
        raise ValueError("invalid hash")

    auth_date = int(params.get("auth_date", 0))
    if time.time() - auth_date > max_age:
        raise ValueError("initData expired")

    user = json.loads(params.get("user", "{}"))
    telegram_id = user.get("id")
    if not telegram_id:
        raise ValueError("user.id missing")

    return int(telegram_id)


_bearer = HTTPBearer(scheme_name="Telegram Mini App")


async def require_telegram_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> int:
    """FastAPI dependency: проверяет initData, возвращает telegram_id.

    Клиент передаёт: Authorization: tma <url-encoded initData>
    """
    if credentials.scheme.lower() != "tma":
        raise HTTPException(status_code=401, detail="Expected scheme 'tma'")
    bot_token = os.environ.get("BOT_TOKEN", "")
    try:
        return verify_init_data(credentials.credentials, bot_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
