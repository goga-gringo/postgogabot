import logging

from aiogram import Bot
from aiogram.types import Message

from bot import db

logger = logging.getLogger(__name__)


async def clear_previous(bot: Bot, chat_id: int, user_id: int):
    """Удаляет предыдущее 'экранное' сообщение бота этому пользователю, если есть.
    Вызывать перед показом нового экрана (список каналов, список постов, настройки,
    мастер создания поста), чтобы не плодить вереницу сообщений с мёртвыми кнопками."""
    user = await db.get_user(user_id)
    last_id = user["last_bot_message_id"] if user else None
    if not last_id:
        return
    try:
        await bot.delete_message(chat_id, last_id)
    except Exception as e:
        logger.debug("Could not delete previous screen message %s: %s", last_id, e)


async def track(user_id: int, message: Message):
    """Запоминаем id только что отправленного 'экранного' сообщения."""
    await db.set_last_message_id(user_id, message.message_id)


async def delete_user_message(message: Message):
    """Удаляет сообщение, которое прислал сам пользователь (контент поста,
    нажатие reply-кнопки, ввод текста и т.п.) — после того как бот его уже
    обработал. Боты могут удалять входящие сообщения в личных чатах (это
    штатно разрешено Bot API), поэтому работает без специальных прав."""
    try:
        await message.delete()
    except Exception as e:
        logger.debug("Could not delete user message %s: %s", message.message_id, e)
