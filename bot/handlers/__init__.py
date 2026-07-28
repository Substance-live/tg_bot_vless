"""Сбор роутеров бота (кнопочный интерфейс)."""

from __future__ import annotations

from aiogram import Router

from bot.handlers import admin_cb, start, user_cb


def get_routers() -> list[Router]:
    # start — только команда /start; user_cb — навигация + FSM (без фильтра);
    # admin_cb — под AdminFilter на уровне роутера.
    return [
        start.router,
        user_cb.router,
        admin_cb.router,
    ]
