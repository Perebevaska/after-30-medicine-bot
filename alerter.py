"""Алерты администратору через Telegram Bot API.

Использование:
    from alerter import send_admin_alert_sync   # синхронно (worker, startup)
    from alerter import send_admin_alert        # async (scheduler, bot)
"""
import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

# Порог последовательных ошибок scheduler перед алертом
SCHEDULER_ERROR_THRESHOLD = 3
_scheduler_consecutive_errors: int = 0


def send_admin_alert_sync(text: str) -> None:
    token = os.getenv("BOT_TOKEN", "")
    admin_id_str = os.getenv("ADMIN_ID", "")
    if not token or not admin_id_str:
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": int(admin_id_str), "text": text, "parse_mode": "HTML"},
            timeout=8,
        )
    except Exception as exc:
        logger.error("alerter send failed: %s", exc)


async def send_admin_alert(text: str) -> None:
    await asyncio.to_thread(send_admin_alert_sync, text)


def on_scheduler_error(exc: Exception) -> None:
    """Вызывать при каждом сбое send_reminders; шлёт алерт при ≥3 подряд."""
    global _scheduler_consecutive_errors
    _scheduler_consecutive_errors += 1
    logger.error("scheduler error #%d: %s", _scheduler_consecutive_errors, exc)
    if _scheduler_consecutive_errors == SCHEDULER_ERROR_THRESHOLD:
        send_admin_alert_sync(
            f"🚨 <b>Scheduler: {SCHEDULER_ERROR_THRESHOLD}+ ошибок подряд</b>\n"
            f"<code>{type(exc).__name__}: {exc}</code>"
        )


def on_scheduler_ok() -> None:
    """Вызывать при каждом успешном проходе; сбрасывает счётчик и шлёт recovery-алерт."""
    global _scheduler_consecutive_errors
    if _scheduler_consecutive_errors >= SCHEDULER_ERROR_THRESHOLD:
        send_admin_alert_sync("✅ <b>Scheduler восстановился</b>")
    _scheduler_consecutive_errors = 0
