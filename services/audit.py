"""Запись действий в audit_logs."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog


async def log_action(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    meta: dict | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        meta=meta,
    )
    session.add(entry)
    if commit:
        await session.commit()
    return entry
