"""Callback-хендлеры админа: пользователи, карточки, создание с deep-link."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.admin import AdminFilter
from bot.keyboards.menus import (
    NAV_ADMIN,
    NAV_ADMIN_NEWUSER,
    NAV_ADMIN_TEMPLINK,
    NAV_ADMIN_USERS,
    TempLinkCB,
    UserCardCB,
    UsersPageCB,
    back_kb,
    templink_menu_kb,
    user_card_kb,
    users_list_kb,
)
from bot.views import ensure_admin_user, safe_edit, show_admin_menu
from core import messages as msg
from db.models import ActivationKey, User
from services.audit import log_action
from services.key_manager import create_user_with_key
from services.provisioning import set_user_enabled_on_nodes
from services.subscription import (
    get_active_subscription,
    get_user_by_id,
    list_user_profiles,
)

router = Router(name="admin_cb")
router.callback_query.filter(AdminFilter())


@router.callback_query(F.data == NAV_ADMIN)
async def cb_admin_menu(cb: CallbackQuery) -> None:
    await show_admin_menu(cb.message, edit=True)
    await cb.answer()


async def _render_users(cb: CallbackQuery, session: AsyncSession, page: int) -> None:
    profiles = await list_user_profiles(session)
    await safe_edit(cb.message, msg.USERS_LIST_TITLE, users_list_kb(profiles, page))


@router.callback_query(F.data == NAV_ADMIN_USERS)
async def cb_users_list(cb: CallbackQuery, session: AsyncSession) -> None:
    await _render_users(cb, session, 0)
    await cb.answer()


@router.callback_query(UsersPageCB.filter())
async def cb_users_page(
    cb: CallbackQuery, callback_data: UsersPageCB, session: AsyncSession
) -> None:
    await _render_users(cb, session, callback_data.page)
    await cb.answer()


async def _render_card(cb: CallbackQuery, session: AsyncSession, target: User) -> None:
    sub = await get_active_subscription(session, target)
    expires_at = sub.expires_at if sub else None
    text = msg.user_card_text(
        target.name,
        target.telegram_username,
        target.telegram_id,
        target.is_active,
        expires_at=expires_at,
        is_admin=target.is_admin,
    )
    await safe_edit(cb.message, text, user_card_kb(target))


@router.callback_query(UserCardCB.filter(F.action == "open"))
async def cb_user_card(
    cb: CallbackQuery, callback_data: UserCardCB, session: AsyncSession
) -> None:
    target = await get_user_by_id(session, callback_data.user_id)
    if target is None:
        await cb.answer(msg.USER_CARD_NOT_FOUND, show_alert=True)
        return
    await _render_card(cb, session, target)
    await cb.answer()


@router.callback_query(UserCardCB.filter(F.action.in_({"on", "off"})))
async def cb_user_toggle(
    cb: CallbackQuery, callback_data: UserCardCB, session: AsyncSession
) -> None:
    target = await get_user_by_id(session, callback_data.user_id)
    if target is None:
        await cb.answer(msg.USER_CARD_NOT_FOUND, show_alert=True)
        return
    # Админ-аккаунт нельзя делать неактивным (ни другого, ни себя).
    if target.is_admin:
        await cb.answer("Нельзя отключить администратора", show_alert=True)
        return
    enabled = callback_data.action == "on"
    target.is_active = enabled
    await session.commit()

    per_node = await set_user_enabled_on_nodes(session, target, enabled)
    admin = await ensure_admin_user(session, cb.from_user)
    await log_action(
        session,
        actor_id=admin.id,
        action="user.enable" if enabled else "user.disable",
        entity_type="user",
        entity_id=target.id,
        meta={"nodes": {name: ok for name, ok in per_node}},
    )
    await session.refresh(target)
    await _render_card(cb, session, target)
    await cb.answer("🟢 Включён" if enabled else "🔴 Отключён")


@router.callback_query(UserCardCB.filter(F.action == "link"))
async def cb_user_link(
    cb: CallbackQuery, callback_data: UserCardCB, session: AsyncSession
) -> None:
    target = await get_user_by_id(session, callback_data.user_id)
    if target is None:
        await cb.answer(msg.USER_CARD_NOT_FOUND, show_alert=True)
        return
    key = None
    if target.secret_key_id:
        key = await session.scalar(
            select(ActivationKey).where(ActivationKey.id == target.secret_key_id)
        )
    if key is None or key.is_used:
        await cb.answer("Профиль уже активирован или ключ недоступен", show_alert=True)
        return
    me = await cb.bot.me()
    link = f"https://t.me/{me.username}?start={key.key_value}"
    await safe_edit(
        cb.message,
        msg.admin_key_created_link(target.name, key.key_value, link),
        back_kb(NAV_ADMIN_USERS),
    )
    await cb.answer()


@router.callback_query(F.data == NAV_ADMIN_NEWUSER)
async def cb_newuser(cb: CallbackQuery, session: AsyncSession) -> None:
    admin = await ensure_admin_user(session, cb.from_user)
    profile, key = await create_user_with_key(session, admin, name=None)
    await log_action(
        session,
        actor_id=admin.id,
        action="user.create",
        entity_type="user",
        entity_id=profile.id,
        meta={"via": "button"},
    )
    me = await cb.bot.me()
    link = f"https://t.me/{me.username}?start={key.key_value}"
    await safe_edit(
        cb.message,
        msg.admin_key_created_link(profile.name, key.key_value, link),
        back_kb(NAV_ADMIN),
    )
    await cb.answer()


@router.callback_query(F.data == NAV_ADMIN_TEMPLINK)
async def cb_templink_menu(cb: CallbackQuery) -> None:
    await safe_edit(cb.message, msg.TEMPLINK_TITLE, templink_menu_kb())
    await cb.answer()


@router.callback_query(TempLinkCB.filter())
async def cb_templink_create(
    cb: CallbackQuery, callback_data: TempLinkCB, session: AsyncSession
) -> None:
    days = callback_data.days
    admin = await ensure_admin_user(session, cb.from_user)
    profile, key = await create_user_with_key(session, admin, name=None, duration_days=days)
    await log_action(
        session,
        actor_id=admin.id,
        action="user.create",
        entity_type="user",
        entity_id=profile.id,
        meta={"via": "templink", "duration_days": days},
    )
    me = await cb.bot.me()
    link = f"https://t.me/{me.username}?start={key.key_value}"
    await safe_edit(
        cb.message,
        msg.admin_templink_created(profile.name, key.key_value, link, days),
        back_kb(NAV_ADMIN),
    )
    await cb.answer()
