"""Аудит безопасности 2026-06-02: защита API от модифицированного Telegram-клиента.

SEC-1 auth fail-closed; SEC-2 длины/лимиты medications; SEC-3 числа stock;
SEC-4 валидация settings; SEC-5 лимит dependents.
"""
import pytest


# ── SEC-1: пустой токен не должен валидировать подпись ───────────────────────

def test_verify_init_data_rejects_empty_token():
    from api.auth import verify_init_data
    with pytest.raises(ValueError):
        verify_init_data("user=%7B%22id%22%3A1%7D&hash=deadbeef", "")


# ── SEC-2: лимиты строк/списков medications ──────────────────────────────────

def _med_body(**over):
    body = {
        "name": "Аспирин", "dosage": "100мг", "meal_relation": "any",
        "times_per_day": 1, "rules": [{"reminder_time": "09:00", "frequency": "daily"}],
    }
    body.update(over)
    return body


def test_med_name_too_long_rejected(api_client, db):
    db.get_or_create_user(77001)
    r = api_client.post("/medications", json=_med_body(name="Я" * 200))
    assert r.status_code == 422


def test_med_too_many_rules_rejected(api_client, db):
    db.get_or_create_user(77001)
    rules = [{"reminder_time": "09:00", "frequency": "daily"} for _ in range(50)]
    r = api_client.post("/medications", json=_med_body(rules=rules))
    assert r.status_code == 422


def test_med_empty_rules_allowed(api_client, db):
    # A1: лекарство-упаковка можно создать без расписания (приёмы добавят позже).
    db.get_or_create_user(77001)
    r = api_client.post("/medications", json=_med_body(rules=[]))
    assert r.status_code == 201


def test_med_times_per_day_out_of_range(api_client, db):
    db.get_or_create_user(77001)
    r = api_client.post("/medications", json=_med_body(times_per_day=10_000))
    assert r.status_code == 422


def test_med_duplicate_rules_rejected(api_client, db):
    # #1: два одинаковых приёма (время+частота) схлопнулись бы в один слот intake_log
    # и тикались бы разом — запрещаем на входе.
    db.get_or_create_user(77001)
    dup = [{"reminder_time": "09:00", "frequency": "daily"},
           {"reminder_time": "09:00", "frequency": "daily"}]
    r = api_client.post("/medications", json=_med_body(times_per_day=2, rules=dup))
    assert r.status_code == 422


# ── SEC-3: числа stock ───────────────────────────────────────────────────────

def _make_med(api_client):
    r = api_client.post("/medications", json=_med_body())
    return r.json()["id"]


def test_stock_negative_rejected(api_client, db):
    db.get_or_create_user(77001)
    mid = _make_med(api_client)
    r = api_client.put(f"/medications/{mid}/stock", json={"qty": -5})
    assert r.status_code == 422


def test_stock_huge_rejected(api_client, db):
    db.get_or_create_user(77001)
    mid = _make_med(api_client)
    r = api_client.put(f"/medications/{mid}/stock", json={"qty": 1e12})
    assert r.status_code == 422


def test_stock_units_zero_rejected(api_client, db):
    db.get_or_create_user(77001)
    mid = _make_med(api_client)
    r = api_client.put(f"/medications/{mid}/stock/units", json={"units": 0})
    assert r.status_code == 422


# ── SEC-4: settings ──────────────────────────────────────────────────────────

def test_reminder_mode_invalid_rejected(api_client, db):
    db.get_or_create_user(77001)
    r = api_client.put("/settings/reminder-mode", json={"mode": " haxx"})
    assert r.status_code == 422


def test_preset_unknown_slot_rejected(api_client, db):
    db.get_or_create_user(77001)
    r = api_client.put("/settings/presets/evilslot", json={"time": "09:00"})
    assert r.status_code == 400


def test_preset_bad_time_rejected(api_client, db):
    db.get_or_create_user(77001)
    r = api_client.put("/settings/presets/morning", json={"time": "25:99"})
    assert r.status_code == 422


# ── SEC-5: лимит dependents ──────────────────────────────────────────────────

def test_dependents_limit_enforced(api_client, db):
    from constants import MAX_DEPENDENTS
    db.get_or_create_user(77001)
    for i in range(MAX_DEPENDENTS):
        r = api_client.post("/dependents", json={"name": f"Подопечный {i}"})
        assert r.status_code == 201
    r = api_client.post("/dependents", json={"name": "Лишний"})
    assert r.status_code == 400


def test_dependent_long_name_rejected(api_client, db):
    db.get_or_create_user(77001)
    r = api_client.post("/dependents", json={"name": "Я" * 100})
    assert r.status_code == 422
