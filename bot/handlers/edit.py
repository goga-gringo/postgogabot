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
