"""AdminFilter: пропускает только администраторов."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject, User as TgUser

from core.config import settings
from db.models import User


class AdminFilter(BaseFilter):
    async def __call__(
        self,
        event: TelegramObject,
        user: User | None = None,
        event_from_user: TgUser | None = None,
    ) -> bool:
        if user is not None and user.is_admin:
            return True
        if event_from_user is not None and event_from_user.id in settings.ADMIN_TELEGRAM_IDS:
            return True
        return False
