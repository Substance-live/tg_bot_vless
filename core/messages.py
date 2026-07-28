"""Шаблоны сообщений бота (HTML parse mode). Форматирование через str.format."""

from __future__ import annotations

# ── Общие / пользователь ────────────────────────────────────────────────────

WELCOME_BOUND = (
    "👋 Вы авторизованы.\n\n"
    "• /configs — ваши конфигурации (VLESS + MTProto)\n"
    "• /status — статус доступа"
)

WELCOME_NEED_KEY = (
    "👋 Добро пожаловать!\n\n"
    "Чтобы получить доступ, введите ключ активации:\n"
    "<code>/activate ВАШ_КЛЮЧ</code>"
)

NEED_KEY_ARG = "Укажите ключ: <code>/activate ВАШ_КЛЮЧ</code>"

KEY_INVALID = {
    "key_not_found": "❌ Ключ не найден. Проверьте правильность ввода.",
    "key_used": "❌ Этот ключ уже использован.",
    "profile_not_found": "❌ Профиль для этого ключа не найден. Обратитесь к администратору.",
    "telegram_already_bound": "❌ Ваш Telegram уже привязан к другому профилю.",
}
KEY_INVALID_DEFAULT = "❌ Не удалось активировать ключ."

ACTIVATED_HEADER = "✅ Ключ активирован! Ваши конфигурации:\n"

NO_SUBSCRIPTION = "У вас нет активной подписки. Введите ключ: <code>/activate ВАШ_КЛЮЧ</code>"

ACCOUNT_DISABLED = "⛔ Ваш доступ приостановлен администратором."

NO_NODES = "⚠️ Пока нет доступных серверов. Попробуйте позже."

NODE_UNAVAILABLE = "🔧 <b>{name}</b> ({country}) — временно недоступен."


def config_node_block(name: str, country: str, vless_link: str, enabled: bool) -> str:
    state = "🟢 активен" if enabled else "🔴 отключён"
    return (
        f"🌍 <b>{name}</b> ({country}) — {state}\n"
        f"<b>VLESS:</b>\n<code>{vless_link}</code>"
    )


def mtproto_block(tg_link: str) -> str:
    return (
        "📱 <b>MTProto-прокси для Telegram</b>\n"
        f'<a href="{tg_link}">Подключиться одним нажатием</a>\n'
        f"<code>{tg_link}</code>"
    )


# ── Статус ──────────────────────────────────────────────────────────────────

def status_text(bound: bool, active: bool, lines: list[str]) -> str:
    head = "📊 <b>Статус доступа</b>\n"
    head += f"Аккаунт: {'привязан' if bound else 'не привязан'}\n"
    head += f"Доступ: {'🟢 активен' if active else '🔴 приостановлен'}\n"
    if lines:
        head += "\n<b>Серверы:</b>\n" + "\n".join(lines)
    return head


def status_node_line(name: str, country: str, ok: bool, enabled: bool | None) -> str:
    if not ok:
        return f"• {name} ({country}) — 🔧 недоступен"
    mark = "🟢" if enabled else "🔴"
    return f"• {name} ({country}) — {mark} {'вкл' if enabled else 'выкл'}"


# ── Админ ───────────────────────────────────────────────────────────────────

def admin_key_created(name: str | None, key_value: str) -> str:
    who = f" для «{name}»" if name else ""
    return (
        f"🔑 Профиль создан{who}. Одноразовый ключ:\n\n"
        f"<code>{key_value}</code>\n\n"
        "Передайте его пользователю. Активация: "
        f"<code>/activate {key_value}</code>"
    )


def user_list_row(
    name: str | None, telegram_id: int | None, is_active: bool, bound: bool
) -> str:
    label = name or "—"
    tg = str(telegram_id) if telegram_id else "не привязан"
    flags = ("🟢" if is_active else "🔴") + ("🔗" if bound else "◻️")
    return f"{flags} <b>{label}</b> · tg: {tg}"


USER_LIST_EMPTY = "Профилей пока нет. Создайте: <code>/newuser Имя</code>"
USER_LIST_HEADER = "👥 <b>Пользователи</b> (🟢/🔴 активен · 🔗 привязан):\n\n"

ADMIN_NEED_REF = "Укажите пользователя: <code>/{cmd} tg_id | имя | uuid</code>"
ADMIN_USER_NOT_FOUND = "❌ Пользователь не найден: <code>{ref}</code>"


def admin_toggle_result(name: str | None, enabled: bool, per_node: list[str]) -> str:
    action = "включён" if enabled else "отключён"
    head = f"{'🟢' if enabled else '🔴'} Пользователь «{name or '—'}» {action}.\n"
    if per_node:
        head += "\n" + "\n".join(per_node)
    return head


def admin_node_result(name: str, ok: bool) -> str:
    return f"• {name} — {'✅' if ok else '⚠️ ошибка'}"
