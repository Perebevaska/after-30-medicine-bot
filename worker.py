"""ARQ worker: отправляет сообщения в Telegram из очереди Redis.

Запуск: arq worker.WorkerSettings
Системный сервис: medbot-worker.service
"""
import asyncio
import logging
import os

from arq.connections import RedisSettings
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import RetryAfter, TelegramError

logger = logging.getLogger(__name__)


async def send_reminder(ctx, *, chat_id: int, text: str, buttons: list | None = None):
    """Отправляет одно сообщение; при 429 ждёт и повторяет до 4 раз."""
    bot: Bot = ctx['bot']
    reply_markup = None
    if buttons:
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn['text'], callback_data=btn['callback_data']) for btn in row]
            for row in buttons
        ])
    for attempt in range(4):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='HTML',
                reply_markup=reply_markup,
            )
            return
        except RetryAfter as e:
            wait = e.retry_after + 1
            logger.warning("Telegram 429, ждём %ss (попытка %s)", wait, attempt + 1)
            await asyncio.sleep(wait)
        except TelegramError as e:
            logger.error("TelegramError chat_id=%s: %s", chat_id, e)
            return


class WorkerSettings:
    functions = [send_reminder]
    max_jobs = 25  # ≤25 одновременных → безопасно при лимите Telegram 30 msg/s
    # AX8: единый REDIS_URL вместо дефолтного localhost.
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379"))

    @staticmethod
    async def on_startup(ctx):
        ctx['bot'] = Bot(token=os.environ['BOT_TOKEN'])
        logger.info("ARQ worker запущен")

    @staticmethod
    async def on_shutdown(ctx):
        await ctx['bot'].close()
        logger.info("ARQ worker остановлен")
