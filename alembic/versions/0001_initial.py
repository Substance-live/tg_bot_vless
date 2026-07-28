"""initial schema (full on-vyrost schema, 02 §4)

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


# Нативные Postgres-enum'ы. Создаём типы явно один раз, в колонках create_type=False.
subscription_status = postgresql.ENUM(
    "active", "expired", "suspended", "pending", "trial",
    name="subscription_status", create_type=False,
)
node_config_protocol = postgresql.ENUM(
    "vless", "mtproto", name="node_config_protocol", create_type=False,
)
node_config_status = postgresql.ENUM(
    "active", "suspended", "pending", "error",
    name="node_config_status", create_type=False,
)
payment_status = postgresql.ENUM(
    "pending", "completed", "failed", "refunded",
    name="payment_status", create_type=False,
)
node_health_status = postgresql.ENUM(
    "ok", "degraded", "offline", "unknown",
    name="node_health_status", create_type=False,
)

_ENUMS = (
    subscription_status,
    node_config_protocol,
    node_config_status,
    payment_status,
    node_health_status,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in _ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("country", sa.String(), nullable=False),
        sa.Column("agent_url", sa.String(), nullable=False),
        sa.Column("agent_secret", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_health_check", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_status", node_health_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("agent_url", name="uq_nodes_agent_url"),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_username", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        # FK на activation_keys добавляется ниже (циклическая зависимость).
        sa.Column("secret_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "activation_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key_value", sa.String(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("is_trial", sa.Boolean(), nullable=False),
        sa.Column("created_by_admin", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("activated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("key_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_used", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_admin"], ["users.id"], name="fk_keys_created_by_admin"),
        sa.ForeignKeyConstraint(["activated_by"], ["users.id"], name="fk_keys_activated_by"),
    )
    op.create_index("ix_activation_keys_key_value", "activation_keys", ["key_value"], unique=True)

    op.create_foreign_key(
        "fk_users_secret_key_id", "users", "activation_keys", ["secret_key_id"], ["id"]
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", subscription_status, nullable=False),
        sa.Column("is_trial", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_subscriptions_user_id"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])

    op.create_table(
        "node_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("protocol", node_config_protocol, nullable=False),
        sa.Column("external_config_id", sa.String(), nullable=True),
        sa.Column("config_data", postgresql.JSONB(), nullable=True),
        sa.Column("status", node_config_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], name="fk_node_configs_subscription_id"),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], name="fk_node_configs_node_id"),
        sa.UniqueConstraint("subscription_id", "node_id", "protocol", name="uq_node_config_sub_node_proto"),
    )
    op.create_index("ix_node_configs_subscription_id", "node_configs", ["subscription_id"])

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("provider_payment_id", sa.String(), nullable=True),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_payments_user_id"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], name="fk_payments_subscription_id"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("payments")
    op.drop_index("ix_node_configs_subscription_id", table_name="node_configs")
    op.drop_table("node_configs")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_constraint("fk_users_secret_key_id", "users", type_="foreignkey")
    op.drop_index("ix_activation_keys_key_value", table_name="activation_keys")
    op.drop_table("activation_keys")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
    op.drop_table("nodes")

    bind = op.get_bind()
    for enum in _ENUMS:
        enum.drop(bind, checkfirst=True)
