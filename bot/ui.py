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
