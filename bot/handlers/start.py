"""Хендлер /start."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from core import messages as msg
from db.models import User

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, user: User | None) -> None:
    if user is not None and user.telegram_id is not None and user.is_active:
        await message.answer(msg.WELCOME_BOUND)
    else:
        await message.answer(msg.WELCOME_NEED_KEY)
