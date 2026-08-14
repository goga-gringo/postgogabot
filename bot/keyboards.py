from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

MENU_CREATE = "📝 Создать пост"
MENU_CHANNELS = "📢 Мои каналы"
MENU_POSTS = "📋 Мои посты"
MENU_SETTINGS = "⚙️ Настройки"

HOME_BUTTON = InlineKeyboardButton(text="🏠 Главное меню", callback_data="go_home")


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Постоянное меню внизу экрана — разделы, а не настройки конкретного поста."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_CREATE)],
            [KeyboardButton(text=MENU_CHANNELS), KeyboardButton(text=MENU_POSTS)],
            [KeyboardButton(text=MENU_SETTINGS)],
        ],
        resize_keyboard=True,
    )


def channels_keyboard(channels, selected: set[int]) -> InlineKeyboardMarkup:
    """Выбор каналов при создании поста (toggle-галочки + 'во все')."""
    b = InlineKeyboardBuilder()
    for ch in channels:
        mark = "✅ " if ch["id"] in selected else "◻️ "
        b.button(text=f"{mark}{ch['title']}", callback_data=f"ch:{ch['id']}")
    b.adjust(1)

    all_ids = {ch["id"] for ch in channels}
    if channels and selected == all_ids:
        b.row(InlineKeyboardButton(text="🚫 Снять со всех", callback_data="toggle_all"))
    else:
        b.row(InlineKeyboardButton(text="✅ Во все", callback_data="toggle_all"))

    b.row(InlineKeyboardButton(text="➡️ Далее", callback_data="channels_done"))
    b.row(InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel"))
    return b.as_markup()


HOUR_OPTIONS = [1, 2, 4, 8, 12, 24, 48, 72]


def delete_after_keyboard(default_hours: int | None = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for hours in HOUR_OPTIONS:
        star = "⭐" if (default_hours or 0) == hours else ""
        b.button(text=f"{star}{hours}ч", callback_data=f"del:{hours}")
    never_star = "⭐" if not default_hours else ""
    b.button(text=f"{never_star}Не удалять", callback_data="del:0")
    b.adjust(4, 4, 1)
    b.row(InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel"))
    return b.as_markup()


def preview_keyboard(link_button_rows=None, allow_link_buttons: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура под предпросмотром: сверху кнопки-ссылки (если есть),
    снизу управление ботом (когда публиковать / добавить кнопки)."""
    b = InlineKeyboardBuilder()
    for row in (link_button_rows or []):
        b.row(*[InlineKeyboardButton(text=btn["text"], url=btn["url"]) for btn in row])

    b.row(InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data="when:now"))
    b.row(InlineKeyboardButton(text="🕐 Через 1 час", callback_data="when:1h"))
    b.row(InlineKeyboardButton(text="🕒 Через 3 часа", callback_data="when:3h"))
    b.row(InlineKeyboardButton(text="📅 Указать время вручную", callback_data="when:custom"))

    if allow_link_buttons:
        label = "🔗 Изменить кнопки-ссылки" if link_button_rows else "🔗 Добавить кнопку-ссылку"
        b.row(InlineKeyboardButton(text=label, callback_data="add_link_buttons"))

    b.row(InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel"))
    return b.as_markup()


def back_only_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="preview_back"))
    b.row(HOME_BUTTON)
    return b.as_markup()


def link_buttons_only_markup(rows) -> InlineKeyboardMarkup | None:
    """Кнопки для РЕАЛЬНОГО опубликованного поста — без служебных when:*."""
    if not rows:
        return None
    b = InlineKeyboardBuilder()
    for row in rows:
        b.row(*[InlineKeyboardButton(text=btn["text"], url=btn["url"]) for btn in row])
    return b.as_markup()


def channels_menu_keyboard(channels) -> InlineKeyboardMarkup:
    """Экран 'Мои каналы': список с удалением + кнопка добавить + выход в меню."""
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.button(text=f"❌ {ch['title']}", callback_data=f"rmch:{ch['id']}")
    b.button(text="➕ Добавить канал", callback_data="show_add_channel_hint")
    b.adjust(1)
    b.row(HOME_BUTTON)
    return b.as_markup()


def settings_keyboard(current_tz: str, current_default_hours: int | None) -> InlineKeyboardMarkup:
    from bot.tzutil import COMMON_TIMEZONES

    b = InlineKeyboardBuilder()
    for tz_name, label in COMMON_TIMEZONES:
        mark = "✅ " if tz_name == current_tz else "◻️ "
        b.button(text=f"{mark}{label}", callback_data=f"tz:{tz_name}")
    b.adjust(1)

    for hours in HOUR_OPTIONS:
        mark = "✅ " if (current_default_hours or 0) == hours else "◻️ "
        b.button(text=f"{mark}По умолчанию: {hours}ч", callback_data=f"defdel:{hours}")
    never_mark = "✅ " if not current_default_hours else "◻️ "
    b.button(text=f"{never_mark}По умолчанию: не удалять", callback_data="defdel:0")
    b.adjust(1)
    b.row(HOME_BUTTON)

    return b.as_markup()
