# Полный аудит проекта Med Bot

**Дата:** 2026-06-03
**Ветка:** develop · последний коммит `ea903e1`
**Объём:** Python ~5 700 строк (28 файлов), фронтенд React/TS (~10 страниц), 174 теста.

Проверено: бэкенд (бот, API, планировщик, воркер, БД), DevOps (контейнеры, systemd, CI/CD, бэкапы), фронтенд (Mini App), зависимости, безопасность.

---

## Сводка

| Область | Статус | Кратко |
|---------|--------|--------|
| Тесты | 🟢 | 174 passed, 38.8 c |
| Сборка фронта | 🟢 | tsc + vite OK, lint чисто |
| Python-зависимости | 🟢 | pip-audit: уязвимостей нет |
| NPM-зависимости | ✅ | было 5 high → `overrides: valibot ^1.2.0` (1.4.1) → **0 уязвимостей** |
| Безопасность API | 🟢 | HMAC initData, параметризованный SQL, проверки владельца |
| systemd-харднинг | ✅ | добавлен sandbox-блок (OP6) на все 3 юнита |
| Конфиг-дрифт | ✅ | rate-limit 60→300, ветка деплоя→main, backup-таймер в деплое; Caddyfile уже в setup.sh |

**Критичных дефектов в коде нет.** Основной долг — обновление фронтовой зависимости и харднинг прод-юнитов.

---

## 1. Безопасность (сильные стороны)

- **Аутентификация Mini App** (`api/auth.py`): валидация `initData` по HMAC-SHA256 корректна. `telegram_id` берётся **только из подписанных данных**, не принимается от клиента. Проверка срока 24 ч. Пустой `BOT_TOKEN` → отказ (SEC-1), а не подделываемая подпись.
- **SQL-инъекции:** все запросы параметризованы (`%s`). Единственная динамическая подстановка имени колонки (`database.py:366,371`) — через белый список `col_map`, пользовательский ввод не попадает в строку SQL. Чисто.
- **Генерация кодов связи** (`database.py:32,796`): `secrets.choice` — криптостойко, не `random`.
- **Проверки владельца:**
  - бот-callback `taken/skipped` проверяет принадлежность лекарства нажавшему (`scheduler.py:382`, S1);
  - `_resolve_med` / `log_intake` в API проверяют own + F7 caregiver + F8 viewer (`medications.py:189`, `today.py:110`);
  - `dependent_id` / `for_linked_user_id` / `for_dep_share_id` валидируются против реальных связей (403/404).
- **Rate limiting:** Redis sliding-window (sorted set), fallback in-memory при сбое Redis. `X-Forwarded-For` читается только при `TRUST_PROXY=true`.
- **Админ-эндпоинт:** `/admin/stats` строго по `ADMIN_ID`; `subprocess` вызывается списком аргументов (без shell).
- **Секреты:** `.env` в `.gitignore` и `.containerignore` — в git и в образ **не попадает**. В репозитории секретов нет.

---

## 2. Бэкенд — находки

### 🟡 B-1. Fire-and-forget уведомления могут теряться
`api/routers/dependent_shares.py` (строки 76, 92, 106) использует `asyncio.create_task(_bot_notify(...))` без удержания ссылки на задачу. Python вправе собрать такую задачу GC до завершения — уведомление в Telegram может не уйти. Для сравнения `caregiver_links.py` те же уведомления делает через `await`.
**Фикс:** заменить на `await`, либо хранить ссылки в множестве (`background_tasks.add(t); t.add_done_callback(discard)`), либо `BackgroundTasks` FastAPI.

### 🟡 B-2. Рассинхрон дефолта rate-limit
`api/main.py:34` → дефолт `RATE_LIMIT_PER_MINUTE=60`, а `.env.example` и `CLAUDE.md` указывают `300`. Если в проде `.env` не задаёт переменную — фактический лимит будет 60, что может резать активного пользователя Mini App (много запросов TanStack Query при навигации).
**Фикс:** привести дефолт в коде к 300 либо явно задать переменную в прод-`.env`.

### 🟢 B-3. /health раскрывает текст ошибок
`api/main.py:188,193` — без авторизации отдаёт строки исключений БД/Redis. Низкий риск (внутренний адрес за прокси), но это лёгкий info-disclosure. Можно отдавать `error` без текста наружу.

### ℹ️ B-4. Известный и осознанный долг (из CLAUDE.md)
- **AX12:** `send_reminders` грузит все правила каждую минуту, O(users×meds). Осознанный дизайн (один JOIN-проход на 3 потребителя). Триггер пересмотра: ~5–10k активных юзеров или проход >5–10 c.
- Целочисленные `active = 1` / `paused 0/1` (наследие SQLite) вместо `boolean` — работает, неидиоматично для Postgres. Не трогать без необходимости.

### 🟢 Качество (хорошо)
- Транзакции через контекст-менеджер `get_connection` (commit/rollback/putconn) — корректно.
- `log_intake` защищён `ON CONFLICT DO UPDATE` от гонок (AX1); `apply_intake_stock` — `SELECT FOR UPDATE`.
- Все синхронные psycopg-вызовы обёрнуты в `asyncio.to_thread` — event loop не блокируется.
- Воркер ARQ: ретраи на `RetryAfter` (429), `max_jobs=25` под лимит Telegram 30 msg/s.
- Планировщик персистит состояние (`_pending`, план дня) в Redis — переживает рестарт; окно догона CATCHUP_MIN=5.
- Alerter: алерт админу при ≥3 ошибках планировщика подряд + recovery-уведомление.

---

## 3. DevOps / инфраструктура — находки

### 🟡 D-1. systemd-юниты без харднинга
`deploy/systemd/medbot-{bot,api,worker}.service` запускаются `User=root` без sandbox-директив. Containerfile корректно использует непривилегированного `appuser`, но **live-окружение = bare systemd+venv от root** (подтверждено CLAUDE.md).
**Рекомендация:** добавить в `[Service]`:
```
User=medbot            # выделенный непривилегированный пользователь
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/root/after-30-medicine-bot
```
(для API дополнительно ограничить сетевые семейства/порты).

### 🟡 D-2. Ветка деплоя: develop vs main
`deploy/setup.sh` ставит и запускает ветку **develop** (`BRANCH="develop"`), а `ci-cd.yml` деплоит **main** (`git pull origin main`). Если VPS изначально на `develop`, то `git pull origin main` либо смержит ветки, либо упрётся в расхождение. Нужно зафиксировать единую ветку прод-деплоя.

### 🟡 D-3. Конфиг обратного прокси (Caddy) вне репозитория
`admin.py` мониторит юнит `caddy`, в проде включён `TRUST_PROXY`, но Caddyfile/конфиг reverse-proxy в репозитории отсутствует. TLS-терминация и маршрутизация `/api` не версионируются — риск «работает только на этой машине».
**Фикс:** положить `deploy/Caddyfile` в репо и синхронизировать его при деплое.

### 🟡 D-4. Бэкап-таймер не синхронизируется деплоем
CI копирует только `medbot-*.service`, но не `deploy/backup/medbot-backup.{service,timer}`. Таймер ежедневного `pg_dump` (ротация 7 дней) нужно включать/обновлять вручную — легко забыть после переустановки.
**Фикс:** добавить копирование backup-юнитов и `systemctl enable --now medbot-backup.timer` в шаг деплоя (или в setup.sh).

### 🟢 D-5. CI: откат без повторного health-check
В `ci-cd.yml` при провале health делается `git reset --hard $PREV` + рестарт, но повторная проверка `/health` после отката не выполняется. Если откат тоже не поднялся — узнаем только из шага OP2 (`is-active`). Низкий риск, но стоит добавить health-проверку и после отката.

### 🟢 DevOps (хорошо)
- Containerfile: multi-stage, пины из `requirements-lock.txt`, непривилегированный `appuser`, очистка apt-кэша.
- compose.yaml: healthcheck'и для db/redis, `depends_on: service_healthy`, `restart: unless-stopped`.
- CI: жёсткий гейт `test → frontend(build+lint) → build → deploy`; `concurrency` без гонок; атомарный деплой с откатом по `/health` (DV4); OP2-проверка `is-active` всех сервисов.
- systemd: `Restart=always`, `StartLimitBurst=5/300s`, `OnFailure=` → Telegram-алерт (OP3), journald `SystemMaxUse=200M` (OP4).
- Бэкап: `pg_dump -Fc` + ротация 7 дней + `Persistent=true` таймер.

---

## 4. Фронтенд (Mini App) — находки

### 🔴 F-1. 5 high-уязвимостей в npm (valibot ReDoS)
`npm audit`: `valibot 0.31.0–1.1.0` — ReDoS в `EMOJI_REGEX` (GHSA-vqpr-j7v3-hqw9). Тянется транзитивно через `@telegram-apps/sdk-react → @telegram-apps/bridge / transformers → valibot`. Прямого фикса без апгрейда SDK нет.
**Фикс:** обновить `@telegram-apps/sdk-react` до версии с непробитым valibot (проверить `npm audit fix --force` в отдельной ветке + регресс Mini App), либо `overrides` на `valibot` в `package.json`. Риск ReDoS прикладной: regex применяется к данным Telegram, но санитизировать стоит.

### 🟢 F-2. Один бандл без code-splitting
`dist/assets/index.js` — 374 KB (110 KB gzip). Все 4 таб-панели монтируются сразу (осознанно, FA-P1 — плавный свайп). Приемлемо для Mini App; при росте можно лениво грузить тяжёлые экраны (PDF-превью статистики).

### 🟢 Фронтенд (хорошо)
- `client.ts`: `Authorization: tma <initDataRaw>` на каждый запрос, единый `apiErrorMessage`.
- Сборка и lint проходят жёсткий CI-гейт; `set-state-in-effect` закрыт точечными disable.
- TanStack Query с оптимистичными апдейтами и откатами; ErrorBoundary с `resetKeys`.

---

## 5. Зависимости

- **Python (`requirements-lock.txt`):** `pip-audit` — **уязвимостей не найдено**. Версии запинены, образ/CI/прод детерминированы (DV3).
- **NPM:** 5 high (см. F-1). Остальное — без замечаний.
- ⚠️ Локальный `venv` — Python **3.12**, а CI/прод/Containerfile — **3.14**. Тесты на 3.12 проходят, но среда разработки расходится с продом. Рекомендуется привести локальный venv к 3.14.

---

## 6. Проверки, выполненные в ходе аудита

```
pytest                → 174 passed, 2 warnings (38.78s)
npm run build         → OK (1811 modules, 3.37s)
npm run lint          → чисто
pip-audit             → No known vulnerabilities found
npm audit             → 5 high (valibot, транзитивно)
grep SQL-инъекции     → только whitelisted {col}, безопасно
```

Предупреждения pytest (некритичны): `StarletteDeprecationWarning` (httpx в TestClient), `psycopg_pool open` deprecation — стоит явно задать `open=True/False` у `ConnectionPool`.

---

## 7. Приоритеты исправления

**Высокий**
1. ✅ `F-1` — `overrides.valibot ^1.2.0` (→1.4.1), `npm audit` = 0, сборка OK.
2. ✅ `D-1` — sandbox-блок (OP6) в 3 юнитах: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome=read-only`, `ReadWritePaths`, `RestrictAddressFamilies`, `SystemCallFilter=@system-service` и др. Выделенный пользователь не вводился (app в /root — потребовал бы релокации каталога). Применится на VPS при следующем деплое (CI копирует юниты + `daemon-reload` + `restart`).

**Средний**
3. ✅ `B-1` — `await` вместо `create_task` в `dependent_shares` (3 места).
4. ✅ `D-2` — `setup.sh BRANCH=main` (единая ветка с CI).
5. ✅ `D-3` — ложная тревога: Caddyfile уже версионируется в `setup.sh` (heredoc → `/etc/caddy/Caddyfile`). Остаток: CI не ресинкает его (только setup.sh) — менять при правке вручную.
6. ✅ `D-4` — backup-юниты переписаны под `/root/after-30-medicine-bot`; CI + setup.sh раскатывают + `enable --now medbot-backup.timer` (OP7).
7. ✅ `B-2` — дефолт `RATE_LIMIT_PER_MINUTE` 60→300.

**Низкий**
8. ✅ `D-5` — health-check после отката в CI (+ ресинк юнитов перед рестартом отката).
9. ✅ `B-3` — `/health` отдаёт `error` без текста исключения (детали в лог).
10. ✅ pool `open=True` (ушла deprecation). Остаток: venv→3.14; deprecated TestClient-путь в `test_api_a5` (тест-инфра, не прод).

---

*Аудит read-only: код не изменялся. Все находки — рекомендации.*
