# Med Bot — Telegram бот для напоминаний о приёме лекарств

> ⚡ Вайб-кодинг проект — написан в паре с Claude (AI) за один вечер.
> Код живой, рабочий, но не идеальный. Идём дальше итерациями.

## Стек
- Python 3.14
- python-telegram-bot — Telegram API
- APScheduler — планировщик напоминаний
- SQLite — база данных
- pytz + timezonefinder + geopy — определение часового пояса

## Структура проекта

```
med-bot/
├── bot.py          # точка входа, все handlers и ConversationHandler'ы
├── database.py     # вся работа с SQLite (CRUD + миграции)
├── scheduler.py    # отправка напоминаний каждую минуту
├── .env            # токен бота и часовой пояс по умолчанию (не коммитить!)
├── requirements.txt
└── med_bot.db      # SQLite база (создаётся автоматически)
```

## База данных

| Таблица | Описание |
|---|---|
| users | пользователи (telegram_id, username, timezone) |
| medications | лекарства (название, дозировка, способ приёма, кол-во раз) |
| schedules | времена напоминаний для каждого лекарства (HH:MM) |
| intake_log | история приёмов (taken / skipped / pending) |

## Команды бота

| Команда | Описание |
|---|---|
| /start | регистрация, запрос часового пояса |
| /add | добавить лекарство (диалог из 5 шагов) |
| /list | список активных лекарств |
| /edit | редактировать лекарство |
| /delete | удалить лекарство и его напоминания |
| /stats | статистика приёмов за сегодня |
| /history | статистика за 7 дней |
| /timezone | изменить часовой пояс |
| /cancel | отмена текущего диалога |

## Запуск

```bash
cd ~/med-bot
source venv/bin/activate
python3 bot.py
```

## .env

```
BOT_TOKEN=ваш_токен_от_BotFather
TIMEZONE=Asia/Yekaterinburg
```

## Планы
- [ ] Docker контейнер
- [ ] Деплой на VPS
- [ ] Telegram Mini App фронтенд
- [ ] Пауза напоминаний
