import pytz
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update
from database import get_user_timezone, DatabaseError


def get_tz_for_user(telegram_id: int) -> pytz.timezone:
    """Возвращает timezone объект для пользователя."""
    tz_name = get_user_timezone(telegram_id)
    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.utc


def handle_db_errors(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except DatabaseError:
            msg = update.message or (
                update.callback_query and update.callback_query.message
            )
            if msg:
                await msg.reply_text("⚠️ Ошибка базы данных. Попробуй позже.")
    return wrapper


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END
