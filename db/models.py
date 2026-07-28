"""SQLAlchemy 2.x ORM-модели оркестратора.

Полная схема «на вырост» (02 §4). В MVP наполняются users, activation_keys,
nodes, subscriptions, node_configs, audit_logs; payments создаётся, но не
используется.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ───────────────────────────────────────────────────────────────────


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    expired = "expired"
    suspended = "suspended"
    pending = "pending"
    trial = "trial"


class NodeConfigProtocol(str, enum.Enum):
    vless = "vless"
    mtproto = "mtproto"


class NodeConfigStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"
    pending = "pending"
    error = "error"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"


class NodeHealthStatus(str, enum.Enum):
    ok = "ok"
    degraded = "degraded"
    offline = "offline"
    unknown = "unknown"


# Нативные Postgres-enum'ы с явными именами (Alembic создаёт CREATE TYPE один раз).
_subscription_status = SAEnum(SubscriptionStatus, name="subscription_status")
_node_config_protocol = SAEnum(NodeConfigProtocol, name="node_config_protocol")
_node_config_status = SAEnum(NodeConfigStatus, name="node_config_status")
_payment_status = SAEnum(PaymentStatus, name="payment_status")
_node_health_status = SAEnum(NodeHealthStatus, name="node_health_status")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


# ── Tables ──────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    telegram_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, index=True, nullable=True
    )
    telegram_username: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    secret_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activation_keys.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="user", foreign_keys="Subscription.user_id"
    )


class ActivationKey(Base):
    __tablename__ = "activation_keys"

    id: Mapped[uuid.UUID] = _uuid_pk()
    key_value: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Две FK на users — держим колонками без relationships (проще, без ambiguity).
    created_by_admin: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    activated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    key_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        _subscription_status, default=SubscriptionStatus.active, nullable=False
    )
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="subscriptions", foreign_keys=[user_id])
    node_configs: Mapped[list[NodeConfig]] = relationship(back_populates="subscription")


class NodeConfig(Base):
    __tablename__ = "node_configs"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "node_id", "protocol", name="uq_node_config_sub_node_proto"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id"), index=True, nullable=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nodes.id"), nullable=False
    )
    protocol: Mapped[NodeConfigProtocol] = mapped_column(_node_config_protocol, nullable=False)
    external_config_id: Mapped[str | None] = mapped_column(String, nullable=True)
    config_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[NodeConfigStatus] = mapped_column(
        _node_config_status, default=NodeConfigStatus.pending, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    subscription: Mapped[Subscription] = relationship(back_populates="node_configs")
    node: Mapped[Node] = relationship()


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)
    agent_url: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    agent_secret: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_health_check: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    health_status: Mapped[NodeHealthStatus] = mapped_column(
        _node_health_status, default=NodeHealthStatus.unknown, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=True
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[PaymentStatus] = mapped_column(
        _payment_status, default=PaymentStatus.pending, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
