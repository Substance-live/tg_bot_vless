"""Утилиты бота: генерация QR-кода."""

from __future__ import annotations

import io

import segno
from aiogram.types import BufferedInputFile


def render_qr(data: str, *, scale: int = 6, border: int = 2) -> BufferedInputFile:
    """PNG QR-кода для ссылки → BufferedInputFile для отправки фото."""
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="png", scale=scale, border=border)
    buf.seek(0)
    return BufferedInputFile(buf.read(), filename="qr.png")
