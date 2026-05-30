from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from database import get_or_create_user, get_user_timezone, set_user_timezone
from constants import SETUP_TZ, SETUP_CITY
from utils import handle_db_errors


def _geo_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Отправить геолокацию", request_location=True)],
         [KeyboardButton("✍️ Ввести город вручную")]],
        resize_keyboard=True, one_time_keyboard=True
    )


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


@handle_db_errors
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id, user.username)
    tz = get_user_timezone(user.id)

    if tz == "UTC":
        await update.message.reply_text(
            f"Привет, {user.first_name}! 💊\n\n"
            "Для точных напоминаний мне нужен твой часовой пояс.\n"
            "Отправь геолокацию или введи город:",
            reply_markup=_geo_keyboard()
        )
        return SETUP_TZ

    await show_main_menu(update, user.first_name)
    return ConversationHandler.END


async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Отправь геолокацию или введи город:",
        reply_markup=_geo_keyboard()
    )
    return SETUP_TZ


async def handle_settings_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point для смены timezone из Settings."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "Отправь геолокацию или введи город:",
        reply_markup=_geo_keyboard()
    )
    return SETUP_TZ


async def handle_tz_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✍️ Ввести город вручную":
        await update.message.reply_text(
            "Введи название города (можно на русском):",
            reply_markup=ReplyKeyboardRemove()
        )
        return SETUP_CITY
    return await handle_city_input(update, context)


@handle_db_errors
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location
    if loc is None:
        await update.message.reply_text(
            "📍 Геолокация недоступна на этом устройстве.\nВведи название своего города:",
            reply_markup=ReplyKeyboardRemove()
        )
        return SETUP_CITY
    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lat=loc.latitude, lng=loc.longitude)
    if tz_name:
        set_user_timezone(update.effective_user.id, tz_name)
        await update.message.reply_text(
            f"✅ Часовой пояс определён: *{tz_name}*\n\nИспользуй /meds чтобы добавить лекарство.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "Не удалось определить часовой пояс. Введи город:",
        reply_markup=ReplyKeyboardRemove()
    )
    return SETUP_CITY


@handle_db_errors
async def handle_city_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = update.message.text.strip()
    try:
        geolocator = Nominatim(user_agent="med_bot")
        location = geolocator.geocode(city, timeout=10)
    except (GeocoderTimedOut, GeocoderServiceError):
        await update.message.reply_text("Сервис геолокации недоступен. Попробуй ещё раз:")
        return SETUP_CITY
    if location:
        tf = TimezoneFinder()
        tz_name = tf.timezone_at(lat=location.latitude, lng=location.longitude)
        if tz_name:
            set_user_timezone(update.effective_user.id, tz_name)
            await update.message.reply_text(
                f"✅ Часовой пояс: *{tz_name}*\n\nИспользуй /meds чтобы добавить лекарство.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
    await update.message.reply_text("Город не найден. Попробуй ещё раз:")
    return SETUP_CITY
