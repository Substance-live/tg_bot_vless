"""Inline-клавиатуры и callback-data фабрики."""

from __future__ import annotations

import uuid

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core import messages as msg
from db.models import User
from services.user_admin import ProfileState

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
    action: str  # open | on | off | link | del | del_yes | unbind
    user_id: uuid.UUID


class UsersPageCB(CallbackData, prefix="up"):
    page: int


class TempLinkCB(CallbackData, prefix="tl"):
    days: int


class ConfigCB(CallbackData, prefix="cfg"):
    action: str  # node | link | qr
    node_id: uuid.UUID


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


def configs_servers_kb(
    nodes: list, back_cb: str
) -> InlineKeyboardMarkup:
    """Список серверов: кнопка на узел + «Назад» в меню."""
    kb = InlineKeyboardBuilder()
    for node in nodes:
        kb.button(
            text=node.name[:64],
            callback_data=ConfigCB(action="node", node_id=node.id),
        )
    kb.button(text=msg.BTN_BACK, callback_data=back_cb)
    kb.adjust(1)
    return kb.as_markup()


def config_node_kb(node_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Выбор формата конфига для конкретного узла."""
    kb = InlineKeyboardBuilder()
    kb.button(text=msg.BTN_LINK, callback_data=ConfigCB(action="link", node_id=node_id))
    kb.button(text=msg.BTN_QR, callback_data=ConfigCB(action="qr", node_id=node_id))
    kb.button(text=msg.BTN_BACK, callback_data=NAV_CONFIGS)
    kb.adjust(2, 1)
    return kb.as_markup()


def back_kb(target: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=msg.BTN_BACK, callback_data=target)
    return kb.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=msg.BTN_CANCEL, callback_data=KEY_CANCEL)
    return kb.as_markup()


def users_list_kb(
    rows: list[tuple[uuid.UUID, str]], page: int
) -> InlineKeyboardMarkup:
    """Список профилей с пагинацией. rows — (user_id, готовая метка), полный список."""
    total = len(rows)
    pages = max(1, (total + USERS_PAGE_SIZE - 1) // USERS_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * USERS_PAGE_SIZE
    chunk = rows[start : start + USERS_PAGE_SIZE]

    kb = InlineKeyboardBuilder()
    for user_id, label in chunk:
        kb.button(text=label[:64], callback_data=UserCardCB(action="open", user_id=user_id))
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


def user_card_kb(target: User, state: ProfileState) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    uid = target.id
    if state == ProfileState.ADMIN:
        kb.button(text=msg.BTN_BACK, callback_data=NAV_ADMIN_USERS)
        return kb.as_markup()

    if state in (ProfileState.ACTIVE, ProfileState.DISABLED):
        if state == ProfileState.ACTIVE:
            kb.button(text=msg.BTN_DISABLE, callback_data=UserCardCB(action="off", user_id=uid))
        else:
            kb.button(text=msg.BTN_ENABLE, callback_data=UserCardCB(action="on", user_id=uid))
        kb.button(text=msg.BTN_UNBIND, callback_data=UserCardCB(action="unbind", user_id=uid))
    else:  # PENDING / DETACHED — отвязанные: выдать/показать ссылку
        kb.button(text=msg.BTN_ACT_LINK, callback_data=UserCardCB(action="link", user_id=uid))

    kb.button(text=msg.BTN_DELETE, callback_data=UserCardCB(action="del", user_id=uid))
    kb.button(text=msg.BTN_BACK, callback_data=NAV_ADMIN_USERS)
    kb.adjust(1)
    return kb.as_markup()


def user_delete_confirm_kb(user_id: uuid.UUID) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=msg.BTN_DELETE_CONFIRM, callback_data=UserCardCB(action="del_yes", user_id=user_id))
    kb.button(text=msg.BTN_CANCEL, callback_data=UserCardCB(action="open", user_id=user_id))
    kb.adjust(1)
    return kb.as_markup()
