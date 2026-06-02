"""Smoke-тест экрана adherence (F3): склейка stats.show_adherence на временной БД."""
import asyncio

import pytest


def run(coro):
    return asyncio.run(coro)


class FakeQuery:
    def __init__(self, data="stats:adherence"):
        self.data = data
        self.edited = []

    async def answer(self, *a, **kw):
        pass

    async def edit_message_text(self, text, **kw):
        self.edited.append(text)


class FakeUser:
    def __init__(self, uid):
        self.id = uid
        self.username = "u"


class FakeUpdate:
    def __init__(self, uid):
        self.callback_query = FakeQuery()
        self.effective_user = FakeUser(uid)


@pytest.fixture
def env(db):
    import handlers.stats as stats
    return db, stats


WIDE = ("2000-01-01 00:00:00", "2100-01-01 00:00:00")


def test_no_active_meds(env):
    d, stats = env
    d.get_or_create_user(9001, "u")
    upd = FakeUpdate(9001)
    run(stats.show_adherence(upd, None))
    assert "Нет активных лекарств" in upd.callback_query.edited[-1]


def test_adherence_reports_taken_and_missed(env):
    d, stats = env
    uid = d.get_or_create_user(9002, "u")          # timezone по умолчанию UTC
    m_ok = d.add_medication(uid, "Аспирин", "100мг", "after", 1)
    d.add_schedule_rule(m_ok, "09:00", "daily")
    m_bad = d.add_medication(uid, "Витамин", "1т", "any", 1)
    d.add_schedule_rule(m_bad, "10:00", "daily")
    # лекарства созданы сегодня → знаменатель = 1 приём за сегодня у каждого
    d.log_intake(m_ok, "09:00", "taken", *WIDE)
    d.log_intake(m_bad, "10:00", "skipped", *WIDE)

    upd = FakeUpdate(9002)
    run(stats.show_adherence(upd, None))
    text = upd.callback_query.edited[-1]
    assert "Соблюдение за 30 дней" in text
    assert "Аспирин" in text and "100% (1/1)" in text
    assert "Витамин" in text and "0% (0/1)" in text
    assert "Итог: 1/2 (50%)" in text


def test_pct_color_thresholds(env):
    _, stats = env
    assert stats._pct_color(80) == "🟢"
    assert stats._pct_color(79) == "🟡"
    assert stats._pct_color(50) == "🟡"
    assert stats._pct_color(49) == "🔴"
