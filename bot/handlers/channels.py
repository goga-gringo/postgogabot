import random
import string
import time

from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, MessageOriginChannel
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import db
from bot import ui
from bot.keyboards import channels_menu_keyboard, HOME_BUTTON

router = Router()

# Коды подтверждения канала: код -> {tg_id, expires}. Живут в памяти процесса —
# этого достаточно, они короткоживущие (10 минут) и на один инстанс бота.
_pending_codes: dict[str, dict] = {}
CODE_TTL_SECONDS = 600


def _generate_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


async def _send_add_instructions(target, tg_id: int, prefix: str = ""):
    code = _generate_code()
    _pending_codes[code] = {"tg_id": tg_id, "expires": time.time() + CODE_TTL_SECONDS}
    user_id = await db.get_or_create_user(tg_id)
    await ui.clear_previous(target.bot, target.chat.id, user_id)
    b = InlineKeyboardBuilder()
    b.row(HOME_BUTTON)
    sent = await target.answer(
        prefix +
        "Чтобы подключить канал:\n\n"
        "1. Добавь меня в канал как администратора с правами:\n"
        "   • Публикация сообщений\n"
        "   • Редактирование сообщений других пользователей\n"
        "   • Удаление сообщений\n\n"
        f"2. Опубликуй в канале сообщение с этим кодом (я сам его удалю):\n\n<code>{code}</code>\n\n"
        "Код действует 10 минут.",
        reply_markup=b.as_markup(),
    )
    await ui.track(user_id, sent)


async def cmd_channels(message: Message):
    """Экран 'Мои каналы': список + удаление + добавление. Переиспользуется из /channels и из reply-меню."""
    user_id = await db.get_or_create_user(message.from_user.id)
    channels = await db.list_channels(user_id)
    if not channels:
        await _send_add_instructions(message, message.from_user.id, prefix="Пока нет подключённых каналов.\n\n")
        return
    await ui.clear_previous(message.bot, message.chat.id, user_id)
    sent = await message.answer("Твои каналы:", reply_markup=channels_menu_keyboard(channels))
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
    await db.remove_channel(user_id, channel_id)

    channels = await db.list_channels(user_id)
    if channels:
        await callback.message.edit_text("Канал отключён.\n\nТвои каналы:", reply_markup=channels_menu_keyboard(channels))
    else:
        await callback.message.edit_text("Канал отключён. Больше подключённых каналов нет.")
    await callback.answer()


# ---------- основной способ подключения: код, опубликованный прямо в канале ----------
# Надёжнее пересылки: если пост в канале сам является репостом из другого канала,
# forward_origin покажет исходный канал, а не тот, куда добавлен бот — пересылка
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
    await db.add_channel(user_id, chat.id, chat.title or "Без названия")

    try:
        await bot.delete_message(chat.id, message.message_id)
    except Exception:
        pass  # не критично, если не смогли подчистить сообщение с кодом

    note = "" if can_edit else (
        "\n⚠️ Нет права «Редактирование сообщений других пользователей» — "
        "live-правка текста уже опубликованных постов работать не будет."
    )
    await bot.send_message(tg_id, f"✅ Канал «{chat.title}» подключён!{note}")


# ---------- запасной способ: пересылка сообщения из канала ----------
# Работает, если пересылаемый пост НЕ является репостом из другого канала.
# StateFilter(None) — важно: если пользователь сейчас в процессе создания поста
# (пересылает контент ДЛЯ ПУБЛИКАЦИИ, а не для подключения канала), этот
# обработчик не должен перехватывать сообщение — оно должно уйти в приём
# контента поста (posts.py).

@router.message(F.forward_origin.as_("origin"), StateFilter(None))
async def handle_forwarded(message: Message, origin: MessageOriginChannel, bot: Bot):
    if origin.type != "channel":
        await message.answer(
            "Не могу определить исходный канал по этой пересылке "
            "(Telegram скрывает эту информацию для репостов и части пересланных сообщений).\n\n"
            "Пересылка вообще ненадёжна для подключения канала — используй способ через код: "
            "«📢 Мои каналы» → «➕ Добавить канал»."
        )
        return

    chat = origin.chat
    try:
        member = await bot.get_chat_member(chat.id, bot.id)
    except Exception as e:
        if "not a member" in str(e).lower() or "forbidden" in str(e).lower():
            await message.answer(
                "Не вижу себя участником канала «" + (chat.title or "") + "».\n\n"
                "Если этот пост сам является репостом из другого канала — Telegram "
                "показывает исходный канал вместо того, куда я добавлен, и пересылка "
                "тут не сработает в принципе.\n\n"
                "Используй способ через код: «📢 Мои каналы» → «➕ Добавить канал» — "
                "надёжнее и не зависит от того, репост это или нет."
            )
        else:
            await message.answer(f"Не удалось проверить права в канале: {e}")
        return

    is_admin = member.status == "administrator"
    can_post = getattr(member, "can_post_messages", False)
    can_edit = getattr(member, "can_edit_messages", False)
    can_delete = getattr(member, "can_delete_messages", False)

    if not is_admin or not can_post or not can_delete:
        await message.answer(
            "Я не администратор этого канала (или не хватает прав публикации/удаления). "
            "Добавь мне права и перешли сообщение ещё раз."
        )
        return

    if not can_edit:
        await message.answer(
            "⚠️ Канал подключаю, но у меня нет права «Редактирование сообщений других "
            "пользователей» — без него не получится править текст уже опубликованных "
            "постов через «📋 Мои посты» (публикация и автоудаление при этом будут работать)."
        )

    user_id = await db.get_or_create_user(message.from_user.id)
    await db.add_channel(user_id, chat.id, chat.title or "Без названия")
    await message.answer(f"✅ Канал «{chat.title}» подключён!")
