"""Конфигурация приложения через pydantic-settings (читается из .env)."""

from __future__ import annotations

import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Telegram ───────────────────────────────────────────────
    # Пусто → бот не запускается, работает только API.
    BOT_TOKEN: str = ""

    # ── API (FastAPI / Swagger) ────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # ── База данных / Redis (используются с Этапа 1) ───────────
    DATABASE_URL: str = "postgresql+asyncpg://vpn:vpn@localhost:5432/vpn_orchestrator"
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Безопасность ───────────────────────────────────────────
    JWT_SECRET: str = "change-me-in-production"

    # ── Администраторы ─────────────────────────────────────────
    # Список Telegram ID начальных админов. Принимает JSON ([1,2]) или CSV (1,2).
    ADMIN_TELEGRAM_IDS: list[int] = []

    # ── Взаимодействие с Node Agent ────────────────────────────
    NODE_AGENT_TIMEOUT_SECONDS: int = 10
    NODE_AGENT_RETRY_COUNT: int = 3

    # ── Ссылки-приглашения ─────────────────────────────────────
    # Сколько живёт неактивированная ссылка (минуты).
    LINK_TTL_MINUTES: int = 5

    # ── VLESS ──────────────────────────────────────────────────
    # Общий бренд-префикс имени конфига: "<prefix>_<метка_узла>_<ник>".
    # Пусто → префикс не добавляется. Метка узла берётся из NODES.name.
    VLESS_REMARK_PREFIX: str = "EdlibiaVPN"

    # ── Сидинг узлов (JSON-строка, парсится на Этапе 1) ────────
    NODES: str = "[]"

    # ── Логирование ────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" | "console"

    @field_validator("ADMIN_TELEGRAM_IDS", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: object) -> object:
        """Допускает пустую строку, CSV ("1,2"), JSON ("[1,2]") или одиночное число.

        pydantic-settings для list-поля сам JSON-декодирует env, поэтому голое
        "123" приходит сюда уже как int — оборачиваем в список.
        """
        if value is None or value == "":
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                return json.loads(text)
            return [int(part) for part in text.split(",") if part.strip()]
        return value


settings = Settings()
