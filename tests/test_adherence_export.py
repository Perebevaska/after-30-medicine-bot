"""Smoke-тест PDF-экспорта adherence (F3): export.export_adherence на временной БД."""
import asyncio

import pytest


def run(coro):
    return asyncio.run(coro)


class FakeMessage:
    def __init__(self):
        self.replies = []
        self.documents = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)

    async def reply_document(self, document=None, filename=None, caption=None, **kw):
        self.documents.append((filename, document.getvalue() if document else b"", caption))


class FakeQuery:
    def __init__(self, data="export:adherence"):
        self.data = data
        self.message = FakeMessage()

    async def answer(self, *a, **kw):
        pass


class FakeUser:
    def __init__(self, uid):
        self.id = uid
        self.username = "u"


class FakeUpdate:
    def __init__(self, uid):
        self.callback_query = FakeQuery()
        self.effective_user = FakeUser(uid)


WIDE = ("2000-01-01 00:00:00", "2100-01-01 00:00:00")


@pytest.fixture
def env(tmp_path, monkeypatch):
    import database as d
    monkeypatch.setattr(d, "DB_PATH", str(tmp_path / "test.db"))
    d.init_db()
    d.migrate()
    import handlers.export as export
    return d, export


def test_export_sends_pdf(env):
    d, export = env
    uid = d.get_or_create_user(9101, "u")
    mid = d.add_medication(uid, "Аспирин", "100мг", "after", 1)
    d.add_schedule_rule(mid, "09:00", "daily")
    d.log_intake(mid, "09:00", "taken", *WIDE)

    upd = FakeUpdate(9101)
    run(export.export_adherence(upd, None))

    docs = upd.callback_query.message.documents
    assert len(docs) == 1
    filename, content, caption = docs[0]
    assert filename.startswith("adherence_") and filename.endswith(".pdf")
    assert content[:4] == b"%PDF"          # валидная PDF-сигнатура
    assert "Соблюдение" in caption


def test_export_no_meds_replies_text(env):
    d, export = env
    d.get_or_create_user(9102, "u")
    upd = FakeUpdate(9102)
    run(export.export_adherence(upd, None))
    assert upd.callback_query.message.documents == []
    assert any("Нет активных лекарств" in r for r in upd.callback_query.message.replies)
