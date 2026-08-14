from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def channels_keyboard(channels, selected: set[int]) -> InlineKeyboardMarkup:
    """channels: список записей из db.list_channels(); selected: множество выбранных channel_id"""
    b = InlineKeyboardBuilder()
    for ch in channels:
        mark = "✅ " if ch["id"] in selected else "◻️ "
        b.button(text=f"{mark}{ch['title']}", callback_data=f"ch:{ch['id']}")
    b.button(text="➡️ Далее", callback_data="channels_done")
    b.button(text="✖️ Отмена", callback_data="cancel")
    b.adjust(1)
    return b.as_markup()


def delete_after_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Удалить через 24ч", callback_data="del:24")
    b.button(text="Удалить через 48ч", callback_data="del:48")
    b.button(text="Удалить через 72ч", callback_data="del:72")
    b.button(text="Не удалять", callback_data="del:0")
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


def remove_channels_keyboard(channels) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.button(text=f"❌ {ch['title']}", callback_data=f"rmch:{ch['id']}")
    b.adjust(1)
    return b.as_markup()
