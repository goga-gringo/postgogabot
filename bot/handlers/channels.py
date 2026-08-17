import random
import string
import time

from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, MessageOriginChannel
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import db
from bot import ui
from bot.i18n import t, get_user_lang
from bot.keyboards import channels_menu_keyboard, home_button

router = Router()

# Коды подтверждения канала: код -> {tg_id, expires}. Живут в памяти процесса —
# этого достаточно, они короткоживущие (10 минут) и на один инстанс бота.
_pending_codes: dict[str, dict] = {}
CODE_TTL_SECONDS = 600


def _generate_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


async def _send_add_instructions(target, tg_id: int, prefix_key: str | None = None):
    code = _generate_code()
    _pending_codes[code] = {"tg_id": tg_id, "expires": time.time() + CODE_TTL_SECONDS}
    user_id = await db.get_or_create_user(tg_id)
    lang = await get_user_lang(user_id)
    await ui.clear_previous(target.bot, target.chat.id, user_id)
    prefix = t(lang, prefix_key) if prefix_key else ""
    b = InlineKeyboardBuilder()
    b.row(home_button(lang))
    sent = await target.answer(
        t(lang, "channels.add_instructions", prefix=prefix, code=code),
        reply_markup=b.as_markup(),
    )
    await ui.track(user_id, sent)


async def cmd_channels(message: Message):
    """Экран 'Мои каналы': список + удаление + добавление. Переиспользуется из /channels и из reply-меню."""
    user_id = await db.get_or_create_user(message.from_user.id)
    lang = await get_user_lang(user_id)
    channels = await db.list_channels(user_id)
    if not channels:
        await _send_add_instructions(message, message.from_user.id, prefix_key="channels.no_channels")
        return
    await ui.clear_previous(message.bot, message.chat.id, user_id)
    sent = await message.answer(t(lang, "channels.list_header"), reply_markup=channels_menu_keyboard(channels, lang))
    await ui.track(user_id, sent)


@router.message(Command("addchannel"))
async def cmd_addchannel(message: Message):
    await _send_add_instructions(message, message.from_user.id)


@router.message(Command("channels"))
async def cmd_channels_cmd(message: Message):
    await cmd_channels(message)


@router.message(Command("removechannel"))
async def cmd_removechannel(message: Message):
    await cmd_channels(message)


@router.callback_query(F.data == "show_add_channel_hint")
async def cb_show_add_hint(callback: CallbackQuery):
    await _send_add_instructions(callback.message, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data.startswith("rmch:"))
async def cb_remove_channel(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    lang = await get_user_lang(user_id)
    await db.remove_channel(user_id, channel_id)

    channels = await db.list_channels(user_id)
    if channels:
        await callback.message.edit_text(t(lang, "channels.removed"), reply_markup=channels_menu_keyboard(channels, lang))
    else:
        await callback.message.edit_text(t(lang, "channels.removed_none_left"))
    await callback.answer()


# ---------- основной способ подключения: код, опубликованный прямо в канале ----------
# Надёжнее пересылки: если пост в канале сам является репостом из другого канала,
# forward_origin показывает исходный канал, а не тот, куда добавлен бот — пересылка
# в таком случае ошибочно ругается на права. Публикация в канал напрямую такой
# проблемы не имеет: chat.id всегда правильный.

@router.channel_post()
async def handle_channel_post(message: Message, bot: Bot):
    raw = (message.text or message.caption or "").strip().upper()
    entry = _pending_codes.get(raw)
    if not entry:
        return
    if entry["expires"] < time.time():
        _pending_codes.pop(raw, None)
        return

    chat = message.chat
    try:
        member = await bot.get_chat_member(chat.id, bot.id)
    except Exception:
        return  # не удалось проверить — просто игнорируем этот пост

    is_admin = member.status == "administrator"
    can_post = getattr(member, "can_post_messages", False)
    can_edit = getattr(member, "can_edit_messages", False)
    can_delete = getattr(member, "can_delete_messages", False)

    if not (is_admin and can_post and can_delete):
        return  # прав не хватает — код останется активным, попробует ещё раз после выдачи прав

    _pending_codes.pop(raw, None)
    tg_id = entry["tg_id"]
    user_id = await db.get_or_create_user(tg_id)
    lang = await get_user_lang(user_id)
    await db.add_channel(user_id, chat.id, chat.title or "Untitled")

    try:
        await bot.delete_message(chat.id, message.message_id)
    except Exception:
        pass  # не критично, если не смогли подчистить сообщение с кодом

    note = "" if can_edit else t(lang, "channels.no_edit_right")
    await bot.send_message(tg_id, t(lang, "channels.connected", title=chat.title, note=note))


# ---------- запасной способ: пересылка сообщения из канала ----------
# Работает, если пересылаемый пост НЕ является репостом из другого канала.
# StateFilter(None) — важно: если пользователь сейчас в процессе создания поста
# (пересылает контент ДЛЯ ПУБЛИКАЦИИ, а не для подключения канала), этот
# обработчик не должен перехватывать сообщение — оно должно уйти в приём
# контента поста (posts.py).

@router.message(F.forward_origin.as_("origin"), StateFilter(None))
async def handle_forwarded(message: Message, origin: MessageOriginChannel, bot: Bot):
    user_id = await db.get_or_create_user(message.from_user.id)
    lang = await get_user_lang(user_id)

    if origin.type != "channel":
        await message.answer(t(lang, "channels.forward_not_channel"))
        return

    chat = origin.chat
    try:
        member = await bot.get_chat_member(chat.id, bot.id)
    except Exception as e:
        if "not a member" in str(e).lower() or "forbidden" in str(e).lower():
            await message.answer(t(lang, "channels.forward_not_member"))
        else:
            await message.answer(t(lang, "channels.forward_check_error", error=str(e)))
        return

    is_admin = member.status == "administrator"
    can_post = getattr(member, "can_post_messages", False)
    can_edit = getattr(member, "can_edit_messages", False)
    can_delete = getattr(member, "can_delete_messages", False)

    if not is_admin or not can_post or not can_delete:
        await message.answer(t(lang, "channels.forward_not_admin"))
        return

    note = "" if can_edit else t(lang, "channels.no_edit_right")
    await db.add_channel(user_id, chat.id, chat.title or "Untitled")
    await message.answer(t(lang, "channels.connected", title=chat.title, note=note))
