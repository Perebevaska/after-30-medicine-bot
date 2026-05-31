import logging
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ContextTypes, ConversationHandler, CommandHandler,
                          CallbackQueryHandler, MessageHandler, filters)
from database import (get_or_create_user, add_medication, add_schedule_rule,
                      get_user_medications, deactivate_medication,
                      get_medication_by_id, get_schedules_by_medication, update_medication,
                      count_active_medications, get_user_time_presets)
from scheduler import clear_pending_for_medication
from constants import (NAME, DOSAGE, MEAL, TIMES, SCHEDULE,
                       EDIT_NAME, EDIT_DOSAGE, EDIT_MEAL, EDIT_TIMES, EDIT_SCHEDULE,
                       FREQ_TYPE, FREQ_INTERVAL, FREQ_WEEKDAYS, FREQ_MONTHDAY,
                       EDIT_FREQ_TYPE, EDIT_FREQ_INTERVAL, EDIT_FREQ_WEEKDAYS, EDIT_FREQ_MONTHDAY,
                       MEAL_LABELS, MAX_MEDICATIONS_PER_USER, SLOT_ORDER, SLOT_LABELS)
from utils import handle_db_errors

logger = logging.getLogger(__name__)

WEEKDAY_NAMES = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}

_CANCEL_BTN = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")]])

_EDIT_NAME_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("➡️ Оставить текущее", callback_data="keep_edit_name")],
    [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")],
])
_EDIT_DOSAGE_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("➡️ Оставить текущее", callback_data="keep_edit_dosage")],
    [InlineKeyboardButton("◀️ Назад", callback_data="back_edit_to_name"),
     InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")],
])


def _back_cancel_kb(back_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Назад", callback_data=back_cb),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_add"),
    ]])


_ADD_DOSAGE_KB = _back_cancel_kb("back_add_to_name")
_ADD_FREQ_INTERVAL_KB = _back_cancel_kb("back_add_to_freq_type")
_ADD_FREQ_MONTHDAY_KB = _back_cancel_kb("back_add_to_freq_type")
_EDIT_FREQ_INTERVAL_KB = _back_cancel_kb("back_edit_to_meal")
_EDIT_FREQ_MONTHDAY_KB = _back_cancel_kb("back_edit_to_meal")


def _freq_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Каждый день", callback_data="freq:daily")],
        [InlineKeyboardButton("🔄 Каждый N день", callback_data="freq:interval")],
        [InlineKeyboardButton("📆 По дням недели", callback_data="freq:weekdays")],
        [InlineKeyboardButton("🗓 Раз в месяц", callback_data="freq:monthly")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_add_to_meal"),
         InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")],
    ])


def _edit_freq_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➡️ Оставить расписание", callback_data="keep_edit_schedule")],
        [InlineKeyboardButton("📅 Каждый день", callback_data="editfreq:daily")],
        [InlineKeyboardButton("🔄 Каждый N день", callback_data="editfreq:interval")],
        [InlineKeyboardButton("📆 По дням недели", callback_data="editfreq:weekdays")],
        [InlineKeyboardButton("🗓 Раз в месяц", callback_data="editfreq:monthly")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_edit_to_dosage"),
         InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")],
    ])


def _weekdays_keyboard(selected: set) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(
            f"✅ {name}" if d in selected else name,
            callback_data=f"weekday:{d}"
        )
        for d, name in WEEKDAY_NAMES.items()
    ]
    return InlineKeyboardMarkup([
        row[:4], row[4:],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_add_to_freq_type"),
         InlineKeyboardButton("✔️ Готово", callback_data="weekdays_confirm"),
         InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")],
    ])


def _edit_weekdays_keyboard(selected: set) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(
            f"✅ {name}" if d in selected else name,
            callback_data=f"editweekday:{d}"
        )
        for d, name in WEEKDAY_NAMES.items()
    ]
    return InlineKeyboardMarkup([
        row[:4], row[4:],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_edit_to_meal"),
         InlineKeyboardButton("✔️ Готово", callback_data="edit_weekdays_confirm"),
         InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")],
    ])


def _edit_meal_keyboard(current_label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"➡️ Оставить ({current_label})", callback_data="keep_edit_meal")]]
        + [[InlineKeyboardButton(label, callback_data=f"editmeal:{key}")] for key, label in MEAL_LABELS.items()]
        + [[InlineKeyboardButton("◀️ Назад", callback_data="back_edit_to_times"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")]]
    )


def _timeslots_keyboard(selected: set, presets: dict) -> InlineKeyboardMarkup:
    btns = [
        InlineKeyboardButton(
            f"{'✅ ' if s in selected else ''}{SLOT_LABELS[s]} ({presets[s]})",
            callback_data=f"timeslot:{s}"
        )
        for s in SLOT_ORDER
    ]
    return InlineKeyboardMarkup([
        [btns[0], btns[1]],
        [btns[2], btns[3]],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_add_to_dosage"),
         InlineKeyboardButton("✔️ Готово", callback_data="timeslots_confirm"),
         InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")],
    ])


def _edit_timeslots_keyboard(selected: set, presets: dict) -> InlineKeyboardMarkup:
    btns = [
        InlineKeyboardButton(
            f"{'✅ ' if s in selected else ''}{SLOT_LABELS[s]} ({presets[s]})",
            callback_data=f"edittimeslot:{s}"
        )
        for s in SLOT_ORDER
    ]
    return InlineKeyboardMarkup([
        [btns[0], btns[1]],
        [btns[2], btns[3]],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_edit_to_freq_type"),
         InlineKeyboardButton("✔️ Готово", callback_data="edit_timeslots_confirm"),
         InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")],
    ])


def _format_schedule_rule(rule) -> str:
    time = rule["reminder_time"]
    freq = rule["frequency"]
    if freq == "daily":
        return time
    if freq == "interval":
        return f"каждые {rule['interval_days']} дн. в {time}"
    if freq == "weekdays":
        days = [WEEKDAY_NAMES[int(d)] for d in rule["weekdays"].split(",") if d]
        return f"{', '.join(days)} в {time}"
    if freq == "monthly":
        return f"{rule['month_day']}-го числа в {time}"
    return time


def _current_schedule_summary(rules: list) -> str:
    if not rules:
        return "не указано"
    has_adv = any(r["frequency"] != "daily" for r in rules)
    if not has_adv:
        times = ", ".join(r["reminder_time"] for r in rules)
        return f"{times} (каждый день)"
    return " | ".join(_format_schedule_rule(r) for r in rules)


def _monthday_warning(day: int) -> str:
    if day == 29:
        return "\n\n⚠️ В феврале невисокосного года напоминание не сработает."
    if day == 30:
        return "\n\n⚠️ В феврале напоминание не сработает."
    if day == 31:
        return "\n\n⚠️ В феврале, апреле, июне, сентябре и ноябре напоминание не сработает."
    return ""


def _freq_label(freq: str, interval_days, weekdays_str, month_day) -> str:
    if freq == "daily":
        return "каждый день"
    if freq == "interval":
        return f"каждые {interval_days} дн."
    if freq == "weekdays" and weekdays_str:
        days = [WEEKDAY_NAMES[int(d)] for d in weekdays_str.split(",") if d]
        return ", ".join(days)
    if freq == "monthly":
        return f"{month_day}-го числа"
    return freq


# ── Display ────────────────────────────────────────────────────────────────

async def show_meds_list(message, user):
    user_id = get_or_create_user(user.id, user.username)
    meds = get_user_medications(user_id)

    if not meds:
        await message.reply_text(
            "У тебя пока нет лекарств.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Добавить лекарство", callback_data="add_med")
            ]])
        )
        return

    await message.reply_text("💊 Твои лекарства:")
    for med in meds:
        rules = get_schedules_by_medication(med["id"])
        has_advanced = any(r["frequency"] != "daily" for r in rules)
        if not has_advanced:
            schedule_str = ", ".join(r["reminder_time"] for r in rules) or "не указано"
        else:
            schedule_str = "\n".join(_format_schedule_rule(r) for r in rules) or "не указано"
        meal = MEAL_LABELS.get(med["meal_relation"], med["meal_relation"])
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✏️ Изменить", callback_data=f"edit:{med['id']}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{med['id']}"),
        ]])
        text = (
            f"*{med['name']}* — {med['dosage']}\n"
            f"🍽 {meal}\n"
        )
        if not has_advanced:
            text += f"🔢 {med['times_per_day']} раз в день\n"
        text += f"⏰ {schedule_str}"
        await message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)

    await message.reply_text(
        "➕ Хочешь добавить ещё?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ Добавить лекарство", callback_data="add_med")
        ]])
    )


@handle_db_errors
async def meds_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_meds_list(update.message, update.effective_user)


# ── Common ─────────────────────────────────────────────────────────────────

async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("Отменено.")
    return ConversationHandler.END


# ── Add flow: entry ────────────────────────────────────────────────────────

async def handle_add_med_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    if count_active_medications(user_id) >= MAX_MEDICATIONS_PER_USER:
        await query.message.reply_text(
            f"⚠️ Достигнут лимит: максимум {MAX_MEDICATIONS_PER_USER} лекарств."
        )
        return ConversationHandler.END
    await query.message.reply_text("Как называется лекарство?", reply_markup=_CANCEL_BTN)
    return NAME


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    if count_active_medications(user_id) >= MAX_MEDICATIONS_PER_USER:
        await update.message.reply_text(
            f"⚠️ Достигнут лимит: максимум {MAX_MEDICATIONS_PER_USER} лекарств."
        )
        return ConversationHandler.END
    await update.message.reply_text("Как называется лекарство?", reply_markup=_CANCEL_BTN)
    return NAME


async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text(
        "Укажи дозировку (например: 500мг, 1 таблетка):",
        reply_markup=_ADD_DOSAGE_KB
    )
    return DOSAGE


async def add_dosage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["dosage"] = update.message.text.strip()
    context.user_data.setdefault("selected_slots", set())
    selected = context.user_data["selected_slots"]
    presets = get_user_time_presets(update.effective_user.id)
    await update.message.reply_text(
        "⏰ *Когда принимать?* — выбери один или несколько:",
        parse_mode="Markdown",
        reply_markup=_timeslots_keyboard(selected, presets)
    )
    return TIMES


async def add_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["meal"] = query.data
    await query.edit_message_text("📅 *Тип расписания* — выбери:",
                                  parse_mode="Markdown", reply_markup=_freq_type_keyboard())
    return FREQ_TYPE


# ── Add flow: slot toggle → meal ───────────────────────────────────────────

async def add_timeslot_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot = query.data.split(":")[1]
    selected = context.user_data.setdefault("selected_slots", set())
    selected.discard(slot) if slot in selected else selected.add(slot)
    presets = get_user_time_presets(update.effective_user.id)
    await query.edit_message_reply_markup(reply_markup=_timeslots_keyboard(selected, presets))
    return TIMES


async def add_timeslots_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    selected = context.user_data.get("selected_slots", set())
    if not selected:
        await query.answer("Выбери хотя бы один приём", show_alert=True)
        return TIMES
    await query.answer()
    presets = get_user_time_presets(update.effective_user.id)
    context.user_data["collected_times"] = [presets[s] for s in SLOT_ORDER if s in selected]
    keyboard = [
        [InlineKeyboardButton(label, callback_data=key)]
        for key, label in MEAL_LABELS.items()
    ]
    keyboard.append([
        InlineKeyboardButton("◀️ Назад", callback_data="back_add_to_times"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_add"),
    ])
    await query.edit_message_text(
        "🍽 *Как принимать с пищей?*",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MEAL


# ── Add flow: freq type → save ─────────────────────────────────────────────

@handle_db_errors
async def choose_freq_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    freq = query.data.split(":")[1]

    if freq == "daily":
        user = update.effective_user
        user_id = get_or_create_user(user.id, user.username)
        if count_active_medications(user_id) >= MAX_MEDICATIONS_PER_USER:
            await query.message.reply_text(
                f"⚠️ Достигнут лимит: максимум {MAX_MEDICATIONS_PER_USER} лекарств.")
            context.user_data.clear()
            return ConversationHandler.END
        collected = context.user_data["collected_times"]
        total = len(collected)
        med_id = add_medication(user_id, context.user_data["name"],
                                context.user_data["dosage"], context.user_data["meal"], total)
        for t in collected:
            add_schedule_rule(med_id, t, "daily")
        await query.edit_message_text(
            f"✅ Лекарство добавлено!\n\n"
            f"💊 {context.user_data['name']} — {context.user_data['dosage']}\n"
            f"🍽 {MEAL_LABELS[context.user_data['meal']]}\n"
            f"🔢 {total} раз в день\n"
            f"⏰ {', '.join(collected)}"
        )
        context.user_data.clear()
        return ConversationHandler.END

    if freq == "interval":
        await query.edit_message_text("🔄 *Через сколько дней?* (например: 2):",
                                      parse_mode="Markdown", reply_markup=_ADD_FREQ_INTERVAL_KB)
        return FREQ_INTERVAL

    if freq == "weekdays":
        context.user_data["freq_weekdays"] = set()
        await query.edit_message_text(
            "📆 *По дням недели* — выбери и нажми Готово:",
            parse_mode="Markdown", reply_markup=_weekdays_keyboard(set())
        )
        return FREQ_WEEKDAYS

    if freq == "monthly":
        await query.edit_message_text("🗓 *Какого числа каждого месяца?* (1–31):",
                                      parse_mode="Markdown", reply_markup=_ADD_FREQ_MONTHDAY_KB)
        return FREQ_MONTHDAY

    return FREQ_TYPE


@handle_db_errors
async def add_freq_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        n = int(update.message.text.strip())
        assert 2 <= n <= 90
    except (ValueError, AssertionError):
        await update.message.reply_text("Введи число от 2 до 90:", reply_markup=_ADD_FREQ_INTERVAL_KB)
        return FREQ_INTERVAL
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    if count_active_medications(user_id) >= MAX_MEDICATIONS_PER_USER:
        await update.message.reply_text(
            f"⚠️ Достигнут лимит: максимум {MAX_MEDICATIONS_PER_USER} лекарств.")
        context.user_data.clear()
        return ConversationHandler.END
    collected = context.user_data["collected_times"]
    total = len(collected)
    anchor_date = date.today().isoformat()
    med_id = add_medication(user_id, context.user_data["name"],
                            context.user_data["dosage"], context.user_data["meal"], total)
    for t in collected:
        add_schedule_rule(med_id, t, "interval", interval_days=n, anchor_date=anchor_date)
    await update.message.reply_text(
        f"✅ Лекарство добавлено!\n\n"
        f"💊 {context.user_data['name']} — {context.user_data['dosage']}\n"
        f"🍽 {MEAL_LABELS[context.user_data['meal']]}\n"
        f"🔢 {total} раз в день\n"
        f"⏰ {', '.join(collected)} — {_freq_label('interval', n, None, None)}"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def toggle_weekday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    day = int(query.data.split(":")[1])
    selected = context.user_data.setdefault("freq_weekdays", set())
    selected.discard(day) if day in selected else selected.add(day)
    await query.edit_message_reply_markup(reply_markup=_weekdays_keyboard(selected))
    return FREQ_WEEKDAYS


@handle_db_errors
async def confirm_weekdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    selected = context.user_data.get("freq_weekdays", set())
    if not selected:
        await query.answer("Выбери хотя бы один день", show_alert=True)
        return FREQ_WEEKDAYS
    await query.answer()
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    if count_active_medications(user_id) >= MAX_MEDICATIONS_PER_USER:
        await query.message.reply_text(
            f"⚠️ Достигнут лимит: максимум {MAX_MEDICATIONS_PER_USER} лекарств.")
        context.user_data.clear()
        return ConversationHandler.END
    collected = context.user_data["collected_times"]
    total = len(collected)
    weekdays = ",".join(str(d) for d in sorted(selected))
    med_id = add_medication(user_id, context.user_data["name"],
                            context.user_data["dosage"], context.user_data["meal"], total)
    for t in collected:
        add_schedule_rule(med_id, t, "weekdays", weekdays=weekdays)
    await query.edit_message_text(
        f"✅ Лекарство добавлено!\n\n"
        f"💊 {context.user_data['name']} — {context.user_data['dosage']}\n"
        f"🍽 {MEAL_LABELS[context.user_data['meal']]}\n"
        f"🔢 {total} раз в день\n"
        f"⏰ {', '.join(collected)} — {_freq_label('weekdays', None, weekdays, None)}"
    )
    context.user_data.clear()
    return ConversationHandler.END


@handle_db_errors
async def add_freq_monthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        day = int(update.message.text.strip())
        assert 1 <= day <= 31
    except (ValueError, AssertionError):
        await update.message.reply_text("Введи число от 1 до 31:", reply_markup=_ADD_FREQ_MONTHDAY_KB)
        return FREQ_MONTHDAY
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    if count_active_medications(user_id) >= MAX_MEDICATIONS_PER_USER:
        await update.message.reply_text(
            f"⚠️ Достигнут лимит: максимум {MAX_MEDICATIONS_PER_USER} лекарств.")
        context.user_data.clear()
        return ConversationHandler.END
    collected = context.user_data["collected_times"]
    total = len(collected)
    med_id = add_medication(user_id, context.user_data["name"],
                            context.user_data["dosage"], context.user_data["meal"], total)
    for t in collected:
        add_schedule_rule(med_id, t, "monthly", month_day=day)
    warning = _monthday_warning(day)
    await update.message.reply_text(
        f"✅ Лекарство добавлено!\n\n"
        f"💊 {context.user_data['name']} — {context.user_data['dosage']}\n"
        f"🍽 {MEAL_LABELS[context.user_data['meal']]}\n"
        f"🔢 {total} раз в день\n"
        f"⏰ {', '.join(collected)} — {_freq_label('monthly', None, None, day)}"
        f"{warning}"
    )
    context.user_data.clear()
    return ConversationHandler.END


# ── Add flow: back handlers ────────────────────────────────────────────────

async def back_add_to_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Как называется лекарство?", reply_markup=_CANCEL_BTN)
    return NAME


async def back_add_to_dosage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Укажи дозировку (например: 500мг, 1 таблетка):",
        reply_markup=_ADD_DOSAGE_KB
    )
    return DOSAGE


async def back_add_to_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected = context.user_data.get("selected_slots", set())
    presets = get_user_time_presets(update.effective_user.id)
    await query.edit_message_text(
        "⏰ *Когда принимать?* — выбери один или несколько:",
        parse_mode="Markdown",
        reply_markup=_timeslots_keyboard(selected, presets)
    )
    return TIMES


async def back_add_to_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(label, callback_data=key)]
        for key, label in MEAL_LABELS.items()
    ]
    keyboard.append([
        InlineKeyboardButton("◀️ Назад", callback_data="back_add_to_times"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_add"),
    ])
    await query.edit_message_text(
        "🍽 *Как принимать с пищей?*",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MEAL


async def back_add_to_freq_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📅 *Тип расписания* — выбери:",
        parse_mode="Markdown", reply_markup=_freq_type_keyboard()
    )
    return FREQ_TYPE


# ── Edit flow: entry & name/dosage ─────────────────────────────────────────

@handle_db_errors
async def handle_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    medication_id = int(query.data.split(":")[1])
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    deactivate_medication(medication_id, user_id)
    clear_pending_for_medication(medication_id)
    await query.edit_message_text("✅ Лекарство удалено из списка, напоминания отключены.")


@handle_db_errors
async def handle_edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    medication_id = int(query.data.split(":")[1])
    user = update.effective_user
    user_id = get_or_create_user(user.id, user.username)
    med = get_medication_by_id(medication_id, user_id)
    schedules = get_schedules_by_medication(medication_id)
    schedule_rules = [dict(s) for s in schedules]
    context.user_data["edit_id"] = medication_id
    context.user_data["edit_user_id"] = user_id
    context.user_data["edit_med"] = {
        "name": med["name"],
        "dosage": med["dosage"],
        "meal_relation": med["meal_relation"],
        "times_per_day": med["times_per_day"],
        "schedule_rules": schedule_rules,
    }
    has_adv = any(r["frequency"] != "daily" for r in schedule_rules)
    if not has_adv:
        schedule_str = ", ".join(r["reminder_time"] for r in schedule_rules) or "не указано"
    else:
        schedule_str = " | ".join(_format_schedule_rule(r) for r in schedule_rules) or "не указано"
    await query.edit_message_text(
        f"✏️ *Редактируем: {med['name']}*\n"
        f"💊 {med['dosage']}  🍽 {MEAL_LABELS[med['meal_relation']]}  ⏰ {schedule_str}\n"
        f"──────────────────\n"
        f"📝 *Название* — введи новое:",
        parse_mode="Markdown",
        reply_markup=_EDIT_NAME_KB
    )
    return EDIT_NAME


async def keep_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    med = context.user_data["edit_med"]
    context.user_data["edit_name"] = med["name"]
    await query.edit_message_text(
        f"📏 *Дозировка* — введи новую\n(текущая: {med['dosage']}):",
        parse_mode="Markdown",
        reply_markup=_EDIT_DOSAGE_KB
    )
    return EDIT_DOSAGE


async def edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["edit_name"] = update.message.text.strip()
    med = context.user_data["edit_med"]
    await update.message.reply_text(
        f"📏 *Дозировка* — введи новую\n(текущая: {med['dosage']}):",
        parse_mode="Markdown",
        reply_markup=_EDIT_DOSAGE_KB
    )
    return EDIT_DOSAGE


async def keep_edit_dosage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["edit_dosage"] = context.user_data["edit_med"]["dosage"]
    rules = context.user_data["edit_med"]["schedule_rules"]
    await query.edit_message_text(
        f"📅 *Расписание* — выбери тип:\nТекущее: {_current_schedule_summary(rules)}",
        parse_mode="Markdown", reply_markup=_edit_freq_type_keyboard()
    )
    return EDIT_FREQ_TYPE


async def edit_dosage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["edit_dosage"] = update.message.text.strip()
    rules = context.user_data["edit_med"]["schedule_rules"]
    await update.message.reply_text(
        f"📅 *Расписание* — выбери тип:\nТекущее: {_current_schedule_summary(rules)}",
        parse_mode="Markdown", reply_markup=_edit_freq_type_keyboard()
    )
    return EDIT_FREQ_TYPE


# ── Edit flow: freq type ───────────────────────────────────────────────────

@handle_db_errors
async def keep_edit_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    edit_med = context.user_data["edit_med"]
    user_id = context.user_data["edit_user_id"]
    update_medication(
        context.user_data["edit_id"], user_id,
        context.user_data["edit_name"], context.user_data["edit_dosage"],
        edit_med["meal_relation"], edit_med["times_per_day"],
        edit_med["schedule_rules"]
    )
    rules = edit_med["schedule_rules"]
    has_adv = any(r["frequency"] != "daily" for r in rules)
    if not has_adv:
        schedule_str = ", ".join(r["reminder_time"] for r in rules)
    else:
        schedule_str = " | ".join(_format_schedule_rule(r) for r in rules)
    await query.edit_message_text(
        f"✅ Лекарство обновлено!\n\n"
        f"💊 {context.user_data['edit_name']} — {context.user_data['edit_dosage']}\n"
        f"🍽 {MEAL_LABELS[edit_med['meal_relation']]}\n"
        f"🔢 {edit_med['times_per_day']} раз в день\n"
        f"⏰ {schedule_str}"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def choose_edit_freq_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    freq = query.data.split(":")[1]
    context.user_data["edit_freq_type"] = freq
    edit_med = context.user_data["edit_med"]
    presets = get_user_time_presets(update.effective_user.id)
    current_times = {r["reminder_time"] for r in edit_med["schedule_rules"]}
    preselected = {s for s in SLOT_ORDER if presets[s] in current_times}
    context.user_data["edit_selected_slots"] = preselected
    await query.edit_message_text(
        "⏰ *Когда принимать?* — выбери один или несколько:",
        parse_mode="Markdown",
        reply_markup=_edit_timeslots_keyboard(preselected, presets)
    )
    return EDIT_TIMES


# ── Edit flow: meal → route by freq type ──────────────────────────────────

@handle_db_errors
async def keep_edit_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["edit_meal"] = context.user_data["edit_med"]["meal_relation"]
    return await _route_after_edit_meal(query, context)


@handle_db_errors
async def edit_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["edit_meal"] = query.data.split(":")[1]
    return await _route_after_edit_meal(query, context)


async def _route_after_edit_meal(query, context):
    freq = context.user_data.get("edit_freq_type", "daily")

    if freq == "daily":
        collected = context.user_data["edit_collected"]
        total = len(collected)
        user_id = context.user_data["edit_user_id"]
        rules = [{"reminder_time": t, "frequency": "daily"} for t in collected]
        update_medication(context.user_data["edit_id"], user_id,
                          context.user_data["edit_name"], context.user_data["edit_dosage"],
                          context.user_data["edit_meal"], total, rules)
        await query.edit_message_text(
            f"✅ Лекарство обновлено!\n\n"
            f"💊 {context.user_data['edit_name']} — {context.user_data['edit_dosage']}\n"
            f"🍽 {MEAL_LABELS[context.user_data['edit_meal']]}\n"
            f"🔢 {total} раз в день\n"
            f"⏰ {', '.join(collected)}"
        )
        context.user_data.clear()
        return ConversationHandler.END

    if freq == "interval":
        await query.edit_message_text("🔄 *Через сколько дней?* (например: 2):",
                                      parse_mode="Markdown", reply_markup=_EDIT_FREQ_INTERVAL_KB)
        return EDIT_FREQ_INTERVAL

    if freq == "weekdays":
        context.user_data["edit_freq_weekdays"] = set()
        await query.edit_message_text(
            "📆 *Дни недели* — выбери и нажми Готово:",
            parse_mode="Markdown",
            reply_markup=_edit_weekdays_keyboard(set())
        )
        return EDIT_FREQ_WEEKDAYS

    if freq == "monthly":
        await query.edit_message_text("🗓 *Какого числа каждого месяца?* (1–31):",
                                      parse_mode="Markdown", reply_markup=_EDIT_FREQ_MONTHDAY_KB)
        return EDIT_FREQ_MONTHDAY

    return ConversationHandler.END


# ── Edit flow: slot toggle → meal ─────────────────────────────────────────

async def edit_timeslot_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot = query.data.split(":")[1]
    selected = context.user_data.setdefault("edit_selected_slots", set())
    selected.discard(slot) if slot in selected else selected.add(slot)
    presets = get_user_time_presets(update.effective_user.id)
    await query.edit_message_reply_markup(reply_markup=_edit_timeslots_keyboard(selected, presets))
    return EDIT_TIMES


async def edit_timeslots_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    selected = context.user_data.get("edit_selected_slots", set())
    if not selected:
        await query.answer("Выбери хотя бы один приём", show_alert=True)
        return EDIT_TIMES
    await query.answer()
    presets = get_user_time_presets(update.effective_user.id)
    context.user_data["edit_collected"] = [presets[s] for s in SLOT_ORDER if s in selected]
    edit_med = context.user_data["edit_med"]
    current_label = MEAL_LABELS.get(edit_med["meal_relation"], edit_med["meal_relation"])
    await query.edit_message_text(
        "🍽 *Приём с пищей* — выбери:",
        parse_mode="Markdown",
        reply_markup=_edit_meal_keyboard(current_label)
    )
    return EDIT_MEAL


# ── Edit flow: advanced paths ──────────────────────────────────────────────

@handle_db_errors
async def edit_freq_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        n = int(update.message.text.strip())
        assert 2 <= n <= 90
    except (ValueError, AssertionError):
        await update.message.reply_text("Введи число от 2 до 90:", reply_markup=_EDIT_FREQ_INTERVAL_KB)
        return EDIT_FREQ_INTERVAL
    user_id = context.user_data["edit_user_id"]
    collected = context.user_data["edit_collected"]
    total = len(collected)
    anchor_date = date.today().isoformat()
    rules = [{"reminder_time": t, "frequency": "interval", "interval_days": n, "anchor_date": anchor_date}
             for t in collected]
    update_medication(context.user_data["edit_id"], user_id,
                      context.user_data["edit_name"], context.user_data["edit_dosage"],
                      context.user_data["edit_meal"], total, rules)
    await update.message.reply_text(
        f"✅ Лекарство обновлено!\n\n"
        f"💊 {context.user_data['edit_name']} — {context.user_data['edit_dosage']}\n"
        f"🍽 {MEAL_LABELS[context.user_data['edit_meal']]}\n"
        f"🔢 {total} раз в день\n"
        f"⏰ {', '.join(collected)} — {_freq_label('interval', n, None, None)}"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def toggle_edit_weekday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    day = int(query.data.split(":")[1])
    selected = context.user_data.setdefault("edit_freq_weekdays", set())
    selected.discard(day) if day in selected else selected.add(day)
    await query.edit_message_reply_markup(reply_markup=_edit_weekdays_keyboard(selected))
    return EDIT_FREQ_WEEKDAYS


@handle_db_errors
async def confirm_edit_weekdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    selected = context.user_data.get("edit_freq_weekdays", set())
    if not selected:
        await query.answer("Выбери хотя бы один день", show_alert=True)
        return EDIT_FREQ_WEEKDAYS
    await query.answer()
    user_id = context.user_data["edit_user_id"]
    collected = context.user_data["edit_collected"]
    total = len(collected)
    weekdays = ",".join(str(d) for d in sorted(selected))
    rules = [{"reminder_time": t, "frequency": "weekdays", "weekdays": weekdays}
             for t in collected]
    update_medication(context.user_data["edit_id"], user_id,
                      context.user_data["edit_name"], context.user_data["edit_dosage"],
                      context.user_data["edit_meal"], total, rules)
    await query.edit_message_text(
        f"✅ Лекарство обновлено!\n\n"
        f"💊 {context.user_data['edit_name']} — {context.user_data['edit_dosage']}\n"
        f"🍽 {MEAL_LABELS[context.user_data['edit_meal']]}\n"
        f"🔢 {total} раз в день\n"
        f"⏰ {', '.join(collected)} — {_freq_label('weekdays', None, weekdays, None)}"
    )
    context.user_data.clear()
    return ConversationHandler.END


@handle_db_errors
async def edit_freq_monthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        day = int(update.message.text.strip())
        assert 1 <= day <= 31
    except (ValueError, AssertionError):
        await update.message.reply_text("Введи число от 1 до 31:", reply_markup=_EDIT_FREQ_MONTHDAY_KB)
        return EDIT_FREQ_MONTHDAY
    user_id = context.user_data["edit_user_id"]
    collected = context.user_data["edit_collected"]
    total = len(collected)
    rules = [{"reminder_time": t, "frequency": "monthly", "month_day": day}
             for t in collected]
    update_medication(context.user_data["edit_id"], user_id,
                      context.user_data["edit_name"], context.user_data["edit_dosage"],
                      context.user_data["edit_meal"], total, rules)
    warning = _monthday_warning(day)
    await update.message.reply_text(
        f"✅ Лекарство обновлено!\n\n"
        f"💊 {context.user_data['edit_name']} — {context.user_data['edit_dosage']}\n"
        f"🍽 {MEAL_LABELS[context.user_data['edit_meal']]}\n"
        f"🔢 {total} раз в день\n"
        f"⏰ {', '.join(collected)} — {_freq_label('monthly', None, None, day)}"
        f"{warning}"
    )
    context.user_data.clear()
    return ConversationHandler.END


# ── Edit flow: back handlers ───────────────────────────────────────────────

async def back_edit_to_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    med = context.user_data["edit_med"]
    await query.edit_message_text(
        f"✏️ *{med['name']}*\n──────────────────\n📝 *Название* — введи новое:",
        parse_mode="Markdown",
        reply_markup=_EDIT_NAME_KB
    )
    return EDIT_NAME


async def back_edit_to_dosage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    med = context.user_data["edit_med"]
    await query.edit_message_text(
        f"📏 *Дозировка* — введи новую\n(текущая: {med['dosage']}):",
        parse_mode="Markdown",
        reply_markup=_EDIT_DOSAGE_KB
    )
    return EDIT_DOSAGE


async def back_edit_to_freq_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rules = context.user_data["edit_med"]["schedule_rules"]
    await query.edit_message_text(
        f"📅 *Расписание* — выбери тип:\nТекущее: {_current_schedule_summary(rules)}",
        parse_mode="Markdown", reply_markup=_edit_freq_type_keyboard()
    )
    return EDIT_FREQ_TYPE


async def back_edit_to_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected = context.user_data.get("edit_selected_slots", set())
    presets = get_user_time_presets(update.effective_user.id)
    await query.edit_message_text(
        "⏰ *Когда принимать?* — выбери один или несколько:",
        parse_mode="Markdown",
        reply_markup=_edit_timeslots_keyboard(selected, presets)
    )
    return EDIT_TIMES


async def back_edit_to_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    edit_med = context.user_data["edit_med"]
    current_label = MEAL_LABELS.get(edit_med["meal_relation"], edit_med["meal_relation"])
    await query.edit_message_text(
        "🍽 *Приём с пищей* — выбери:",
        parse_mode="Markdown",
        reply_markup=_edit_meal_keyboard(current_label)
    )
    return EDIT_MEAL


# ── ConversationHandler factories ──────────────────────────────────────────

def get_add_handler(cancel_handler):
    return ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
            CallbackQueryHandler(handle_add_med_callback, pattern="^add_med$"),
        ],
        states={
            NAME:          [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            DOSAGE:        [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_dosage),
                CallbackQueryHandler(back_add_to_name, pattern="^back_add_to_name$"),
            ],
            TIMES:         [
                CallbackQueryHandler(add_timeslot_toggle, pattern="^timeslot:"),
                CallbackQueryHandler(add_timeslots_confirm, pattern="^timeslots_confirm$"),
                CallbackQueryHandler(back_add_to_dosage, pattern="^back_add_to_dosage$"),
            ],
            MEAL:          [
                CallbackQueryHandler(add_meal, pattern="^(before|after|with|any)$"),
                CallbackQueryHandler(back_add_to_times, pattern="^back_add_to_times$"),
            ],
            FREQ_TYPE:     [
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
            EDIT_NAME:          [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name),
                CallbackQueryHandler(keep_edit_name, pattern="^keep_edit_name$"),
            ],
            EDIT_DOSAGE:        [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_dosage),
                CallbackQueryHandler(keep_edit_dosage, pattern="^keep_edit_dosage$"),
                CallbackQueryHandler(back_edit_to_name, pattern="^back_edit_to_name$"),
            ],
            EDIT_FREQ_TYPE:     [
                CallbackQueryHandler(keep_edit_schedule, pattern="^keep_edit_schedule$"),
                CallbackQueryHandler(choose_edit_freq_type, pattern="^editfreq:"),
                CallbackQueryHandler(back_edit_to_dosage, pattern="^back_edit_to_dosage$"),
            ],
            EDIT_TIMES:         [
                CallbackQueryHandler(edit_timeslot_toggle, pattern="^edittimeslot:"),
                CallbackQueryHandler(edit_timeslots_confirm, pattern="^edit_timeslots_confirm$"),
                CallbackQueryHandler(back_edit_to_freq_type, pattern="^back_edit_to_freq_type$"),
            ],
            EDIT_MEAL:          [
                CallbackQueryHandler(edit_meal, pattern="^editmeal:"),
                CallbackQueryHandler(keep_edit_meal, pattern="^keep_edit_meal$"),
                CallbackQueryHandler(back_edit_to_times, pattern="^back_edit_to_times$"),
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
        },
        fallbacks=[
            cancel_handler,
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
        ],
    )
