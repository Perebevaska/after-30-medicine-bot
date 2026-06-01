"""Характеризационные тесты save-хендлеров meds.py.

Фиксируют текст сообщений «✅ Лекарство добавлено/обновлено» и логику
валидации числовых диапазонов — как страховка перед дедупликацией (Q1).
БД и Telegram заменены фейками; функции БД мокаются в namespace handlers.meds.
"""
import asyncio

import pytest

import handlers.meds as m
from constants import (
    FREQ_INTERVAL, FREQ_MONTHDAY, EDIT_FREQ_INTERVAL, EDIT_FREQ_MONTHDAY,
)
from telegram.ext import ConversationHandler


def run(coro):
    return asyncio.run(coro)


# ── Фейки Telegram ──────────────────────────────────────────────────────────

class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)
        return self


class FakeQuery:
    def __init__(self, data=""):
        self.data = data
        self.message = FakeMessage()
        self.edits = []

    async def answer(self, *a, **kw):
        pass

    async def edit_message_text(self, text, **kw):
        self.edits.append(text)

    async def edit_message_reply_markup(self, **kw):
        pass


class FakeUser:
    def __init__(self, id=123, username="u", first_name="U"):
        self.id = id
        self.username = username
        self.first_name = first_name


class FakeUpdate:
    def __init__(self, message=None, callback_query=None, user=None):
        self.message = message
        self.callback_query = callback_query
        self.effective_user = user or FakeUser()


class FakeContext:
    def __init__(self, user_data=None):
        self.user_data = user_data or {}


# ── Мок БД ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db(monkeypatch):
    calls = {"add_medication": [], "add_schedule_rule": [], "update_medication": []}

    def fake_add_medication(*a, **kw):
        calls["add_medication"].append((a, kw))
        return 42

    monkeypatch.setattr(m, "get_or_create_user", lambda *a, **kw: 1)
    monkeypatch.setattr(m, "count_active_medications", lambda *a, **kw: 0)
    monkeypatch.setattr(m, "add_medication", fake_add_medication)
    monkeypatch.setattr(m, "add_schedule_rule",
                        lambda *a, **kw: calls["add_schedule_rule"].append((a, kw)))
    monkeypatch.setattr(m, "update_medication",
                        lambda *a, **kw: calls["update_medication"].append((a, kw)))
    return calls


def _add_ud():
    return {
        "_add_user_id": 1,
        "name": "Аспирин",
        "dosage": "100мг",
        "meal": "after",
        "collected_times": ["09:00", "21:00"],
    }


def _edit_ud():
    return {
        "edit_user_id": 1,
        "edit_id": 7,
        "edit_name": "Аспирин",
        "edit_dosage": "100мг",
        "edit_meal": "after",
        "edit_collected": ["09:00", "21:00"],
    }


HEAD = "✅ Лекарство {act}!\n\n💊 Аспирин — 100мг\n🍽 После еды\n🔢 2 раз в день\n⏰ "


# ── ADD save paths ──────────────────────────────────────────────────────────

def test_add_daily_text(mock_db):
    q = FakeQuery(data="freq:daily")
    ctx = FakeContext(_add_ud())
    state = run(m.choose_freq_type(FakeUpdate(callback_query=q), ctx))
    assert state == ConversationHandler.END
    assert q.edits[-1] == HEAD.format(act="добавлено") + "09:00, 21:00"
    assert len(mock_db["add_schedule_rule"]) == 2


def test_add_interval_text(mock_db):
    msg = FakeMessage(text="3")
    ctx = FakeContext(_add_ud())
    state = run(m.add_freq_interval(FakeUpdate(message=msg), ctx))
    assert state == ConversationHandler.END
    assert msg.replies[-1] == HEAD.format(act="добавлено") + "09:00, 21:00 — каждые 3 дн."


def test_add_weekdays_text(mock_db):
    q = FakeQuery(data="weekdays_confirm")
    ud = _add_ud()
    ud["freq_weekdays"] = {1, 3, 5}
    state = run(m.confirm_weekdays(FakeUpdate(callback_query=q), FakeContext(ud)))
    assert state == ConversationHandler.END
    assert q.edits[-1] == HEAD.format(act="добавлено") + "09:00, 21:00 — Пн, Ср, Пт"


def test_add_monthday_text(mock_db):
    msg = FakeMessage(text="15")
    state = run(m.add_freq_monthday(FakeUpdate(message=msg), FakeContext(_add_ud())))
    assert state == ConversationHandler.END
    assert msg.replies[-1] == HEAD.format(act="добавлено") + "09:00, 21:00 — 15-го числа"


# ── EDIT save paths ─────────────────────────────────────────────────────────

def test_edit_daily_text(mock_db):
    q = FakeQuery()
    ud = _edit_ud()
    ud["edit_freq_type"] = "daily"
    state = run(m._route_after_edit_meal(q, FakeContext(ud)))
    assert state == ConversationHandler.END
    assert q.edits[-1] == HEAD.format(act="обновлено") + "09:00, 21:00"


def test_edit_interval_text(mock_db):
    msg = FakeMessage(text="3")
    state = run(m.edit_freq_interval(FakeUpdate(message=msg), FakeContext(_edit_ud())))
    assert state == ConversationHandler.END
    assert msg.replies[-1] == HEAD.format(act="обновлено") + "09:00, 21:00 — каждые 3 дн."


def test_edit_weekdays_text(mock_db):
    q = FakeQuery(data="edit_weekdays_confirm")
    ud = _edit_ud()
    ud["edit_freq_weekdays"] = {2, 4}
    state = run(m.confirm_edit_weekdays(FakeUpdate(callback_query=q), FakeContext(ud)))
    assert state == ConversationHandler.END
    assert q.edits[-1] == HEAD.format(act="обновлено") + "09:00, 21:00 — Вт, Чт"


def test_edit_monthday_text(mock_db):
    msg = FakeMessage(text="10")
    state = run(m.edit_freq_monthday(FakeUpdate(message=msg), FakeContext(_edit_ud())))
    assert state == ConversationHandler.END
    assert msg.replies[-1] == HEAD.format(act="обновлено") + "09:00, 21:00 — 10-го числа"


# ── Валидация числовых диапазонов ───────────────────────────────────────────

@pytest.mark.parametrize("bad", ["1", "91", "abc", "", "0"])
def test_add_interval_invalid(mock_db, bad):
    msg = FakeMessage(text=bad)
    state = run(m.add_freq_interval(FakeUpdate(message=msg), FakeContext(_add_ud())))
    assert state == FREQ_INTERVAL
    assert "от 2 до 90" in msg.replies[-1]
    assert not mock_db["add_medication"]


@pytest.mark.parametrize("bad", ["0", "32", "abc", ""])
def test_add_monthday_invalid(mock_db, bad):
    msg = FakeMessage(text=bad)
    state = run(m.add_freq_monthday(FakeUpdate(message=msg), FakeContext(_add_ud())))
    assert state == FREQ_MONTHDAY
    assert "от 1 до 31" in msg.replies[-1]


@pytest.mark.parametrize("bad", ["1", "91", "abc"])
def test_edit_interval_invalid(mock_db, bad):
    msg = FakeMessage(text=bad)
    state = run(m.edit_freq_interval(FakeUpdate(message=msg), FakeContext(_edit_ud())))
    assert state == EDIT_FREQ_INTERVAL
    assert "от 2 до 90" in msg.replies[-1]


@pytest.mark.parametrize("bad", ["0", "32", "abc"])
def test_edit_monthday_invalid(mock_db, bad):
    msg = FakeMessage(text=bad)
    state = run(m.edit_freq_monthday(FakeUpdate(message=msg), FakeContext(_edit_ud())))
    assert state == EDIT_FREQ_MONTHDAY
    assert "от 1 до 31" in msg.replies[-1]


def test_add_monthday_31_warning(mock_db):
    msg = FakeMessage(text="31")
    run(m.add_freq_monthday(FakeUpdate(message=msg), FakeContext(_add_ud())))
    assert "31-го числа" in msg.replies[-1]
    assert "⚠️" in msg.replies[-1]
