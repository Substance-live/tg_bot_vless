"""Утилиты бота: генерация QR-кода, имя VLESS-конфига."""

from __future__ import annotations

import io
from urllib.parse import quote

import segno
from aiogram.types import BufferedInputFile


def render_qr(data: str, *, scale: int = 6, border: int = 2) -> BufferedInputFile:
    """PNG QR-кода для ссылки → BufferedInputFile для отправки фото."""
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="png", scale=scale, border=border)
    buf.seek(0)
    return BufferedInputFile(buf.read(), filename="qr.png")


def apply_vless_remark(config_link: str, remark: str) -> str:
    """Заменяет #fragment у vless://-ссылки на заданное имя (URL-энкод)."""
    base = config_link.split("#", 1)[0]
    return f"{base}#{quote(remark, safe='')}"
