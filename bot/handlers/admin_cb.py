"""Callback-хендлеры админа: пользователи, карточки, создание с deep-link."""

from __future__ import annotations

from datetime import datetime, timezone

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
    user_delete_confirm_kb,
    users_list_kb,
)
from bot.views import ensure_admin_user, safe_edit, show_admin_menu
from core import messages as msg
from db.models import ActivationKey, User
from services.audit import log_action
from services.key_manager import create_user_with_key, reissue_key
from services.provisioning import set_user_enabled_on_nodes
from services.subscription import get_active_subscription, get_user_by_id
from services.user_admin import (
    ProfileState,
    cleanup_expired_pending,
    delete_user,
    link_ttl,
    list_profiles_with_keys,
    profile_state,
    unbind_telegram,
)

router = Router(name="admin_cb")
router.callback_query.filter(AdminFilter())


async def _load_key(session: AsyncSession, target: User) -> ActivationKey | None:
    if target.secret_key_id is None:
        return None
    return await session.scalar(
        select(ActivationKey).where(ActivationKey.id == target.secret_key_id)
    )


@router.callback_query(F.data == NAV_ADMIN)
async def cb_admin_menu(cb: CallbackQuery) -> None:
    await show_admin_menu(cb.message, edit=True)
    await cb.answer()


async def _render_users(cb: CallbackQuery, session: AsyncSession, page: int) -> None:
    await cleanup_expired_pending(session)
    now = datetime.now(timezone.utc)
    ttl = link_ttl()
    rows: list[tuple] = []
    for user, key in await list_profiles_with_keys(session):
        state, remaining = profile_state(user, key, now, ttl)
        label = msg.profile_label(
            state.name,
            remaining,
            user.name,
            user.telegram_username,
            key.key_value if key else None,
        )
        rows.append((user.id, label))
    await safe_edit(cb.message, msg.USERS_LIST_TITLE, users_list_kb(rows, page))


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
    key = await _load_key(session, target)
    now = datetime.now(timezone.utc)
    ttl = link_ttl()
    state, remaining = profile_state(target, key, now, ttl)
    sub = await get_active_subscription(session, target)
    expires_at = sub.expires_at if sub else None

    note = None
    if state == ProfileState.PENDING and remaining:
        m, ss = divmod(remaining, 60)
        note = f"⏳ ожидание активации, осталось {m}:{ss:02d}"
    elif state == ProfileState.DETACHED:
        note = "⚪ TG отвязан"

    text = msg.user_card_text(
        target.name,
        target.telegram_username,
        target.telegram_id,
        target.is_active,
        expires_at=expires_at,
        is_admin=target.is_admin,
        note=note,
    )
    await safe_edit(cb.message, text, user_card_kb(target, state))


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
    key = await _load_key(session, target)
    now = datetime.now(timezone.utc)
    expiry = None
    if key is not None:
        expiry = key.key_expires_at or (key.created_at + link_ttl())
    valid = key is not None and not key.is_used and expiry is not None and expiry > now
    key_value = key.key_value if valid else await reissue_key(session, target)

    me = await cb.bot.me()
    link = f"https://t.me/{me.username}?start={key_value}"
    await safe_edit(
        cb.message,
        msg.admin_key_created_link(target.name, key_value, link),
        back_kb(NAV_ADMIN_USERS),
    )
    await cb.answer()


@router.callback_query(UserCardCB.filter(F.action == "unbind"))
async def cb_user_unbind(
    cb: CallbackQuery, callback_data: UserCardCB, session: AsyncSession
) -> None:
    target = await get_user_by_id(session, callback_data.user_id)
    if target is None:
        await cb.answer(msg.USER_CARD_NOT_FOUND, show_alert=True)
        return
    if target.is_admin:
        await cb.answer("Нельзя отвязать администратора", show_alert=True)
        return
    if target.telegram_id is None:
        await cb.answer("TG уже отвязан", show_alert=True)
        return
    await unbind_telegram(session, target)
    admin = await ensure_admin_user(session, cb.from_user)
    await log_action(
        session, actor_id=admin.id, action="user.unbind",
        entity_type="user", entity_id=target.id,
    )
    await session.refresh(target)
    await _render_card(cb, session, target)
    await cb.answer("🔓 TG отвязан")


@router.callback_query(UserCardCB.filter(F.action == "del"))
async def cb_user_delete(
    cb: CallbackQuery, callback_data: UserCardCB, session: AsyncSession
) -> None:
    target = await get_user_by_id(session, callback_data.user_id)
    if target is None:
        await cb.answer(msg.USER_CARD_NOT_FOUND, show_alert=True)
        return
    if target.is_admin:
        await cb.answer("Нельзя удалить администратора", show_alert=True)
        return
    await safe_edit(cb.message, msg.USER_DELETE_CONFIRM, user_delete_confirm_kb(target.id))
    await cb.answer()


@router.callback_query(UserCardCB.filter(F.action == "del_yes"))
async def cb_user_delete_confirm(
    cb: CallbackQuery, callback_data: UserCardCB, session: AsyncSession
) -> None:
    target = await get_user_by_id(session, callback_data.user_id)
    if target is None:
        await cb.answer(msg.USER_CARD_NOT_FOUND, show_alert=True)
        return
    if target.is_admin:
        await cb.answer("Нельзя удалить администратора", show_alert=True)
        return
    admin = await ensure_admin_user(session, cb.from_user)
    target_id = target.id
    await delete_user(session, target)
    await log_action(
        session, actor_id=admin.id, action="user.delete",
        entity_type="user", entity_id=target_id,
    )
    await _render_users(cb, session, 0)
    await cb.answer("🗑 Удалён")


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
