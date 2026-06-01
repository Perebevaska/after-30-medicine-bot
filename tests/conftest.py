"""Общие фикстуры для DB-тестов на PostgreSQL."""
import pytest

TEST_DSN = "postgresql://medbot:medbot@127.0.0.1/medbot_test"


@pytest.fixture(scope="session", autouse=True)
def _pg_schema():
    """Сессионная инициализация: пул + схема. Запускается один раз на всю сессию."""
    import database as d
    d.init_pool(TEST_DSN)
    d.init_db()
    d.migrate()
    yield
    d.close_pool()


@pytest.fixture
def db(_pg_schema):
    """Функциональная фикстура: чистит все таблицы перед каждым тестом."""
    import database as d
    with d.get_connection() as conn:
        conn.execute(
            "TRUNCATE TABLE intake_log, schedule_rules, medications, dependents, users "
            "RESTART IDENTITY CASCADE"
        )
    return d
