"""F1 — PDF «Отчёт для врача» (календарь приверженности): рендер и пустые случаи.

После F10-D рендер живёт в reports.build_doctor_pdf (builder возвращает BytesIO|None);
бот-хендлер удалён.
"""
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def env(db):
    import reports
    return db, reports


def _log(d, mid, days_ago, status):
    """Прямая вставка записи intake_log с taken_at N дней назад (UTC)."""
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
    with d.get_connection() as conn:
        conn.execute(
            "INSERT INTO intake_log (medication_id, scheduled_time, status, taken_at) VALUES (%s, %s, %s, %s)",
            (mid, "09:00", status, ts))


def test_doctor_report_pdf_generated(env):
    d, reports = env
    uid = d.get_or_create_user(6001, "patient")
    m1 = d.add_medication(uid, "Аспирин", "100мг", "after", 1)
    d.add_schedule_rule(m1, "09:00", "daily")
    m2 = d.add_medication(uid, "Витамин D", "1т", "any", 1)
    d.add_schedule_rule(m2, "09:00", "daily")
    # разноцветные дни: часть принято, часть пропущено
    for da in range(0, 10):
        _log(d, m1, da, "taken" if da % 2 == 0 else "skipped")
        _log(d, m2, da, "taken")

    buf = reports.build_doctor_pdf(6001, "@patient")
    assert buf is not None
    content = buf.getvalue()
    assert content[:4] == b"%PDF"
    assert len(content) > 1500           # непустой календарь


def test_doctor_report_no_meds(env):
    d, reports = env
    d.get_or_create_user(6002, "patient")
    assert reports.build_doctor_pdf(6002, "@patient") is None


def test_doctor_report_paused_excluded(env):
    """Лекарство на паузе не попадает в отчёт (как и в adherence)."""
    d, reports = env
    uid = d.get_or_create_user(6003, "patient")
    mid = d.add_medication(uid, "Магний", "1", "any", 1)
    d.add_schedule_rule(mid, "09:00", "daily")
    d.set_medication_paused(mid, uid, True)
    # единственное лекарство на паузе → нечего показывать
    assert reports.build_doctor_pdf(6003, "@patient") is None
