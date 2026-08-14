from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, MessageOriginChannel

from bot import db
from bot.keyboards import channels_menu_keyboard

router = Router()

ADD_CHANNEL_HINT = (
    "Чтобы подключить канал:\n\n"
    "1. Добавь меня в канал как администратора с правами:\n"
    "   • Публикация сообщений\n"
    "   • Редактирование сообщений других пользователей\n"
    "   • Удаление сообщений\n"
    "2. Перешли мне (сюда, в личку) любое сообщение из этого канала.\n\n"
    "Я проверю права и подключу канал."
)


async def cmd_channels(message: Message):
    """Экран 'Мои каналы': список + удаление + добавление. Переиспользуется из /channels и из reply-меню."""
    user_id = await db.get_or_create_user(message.from_user.id)
    channels = await db.list_channels(user_id)
    if not channels:
        await message.answer("Пока нет подключённых каналов.")
        await message.answer(ADD_CHANNEL_HINT)
        return
    await message.answer("Твои каналы:", reply_markup=channels_menu_keyboard(channels))


@router.message(Command("addchannel"))
async def cmd_addchannel(message: Message):
    await message.answer(ADD_CHANNEL_HINT)


@router.message(Command("channels"))
async def cmd_channels_cmd(message: Message):
    await cmd_channels(message)


@router.message(Command("removechannel"))
async def cmd_removechannel(message: Message):
    await cmd_channels(message)


@router.callback_query(F.data == "show_add_channel_hint")
async def cb_show_add_hint(callback: CallbackQuery):
    await callback.message.answer(ADD_CHANNEL_HINT)
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
            "постов через /myposts (публикация и автоудаление при этом будут работать). "
            "Если нужна и правка текста — выдай это право в настройках канала."
        )

    user_id = await db.get_or_create_user(message.from_user.id)
    await db.add_channel(user_id, chat.id, chat.title or "Без названия")
    await message.answer(f"✅ Канал «{chat.title}» подключён!")
