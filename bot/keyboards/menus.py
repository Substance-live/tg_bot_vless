"""Inline-клавиатуры и callback-data фабрики."""

from __future__ import annotations

import uuid

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core import messages as msg
from db.models import User

# ── Навигационные callback-константы ─────────────────────────────────────────
NAV_USER = "nav:user"
NAV_CONFIGS = "nav:configs"
NAV_STATUS = "nav:status"
NAV_ADMIN = "nav:admin"
NAV_ADMIN_USERS = "nav:admin_users"
NAV_ADMIN_NEWUSER = "nav:admin_newuser"
KEY_ENTER = "key:enter"
KEY_CANCEL = "key:cancel"

USERS_PAGE_SIZE = 8


class UserCardCB(CallbackData, prefix="uc"):
    action: str  # open | on | off | link
    user_id: uuid.UUID


class UsersPageCB(CallbackData, prefix="up"):
    page: int


# ── Билдеры ──────────────────────────────────────────────────────────────────

def user_menu_kb(activated: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if activated:
        kb.button(text=msg.BTN_CONFIGS, callback_data=NAV_CONFIGS)
        kb.button(text=msg.BTN_STATUS, callback_data=NAV_STATUS)
        kb.adjust(2)
    else:
        kb.button(text=msg.BTN_ENTER_KEY, callback_data=KEY_ENTER)
        kb.adjust(1)
    return kb.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=msg.BTN_ADMIN_USERS, callback_data=NAV_ADMIN_USERS)
    kb.button(text=msg.BTN_NEW_USER, callback_data=NAV_ADMIN_NEWUSER)
    kb.button(text=msg.BTN_CONFIGS, callback_data=NAV_CONFIGS)
    kb.button(text=msg.BTN_STATUS, callback_data=NAV_STATUS)
    kb.adjust(1, 1, 2)
    return kb.as_markup()


def back_kb(target: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=msg.BTN_BACK, callback_data=target)
    return kb.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=msg.BTN_CANCEL, callback_data=KEY_CANCEL)
    return kb.as_markup()


def _user_flag(u: User) -> str:
    return ("🟢" if u.is_active else "🔴") + ("🔗" if u.telegram_id else "◻️")


def users_list_kb(profiles: list[User], page: int) -> InlineKeyboardMarkup:
    """Список профилей с пагинацией. profiles — полный список."""
    total = len(profiles)
    pages = max(1, (total + USERS_PAGE_SIZE - 1) // USERS_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * USERS_PAGE_SIZE
    chunk = profiles[start : start + USERS_PAGE_SIZE]

    kb = InlineKeyboardBuilder()
    for u in chunk:
        label = f"{_user_flag(u)} {u.name or (u.telegram_id or '—')}"
        kb.button(text=str(label), callback_data=UserCardCB(action="open", user_id=u.id))
    kb.adjust(1)

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text=msg.BTN_PREV, callback_data=UsersPageCB(page=page - 1).pack())
        )
    if page < pages - 1:
        nav_row.append(
            InlineKeyboardButton(text=msg.BTN_NEXT, callback_data=UsersPageCB(page=page + 1).pack())
        )
    if nav_row:
        kb.row(*nav_row)

    kb.row(InlineKeyboardButton(text=msg.BTN_BACK, callback_data=NAV_ADMIN))
    return kb.as_markup()


def user_card_kb(target: User) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if target.is_active:
        kb.button(
            text=msg.BTN_DISABLE, callback_data=UserCardCB(action="off", user_id=target.id)
        )
    else:
        kb.button(
            text=msg.BTN_ENABLE, callback_data=UserCardCB(action="on", user_id=target.id)
        )
    if not target.telegram_id:
        kb.button(
            text=msg.BTN_ACT_LINK, callback_data=UserCardCB(action="link", user_id=target.id)
        )
    kb.button(text=msg.BTN_BACK, callback_data=NAV_ADMIN_USERS)
    kb.adjust(1)
    return kb.as_markup()
