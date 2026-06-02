# After 30 Med Bot

Telegram-бот для напоминаний о приёме лекарств + Telegram Mini App.  
Вайб-кодинг проект — написан в паре с Claude Code (AI).

## Возможности

### 💊 Лекарства и расписание
- Добавление лекарств с дозировкой, способом приёма и гибким расписанием
- Типы расписания: каждый день · через N дней · по дням недели · раз в месяц
- Разная дозировка — одно лекарство с двумя дозировками (например: 25 мкг нечётные / 50 мкг чётные)
- Пауза лекарства без удаления

### ⏰ Напоминания
- Кнопки ✅ Принял / ❌ Пропустить прямо в уведомлении
- Режим повтора: напоминание каждые 5 минут до подтверждения
- Персональные пресеты времени слотов (утро / обед / вечер / ночь)
- Утренний план на день

### 📦 Запас таблеток
- Учёт остатка, автосписание при приёме
- Прогноз «хватит на N дней», предупреждение при низком запасе

### 📊 Статистика и экспорт
- История за 7 дней
- Соблюдение за 30 дней (adherence) с индикатором 🟢/🟡/🔴
- Серия идеальных дней 🔥
- Отчёт для врача в PDF (календарь приверженности)

### 👨‍👩‍👧 Caregiver-режим
- Отслеживание приёма для близких (до 2 подопечных)

### 📱 Mini App
- Дашборд: лекарства на сегодня + streak + adherence
- Кнопки ✅/❌ прямо в приложении
- FastAPI бэкенд с авторизацией через Telegram initData

---

## Стек

| Компонент | Технологии |
|---|---|
| Бот | Python 3.14, python-telegram-bot 22.7, APScheduler |
| БД | PostgreSQL 18, psycopg 3.3, psycopg_pool |
| API | FastAPI 0.136, Uvicorn |
| Mini App | React 19, Vite 8, @telegram-apps/sdk-react v3, TanStack Query |
| Контейнеры | Podman, Quadlet (VPS) |
| Прочее | pytz, timezonefinder, fpdf2, DejaVuSans TTF |

---

## Требования

- Python 3.14+
- Node.js 22+ (через nvm)
- PostgreSQL 18 (локально или в контейнере)
- Podman (для деплоя на VPS)

---

## Быстрый старт (локальная разработка)

### 1. Клонировать репозиторий

```bash
git clone <repo-url>
cd med-bot
```

### 2. Настроить бэкенд

```bash
# Создать виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt

# Создать .env из шаблона
cp .env.example .env
# Заполнить BOT_TOKEN, ADMIN_ID, DATABASE_URL, MINIAPP_ORIGIN

# Инициализировать БД
python3 -c "from database import init_pool, init_db; import asyncio; asyncio.run(init_pool('postgresql://...'))"
# Или запустить бота — он сделает init_db автоматически
```

### 3. Настроить Mini App

```bash
# Установить nvm (если нет)
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.nvm/nvm.sh

# Установить Node 22
nvm install 22

# Установить зависимости Mini App
cd miniapp
npm install
```

### 4. Запуск

Каждый компонент в отдельном терминале:

```bash
# Терминал 1 — Telegram-бот
source venv/bin/activate && python3 bot.py

# Терминал 2 — FastAPI
source venv/bin/activate && uvicorn api.main:app --reload --port 8000

# Терминал 3 — Mini App (dev-сервер)
source ~/.nvm/nvm.sh && cd miniapp && npm run dev
```

Mini App доступна на `http://localhost:5173`.  
Для мобильного превью: DevTools → мобильный режим (F12 → Ctrl+Shift+M).

---

## Переменные окружения (.env)

```env
BOT_TOKEN=токен_от_BotFather
ADMIN_ID=telegram_id_администратора
DATABASE_URL=postgresql://medbot:ПАРОЛЬ@localhost/medbot
MINIAPP_ORIGIN=https://your-domain.com   # CORS; * = dev-режим
RATE_LIMIT_PER_MINUTE=60
TRUST_PROXY=false                        # true при работе за Caddy
```

---

## Тесты

```bash
# Нужна тестовая БД: postgresql://medbot:medbot@127.0.0.1/medbot_test
python -m pytest -q
```

Всего 217 тестов (PostgreSQL, без SQLite).

---

## Деплой на VPS

Стек деплоя: Podman + Quadlet + Caddy + Let's Encrypt.  
Требуется домен (или бесплатный поддомен через DuckDNS) — Telegram Mini App работает только по HTTPS.

Конфигурация: `deploy/quadlet/` (контейнеры), `deploy/backup/` (pg_dump backup/restore).

Порядок деплоя:
1. Арендовать VPS (Ubuntu 22.04, 1 vCPU, 1 GB RAM)
2. Получить домен (купить или DuckDNS)
3. Установить Podman, настроить Quadlet-юниты
4. Настроить Caddy (HTTPS, `/api` → FastAPI, `/` → Mini App)
5. Зарегистрировать Mini App URL в BotFather

---

## Разработка с Claude Code

Весь контекст проекта хранится в `CLAUDE.md` — Claude читает его автоматически при старте сессии.

### Установка Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

### Запуск в проекте

```bash
cd med-bot
claude
```

Claude автоматически загрузит `CLAUDE.md` и продолжит разработку с того места, где остановились. Все архитектурные решения, стек, схема БД, роадмап и история изменений описаны в `CLAUDE.md` и `HISTORY.md`.

### Структура файлов с контекстом

| Файл | Назначение |
|---|---|
| `CLAUDE.md` | Архитектура, стек, команды, роадмап — основной контекст для Claude |
| `HISTORY.md` | История всех закрытых багов и фич (архив) |
| `deploy/` | Конфигурации для деплоя на VPS |
