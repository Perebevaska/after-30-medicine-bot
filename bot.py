import os
import logging
import pytz
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, ContextTypes
)
from database import (init_db, migrate, get_or_create_user, add_medication, add_schedule,
                      get_user_medications, deactivate_medication, get_today_stats,
                      get_history, get_medication_by_id, get_schedules_by_medication,
                      update_medication, set_user_timezone, get_user_timezone)
from scheduler import send_reminders, handle_intake_callback

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TZ = pytz.timezone(os.getenv("TIMEZONE", "UTC"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния диалога добавления лекарства
NAME, DOSAGE, MEAL, TIMES, SCHEDULE = range(5)
# Состояния диалога редактирования
EDIT_NAME, EDIT_DOSAGE, EDIT_MEAL, EDIT_TIMES, EDIT_SCHEDULE = range(5, 10)

MEAL_LABELS = {
    "before": "Натощак (до еды)",
    "after": "После еды",
    "with": "Во время еды",
    "any": "Независимо от еды",
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
    user = update.effective_user
    get_or_create_user(user.id, user.username)
    tz = get_user_timezone(user.id)

    if tz == "UTC":
        from telegram import KeyboardButton, ReplyKeyboardMarkup
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📍 Отправить геолокацию", request_location=True)],
             [KeyboardButton("✍️ Ввести город вручную")]],
            resize_keyboard=True, one_time_keyboard=True
        )
        await update.message.reply_text(
            f"Привет, {user.first_name}! 💊\n\n"
            "Для точных напоминаний мне нужен твой часовой пояс.\n"
            "Отправь геолокацию или введи город:",
            reply_markup=keyboard
        )
        return SETUP_TZ

    await show_main_menu(update, user.first_name)
    return ConversationHandler.END


async def show_main_menu(update, first_name):
    from telegram import ReplyKeyboardRemove
    await update.message.reply_text(
        f"Привет, {first_name}! 💊\n\n"
        "Я помогу тебе не забывать принимать лекарства.\n\n"
        "Команды:\n"
        "/add — добавить лекарство\n"
        "/list — мои лекарства\n"
        "/edit — редактировать лекарство\n"
        "/delete — удалить лекарство\n"
        "/stats — статистика за сегодня\n"
        "/history — история за 7 дней\n"
        "/timezone — изменить часовой пояс\n",
        reply_markup=ReplyKeyboardRemove()
    )


async def handle_tz_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатие кнопки 'Ввести город' или любой текст в состоянии SETUP_TZ."""
    from telegram import ReplyKeyboardRemove
    await update.message.reply_text(
        "Введи название города (можно на русском):",
        reply_markup=ReplyKeyboardRemove()
    )
    return SETUP_CITY


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from timezonefinder import TimezoneFinder
    from telegram import ReplyKeyboardRemove
    loc = update.message.location
    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lat=loc.latitude, lng=loc.longitude)
    if tz_name:
        set_user_timezone(update.effective_user.id, tz_name)
        await update.message.reply_text(
            f"✅ Часовой пояс определён: *{tz_name}*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        await show_main_menu(update, update.effective_user.first_name)
    else:
        await update.message.reply_text("Не удалось определить часовой пояс. Введи город:")
        return SETUP_CITY
    return ConversationHandler.END


async def handle_city_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from geopy.geocoders import Nominatim
    from timezonefinder import TimezoneFinder
    from telegram import ReplyKeyboardRemove
    city = update.message.text.strip()
    geolocator = Nominatim(user_agent="med_bot")
    location = geolocator.geocode(city)
    if location:
        tf = TimezoneFinder()
        tz_name = tf.timezone_at(lat=location.latitude, lng=location.longitude)
        if tz_name:
            set_user_timezone(update.effective_user.id, tz_name)
            await update.message.reply_text(
                f"✅ Часовой пояс: *{tz_name}*",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            await show_main_menu(update, update.effective_user.first_name)
            return ConversationHandler.END
    await update.message.reply_text("Город не найден. Попробуй ещё раз (на английском):")
    return SETUP_CITY


async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Позволяет пользователю изменить часовой пояс."""
    from telegram import KeyboardButton, ReplyKeyboardMarkup
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Отправить геолокацию", request_location=True)],
         [KeyboardButton("✍️ Ввести город вручную")]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await update.message.reply_text(
        "Отправь геолокацию или введи город:",
        reply_markup=keyboard
    )
    return SETUP_TZ


CANCEL_TIP = "_(/cancel для отмены)_"
SETUP_TZ, SETUP_CITY = range(10, 12)


def get_tz_for_user(telegram_id: int) -> pytz.timezone:
    """Возвращает timezone объект для пользователя."""
    tz_name = get_user_timezone(telegram_id)
    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.utc


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Как называется лекарство?\n{CANCEL_TIP}",
        parse_mode="Markdown"
    )
    return NAME


async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text(
        f"Укажи дозировку (например: 500мг, 1 таблетка):\n{CANCEL_TIP}",
        parse_mode="Markdown"
    )
    return DOSAGE


async def add_dosage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["dosage"] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton(label, callback_data=key)]
        for key, label in MEAL_LABELS.items()
    ]
    await update.message.reply_text(
        f"Как принимать?\n{CANCEL_TIP}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return MEAL


async def add_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["meal"] = query.data
    keyboard = [
        [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(1, 5)]
    ]
    await query.edit_message_text(
        "Сколько раз в день?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TIMES


async def add_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    times = int(query.data)
    context.user_data["times"] = times
    context.user_data["collected_times"] = []
    await query.edit_message_text(
        f"Укажи время 1 из {times} приёмов (формат ЧЧ:ММ, например 08:00):\n{CANCEL_TIP}",
        parse_mode="Markdown"
    )
    return SCHEDULE


async def add_schedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text.strip()

    # Простая проверка формата
    try:
        h, m = map(int, time_str.split(":"))
        assert 0 <= h <= 23 and 0 <= m <= 59
    except Exception:
        await update.message.reply_text("Неверный формат. Введи время как ЧЧ:ММ, например 09:30:")
        return SCHEDULE

    context.user_data["collected_times"].append(time_str)
    collected = context.user_data["collected_times"]
    total = context.user_data["times"]

    if len(collected) < total:
        await update.message.reply_text(
            f"Время {len(collected)} из {total} принято. "
            f"Введи время {len(collected) + 1} из {total}:"
        )
        return SCHEDULE

    # Все времена собраны — сохраняем
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    med_id = add_medication(
        user_id,
        context.user_data["name"],
        context.user_data["dosage"],
        context.user_data["meal"],
        total
    )
    for t in collected:
        add_schedule(med_id, t)

    meal_label = MEAL_LABELS[context.user_data["meal"]]
    times_str = ", ".join(collected)
    await update.message.reply_text(
        f"✅ Лекарство добавлено!\n\n"
        f"💊 {context.user_data['name']} — {context.user_data['dosage']}\n"
        f"🍽 {meal_label}\n"
        f"⏰ Напоминания: {times_str}"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


async def delete_medication(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    meds = get_user_medications(user_id)

    if not meds:
        await update.message.reply_text("У тебя нет активных лекарств.")
        return

    keyboard = [
        [InlineKeyboardButton(
            f"❌ {med['name']} — {med['dosage']}",
            callback_data=f"delete:{med['id']}"
        )]
        for med in meds
    ]
    await update.message.reply_text(
        "Какое лекарство удалить?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    medication_id = int(query.data.split(":")[1])
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)

    deactivate_medication(medication_id, user_id)
    await query.edit_message_text("✅ Лекарство удалено из списка, напоминания отключены.")


async def stats_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    rows = get_today_stats(user_id)

    if not rows:
        await update.message.reply_text("За сегодня нет записей о приёмах.")
        return

    header = f"{'Время':<6} {'Лекарство':<22} Статус"
    divider = "-" * 36
    table_lines = [header, divider]
    for r in rows:
        status_text = "OK " if r["status"] == "taken" else "---"
        name = f"{r['name']} {r['dosage']}"[:22].ljust(22)
        t = r["taken_at"] or r["scheduled_time"]
        if len(t) > 10:
            # конвертируем UTC -> локальный часовой пояс
            from datetime import datetime
            user_tz = get_tz_for_user(update.effective_user.id)
            utc_dt = datetime.strptime(t, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.utc)
            local_dt = utc_dt.astimezone(user_tz)
            time = local_dt.strftime("%H:%M").ljust(6)
        else:
            time = (t if ":" in t else t + ":00").ljust(6)
        table_lines.append(f"{time} {name} {status_text}")

    await update.message.reply_text(
        f"📊 Статистика за сегодня\n\n```\n{chr(10).join(table_lines)}\n```",
        parse_mode="Markdown"
    )


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    rows = get_history(user_id, days=7)

    if not rows:
        await update.message.reply_text("За последние 7 дней нет данных.")
        return

    header = f"{'Лекарство':<20} {'Принято':>10} {'Пропущено':>10}"
    divider = "-" * len(header)
    table_lines = [header, divider]
    for r in rows:
        name = r["name"][:20].ljust(20)
        pct = int(r["taken"] / r["total"] * 100) if r["total"] else 0
        taken = f"{r['taken']}/{r['total']} ({pct}%)"
        table_lines.append(f"{name} {taken:>10} {r['skipped']:>10}")

    await update.message.reply_text(
        f"📈 История за 7 дней\n\n```\n{chr(10).join(table_lines)}\n```",
        parse_mode="Markdown"
    )


async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    meds = get_user_medications(user_id)

    if not meds:
        await update.message.reply_text("У тебя нет активных лекарств.")
        return

    keyboard = [
        [InlineKeyboardButton(
            f"✏️ {med['name']} — {med['dosage']}",
            callback_data=f"edit:{med['id']}"
        )]
        for med in meds
    ]
    await update.message.reply_text(
        "Какое лекарство редактировать?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    medication_id = int(query.data.split(":")[1])
    context.user_data["edit_id"] = medication_id

    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    med = get_medication_by_id(medication_id, user_id)
    schedules = get_schedules_by_medication(medication_id)
    times = ", ".join([s["reminder_time"] for s in schedules])

    await query.edit_message_text(
        f"Редактируем: *{med['name']}*\n"
        f"Дозировка: {med['dosage']}\n"
        f"Приём: {MEAL_LABELS[med['meal_relation']]}\n"
        f"Времена: {times}\n\n"
        f"Введи новое название (или напиши `-` чтобы оставить текущее `{med['name']}`):",
        parse_mode="Markdown"
    )
    return EDIT_NAME


async def edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    med = get_medication_by_id(context.user_data["edit_id"], user_id)
    val = update.message.text.strip()
    context.user_data["edit_name"] = med["name"] if val == "-" else val
    await update.message.reply_text(
        f"Введи новую дозировку (или `-` чтобы оставить `{med['dosage']}`):"
    )
    return EDIT_DOSAGE


async def edit_dosage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    med = get_medication_by_id(context.user_data["edit_id"], user_id)
    val = update.message.text.strip()
    context.user_data["edit_dosage"] = med["dosage"] if val == "-" else val
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"editmeal:{key}")]
        for key, label in MEAL_LABELS.items()
    ]
    await update.message.reply_text(
        "Выбери способ приёма:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return EDIT_MEAL


async def edit_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["edit_meal"] = query.data.split(":")[1]
    keyboard = [
        [InlineKeyboardButton(str(i), callback_data=f"edittimes:{i}") for i in range(1, 5)]
    ]
    await query.edit_message_text(
        "Сколько раз в день?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return EDIT_TIMES


async def edit_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    times = int(query.data.split(":")[1])
    context.user_data["edit_times"] = times
    context.user_data["edit_collected"] = []
    await query.edit_message_text(
        f"Введи время 1 из {times} (формат ЧЧ:ММ):"
    )
    return EDIT_SCHEDULE


async def edit_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text.strip()
    try:
        h, m = map(int, time_str.split(":"))
        assert 0 <= h <= 23 and 0 <= m <= 59
    except Exception:
        await update.message.reply_text("Неверный формат. Введи время как ЧЧ:ММ:")
        return EDIT_SCHEDULE

    context.user_data["edit_collected"].append(time_str)
    collected = context.user_data["edit_collected"]
    total = context.user_data["edit_times"]

    if len(collected) < total:
        await update.message.reply_text(
            f"Время {len(collected)} из {total} принято. Введи время {len(collected)+1}:"
        )
        return EDIT_SCHEDULE

    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    update_medication(
        context.user_data["edit_id"], user_id,
        context.user_data["edit_name"],
        context.user_data["edit_dosage"],
        context.user_data["edit_meal"],
        total, collected
    )
    await update.message.reply_text(
        f"✅ Лекарство обновлено!\n\n"
        f"💊 {context.user_data['edit_name']} — {context.user_data['edit_dosage']}\n"
        f"🍽 {MEAL_LABELS[context.user_data['edit_meal']]}\n"
        f"⏰ {', '.join(collected)}"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def list_medications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    meds = get_user_medications(user_id)

    if not meds:
        await update.message.reply_text("У тебя пока нет лекарств. Добавь через /add")
        return

    text = "💊 Твои лекарства:\n\n"
    for med in meds:
        times = med["times"] or "не указано"
        meal = MEAL_LABELS.get(med["meal_relation"], med["meal_relation"])
        text += (
            f"• {med['name']} — {med['dosage']}\n"
            f"  {meal}\n"
            f"  ⏰ {times}\n\n"
        )
    await update.message.reply_text(text)


def main():
    init_db()
    migrate()
    app = Application.builder().token(BOT_TOKEN).build()

    setup_tz_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("timezone", timezone_command),
        ],
        states={
            SETUP_TZ: [
                MessageHandler(filters.LOCATION, handle_location),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tz_text),
            ],
            SETUP_CITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_city_input),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            DOSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_dosage)],
            MEAL: [CallbackQueryHandler(add_meal)],
            TIMES: [CallbackQueryHandler(add_times)],
            SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_schedule_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(setup_tz_handler)
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("list", list_medications))
    edit_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_edit_select, pattern="^edit:\\d+$")],
        states={
            EDIT_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name)],
            EDIT_DOSAGE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_dosage)],
            EDIT_MEAL:     [CallbackQueryHandler(edit_meal, pattern="^editmeal:")],
            EDIT_TIMES:    [CallbackQueryHandler(edit_times, pattern="^edittimes:")],
            EDIT_SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_schedule)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("edit", edit_start))
    app.add_handler(edit_handler)
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("stats", stats_today))
    app.add_handler(CommandHandler("delete", delete_medication))
    app.add_handler(CallbackQueryHandler(handle_delete_callback, pattern="^delete:"))
    app.add_handler(CallbackQueryHandler(handle_intake_callback, pattern="^(taken|skipped):"))

    # Планировщик — проверка каждую минуту
    job_queue = app.job_queue
    job_queue.run_repeating(
        lambda ctx: send_reminders(app),
        interval=60,
        first=0
    )

    logger.info("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
