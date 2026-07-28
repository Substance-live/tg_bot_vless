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
NAV_ADMIN_TEMPLINK = "nav:admin_templink"
KEY_ENTER = "key:enter"
KEY_CANCEL = "key:cancel"

USERS_PAGE_SIZE = 8
TEMPLINK_DURATIONS = (1, 3, 7, 30)  # дни


class UserCardCB(CallbackData, prefix="uc"):
    action: str  # open | on | off | link
    user_id: uuid.UUID


class UsersPageCB(CallbackData, prefix="up"):
    page: int


class TempLinkCB(CallbackData, prefix="tl"):
    days: int


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
    kb.button(text=msg.BTN_TEMPLINK, callback_data=NAV_ADMIN_TEMPLINK)
    kb.button(text=msg.BTN_CONFIGS, callback_data=NAV_CONFIGS)
    kb.button(text=msg.BTN_STATUS, callback_data=NAV_STATUS)
    kb.adjust(1, 1, 1, 2)
    return kb.as_markup()


def templink_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for days in TEMPLINK_DURATIONS:
        kb.button(text=msg.templink_btn(days), callback_data=TempLinkCB(days=days))
    kb.button(text=msg.BTN_BACK, callback_data=NAV_ADMIN)
    kb.adjust(2, 2, 1)
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
    base = ("🟢" if u.is_active else "🔴") + ("🔗" if u.telegram_id else "◻️")
    return base + ("🛡" if u.is_admin else "")


def _user_label(u: User) -> str:
    name = u.name or "—"
    nick = f" @{u.telegram_username}" if u.telegram_username else ""
    return f"{_user_flag(u)} {name}{nick}"


def users_list_kb(profiles: list[User], page: int) -> InlineKeyboardMarkup:
    """Список профилей с пагинацией. profiles — полный список."""
    total = len(profiles)
    pages = max(1, (total + USERS_PAGE_SIZE - 1) // USERS_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * USERS_PAGE_SIZE
    chunk = profiles[start : start + USERS_PAGE_SIZE]

    kb = InlineKeyboardBuilder()
    for u in chunk:
        kb.button(
            text=_user_label(u)[:64], callback_data=UserCardCB(action="open", user_id=u.id)
        )
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
    # Админа отключать нельзя — тумблер не показываем.
    if not target.is_admin:
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
