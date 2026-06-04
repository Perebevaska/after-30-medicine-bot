"""Демо-наполнение статистики для ADMIN: 3 лекарства + 50 дней приёмов/пропусков.

Назначение — увидеть все модули рефакторинга вкладки «Прогресс» (F11-C):
серии (текущая+лучшая), соблюдение 7/30/90 + график, пунктуальность отметок
(разные отклонения, «проблемный час» = вечер 21:00), нагрузка по терапии.

Идемпотентно: при повторном запуске удаляет ранее засеянные демо-лекарства
(по именам) вместе с их расписанием и журналом и сеет заново.

Запуск:  python seed_admin_stats.py
Пишет в прод-БД (DATABASE_URL) в СОБСТВЕННЫЙ аккаунт админа (dependent_id NULL).
"""
import os
import random
from datetime import datetime, timedelta

import pytz
from dotenv import load_dotenv

import database as db
from utils import get_tz_for_user

load_dotenv()

ADMIN_ID = int(os.environ["ADMIN_ID"])
SEED_NAMES = ["Аспирин Кардио", "Метформин", "Витамин D3"]
DAYS = 50

# (name, times_per_day, [reminder_time...], unit_dose_value, dose_per_intake, pack_size)
MEDS = [
    ("Аспирин Кардио", 1, ["08:00"],          100,  100, 30),
    ("Метформин",      2, ["08:00", "21:00"], 500, 1000, 60),
    ("Витамин D3",     1, ["14:00"],          2000, 2000, 90),
]

# Базовая вероятность пропуска по часу приёма (вечер — самый проблемный)
SKIP_BY_HOUR = {8: 0.08, 14: 0.15, 21: 0.40}


def _cleanup(conn, user_id):
    rows = conn.execute(
        "SELECT id FROM medications WHERE user_id = %s AND name = ANY(%s)",
        (user_id, SEED_NAMES),
    ).fetchall()
    ids = [r["id"] for r in rows]
    if not ids:
        return
    conn.execute("DELETE FROM intake_log WHERE medication_id = ANY(%s)", (ids,))
    conn.execute("DELETE FROM schedule_rules WHERE medication_id = ANY(%s)", (ids,))
    conn.execute("DELETE FROM medications WHERE id = ANY(%s)", (ids,))


def _is_perfect_day(i: int) -> bool:
    """Идеальные дни (все слоты taken): текущая серия 0..5 + лучшая 15..30."""
    return i <= 5 or (15 <= i <= 30)


def main():
    random.seed(42)
    db.init_pool(os.environ["DATABASE_URL"])
    db.migrate()

    user_id = db.get_or_create_user(ADMIN_ID, "admin")
    tz = get_tz_for_user(ADMIN_ID)
    today = datetime.now(tz).date()
    created_at = (datetime.now(pytz.utc) - timedelta(days=DAYS + 1)).strftime("%Y-%m-%d %H:%M:%S")

    with db.get_connection() as conn:
        _cleanup(conn, user_id)

    med_slots = []  # (mid, "HH:MM")
    for name, tpd, times, udv, dpi, pack in MEDS:
        dosage = f"{dpi} мг" if name != "Витамин D3" else "2000 МЕ"
        mid = db.add_medication(
            user_id, name, dosage, "after", tpd,
            unit_dose_value=udv, dose_per_intake=dpi, pack_size=pack,
        )
        for t in times:
            db.add_schedule_rule(mid, t, "daily")
            med_slots.append((mid, t))
        # отодвигаем дату создания, чтобы все 50 дней считались положенными
        with db.get_connection() as conn:
            conn.execute("UPDATE medications SET created_at = %s WHERE id = %s",
                         (created_at, mid))

    rows = []  # (mid, scheduled_time, status, taken_at_utc)
    for i in range(DAYS):                       # i=0 — сегодня, i растёт в прошлое
        day = today - timedelta(days=i)
        perfect = _is_perfect_day(i)
        day_slots = []
        for mid, t in med_slots:
            hh, mm = int(t[:2]), int(t[3:5])
            if perfect:
                status = "taken"
            else:
                p = SKIP_BY_HOUR.get(hh, 0.15) + (i / DAYS) * 0.15   # старее → хуже
                status = "skipped" if random.random() < p else "taken"
            day_slots.append([mid, t, hh, mm, status])
        # гарантия: неп'идеальный' день имеет хотя бы один пропуск (иначе случайно
        # продлил бы серию) — роняем вечерний слот, если все taken
        if not perfect and all(s[4] == "taken" for s in day_slots):
            for s in day_slots:
                if s[2] == 21:
                    s[4] = "skipped"
                    break
            else:
                day_slots[-1][4] = "skipped"

        for mid, t, hh, mm, status in day_slots:
            if status == "taken":
                # отклонение отметки: утро — точнее, вечер — позже и разбросаннее.
                # Диапазон захватывает «раньше» (< −30) для наглядного распределения.
                if hh == 21:
                    delay = random.randint(-50, 110)
                elif hh == 14:
                    delay = random.randint(-45, 60)
                else:
                    delay = random.randint(-40, 35)
            else:
                delay = 0   # авто-skip фиксируется у времени напоминания
            local_dt = tz.localize(datetime(day.year, day.month, day.day, hh, mm)) \
                + timedelta(minutes=delay)
            taken_at = local_dt.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
            rows.append((mid, t, status, taken_at))

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO intake_log (medication_id, scheduled_time, status, taken_at)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                rows,
            )

    taken = sum(1 for r in rows if r[2] == "taken")
    print(f"OK: user_id={user_id}, лекарств={len(MEDS)}, слотов/день={len(med_slots)}, "
          f"записей={len(rows)} (taken={taken}, skipped={len(rows) - taken}) за {DAYS} дней.")
    db.close_pool()


if __name__ == "__main__":
    main()
