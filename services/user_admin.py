"""Админ-операции над учётками: состояния, удаление, чистка pending, отвязка.

Удаление — чистый Core (без ORM-cascade, т.к. async-lazy-load сломается, а
ON DELETE CASCADE в схеме нет). Порядок шагов учитывает циклическую FK
users.secret_key_id ↔ activation_keys.activated_by.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.logging import get_logger
from db.models import ActivationKey, NodeConfig, Payment, Subscription, User
from services.node_client import NodeClient, NodeClientError
from services.provisioning import external_id_for, get_active_nodes

logger = get_logger("user_admin")


def link_ttl() -> timedelta:
    return timedelta(minutes=settings.LINK_TTL_MINUTES)


class ProfileState(enum.Enum):
    ADMIN = "admin"
    ACTIVE = "active"
    DISABLED = "disabled"
    PENDING = "pending"      # отвязан, ключ жив — ожидает активации
    DETACHED = "detached"    # отвязан, ключ использован/истёк — «отвязанная» учётка


def profile_state(
    user: User, key: ActivationKey | None, now: datetime, ttl: timedelta
) -> tuple[ProfileState, int | None]:
    """Состояние профиля и (для PENDING) остаток секунд жизни ссылки."""
    if user.is_admin:
        return ProfileState.ADMIN, None
    if user.telegram_id is not None:
        return (ProfileState.ACTIVE if user.is_active else ProfileState.DISABLED), None
    if key is not None and not key.is_used:
        expiry = key.key_expires_at or (key.created_at + ttl)
        remaining = (expiry - now).total_seconds()
        if remaining > 0:
            return ProfileState.PENDING, int(remaining)
    return ProfileState.DETACHED, None


async def list_profiles_with_keys(
    session: AsyncSession,
) -> list[tuple[User, ActivationKey | None]]:
    """Профили + их ключ (по secret_key_id), новые сверху."""
    rows = await session.execute(
        select(User, ActivationKey)
        .outerjoin(ActivationKey, User.secret_key_id == ActivationKey.id)
        .order_by(User.created_at.desc())
    )
    return [(row[0], row[1]) for row in rows.all()]


async def _deprovision_on_nodes(session: AsyncSession, user: User) -> None:
    """Best-effort удаление VLESS-клиента пользователя на всех активных узлах."""
    ext_id = external_id_for(user)
    for node in await get_active_nodes(session):
        try:
            async with NodeClient(node) as client:
                await client.delete_vless_user(ext_id)
        except NodeClientError as exc:
            logger.warning("delete.node_failed", node=node.name, error=str(exc))


async def delete_user(session: AsyncSession, user: User) -> None:
    """Полное удаление учётки (FK-safe). Админа удалять нельзя."""
    if user.is_admin:
        raise ValueError("cannot delete admin")

    uid = user.id
    key_id = user.secret_key_id

    await _deprovision_on_nodes(session, user)

    # 1. Разорвать ребро user→key.
    await session.execute(update(User).where(User.id == uid).values(secret_key_id=None))
    # 2. node_configs подписок пользователя.
    await session.execute(
        delete(NodeConfig).where(
            NodeConfig.subscription_id.in_(
                select(Subscription.id).where(Subscription.user_id == uid)
            )
        )
    )
    # 3. payments (FK на users и subscriptions) → до subscriptions.
    await session.execute(delete(Payment).where(Payment.user_id == uid))
    # 4. subscriptions.
    await session.execute(delete(Subscription).where(Subscription.user_id == uid))
    # 5. Ключ профиля.
    if key_id is not None:
        await session.execute(delete(ActivationKey).where(ActivationKey.id == key_id))
    # Защитно — любые ключи, активированные этим пользователем.
    await session.execute(delete(ActivationKey).where(ActivationKey.activated_by == uid))
    # 6. Сам пользователь.
    await session.execute(delete(User).where(User.id == uid))
    await session.commit()
    logger.info("user.deleted", user_id=str(uid))


async def unbind_telegram(session: AsyncSession, user: User) -> None:
    """Мягкое удаление: снять привязку TG (подписка/конфиги/ключ остаются)."""
    if user.is_admin:
        raise ValueError("cannot unbind admin")
    user.telegram_id = None
    user.telegram_username = None
    await session.commit()
    logger.info("user.unbound", user_id=str(user.id))


async def cleanup_expired_pending(session: AsyncSession, now: datetime | None = None) -> int:
    """Удаляет отвязанные не-админ профили с неиспользованным истёкшим ключом.

    Чистит и легаси (key_expires_at IS NULL) через created_at + TTL. У pending нет
    подписки/конфигов (никогда не активировались) — узлы не трогаем.
    """
    now = now or datetime.now(timezone.utc)
    ttl = link_ttl()
    expiry = func.coalesce(
        ActivationKey.key_expires_at, ActivationKey.created_at + ttl
    )
    victims = (
        await session.execute(
            select(User.id, ActivationKey.id)
            .join(ActivationKey, User.secret_key_id == ActivationKey.id)
            .where(
                User.telegram_id.is_(None),
                User.is_admin.is_(False),
                ActivationKey.is_used.is_(False),
                expiry < now,
            )
        )
    ).all()
    if not victims:
        return 0

    uids = [row[0] for row in victims]
    kids = [row[1] for row in victims]

    await session.execute(update(User).where(User.id.in_(uids)).values(secret_key_id=None))
    await session.execute(
        delete(NodeConfig).where(
            NodeConfig.subscription_id.in_(
                select(Subscription.id).where(Subscription.user_id.in_(uids))
            )
        )
    )
    await session.execute(delete(Payment).where(Payment.user_id.in_(uids)))
    await session.execute(delete(Subscription).where(Subscription.user_id.in_(uids)))
    await session.execute(delete(ActivationKey).where(ActivationKey.id.in_(kids)))
    await session.execute(delete(User).where(User.id.in_(uids)))
    await session.commit()
    logger.info("pending.cleanup", count=len(uids))
    return len(uids)
