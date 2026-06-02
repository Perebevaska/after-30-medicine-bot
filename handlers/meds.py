"""Точка входа модуля handlers.meds.

Реэкспортирует все публичные символы из подмодулей, чтобы внешний код
(bot.py, timezone.py, тесты) мог продолжать импортировать из handlers.meds.
Логика разделена на:
  meds_common.py  — клавиатуры, форматтеры, карточка лекарства, show_meds_list
  meds_add.py     — флоу добавления лекарства (включая multi-dosage и caregiver)
  meds_edit.py    — флоу редактирования, удаления, паузы
"""
from telegram.ext import (ConversationHandler, CommandHandler,
                           CallbackQueryHandler, MessageHandler, filters)
from constants import (NAME, DOSAGE, MEAL, TIMES, DOSAGE_B, TIMES_B,
                       FREQ_TYPE, FREQ_INTERVAL, FREQ_WEEKDAYS, FREQ_MONTHDAY,
                       FREQ_TYPE_B, FREQ_INTERVAL_B, FREQ_WEEKDAYS_B, FREQ_MONTHDAY_B,
                       EDIT_NAME, EDIT_DOSAGE, EDIT_DOSAGE_B, EDIT_FREQ_TYPE, EDIT_TIMES,
                       EDIT_MEAL, EDIT_FREQ_INTERVAL, EDIT_FREQ_WEEKDAYS, EDIT_FREQ_MONTHDAY,
                       SELECT_DEPENDENT, ADD_DEPENDENT_NAME)

# ── Re-exports ─────────────────────────────────────────────────────────────
from handlers.meds_common import (  # noqa: F401
    WEEKDAY_NAMES,
    _CANCEL_BTN, _EDIT_NAME_KB, _EDIT_DOSAGE_KB, _EDIT_DOSAGE_B_KB,
    _ADD_DOSAGE_KB, _ADD_FREQ_INTERVAL_KB, _ADD_FREQ_MONTHDAY_KB,
    _EDIT_FREQ_INTERVAL_KB, _EDIT_FREQ_MONTHDAY_KB,
    _back_cancel_kb, _freq_type_keyboard, _freq_type_b_keyboard,
    _edit_freq_type_keyboard, _edit_freq_type_keyboard_multi,
    _weekdays_keyboard, _weekdays_b_keyboard, _edit_weekdays_keyboard,
    _edit_meal_keyboard, _edit_meal_keyboard_multi,
    _timeslots_keyboard, _timeslots_b_keyboard, _edit_timeslots_keyboard,
    _format_schedule_rule, _current_schedule_summary, _monthday_warning,
    _med_saved_text, _parse_int_range, _saved_keyboard, _freq_label, _dosage_a_summary,
    _compute_next_fire, _next_fire_label,
    _med_card_text, _med_card_keyboard,
    show_meds_list, meds_command, cancel_add,
)
from handlers.meds_add import (  # noqa: F401
    _dependent_select_keyboard, _dependent_select_keyboard_no_add,
    handle_select_dependent, handle_new_dependent_name_in_flow,
    _begin_add_flow, handle_add_med_callback, add_start,
    add_name, enter_multi_dosage_mode, add_dosage, add_dosage_b,
    add_timeslot_toggle, add_timeslots_confirm,
    add_timeslot_b_toggle, add_timeslots_b_confirm,
    add_meal, _go_to_freq_type_b, choose_freq_type,
    add_freq_interval, toggle_weekday, confirm_weekdays, add_freq_monthday,
    choose_freq_type_b, add_freq_interval_b_days, add_freq_interval_b_anchor,
    toggle_weekday_b, confirm_weekdays_b, add_freq_monthday_b,
    _save_multi_medication,
    back_add_to_name, back_add_to_dosage, back_multi_to_dosage_a, back_multi_to_dosage_b,
    back_add_to_times, back_multi_to_times_a, back_add_to_meal,
    back_add_to_freq_type, back_multi_to_freq_type_b,
)
from handlers.meds_edit import (  # noqa: F401
    handle_delete_callback, handle_pause_toggle, handle_edit_select,
    keep_edit_name, edit_name,
    keep_edit_dosage, edit_dosage,
    _show_edit_dosage_b_step, keep_edit_dosage_b, edit_dosage_b,
    _show_edit_meal_multi_step, _get_edit_rules_with_dosage, _show_edit_freq_type_step,
    keep_edit_schedule, choose_edit_freq_type,
    keep_edit_meal, edit_meal, _route_after_edit_meal,
    edit_timeslot_toggle, edit_timeslots_confirm,
    edit_freq_interval, toggle_edit_weekday, confirm_edit_weekdays, edit_freq_monthday,
    handle_multi_edit_change_schedule,
    back_edit_to_name, back_edit_to_dosage, back_edit_to_freq_type, back_edit_to_times,
    back_edit_to_dosage_b, back_edit_to_meal,
)


# ── ConversationHandler factories ──────────────────────────────────────────

def _schedule_input_states(times_back: list) -> dict:
    """Общие состояния ввода расписания (multi-dosage), переиспользуемые add- и edit-флоу."""
    return {
        TIMES: [
            CallbackQueryHandler(add_timeslot_toggle, pattern="^timeslot:"),
            CallbackQueryHandler(add_timeslots_confirm, pattern="^timeslots_confirm$"),
            *times_back,
        ],
        TIMES_B: [
            CallbackQueryHandler(add_timeslot_b_toggle, pattern="^timeslotb:"),
            CallbackQueryHandler(add_timeslots_b_confirm, pattern="^timeslotsb_confirm$"),
            CallbackQueryHandler(back_multi_to_times_a, pattern="^back_multi_to_times_a$"),
        ],
        MEAL: [
            CallbackQueryHandler(add_meal, pattern="^(before|after|with|any)$"),
            CallbackQueryHandler(back_add_to_times, pattern="^back_add_to_times$"),
        ],
        FREQ_TYPE: [
            CallbackQueryHandler(choose_freq_type, pattern="^freq:"),
            CallbackQueryHandler(back_add_to_meal, pattern="^back_add_to_meal$"),
        ],
        FREQ_INTERVAL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, add_freq_interval),
            CallbackQueryHandler(back_add_to_freq_type, pattern="^back_add_to_freq_type$"),
        ],
        FREQ_WEEKDAYS: [
            CallbackQueryHandler(toggle_weekday, pattern="^weekday:\\d+$"),
            CallbackQueryHandler(confirm_weekdays, pattern="^weekdays_confirm$"),
            CallbackQueryHandler(back_add_to_freq_type, pattern="^back_add_to_freq_type$"),
        ],
        FREQ_MONTHDAY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, add_freq_monthday),
            CallbackQueryHandler(back_add_to_freq_type, pattern="^back_add_to_freq_type$"),
        ],
        FREQ_TYPE_B: [
            CallbackQueryHandler(choose_freq_type_b, pattern="^freqb:"),
            CallbackQueryHandler(back_add_to_meal, pattern="^back_add_to_meal$"),
        ],
        FREQ_INTERVAL_B: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, add_freq_interval_b_days),
            CallbackQueryHandler(add_freq_interval_b_anchor, pattern="^freqb_anchor:"),
            CallbackQueryHandler(back_multi_to_freq_type_b, pattern="^back_multi_to_freq_type_b$"),
        ],
        FREQ_WEEKDAYS_B: [
            CallbackQueryHandler(toggle_weekday_b, pattern="^weekdayb:\\d+$"),
            CallbackQueryHandler(confirm_weekdays_b, pattern="^weekdaysb_confirm$"),
            CallbackQueryHandler(back_multi_to_freq_type_b, pattern="^back_multi_to_freq_type_b$"),
        ],
        FREQ_MONTHDAY_B: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, add_freq_monthday_b),
            CallbackQueryHandler(back_multi_to_freq_type_b, pattern="^back_multi_to_freq_type_b$"),
        ],
    }


def get_add_handler(cancel_handler):
    return ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
            CallbackQueryHandler(handle_add_med_callback, pattern="^add_med$"),
        ],
        states={
            SELECT_DEPENDENT: [
                CallbackQueryHandler(handle_select_dependent, pattern="^select_dep:"),
            ],
            ADD_DEPENDENT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_dependent_name_in_flow),
            ],
            NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_name),
            ],
            DOSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_dosage),
                CallbackQueryHandler(enter_multi_dosage_mode, pattern="^multi_dosage$"),
                CallbackQueryHandler(back_add_to_name, pattern="^back_add_to_name$"),
            ],
            DOSAGE_B: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_dosage_b),
                CallbackQueryHandler(back_multi_to_dosage_a, pattern="^back_multi_to_dosage_a$"),
            ],
            **_schedule_input_states([
                CallbackQueryHandler(back_add_to_dosage, pattern="^back_add_to_dosage$"),
                CallbackQueryHandler(back_multi_to_dosage_b, pattern="^back_multi_to_dosage_b$"),
            ]),
        },
        fallbacks=[
            cancel_handler,
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
        ],
    )


def get_edit_handler(cancel_handler):
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_edit_select, pattern="^edit:\\d+$")],
        states={
            EDIT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name),
                CallbackQueryHandler(keep_edit_name, pattern="^keep_edit_name$"),
            ],
            EDIT_DOSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_dosage),
                CallbackQueryHandler(keep_edit_dosage, pattern="^keep_edit_dosage$"),
                CallbackQueryHandler(back_edit_to_name, pattern="^back_edit_to_name$"),
            ],
            EDIT_DOSAGE_B: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_dosage_b),
                CallbackQueryHandler(keep_edit_dosage_b, pattern="^keep_edit_dosage_b$"),
                CallbackQueryHandler(back_edit_to_dosage, pattern="^back_edit_to_dosage$"),
            ],
            EDIT_FREQ_TYPE: [
                CallbackQueryHandler(keep_edit_schedule, pattern="^keep_edit_schedule$"),
                CallbackQueryHandler(choose_edit_freq_type, pattern="^editfreq:"),
                CallbackQueryHandler(handle_multi_edit_change_schedule, pattern="^multi_edit_change_schedule$"),
                CallbackQueryHandler(back_edit_to_dosage, pattern="^back_edit_to_dosage$"),
                CallbackQueryHandler(back_edit_to_meal, pattern="^back_edit_to_meal$"),
            ],
            EDIT_TIMES: [
                CallbackQueryHandler(edit_timeslot_toggle, pattern="^edittimeslot:"),
                CallbackQueryHandler(edit_timeslots_confirm, pattern="^edit_timeslots_confirm$"),
                CallbackQueryHandler(back_edit_to_freq_type, pattern="^back_edit_to_freq_type$"),
            ],
            EDIT_MEAL: [
                CallbackQueryHandler(edit_meal, pattern="^editmeal:"),
                CallbackQueryHandler(keep_edit_meal, pattern="^keep_edit_meal$"),
                CallbackQueryHandler(back_edit_to_times, pattern="^back_edit_to_times$"),
                CallbackQueryHandler(back_edit_to_dosage_b, pattern="^back_edit_to_dosage_b$"),
            ],
            EDIT_FREQ_INTERVAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_freq_interval),
                CallbackQueryHandler(back_edit_to_meal, pattern="^back_edit_to_meal$"),
            ],
            EDIT_FREQ_WEEKDAYS: [
                CallbackQueryHandler(toggle_edit_weekday, pattern="^editweekday:\\d+$"),
                CallbackQueryHandler(confirm_edit_weekdays, pattern="^edit_weekdays_confirm$"),
                CallbackQueryHandler(back_edit_to_meal, pattern="^back_edit_to_meal$"),
            ],
            EDIT_FREQ_MONTHDAY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_freq_monthday),
                CallbackQueryHandler(back_edit_to_meal, pattern="^back_edit_to_meal$"),
            ],
            **_schedule_input_states([
                CallbackQueryHandler(back_edit_to_freq_type, pattern="^back_edit_to_freq_type$"),
            ]),
        },
        fallbacks=[
            cancel_handler,
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
        ],
    )
