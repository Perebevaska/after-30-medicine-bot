"""F11-C (Фаза C-1) — чистые тесты analytics.py (без БД)."""
from datetime import date, datetime, timedelta

import pytz

import analytics


def _rule(mid, time="09:00", freq="daily"):
    return {"medication_id": mid, "reminder_time": time, "frequency": freq,
            "weekdays": None, "month_day": None, "anchor_date": None, "interval_days": None}


def _taken(*days):
    """status_by_day со всеми (1,'09:00') taken на указанных датах."""
    return {d: {(1, "09:00"): "taken"} for d in days}


# ── best_streak ─────────────────────────────────────────────────────────────

def test_best_streak_picks_longest_past_run():
    rows = [_rule(1)]
    today = date(2026, 1, 10)
    created = {1: date(2026, 1, 1)}
    # 1-3 taken, 4 skipped (разрыв), 5-10 taken → лучшая серия = 6
    st = _taken(date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3),
                date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7),
                date(2026, 1, 8), date(2026, 1, 9), date(2026, 1, 10))
    st[date(2026, 1, 4)] = {(1, "09:00"): "skipped"}
    assert analytics.best_streak(rows, st, today, created) == 6


def test_best_streak_zero_when_no_perfect_day():
    rows = [_rule(1)]
    today = date(2026, 1, 3)
    created = {1: date(2026, 1, 1)}
    st = {date(2026, 1, 1): {(1, "09:00"): "skipped"}}
    assert analytics.best_streak(rows, st, today, created) == 0


# ── daily_adherence / window_pct ────────────────────────────────────────────

def test_daily_and_window_pct():
    rows = [_rule(1)]
    today = date(2026, 1, 3)
    start = date(2026, 1, 1)
    taken_by_day = {date(2026, 1, 1): 1, date(2026, 1, 2): 1}  # 2 из 3 дней
    daily = analytics.daily_adherence(rows, taken_by_day, {}, start, today)
    assert len(daily) == 3
    assert daily[0] == {"day": "2026-01-01", "due": 1, "taken": 1, "pct": 100}
    assert daily[2]["pct"] == 0
    assert analytics.window_pct(daily, 3) == 67
    assert analytics.window_pct(daily, 7) == 67  # окно длиннее истории — то же


def test_daily_null_pct_when_no_due():
    # interval-правило без anchor → не срабатывает → due=0 → pct=None
    rows = [{"medication_id": 1, "reminder_time": "09:00", "frequency": "interval",
             "weekdays": None, "month_day": None, "anchor_date": None, "interval_days": None}]
    daily = analytics.daily_adherence(rows, {}, {}, date(2026, 1, 1), date(2026, 1, 1))
    assert daily[0]["pct"] is None


# ── punctuality ─────────────────────────────────────────────────────────────

def test_punctuality_metrics_and_worst_hour():
    tz = pytz.utc
    intakes = [
        {"scheduled_time": "09:00", "status": "taken", "taken_at": "2026-01-01 09:10:00"},  # +10
        {"scheduled_time": "09:00", "status": "taken", "taken_at": "2026-01-02 09:50:00"},  # +50
        {"scheduled_time": "21:00", "status": "skipped", "taken_at": "2026-01-01 23:00:00"},
        {"scheduled_time": "21:00", "status": "skipped", "taken_at": "2026-01-02 23:00:00"},
        {"scheduled_time": "21:00", "status": "skipped", "taken_at": "2026-01-03 23:00:00"},
    ]
    r = analytics.punctuality(intakes, tz, min_sample=2)
    assert r["sample"] == 2
    assert r["ontime_pct"] == 50          # +10 вовремя, +50 поздно
    assert r["late_pct"] == 50
    assert r["avg_delay_min"] == 30       # (10+50)/2
    assert r["worst_hour"] == 21
    assert r["worst_hour_skip_pct"] == 100


def test_punctuality_hides_metrics_below_min_sample():
    tz = pytz.utc
    intakes = [{"scheduled_time": "09:00", "status": "taken", "taken_at": "2026-01-01 09:10:00"}]
    r = analytics.punctuality(intakes, tz, min_sample=10)
    assert r["sample"] == 1
    assert r["ontime_pct"] is None and r["avg_delay_min"] is None


def test_weekly_adherence_buckets():
    rows = [_rule(1)]
    today = date(2026, 1, 14)
    start = date(2026, 1, 1)                    # 14 дней → 2 недельных бакета
    taken = {start + timedelta(days=i): 1 for i in range(7)}  # 1-я неделя 100%
    daily = analytics.daily_adherence(rows, taken, {}, start, today)
    wk = analytics.weekly_adherence(daily)
    assert len(wk) == 2
    assert wk[-1]["end"] == "2026-01-14"        # последний бакет оканчивается сегодня
    assert wk[0]["pct"] == 100 and wk[1]["pct"] == 0


# ── risk_signals (F11 C-2) ───────────────────────────────────────────────────

def _daily(misses_per_day):
    """daily из списка пропусков/день (due=2 фикс, taken=2-miss)."""
    base = date(2026, 1, 1)
    return [{"day": (base + timedelta(days=i)).isoformat(), "due": 2,
             "taken": 2 - m, "pct": round((2 - m) / 2 * 100)}
            for i, m in enumerate(misses_per_day)]


def test_risk_gate_below_21_days_not_ready():
    daily = _daily([0] * 14)  # 14 дней истории < 21
    r = analytics.risk_signals(daily, [], pytz.utc, date(2026, 1, 14))
    assert r["ready"] is False
    assert r["signals"] == []
    assert r["history_days"] == 14


def test_risk_rising_miss_trend():
    # 21 день: первые 14 ровные, неделя A=0 пропусков, неделя B=5 → триггер
    misses = [0] * 14 + [1, 1, 1, 1, 1, 0, 0]  # last7 misses=5, prev7=0
    daily = _daily(misses)
    r = analytics.risk_signals(daily, [], pytz.utc, date(2026, 1, 21))
    assert r["ready"] is True
    keys = {s["key"] for s in r["signals"]}
    assert "rising_risk" in keys


def test_risk_no_rising_when_stable():
    daily = _daily([0] * 25)  # пропусков нет вовсе
    r = analytics.risk_signals(daily, [], pytz.utc, date(2026, 1, 25))
    assert r["ready"] is True
    assert all(s["key"] != "rising_risk" for s in r["signals"])


def test_risk_unstable_timing():
    daily = _daily([0] * 21)
    base = date(2026, 1, 1)
    # 10 отметок слота 09:00 с большим разбросом (стдев > 90 мин)
    offsets = [-180, 180, -150, 150, -120, 120, -90, 90, -60, 60]
    intakes = [{"medication_id": 1, "scheduled_time": "09:00", "status": "taken",
                "taken_at": (datetime(base.year, base.month, base.day, 9, 0)
                             + timedelta(days=i, minutes=off)).strftime("%Y-%m-%d %H:%M:%S")}
               for i, off in enumerate(offsets)]
    r = analytics.risk_signals(daily, intakes, pytz.utc, date(2026, 1, 21))
    keys = {s["key"] for s in r["signals"]}
    assert "unstable_timing" in keys


def test_risk_stable_timing_no_signal():
    daily = _daily([0] * 21)
    base = date(2026, 1, 1)
    # 10 отметок ровно в 09:00 → разброс 0
    intakes = [{"medication_id": 1, "scheduled_time": "09:00", "status": "taken",
                "taken_at": (datetime(base.year, base.month, base.day, 9, 0)
                             + timedelta(days=i)).strftime("%Y-%m-%d %H:%M:%S")}
               for i in range(10)]
    r = analytics.risk_signals(daily, intakes, pytz.utc, date(2026, 1, 21))
    assert all(s["key"] != "unstable_timing" for s in r["signals"])


# ── therapy_load ────────────────────────────────────────────────────────────

def test_therapy_load():
    rows = [_rule(1), _rule(2, time="20:00")]
    units = {1: 1, 2: 0.5}
    r = analytics.therapy_load(rows, units, date(2026, 1, 1))
    assert r["meds"] == 2
    assert r["intakes_per_day"] == 2.0          # 2 приёма/день
    assert r["units_per_week"] == 10.5          # (1 + 0.5) * 7
