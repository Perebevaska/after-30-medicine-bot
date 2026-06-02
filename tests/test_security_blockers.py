"""Регрессия на блокеры аудита 2026-06-02.

S1 — IDOR в боте: handle_intake_callback не должен писать в чужой intake_log/запас.
S2 — IDOR в API: create_medication не должен принимать чужой dependent_id.
"""
import asyncio

import pytest

from tests.conftest import TEST_TELEGRAM_ID


def run(coro):
    return asyncio.run(coro)


# ── Fakes для Telegram (S1) ──────────────────────────────────────────────────

class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.message = FakeMessage()
        self.edited = []

    async def answer(self, *a, **kw):
        pass

    async def edit_message_text(self, text, **kw):
        self.edited.append(text)


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeUpdate:
    def __init__(self, query, uid):
        self.callback_query = query
        self.effective_user = FakeUser(uid)


# ── S1: чужой callback отклоняется ───────────────────────────────────────────

def test_s1_foreign_callback_rejected(db):
    """Атакующий отправляет taken: на лекарство владельца — запись не происходит."""
    import scheduler
    owner_uid = db.get_or_create_user(7001, "owner")
    mid = db.add_medication(owner_uid, "Аспирин", "100мг", "after", 1)
    db.add_schedule_rule(mid, "09:00", "daily")
    db.set_medication_stock(mid, owner_uid, 10)

    attacker_id = 9999  # не владелец
    q = FakeQuery(f"taken:{mid}:09:00")
    run(scheduler.handle_intake_callback(FakeUpdate(q, attacker_id), None))

    # запас не тронут, ничего не отвечено пользователю
    assert db.get_medication_by_id(mid, owner_uid)["stock_qty"] == 10
    assert q.edited == []
    assert q.message.replies == []


def test_s1_owner_callback_still_works(db):
    """Контроль: владелец по-прежнему может отметить приём."""
    import scheduler
    owner_uid = db.get_or_create_user(7001, "owner")
    mid = db.add_medication(owner_uid, "Аспирин", "100мг", "after", 1)
    db.add_schedule_rule(mid, "09:00", "daily")
    db.set_medication_stock(mid, owner_uid, 10)

    q = FakeQuery(f"taken:{mid}:09:00")
    run(scheduler.handle_intake_callback(FakeUpdate(q, 7001), None))

    assert db.get_medication_by_id(mid, owner_uid)["stock_qty"] == 9
    assert q.edited and "записан" in q.edited[-1]


# ── S2: чужой dependent_id отклоняется ───────────────────────────────────────

def test_s2_foreign_dependent_rejected(api_client, db):
    """Нельзя привязать лекарство к подопечному другого пользователя."""
    db.get_or_create_user(TEST_TELEGRAM_ID, "testuser")
    other_uid = db.get_or_create_user(88888, "other")
    foreign_dep = db.add_dependent(88888, "Бабушка")

    r = api_client.post("/medications", json={
        "name": "Аспирин", "dosage": "100мг", "meal_relation": "after",
        "times_per_day": 1, "dependent_id": foreign_dep,
        "rules": [{"reminder_time": "09:00", "frequency": "daily"}],
    })
    assert r.status_code == 404


def test_s2_own_dependent_allowed(api_client, db):
    """Контроль: к своему подопечному лекарство привязывается."""
    db.get_or_create_user(TEST_TELEGRAM_ID, "testuser")
    own_dep = db.add_dependent(TEST_TELEGRAM_ID, "Дочь")

    r = api_client.post("/medications", json={
        "name": "Аспирин", "dosage": "100мг", "meal_relation": "after",
        "times_per_day": 1, "dependent_id": own_dep,
        "rules": [{"reminder_time": "09:00", "frequency": "daily"}],
    })
    assert r.status_code == 201


# ── S3: повторный get_or_create_user не затирает username ─────────────────────

def test_s3_username_preserved(db):
    """Вызов без username (как из API) не должен обнулять сохранённый username."""
    uid = db.get_or_create_user(7001, "ivan")
    same = db.get_or_create_user(7001)  # без username — типичный API-вызов
    assert same == uid
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT username FROM users WHERE telegram_id = %s", (7001,)
        ).fetchone()
    assert row["username"] == "ivan"


# ── B5: серверная валидация правил расписания ────────────────────────────────

def _post_med(api_client, rule):
    return api_client.post("/medications", json={
        "name": "Аспирин", "dosage": "100мг", "meal_relation": "after",
        "times_per_day": 1, "rules": [rule],
    })


def test_b5_bad_reminder_time(api_client, db):
    db.get_or_create_user(TEST_TELEGRAM_ID, "testuser")
    r = _post_med(api_client, {"reminder_time": "25:99", "frequency": "daily"})
    assert r.status_code == 422


def test_b5_interval_without_anchor(api_client, db):
    db.get_or_create_user(TEST_TELEGRAM_ID, "testuser")
    r = _post_med(api_client, {
        "reminder_time": "09:00", "frequency": "interval", "interval_days": 2,
    })
    assert r.status_code == 422


def test_b5_bad_month_day(api_client, db):
    db.get_or_create_user(TEST_TELEGRAM_ID, "testuser")
    r = _post_med(api_client, {
        "reminder_time": "09:00", "frequency": "monthly", "month_day": 40,
    })
    assert r.status_code == 422


def test_b5_valid_interval_accepted(api_client, db):
    db.get_or_create_user(TEST_TELEGRAM_ID, "testuser")
    r = _post_med(api_client, {
        "reminder_time": "09:00", "frequency": "interval",
        "interval_days": 2, "anchor_date": "2026-06-01",
    })
    assert r.status_code == 201
