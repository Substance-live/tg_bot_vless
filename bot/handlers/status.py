"""/status — сводка доступа: привязан, активен, состояние узлов (живьём)."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from core import messages as msg
from db.models import User
from services.node_client import NodeClient, NodeClientError
from services.provisioning import external_id_for, get_active_nodes
from services.subscription import get_active_subscription

router = Router(name="status")


@router.message(Command("status"))
async def cmd_status(message: Message, session: AsyncSession, user: User | None) -> None:
    if user is None:
        await message.answer(msg.status_text(bound=False, active=False, lines=[]))
        return

    subscription = await get_active_subscription(session, user)
    lines: list[str] = []
    if subscription is not None and user.is_active:
        external_id = external_id_for(user)
        for node in await get_active_nodes(session):
            try:
                async with NodeClient(node) as client:
                    vless = await client.get_vless_user(external_id)
                ok = vless is not None
                enabled = vless.get("is_enabled") if vless else None
            except NodeClientError:
                ok, enabled = False, None
            lines.append(msg.status_node_line(node.name, node.country, ok, enabled))

    await message.answer(
        msg.status_text(
            bound=user.telegram_id is not None,
            active=user.is_active and subscription is not None,
            lines=lines,
        )
    )
