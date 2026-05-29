import os
import logging
from datetime import datetime
import pytz
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_all_schedules, log_intake

load_dotenv()
TZ = pytz.timezone(os.getenv("TIMEZONE", "UTC"))

logger = logging.getLogger(__name__)


async def send_reminders(app):
    """Проверяет расписание и отправляет напоминания."""
    now = datetime.now(TZ).strftime("%H:%M")
    schedules = get_all_schedules()

    for row in schedules:
        if row["reminder_time"] == now:
            telegram_id = row["telegram_id"]
            name = row["name"]
            dosage = row["dosage"]
            meal = row["meal_relation"]
            medication_id = row["medication_id"]

            meal_labels = {
                "before": "натощак (до еды)",
                "after": "после еды",
                "with": "во время еды",
                "any": "независимо от еды",
            }
            meal_text = meal_labels.get(meal, meal)

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Принял",
                        callback_data=f"taken:{medication_id}:{now}"
                    ),
                    InlineKeyboardButton(
                        "❌ Пропустить",
                        callback_data=f"skipped:{medication_id}:{now}"
                    ),
                ]
            ])

            try:
                await app.bot.send_message(
                    chat_id=telegram_id,
                    text=(
                        f"💊 Время принять лекарство!\n\n"
                        f"*{name}* — {dosage}\n"
                        f"🍽 Принимать {meal_text}"
                    ),
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                logger.info(f"Напоминание отправлено: {name} → {telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки напоминания: {e}")


async def handle_intake_callback(update, context):
    """Обрабатывает нажатие кнопки Принял/Пропустил."""
    query = update.callback_query
    await query.answer()

    data = query.data.split(":")
    status = data[0]        # taken / skipped
    medication_id = int(data[1])
    scheduled_time = data[2]

    log_intake(medication_id, scheduled_time, status)

    if status == "taken":
        await query.edit_message_text("✅ Отлично! Приём записан.")
    else:
        await query.edit_message_text("❌ Пропуск записан.")
