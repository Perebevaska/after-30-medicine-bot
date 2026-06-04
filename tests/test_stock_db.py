"""DB-тесты учёта запаса (F5) на временной БД (monkeypatch database.DB_PATH)."""
import importlib

import pytest



def _med(d):
    uid = d.get_or_create_user(555001, "stock")
    mid = d.add_medication(uid, "Аспирин", "100мг", "after", 1)
    return d, uid, mid


def test_defaults(db):
    d, uid, mid = _med(db)
    m = d.get_medication_by_id(mid, uid)
    assert m["stock_qty"] is None          # трекинг выключен по умолчанию
    assert m["units_per_dose"] == 1
    assert m["low_stock_days"] == 5


def test_set_and_add_stock(db):
    d, uid, mid = _med(db)
    d.set_medication_stock(mid, uid, 30)
    assert d.get_medication_by_id(mid, uid)["stock_qty"] == 30
    d.add_medication_stock(mid, uid, 20)
    assert d.get_medication_by_id(mid, uid)["stock_qty"] == 50


def test_add_stock_from_disabled(db):
    d, uid, mid = _med(db)
    d.add_medication_stock(mid, uid, 10)   # был NULL → 0 + 10
    assert d.get_medication_by_id(mid, uid)["stock_qty"] == 10


def test_units_and_threshold(db):
    d, uid, mid = _med(db)
    d.set_units_per_dose(mid, uid, 2)
    d.set_low_stock_days(mid, uid, 7)
    m = d.get_medication_by_id(mid, uid)
    assert m["units_per_dose"] == 2 and m["low_stock_days"] == 7


def test_apply_intake_stock_off_returns_none(db):
    d, uid, mid = _med(db)
    assert d.apply_intake_stock(mid, "taken", None) is None   # трекинг выключен


def test_apply_intake_decrement_and_refund(db):
    d, uid, mid = _med(db)
    d.set_medication_stock(mid, uid, 10)
    d.set_units_per_dose(mid, uid, 2)

    r = d.apply_intake_stock(mid, "taken", None)
    assert r["changed"] and r["stock_qty"] == 8

    # повторный taken — без изменений (идемпотентно)
    r = d.apply_intake_stock(mid, "taken", "taken")
    assert not r["changed"] and r["stock_qty"] == 8

    # taken → skipped — возврат
    r = d.apply_intake_stock(mid, "skipped", "taken")
    assert r["changed"] and r["stock_qty"] == 10


def test_apply_intake_per_rule_dose(db):
    # Поприёмная доза: правило в 09:00 со своей dosage "250 мг" при дозировке
    # 1 ед = 500 мг → списываем 250/500 = 0.5 ед, а не общую units_per_dose.
    d = db
    uid = d.get_or_create_user(555099, "perdose")
    mid = d.add_medication(uid, "Аспирин", "500 мг", "after", 1,
                           unit_dose_value=500, dose_per_intake=500, pack_size=10)
    d.add_schedule_rule(mid, "09:00", "daily", dosage="250 мг")
    r = d.apply_intake_stock(mid, "taken", None, "09:00")
    assert r["changed"] and r["stock_qty"] == 9.5
    # Правило без своей dosage → общая units_per_dose (тут 1)
    d.add_schedule_rule(mid, "21:00", "daily")
    r = d.apply_intake_stock(mid, "taken", None, "21:00")
    assert r["stock_qty"] == 8.5


def test_apply_intake_clamps_at_zero(db):
    d, uid, mid = _med(db)
    d.set_medication_stock(mid, uid, 1)
    d.set_units_per_dose(mid, uid, 2)
    r = d.apply_intake_stock(mid, "taken", None)
    assert r["stock_qty"] == 0   # не уходит в минус


def test_disable_tracking(db):
    d, uid, mid = _med(db)
    d.set_medication_stock(mid, uid, 5)
    d.disable_stock_tracking(mid, uid)
    assert d.get_medication_by_id(mid, uid)["stock_qty"] is None


def test_log_intake_returns_old_status(db):
    d, uid, mid = _med(db)
    lo, hi = "2000-01-01 00:00:00", "2100-01-01 00:00:00"
    assert d.log_intake(mid, "09:00", "taken", lo, hi) is None      # новая запись
    assert d.log_intake(mid, "09:00", "skipped", lo, hi) == "taken"  # прежний статус
    assert d.log_intake(mid, "09:00", "taken", lo, hi) == "skipped"


# ── A1: новая модель упаковки/дозы/курса ────────────────────────────────────

def test_compute_units_per_dose(db):
    d = db
    assert d.compute_units_per_dose(250, 500) == 0.5   # аспирин: полтаблетки
    assert d.compute_units_per_dose(500, 500) == 1
    assert d.compute_units_per_dose(None, 500) == 1     # нет назначенной дозы
    assert d.compute_units_per_dose(250, None) == 1     # нет дозировки 1 ед.
    assert d.compute_units_per_dose(250, 0) == 1        # защита от деления на 0


def test_add_medication_package_fields(db):
    d = db
    uid = d.get_or_create_user(555010, "pkg")
    mid = d.add_medication(
        uid, "Аспирин", "250 мг", "after", 1,
        unit_dose_value=500, unit_dose_label="мг",
        dose_per_intake=250, pack_size=10, course_total=20,
    )
    m = d.get_medication_by_id(mid, uid)
    assert m["unit_dose_value"] == 500
    assert m["dose_per_intake"] == 250
    assert m["pack_size"] == 10
    assert m["course_total"] == 20
    assert m["units_per_dose"] == 0.5        # 250/500
    assert m["stock_qty"] == 10              # pack_size → стартовый остаток


def test_add_medication_no_package_off(db):
    d = db
    uid = d.get_or_create_user(555011, "nopkg")
    mid = d.add_medication(uid, "Витамин", "1 таб", "any", 1)
    m = d.get_medication_by_id(mid, uid)
    assert m["stock_qty"] is None            # без pack_size учёт выключен
    assert m["units_per_dose"] == 1


def test_half_tablet_decrement(db):
    d = db
    uid = d.get_or_create_user(555012, "half")
    mid = d.add_medication(
        uid, "Аспирин", "250 мг", "after", 1,
        unit_dose_value=500, dose_per_intake=250, pack_size=10,
    )
    r = d.apply_intake_stock(mid, "taken", None)
    assert r["stock_qty"] == 9.5             # списали полтаблетки


def test_course_progress_and_continue(db):
    d = db
    uid = d.get_or_create_user(555013, "course")
    mid = d.add_medication(uid, "Курс", "1 таб", "any", 1, course_total=3)
    lo, hi = "2000-01-01 00:00:00", "2100-01-01 00:00:00"
    assert d.get_course_progress(mid) == 0
    d.log_intake(mid, "09:00", "taken", lo, hi)
    d.log_intake(mid, "12:00", "taken", lo, hi)
    assert d.get_course_progress(mid) == 2
    # «продолжить» — снять лимит
    d.set_course_total(mid, uid, None)
    assert d.get_medication_by_id(mid, uid)["course_total"] is None


def test_update_medication_recomputes_units(db):
    d = db
    uid = d.get_or_create_user(555014, "upd")
    mid = d.add_medication(uid, "Аспирин", "500 мг", "after", 1,
                           unit_dose_value=500, dose_per_intake=500, pack_size=10)
    assert d.get_medication_by_id(mid, uid)["units_per_dose"] == 1
    d.update_medication(mid, uid, "Аспирин", "250 мг", "after", 1,
                        [{"reminder_time": "09:00", "frequency": "daily"}],
                        unit_dose_value=500, dose_per_intake=250, pack_size=10)
    assert d.get_medication_by_id(mid, uid)["units_per_dose"] == 0.5
