"""Создание профилей с одноразовым ключом и активация ключа."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import generate_activation_key
from db.models import ActivationKey, Subscription, SubscriptionStatus, User


class ActivationError(Exception):
    """Ошибка активации ключа (не найден / использован / telegram уже привязан)."""


async def create_user_with_key(
    session: AsyncSession, admin: User, name: str | None = None
) -> tuple[User, ActivationKey]:
    """Создаёт профиль (telegram_id=NULL) и одноразовый ключ к нему."""
    profile = User(telegram_id=None, name=name, is_active=True)
    session.add(profile)
    await session.flush()  # получить profile.id

    # Гарантируем уникальность key_value.
    for _ in range(5):
        key_value = generate_activation_key()
        exists = await session.scalar(
            select(ActivationKey.id).where(ActivationKey.key_value == key_value)
        )
        if not exists:
            break
    else:
        raise RuntimeError("failed to generate unique activation key")

    key = ActivationKey(
        key_value=key_value,
        created_by_admin=admin.id,
        is_used=False,
    )
    session.add(key)
    # Привяжем ключ к профилю сразу (secret_key_id), чтобы /users показывал связь.
    await session.flush()
    profile.secret_key_id = key.id
    await session.commit()
    await session.refresh(profile)
    await session.refresh(key)
    return profile, key


async def activate_key(
    session: AsyncSession,
    key_value: str,
    telegram_id: int,
    username: str | None,
) -> tuple[User, Subscription]:
    """Активирует ключ: привязывает telegram к профилю и создаёт подписку.

    Атомарно в рамках текущей (autobegin) транзакции сессии: при ошибке
    валидации изменения не вносятся; при успехе всё коммитится разом.
    Возвращает (профиль, подписка).
    """
    key = await session.scalar(
        select(ActivationKey)
        .where(ActivationKey.key_value == key_value)
        .with_for_update()
    )
    if key is None:
        raise ActivationError("key_not_found")
    if key.is_used:
        raise ActivationError("key_used")

    # Профиль, к которому относится ключ (создатель — админ; профиль — по secret_key_id).
    profile = await session.scalar(
        select(User).where(User.secret_key_id == key.id).with_for_update()
    )
    if profile is None:
        raise ActivationError("profile_not_found")

    # telegram_id уже привязан к другому профилю?
    other = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if other is not None and other.id != profile.id:
        raise ActivationError("telegram_already_bound")

    now = datetime.now(timezone.utc)
    profile.telegram_id = telegram_id
    profile.telegram_username = username
    profile.is_active = True

    key.is_used = True
    key.activated_by = profile.id
    key.activated_at = now

    subscription = Subscription(
        user_id=profile.id,
        status=SubscriptionStatus.active,
        expires_at=None,
    )
    session.add(subscription)

    await session.commit()
    await session.refresh(profile)
    await session.refresh(subscription)
    return profile, subscription
