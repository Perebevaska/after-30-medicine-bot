"""Снапшот-тесты структуры ConversationHandler'ов add/edit (meds.py).

Фиксируют состав состояний, callback-функции и паттерны — защита для
дедупликации общих состояний (Q1b). Любое изменение маршрутизации диалога
должно осознанно обновлять эталон ниже.
"""
import handlers.meds as m
import constants as c


def _sig(conv):
    """{state: [(callback_name, pattern_or_None), ...]} для ConversationHandler."""
    out = {}
    for state, handlers in conv.states.items():
        items = []
        for h in handlers:
            pat = getattr(h, "pattern", None)
            items.append((h.callback.__name__, pat.pattern if pat else None))
        out[state] = items
    return out


_ADD = _sig(m.get_add_handler(lambda *a, **k: None))
_EDIT = _sig(m.get_edit_handler(lambda *a, **k: None))

# Общий блок состояний ввода расписания (одинаков в add и edit, кроме TIMES).
SHARED_BLOCK = {
    c.TIMES_B: [('add_timeslot_b_toggle', '^timeslotb:'), ('add_timeslots_b_confirm', '^timeslotsb_confirm$'), ('back_multi_to_times_a', '^back_multi_to_times_a$')],
    c.MEAL: [('add_meal', '^(before|after|with|any)$'), ('back_add_to_times', '^back_add_to_times$')],
    c.FREQ_TYPE: [('choose_freq_type', '^freq:'), ('back_add_to_meal', '^back_add_to_meal$')],
    c.FREQ_INTERVAL: [('add_freq_interval', None), ('back_add_to_freq_type', '^back_add_to_freq_type$')],
    c.FREQ_WEEKDAYS: [('toggle_weekday', '^weekday:\\d+$'), ('confirm_weekdays', '^weekdays_confirm$'), ('back_add_to_freq_type', '^back_add_to_freq_type$')],
    c.FREQ_MONTHDAY: [('add_freq_monthday', None), ('back_add_to_freq_type', '^back_add_to_freq_type$')],
    c.FREQ_TYPE_B: [('choose_freq_type_b', '^freqb:'), ('back_add_to_meal', '^back_add_to_meal$')],
    c.FREQ_INTERVAL_B: [('add_freq_interval_b_days', None), ('add_freq_interval_b_anchor', '^freqb_anchor:'), ('back_multi_to_freq_type_b', '^back_multi_to_freq_type_b$')],
    c.FREQ_WEEKDAYS_B: [('toggle_weekday_b', '^weekdayb:\\d+$'), ('confirm_weekdays_b', '^weekdaysb_confirm$'), ('back_multi_to_freq_type_b', '^back_multi_to_freq_type_b$')],
    c.FREQ_MONTHDAY_B: [('add_freq_monthday_b', None), ('back_multi_to_freq_type_b', '^back_multi_to_freq_type_b$')],
}

TIMES_ADD = [('add_timeslot_toggle', '^timeslot:'), ('add_timeslots_confirm', '^timeslots_confirm$'),
             ('back_add_to_dosage', '^back_add_to_dosage$'), ('back_multi_to_dosage_b', '^back_multi_to_dosage_b$')]
TIMES_EDIT = [('add_timeslot_toggle', '^timeslot:'), ('add_timeslots_confirm', '^timeslots_confirm$'),
              ('back_edit_to_freq_type', '^back_edit_to_freq_type$')]


def test_add_state_keys():
    assert set(_ADD.keys()) == {
        c.SELECT_DEPENDENT, c.ADD_DEPENDENT_NAME, c.NAME, c.DOSAGE, c.DOSAGE_B,
        c.TIMES, c.TIMES_B, c.MEAL, c.FREQ_TYPE, c.FREQ_INTERVAL, c.FREQ_WEEKDAYS,
        c.FREQ_MONTHDAY, c.FREQ_TYPE_B, c.FREQ_INTERVAL_B, c.FREQ_WEEKDAYS_B, c.FREQ_MONTHDAY_B,
    }


def test_edit_state_keys():
    assert set(_EDIT.keys()) == {
        c.EDIT_NAME, c.EDIT_DOSAGE, c.EDIT_DOSAGE_B, c.EDIT_FREQ_TYPE, c.EDIT_TIMES,
        c.EDIT_MEAL, c.EDIT_FREQ_INTERVAL, c.EDIT_FREQ_WEEKDAYS, c.EDIT_FREQ_MONTHDAY,
        c.TIMES, c.TIMES_B, c.MEAL, c.FREQ_TYPE, c.FREQ_INTERVAL, c.FREQ_WEEKDAYS,
        c.FREQ_MONTHDAY, c.FREQ_TYPE_B, c.FREQ_INTERVAL_B, c.FREQ_WEEKDAYS_B, c.FREQ_MONTHDAY_B,
    }


def test_shared_block_in_add():
    for state, expected in SHARED_BLOCK.items():
        assert _ADD[state] == expected


def test_shared_block_in_edit():
    for state, expected in SHARED_BLOCK.items():
        assert _EDIT[state] == expected


def test_shared_block_identical_add_edit():
    for state in SHARED_BLOCK:
        assert _ADD[state] == _EDIT[state]


def test_times_differs():
    assert _ADD[c.TIMES] == TIMES_ADD
    assert _EDIT[c.TIMES] == TIMES_EDIT


def test_entry_and_fallbacks_present():
    add = m.get_add_handler(lambda *a, **k: None)
    edit = m.get_edit_handler(lambda *a, **k: None)
    assert len(add.entry_points) == 2   # /add + add_med callback
    assert len(edit.entry_points) == 1  # edit:<id>
    # fallbacks: cancel_handler + cancel_add
    assert any(getattr(h, "pattern", None) and h.pattern.pattern == "^cancel_add$"
               for h in add.fallbacks)
    assert any(getattr(h, "pattern", None) and h.pattern.pattern == "^cancel_add$"
               for h in edit.fallbacks)
