"""/start — единственная команда. Deep-link активация + вход в меню по роли."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.views import (
    ensure_admin_user,
    send_user_configs,
    show_admin_menu,
    show_user_menu,
)
from core import messages as msg
from core.config import settings
from core.logging import get_logger
from db.models import User
from services.audit import log_action
from services.key_manager import ActivationError, activate_key
from services.provisioning import provision_subscription
from services.subscription import get_or_create_active_subscription

router = Router(name="start")
logger = get_logger("start")


def _is_admin(user: User | None, tg_id: int) -> bool:
    return (user is not None and user.is_admin) or (tg_id in settings.ADMIN_TELEGRAM_IDS)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: User | None,
    state: FSMContext,
) -> None:
    await state.clear()
    tg = message.from_user
    payload = (command.args or "").strip()

    # (a) Deep-link с ключом активации.
    if payload:
        try:
            profile, subscription = await activate_key(session, payload, tg.id, tg.username)
        except ActivationError as exc:
            await message.answer(msg.KEY_INVALID.get(str(exc), msg.KEY_INVALID_DEFAULT))
            await show_user_menu(message, session, user, edit=False)
            return
        await log_action(
            session,
            actor_id=profile.id,
            action="subscription.activate",
            entity_type="subscription",
            entity_id=subscription.id,
            meta={"key": payload, "via": "deeplink"},
        )
        await provision_subscription(session, subscription, profile)
        await message.answer(msg.ACTIVATED_HEADER)
        await send_user_configs(message, session, profile)
        await show_user_menu(message, session, profile, edit=False)
        return

    # (b) Админ — дефолтный VPN-доступ без ключа.
    if _is_admin(user, tg.id):
        admin = await ensure_admin_user(session, tg)
        subscription = await get_or_create_active_subscription(session, admin)
        await provision_subscription(session, subscription, admin)
        await show_admin_menu(message, edit=False)
        return

    # (c)/(d) Обычный пользователь — меню (с доступом или с приглашением ввести ключ).
    await show_user_menu(message, session, user, edit=False)
