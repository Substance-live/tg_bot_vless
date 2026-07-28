"""Точка входа vpn-orchestrator: FastAPI (Admin API/Swagger) + Telegram-бот в одном процессе.

Бот (aiogram polling) запускается как фоновая задача внутри FastAPI lifespan.
Если BOT_TOKEN не задан — бот не стартует, поднимается только API.
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

import uvicorn
from aiogram.types import BotCommand
from fastapi import FastAPI

from api.routers import health
from bot.factory import create_bot, create_dispatcher
from core.config import settings
from core.logging import get_logger, setup_logging
from db.session import SessionMaker
from services.node_seed import seed_nodes

setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
log = get_logger("orchestrator")


@asynccontextmanager
async def lifespan(app: FastAPI):
    bot = None
    polling_task: asyncio.Task | None = None

    # Сидинг узлов из NODES. Best-effort: не роняем API/health при сбое БД.
    try:
        async with SessionMaker() as session:
            nodes = await seed_nodes(session, settings.NODES)
        log.info("nodes.seeded", count=len(nodes))
    except Exception as exc:  # noqa: BLE001
        log.error("nodes.seed_failed", error=str(exc))

    if settings.BOT_TOKEN:
        bot = create_bot()
        dp = create_dispatcher()
        # В меню Telegram публикуем только /start — остальное через кнопки.
        await bot.set_my_commands([BotCommand(command="start", description="Открыть меню")])
        polling_task = asyncio.create_task(
            dp.start_polling(bot, handle_signals=False),
            name="bot-polling",
        )
        log.info("bot.started", mode="polling")
    else:
        log.warning("bot.disabled", reason="BOT_TOKEN is empty; running API only")

    try:
        yield
    finally:
        if polling_task is not None:
            polling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await polling_task
        if bot is not None:
            await bot.session.close()
            log.info("bot.stopped")


app = FastAPI(title="vpn-orchestrator", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
    )
