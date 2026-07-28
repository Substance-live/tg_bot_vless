"""AuthMiddleware: сессия БД + текущий пользователь в каждый апдейт.

Пользователя НЕ создаёт (профиль создаётся админом через /newuser и
привязывается в /activate). Только ищет по telegram_id и инжектит:
  data["session"] -> AsyncSession
  data["user"]    -> User | None
Если telegram_id входит в ADMIN_TELEGRAM_IDS и профиль найден — форсит is_admin.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser
from sqlalchemy import select

from core.config import settings
from db.models import User
from db.session import SessionMaker


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")

        async with SessionMaker() as session:
            user: User | None = None
            if tg_user is not None:
                user = await session.scalar(
                    select(User).where(User.telegram_id == tg_user.id)
                )
                if user is not None and tg_user.id in settings.ADMIN_TELEGRAM_IDS:
                    if not user.is_admin:
                        user.is_admin = True
                        await session.commit()

            data["session"] = session
            data["user"] = user
            return await handler(event, data)
