"""ARQ worker: отправляет сообщения в Telegram из очереди Redis.

Запуск: arq worker.WorkerSettings
Системный сервис: medbot-worker.service
"""
import asyncio
import json
import logging
import os

import redis.asyncio as aioredis
from arq.connections import RedisSettings
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest, RetryAfter, TelegramError

logger = logging.getLogger(__name__)

# Ключ хранит (chat_id, message_id, text) последнего напоминания по слоту, чтобы
# отметка через Mini App могла отредактировать TG-сообщение (убрать кнопки +
# дописать статус). TTL > окна repeat (макс. 12ч), берём 13ч.
_REMINDER_MSG_TTL = 13 * 3600


def reminder_msg_key(track_key: str) -> str:
    return f"rmd:{track_key}"


async def send_reminder(ctx, *, chat_id: int, text: str, buttons: list | None = None,
                        track_key: str | None = None):
    """Отправляет одно сообщение; при 429 ждёт и повторяет до 4 раз.

    track_key (med_id:HH:MM:YYYY-MM-DD) → сохраняем message_id в Redis для
    последующего edit при отметке приёма через приложение.
    """
    bot: Bot = ctx['bot']
    reply_markup = None
    if buttons:
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn['text'], callback_data=btn['callback_data']) for btn in row]
            for row in buttons
        ])
    for attempt in range(4):
        try:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='HTML',
                reply_markup=reply_markup,
            )
            if track_key and reply_markup is not None:
                try:
                    await ctx['redis'].set(
                        reminder_msg_key(track_key),
                        json.dumps({"chat_id": chat_id, "message_id": msg.message_id, "text": text}),
                        ex=_REMINDER_MSG_TTL,
                    )
                except Exception as e:
                    logger.warning("reminder track store error: %s", e)
            return
        except RetryAfter as e:
            wait = e.retry_after + 1
            logger.warning("Telegram 429, ждём %ss (попытка %s)", wait, attempt + 1)
            await asyncio.sleep(wait)
        except TelegramError as e:
            logger.error("TelegramError chat_id=%s: %s", chat_id, e)
            return


async def edit_reminder(ctx, *, chat_id: int, message_id: int, text: str):
    """Редактирует TG-сообщение напоминания (убирает кнопки, дописывает статус).

    Вызывается из API после отметки приёма в Mini App — чтобы в чате не осталось
    активных кнопок ✓/✕ для уже отмеченного приёма.
    """
    bot: Bot = ctx['bot']
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, parse_mode='HTML',
        )
    except BadRequest as e:
        # message not found / not modified — сообщение удалено или уже отредактировано
        logger.info("edit_reminder skip chat_id=%s mid=%s: %s", chat_id, message_id, e)
    except TelegramError as e:
        logger.error("edit_reminder error chat_id=%s: %s", chat_id, e)


class WorkerSettings:
    functions = [send_reminder, edit_reminder]
    max_jobs = 25  # ≤25 одновременных → безопасно при лимите Telegram 30 msg/s
    # AX8: единый REDIS_URL вместо дефолтного localhost.
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379"))

    @staticmethod
    async def on_startup(ctx):
        try:
            ctx['bot'] = Bot(token=os.environ['BOT_TOKEN'])
            ctx['redis'] = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
            logger.info("ARQ worker запущен")
        except Exception as exc:
            logger.critical("ARQ worker startup failed: %s", exc)
            from alerter import send_admin_alert_sync
            send_admin_alert_sync(
                f"🚨 <b>ARQ Worker: ошибка запуска</b>\n"
                f"<code>{type(exc).__name__}: {exc}</code>"
            )
            raise

    @staticmethod
    async def on_shutdown(ctx):
        await ctx['bot'].close()
        try:
            await ctx['redis'].aclose()
        except Exception:
            pass
        logger.info("ARQ worker остановлен")
