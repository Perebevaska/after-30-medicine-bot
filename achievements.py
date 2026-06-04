"""Фаза 12a — ачивки (детерминированные бейджи по абсолютным порогам).

Чистый модуль (без БД/Telegram): каталог бейджей + `evaluate()` решает, какие
коды заслужены по метрикам терапии. Пороги — абсолютные (серия/соблюдение/число
приёмов/первая «Забота»); перцентилей («топ-1%») нет — нет базы пользователей.

Бейдж — факт достижения, не валюта. Сердца-экономика (Ф15) ачивок не касается.
"""

# Каталог: порядок = порядок показа в «Прогресс». desc — подсказка под бейджем.
CATALOG = [
    {"code": "intake_10",  "icon": "🌱", "title": "Первые шаги",      "desc": "10 принятых приёмов"},
    {"code": "streak_7",   "icon": "⭐", "title": "Неделя подряд",    "desc": "7 идеальных дней без пропусков"},
    {"code": "adh_30",     "icon": "🎯", "title": "Точный месяц",     "desc": "≥90% соблюдения за 30 дней"},
    {"code": "intake_100", "icon": "🌟", "title": "Сотня приёмов",    "desc": "100 принятых приёмов"},
    {"code": "streak_30",  "icon": "🏆", "title": "Месяц дисциплины", "desc": "30 идеальных дней подряд"},
    {"code": "adh_90",     "icon": "🛡️", "title": "Надёжный квартал", "desc": "≥90% соблюдения за 90 дней"},
    {"code": "care_first", "icon": "🤝", "title": "Вместе",           "desc": "Первая связь «Забота»"},
    {"code": "intake_500", "icon": "👑", "title": "Пятьсот приёмов",  "desc": "500 принятых приёмов"},
    {"code": "streak_100", "icon": "💎", "title": "Сотня дней",       "desc": "100 идеальных дней подряд"},
]

# Минимум положенных приёмов в окне, чтобы % соблюдения был осмысленным
# (защита от анлока «90% за месяц» у юзера с 1 идеальным днём истории).
_MIN_DUE_30 = 20
_MIN_DUE_90 = 60


def evaluate(*, best_streak: int, adh30, due30: int, adh90, due90: int,
             total_taken: int, has_care_link: bool) -> set:
    """Множество заслуженных кодов по метрикам.

    best_streak — лучшая серия за историю (бейджи серии перманентны → берём пик);
    adh30/adh90 — % соблюдения (int|None) с числом положенных due30/due90 (гейт);
    total_taken — всего приёмов taken; has_care_link — есть активная связь «Забота».
    """
    earned = set()
    if total_taken >= 10:
        earned.add("intake_10")
    if total_taken >= 100:
        earned.add("intake_100")
    if total_taken >= 500:
        earned.add("intake_500")
    if best_streak >= 7:
        earned.add("streak_7")
    if best_streak >= 30:
        earned.add("streak_30")
    if best_streak >= 100:
        earned.add("streak_100")
    if adh30 is not None and adh30 >= 90 and due30 >= _MIN_DUE_30:
        earned.add("adh_30")
    if adh90 is not None and adh90 >= 90 and due90 >= _MIN_DUE_90:
        earned.add("adh_90")
    if has_care_link:
        earned.add("care_first")
    return earned
