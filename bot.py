import os
from dotenv import load_dotenv
load_dotenv()

import logging
import warnings
from telegram.error import TimedOut, NetworkError
from telegram.warnings import PTBUserWarning
from telegram import BotCommand, MenuButtonWebApp, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)
from database import init_pool, init_db, migrate, close_pool
from scheduler import send_reminders, handle_intake_callback, init_arq_pool
from handlers import timezone as tz_handler
from handlers import care_links
from utils import cancel
from constants import SETUP_TZ, SETUP_CITY

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("fontTools").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", category=PTBUserWarning)
logger = logging.getLogger(__name__)


async def post_init(app):
    await init_arq_pool()
    try:
        await app.bot.set_my_commands([
            BotCommand("menu", "🏠 Меню"),
        ])
        from handlers.timezone import MINIAPP_URL
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="📱 Приложение", web_app=WebAppInfo(url=MINIAPP_URL))
        )
    except Exception as e:
        logger.warning("Не удалось установить команды бота (транзиентно): %s", e)


async def error_handler(update, context):
    """Глобальный обработчик ошибок: игнорирует транзиентные сетевые ошибки Telegram."""
    if isinstance(context.error, (TimedOut, NetworkError)):
        logger.warning("Telegram network error (transient): %s", context.error)
        return
    logger.error("Unhandled error", exc_info=context.error)


def main():
    """Точка входа: инициализирует БД, регистрирует все handlers, запускает бота."""
    init_pool()
    init_db()
    migrate()
    # Увеличенные таймауты: дефолтные 5с часто срабатывают на нестабильной
    # сети (в т.ч. WSL) и дают telegram.error.TimedOut.
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .connect_timeout(20.0)
        .read_timeout(20.0)
        .write_timeout(20.0)
        .pool_timeout(20.0)
        .get_updates_read_timeout(42.0)
        .build()
    )

    cancel_handler = CommandHandler("cancel", cancel)

    setup_tz_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", tz_handler.start),
            CommandHandler("timezone", tz_handler.timezone_command),
        ],
        states={
            SETUP_TZ: [
                MessageHandler(filters.LOCATION, tz_handler.handle_location),
                MessageHandler(filters.TEXT & ~filters.COMMAND, tz_handler.handle_tz_text),
            ],
            SETUP_CITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, tz_handler.handle_city_input),
            ],
        },
        fallbacks=[cancel_handler],
    )

    # F10-D: бот = напоминания + быстрая отметка приёма + подтверждение связей «Забота».
    # Управление лекарствами/статистика/настройки/запас перенесены в Mini App.
    app.add_handler(setup_tz_handler)
    app.add_handler(CommandHandler("menu", tz_handler.menu_command))
    app.add_handler(CallbackQueryHandler(tz_handler.handle_menu_callback, pattern="^menu:"))
    app.add_handler(CallbackQueryHandler(handle_intake_callback, pattern="^(taken|skipped):"))
    for h in care_links.get_handlers():
        app.add_handler(h)
    app.add_error_handler(error_handler)

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
