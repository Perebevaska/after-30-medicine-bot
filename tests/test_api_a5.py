"""A5 — изоляция пользователей и edge cases."""
import pytest
from contextlib import contextmanager
from starlette.testclient import TestClient
from tests.conftest import TEST_TELEGRAM_ID

OTHER_ID = 77002


# ── Хелперы ──────────────────────────────────────────────────────────────────

def _seed(db, telegram_id=TEST_TELEGRAM_ID):
    return db.get_or_create_user(telegram_id)


def _create_med(client, name="Аспирин"):
    r = client.post("/medications", json={
        "name": name, "dosage": "100мг", "meal_relation": "after",
        "times_per_day": 1, "rules": [{"reminder_time": "09:00", "frequency": "daily"}],
    })
    assert r.status_code == 201
    return r.json()["id"]


@contextmanager
def _as_user(telegram_id):
    """Временно переключает dependency override на другого пользователя."""
    from api.main import app
    from api.auth import require_telegram_user
    original = app.dependency_overrides.get(require_telegram_user)
    app.dependency_overrides[require_telegram_user] = lambda: telegram_id
    with TestClient(app) as c:
        yield c
    if original is not None:
        app.dependency_overrides[require_telegram_user] = original
    else:
        app.dependency_overrides.pop(require_telegram_user, None)


# ── Изоляция пользователей ────────────────────────────────────────────────────

def test_isolation_list(api_client, db):
    """Пользователь B не видит лекарства пользователя A."""
    _seed(db)
    _create_med(api_client)

    with _as_user(OTHER_ID) as cb:
        _seed(db, OTHER_ID)
        r = cb.get("/medications")
    assert r.status_code == 200
    assert r.json() == []


def test_isolation_delete(api_client, db):
    """Пользователь B не может удалить лекарство пользователя A."""
    _seed(db)
    mid = _create_med(api_client)

    with _as_user(OTHER_ID) as cb:
        _seed(db, OTHER_ID)
        r = cb.delete(f"/medications/{mid}")
    assert r.status_code == 404


def test_isolation_update(api_client, db):
    """Пользователь B не может изменить лекарство пользователя A."""
    _seed(db)
    mid = _create_med(api_client)

    with _as_user(OTHER_ID) as cb:
        _seed(db, OTHER_ID)
        r = cb.put(f"/medications/{mid}", json={
            "name": "Взлом", "dosage": "0", "meal_relation": "any",
            "times_per_day": 1, "rules": [],
        })
    assert r.status_code == 404


def test_isolation_stock(api_client, db):
    """Пользователь B не видит запас лекарства пользователя A."""
    _seed(db)
    mid = _create_med(api_client)
    api_client.put(f"/medications/{mid}/stock", json={"qty": 30})

    with _as_user(OTHER_ID) as cb:
        _seed(db, OTHER_ID)
        r = cb.get(f"/medications/{mid}/stock")
    assert r.status_code == 404


def test_isolation_pause(api_client, db):
    """Пользователь B не может поставить паузу чужому лекарству."""
    _seed(db)
    mid = _create_med(api_client)

    with _as_user(OTHER_ID) as cb:
        _seed(db, OTHER_ID)
        r = cb.post(f"/medications/{mid}/pause")
    assert r.status_code == 404


# ── CORS ─────────────────────────────────────────────────────────────────────

def test_cors_header_present(api_client):
    """CORS-заголовок присутствует в ответе."""
    r = api_client.get("/health", headers={"Origin": "https://example.com"})
    assert r.status_code == 200
    assert "access-control-allow-origin" in r.headers


def test_cors_preflight(api_client):
    """OPTIONS preflight возвращает 200 и нужные заголовки."""
    r = api_client.options(
        "/health",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code in (200, 204)
    assert "access-control-allow-origin" in r.headers


# ── Rate limiting ─────────────────────────────────────────────────────────────

def test_rate_limit(api_client, monkeypatch):
    """После превышения лимита возвращается 429."""
    import api.main as m
    monkeypatch.setattr(m, "_RATE_LIMIT", 3)
    m._counters.clear()

    for _ in range(3):
        r = api_client.get("/health")
        assert r.status_code == 200

    r = api_client.get("/health")
    assert r.status_code == 429
    assert r.json()["detail"] == m._RATE_MSG


# ── Unified error format ──────────────────────────────────────────────────────

def test_validation_error_is_string(api_client, db):
    """422 возвращает detail как строку, а не список."""
    _seed(db)
    r = api_client.post("/medications", json={"name": "X"})  # отсутствуют обязательные поля
    assert r.status_code == 422
    data = r.json()
    assert "detail" in data
    assert isinstance(data["detail"], str)


def test_validation_error_contains_field(api_client, db):
    """В тексте ошибки есть имя пропущенного поля."""
    _seed(db)
    r = api_client.post("/medications", json={"name": "X"})
    assert "dosage" in r.json()["detail"]


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_create_med_invalid_meal_relation(api_client, db):
    """Неверное значение meal_relation отвергается Pydantic → 422."""
    _seed(db)
    r = api_client.post("/medications", json={
        "name": "X", "dosage": "1", "meal_relation": "INVALID",
        "times_per_day": 1, "rules": [{"reminder_time": "09:00"}],
    })
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)


def test_log_intake_unknown_med(api_client, db):
    """Логирование приёма несуществующего лекарства возвращает 404."""
    _seed(db)
    r = api_client.post("/today/intake", json={
        "medication_id": 999999, "scheduled_time": "09:00", "status": "taken",
    })
    assert r.status_code == 404


def test_settings_invalid_timezone(api_client, db):
    """Невалидный часовой пояс возвращает ошибку."""
    _seed(db)
    r = api_client.put("/settings/timezone", json={"timezone": "Mars/Olympus"})
    assert r.status_code in (400, 422)


def test_stock_days_left_calculated(api_client, db):
    """days_left считается корректно при заданном stock_qty."""
    _seed(db)
    mid = _create_med(api_client)
    api_client.put(f"/medications/{mid}/stock", json={"qty": 30})
    api_client.put(f"/medications/{mid}/stock/units", json={"units": 1.0})
    r = api_client.get(f"/medications/{mid}/stock")
    assert r.status_code == 200
    assert r.json()["days_left"] is not None
    assert r.json()["days_left"] > 0
