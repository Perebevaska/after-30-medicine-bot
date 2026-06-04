"""Ф15 v1 — соцмеханика пожеланий (тестовый функционал за тоглом)."""
import database as db
import wish_presets
from tests.conftest import TEST_TELEGRAM_ID

OTHER_TID = 77002


def _enable(tid):
    """Создаёт юзера (если нет) и включает участие в механике. Возвращает user_id."""
    uid = db.get_or_create_user(tid)
    db.set_wishes_enabled(tid, True)
    return uid


# ── Пресеты (чистый модуль) ─────────────────────────────────────────────────

def test_presets_bands():
    assert wish_presets.band_for_hour(8) == "morning"
    assert wish_presets.band_for_hour(13) == "day"
    assert wish_presets.band_for_hour(20) == "evening"
    assert wish_presets.band_for_hour(2) == "night"
    assert len(wish_presets.presets_for_hour(8)) >= 1


def test_preset_code_validation():
    code = wish_presets.presets_for_hour(13)[0]["code"]
    assert wish_presets.is_valid_code(code)
    assert not wish_presets.is_valid_code("zzz")
    assert wish_presets.text_for_code(code)
    assert wish_presets.text_for_code("zzz") is None


# ── Тогл ────────────────────────────────────────────────────────────────────

def test_toggle_default_off_then_on(api_client, db):
    db.get_or_create_user(TEST_TELEGRAM_ID)
    assert db.is_wishes_enabled(TEST_TELEGRAM_ID) is False
    r = api_client.put("/settings/wishes", json={"enabled": True})
    assert r.status_code == 204
    assert db.is_wishes_enabled(TEST_TELEGRAM_ID) is True
    api_client.put("/settings/wishes", json={"enabled": False})
    assert db.is_wishes_enabled(TEST_TELEGRAM_ID) is False


def test_settings_exposes_flag(api_client, db):
    _enable(TEST_TELEGRAM_ID)
    r = api_client.get("/settings")
    assert r.json().get("wishes_enabled") == 1


# ── Статус / пул ────────────────────────────────────────────────────────────

def test_status_pool_not_ready_alone(api_client, db):
    _enable(TEST_TELEGRAM_ID)
    r = api_client.get("/wishes/status")
    body = r.json()
    assert body["enabled"] is True
    assert len(body["presets"]) >= 1
    assert body["pool_size"] == 1
    assert body["pool_ready"] is False


def test_status_pool_ready_with_two(api_client, db):
    _enable(TEST_TELEGRAM_ID)
    _enable(OTHER_TID)
    body = api_client.get("/wishes/status").json()
    assert body["pool_size"] == 2
    assert body["pool_ready"] is True


# ── Отправка ────────────────────────────────────────────────────────────────

def test_send_requires_enabled(api_client, db):
    db.get_or_create_user(TEST_TELEGRAM_ID)
    r = api_client.post("/wishes/send", json={"preset_code": "m1"})
    assert r.status_code == 403


def test_send_blocked_small_pool(api_client, db):
    _enable(TEST_TELEGRAM_ID)
    r = api_client.post("/wishes/send", json={"preset_code": "m1"})
    assert r.status_code == 400


def test_send_invalid_preset(api_client, db):
    _enable(TEST_TELEGRAM_ID)
    _enable(OTHER_TID)
    r = api_client.post("/wishes/send", json={"preset_code": "nope"})
    assert r.status_code == 422


def test_send_success_to_other(api_client, db):
    sender = _enable(TEST_TELEGRAM_ID)
    recipient = _enable(OTHER_TID)
    r = api_client.post("/wishes/send", json={"preset_code": "m1"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    inbox = db.get_wish_inbox(recipient)
    assert len(inbox) == 1
    assert inbox[0]["preset_code"] == "m1"
    # отправитель — не получатель
    assert db.get_wish_inbox(sender) == []


def test_send_never_self(api_client, db):
    # только сам участник в пуле → получателя нет
    uid = _enable(TEST_TELEGRAM_ID)
    assert db.pick_wish_recipient(uid) is None
    _enable(OTHER_TID)
    assert db.pick_wish_recipient(uid) != uid


def test_daily_limit(api_client, db, monkeypatch):
    _enable(TEST_TELEGRAM_ID)
    _enable(OTHER_TID)
    monkeypatch.setattr(db, "WISH_DAILY_LIMIT", 1)
    assert api_client.post("/wishes/send", json={"preset_code": "m1"}).status_code == 200
    assert api_client.post("/wishes/send", json={"preset_code": "m1"}).status_code == 400


# ── Inbox / реакции ─────────────────────────────────────────────────────────

def test_inbox_and_react(api_client, db):
    me = _enable(TEST_TELEGRAM_ID)
    other = db.get_or_create_user(OTHER_TID)
    wid = db.create_wish(other, me, "d1")
    inbox = api_client.get("/wishes/inbox").json()
    assert len(inbox) == 1
    assert inbox[0]["id"] == wid
    assert inbox[0]["text"]
    # реакция
    r = api_client.post(f"/wishes/{wid}/react", json={"reaction": "helped"})
    assert r.status_code == 204
    assert api_client.get("/wishes/inbox").json() == []
    # повторная реакция — уже нет такого «нового» пожелания
    assert api_client.post(f"/wishes/{wid}/react", json={"reaction": "helped"}).status_code == 404


def test_react_invalid_reaction(api_client, db):
    me = _enable(TEST_TELEGRAM_ID)
    other = db.get_or_create_user(OTHER_TID)
    wid = db.create_wish(other, me, "d1")
    assert api_client.post(f"/wishes/{wid}/react", json={"reaction": "lol"}).status_code == 422


def test_react_not_owner(api_client, db):
    _enable(TEST_TELEGRAM_ID)
    other = db.get_or_create_user(OTHER_TID)
    third = db.get_or_create_user(77003)
    # пожелание адресовано third, не нам
    wid = db.create_wish(other, third, "d1")
    assert api_client.post(f"/wishes/{wid}/react", json={"reaction": "helped"}).status_code == 404


def test_inbox_empty_when_disabled(api_client, db):
    me = db.get_or_create_user(TEST_TELEGRAM_ID)
    other = db.get_or_create_user(OTHER_TID)
    db.create_wish(other, me, "d1")
    # тогл выключен → inbox пуст
    assert api_client.get("/wishes/inbox").json() == []


def test_delete_user_data_clears_wishes(api_client, db):
    me = _enable(TEST_TELEGRAM_ID)
    other = _enable(OTHER_TID)
    db.create_wish(other, me, "d1")
    db.create_wish(me, other, "d2")
    db.delete_user_data(TEST_TELEGRAM_ID)
    assert db.get_wish_inbox(other) == []


# ── TG-дайджест откликов ────────────────────────────────────────────────────

def test_tg_notify_toggle_default_off(api_client, db):
    _enable(TEST_TELEGRAM_ID)
    assert api_client.get("/settings").json().get("wishes_tg_notify") == 0
    assert api_client.put("/settings/wishes-tg", json={"enabled": True}).status_code == 204
    assert api_client.get("/settings").json().get("wishes_tg_notify") == 1


def test_ack_summary_and_status(api_client, db):
    me = _enable(TEST_TELEGRAM_ID)
    other = db.get_or_create_user(OTHER_TID)
    w1 = db.create_wish(me, other, "d1")
    w2 = db.create_wish(me, other, "d2")
    db.create_wish(me, other, "d3")  # без реакции — не считается
    db.react_to_wish(w1, other, "helped")
    db.react_to_wish(w2, other, "supported")
    assert db.get_wish_ack_summary(me) == {"helped": 1, "supported": 1}
    body = api_client.get("/wishes/status").json()
    assert body["ack_helped"] == 1
    assert body["ack_supported"] == 1


def test_digest_candidates_gated_by_toggle(api_client, db):
    me = _enable(TEST_TELEGRAM_ID)
    other = db.get_or_create_user(OTHER_TID)
    w = db.create_wish(me, other, "d1")
    db.react_to_wish(w, other, "helped")
    # тогл TG выкл → не кандидат
    assert all(c["user_id"] != me for c in db.get_wish_digest_candidates())
    db.set_wishes_tg_notify(TEST_TELEGRAM_ID, True)
    cands = {c["user_id"]: c for c in db.get_wish_digest_candidates()}
    assert me in cands and cands[me]["helped"] == 1


def test_digest_mark_dedup(api_client, db):
    me = _enable(TEST_TELEGRAM_ID)
    db.set_wishes_tg_notify(TEST_TELEGRAM_ID, True)
    other = db.get_or_create_user(OTHER_TID)
    w = db.create_wish(me, other, "d1")
    db.react_to_wish(w, other, "helped")
    assert any(c["user_id"] == me for c in db.get_wish_digest_candidates())
    db.mark_wish_reactions_digested(me)
    # после метки — больше не кандидат (дедуп), но in-app summary остаётся
    assert all(c["user_id"] != me for c in db.get_wish_digest_candidates())
    assert db.get_wish_ack_summary(me)["helped"] == 1
