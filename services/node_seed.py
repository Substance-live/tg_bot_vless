"""Сидинг узлов из settings.NODES (JSON) в таблицу nodes при старте.

Секреты узлов задаются только здесь (в .env), не через Telegram.
Upsert по agent_url: обновляет name/country/secret, форсит is_active=True;
вставляет отсутствующие.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models import Node

logger = get_logger("node_seed")

_REQUIRED = ("name", "country", "agent_url", "agent_secret")


def _parse_nodes(raw: str) -> list[dict]:
    raw = (raw or "").strip()
    if not raw or raw == "[]":
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("NODES must be a JSON array")
    for item in data:
        missing = [k for k in _REQUIRED if not item.get(k)]
        if missing:
            raise ValueError(f"NODES entry missing fields {missing}: {item}")
    return data


async def seed_nodes(session: AsyncSession, raw_nodes: str) -> list[Node]:
    """Upsert узлов из JSON-строки. Возвращает актуальный список узлов."""
    try:
        entries = _parse_nodes(raw_nodes)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("node_seed.parse_failed", error=str(exc))
        raise

    existing = {
        node.agent_url: node
        for node in (await session.execute(select(Node))).scalars().all()
    }

    seeded: list[Node] = []
    for entry in entries:
        node = existing.get(entry["agent_url"])
        if node is None:
            node = Node(
                name=entry["name"],
                country=entry["country"],
                agent_url=entry["agent_url"],
                agent_secret=entry["agent_secret"],
                is_active=True,
            )
            session.add(node)
            logger.info("node_seed.insert", name=entry["name"], url=entry["agent_url"])
        else:
            node.name = entry["name"]
            node.country = entry["country"]
            node.agent_secret = entry["agent_secret"]
            node.is_active = True
            logger.info("node_seed.update", name=entry["name"], url=entry["agent_url"])
        seeded.append(node)

    await session.commit()
    logger.info("node_seed.done", count=len(seeded))
    return seeded
