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
    "key_expired": "❌ Ссылка истекла. Запросите новую у администратора.",
    "profile_not_found": "❌ Профиль для этого ключа не найден. Обратитесь к администратору.",
    "telegram_already_bound": "❌ Ваш Telegram уже привязан к другому профилю.",
}
KEY_INVALID_DEFAULT = "❌ Не удалось активировать ключ."

ACTIVATED_HEADER = "✅ Ключ активирован! Ваши конфигурации:\n"

NO_SUBSCRIPTION = "У вас нет активной подписки. Введите ключ: <code>/activate ВАШ_КЛЮЧ</code>"

ACCOUNT_DISABLED = "⛔ Ваш доступ приостановлен администратором."

NO_NODES = "⚠️ Пока нет доступных серверов. Попробуйте позже."

NODE_UNAVAILABLE = "🔧 <b>{name}</b> — временно недоступен."


def config_node_block(name: str, vless_link: str, enabled: bool) -> str:
    state = "🟢 активен" if enabled else "🔴 отключён"
    return (
        f"🌍 <b>{name}</b> — {state}\n"
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


def status_node_line(name: str, ok: bool, enabled: bool | None) -> str:
    if not ok:
        return f"• {name} — 🔧 недоступен"
    mark = "🟢" if enabled else "🔴"
    return f"• {name} — {mark} {'вкл' if enabled else 'выкл'}"


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


# ── Кнопочный интерфейс (inline) ─────────────────────────────────────────────

# Метки кнопок
BTN_CONFIGS = "🔐 Мои конфиги"
BTN_STATUS = "📊 Статус"
BTN_ENTER_KEY = "🔑 Ввести ключ"
BTN_ADMIN_USERS = "👥 Пользователи"
BTN_NEW_USER = "➕ Новый пользователь"
BTN_BACK = "◀ Назад"
BTN_CANCEL = "✖ Отмена"
BTN_ENABLE = "🟢 Включить"
BTN_DISABLE = "🔴 Отключить"
BTN_ACT_LINK = "🔗 Ссылка активации"
BTN_TEMPLINK = "⏳ Временная ссылка"
BTN_UNBIND = "🔓 Отвязать TG"
BTN_DELETE = "🗑 Удалить"
BTN_DELETE_CONFIRM = "🗑 Удалить навсегда"
BTN_PREV = "◀"
BTN_NEXT = "▶"

USER_DELETE_CONFIRM = (
    "🗑 <b>Удалить пользователя?</b>\n\n"
    "Будут удалены профиль, подписка и VLESS-клиент на узлах. Действие необратимо."
)

# Тексты меню
USER_MENU = "🏠 <b>Личный кабинет</b>\n\nВыберите действие:"
USER_MENU_NEED_KEY = (
    "🏠 <b>Личный кабинет</b>\n\n"
    "У вас пока нет доступа. Активируйте его:\n"
    "• по ссылке-приглашению от администратора (один тап), или\n"
    "• нажмите «🔑 Ввести ключ» и пришлите ключ."
)
ADMIN_MENU = "🛠 <b>Панель администратора</b>\n\nВыберите действие:"

ENTER_KEY_PROMPT = "Пришлите ключ активации одним сообщением:"
KEY_CANCELLED = "Отменено."
CONFIGS_SENDING = "Отправляю конфигурации…"

USERS_LIST_TITLE = "👥 <b>Пользователи</b>\n\n🟢/🔴 — активен · 🔗 — привязан"
USER_CARD_NOT_FOUND = "Пользователь не найден"


def user_card_text(
    name: str | None,
    username: str | None,
    telegram_id: int | None,
    is_active: bool,
    expires_at=None,
    is_admin: bool = False,
    note: str | None = None,
) -> str:
    bound = "🔗 привязан" if telegram_id else "◻️ не привязан"
    state = "🟢 активен" if is_active else "🔴 отключён"
    nick = f"@{username}" if username else "—"
    lines = [
        f"👤 <b>{name or '—'}</b>",
        f"Ник: {nick}",
        f"Telegram ID: {telegram_id or 'не привязан'}",
        f"Доступ: {state}",
        f"Статус: {bound}",
    ]
    if is_admin:
        lines.append("🛡 администратор")
    if expires_at is not None:
        lines.append(f"⏳ Доступ до: {expires_at:%d.%m.%Y}")
    if note:
        lines.append(note)
    return "\n".join(lines)


def profile_label(
    state_name: str,
    remaining: int | None,
    name: str | None,
    username: str | None,
    key_value: str | None,
) -> str:
    """Метка кнопки в списке пользователей (по состоянию профиля)."""
    nick = f"@{username}" if username else None
    primary = name or nick or "—"
    secondary = f" {nick}" if (name and nick) else ""
    if state_name == "PENDING":
        m, ss = divmod(max(0, int(remaining or 0)), 60)
        return f"🟡 {primary} · {m}:{ss:02d} · {key_value or ''}".strip()[:64]
    emoji = {"ADMIN": "🛡", "ACTIVE": "🟢", "DISABLED": "🔴", "DETACHED": "⚪"}.get(
        state_name, "•"
    )
    return f"{emoji} {primary}{secondary}"[:64]


def admin_key_created_link(name: str | None, key_value: str, link: str) -> str:
    who = f" «{name}»" if name else ""
    return (
        f"🔑 Профиль{who} создан.\n\n"
        f'<a href="{link}">👉 Ссылка-приглашение (один тап)</a>\n'
        f"<code>{link}</code>\n\n"
        f"Или ключ для ручного ввода: <code>{key_value}</code>\n\n"
        "Перешлите ссылку пользователю — он откроет бота и получит доступ автоматически."
    )


TEMPLINK_TITLE = "⏳ <b>Временная ссылка</b>\n\nВыберите срок VPN-доступа:"


def _days_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "дня"
    return "дней"


def templink_btn(days: int) -> str:
    return f"{days} {_days_word(days)}"


def admin_templink_created(name: str | None, key_value: str, link: str, days: int) -> str:
    who = f" «{name}»" if name else ""
    return (
        f"⏳ Временный профиль{who} создан. Доступ: <b>{days} {_days_word(days)}</b>.\n\n"
        f'<a href="{link}">👉 Ссылка-приглашение (один тап)</a>\n'
        f"<code>{link}</code>\n\n"
        f"Или ключ для ручного ввода: <code>{key_value}</code>\n\n"
        "После активации VLESS-доступ автоматически истечёт на узле по сроку."
    )
