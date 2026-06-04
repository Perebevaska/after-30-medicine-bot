"""AX1: UNIQUE(medication_id, scheduled_time, UTC-день) + ON CONFLICT.

Защита от дублей intake_log при параллельных отметках приёма.
"""


def test_intake_log_unique_slot_day(db):
    uid = db.get_or_create_user(123)
    mid = db.add_medication(uid, "A", "1 таб", "any", 1)

    # Имитация гонки: два INSERT одного слота в один UTC-день минуя SELECT-ветку
    # log_intake. ON CONFLICT должен схлопнуть их в одну строку (последняя выигрывает).
    with db.get_connection() as conn:
        for st in ("taken", "skipped"):
            conn.execute(
                """INSERT INTO intake_log (medication_id, scheduled_time, status, taken_at)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (medication_id, scheduled_time, (LEFT(taken_at, 10)))
                   DO UPDATE SET status = EXCLUDED.status, taken_at = EXCLUDED.taken_at""",
                (mid, "09:00", st, "2026-06-02 10:00:00"),
            )
        rows = conn.execute(
            "SELECT status FROM intake_log WHERE medication_id = %s AND scheduled_time = %s",
            (mid, "09:00"),
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["status"] == "skipped"


def test_apply_intake_stock_no_lost_update(db):
    """AX2: параллельные списания запаса не теряются (FOR UPDATE)."""
    import threading

    uid = db.get_or_create_user(125)
    mid = db.add_medication(uid, "C", "1 таб", "any", 1)
    db.set_medication_stock(mid, uid, 10)
    db.set_units_per_dose(mid, uid, 1)

    n = 5
    barrier = threading.Barrier(n)

    def worker():
        barrier.wait()  # стартуем одновременно — максимизируем гонку
        db.apply_intake_stock(mid, "taken", None)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with db.get_connection() as conn:
        qty = conn.execute(
            "SELECT stock_qty FROM medications WHERE id = %s", (mid,)
        ).fetchone()["stock_qty"]
    assert qty == 10 - n  # каждое списание учтено, без потерь


def test_intake_log_distinct_days_kept(db):
    """Разные UTC-дни того же слота — отдельные строки (индекс не мешает)."""
    uid = db.get_or_create_user(124)
    mid = db.add_medication(uid, "B", "1 таб", "any", 1)
    with db.get_connection() as conn:
        for day in ("2026-06-01", "2026-06-02"):
            conn.execute(
                """INSERT INTO intake_log (medication_id, scheduled_time, status, taken_at)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (medication_id, scheduled_time, (LEFT(taken_at, 10)))
                   DO UPDATE SET status = EXCLUDED.status""",
                (mid, "09:00", "taken", f"{day} 10:00:00"),
            )
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM intake_log WHERE medication_id = %s", (mid,)
        ).fetchone()["n"]
    assert n == 2
