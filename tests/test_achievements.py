"""F12a — ачивки: чистый движок + DB-хелперы + контракт эндпоинта."""

import achievements


# ── Чистый движок ────────────────────────────────────────────────────────────

def test_evaluate_thresholds():
    e = achievements.evaluate(
        best_streak=100, adh30=95, due30=30, adh90=92, due90=80,
        total_taken=500, has_care_link=True,
    )
    assert e == {
        "intake_10", "intake_100", "intake_500",
        "streak_7", "streak_30", "streak_100",
        "adh_30", "adh_90", "care_first",
    }


def test_evaluate_empty():
    assert achievements.evaluate(
        best_streak=6, adh30=None, due30=0, adh90=None, due90=0,
        total_taken=9, has_care_link=False,
    ) == set()


def test_evaluate_adherence_due_gate():
    # 100% соблюдения, но мало положенных приёмов → бейдж НЕ даётся
    e = achievements.evaluate(
        best_streak=0, adh30=100, due30=5, adh90=100, due90=10,
        total_taken=5, has_care_link=False,
    )
    assert "adh_30" not in e and "adh_90" not in e


def test_evaluate_partial_tiers():
    e = achievements.evaluate(
        best_streak=30, adh30=90, due30=25, adh90=None, due90=0,
        total_taken=100, has_care_link=False,
    )
    assert e == {"intake_10", "intake_100", "streak_7", "streak_30", "adh_30"}
    assert "streak_100" not in e and "intake_500" not in e


def test_catalog_codes_match_evaluate():
    # каждый код из evaluate присутствует в каталоге (и наоборот)
    cat = {a["code"] for a in achievements.CATALOG}
    full = achievements.evaluate(
        best_streak=100, adh30=95, due30=30, adh90=92, due90=80,
        total_taken=500, has_care_link=True,
    )
    assert full == cat


# ── DB-хелперы ───────────────────────────────────────────────────────────────

def _make_med(db, uid, name="Аспирин"):
    with db.get_connection() as conn:
        return conn.execute(
            "INSERT INTO medications (user_id, name, dosage, meal_relation, times_per_day) "
            "VALUES (%s, %s, '1таб', 'any', 1) RETURNING id",
            (uid, name),
        ).fetchone()["id"]


def _log(db, mid, status, day="2026-06-01"):
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO intake_log (medication_id, scheduled_time, status, taken_at) "
            "VALUES (%s, %s, %s, %s)",
            (mid, "09:00", status, f"{day} 09:00:00"),
        )


def test_count_total_taken_own_only(db):
    uid = db.get_or_create_user(8101)
    mid = _make_med(db, uid)
    _log(db, mid, "taken", "2026-06-01")
    _log(db, mid, "taken", "2026-06-02")
    _log(db, mid, "skipped", "2026-06-03")
    assert db.count_total_taken(uid) == 2


def test_has_any_care_link(db):
    a = db.get_or_create_user(8201)
    b = db.get_or_create_user(8202)
    assert db.has_any_care_link(a) is False
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO caregiver_links (caregiver_id, dependent_id, status) "
            "VALUES (%s, %s, 'active')",
            (a, b),
        )
    assert db.has_any_care_link(a) is True
    assert db.has_any_care_link(b) is True


def test_unlock_idempotent(db):
    uid = db.get_or_create_user(8301)
    assert sorted(db.unlock_achievements(uid, ["streak_7", "intake_10"])) == ["intake_10", "streak_7"]
    # повтор → новых нет
    assert db.unlock_achievements(uid, ["streak_7", "intake_10"]) == []
    # новый код среди старых → только он
    assert db.unlock_achievements(uid, ["streak_7", "adh_30"]) == ["adh_30"]
    assert sorted(db.get_achievements(uid)) == ["adh_30", "intake_10", "streak_7"]
    assert db.unlock_achievements(uid, []) == []


# ── Контракт эндпоинта ───────────────────────────────────────────────────────

def test_overview_achievements_block(api_client, db):
    db.get_or_create_user(77001)
    r = api_client.get("/stats/overview")
    assert r.status_code == 200
    ach = r.json()["achievements"]
    assert set(ach) == {"catalog", "unlocked", "newly"}
    assert len(ach["catalog"]) == len(achievements.CATALOG)
    assert ach["catalog"][0]["code"] == achievements.CATALOG[0]["code"]
    assert ach["unlocked"] == [] and ach["newly"] == []
