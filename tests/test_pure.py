"""Unit-тесты чистых функций med-bot (без БД и Telegram).

Запуск: source venv/bin/activate && pytest -q
"""
from datetime import date, datetime

import pytest
import pytz

from utils import escape_md, escape_html, parse_time, local_day_bounds_utc
from scheduler import _rule_fires_today
from handlers.meds import (
    _compute_next_fire, _next_fire_label, _freq_label,
    _format_schedule_rule, _monthday_warning, _current_schedule_summary,
)


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


# ── meds._compute_next_fire ─────────────────────────────────────────────────

def test_next_fire_daily():
    assert _compute_next_fire(_rule(frequency="daily"), MONDAY) == MONDAY


def test_next_fire_interval_today():
    r = _rule(frequency="interval", interval_days=3, anchor_date="2026-06-01")
    assert _compute_next_fire(r, MONDAY) == MONDAY


def test_next_fire_interval_future():
    r = _rule(frequency="interval", interval_days=3, anchor_date="2026-06-01")
    # 2 июня: remainder 1, next = +2 → 4 июня
    assert _compute_next_fire(r, date(2026, 6, 2)) == date(2026, 6, 4)


def test_next_fire_weekdays():
    # понедельник, правило только на среду(3)/пятницу(5) → ближайшее среда 3 июня
    r = _rule(frequency="weekdays", weekdays="3,5")
    assert _compute_next_fire(r, MONDAY) == date(2026, 6, 3)


def test_next_fire_monthly_same_month():
    r = _rule(frequency="monthly", month_day=15)
    assert _compute_next_fire(r, MONDAY) == date(2026, 6, 15)


def test_next_fire_monthly_rollover():
    # 20 июня, число 5 → 5 июля
    r = _rule(frequency="monthly", month_day=5)
    assert _compute_next_fire(r, date(2026, 6, 20)) == date(2026, 7, 5)


def test_next_fire_monthly_skips_short_month():
    # 31-е: февраль/апрель и т.п. пропускаются; с 1 фев 2027 → 31 марта 2027
    r = _rule(frequency="monthly", month_day=31)
    assert _compute_next_fire(r, date(2027, 2, 1)) == date(2027, 3, 31)


# ── meds._next_fire_label ───────────────────────────────────────────────────

def test_next_fire_label_daily_empty():
    assert _next_fire_label(_rule(frequency="daily"), MONDAY) == ""


def test_next_fire_label_today():
    r = _rule(frequency="interval", interval_days=2, anchor_date="2026-06-01")
    assert _next_fire_label(r, MONDAY) == " (сегодня)"


def test_next_fire_label_tomorrow():
    r = _rule(frequency="monthly", month_day=2)
    assert _next_fire_label(r, MONDAY) == " (завтра)"


def test_next_fire_label_day_after_tomorrow():
    # ближайшее срабатывание через 2 дня → "(послезавтра)"
    r = _rule(frequency="monthly", month_day=3)
    assert _next_fire_label(r, MONDAY) == " (послезавтра)"


def test_next_fire_label_weekday_name():
    # 4 июня 2026 — четверг, delta=3 → подпись днём недели
    r = _rule(frequency="monthly", month_day=4)
    assert _next_fire_label(r, MONDAY) == " (чт)"


def test_next_fire_label_date():
    # delta=9 (>6) → подпись датой "(10 июн)"
    r = _rule(frequency="monthly", month_day=10)
    assert _next_fire_label(r, MONDAY) == " (10 июн)"


# ── meds._freq_label ────────────────────────────────────────────────────────

def test_freq_label_daily():
    assert _freq_label("daily", None, None, None) == "каждый день"


def test_freq_label_interval():
    assert _freq_label("interval", 3, None, None) == "каждые 3 дн."


def test_freq_label_weekdays():
    assert _freq_label("weekdays", None, "1,3", None) == "Пн, Ср"


def test_freq_label_monthly():
    assert _freq_label("monthly", None, None, 15) == "15-го числа"


# ── meds._format_schedule_rule ──────────────────────────────────────────────

def test_format_rule_daily():
    assert _format_schedule_rule(_rule(reminder_time="09:00", frequency="daily")) == "09:00"


def test_format_rule_interval():
    r = _rule(reminder_time="09:00", frequency="interval", interval_days=2)
    assert _format_schedule_rule(r) == "каждые 2 дн. в 09:00"


def test_format_rule_weekdays():
    r = _rule(reminder_time="09:00", frequency="weekdays", weekdays="1,7")
    assert _format_schedule_rule(r) == "Пн, Вс в 09:00"


def test_format_rule_monthly():
    r = _rule(reminder_time="09:00", frequency="monthly", month_day=5)
    assert _format_schedule_rule(r) == "5-го числа в 09:00"


# ── meds._monthday_warning ──────────────────────────────────────────────────

@pytest.mark.parametrize("day", [29, 30, 31])
def test_monthday_warning_present(day):
    assert _monthday_warning(day) != ""


@pytest.mark.parametrize("day", [1, 15, 28])
def test_monthday_warning_absent(day):
    assert _monthday_warning(day) == ""


# ── meds._current_schedule_summary ──────────────────────────────────────────

def test_schedule_summary_empty():
    assert _current_schedule_summary([]) == "не указано"


def test_schedule_summary_daily():
    rules = [_rule(reminder_time="09:00", frequency="daily"),
             _rule(reminder_time="21:00", frequency="daily")]
    assert _current_schedule_summary(rules) == "09:00, 21:00 (каждый день)"


def test_schedule_summary_advanced():
    rules = [_rule(reminder_time="09:00", frequency="monthly", month_day=5)]
    assert _current_schedule_summary(rules) == "5-го числа в 09:00"
