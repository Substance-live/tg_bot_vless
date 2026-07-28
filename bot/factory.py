"""Фабрики aiogram: создание Bot и Dispatcher с подключёнными роутерами."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.handlers import get_routers
from bot.middlewares.auth import AuthMiddleware
from core.config import settings


def create_bot() -> Bot:
    return Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    # Сессия БД + текущий пользователь в каждый апдейт (message и callback_query).
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    for router in get_routers():
        dp.include_router(router)
    return dp
