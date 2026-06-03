# История исправлений

Архив закрытых багов по хронологии. Детали — git log.

---

## Аудит 2026-06-03 (UX + Надёжность)

| # | Что | Файлы |
|---|-----|-------|
| UX-A | Анимация inline-меню лекарств: CSS grid 0fr→1fr; закрытие с задержкой 220ms (контент живёт до конца анимации) | `MedicationList.tsx`, `App.css` |
| UX-C | Админ-панель в Настройках (ADMIN_ID): systemd-статусы 6 сервисов, CPU/RAM/SWAP/Disk, Redis mem+clients+ARQ, DB pool, счётчики. InfoTip-тултипы. Пороги warn: CPU>80%, RAM>85%, SWAP>50%, Disk>85%, ARQ>50, DB-free<2 | `api/routers/admin.py`, `SettingsPage.tsx` |
| OP | `reminder_repeat_hours` (1–12h, def 2) в users; scheduler использует per-user окно вместо хардкода 7200s; UI поле в Настройках при repeat=on | `database.py`, `scheduler.py`, `settings.py`, `SettingsPage.tsx` |
| SYS | Диск VPS: раздел sda2 расширен 20→40 ГБ (`growpart` + `resize2fs`); `medbot-api.service` переведён на systemd (был ручной запуск) | VPS |

---

## Аудит 2026-06-02 — Фаза 6 (Геймификация)

| # | Что |
|---|-----|
| G1 | Сердечки: `users.hearts`; `apply_intake_hearts` (+1 taken/−1 skipped, idempotent, GREATEST 0); вызов в API POST /today/intake + scheduler callback; `GET /stats/hearts`; WishCard счётчик |
| G2 | Строгий режим: `users.strict_mode` + `strict_mode_hours`; `_apply_strict_autoskip` каждую минуту → skipped + −1❤️ + уведомление; idempotent; API PUT /settings/strict-mode; UI тоггл + часы |
| G3 | Dashboard: заголовки секций «Сейчас» / «Сегодня» |
| G4 | Telegram 429: Redis + ARQ worker; scheduler → enqueue_job; `medbot-worker.service` |
| G5 | Ежедневный план: убрано «независимо» при `meal=any` |

---

## Аудит 2026-06-02 — Баги данных (AX)

| # | Приоритет | Что | Файлы |
|---|-----------|-----|-------|
| AX1 | 🔴 | Нет UNIQUE на intake_log → дубли приёмов. UNIQUE-индекс `uq_intake_log_slot_day`; `log_intake` → ON CONFLICT DO UPDATE | `database.py` |
| AX2 | 🔴 | `apply_intake_stock`: потерянное обновление при параллельных запросах. SELECT FOR UPDATE | `database.py` |
| AX3 | 🔴 | Dashboard race: React-машина анимации размножала карточки. Удалена; render — чистая функция от data; CSS-only enter | `Dashboard.tsx` |
| AX4 | 🔴 | Scheduler теряет напоминание при пропуске минуты. Окно догона CATCHUP_MIN=5 мин; dедуп через `_pending` | `scheduler.py` |
| AX5 | 🔴 | `isDue()` во фронте брал время браузера вместо TZ юзера. Серверный `is_due` в каждом TodayItem | `api/routers/today.py`, `Dashboard.tsx` |
| AX6 | 🟡 | `_pending`/`_daily_plan_sent` в памяти — не переживали рестарт. Перенесены в Redis (JSON, TTL 2h), fallback на память | `scheduler.py` |
| AX7 | 🟡 | Rate limiter per-process. Redis sliding window (sorted set); fallback in-memory; попутно пофиксен сломанный тест | `api/main.py`, `conftest.py` |
| AX8 | 🟡 | REDIS_URL захардкожен в 3 местах. Унифицирован через env | `api/main.py`, `scheduler.py`, `worker.py` |
| AX9 | 🟢 | Мёртвый код: `due_intakes_on`, лишний import в scheduler, закомментированный health-bar в Dashboard | разные |
| AX10 | 🟢 | `MEAL.no_meal` в Dashboard не совпадал с enum бэка | `Dashboard.tsx` |
| AX11 | ⏸ | Дубли SQL-запросов — отложено осознанно (разные колонки/фильтры, высокий риск регрессий) | — |
| AX12 | ℹ️ | `send_reminders` грузит все правила каждую минуту O(users×meds). Приемлемо, задел на будущее | — |
| AX13 | ℹ️ | Локальные тесты PoolTimeout без PostgreSQL `medbot_test` — не баг кода | — |

---

## Аудит 2026-06-02 — Безопасность (SEC)

| # | Что | Файлы |
|---|-----|-------|
| SEC-1 | Auth fail-closed при пустом BOT_TOKEN (раньше HMAC с пустым ключом = подделываемый) | `api/auth.py` |
| SEC-2 | Лимиты name≤50, dosage≤30, times_per_day 1..24, rules 1..24, interval_days 1..3650 (API не ограничивал → DoS PDF) | `api/routers/medications.py` |
| SEC-3 | Валидация stock: qty 0..1e6, amount>0, units>0..1e4, days 1..3650; NaN/inf отсечены | `api/routers/stock.py` |
| SEC-4 | Валидация settings: reminder_mode Literal; slot∈SLOT_ORDER; time через parse_time; tz≤64; lat/lng диапазоны | `api/routers/settings.py` |
| SEC-5 | Лимит dependents: name 1..30+trim; кол-во ≤MAX_DEPENDENTS=2 (в API не было) | `api/routers/dependents.py` |

Проверено безопасным: IDOR (все `*_by_id` фильтруют по владельцу), SQL-инъекции (параметризовано), export slot (whitelist).

---

## Аудит 2026-06-02 — Mini App фронтенд (MF)

| # | Что |
|---|-----|
| MF1 | CI: job `frontend` (npm ci + npm run build как гейт; lint continue-on-error) |
| MF2 | Закрыт через AX3 (pure-render) |
| MF3 | Дубль `isDue()` удалён — заменён серверным `item.is_due` (AX5) |
| MF4 | `anchor_date` — локальная дата через getFullYear/getMonth/getDate, не toISOString |
| MF5 | Порог запаса дефолт `?? 5` = БД default |
| MF6 | `MEAL.no_meal` убран (AX10) |
| MF7 | Мёртвый `StockPage`/`StockCard` удалён; остался только экспорт `StockExpanded` |
| MF8 | `index.html`: lang="ru", осмысленный title, viewport-fit=cover |
| MF9 | Единая обработка ошибок API: `apiErrorMessage()` в client.ts |

---

## Аудит 2026-06-02 — DevOps (DV)

| # | Что |
|---|-----|
| DV1 | Прод-деплой = git pull + venv + systemd; ghcr-образ — bot-only артефакт |
| DV2 | `.containerignore`: исключены `miniapp/` и `*.md` |
| DV3 | `Containerfile` и CI test job ставят `requirements-lock.txt` |
| DV4 | Атомарный деплой: PREV=git head; rollback при провале health check |
| DV5 | CI `concurrency` на уровне workflow (cancel-in-progress: false) |
| DV6 | `compose.yaml`: redis, api (uvicorn :8000), worker (arq) |

---

## Аудит 2026-06-02 — PostgreSQL-версия (AX-PG / SEC / O)

| # | Файл | Проблема |
|---|------|----------|
| S1 | `scheduler.py` | IDOR: `med_id` в callback не проверялся на владельца |
| S2 | `api/routers/medications.py` | IDOR: `dependent_id` из тела не проверялся |
| B1 | `broadcast.py` | Читал мёртвый SQLite вместо PostgreSQL |
| S3 | `database.py` | ON CONFLICT затирал username при API-запросах |
| B2 | `database.py` | `datetime.utcnow()` устарел в Python 3.14 |
| B3 | `scheduler.py` | Синхронный psycopg в event loop каждую минуту |
| B4 | `schedule_utils.py` | `interval`-правило без interval_days → TypeError/ZeroDivision |
| S4 | `api/main.py` | Rate limiter: пустые ключи не чистились; нет X-Forwarded-For |
| S5 | `api/main.py` | CORS fail-open: дефолт `*` без warning |
| B5 | `api/routers/medications.py` | Нет серверной валидации schedule_rules |
| O1 | репо | Артефакты `med_bot.db`, `db_errors.log`, `bot_run.log` |
| O2 | `.claude/CLAUDE.md` | Устаревший дубль SQLite-архитектуры |
| O3 | `handlers/meds.py` | Монолит 108 КБ → meds_common / meds_add / meds_edit |
| O4 | `api/routers/*` | `get_or_create_user` повторялся в ~17 эндпоинтах |
| O5 | handlers, scheduler | `parse_mode="Markdown"` → мигрировано на HTML |
| O6 | зависимости | pip-audit + requirements-lock.txt |

---

## SQLite-фаза (до миграции на PostgreSQL)

42 бага + UX-пакет + фичи F1–F6.

| # | Файл | Проблема |
|---|------|----------|
| 1 | `scheduler.py` | Scheduler использовал серверный TZ вместо TZ пользователя |
| 2 | `scheduler.py` | Режим «повтор каждые 5 минут» не реализован |
| 3 | `database.py` | `get_today_stats` использовал `date('now')` UTC вместо TZ юзера |
| 4 | `handlers/meds.py`, `handlers/timezone.py` | Многие DB-функции без `@handle_db_errors` |
| 5 | `handlers/timezone.py` | Нет обработки таймаута geopy |
| 6 | `handlers/meds.py` | Лишние DB-запросы в цепочке edit (`get_or_create_user` × 5) |
| 7 | `scheduler.py` | `handle_intake_callback` без try/except вокруг `log_intake` |
| 8 | `handlers/meds.py` | TIMES/MEAL без паттернов — ловили любой callback |
| 9 | `database.py` | `log_intake` INSERT при каждом нажатии → upsert |
| 10 | `scheduler.py` | Ключи удалённых лекарств висели в `_pending` |
| 11 | `handlers/meds.py` | При смене кол-ва приёмов показывались старые времена |
| 12 | `scheduler.py` | `handle_intake_callback` брал `parts[2]` — обрезал минуты |
| 13 | `handlers/meds.py` | `_check_time` не нормализовал формат |
| 14 | `handlers/timezone.py` | `handle_menu_callback` без `@handle_db_errors` |
| 15 | `handlers/meds.py` | `keep_edit_schedule` не показывал `🔢 X раз в день` |
| 16 | `handlers/meds.py` | Мёртвый код `add_freq_time` / `edit_freq_time` |
| 17 | `handlers/timezone.py` | `handle_menu_callback` рендерил настройки хардкодом |
| 18 | `handlers/timezone.py` | После установки TZ пишет «Используй /meds» |
| 19 | `scheduler.py` | `meal_labels` dict пересоздавался на каждой итерации |
| 20 | `handlers/stats.py` | Нет защиты от лимита 4096 символов |
| 21 | `handlers/meds.py`, `handlers/settings.py` | `_parse_time` дублирована → перенесена в `utils.py` |
| 22 | `handlers/timezone.py` | `TimezoneFinder()` создавался при каждом запросе |
| 23 | `utils.py` | `handle_db_errors` без `functools.wraps` |
| 24 | `handlers/meds.py` | Нет предупреждения для дней 29–31 в monthly |
| 25 | `handlers/settings.py` | Нет описаний в `/settings` |
| 26 | `broadcast.py` | Отдельный скрипт рассылки |
| 27 | `handlers/admin.py`, `database.py` | Кнопка «🔧 Админ панель» в `/settings` |
| 29 | `handlers/meds.py` | Нельзя редактировать лекарство с разными дозировками |
| 30 | `handlers/meds.py` | Multi-dosage edit: устаревшее сообщение, кнопка питания не там |
| 31 | `handlers/stats.py`, `handlers/export.py` | Экспорт истории и плана в PDF |
| 32 | `database.py` | Таблица `schedules` не удалялась |
| 33 | `handlers/meds.py`, `utils.py`, `scheduler.py` | Аудит валидации: escape_md(), лимиты NAME/DOSAGE_MAX_LEN |
| 34 | `database.py`, `handlers/meds.py` | Caregiver-режим: dependents, dependent_id, шаг «Для кого?», лимиты |
| 35 | `handlers/timezone.py` | После установки TZ новому юзеру непонятно что делать |
| 36 | `handlers/stats.py` | В `/stats` нет плана на неделю |
| 37 | `handlers/stats.py`, `utils.py` | HTML без экранирования → добавлен `escape_html()` |
| 38 | `database.py`, `scheduler.py` | «Сегодня» по UTC вместо TZ юзера → `local_day_bounds_utc()` |
| 39 | `handlers/meds.py` | Multi-dosage edit показывал «добавлено» вместо «обновлено» |
| 40 | `database.py` | Нет PRAGMA busy_timeout/WAL/foreign_keys |
| 41 | `database.py` | Нет индексов → full-scan. Добавлены 5 индексов |
| 42 | `database.py` | `delete_dependent` не занулял `dependent_id` → FK-нарушение |
| 43 | `scheduler.py` | Утечки: `_pending`/`_daily_plan_sent` без TTL-prune |
| 44 | `database.py`, `scheduler.py` | 2 full-scan/мин → один `get_active_schedule_rows()` |
| 45 | `database.py`, `handlers/settings.py` | `fetch_settings_data` открывала 5 соединений → один `get_user_settings_row()` |
| 46 | `database.py`, `handlers/meds.py` | N+1 запросов в списке лекарств → `get_rules_grouped_for_user()` |
| 47 | `handlers/settings.py`, `handlers/timezone.py` | Нет «◀️ Назад» из под-экранов `/settings` |
| 48 | `constants.py`, `handlers/settings.py` | Дубль текста «О проекте» → вынесен в `ABOUT_TEXT` |
| 49 | `database.py` | `db_logger` без `propagate=False` — дубли в консоли |
| 50 | `database.py` | `migrate()` повторно создавал `dependents` |
| 51 | `tests/` | Не было тестов → 58 unit-тестов |
| 52 | `handlers/meds.py` | Дубль `add_start` ≈ `handle_add_med_callback` → `_begin_add_flow()` |
| 53 | `handlers/meds.py` | Success-сообщения → `_med_saved_text()`; валидация → `_parse_int_range()` |
| 54 | разные | Непоследовательные «Назад» → единая точка `/menu` |
| 55 | `handlers/timezone.py`, `bot.py` | `TimedOut` ронял старт → таймауты 20с + try/except |
| 56 | разные | F5: учёт запаса (stock_qty/units_per_dose/low_stock_days, автосписание, прогноз) |
| 57 | `database.py`, `handlers/settings.py` | Смена пресета не прокидывалась в правила → `set_user_time_preset` мигрирует reminder_time |
| Q1b | `handlers/meds.py` | Слияние состояний add/edit → `_schedule_input_states()` |
| UX | разные | UX-пакет: подсказка слотов, кнопка запаса, слияние кнопок в списке |
| F1 | разные | «Отчёт для врача»: PDF-календарь adherence 30 дней |
| F2 | `streak.py` | Серия идеальных дней: `compute_streak`, `streaks_by_subject` |
| F3 | разные | Adherence за 30 дней: экран stats:adherence |
| F4 | разные | Пауза лекарства: `medications.paused`, кнопки ⏸/▶️ |
| F6 | разные | «✅ Принять всё»: кнопка на экране «Сегодня» |
