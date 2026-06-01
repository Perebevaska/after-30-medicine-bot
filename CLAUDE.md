# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About
Telegram бот для напоминаний о приёме лекарств с поддержкой гибкого расписания, статистики, экспорта в PDF и определения часовых поясов.

## Stack
- **Language**: Python 3.14
- **Framework**: python-telegram-bot 22.7 (async API)
- **Scheduler**: APScheduler 3.11.2 (задача каждую минуту)
- **Database**: SQLite (`med_bot.db`)
- **Timezone**: pytz, timezonefinder, geopy (Nominatim кэшируется как `_geolocator` на уровне модуля)
- **PDF**: fpdf2 + DejaVuSans TTF (`/usr/share/fonts/truetype/dejavu/`)

## Architecture

### Структура
```
med-bot/
├── bot.py              # точка входа — только main() + регистрация handlers
├── database.py         # SQLite CRUD через get_connection()
├── scheduler.py        # send_reminders() каждую минуту
├── schedule_utils.py   # чистая логика «положенных приёмов» (_rule_fires_today + due/count хелперы)
├── streak.py           # F2: серия идеальных дней (compute_streak + группировка по подопечным)
├── constants.py        # States, MEAL_LABELS, MONTHS_GEN, MAX_MEDICATIONS_PER_USER
├── utils.py            # handle_db_errors, get_tz_for_user, cancel, escape_md, parse_time
├── broadcast.py        # standalone скрипт рассылки (python3 broadcast.py)
└── handlers/
    ├── meds.py         # add/edit/delete medications
    ├── stats.py        # stats_week, show_week_plan
    ├── export.py       # PDF экспорт плана и истории (asyncio.to_thread)
    ├── settings.py     # settings, about, reminder_mode toggle, daily plan
    ├── admin.py        # админ-панель (только ADMIN_ID)
    ├── caregiver.py    # caregiver-режим: подопечные (dependents), вкл/выкл
    ├── stock.py        # F5: экран «📦 Запас» — остаток/расход/порог/прогноз
    └── timezone.py     # start, timezone setup, main menu, Лекарства на сегодня
```

### Схема БД
5 активных таблиц:
- `users` (telegram_id, username, timezone, reminder_mode, time_morning, time_lunch, time_evening, time_night, daily_plan_enabled, daily_plan_time, **caregiver_enabled**)
- `dependents` (user_id FK, name) — подопечные caregiver-режима
- `medications` (user_id FK, name, dosage, meal_relation, times_per_day, active, **dependent_id** FK NULL, **stock_qty** REAL NULL=трекинг выкл, **units_per_dose** REAL, **low_stock_days** INTEGER, **paused** INTEGER 0/1 — F4: пауза) — F5: учёт запаса
- `schedule_rules` (medication_id FK, reminder_time, frequency, interval_days, weekdays, month_day, anchor_date, dosage) — `dosage NULL` = берётся из `medications.dosage`
- `intake_log` (medication_id FK, scheduled_time, taken_at, status: taken/skipped/pending)

Таблица `schedules` удалена в `migrate()` через `DROP TABLE IF EXISTS schedules`.

**Соединение БД** (`get_connection`): `PRAGMA journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON` — параллельные чтение/запись и контроль FK.
**Индексы** (создаются в `init_db`): `medications(user_id, active)`, `medications(dependent_id)`, `schedule_rules(medication_id)`, `intake_log(medication_id, scheduled_time)`, `intake_log(taken_at)`.
**Внимание про FK**: при удалении подопечного `delete_dependent` обязан занулять `medications.dependent_id` — иначе `DELETE` нарушит включённый `foreign_keys`.

### schedule_rules — типы frequency
| frequency | поля | описание |
|-----------|------|----------|
| `daily` | — | каждый день |
| `interval` | `interval_days`, `anchor_date` | каждые N дней от anchor_date |
| `weekdays` | `weekdays` | по дням недели, '1,3,5' (пн=1, вс=7) |
| `monthly` | `month_day` | раз в месяц, N-го числа |

### Поток данных
1. Пользователь добавляет лекарство → `handlers/meds.py` → `database.add_medication()` + `database.add_schedule_rule()`
2. APScheduler каждую минуту → `scheduler.send_reminders()` → проверяет `_rule_fires_today()` → InlineKeyboard с ✅/❌
3. Нажатие кнопки → `scheduler.handle_intake_callback()` → `database.log_intake()` (upsert)
4. Кнопка PDF → `handlers/export.py` → `asyncio.to_thread(_build_pdf, ...)` → `reply_document`

### Флоу добавления лекарства
```
Название → Дозировка
  ├── (текст) → Когда принимать (multi-select) → Как с пищей → Тип расписания → сохранить
  └── 📊 Разная дозировка
        → Дозировка А → Дозировка Б
        → Слоты А → Слоты Б
        → Как с пищей (один раз для обеих)
        → Расписание А (daily/interval/weekdays/monthly)
        → Расписание Б (+ выбор даты начала для interval)
        → сохранить одно лекарство с rules: А dosage=NULL, Б dosage=dosage_b
```

Время выбирается через multi-select по пресетам (Утро/Обед/Вечер/Ночь). Пресеты настраиваются в /settings.
Каждое выбранное время сохраняется отдельной строкой в `schedule_rules`.
При разных дозировках правила Б хранят `dosage` явно; правила А — `dosage=NULL` (наследуют из `medications`).

### Флоу редактирования лекарства
```
Название → Дозировка А → [Дозировка Б] → Приём с пищей → Тип расписания:
  Оставить расписание → сохранить
  Каждый день / Через N / По дням / Раз в месяц →
    Когда принимать (multi-select) → Как с пищей →
      Каждый день   → сохранить
      Через N дней  → N дней → сохранить
      По дням недели → Дни → сохранить
      Раз в месяц   → Число → сохранить
```

### Handler Pattern
```python
app.add_handler(settings.get_handler())
for h in stats.get_handlers():
    app.add_handler(h)
for h in export.get_handlers():
    app.add_handler(h)
app.add_handler(meds.get_add_handler(cancel_handler))
app.add_handler(meds.get_edit_handler(cancel_handler))
app.add_handler(CallbackQueryHandler(tz_handler.handle_menu_callback, pattern="^menu:"))
```

### utils.py
- `handle_db_errors` — декоратор: ловит `DatabaseError`, отвечает пользователю
- `get_tz_for_user(telegram_id)` → `pytz.timezone` объект
- `cancel` — handler для `/cancel`, завершает любой ConversationHandler
- `escape_md(text)` — экранирует спецсимволы Telegram Markdown v1 (`*`, `_`, `` ` ``, `[`)
- `escape_html(text)` — экранирует `&`, `<`, `>` для `parse_mode="HTML"` (stats.py, план)
- `local_day_bounds_utc(user_tz, now_local=None)` → `(start_utc, end_utc)` — границы локальных суток пользователя как UTC-строки; для запросов «сегодня» по `intake_log`
- `parse_time(time_str)` → `ЧЧ:ММ` с ведущим нулём; поднимает `ValueError` при ошибке
- `NAME_MAX_LEN = 50`, `DOSAGE_MAX_LEN = 30` — лимиты длины пользовательского ввода

## Commands

```bash
# Разработка
source venv/bin/activate
python3 bot.py

# Установка зависимостей
pip install -r requirements.txt

# Рассылка (standalone)
python3 broadcast.py

# Миграция БД вызывается автоматически в bot.py при старте

# Тесты (чистые функции, без БД/Telegram)
pip install -r requirements-dev.txt
pytest -q
```

## Тесты
- `tests/test_pure.py` — unit-тесты чистых функций: `parse_time`, `escape_md`, `escape_html`, `local_day_bounds_utc`, `_rule_fires_today`, `_compute_next_fire`, `_next_fire_label`, `_freq_label`, `_format_schedule_rule`, `_monthday_warning`, `_current_schedule_summary`
- `tests/test_handlers.py` — характеризационные тесты save-хендлеров (add/edit × daily/interval/weekdays/monthly): фиксируют текст «✅ Лекарство добавлено/обновлено» и валидацию диапазонов; БД мокается в namespace `handlers.meds`, Telegram заменён фейками
- `tests/test_menu.py` — навигация меню (`menu:main`/`about`/`stats`), наличие кнопок «◀️ В меню»; F6: `_today_keyboard` с/без pending
- `tests/test_conv_structure.py` — снапшот структуры `get_add_handler`/`get_edit_handler` (состояния, callback'и, паттерны); защищает дедуп общих состояний (`_schedule_input_states`)
- `tests/test_schedule_utils.py` — «положенные приёмы» за день/период (`due_intakes_on`, `iter_due_by_day`, `count_due_*` + кламп `created_dates` для F3) + прогноз запаса `days_of_stock_left` (F5) + реэкспорт `_rule_fires_today`
- `tests/test_adherence_db.py` — DB-слой adherence F3: `get_adherence_rules` (только активные, с `created_at`) и `get_taken_counts` (только `taken`, диапазон/изоляция по пользователю)
- `tests/test_adherence_handler.py` — экран `show_adherence` (текст %, итог, `_pct_color`); `tests/test_adherence_export.py` — PDF-экспорт `export_adherence` (валидная `%PDF`-сигнатура, пустой случай)
- `tests/test_doctor_report.py` — F1 PDF-отчёт врача: валидная `%PDF`, непустой календарь, пустые случаи, исключение лекарств на паузе
- `tests/test_pause.py` — F4 пауза: DB-фильтры (планировщик/`get_schedules_for_user`/adherence исключают `paused=1`, список — оставляет) + toggle-хендлер `handle_pause_toggle` (пауза↔возобновление, смена кнопки/пометки)
- `tests/test_streak.py` — F2 серия: чистая `compute_streak` (идеальные дни, grace для сегодня, пропуск рвёт, недельные пустые дни, кламп по `created_at`) + `streaks_by_subject` (отдельная серия владельца и подопечного)
- `tests/test_stock_db.py` — DB-слой запаса F5 (set/add/units/threshold, `apply_intake_stock` идемпотентно, `log_intake` возвращает старый статус) на временной БД
- `tests/test_stock_intake.py` — интеграция: списание и предупреждение при пересечении порога через `handle_intake_callback`
- `tests/test_delete_user_data.py` — полное удаление данных пользователя по всем таблицам + изоляция от других
- `tests/test_preset_migration.py` — миграция правил при смене пресета времени (`set_user_time_preset`, баг #57)
- Не трогают реальную БД и сеть — функции/хендлеры вызываются напрямую
- Всего **168** тестов (на момент F1/F2/F3/F4/F5/F6)
- Конфиг — `pytest.ini` (`testpaths = tests`); dev-зависимости — `requirements-dev.txt`
- **Перед рефакторингом хендлеров**: запусти `pytest` до и после — `test_handlers.py` ловит изменения текста сообщений

## Conversational States
Состояния определены в `constants.py`:
- `NAME, DOSAGE, MEAL, TIMES, SCHEDULE` (0-4) — добавление лекарства (SCHEDULE не используется)
- `EDIT_NAME, EDIT_DOSAGE, EDIT_MEAL, EDIT_TIMES, EDIT_SCHEDULE` (5-9) — редактирование (EDIT_SCHEDULE не используется)
- `SETUP_TZ, SETUP_CITY` (10-11) — настройка часового пояса
- `FREQ_TYPE, FREQ_INTERVAL, FREQ_WEEKDAYS, FREQ_MONTHDAY, FREQ_TIME` (12-16) — тип расписания при добавлении (FREQ_TIME не используется)
- `EDIT_FREQ_TYPE, EDIT_FREQ_INTERVAL, EDIT_FREQ_WEEKDAYS, EDIT_FREQ_MONTHDAY, EDIT_FREQ_TIME` (17-21) — тип расписания при редактировании (EDIT_FREQ_TIME не используется)
- `PRESET_TIME` (22) — ввод времени пресета в настройках
- `DAILY_PLAN_TIME` (23) — ввод времени плана дня
- `DOSAGE_B, TIMES_B, FREQ_TYPE_B, FREQ_INTERVAL_B, FREQ_WEEKDAYS_B, FREQ_MONTHDAY_B` (29-34) — ветка «Разная дозировка» при добавлении
- `EDIT_DOSAGE_B` (35) — ввод дозировки Б при редактировании multi-dosage
- `SELECT_DEPENDENT` (36) — выбор «Для кого?» в начале add-флоу (caregiver)
- `ADD_DEPENDENT_NAME` (37) — ввод имени нового подопечного (settings + add-флоу)
- `STOCK_INPUT` (38) — ввод числа на экране «📦 Запас» (остаток/пополнение/единицы/порог), F5

Все диалоги поддерживают `/cancel` для выхода.

## Error Handling
- `DatabaseError` — custom exception в `database.py`
- Декоратор `@handle_db_errors` из `utils.py` — оборачивает handler-функции
- Ошибки БД пишутся в `db_errors.log`
- Ошибки Telegram API молча игнорируются в `send_reminders()` с записью в основной лог
- PDF генерируется в `asyncio.to_thread` чтобы не блокировать event loop

## Configuration
`.env` файл (не коммитится):
```
BOT_TOKEN=токен_от_BotFather
ADMIN_ID=telegram_id_админа
```

Логирование в `bot.py`: httpx, apscheduler, telegram, **fontTools** — уровень WARNING.

## Key Behaviors
- БД создаётся автоматически при первом запуске (`init_db()`)
- Часовой пояс запрашивается при `/start` если не задан (геолокация или город)
- Напоминания в local time пользователя (хранится в `users.timezone`)
- Режим напоминаний: `once` или `repeat` (каждые 5 минут до подтверждения, до 2 часов)
- Лимит лекарств: `MAX_MEDICATIONS_PER_USER = 10` (задан в `constants.py`)
- **Единая точка входа `/menu`** (`menu_command` в `timezone.py`): открывает главное меню. В списке команд бота (`post_init`) только `menu`. `/cancel` остаётся рабочим как fallback диалогов (выход из текстового ввода), но скрыт из меню; `/start` оставлен для онбординга (TZ); `/meds`/`/stats`/`/settings`/`/about` работают, но скрыты
- **Навигация edit-in-place**: пункты меню (`menu:today/meds/stats/settings/about`) редактируют текущее сообщение; `menu:main` возвращает главное меню. Все под-экраны имеют «◀️ В меню» (`back_menu_kb()` в `timezone.py`, `_stats_period_keyboard`/`_report_keyboard`/`_nav_keyboard` в `stats.py`, кнопка в `_settings_keyboard`, в списке лекарств). Слой навигации — глобальный handler `^menu:`, вне диалогов add/edit (не задевается Q1b)
- Главное меню — inline-кнопки: 📋 Лекарства на сегодня, 💊 Мои лекарства, 📊 Статистика, ⚙️ Настройки, ℹ️ О проекте
- **Мои лекарства** — многосообщенный список; «◀️ В меню» на завершающем сообщении (`show_meds_list`)
- **Лекарства на сегодня** (`menu:today`): показывает расписание на текущий день с иконками ✅/❌/⏳ по данным `get_today_intake_statuses()`
- **Статистика** (`menu:stats`): кнопки «📈 За 7 дней», «📆 План на 7 дней», «📊 Соблюдение за 30 дней» (adherence, `stats:adherence`, последней перед «В меню»); под историей/планом — «📄 Скачать PDF» (`export:week`/`export:plan`); под соблюдением — «🩺 Отчёт для врача» (`export:doctor`, альбомный PDF-календарь, F1)
- `log_intake` — upsert: при повторном нажатии обновляет запись за сегодня вместо дубля
- При удалении лекарства `clear_pending_for_medication()` сразу чистит `_pending` в scheduler
- `parse_time()` в `utils.py` нормализует формат → `ЧЧ:ММ` с ведущим нулём
- `handle_intake_callback` парсит `callback_data` как `status:med_id:HH:MM` → время восстанавливается через `":".join(parts[2:])`
- **Перезапуск после рефакторинга обязателен**: ConversationHandler хранит состояния в памяти
- Пресеты времени (🌅 Утро/☀️ Обед/🌇 Вечер/🌙 Ночь): хранятся в `users.time_morning/lunch/evening/night`, редактируются через `/settings` → "⏰ Настроить время приёмов"
- `SLOT_ORDER`, `SLOT_LABELS` в `constants.py`; `get_user_time_presets()` / `set_user_time_preset()` в `database.py`
- **Смена пресета мигрирует правила**: `set_user_time_preset()` обновляет все активные `schedule_rules` пользователя с `reminder_time == старое значение` на новое (слоты хранятся как снимок времени) — иначе старое время «зависает» в напоминаниях/списке/плане. Возвращает число перенесённых правил
- **Разная дозировка**: одно `medications`-запись, правила А с `dosage=NULL`, правила Б с `dosage=dosage_b`; планировщик использует `rule_dosage or med_dosage`; список лекарств показывает дату следующего срабатывания через `_next_fire_label()` + `_compute_next_fire()`
- **Один проход планировщика**: `send_reminders()` берёт `get_active_schedule_rows()` (все правила активных лекарств + поля пользователя одним запросом) и передаёт их в `_send_daily_plans(app, schedules)`; план дня фильтруется по `daily_plan_enabled` в Python — без второго запроса к БД
- **Plan на день**: `_daily_plan_sent: set` в `scheduler.py` предотвращает дубли (TTL-prune старше 2 дней); строки берутся из общего прохода (`daily_plan_enabled=1`)
- **Настройки одним запросом**: `fetch_settings_data()` использует `get_user_settings_row()` (одна строка вместо 5 соединений); список лекарств — `get_rules_grouped_for_user()` вместо N+1
- **ADMIN_ID**: читается через `os.getenv("ADMIN_ID")` в обоих `admin.py` и `settings.py`; обёрнут в `try/except ValueError`; `load_dotenv()` вызывается в `bot.py` **до** всех импортов
- **broadcast.py**: standalone скрипт, не импортирует handlers; завершение ввода текста — строка `.`; режим 2 требует подтверждения словом `да`
- **PDF export**: `_build_pdf()` в `handlers/export.py` использует DejaVuSans (`/usr/share/fonts/truetype/dejavu/`); вызывается через `asyncio.to_thread` чтобы не блокировать event loop; fontTools лог заглушён до WARNING в `bot.py`
- `escape_md()` применяется ко всем пользовательским строкам при отображении в `parse_mode="Markdown"`; stats.py и план используют HTML — пользовательские строки (название, дозировка, имя подопечного) экранируются через `escape_html()`
- **«Сегодня» по TZ пользователя**: `log_intake()` и `get_today_intake_statuses()` принимают диапазон `[start_utc, end_utc)` из `local_day_bounds_utc()`, а не UTC `date('now')`

## Known Issues

### 🔲 К исправлению

| # | Файл | Проблема |
|---|------|----------|

### Порядок работы с багами
1. Найти баг → добавить в таблицу "К исправлению"
2. Исправить → коммит (сообщение = описание бага)
3. После правок — основной флоу: `/start` → добавить лекарство → изменить → `/stats`

---

## Roadmap

Реализованы F1–F6, 168 тестов. Доменная логика изолирована: `schedule_utils.py`, `streak.py`, `database.py`.

**Размер:** `S` < 1д · `M` 2–5д · `L` 1–2 нед  
**Критичность:** 🔴 блокер · 🟡 важно · 🟢 желательно  
**Тест:** `[тест]` — обязательная проверка перед тем как считать задачу закрытой

**Критичный путь:** P0→P1→P2→P3→P5→C1→C2→C3→A1→A2→A3→M1→M2→D1

---

### Фаза 1 — Postgres

P0→P1→P2→P3 строго последовательно. После P3: P4 и P5 параллельно.

**P0** `S` 🔴 Решение по типам *(принять до первой строки кода)*
Выбрать стратегию и зафиксировать письменно — всё остальное зависит от неё.
- Таймстампы: TEXT в формате `'YYYY-MM-DD HH:MM:SS'` UTC (минимальный риск, код парсинга не трогаем)
- Булевы колонки: `INTEGER` (0/1), код с `if row["paused"]` работает как есть

**P1** `M` 🔴 Слой соединений
`sqlite3` → `psycopg3` + `psycopg_pool.ConnectionPool`. Сохранить контракт `get_connection()` как контекст-менеджер — хендлеры не трогаем. Конфиг через `DATABASE_URL` env.

**P2** `M` 🔴 DDL
Портировать `init_db()` / `migrate()`: `INTEGER PRIMARY KEY AUTOINCREMENT` → `GENERATED ALWAYS AS IDENTITY`, FK объявить в схеме, убрать все `PRAGMA`.

**P3** `M` 🔴 Запросы `[тест]`
`?` → `%s`, upsert `INSERT ... ON CONFLICT (...) DO UPDATE`, `date('now')`/`CURRENT_TIMESTAMP` → генерация времени в Python (`datetime.utcnow().strftime(...)`).
Тест: `pytest -q` до и после — все 168 должны остаться зелёными.

**P4** `S` 🟡 Скрипт миграции данных
`migrate_sqlite_to_pg.py`: читает `med_bot.db`, пишет в Postgres. Идемпотентный, с проверкой счётчиков строк на входе и выходе.

**P5** `L` 🟡 Тесты на Postgres `[тест]`
DB-тесты (`test_stock_db`, `test_adherence_db`, `test_doctor_report`, `test_pause`, `test_delete_user_data`, `test_preset_migration`, `test_stock_intake`) — заменить временную SQLite на тестовую схему Postgres (testcontainers-python или тест-БД + truncate между тестами).
Критерий готовности Фазы 1: **все 168 тестов зелёные**, ручной флоу `/start → добавить → напоминание → ✅/❌ → stats → серия → запас → пауза → PDF` идентичен SQLite-версии.

---

### Фаза 2 — Podman + VPS

C1→C2 строго. После C2: C3 параллельно с A1 (Фаза 3). C4/C5 — после C3, не блокируют.

**C1** `S` 🔴 Containerfile
Multi-stage, база `python:3.14-slim`, непривилегированный пользователь.
⚠️ Обязательно установить `fonts-dejavu-core` — fpdf2 ждёт `/usr/share/fonts/truetype/dejavu/`, без этого PDF-экспорт (отчёт врача, план) упадёт в контейнере.

**C2** `S` 🔴 Секреты
`BOT_TOKEN`, `ADMIN_ID`, `DATABASE_URL` — через Podman secrets или env-файлы. Не класть в образ и не коммитить.

**C3** `M` 🟡 Оркестрация
Локально: `podman compose` (postgres + bot). VPS: Quadlet-юниты (`db.container`, `bot.container`), общий pod, volume `pgdata`, healthcheck, политика рестарта, `loginctl enable-linger`.
Режим бота: **long polling** на этом этапе — не требует входящего HTTPS.

**C4** `S` 🟡 Бэкапы `[тест]`
systemd-timer с `pg_dump`, ротация 7 дней.
Тест: выполнить restore из дампа на чистой БД и убедиться в корректности данных — до продакшена.

**C5** `S` 🟢 Логи
Перевести `db_errors.log` и основной лог на stdout/stderr — стандарт для контейнеров, сбор через journald/podman logs.

---

### Фаза 3 — FastAPI (Backend API)

Стартует после P3, не ждёт Quadlet. A1→A2→A3 последовательно.

**A1** `M` 🔴 FastAPI-приложение
В монорепо; импортирует `database.py`, `schedule_utils.py`, `streak.py`. Запуск через Uvicorn как отдельный контейнер/команда.
⚠️ APScheduler запускать **только в боте** — иначе дубли напоминаний.

**A2** `S` 🔴 Auth middleware `[тест]`
Валидация `initData` (HMAC-SHA256 по `BOT_TOKEN`), извлечение `telegram_id` — только из подписи, не с клиента. Без валидации — 401.
Тест: три кейса — валидный initData, просроченный, поддельный.

**A3** `L` 🔴 Эндпоинты `[тест]`
Паритет с ботом. Чтение: лекарства, «на сегодня», статистика (week/adherence/streak), запас, план, подопечные, настройки. Запись: CRUD лекарств, log intake (taken/skipped), пауза/возобновление, операции с запасом, пресеты, caregiver. PDF: переиспользовать рендер из `handlers/export.py` через `asyncio.to_thread`.
Тест: happy path + edge cases, контроллеры тонкие — вся логика в существующих доменных функциях.

**A4** `S` 🟡 Инфра API
CORS только на домен Mini App, rate limiting, единый формат ошибок.

**A5** `M` 🟡 Тесты API `[тест]`
Покрыть: auth (A2), все эндпоинты (A3), изоляцию пользователей. Переиспользование domain-функций — нет дублирования логики.

---

### Фаза 4 — Mini App (Frontend)

M1 стартует после A2 (против мок-API, не ждёт A3). M2–M7 параллельно после M1+A3.

**M1** `S` 🔴 Стек
Vite + React или Svelte, `@telegram-apps/sdk` (или `telegram-web-app.js`), адаптация под `themeParams` (светлая/тёмная тема), TanStack Query для API-запросов.

**M2** `M` 🔴 Дашборд
«На сегодня» + 🔥 серия + краткое соблюдение + быстрые ✅/❌ прямо на экране.

**M3** `L` 🔴 Редактор лекарства `[тест]`
Форма вместо ConversationHandler: название, дозировка, разная дозировка (multi-dosage), тип расписания (daily/interval/weekdays/monthly), приём с пищей, мульти-слоты времени. Покрывает add и edit.
Тест: проверить создание и редактирование каждого типа расписания на iOS, Android, Desktop.

**M4** `M` 🟡 Список лекарств
Скроллируемые карточки, пауза/возобновление, удаление, переход в редактор (M3).

**M5** `M` 🟡 Запас
Числовые поля (остаток/пополнение/единицы/порог) + прогноз дней + история.

**M6** `M` 🟡 Статистика
Adherence бар-чарт 30 дней, визуализация серии, история. PDF-отчёт врача — просмотр и скачивание через API.

**M7** `M` 🟢 Настройки
Пресеты времени, режим напоминаний (once/repeat), caregiver/подопечные.

**M8** `S` 🟡 Регистрация и точка входа
BotFather: зарегистрировать Web App URL. В боте: кнопка «📱 Приложение» в главном меню.

---

### Фаза 5 — Деплой и эксплуатация

**D1** `S` 🔴 Caddy (reverse proxy + HTTPS) `[тест]`
`/api` → api-контейнер, `/` → статика miniapp, авто-HTTPS через Let's Encrypt.
Опционально: перевести бота на webhook (теперь есть HTTPS).
Тест: end-to-end на VPS — HTTPS работает, бот и Mini App читают одну Postgres, переживает `reboot`.

**D2** `M` 🟡 Quadlet для всех пяти контейнеров
db, bot, api, miniapp, caddy: единый pod, общая сеть, volumes, healthcheck, rootless, авто-рестарт.

**D3** `M` 🟢 CI/CD
Сборка образов → ghcr → деплой через Podman auto-update или git-pull на VPS. Альтернатива: Coolify на том же VPS.

**D4** `M` 🟢 Наблюдаемость
Централизованные логи, healthcheck-и, метрики напоминаний (отправлено/подтверждено), алертинг по ошибкам.

---

### UX-интеграция бот ↔ Mini App

Выполняется после появления соответствующих экранов Mini App. В боте **остаются навсегда**: APScheduler-напоминания, ✅/❌ в сообщении напоминания, /start онбординг.

**U1** `S` 🟡 Deep links из напоминаний
Добавить кнопку в сообщение напоминания → открывает конкретное лекарство/дашборд в Mini App.

**U2** `M` 🟢 Упрощение add/edit в боте
При добавлении/редактировании — предлагать Mini App первым. ConversationHandler остаётся как fallback для клиентов без поддержки WebApp.

**U3** `S` 🟢 Stats в боте
Добавить «📊 Подробнее →» deep link в Mini App под текстовой статистикой.

---

### Продуктовые фичи

**F7** `L` 🟡 Caregiver-расширение *(зависит от A3, M3)*
Уведомления опекуну о пропусках подопечного («Маша не приняла лекарство в 09:00»). Сводка adherence подопечного. Связать двух реальных пользователей (invite/confirm по telegram_id). Приватность и согласие — продумать отдельно.
Задел уже есть: таблица `dependents`, `medications.dependent_id`, caregiver-режим в `/settings`.
