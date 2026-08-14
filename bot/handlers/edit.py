import html as html_lib
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import db
from bot.states import EditPost
from bot.entities_util import serialize_entities, deserialize_entities

router = Router()
logger = logging.getLogger(__name__)


def _plain_preview(text: str | None, length: int = 40) -> str:
    if not text:
        return "(без текста)"
    plain = text.strip() or "(медиа без подписи)"
    return plain[:length] + ("…" if len(plain) > length else "")


@router.message(Command("myposts"))
async def cmd_myposts(message: Message):
    user_id = await db.get_or_create_user(message.from_user.id)
    posts = await db.list_user_posts(user_id)
    if not posts:
        await message.answer("Постов пока нет. Пришли текст/фото/видео, чтобы создать первый.")
        return

    b = InlineKeyboardBuilder()
    for p in posts:
        preview = _plain_preview(p["text"])
        status = f"{p['published_count']}/{p['targets_count']} опубл."
        b.button(text=f"#{p['id']} [{p['media_type']}] {preview} — {status}", callback_data=f"editpost:{p['id']}")
    b.adjust(1)
    await message.answer("Твои последние посты:", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("editpost:"))
async def show_post(callback: CallbackQuery):
    post_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        await callback.answer("Пост не найден", show_alert=True)
        return

    targets = await db.get_targets_for_post(post_id)
    lines = [
        f"<b>Пост #{post_id}</b> ({html_lib.escape(post['media_type'] or '')})",
        "",
        html_lib.escape(post["text"]) if post["text"] else "<i>(без текста)</i>",
        "",
        "<b>Каналы:</b>",
    ]
    status_ru = {"scheduled": "запланирован", "published": "опубликован", "deleted": "удалён", "failed": "ошибка"}
    for t in targets:
        lines.append(f"• {html_lib.escape(t['title'])} — {status_ru.get(t['status'], t['status'])}")

    b = InlineKeyboardBuilder()
    b.button(text="✏️ Изменить текст", callback_data=f"edittext:{post_id}")
    b.button(text="🗑 Удалить пост", callback_data=f"delpost:{post_id}")
    b.adjust(1)

    await callback.message.edit_text("\n".join(lines), reply_markup=b.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("edittext:"))
async def ask_new_text(callback: CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        await callback.answer("Пост не найден", show_alert=True)
        return

    await state.set_state(EditPost.waiting_text)
    await state.update_data(edit_post_id=post_id)

    hint = (
        "Только медиа-подпись, само фото/видео менять нельзя."
        if post["media_type"] in ("photo", "video", "album")
        else "Это текстовый пост целиком."
    )
    await callback.message.edit_text(
        f"Пришли новый текст поста (форматирование сохранится).\n{hint}\n\n/cancel — отменить"
    )
    await callback.answer()


@router.message(EditPost.waiting_text)
async def apply_new_text(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    post_id = data["edit_post_id"]
    new_text = message.text
    entities_json = serialize_entities(message.entities)
    entities = deserialize_entities(entities_json)

    await db.update_post_text(post_id, new_text, entities_json)
    post = await db.get_post(post_id)
    targets = await db.get_targets_for_post(post_id)

    updated, failed = 0, 0
    for t in targets:
        if t["status"] != "published" or not t["message_ids"]:
            continue
        first_id = t["message_ids"][0]
        try:
            if post["media_type"] == "text":
                await bot.edit_message_text(new_text, chat_id=t["chat_id"], message_id=first_id, entities=entities)
            else:
                await bot.edit_message_caption(
                    chat_id=t["chat_id"], message_id=first_id, caption=new_text, caption_entities=entities
                )
            updated += 1
        except Exception as e:
            logger.warning("Live edit failed for target %s: %s", t["target_id"], e)
            failed += 1

    await state.clear()

    reply = f"✅ Текст обновлён.\nУже опубликованные посты обновлены: {updated}."
    if failed:
        reply += f"\n⚠️ Не удалось обновить {failed} шт. (например, сообщение уже удалено вручную)."
    reply += "\n\nЗапланированные, ещё не опубликованные посты выйдут уже с новым текстом."
    await message.answer(reply)


# ---------- удаление поста: везде или из одного канала ----------

@router.callback_query(F.data.startswith("delpost:"))
async def ask_delete_scope(callback: CallbackQuery):
    post_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        await callback.answer("Пост не найден", show_alert=True)
        return

    targets = await db.get_targets_for_post(post_id)
    active = [t for t in targets if t["status"] in ("scheduled", "published")]
    if not active:
        await callback.answer("Пост уже нигде не активен.", show_alert=True)
        return

    if len(active) == 1:
        await _delete_targets(callback, post_id, [active[0]["target_id"]])
        return

    b = InlineKeyboardBuilder()
    b.button(text=f"🗑 Удалить везде ({len(active)})", callback_data=f"delall:{post_id}")
    for t in active:
        b.button(text=f"📍 Только «{t['title']}»", callback_data=f"delone:{post_id}:{t['target_id']}")
    b.button(text="⬅️ Назад", callback_data=f"editpost:{post_id}")
    b.adjust(1)
    await callback.message.edit_text("Где удалить пост?", reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("delall:"))
async def delete_all(callback: CallbackQuery):
    post_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        await callback.answer("Пост не найден", show_alert=True)
        return

    targets = await db.get_targets_for_post(post_id)
    ids = [t["target_id"] for t in targets if t["status"] in ("scheduled", "published")]
    await _delete_targets(callback, post_id, ids)


@router.callback_query(F.data.startswith("delone:"))
async def delete_one(callback: CallbackQuery):
    _, post_id_str, target_id_str = callback.data.split(":")
    post_id, target_id = int(post_id_str), int(target_id_str)
    user_id = await db.get_or_create_user(callback.from_user.id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        await callback.answer("Пост не найден", show_alert=True)
        return
    await _delete_targets(callback, post_id, [target_id])


async def _delete_targets(callback: CallbackQuery, post_id: int, target_ids: list[int]):
    bot = callback.bot
    targets = await db.get_targets_for_post(post_id)
    by_id = {t["target_id"]: t for t in targets}

    removed = 0
    for tid in target_ids:
        t = by_id.get(tid)
        if not t:
            continue
        if t["status"] == "published" and t["message_ids"]:
            for mid in t["message_ids"]:
                try:
                    await bot.delete_message(t["chat_id"], mid)
                except Exception as e:
                    logger.warning("Manual delete failed target %s msg %s: %s", tid, mid, e)
        await db.mark_deleted(tid)
        removed += 1

    await callback.message.edit_text(f"🗑 Удалено: {removed} шт.")
    await callback.answer()
