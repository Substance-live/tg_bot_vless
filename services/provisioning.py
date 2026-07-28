"""Провизия подписки на узлах и массовое включение/отключение VLESS.

Все узлы обрабатываются параллельно (asyncio.gather, return_exceptions=True):
один мёртвый узел не блокирует остальных (02 §7.1). VLESS создаётся под
external_id = str(user.id); MTProto — общая ссылка узла.
"""

from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.logging import get_logger
from db.models import (
    Node,
    NodeConfig,
    NodeConfigProtocol,
    NodeConfigStatus,
    Subscription,
    User,
)
from services.node_client import NodeClient, NodeClientError

logger = get_logger("provisioning")

EXPIRE_NEVER = 0  # бессрочный доступ.


def external_id_for(user: User) -> str:
    return str(user.id)


def build_remark(user: User) -> str:
    """Имя конфига в клиенте: "<prefix>_<ник>" (ник из TG / имени / id)."""
    raw = (
        user.telegram_username
        or user.name
        or (str(user.telegram_id) if user.telegram_id else str(user.id)[:8])
    )
    nick = re.sub(r"\s+", "_", raw.strip()) or "user"
    return f"{settings.VLESS_REMARK_PREFIX}_{nick}"


def expire_days_for(subscription: Subscription) -> int:
    """expire_days для узла из subscription.expires_at.

    None → 0 (бессрочно). Иначе — оставшиеся сутки, минимум 1 (узел оперирует
    целыми днями). Прошедший срок → 1 (клиент истёк).
    """
    if subscription.expires_at is None:
        return EXPIRE_NEVER
    now = datetime.now(timezone.utc)
    remaining = (subscription.expires_at - now).total_seconds()
    if remaining <= 0:
        return 1  # уже истекло — узел покажет клиента истёкшим
    return max(1, math.ceil(remaining / 86400))


async def get_active_nodes(session: AsyncSession) -> list[Node]:
    result = await session.execute(select(Node).where(Node.is_active.is_(True)))
    return list(result.scalars().all())


@dataclass
class _NodeProvisionResult:
    node: Node
    vless: dict | None = None
    vless_error: str | None = None
    mtproto: dict | None = None
    mtproto_error: str | None = None


async def _provision_one_node(
    node: Node, external_id: str, remark: str, expire_days: int
) -> _NodeProvisionResult:
    res = _NodeProvisionResult(node=node)
    async with NodeClient(node) as client:
        try:
            res.vless = await client.create_vless_user(
                external_id, expire_days=expire_days, remark=remark
            )
        except NodeClientError as exc:
            res.vless_error = str(exc)
            logger.warning("provision.vless_failed", node=node.name, error=str(exc))
        try:
            res.mtproto = await client.get_mtproto_info()
        except NodeClientError as exc:
            res.mtproto_error = str(exc)
            logger.warning("provision.mtproto_failed", node=node.name, error=str(exc))
    return res


async def provision_subscription(
    session: AsyncSession, subscription: Subscription, user: User
) -> list[NodeConfig]:
    """Создаёт/обновляет node_configs (vless+mtproto) на всех активных узлах."""
    nodes = await get_active_nodes(session)
    if not nodes:
        return []

    external_id = external_id_for(user)
    remark = build_remark(user)
    expire_days = expire_days_for(subscription)

    results: list[_NodeProvisionResult] = await asyncio.gather(
        *(_provision_one_node(node, external_id, remark, expire_days) for node in nodes)
    )

    # Существующие конфиги подписки → map (node_id, protocol) -> NodeConfig.
    existing_rows = (
        await session.execute(
            select(NodeConfig).where(NodeConfig.subscription_id == subscription.id)
        )
    ).scalars().all()
    existing = {(c.node_id, c.protocol): c for c in existing_rows}

    def _upsert(
        node_id, protocol: NodeConfigProtocol, external_config_id, config_data, status
    ) -> NodeConfig:
        cfg = existing.get((node_id, protocol))
        if cfg is None:
            cfg = NodeConfig(
                subscription_id=subscription.id,
                node_id=node_id,
                protocol=protocol,
                external_config_id=external_config_id,
                config_data=config_data,
                status=status,
            )
            session.add(cfg)
            existing[(node_id, protocol)] = cfg
        else:
            cfg.external_config_id = external_config_id
            cfg.config_data = config_data
            cfg.status = status
        return cfg

    configs: list[NodeConfig] = []
    for res in results:
        # VLESS
        if res.vless is not None:
            configs.append(
                _upsert(
                    res.node.id,
                    NodeConfigProtocol.vless,
                    external_id,
                    {"config_link": res.vless.get("config_link")},
                    NodeConfigStatus.active,
                )
            )
        else:
            configs.append(
                _upsert(
                    res.node.id, NodeConfigProtocol.vless, external_id, None,
                    NodeConfigStatus.pending,
                )
            )
        # MTProto
        if res.mtproto is not None:
            configs.append(
                _upsert(
                    res.node.id,
                    NodeConfigProtocol.mtproto,
                    None,
                    {"tg_link": res.mtproto.get("tg_link")},
                    NodeConfigStatus.active,
                )
            )
        else:
            configs.append(
                _upsert(
                    res.node.id, NodeConfigProtocol.mtproto, None, None,
                    NodeConfigStatus.pending,
                )
            )

    await session.commit()
    return configs


async def set_user_enabled_on_nodes(
    session: AsyncSession, user: User, enabled: bool
) -> list[tuple[str, bool]]:
    """set_vless_enabled на всех активных узлах. Возвращает [(имя_узла, ok)]."""
    nodes = await get_active_nodes(session)
    external_id = external_id_for(user)

    async def _toggle(node: Node) -> tuple[str, bool]:
        try:
            async with NodeClient(node) as client:
                await client.set_vless_enabled(external_id, enabled)
            return node.name, True
        except NodeClientError as exc:
            logger.warning("toggle.failed", node=node.name, error=str(exc))
            return node.name, False

    if not nodes:
        return []
    return list(await asyncio.gather(*(_toggle(node) for node in nodes)))
