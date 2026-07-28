"""/configs — живой рендер конфигураций пользователя из node-агентов."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import LinkPreviewOptions, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils import render_qr
from core import messages as msg
from db.models import User
from services.node_client import NodeClient, NodeClientError
from services.provisioning import external_id_for, get_active_nodes
from services.subscription import get_active_subscription

router = Router(name="configs")


async def require_access(message: Message, session: AsyncSession, user: User | None) -> bool:
    """Проверка доступа: привязан, активен, есть подписка. Иначе шлёт ответ."""
    if user is None:
        await message.answer(msg.NO_SUBSCRIPTION)
        return False
    if not user.is_active:
        await message.answer(msg.ACCOUNT_DISABLED)
        return False
    subscription = await get_active_subscription(session, user)
    if subscription is None:
        await message.answer(msg.NO_SUBSCRIPTION)
        return False
    return True


async def send_user_configs(message: Message, session: AsyncSession, user: User) -> None:
    """Читает конфиги живьём со всех активных узлов и отправляет пользователю."""
    nodes = await get_active_nodes(session)
    if not nodes:
        await message.answer(msg.NO_NODES)
        return

    external_id = external_id_for(user)
    for node in nodes:
        try:
            async with NodeClient(node) as client:
                vless = await client.get_vless_user(external_id)
                try:
                    mtproto = await client.get_mtproto_info()
                except NodeClientError:
                    mtproto = None
        except NodeClientError:
            await message.answer(
                msg.NODE_UNAVAILABLE.format(name=node.name, country=node.country)
            )
            continue

        if vless is None:
            await message.answer(
                msg.NODE_UNAVAILABLE.format(name=node.name, country=node.country)
            )
            continue

        block = msg.config_node_block(
            node.name, node.country, vless["config_link"], vless.get("is_enabled", True)
        )
        if mtproto and mtproto.get("tg_link"):
            block += "\n\n" + msg.mtproto_block(mtproto["tg_link"])
        await message.answer(
            block, link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
        await message.answer_photo(
            render_qr(vless["config_link"]), caption=f"QR · {node.name}"
        )


@router.message(Command("configs"))
async def cmd_configs(message: Message, session: AsyncSession, user: User | None) -> None:
    if not await require_access(message, session, user):
        return
    await send_user_configs(message, session, user)
