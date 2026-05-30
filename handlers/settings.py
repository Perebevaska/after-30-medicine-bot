from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from database import get_user_timezone, get_reminder_mode, set_reminder_mode
from utils import handle_db_errors


@handle_db_errors
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tz = get_user_timezone(user.id)
    mode = get_reminder_mode(user.id)
    mode_label = "🔔 Один раз" if mode == "once" else "🔁 Повторять каждые 5 минут"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌍 Изменить часовой пояс", callback_data="settings:timezone")],
        [InlineKeyboardButton(f"Напоминания: {mode_label}", callback_data="settings:reminder")],
    ])
    await update.message.reply_text(
        f"⚙️ *Настройки*\n\n"
        f"🌍 Часовой пояс: `{tz}`\n"
        f"🔔 Напоминания: {mode_label}",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@handle_db_errors
async def handle_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    mode = get_reminder_mode(user.id)
    new_mode = "repeat" if mode == "once" else "once"
    set_reminder_mode(user.id, new_mode)
    new_label = "🔁 Повторять каждые 5 минут" if new_mode == "repeat" else "🔔 Один раз"
    tz = get_user_timezone(user.id)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌍 Изменить часовой пояс", callback_data="settings:timezone")],
        [InlineKeyboardButton(f"Напоминания: {new_label}", callback_data="settings:reminder")],
    ])
    await query.edit_message_text(
        f"⚙️ *Настройки*\n\n"
        f"🌍 Часовой пояс: `{tz}`\n"
        f"🔔 Напоминания: {new_label}",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *О проекте*\n\n"
        "Этот бот — вайб-кодинг проект: написан за один вечер в паре с AI (Claude).\n\n"
        "Код живой, рабочий, итерируем дальше 🚀\n\n"
        "📦 GitHub: [after-38-medicine-bot](https://github.com/Perebevaska/after-38-medicine-bot)",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


def get_handler():
    return CallbackQueryHandler(handle_reminder_callback, pattern="^settings:reminder$")
