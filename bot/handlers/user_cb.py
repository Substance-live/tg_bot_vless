"""Callback-хендлеры пользователя: навигация, конфиги, статус, ввод ключа (FSM)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.menus import (
    KEY_CANCEL,
    KEY_ENTER,
    NAV_ADMIN,
    NAV_CONFIGS,
    NAV_STATUS,
    NAV_USER,
    ConfigCB,
    back_kb,
    cancel_kb,
    config_back_kb,
    config_node_kb,
)
from bot.states import ActivateStates
from bot.utils import render_qr
from bot.views import (
    fetch_node_vless,
    get_node,
    is_admin_ctx,
    require_access,
    safe_delete,
    safe_edit,
    send_user_configs,
    show_configs_servers,
    show_user_menu,
    status_view,
)
from core import messages as msg
from core.logging import get_logger
from db.models import User
from services.audit import log_action
from services.key_manager import ActivationError, activate_key
from services.provisioning import provision_subscription

router = Router(name="user_cb")
logger = get_logger("user_cb")


@router.callback_query(F.data == NAV_USER)
async def cb_user_menu(cb: CallbackQuery, session: AsyncSession, user: User | None) -> None:
    await show_user_menu(cb.message, session, user, edit=True)
    await cb.answer()


@router.callback_query(F.data == NAV_CONFIGS)
async def cb_configs(cb: CallbackQuery, session: AsyncSession, user: User | None) -> None:
    if not await require_access(cb.message, session, user):
        await cb.answer()
        return
    await show_configs_servers(cb.message, session, user, edit=True)
    await cb.answer()


@router.callback_query(ConfigCB.filter(F.action == "node"))
async def cb_config_node(
    cb: CallbackQuery, callback_data: ConfigCB, session: AsyncSession, user: User | None
) -> None:
    """Экран выбора формата. Может прийти из списка (текст) или с QR (фото)."""
    if not await require_access(cb.message, session, user):
        await cb.answer()
        return
    node = await get_node(session, callback_data.node_id)
    if node is None:
        await cb.answer(msg.CONFIG_NO_DATA, show_alert=True)
        return
    _, enabled, _ = await fetch_node_vless(node, user)
    text = msg.configs_node_screen(node.name, enabled)
    kb = config_node_kb(node.id)
    if cb.message.photo:  # пришли с QR-фото — текст в фото не превратить, пересоздаём
        await safe_delete(cb.message)
        await cb.message.answer(text, reply_markup=kb)
    else:
        await safe_edit(cb.message, text, kb)
    await cb.answer()


@router.callback_query(ConfigCB.filter(F.action == "link"))
async def cb_config_link(
    cb: CallbackQuery, callback_data: ConfigCB, session: AsyncSession, user: User | None
) -> None:
    """Ссылка — правим то же (текстовое) сообщение выбора формата."""
    if not await require_access(cb.message, session, user):
        await cb.answer()
        return
    node = await get_node(session, callback_data.node_id)
    if node is None:
        await cb.answer(msg.CONFIG_NO_DATA, show_alert=True)
        return
    link, enabled, mtproto = await fetch_node_vless(node, user)
    if link is None:
        await cb.answer(msg.CONFIG_NO_DATA, show_alert=True)
        return
    block = msg.config_node_block(node.name, link, enabled)
    if mtproto and mtproto.get("tg_link"):
        block += "\n\n" + msg.mtproto_block(mtproto["tg_link"])
    await safe_edit(cb.message, block, config_back_kb(node.id), disable_preview=True)
    await cb.answer()


@router.callback_query(ConfigCB.filter(F.action == "qr"))
async def cb_config_qr(
    cb: CallbackQuery, callback_data: ConfigCB, session: AsyncSession, user: User | None
) -> None:
    """QR — заменяем текстовое сообщение фото (удаляем + шлём фото)."""
    if not await require_access(cb.message, session, user):
        await cb.answer()
        return
    node = await get_node(session, callback_data.node_id)
    if node is None:
        await cb.answer(msg.CONFIG_NO_DATA, show_alert=True)
        return
    link, _, _ = await fetch_node_vless(node, user)
    if link is None:
        await cb.answer(msg.CONFIG_NO_DATA, show_alert=True)
        return
    await safe_delete(cb.message)
    await cb.message.answer_photo(
        render_qr(link),
        caption=f"QR · {node.name}",
        reply_markup=config_back_kb(node.id),
    )
    await cb.answer()


@router.callback_query(F.data == NAV_STATUS)
async def cb_status(cb: CallbackQuery, session: AsyncSession, user: User | None) -> None:
    text = await status_view(session, user)
    back = NAV_ADMIN if is_admin_ctx(user, cb.from_user) else NAV_USER
    await safe_edit(cb.message, text, back_kb(back))
    await cb.answer()


@router.callback_query(F.data == KEY_ENTER)
async def cb_enter_key(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ActivateStates.waiting_key)
    await safe_edit(cb.message, msg.ENTER_KEY_PROMPT, cancel_kb())
    await cb.answer()


@router.callback_query(F.data == KEY_CANCEL)
async def cb_cancel_key(
    cb: CallbackQuery, state: FSMContext, session: AsyncSession, user: User | None
) -> None:
    await state.clear()
    await show_user_menu(cb.message, session, user, edit=True)
    await cb.answer(msg.KEY_CANCELLED)


@router.message(ActivateStates.waiting_key)
async def on_key_text(
    message: Message, state: FSMContext, session: AsyncSession, user: User | None
) -> None:
    key_value = (message.text or "").strip()
    tg = message.from_user
    try:
        profile, subscription = await activate_key(session, key_value, tg.id, tg.username)
    except ActivationError as exc:
        # Оставляем состояние — пользователь может повторить ввод.
        await message.answer(msg.KEY_INVALID.get(str(exc), msg.KEY_INVALID_DEFAULT))
        return

    await state.clear()
    await log_action(
        session,
        actor_id=profile.id,
        action="subscription.activate",
        entity_type="subscription",
        entity_id=subscription.id,
        meta={"key": key_value, "via": "manual"},
    )
    await provision_subscription(session, subscription, profile)
    await message.answer(msg.ACTIVATED_HEADER)
    await send_user_configs(message, session, profile)
    await show_user_menu(message, session, profile, edit=False)
