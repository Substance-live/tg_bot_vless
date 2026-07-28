"""Безопасность: генерация ключей активации (JWT/bcrypt — пост-MVP)."""

from __future__ import annotations

import secrets

# Без неоднозначных символов (0/O, 1/I/l).
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_activation_key(length: int = 10) -> str:
    """Короткий безопасный одноразовый ключ активации."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))
