import asyncio
import logging

from aiogram import Bot
from aiogram.types import InputMediaPhoto, InputMediaVideo

from bot import db
from bot.config import POLL_INTERVAL_SECONDS

logger = logging.getLogger(__name__)


async def _publish_one(bot: Bot, row):
    chat_id = row["chat_id"]
    try:
        if row["media_type"] == "photo":
            msg = await bot.send_photo(chat_id, row["file_id"], caption=row["text"], parse_mode="HTML")
            message_ids = [msg.message_id]

        elif row["media_type"] == "video":
            msg = await bot.send_video(chat_id, row["file_id"], caption=row["text"], parse_mode="HTML")
            message_ids = [msg.message_id]

        elif row["media_type"] == "album":
            items = await db.get_album_items(row["post_id"])
            media = []
            for i, item in enumerate(items):
                cls = InputMediaPhoto if item["media_type"] == "photo" else InputMediaVideo
                kwargs = {}
                if i == 0 and row["text"]:
                    kwargs["caption"] = row["text"]
                    kwargs["parse_mode"] = "HTML"
                media.append(cls(media=item["file_id"], **kwargs))
            msgs = await bot.send_media_group(chat_id, media)
            message_ids = [m.message_id for m in msgs]

        else:  # text
            msg = await bot.send_message(chat_id, row["text"], parse_mode="HTML")
            message_ids = [msg.message_id]

        await db.mark_published(row["target_id"], message_ids, row["delete_after_hours"])
        logger.info("Published target %s to chat %s (%d msg)", row["target_id"], chat_id, len(message_ids))
    except Exception as e:
        logger.exception("Failed to publish target %s", row["target_id"])
        await db.mark_failed(row["target_id"], str(e))


async def _delete_one(bot: Bot, row):
    for message_id in (row["message_ids"] or []):
        try:
            await bot.delete_message(row["chat_id"], message_id)
        except Exception as e:
            # Сообщение могло быть уже удалено вручную — это не критично
            logger.warning("Delete failed for target %s msg %s: %s", row["target_id"], message_id, e)
    await db.mark_deleted(row["target_id"])


async def publisher_loop(bot: Bot):
    while True:
        try:
            due = await db.fetch_due_to_publish()
            for row in due:
                await _publish_one(bot, row)
        except Exception:
            logger.exception("publisher_loop iteration failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def cleaner_loop(bot: Bot):
    while True:
        try:
            due = await db.fetch_due_to_delete()
            for row in due:
                await _delete_one(bot, row)
        except Exception:
            logger.exception("cleaner_loop iteration failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
