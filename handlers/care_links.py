"""F10-B: подтверждение/отклонение связей «Забота» прямо в боте.

Уведомления из API (caregiver_links / dependent_shares) несут inline-кнопки
с callback_data `cglink:confirm|decline:{link_id}` и
`depshare:confirm|decline:{share_id}`. Эти хендлеры дёргают те же db-функции,
что и Mini App, и шлют обратное уведомление инициатору.
"""
from telegram.ext import CallbackQueryHandler

import database as db
from utils import handle_db_errors


def _uname(username, fallback):
    return f"@{username}" if username else fallback


@handle_db_errors
async def handle_cglink_callback(update, context):
    """cglink:confirm|decline:{link_id} — подопечный решает по запросу помощника."""
    query = update.callback_query
    await query.answer()
    _, action, raw_id = query.data.split(":")
    link_id = int(raw_id)
    dependent_tid = update.effective_user.id
    parties = db.get_caregiver_link_parties(link_id)
    care_tid = parties.get("caregiver_telegram_id") if parties else None
    dep_label = _uname(parties.get("dependent_username") if parties else None, "Ваш близкий")

    if action == "confirm":
        result = db.confirm_caregiver_link(link_id, dependent_tid)
        if result == "ok":
            await query.edit_message_text("✅ Связь подтверждена. Помощник видит ваши приёмы.")
            if care_tid:
                await context.bot.send_message(
                    care_tid, f"✅ {dep_label} подтвердил связь. Теперь вы видите его приёмы в приложении."
                )
        elif result == "limit":
            await query.edit_message_text("⚠️ Лимит близких достигнут (максимум 2).")
        else:
            await query.edit_message_text("Запрос не найден или уже обработан.")
    else:  # decline
        ok = db.decline_caregiver_link(link_id, dependent_tid)
        if ok:
            await query.edit_message_text("❌ Запрос отклонён.")
            if care_tid:
                await context.bot.send_message(
                    care_tid, f"❌ {dep_label} отклонил запрос на подключение помощника."
                )
        else:
            await query.edit_message_text("Запрос не найден или уже обработан.")


@handle_db_errors
async def handle_depshare_callback(update, context):
    """depshare:confirm|decline:{share_id} — владелец решает по запросу наблюдателя."""
    query = update.callback_query
    await query.answer()
    _, action, raw_id = query.data.split(":")
    share_id = int(raw_id)
    owner_tid = update.effective_user.id
    parties = db.get_dep_share_parties(share_id)
    viewer_tid = parties.get("viewer_telegram_id") if parties else None
    dep_name = parties.get("dep_name", "") if parties else ""

    if action == "confirm":
        try:
            db.confirm_dep_share(share_id, owner_tid)
        except db.DatabaseError as e:
            await query.edit_message_text(f"⚠️ {e}")
            return
        await query.edit_message_text(f"✅ Доступ к «{dep_name}» подтверждён.")
        if viewer_tid:
            await context.bot.send_message(
                viewer_tid, f"✅ Доступ к «{dep_name}» подтверждён. Откройте приложение."
            )
    else:  # decline
        ok = db.decline_dep_share(share_id, owner_tid)
        if ok:
            await query.edit_message_text(f"❌ Запрос на помощь с «{dep_name}» отклонён.")
            if viewer_tid:
                await context.bot.send_message(
                    viewer_tid, f"❌ Запрос на помощь с «{dep_name}» отклонён."
                )
        else:
            await query.edit_message_text("Запрос не найден или уже обработан.")


def get_handlers():
    return [
        CallbackQueryHandler(handle_cglink_callback, pattern=r"^cglink:(confirm|decline):\d+$"),
        CallbackQueryHandler(handle_depshare_callback, pattern=r"^depshare:(confirm|decline):\d+$"),
    ]
