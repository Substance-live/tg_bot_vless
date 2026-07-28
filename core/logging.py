"""Настройка structlog: JSON в проде, читаемый вывод в dev."""

from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Конфигурирует stdlib logging + structlog.

    fmt="json"    → структурированные JSON-логи (прод).
    fmt="console" → цветной человекочитаемый вывод (dev).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        timestamper,
    ]

    if fmt == "json":
        renderer: structlog.typing.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Привести stdlib-логгеры (uvicorn, sqlalchemy, aiogram) к тому же уровню.
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).setLevel(max(log_level, logging.INFO))


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
