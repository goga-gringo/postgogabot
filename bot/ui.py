import logging

from aiogram import Bot
from aiogram.types import Message

from bot import db

logger = logging.getLogger(__name__)


async def clear_previous(bot: Bot, chat_id: int, user_id: int):
    """Удаляет предыдущий 'экран' бота этому пользователю, если есть (может
    состоять из нескольких сообщений — например медиа + отдельный статус-текст).
    Вызывать перед показом нового экрана, чтобы не плодить вереницу сообщений
    с мёртвыми кнопками."""
    user = await db.get_user(user_id)
    ids = list(user["last_bot_message_ids"] or []) if user else []
    if not ids:
        return
    for mid in ids:
        try:
            await bot.delete_message(chat_id, mid)
        except Exception as e:
            logger.debug("Could not delete previous screen message %s: %s", mid, e)
    await db.set_last_message_ids(user_id, [])


async def track(user_id: int, message_or_messages):
    """Запоминаем id только что отправленного 'экрана' — одно сообщение или
    список (если экран из нескольких, например медиа + статус отдельно)."""
    if isinstance(message_or_messages, (list, tuple)):
        ids = [m.message_id for m in message_or_messages]
    else:
        ids = [message_or_messages.message_id]
    await db.set_last_message_ids(user_id, ids)


async def delete_user_message(message: Message):
    """Удаляет сообщение, которое прислал сам пользователь (контент поста,
    нажатие reply-кнопки, ввод текста и т.п.) — после того как бот его уже
    обработал. Боты могут удалять входящие сообщения в личных чатах (это
    штатно разрешено Bot API), поэтому работает без специальных прав."""
    try:
        await message.delete()
    except Exception as e:
        logger.debug("Could not delete user message %s: %s", message.message_id, e)
