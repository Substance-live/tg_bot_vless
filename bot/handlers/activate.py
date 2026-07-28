"""/activate <key> — привязка Telegram к профилю и провизия конфигов."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.configs import send_user_configs
from core import messages as msg
from core.logging import get_logger
from db.models import User
from services.audit import log_action
from services.key_manager import ActivationError, activate_key
from services.provisioning import provision_subscription

router = Router(name="activate")
logger = get_logger("activate")


@router.message(Command("activate"))
async def cmd_activate(
    message: Message, command, session: AsyncSession, user: User | None
) -> None:
    key_value = (command.args or "").strip()
    if not key_value:
        await message.answer(msg.NEED_KEY_ARG)
        return

    tg = message.from_user
    try:
        profile, subscription = await activate_key(
            session, key_value, tg.id, tg.username
        )
    except ActivationError as exc:
        await message.answer(msg.KEY_INVALID.get(str(exc), msg.KEY_INVALID_DEFAULT))
        return

    await log_action(
        session,
        actor_id=profile.id,
        action="subscription.activate",
        entity_type="subscription",
        entity_id=subscription.id,
        meta={"key": key_value},
    )

    # Провизия на всех активных узлах (частичные сбои → pending, не блокируют).
    await provision_subscription(session, subscription, profile)

    await message.answer(msg.ACTIVATED_HEADER)
    await send_user_configs(message, session, profile)
