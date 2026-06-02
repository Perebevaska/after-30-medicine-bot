"""Фаза 6: G1 (сердечки) + G2 (строгий режим)."""


# ── G1: сердечки (DB-слой) ───────────────────────────────────────────────────

def test_apply_intake_hearts_math(db):
    uid = db.get_or_create_user(901)
    assert db.get_hearts(901) == 0
    assert db.apply_intake_hearts(uid, "taken", None) == 1
    assert db.apply_intake_hearts(uid, "taken", None) == 2
    # undo taken → pending: delta = 0 − 1 = −1
    assert db.apply_intake_hearts(uid, "pending", "taken") == 1
    # skipped с нуля контекста: −1, но клампится у 0 (1 → 0)
    assert db.apply_intake_hearts(uid, "skipped", None) == 0
    assert db.apply_intake_hearts(uid, "skipped", None) == 0  # кламп
    # taken из skipped: delta = 1 − (−1) = +2
    assert db.apply_intake_hearts(uid, "taken", "skipped") == 2


def test_apply_intake_hearts_pending_noop(db):
    uid = db.get_or_create_user(903)
    db.apply_intake_hearts(uid, "taken", None)
    # pending без прежнего taken — delta 0, значение не меняется
    assert db.apply_intake_hearts(uid, "pending", None) == 1


# ── G2: строгий режим (DB-слой) ──────────────────────────────────────────────

def test_set_strict_mode(db):
    db.get_or_create_user(902)
    db.set_strict_mode(902, True, 5)
    row = db.get_user_settings_row(902)
    assert row["strict_mode"] == 1
    assert row["strict_mode_hours"] == 5
    # без hours — порог не меняется
    db.set_strict_mode(902, False)
    row = db.get_user_settings_row(902)
    assert row["strict_mode"] == 0
    assert row["strict_mode_hours"] == 5


# ── API ──────────────────────────────────────────────────────────────────────

def _create_med(api_client, time="09:00"):
    r = api_client.post("/medications", json={
        "name": "Аспирин", "dosage": "100мг", "meal_relation": "any",
        "times_per_day": 1, "rules": [{"reminder_time": time, "frequency": "daily"}],
    })
    assert r.status_code == 201
    return r.json()["id"]


def test_hearts_endpoint(api_client, db):
    db.get_or_create_user(77001)
    r = api_client.get("/stats/hearts")
    assert r.status_code == 200
    assert r.json() == {"hearts": 0}


def test_intake_taken_increments_hearts(api_client, db):
    db.get_or_create_user(77001)
    mid = _create_med(api_client)
    r = api_client.post("/today/intake", json={
        "medication_id": mid, "scheduled_time": "09:00", "status": "taken",
    })
    assert r.status_code == 204
    assert api_client.get("/stats/hearts").json()["hearts"] == 1
    # undo → сердечко возвращается
    api_client.post("/today/intake", json={
        "medication_id": mid, "scheduled_time": "09:00", "status": "pending",
    })
    assert api_client.get("/stats/hearts").json()["hearts"] == 0


def test_strict_mode_endpoint(api_client, db):
    db.get_or_create_user(77001)
    r = api_client.put("/settings/strict-mode", json={"enabled": True, "hours": 3})
    assert r.status_code == 204
    s = api_client.get("/settings").json()
    assert s["strict_mode"] == 1
    assert s["strict_mode_hours"] == 3


def test_strict_mode_hours_out_of_range(api_client, db):
    db.get_or_create_user(77001)
    r = api_client.put("/settings/strict-mode", json={"enabled": True, "hours": 99})
    assert r.status_code == 422
