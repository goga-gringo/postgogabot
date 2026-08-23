from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from bot.i18n import t, DEFAULT_LANG


def home_button(lang: str = DEFAULT_LANG) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=t(lang, "btn.home"), callback_data="go_home")


def main_menu_keyboard(lang: str = DEFAULT_LANG) -> ReplyKeyboardMarkup:
    """Постоянное меню внизу экрана — разделы, а не настройки конкретного поста."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "menu.create"))],
            [KeyboardButton(text=t(lang, "menu.channels")), KeyboardButton(text=t(lang, "menu.posts"))],
            [KeyboardButton(text=t(lang, "menu.settings"))],
        ],
        resize_keyboard=True,
    )


def channels_keyboard(channels, selected: set[int], lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Выбор каналов при создании поста (toggle-галочки + 'во все')."""
    b = InlineKeyboardBuilder()
    for ch in channels:
        mark = "✅ " if ch["id"] in selected else "◻️ "
        b.button(text=f"{mark}{ch['title']}", callback_data=f"ch:{ch['id']}")
    b.adjust(1)

    all_ids = {ch["id"] for ch in channels}
    if channels and selected == all_ids:
        b.row(InlineKeyboardButton(text=t(lang, "btn.deselect_all"), callback_data="toggle_all"))
    else:
        b.row(InlineKeyboardButton(text=t(lang, "btn.select_all"), callback_data="toggle_all"))

    b.row(InlineKeyboardButton(text=t(lang, "btn.next"), callback_data="channels_done"))
    b.row(InlineKeyboardButton(text=t(lang, "btn.cancel"), callback_data="cancel"))
    return b.as_markup()


HOUR_OPTIONS = [1, 2, 4, 8, 12, 24, 48, 72]


def delete_after_keyboard(default_hours: int | None = None, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for hours in HOUR_OPTIONS:
        star = "⭐" if (default_hours or 0) == hours else ""
        b.button(text=f"{star}{hours}ч" if lang == "ru" else f"{star}{hours}h", callback_data=f"del:{hours}")
    never_star = "⭐" if not default_hours else ""
    b.button(text=f"{never_star}{t(lang, 'btn.never_delete')}", callback_data="del:0")
    b.adjust(4, 4, 1)
    b.row(InlineKeyboardButton(text=t(lang, "btn.cancel"), callback_data="cancel"))
    return b.as_markup()


def preview_keyboard(link_button_rows=None, allow_link_buttons: bool = True, lang: str = DEFAULT_LANG, silent: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура под предпросмотром: сверху кнопки-ссылки (если есть),
    снизу управление ботом (звук / когда публиковать / добавить кнопки)."""
    b = InlineKeyboardBuilder()
    for row in (link_button_rows or []):
        b.row(*[InlineKeyboardButton(text=btn["text"], url=btn["url"]) for btn in row])

    sound_label = t(lang, "btn.silent_on") if silent else t(lang, "btn.silent_off")
    b.row(InlineKeyboardButton(text=sound_label, callback_data="toggle_silent"))

    b.row(InlineKeyboardButton(text=t(lang, "btn.publish_now"), callback_data="when:now"))
    b.row(InlineKeyboardButton(text=t(lang, "btn.in_1h"), callback_data="when:1h"))
    b.row(InlineKeyboardButton(text=t(lang, "btn.in_3h"), callback_data="when:3h"))
    b.row(InlineKeyboardButton(text=t(lang, "btn.custom_time"), callback_data="when:custom"))

    if allow_link_buttons:
        label = t(lang, "btn.edit_link_buttons") if link_button_rows else t(lang, "btn.add_link_buttons")
        b.row(InlineKeyboardButton(text=label, callback_data="add_link_buttons"))

    b.row(InlineKeyboardButton(text=t(lang, "btn.cancel"), callback_data="cancel"))
    return b.as_markup()


def back_only_keyboard(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=t(lang, "btn.back"), callback_data="preview_back"))
    b.row(home_button(lang))
    return b.as_markup()


def link_buttons_only_markup(rows) -> InlineKeyboardMarkup | None:
    """Кнопки для РЕАЛЬНОГО опубликованного поста — без служебных when:*."""
    if not rows:
        return None
    b = InlineKeyboardBuilder()
    for row in rows:
        b.row(*[InlineKeyboardButton(text=btn["text"], url=btn["url"]) for btn in row])
    return b.as_markup()


def channels_menu_keyboard(channels, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Экран 'Мои каналы': список с удалением + кнопка добавить + выход в меню."""
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.button(text=f"❌ {ch['title']}", callback_data=f"rmch:{ch['id']}")
    b.button(text=t(lang, "btn.add_channel"), callback_data="show_add_channel_hint")
    b.adjust(1)
    b.row(home_button(lang))
    return b.as_markup()


def settings_keyboard(
    current_tz: str, current_default_hours: int | None, current_lang: str,
    delete_from_comments: bool = False, lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    from bot.tzutil import COMMON_TIMEZONES

    b = InlineKeyboardBuilder()

    b.row(
        InlineKeyboardButton(
            text=("✅ " if current_lang == "ru" else "◻️ ") + t(lang, "btn.lang_ru"), callback_data="lang:ru"
        ),
        InlineKeyboardButton(
            text=("✅ " if current_lang == "en" else "◻️ ") + t(lang, "btn.lang_en"), callback_data="lang:en"
        ),
    )

    for tz_name, labels in COMMON_TIMEZONES:
        label = labels.get(lang, labels["ru"])
        mark = "✅ " if tz_name == current_tz else "◻️ "
        b.button(text=f"{mark}{label}", callback_data=f"tz:{tz_name}")
    b.adjust(1)

    for hours in HOUR_OPTIONS:
        mark = "✅ " if (current_default_hours or 0) == hours else "◻️ "
        b.button(text=f"{mark}{t(lang, 'btn.default_delete_hours', h=hours)}", callback_data=f"defdel:{hours}")
    never_mark = "✅ " if not current_default_hours else "◻️ "
    b.button(text=f"{never_mark}{t(lang, 'btn.default_never')}", callback_data="defdel:0")
    b.adjust(1)

    comments_mark = "✅ " if delete_from_comments else "◻️ "
    b.row(InlineKeyboardButton(
        text=f"{comments_mark}{t(lang, 'btn.delete_from_comments')}", callback_data="toggle_comments"
    ))

    b.row(home_button(lang))

    return b.as_markup()
