import asyncio
import json
import logging

from aiogram import Bot
from aiogram.types import InputMediaPhoto, InputMediaVideo

from bot import db
from bot.config import POLL_INTERVAL_SECONDS, POST_RETENTION_DAYS, CLEANUP_INTERVAL_SECONDS
from bot.entities_util import deserialize_entities
from bot.keyboards import link_buttons_only_markup

logger = logging.getLogger(__name__)


def _button_markup(row):
    try:
        rows = json.loads(row["button_json"]) if row["button_json"] else None
    except Exception:
        rows = None
    return link_buttons_only_markup(rows)


async def _publish_via_copy(bot: Bot, row) -> list[int] | None:
    """Пытаемся опубликовать через copyMessage(s) — Telegram копирует сообщение
    как есть на своей стороне, со всеми entities (включая premium-эмодзи),
    без пересборки ботом. Возвращает None, если не получилось (сообщение
    в личке удалено, пост правили и т.п.) — тогда используем реконструкцию."""
    if row["text_edited"] or not row["source_chat_id"] or not row["source_message_ids"]:
        return None
    try:
        if row["media_type"] == "album":
            # copyMessages не поддерживает reply_markup — кнопки-ссылки у альбомов
            # в принципе недоступны (ограничение Telegram), поэтому просто копируем.
            results = await bot.copy_messages(row["chat_id"], row["source_chat_id"], row["source_message_ids"])
            return [r.message_id for r in results]
        else:
            result = await bot.copy_message(
                row["chat_id"], row["source_chat_id"], row["source_message_ids"][0],
                parse_mode=None, reply_markup=_button_markup(row),
            )
            return [result.message_id]
    except Exception as e:
        logger.warning("copy_message failed for target %s, falling back to reconstruct: %s", row["target_id"], e)
        return None


async def _publish_via_reconstruct(bot: Bot, row) -> list[int]:
    """Запасной путь: пересобираем сообщение из file_id + текст + entities.
    Используется, если пост правили после создания, или если copy не удался."""
    chat_id = row["chat_id"]
    entities = deserialize_entities(row["entities_json"])
    markup = _button_markup(row)

    if row["media_type"] == "photo":
        msg = await bot.send_photo(
            chat_id, row["file_id"], caption=row["text"], caption_entities=entities,
            parse_mode=None, reply_markup=markup,
        )
        return [msg.message_id]

    if row["media_type"] == "video":
        msg = await bot.send_video(
            chat_id, row["file_id"], caption=row["text"], caption_entities=entities,
            parse_mode=None, reply_markup=markup,
        )
        return [msg.message_id]

    if row["media_type"] == "album":
        items = await db.get_album_items(row["post_id"])
        media = []
        for i, item in enumerate(items):
            cls = InputMediaPhoto if item["media_type"] == "photo" else InputMediaVideo
            kwargs = {}
            if i == 0 and row["text"]:
                kwargs["caption"] = row["text"]
                kwargs["caption_entities"] = entities
                kwargs["parse_mode"] = None
            media.append(cls(media=item["file_id"], **kwargs))
        msgs = await bot.send_media_group(chat_id, media)  # sendMediaGroup не поддерживает reply_markup
        return [m.message_id for m in msgs]

    msg = await bot.send_message(chat_id, row["text"], entities=entities, parse_mode=None, reply_markup=markup)
    return [msg.message_id]


async def _publish_one(bot: Bot, row):
    try:
        message_ids = await _publish_via_copy(bot, row)
        if message_ids is None:
            message_ids = await _publish_via_reconstruct(bot, row)

        await db.mark_published(row["target_id"], message_ids, row["delete_after_hours"])
        logger.info("Published target %s to chat %s (%d msg)", row["target_id"], row["chat_id"], len(message_ids))
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


async def old_posts_cleanup_loop():
    """Периодически физически стирает из БД посты старше POST_RETENTION_DAYS
    дней (у которых не осталось активных запланированных публикаций).
    Каскадом удаляются и их медиа-элементы, и таргеты по каналам."""
    while True:
        try:
            removed = await db.purge_old_posts(POST_RETENTION_DAYS)
            if removed:
                logger.info("Purged %d old post(s) (older than %d days)", removed, POST_RETENTION_DAYS)
        except Exception:
            logger.exception("old_posts_cleanup_loop iteration failed")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
