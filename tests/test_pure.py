"""Unit-тесты чистых функций med-bot (без БД и Telegram).

Запуск: source venv/bin/activate && pytest -q
"""
from datetime import date, datetime

import pytest
import pytz

from utils import escape_md, escape_html, parse_time, local_day_bounds_utc
from scheduler import _rule_fires_today


# ── utils.parse_time ────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("9:5", "09:05"),
    ("09:00", "09:00"),
    ("23:59", "23:59"),
    ("0:0", "00:00"),
])
def test_parse_time_valid(raw, expected):
    assert parse_time(raw) == expected


@pytest.mark.parametrize("raw", ["24:00", "12:60", "-1:00", "abc", "12", "12:30:00", "", "12:"])
def test_parse_time_invalid(raw):
    with pytest.raises(ValueError):
        parse_time(raw)


# ── utils.escape_md / escape_html ───────────────────────────────────────────

def test_escape_md():
    assert escape_md("a*b_c`d[e") == "a\\*b\\_c\\`d\\[e"


def test_escape_md_no_special():
    assert escape_md("обычный текст") == "обычный текст"


def test_escape_html():
    assert escape_html("Vit <D> & Fe") == "Vit &lt;D&gt; &amp; Fe"


def test_escape_html_ampersand_first():
    # & должен экранироваться первым, иначе двойное экранирование
    assert escape_html("<&>") == "&lt;&amp;&gt;"


# ── utils.local_day_bounds_utc ──────────────────────────────────────────────

def test_local_day_bounds_utc_offset():
    tz = pytz.timezone("Asia/Yekaterinburg")  # UTC+5
    start, end = local_day_bounds_utc(tz, datetime(2026, 6, 1))
    assert start == "2026-05-31 19:00:00"
    assert end == "2026-06-01 19:00:00"


def test_local_day_bounds_utc_is_24h():
    tz = pytz.timezone("Europe/Moscow")
    start, end = local_day_bounds_utc(tz, datetime(2026, 6, 1))
    s = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
    e = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
    assert (e - s).total_seconds() == 86400


def test_local_day_bounds_utc_utc():
    start, end = local_day_bounds_utc(pytz.utc, datetime(2026, 6, 1))
    assert start == "2026-06-01 00:00:00"
    assert end == "2026-06-02 00:00:00"


# ── scheduler._rule_fires_today ─────────────────────────────────────────────

MONDAY = date(2026, 6, 1)  # isoweekday() == 1


def _rule(**kw):
    base = {"frequency": "daily", "weekdays": None, "month_day": None,
            "anchor_date": None, "interval_days": None}
    base.update(kw)
    return base


def test_fires_daily():
    assert _rule_fires_today(_rule(frequency="daily"), MONDAY) is True


def test_fires_weekdays_match():
    assert _rule_fires_today(_rule(frequency="weekdays", weekdays="1,3,5"), MONDAY) is True


def test_fires_weekdays_no_match():
    assert _rule_fires_today(_rule(frequency="weekdays", weekdays="2,4"), MONDAY) is False


def test_fires_monthly_match():
    assert _rule_fires_today(_rule(frequency="monthly", month_day=1), MONDAY) is True


def test_fires_monthly_no_match():
    assert _rule_fires_today(_rule(frequency="monthly", month_day=15), MONDAY) is False


def test_fires_interval_on_anchor():
    r = _rule(frequency="interval", interval_days=2, anchor_date="2026-06-01")
    assert _rule_fires_today(r, MONDAY) is True


def test_fires_interval_multiple():
    r = _rule(frequency="interval", interval_days=2, anchor_date="2026-06-01")
    assert _rule_fires_today(r, date(2026, 6, 3)) is True
    assert _rule_fires_today(r, date(2026, 6, 2)) is False


def test_fires_interval_missing_anchor():
    assert _rule_fires_today(_rule(frequency="interval", interval_days=2), MONDAY) is False


def test_fires_interval_missing_interval_days():
    # B4: interval_days NULL/0 не должен ронять (TypeError/ZeroDivisionError)
    assert _rule_fires_today(
        _rule(frequency="interval", interval_days=None, anchor_date="2026-06-01"), MONDAY
    ) is False
    assert _rule_fires_today(
        _rule(frequency="interval", interval_days=0, anchor_date="2026-06-01"), MONDAY
    ) is False


def test_fires_unknown_frequency():
    assert _rule_fires_today(_rule(frequency="whatever"), MONDAY) is False
