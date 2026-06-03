"""A2 — валидация Telegram initData: валидный / просроченный / поддельный."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

BOT_TOKEN = "test-bot-token-1234567890"


def _make_init_data(
    telegram_id: int = 99001,
    auth_date: int | None = None,
    bot_token: str = BOT_TOKEN,
) -> str:
    """Генерирует корректный initData, подписанный bot_token."""
    if auth_date is None:
        auth_date = int(time.time())
    user = json.dumps({"id": telegram_id, "first_name": "Test"}, separators=(",", ":"))
    params = {
        "user": user,
        "auth_date": str(auth_date),
        "query_id": "AAHtest",
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(params)


def test_valid_init_data():
    from api.auth import verify_init_data
    init_data = _make_init_data(12345)
    telegram_id, username = verify_init_data(init_data, BOT_TOKEN)
    assert telegram_id == 12345


def test_expired_init_data():
    from api.auth import verify_init_data
    old = int(time.time()) - 90_000   # > 24 часов назад
    init_data = _make_init_data(12345, auth_date=old)
    with pytest.raises(ValueError, match="expired"):
        verify_init_data(init_data, BOT_TOKEN)


def test_tampered_hash():
    from api.auth import verify_init_data
    init_data = _make_init_data(12345, bot_token="wrong-token")
    with pytest.raises(ValueError, match="invalid hash"):
        verify_init_data(init_data, BOT_TOKEN)
