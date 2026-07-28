"""Вспомогательные выборки по пользователям и подпискам."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Subscription, SubscriptionStatus, User


async def get_active_subscription(
    session: AsyncSession, user: User
) -> Subscription | None:
    """Активная подписка пользователя (в MVP — одна)."""
    return await session.scalar(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.active,
        )
        .order_by(Subscription.created_at.desc())
    )


async def get_or_create_active_subscription(
    session: AsyncSession, user: User
) -> Subscription:
    """Активная подписка пользователя; создаёт при отсутствии (идемпотентно).

    Используется для дефолтного VPN-доступа админа при /start.
    """
    sub = await get_active_subscription(session, user)
    if sub is None:
        sub = Subscription(
            user_id=user.id,
            status=SubscriptionStatus.active,
            expires_at=None,
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
    return sub


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Пользователь по внутреннему UUID (для callback-карточек)."""
    return await session.scalar(select(User).where(User.id == user_id))


async def get_user_by_ref(session: AsyncSession, ref: str) -> User | None:
    """Резолвит пользователя по ссылке: telegram_id | внутренний UUID | имя."""
    ref = ref.strip()
    if not ref:
        return None

    # telegram_id (число)
    if ref.isdigit():
        user = await session.scalar(
            select(User).where(User.telegram_id == int(ref))
        )
        if user is not None:
            return user

    # внутренний UUID
    try:
        uid = uuid.UUID(ref)
    except ValueError:
        uid = None
    if uid is not None:
        user = await session.scalar(select(User).where(User.id == uid))
        if user is not None:
            return user

    # имя (точное совпадение)
    return await session.scalar(select(User).where(User.name == ref))


async def list_user_profiles(session: AsyncSession) -> list[User]:
    """Все профили для админского /users."""
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())
