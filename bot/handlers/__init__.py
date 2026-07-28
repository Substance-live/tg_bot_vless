"""Сбор роутеров бота."""

from __future__ import annotations

from aiogram import Router

from bot.handlers import activate, admin, configs, start, status


def get_routers() -> list[Router]:
    # admin — последним (со своим AdminFilter на роутере).
    return [
        start.router,
        activate.router,
        configs.router,
        status.router,
        admin.router,
    ]
