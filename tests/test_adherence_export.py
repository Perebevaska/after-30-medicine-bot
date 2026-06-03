"""Smoke-тест PDF-экспорта adherence (F3): reports.build_adherence_pdf на временной БД.

После F10-D рендер живёт в reports.build_adherence_pdf (BytesIO|None); бот-хендлер удалён.
"""
import pytest

WIDE = ("2000-01-01 00:00:00", "2100-01-01 00:00:00")


@pytest.fixture
def env(db):
    import reports
    return db, reports


def test_export_sends_pdf(env):
    d, reports = env
    uid = d.get_or_create_user(9101, "u")
    mid = d.add_medication(uid, "Аспирин", "100мг", "after", 1)
    d.add_schedule_rule(mid, "09:00", "daily")
    d.log_intake(mid, "09:00", "taken", *WIDE)

    buf = reports.build_adherence_pdf(9101)
    assert buf is not None
    assert buf.getvalue()[:4] == b"%PDF"          # валидная PDF-сигнатура


def test_export_no_meds_replies_text(env):
    d, reports = env
    d.get_or_create_user(9102, "u")
    assert reports.build_adherence_pdf(9102) is None
