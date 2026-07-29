"""Общие рендер-хелперы бота: меню, конфиги, статус, доступ.

Вынесено из командных хендлеров, чтобы переиспользовать в callback-хендлерах.
`target` — Message (callback.message или обычный message); флаг edit выбирает
редактирование существующего сообщения или отправку нового.
"""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, LinkPreviewOptions, Message, User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.menus import (
    NAV_ADMIN,
    NAV_USER,
    admin_menu_kb,
    configs_servers_kb,
    user_menu_kb,
)
from bot.utils import apply_vless_remark, render_qr
from core import messages as msg
from core.config import settings
from db.models import Node, User
from services.node_client import NodeClient, NodeClientError
from services.provisioning import build_remark, external_id_for, get_active_nodes
from services.subscription import get_active_subscription


def is_admin_ctx(user: User | None, tg_user: TgUser | None = None) -> bool:
    """Админ ли контекст (мирроринг AdminFilter): по флагу или по ADMIN_TELEGRAM_IDS."""
    if user is not None and user.is_admin:
        return True
    if tg_user is not None and tg_user.id in settings.ADMIN_TELEGRAM_IDS:
        return True
    return False


async def ensure_admin_user(session: AsyncSession, tg_user: TgUser) -> User:
    """Возвращает user-строку админа, создавая её при первом обращении."""
    user = await session.scalar(select(User).where(User.telegram_id == tg_user.id))
    if user is None:
        user = User(
            telegram_id=tg_user.id,
            telegram_username=tg_user.username,
            name=tg_user.full_name,
            is_active=True,
            is_admin=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif not user.is_admin:
        user.is_admin = True
        await session.commit()
    return user


async def safe_edit(
    target: Message,
    text: str,
    kb: InlineKeyboardMarkup,
    *,
    disable_preview: bool = False,
) -> None:
    """edit_text, глотая 'message is not modified'."""
    opts = LinkPreviewOptions(is_disabled=True) if disable_preview else None
    try:
        await target.edit_text(text, reply_markup=kb, link_preview_options=opts)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


async def safe_delete(target: Message) -> None:
    """Удаляет сообщение, игнорируя ошибку (старое/уже удалено)."""
    try:
        await target.delete()
    except TelegramBadRequest:
        pass


async def show_user_menu(
    target: Message, session: AsyncSession, user: User | None, *, edit: bool
) -> None:
    activated = False
    if user is not None and user.is_active and user.telegram_id is not None:
        activated = await get_active_subscription(session, user) is not None
    text = msg.USER_MENU if activated else msg.USER_MENU_NEED_KEY
    kb = user_menu_kb(activated)
    if edit:
        await safe_edit(target, text, kb)
    else:
        await target.answer(text, reply_markup=kb)


async def show_admin_menu(target: Message, *, edit: bool) -> None:
    if edit:
        await safe_edit(target, msg.ADMIN_MENU, admin_menu_kb())
    else:
        await target.answer(msg.ADMIN_MENU, reply_markup=admin_menu_kb())


async def require_access(target: Message, session: AsyncSession, user: User | None) -> bool:
    """Проверка доступа: привязан, активен, есть подписка. Иначе шлёт ответ."""
    if user is None:
        await target.answer(msg.NO_SUBSCRIPTION)
        return False
    if not user.is_active:
        await target.answer(msg.ACCOUNT_DISABLED)
        return False
    if await get_active_subscription(session, user) is None:
        await target.answer(msg.NO_SUBSCRIPTION)
        return False
    return True


async def send_user_configs(target: Message, session: AsyncSession, user: User) -> None:
    """Читает конфиги живьём со всех активных узлов и отправляет пользователю."""
    nodes = await get_active_nodes(session)
    if not nodes:
        await target.answer(msg.NO_NODES)
        return

    external_id = external_id_for(user)
    for node in nodes:
        try:
            async with NodeClient(node) as client:
                vless = await client.get_vless_user(external_id)
                try:
                    mtproto = await client.get_mtproto_info()
                except NodeClientError:
                    mtproto = None
        except NodeClientError:
            await target.answer(
                msg.NODE_UNAVAILABLE.format(name=node.name)
            )
            continue

        if vless is None:
            await target.answer(
                msg.NODE_UNAVAILABLE.format(name=node.name)
            )
            continue

        link = apply_vless_remark(vless["config_link"], build_remark(node, user))
        block = msg.config_node_block(node.name, link, vless.get("is_enabled", True))
        if mtproto and mtproto.get("tg_link"):
            block += "\n\n" + msg.mtproto_block(mtproto["tg_link"])
        await target.answer(
            block, link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
        await target.answer_photo(render_qr(link), caption=f"QR · {node.name}")


async def get_node(session: AsyncSession, node_id) -> Node | None:
    """Активный узел по id (иначе None)."""
    return await session.scalar(
        select(Node).where(Node.id == node_id, Node.is_active.is_(True))
    )


async def fetch_node_vless(
    node: Node, user: User
) -> tuple[str | None, bool, dict | None]:
    """Читает конфиг пользователя с одного узла живьём.

    Возвращает (vless_link | None, enabled, mtproto | None). Узел недоступен или
    клиента нет → (None, False, ...). Ссылка уже с применённым remark.
    """
    external_id = external_id_for(user)
    try:
        async with NodeClient(node) as client:
            vless = await client.get_vless_user(external_id)
            try:
                mtproto = await client.get_mtproto_info()
            except NodeClientError:
                mtproto = None
    except NodeClientError:
        return None, False, None
    if vless is None:
        return None, False, mtproto
    link = apply_vless_remark(vless["config_link"], build_remark(node, user))
    return link, bool(vless.get("is_enabled", True)), mtproto


async def show_configs_servers(
    target: Message, session: AsyncSession, user: User, *, edit: bool
) -> None:
    """Экран выбора сервера для получения конфига."""
    nodes = await get_active_nodes(session)
    if not nodes:
        await target.answer(msg.NO_NODES)
        return
    back_cb = NAV_ADMIN if is_admin_ctx(user) else NAV_USER
    kb = configs_servers_kb(nodes, back_cb)
    if edit:
        await safe_edit(target, msg.CONFIGS_CHOOSE_SERVER, kb)
    else:
        await target.answer(msg.CONFIGS_CHOOSE_SERVER, reply_markup=kb)


async def status_view(session: AsyncSession, user: User | None) -> str:
    """Текст статуса с живым чтением состояния узлов."""
    if user is None:
        return msg.status_text(bound=False, active=False, lines=[])

    subscription = await get_active_subscription(session, user)
    lines: list[str] = []
    if subscription is not None and user.is_active:
        external_id = external_id_for(user)
        for node in await get_active_nodes(session):
            try:
                async with NodeClient(node) as client:
                    vless = await client.get_vless_user(external_id)
                ok = vless is not None
                enabled = vless.get("is_enabled") if vless else None
            except NodeClientError:
                ok, enabled = False, None
            lines.append(msg.status_node_line(node.name, ok, enabled))

    return msg.status_text(
        bound=user.telegram_id is not None,
        active=user.is_active and subscription is not None,
        lines=lines,
    )
