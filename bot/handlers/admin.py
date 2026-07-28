"""Админ-команды: /newuser, /users, /enable, /disable (под AdminFilter)."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.admin import AdminFilter
from core import messages as msg
from db.models import User
from services.audit import log_action
from services.key_manager import create_user_with_key
from services.provisioning import set_user_enabled_on_nodes
from services.subscription import get_user_by_ref, list_user_profiles

router = Router(name="admin")
# Все хендлеры роутера — только для админов.
router.message.filter(AdminFilter())


async def _ensure_admin_user(session: AsyncSession, message: Message, user: User | None) -> User:
    """Возвращает user-строку админа, создавая её при первом действии."""
    if user is not None:
        return user
    tg = message.from_user
    admin = User(
        telegram_id=tg.id,
        telegram_username=tg.username,
        name=tg.full_name,
        is_active=True,
        is_admin=True,
    )
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    return admin


@router.message(Command("newuser"))
async def cmd_newuser(
    message: Message, command, session: AsyncSession, user: User | None
) -> None:
    admin = await _ensure_admin_user(session, message, user)
    name = (command.args or "").strip() or None
    profile, key = await create_user_with_key(session, admin, name)
    await log_action(
        session,
        actor_id=admin.id,
        action="user.create",
        entity_type="user",
        entity_id=profile.id,
        meta={"name": name},
    )
    await message.answer(msg.admin_key_created(name, key.key_value))


@router.message(Command("users"))
async def cmd_users(message: Message, session: AsyncSession, user: User | None) -> None:
    profiles = await list_user_profiles(session)
    if not profiles:
        await message.answer(msg.USER_LIST_EMPTY)
        return
    rows = [
        msg.user_list_row(
            p.name, p.telegram_id, p.is_active, bound=p.telegram_id is not None
        )
        for p in profiles
    ]
    await message.answer(msg.USER_LIST_HEADER + "\n".join(rows))


async def _toggle(
    message: Message, command, session: AsyncSession, user: User | None, enabled: bool
) -> None:
    admin = await _ensure_admin_user(session, message, user)
    ref = (command.args or "").strip()
    if not ref:
        cmd = "enable" if enabled else "disable"
        await message.answer(msg.ADMIN_NEED_REF.format(cmd=cmd))
        return

    target = await get_user_by_ref(session, ref)
    if target is None:
        await message.answer(msg.ADMIN_USER_NOT_FOUND.format(ref=ref))
        return

    target.is_active = enabled
    await session.commit()

    per_node = await set_user_enabled_on_nodes(session, target, enabled)
    await log_action(
        session,
        actor_id=admin.id,
        action="user.enable" if enabled else "user.disable",
        entity_type="user",
        entity_id=target.id,
        meta={"nodes": {name: ok for name, ok in per_node}},
    )
    lines = [msg.admin_node_result(name, ok) for name, ok in per_node]
    await message.answer(msg.admin_toggle_result(target.name, enabled, lines))


@router.message(Command("enable"))
async def cmd_enable(
    message: Message, command, session: AsyncSession, user: User | None
) -> None:
    await _toggle(message, command, session, user, enabled=True)


@router.message(Command("disable"))
async def cmd_disable(
    message: Message, command, session: AsyncSession, user: User | None
) -> None:
    await _toggle(message, command, session, user, enabled=False)
