"""A3 — эндпоинты API: happy path + edge cases."""
import pytest
from tests.conftest import TEST_TELEGRAM_ID

# ── Хелперы ─────────────────────────────────────────────────────────────────

def _create_med(client, name="Аспирин", dosage="100мг", rules=None):
    rules = rules or [{"reminder_time": "09:00", "frequency": "daily"}]
    r = client.post("/medications", json={
        "name": name, "dosage": dosage,
        "meal_relation": "after", "times_per_day": 1, "rules": rules,
    })
    assert r.status_code == 201
    return r.json()["id"]


def _seed_user(db):
    """Создаёт пользователя TEST_TELEGRAM_ID в БД."""
    return db.get_or_create_user(TEST_TELEGRAM_ID, "testuser")


# ── /medications ─────────────────────────────────────────────────────────────

def test_list_empty(api_client, db):
    _seed_user(db)
    r = api_client.get("/medications")
    assert r.status_code == 200
    assert r.json() == []


def test_create_and_list(api_client, db):
    _seed_user(db)
    mid = _create_med(api_client)
    r = api_client.get("/medications")
    assert r.status_code == 200
    meds = r.json()
    assert len(meds) == 1
    assert meds[0]["id"] == mid
    assert meds[0]["name"] == "Аспирин"
    assert len(meds[0]["rules"]) == 1


def test_create_limit(api_client, db):
    _seed_user(db)
    from constants import MAX_MEDICATIONS_PER_USER
    for i in range(MAX_MEDICATIONS_PER_USER):
        _create_med(api_client, name=f"Med{i}")
    r = api_client.post("/medications", json={
        "name": "Extra", "dosage": "1", "meal_relation": "any",
        "times_per_day": 1, "rules": [{"reminder_time": "09:00"}],
    })
    assert r.status_code == 400


def test_update_medication(api_client, db):
    _seed_user(db)
    mid = _create_med(api_client)
    r = api_client.put(f"/medications/{mid}", json={
        "name": "Ибупрофен", "dosage": "200мг", "meal_relation": "after",
        "times_per_day": 2,
        "rules": [{"reminder_time": "09:00"}, {"reminder_time": "21:00"}],
    })
    assert r.status_code == 200
    meds = api_client.get("/medications").json()
    assert meds[0]["name"] == "Ибупрофен"
    assert len(meds[0]["rules"]) == 2


def test_update_not_found(api_client, db):
    _seed_user(db)
    r = api_client.put("/medications/999999", json={
        "name": "X", "dosage": "1", "meal_relation": "any",
        "times_per_day": 1, "rules": [],
    })
    assert r.status_code == 404


def test_delete_medication(api_client, db):
    _seed_user(db)
    mid = _create_med(api_client)
    r = api_client.delete(f"/medications/{mid}")
    assert r.status_code == 204
    assert api_client.get("/medications").json() == []


def test_delete_not_found(api_client, db):
    _seed_user(db)
    assert api_client.delete("/medications/999999").status_code == 404


def test_pause_and_resume(api_client, db):
    _seed_user(db)
    mid = _create_med(api_client)
    assert api_client.post(f"/medications/{mid}/pause").status_code == 204
    med = api_client.get("/medications").json()[0]
    assert med["paused"] == 1
    assert api_client.post(f"/medications/{mid}/resume").status_code == 204
    assert api_client.get("/medications").json()[0]["paused"] == 0


# ── /today ───────────────────────────────────────────────────────────────────

def test_today_empty(api_client, db):
    _seed_user(db)
    r = api_client.get("/today")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_log_intake(api_client, db):
    import database as d
    uid = _seed_user(db)
    mid = d.add_medication(uid, "X", "1", "any", 1)
    d.add_schedule_rule(mid, "09:00", "daily")
    r = api_client.post("/today/intake", json={
        "medication_id": mid, "scheduled_time": "09:00", "status": "taken",
    })
    assert r.status_code == 204


# ── /stats ───────────────────────────────────────────────────────────────────

def test_stats_week_empty(api_client, db):
    _seed_user(db)
    r = api_client.get("/stats/week")
    assert r.status_code == 200
    assert r.json() == []


def test_stats_adherence_no_meds(api_client, db):
    _seed_user(db)
    r = api_client.get("/stats/adherence")
    assert r.status_code == 200
    assert r.json()["medications"] == []


def test_stats_streak(api_client, db):
    _seed_user(db)
    r = api_client.get("/stats/streak")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── /medications/{id}/stock ──────────────────────────────────────────────────

def test_stock_lifecycle(api_client, db):
    _seed_user(db)
    mid = _create_med(api_client)
    # по умолчанию трекинг выключен
    r = api_client.get(f"/medications/{mid}/stock")
    assert r.status_code == 200
    assert r.json()["stock_qty"] is None

    # установить остаток
    api_client.put(f"/medications/{mid}/stock", json={"qty": 30})
    assert api_client.get(f"/medications/{mid}/stock").json()["stock_qty"] == 30

    # пополнить
    api_client.post(f"/medications/{mid}/stock/add", json={"amount": 10})
    assert api_client.get(f"/medications/{mid}/stock").json()["stock_qty"] == 40

    # выключить трекинг
    api_client.delete(f"/medications/{mid}/stock")
    assert api_client.get(f"/medications/{mid}/stock").json()["stock_qty"] is None


def test_stock_units_and_threshold(api_client, db):
    """MA6: PUT /stock/units и /stock/threshold — вызываются из handleSave() в StockExpanded."""
    _seed_user(db)
    mid = _create_med(api_client)

    r = api_client.put(f"/medications/{mid}/stock/units", json={"units": 2.5})
    assert r.status_code == 204

    r = api_client.put(f"/medications/{mid}/stock/threshold", json={"days": 14})
    assert r.status_code == 204

    info = api_client.get(f"/medications/{mid}/stock").json()
    assert info["units_per_dose"] == 2.5
    assert info["low_stock_days"] == 14


def test_stock_save_all_fields(api_client, db):
    """MA6: handleSave() вызывает set/units/threshold параллельно — все три изменения сохраняются."""
    _seed_user(db)
    mid = _create_med(api_client)

    api_client.put(f"/medications/{mid}/stock", json={"qty": 60})
    api_client.put(f"/medications/{mid}/stock/units", json={"units": 3})
    api_client.put(f"/medications/{mid}/stock/threshold", json={"days": 10})

    info = api_client.get(f"/medications/{mid}/stock").json()
    assert info["stock_qty"] == 60
    assert info["units_per_dose"] == 3
    assert info["low_stock_days"] == 10


def test_stock_not_found(api_client, db):
    _seed_user(db)
    assert api_client.get("/medications/999999/stock").status_code == 404


# ── /dependents ──────────────────────────────────────────────────────────────

def test_dependents_lifecycle(api_client, db):
    _seed_user(db)
    # список пустой
    assert api_client.get("/dependents").json() == []
    # добавить
    r = api_client.post("/dependents", json={"name": "Маша"})
    assert r.status_code == 201
    dep_id = r.json()["id"]
    deps = api_client.get("/dependents").json()
    assert len(deps) == 1 and deps[0]["name"] == "Маша"
    # удалить
    assert api_client.delete(f"/dependents/{dep_id}").status_code == 204
    assert api_client.get("/dependents").json() == []


# ── /settings ────────────────────────────────────────────────────────────────

def test_settings_get(api_client, db):
    _seed_user(db)
    r = api_client.get("/settings")
    assert r.status_code == 200
    data = r.json()
    assert "timezone" in data and "reminder_mode" in data


def test_settings_timezone(api_client, db):
    _seed_user(db)
    r = api_client.put("/settings/timezone", json={"timezone": "Europe/Moscow"})
    assert r.status_code == 204
    assert api_client.get("/settings").json()["timezone"] == "Europe/Moscow"


def test_settings_reminder_mode(api_client, db):
    _seed_user(db)
    api_client.put("/settings/reminder-mode", json={"mode": "repeat"})
    assert api_client.get("/settings").json()["reminder_mode"] == "repeat"


def test_settings_preset(api_client, db):
    _seed_user(db)
    api_client.put("/settings/presets/morning", json={"time": "07:30"})
    assert api_client.get("/settings").json()["time_morning"] == "07:30"


def test_settings_caregiver(api_client, db):
    _seed_user(db)
    api_client.put("/settings/caregiver", json={"enabled": True})
    assert api_client.get("/settings").json()["caregiver_enabled"] == 1


# ── /health ──────────────────────────────────────────────────────────────────

def test_health(api_client):
    assert api_client.get("/health").json() == {"status": "ok"}
