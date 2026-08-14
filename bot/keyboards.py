from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

MENU_CREATE = "📝 Создать пост"
MENU_CHANNELS = "📢 Мои каналы"
MENU_POSTS = "📋 Мои посты"
MENU_SETTINGS = "⚙️ Настройки"


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
    """Выбор каналов при создании поста (toggle-галочки)."""
    b = InlineKeyboardBuilder()
    for ch in channels:
        mark = "✅ " if ch["id"] in selected else "◻️ "
        b.button(text=f"{mark}{ch['title']}", callback_data=f"ch:{ch['id']}")
    b.button(text="➡️ Далее", callback_data="channels_done")
    b.button(text="✖️ Отмена", callback_data="cancel")
    b.adjust(1)
    return b.as_markup()


def delete_after_keyboard(default_hours: int | None = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    options = [
        (24, "Удалить через 24ч"),
        (48, "Удалить через 48ч"),
        (72, "Удалить через 72ч"),
        (0, "Не удалять"),
    ]
    for hours, label in options:
        star = "⭐ " if (default_hours or 0) == hours else ""
        b.button(text=f"{star}{label}", callback_data=f"del:{hours}")
    b.adjust(1)
    return b.as_markup()


def when_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🚀 Опубликовать сейчас", callback_data="when:now")
    b.button(text="🕐 Через 1 час", callback_data="when:1h")
    b.button(text="🕒 Через 3 часа", callback_data="when:3h")
    b.button(text="📅 Указать время вручную", callback_data="when:custom")
    b.adjust(1)
    return b.as_markup()


def channels_menu_keyboard(channels) -> InlineKeyboardMarkup:
    """Экран 'Мои каналы': список с удалением + кнопка добавить."""
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.button(text=f"❌ {ch['title']}", callback_data=f"rmch:{ch['id']}")
    b.button(text="➕ Добавить канал", callback_data="show_add_channel_hint")
    b.adjust(1)
    return b.as_markup()


def settings_keyboard(current_tz: str, current_default_hours: int | None) -> InlineKeyboardMarkup:
    from bot.tzutil import COMMON_TIMEZONES

    b = InlineKeyboardBuilder()
    for tz_name, label in COMMON_TIMEZONES:
        mark = "✅ " if tz_name == current_tz else "◻️ "
        b.button(text=f"{mark}{label}", callback_data=f"tz:{tz_name}")
    b.adjust(1)

    for hours, label in [(24, "24ч"), (48, "48ч"), (72, "72ч"), (0, "не удалять")]:
        mark = "✅ " if (current_default_hours or 0) == hours else "◻️ "
        b.button(text=f"{mark}Автоудаление по умолчанию: {label}", callback_data=f"defdel:{hours}")
    b.adjust(1)

    return b.as_markup()
