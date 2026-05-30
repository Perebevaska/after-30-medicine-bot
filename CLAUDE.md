# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About
Telegram бот для напоминаний о приёме лекарств с поддержкой расписания, статистики и определения часовых поясов.

## Stack
- **Language**: Python 3.14
- **Framework**: python-telegram-bot 22.7 (async API)
- **Scheduler**: APScheduler 3.11.2 (задача каждую минуту)
- **Database**: SQLite (`med_bot.db`)
- **Timezone**: pytz, timezonefinder, geopy

## Architecture

### Структура
```
med-bot/
├── bot.py              # точка входа — только main() + регистрация handlers
├── database.py         # SQLite CRUD через get_connection()
├── scheduler.py        # send_reminders() каждую минуту
├── constants.py        # States, MEAL_LABELS, MONTHS_GEN
├── utils.py            # handle_db_errors, get_tz_for_user, cancel
└── handlers/
    ├── meds.py         # add/edit/delete medications
    ├── stats.py        # stats_today, stats_week
    ├── settings.py     # settings, about, reminder_mode toggle
    └── timezone.py     # start, timezone setup
```

### Схема БД
4 таблицы:
- `users` (telegram_id, username, timezone, reminder_mode)
- `medications` (user_id FK, name, dosage, meal_relation, times_per_day, active)
- `schedules` (medication_id FK, reminder_time HH:MM)
- `intake_log` (medication_id FK, scheduled_time, taken_at, status: taken/skipped/pending)

### Поток данных
1. Пользователь добавляет лекарство → `handlers/meds.py` → `database.add_medication()` + `database.add_schedule()`
2. APScheduler каждую минуту → `scheduler.send_reminders()` → InlineKeyboard с ✅/❌
3. Нажатие кнопки → `scheduler.handle_intake_callback()` → `database.log_intake()`

### Handler Pattern
Каждый модуль в `handlers/` экспортирует функции-фабрики, которые возвращают готовые handler-объекты:

```python
# Одиночный handler:
app.add_handler(settings.get_handler())

# Список handlers:
for h in stats.get_handlers():
    app.add_handler(h)

# ConversationHandler с несколькими шагами:
app.add_handler(meds.get_add_handler(cancel_handler))

# Исключение — timezone собирается вручную в bot.py:
setup_tz_handler = ConversationHandler(
    entry_points=[CommandHandler("start", tz_handler.start), ...],
    states={SETUP_TZ: [...], SETUP_CITY: [...]},
    fallbacks=[cancel_handler]
)
```

### utils.py
- `handle_db_errors` — декоратор: ловит `DatabaseError`, отвечает пользователю
- `get_tz_for_user(telegram_id)` → `pytz.timezone` объект
- `cancel` — handler для `/cancel`, завершает любой ConversationHandler

## Commands

```bash
# Разработка
source venv/bin/activate
python3 bot.py

# Установка зависимостей
pip install -r requirements.txt

# Миграция БД (при изменении схемы)
# database.migrate() вызывается автоматически в bot.py при старте
```

## Conversational States
Состояния определены в `constants.py`:
- `NAME, DOSAGE, MEAL, TIMES, SCHEDULE` (0-4) — добавление лекарства
- `EDIT_NAME, EDIT_DOSAGE, EDIT_MEAL, EDIT_TIMES, EDIT_SCHEDULE` (5-9) — редактирование
- `SETUP_TZ, SETUP_CITY` (10-11) — настройка часового пояса

Все диалоги поддерживают `/cancel` для выхода.

## Error Handling
- `DatabaseError` — custom exception в `database.py`
- Декоратор `@handle_db_errors` из `utils.py` — оборачивает handler-функции
- Ошибки БД пишутся в `db_errors.log`
- Ошибки Telegram API молча игнорируются в `send_reminders()` с записью в основной лог

## Configuration
`.env` файл (не коммитится):
```
BOT_TOKEN=токен_от_BotFather
TIMEZONE=Asia/Yekaterinburg
```

## Key Behaviors
- БД создаётся автоматически при первом запуске (`init_db()`)
- Часовой пояс запрашивается при `/start` если не задан (геолокация или город)
- Напоминания в local time пользователя (хранится в `users.timezone`)
- Режим напоминаний: `once` или `repeat` (каждые 5 минут до подтверждения)
