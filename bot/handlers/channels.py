from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, MessageOriginChannel

from bot import db
from bot.keyboards import remove_channels_keyboard

router = Router()

ADD_CHANNEL_HINT = (
    "Чтобы подключить канал:\n\n"
    "1. Добавь меня в канал как администратора с правами:\n"
    "   • Публикация сообщений\n"
    "   • Удаление сообщений\n"
    "2. Перешли мне (сюда, в личку) любое сообщение из этого канала.\n\n"
    "Я проверю права и подключу канал."
)


@router.message(Command("addchannel"))
async def cmd_addchannel(message: Message):
    await message.answer(ADD_CHANNEL_HINT)


@router.message(Command("channels"))
async def cmd_channels(message: Message):
    user_id = await db.get_or_create_user(message.from_user.id)
    channels = await db.list_channels(user_id)
    if not channels:
        await message.answer("Пока нет подключённых каналов. Используй /addchannel")
        return
    text = "Твои каналы:\n" + "\n".join(f"• {c['title']}" for c in channels)
    await message.answer(text)


@router.message(Command("removechannel"))
async def cmd_removechannel(message: Message):
    user_id = await db.get_or_create_user(message.from_user.id)
    channels = await db.list_channels(user_id)
    if not channels:
        await message.answer("Нет подключённых каналов.")
        return
    await message.answer("Выбери канал для отключения:", reply_markup=remove_channels_keyboard(channels))


@router.callback_query(F.data.startswith("rmch:"))
async def cb_remove_channel(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    await db.remove_channel(user_id, channel_id)
    await callback.message.edit_text("Канал отключён.")
    await callback.answer()


@router.message(F.forward_origin.as_("origin"))
async def handle_forwarded(message: Message, origin: MessageOriginChannel, bot: Bot):
    """Пользователь переслал пост из канала — пытаемся подключить канал."""
    if origin.type != "channel":
        await message.answer("Это не похоже на пересланное сообщение из канала.")
        return

    chat = origin.chat
    try:
        member = await bot.get_chat_member(chat.id, bot.id)
    except Exception as e:
        await message.answer(f"Не удалось проверить права в канале: {e}")
        return

    is_admin = member.status == "administrator"
    can_post = getattr(member, "can_post_messages", False)
    can_delete = getattr(member, "can_delete_messages", False)

    if not is_admin or not can_post or not can_delete:
        await message.answer(
            "Я не администратор этого канала (или не хватает прав публикации/удаления). "
            "Добавь мне права и перешли сообщение ещё раз."
        )
        return

    user_id = await db.get_or_create_user(message.from_user.id)
    await db.add_channel(user_id, chat.id, chat.title or "Без названия")
    await message.answer(f"✅ Канал «{chat.title}» подключён!")
