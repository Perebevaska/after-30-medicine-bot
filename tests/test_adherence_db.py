"""DB-слой adherence (F3): правила для знаменателя + числитель taken на временной БД."""
import pytest



WIDE = ("2000-01-01 00:00:00", "2100-01-01 00:00:00")  # диапазон, покрывающий CURRENT_TIMESTAMP


def test_adherence_rules_only_active_and_has_created(db):
    d = db
    uid = d.get_or_create_user(7001, "u")
    mid = d.add_medication(uid, "Аспирин", "100мг", "after", 2)
    d.add_schedule_rule(mid, "09:00", "daily")
    d.add_schedule_rule(mid, "21:00", "daily")
    # неактивное лекарство в выборку не попадает
    mid2 = d.add_medication(uid, "Старое", "1", "any", 1)
    d.add_schedule_rule(mid2, "08:00", "daily")
    d.deactivate_medication(mid2, uid)

    rules = d.get_adherence_rules(uid)
    assert {r["medication_id"] for r in rules} == {mid}
    assert len(rules) == 2                       # два правила активного лекарства
    assert all(r["created_at"] for r in rules)   # created_at присутствует
    assert rules[0]["name"] == "Аспирин"


def test_taken_counts_counts_only_taken(db):
    d = db
    uid = d.get_or_create_user(7002, "u")
    mid = d.add_medication(uid, "X", "1", "any", 2)
    d.add_schedule_rule(mid, "09:00", "daily")
    d.add_schedule_rule(mid, "21:00", "daily")

    d.log_intake(mid, "09:00", "taken", *WIDE)
    d.log_intake(mid, "21:00", "skipped", *WIDE)   # не считается

    assert d.get_taken_counts(uid, *WIDE) == {mid: 1}


def test_taken_counts_respects_range(db):
    d = db
    uid = d.get_or_create_user(7003, "u")
    mid = d.add_medication(uid, "X", "1", "any", 1)
    d.add_schedule_rule(mid, "09:00", "daily")
    d.log_intake(mid, "09:00", "taken", *WIDE)
    # диапазон в прошлом — приёма нет
    assert d.get_taken_counts(uid, "2000-01-01 00:00:00", "2000-01-02 00:00:00") == {}


def test_taken_counts_isolated_per_user(db):
    d = db
    a = d.get_or_create_user(7101, "a")
    b = d.get_or_create_user(7102, "b")
    ma = d.add_medication(a, "A", "1", "any", 1); d.add_schedule_rule(ma, "09:00", "daily")
    mb = d.add_medication(b, "B", "1", "any", 1); d.add_schedule_rule(mb, "09:00", "daily")
    d.log_intake(ma, "09:00", "taken", *WIDE)
    d.log_intake(mb, "09:00", "taken", *WIDE)
    assert d.get_taken_counts(a, *WIDE) == {ma: 1}
    assert d.get_taken_counts(b, *WIDE) == {mb: 1}
