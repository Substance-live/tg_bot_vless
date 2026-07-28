"""Создание профилей с одноразовым ключом и активация ключа."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.security import generate_activation_key
from db.models import ActivationKey, Subscription, SubscriptionStatus, User
from services.subscription import get_active_subscription


class ActivationError(Exception):
    """Ошибка активации ключа (не найден / использован / истёк / telegram уже привязан)."""


def _link_ttl() -> timedelta:
    return timedelta(minutes=settings.LINK_TTL_MINUTES)


async def _unique_key_value(session: AsyncSession) -> str:
    for _ in range(5):
        value = generate_activation_key()
        exists = await session.scalar(
            select(ActivationKey.id).where(ActivationKey.key_value == value)
        )
        if not exists:
            return value
    raise RuntimeError("failed to generate unique activation key")


async def create_user_with_key(
    session: AsyncSession,
    admin: User,
    name: str | None = None,
    duration_days: int = 0,
) -> tuple[User, ActivationKey]:
    """Создаёт профиль (telegram_id=NULL) и одноразовый ключ к нему.

    duration_days=0 → бессрочный доступ; >0 → временный (доступ на N дней с момента
    активации, срок применяется к VLESS на узле).
    """
    profile = User(telegram_id=None, name=name, is_active=True)
    session.add(profile)
    await session.flush()  # получить profile.id

    key_value = await _unique_key_value(session)
    key = ActivationKey(
        key_value=key_value,
        created_by_admin=admin.id,
        duration_days=duration_days,
        is_used=False,
        key_expires_at=datetime.now(timezone.utc) + _link_ttl(),
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

    # Срок жизни ссылки (legacy без key_expires_at → created_at + TTL).
    now = datetime.now(timezone.utc)
    expiry = key.key_expires_at or (key.created_at + _link_ttl())
    if now > expiry:
        raise ActivationError("key_expired")

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

    profile.telegram_id = telegram_id
    profile.telegram_username = username
    profile.is_active = True

    key.is_used = True
    key.activated_by = profile.id
    key.activated_at = now

    # Переиспользуем активную подписку (кейс перепривязки TG), иначе создаём новую.
    duration = key.duration_days or 0
    subscription = await get_active_subscription(session, profile)
    if subscription is None:
        subscription = Subscription(
            user_id=profile.id,
            status=SubscriptionStatus.active,
            expires_at=now + timedelta(days=duration) if duration > 0 else None,
            is_trial=duration > 0,
        )
        session.add(subscription)

    await session.commit()
    await session.refresh(profile)
    await session.refresh(subscription)
    return profile, subscription


async def reissue_key(session: AsyncSession, user: User) -> str:
    """Перевыпускает ссылку-приглашение профиля: свежий key_value + TTL, is_used=False.

    Тот же row activation_keys (secret_key_id не меняется). Для отвязанных/просроченных
    профилей — чтобы админ мог выдать рабочую ссылку и (пере)привязать TG.
    """
    key = None
    if user.secret_key_id is not None:
        key = await session.scalar(
            select(ActivationKey)
            .where(ActivationKey.id == user.secret_key_id)
            .with_for_update()
        )
    if key is None:
        raise RuntimeError("profile has no activation key")

    key.key_value = await _unique_key_value(session)
    key.is_used = False
    key.activated_by = None
    key.activated_at = None
    key.key_expires_at = datetime.now(timezone.utc) + _link_ttl()
    await session.commit()
    await session.refresh(key)
    return key.key_value
