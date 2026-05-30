import os
import logging
import warnings
import pytz
from telegram.warnings import PTBUserWarning
from collections import defaultdict, OrderedDict
from datetime import datetime
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup,
                      KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, ContextTypes
)
from database import (DatabaseError,
                      init_db, migrate, get_or_create_user, add_medication, add_schedule,
                      get_user_medications, deactivate_medication, get_today_stats,
                      get_history, get_history_by_days, get_history_detailed, get_medication_by_id,
                      get_schedules_by_medication, update_medication,
                      set_user_timezone, get_user_timezone,
                      get_reminder_mode, set_reminder_mode)
from scheduler import send_reminders, handle_intake_callback

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TZ = pytz.timezone(os.getenv("TIMEZONE", "UTC"))

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", category=PTBUserWarning)
logger = logging.getLogger(__name__)


def handle_db_errors(func):
    """Декоратор: ловит DatabaseError и отвечает пользователю."""
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


MEAL_LABELS = {
    "before": "Натощак (до еды)",
    "after": "После еды",
    "with": "Во время еды",
    "any": "Независимо от еды",
}

# Состояния диалогов
NAME, DOSAGE, MEAL, TIMES, SCHEDULE = range(5)
EDIT_NAME, EDIT_DOSAGE, EDIT_MEAL, EDIT_TIMES, EDIT_SCHEDULE = range(5, 10)
SETUP_TZ, SETUP_CITY = range(10, 12)
CANCEL_TIP = "_(/cancel для отмены)_"

MONTHS_GEN = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}
MONTHS_SHORT = ["янв","фев","мар","апр","мая","июн","июл","авг","сен","окт","ноя","дек"]


@handle_db_errors
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id, user.username)
    tz = get_user_timezone(user.id)

    if tz == "UTC":
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
    await update.message.reply_text(
        f"Привет, {first_name}! 💊\n\n"
        "Я помогу тебе не забывать принимать лекарства.\n\n"
        "Команды:\n"
        "/meds — мои лекарства\n"
        "/stats — статистика\n"
        "/settings — настройки\n"
        "/about — о проекте\n",
        reply_markup=ReplyKeyboardRemove()
    )


async def handle_tz_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатие кнопки 'Ввести город' — переходим к вводу города."""
    if update.message.text == "✍️ Ввести город вручную":
        await update.message.reply_text(
            "Введи название города (можно на русском):",
            reply_markup=ReplyKeyboardRemove()
        )
        return SETUP_CITY
    # Если пользователь сразу написал город — обрабатываем его
    return await handle_city_input(update, context)


@handle_db_errors
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location
    if loc is None:
        # Геолокация недоступна (Desktop) — предлагаем город
        await update.message.reply_text(
            "📍 Геолокация недоступна на этом устройстве.\n"
            "Введи название своего города:",
            reply_markup=ReplyKeyboardRemove()
        )
        return SETUP_CITY
    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lat=loc.latitude, lng=loc.longitude)
    if tz_name:
        set_user_timezone(update.effective_user.id, tz_name)
        await update.message.reply_text(
            f"✅ Часовой пояс определён: *{tz_name}*\n\nТеперь можешь пользоваться ботом! Используй /add чтобы добавить лекарство.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "Не удалось определить часовой пояс. Введи город:",
            reply_markup=ReplyKeyboardRemove()
        )
        return SETUP_CITY


@handle_db_errors
async def handle_city_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = update.message.text.strip()
    geolocator = Nominatim(user_agent="med_bot")
    location = geolocator.geocode(city)
    if location:
        tf = TimezoneFinder()
        tz_name = tf.timezone_at(lat=location.latitude, lng=location.longitude)
        if tz_name:
            set_user_timezone(update.effective_user.id, tz_name)
            await update.message.reply_text(
                f"✅ Часовой пояс: *{tz_name}*\n\nТеперь можешь пользоваться ботом! Используй /add чтобы добавить лекарство.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
    await update.message.reply_text("Город не найден. Попробуй ещё раз:")
    return SETUP_CITY


async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Позволяет пользователю изменить часовой пояс."""
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


def get_tz_for_user(telegram_id: int) -> pytz.timezone:
    """Возвращает timezone объект для пользователя."""
    tz_name = get_user_timezone(telegram_id)
    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.utc


@handle_db_errors
async def handle_add_med_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатие кнопки ➕ Добавить лекарство."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        f"Как называется лекарство?\n{CANCEL_TIP}",
        parse_mode="Markdown"
    )
    return NAME


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


@handle_db_errors
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


@handle_db_errors
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def handle_settings_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point для смены timezone из Settings — запускает ConversationHandler."""
    query = update.callback_query
    await query.answer()
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Отправить геолокацию", request_location=True)],
         [KeyboardButton("✍️ Ввести город вручную")]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await query.message.reply_text(
        "Отправь геолокацию или введи город:",
        reply_markup=keyboard
    )
    return SETUP_TZ


@handle_db_errors
async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(":")[1]
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


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *О проекте*\n\n"
        "Этот бот — вайб-кодинг проект: написан за один вечер в паре с AI (Claude).\n\n"
        "Код живой, рабочий, итерируем дальше 🚀\n\n"
        "📦 GitHub: [after-38-medicine-bot](https://github.com/Perebevaska/after-38-medicine-bot)",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


@handle_db_errors
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


@handle_db_errors
async def handle_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    medication_id = int(query.data.split(":")[1])
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)

    deactivate_medication(medication_id, user_id)
    await query.edit_message_text("✅ Лекарство удалено из списка, напоминания отключены.")


async def stats_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает кнопки выбора периода статистики."""
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📅 За сегодня", callback_data="stats:today"),
        InlineKeyboardButton("📈 За 7 дней", callback_data="stats:week"),
    ]])
    await update.message.reply_text("Выбери период:", reply_markup=keyboard)


@handle_db_errors
async def show_stats_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику за сегодня — Вариант В с итогом дня."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    rows = get_today_stats(user_id)

    if not rows:
        await query.edit_message_text("За сегодня нет записей о приёмах.")
        return

    user_tz = get_tz_for_user(user.id)
    now = datetime.now(user_tz)
    today_str = f"{now.day} {MONTHS_GEN[now.month]}"

    # Группируем по лекарству
    meds = OrderedDict()
    total_taken = 0
    total_all = 0

    for r in rows:
        key = f"{r['name']} {r['dosage']}"
        t = r["taken_at"] or r["scheduled_time"]
        if len(t) > 10:
            utc_dt = dt.strptime(t, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.utc)
            time_str = utc_dt.astimezone(user_tz).strftime("%H:%M")
        else:
            time_str = t if ":" in t else t + ":00"

        icon = "✅" if r["status"] == "taken" else "❌"
        if key not in meds:
            meds[key] = {"intakes": [], "taken": 0, "total": 0}
        meds[key]["intakes"].append(f"{time_str} {icon}")
        meds[key]["total"] += 1
        if r["status"] == "taken":
            meds[key]["taken"] += 1
            total_taken += 1
        total_all += 1

    blocks = [f"📊 <b>Сегодня, {today_str}</b>\n"]
    for med_name, data in meds.items():
        pct = int(data["taken"] / data["total"] * 100) if data["total"] else 0
        color = "🟢" if pct >= 80 else ("🟡" if pct >= 50 else "🔴")
        intakes_str = "  ".join(data["intakes"])
        blocks.append(f"💊 <b>{med_name}</b> — {pct}% {color}")
        blocks.append(f"{intakes_str}\n")

    day_pct = int(total_taken / total_all * 100) if total_all else 0
    day_color = "🟢" if day_pct >= 80 else ("🟡" if day_pct >= 50 else "🔴")
    blocks.append(f"──────────────────")
    blocks.append(f"<b>Итог дня: {total_taken}/{total_all} ({day_pct}%) {day_color}</b>")

    await query.edit_message_text(
        "\n".join(blocks),
        parse_mode="HTML"
    )


@handle_db_errors
async def show_stats_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает детальную статистику за 7 дней."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    rows = get_history_detailed(user_id, days=7)

    if not rows:
        await query.edit_message_text("За последние 7 дней нет данных.")
        return

    user_tz = get_tz_for_user(user.id)

    # Структура: { "Аспирин 500мг": { "29 мая": [("08:00", "taken"), ...] } }
    meds = OrderedDict()
    meds_totals = defaultdict(lambda: {"taken": 0, "total": 0})

    for r in rows:
        key = f"{r['name']} {r['dosage']}"
        d = datetime.strptime(r["day"], "%Y-%m-%d")
        day_str = f"{d.day} {MONTHS_SHORT[d.month-1]}"

        # Берём реальное время приёма из taken_at
        t = r["taken_at"] or r["scheduled_time"]
        if len(t) > 10:
            utc_dt = datetime.strptime(t, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.utc)
            time_str = utc_dt.astimezone(user_tz).strftime("%H:%M")
        else:
            time_str = t if ":" in t else t + ":00"

        icon = "✅" if r["status"] == "taken" else "❌"

        if key not in meds:
            meds[key] = OrderedDict()
        if day_str not in meds[key]:
            meds[key][day_str] = []
        meds[key][day_str].append(f"{time_str} {icon}")

        meds_totals[key]["total"] += 1
        if r["status"] == "taken":
            meds_totals[key]["taken"] += 1

    # Формируем HTML
    blocks = ["📈 <b>История за 7 дней</b>\n"]
    for med_name, days_dict in meds.items():
        taken = meds_totals[med_name]["taken"]
        total = meds_totals[med_name]["total"]
        pct = int(taken / total * 100) if total else 0
        color = "🟢" if pct >= 80 else ("🟡" if pct >= 50 else "🔴")

        blocks.append(f"💊 <b>{med_name}</b> — {pct}% {color}\n")
        for day_str, intakes in days_dict.items():
            intakes_str = "  ".join(intakes)
            blocks.append(f"{day_str}  {intakes_str}")
        blocks.append(f"\n<i>Итого: {taken}/{total} ({pct}%)</i>")
        blocks.append("──────────────────")

    await query.edit_message_text(
        "\n".join(blocks),
        parse_mode="HTML"
    )


@handle_db_errors
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


@handle_db_errors
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


@handle_db_errors
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


@handle_db_errors
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


@handle_db_errors
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


@handle_db_errors
async def meds_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    meds = get_user_medications(user_id)

    if not meds:
        await update.message.reply_text(
            "У тебя пока нет лекарств.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Добавить лекарство", callback_data="add_med")
            ]])
        )
        return

    await update.message.reply_text("💊 Твои лекарства:")
    for med in meds:
        times = med["times"] or "не указано"
        meal = MEAL_LABELS.get(med["meal_relation"], med["meal_relation"])
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✏️ Изменить", callback_data=f"edit:{med['id']}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{med['id']}"),
        ]])
        await update.message.reply_text(
            f"*{med['name']}* — {med['dosage']}\n"
            f"🍽 {meal}\n"
            f"⏰ {times}",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    await update.message.reply_text(
        "➕ Хочешь добавить ещё?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ Добавить лекарство", callback_data="add_med")
        ]])
    )


def main():
    init_db()
    migrate()
    app = Application.builder().token(BOT_TOKEN).build()

    setup_tz_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("timezone", timezone_command),
            CallbackQueryHandler(handle_settings_timezone, pattern="^settings:timezone$"),
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
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
    )

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
            CallbackQueryHandler(handle_add_med_callback, pattern="^add_med$"),
        ],
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
    app.add_handler(CommandHandler("meds", meds_command))
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

    app.add_handler(edit_handler)
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("stats", stats_today))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CallbackQueryHandler(show_stats_today, pattern="^stats:today$"))
    app.add_handler(CallbackQueryHandler(show_stats_week, pattern="^stats:week$"))
    app.add_handler(CallbackQueryHandler(handle_settings_callback, pattern="^settings:reminder$"))
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
