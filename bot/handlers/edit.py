import html as html_lib
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import db
from bot import ui
from bot.i18n import t, get_user_lang
from bot.tzutil import get_user_tz
from bot.states import EditPost
from bot.entities_util import serialize_entities, deserialize_entities
from bot.keyboards import home_button

router = Router()
logger = logging.getLogger(__name__)


def _plain_preview(text: str | None, lang: str, length: int = 40) -> str:
    if not text:
        return t(lang, "post.no_text")
    plain = text.strip() or t(lang, "post.no_text")
    return plain[:length] + ("…" if len(plain) > length else "")


@router.message(Command("myposts"))
async def cmd_myposts(message: Message):
    user_id = await db.get_or_create_user(message.from_user.id)
    lang = await get_user_lang(user_id)
    posts = await db.list_user_posts(user_id)
    await ui.clear_previous(message.bot, message.chat.id, user_id)
    if not posts:
        sent = await message.answer(t(lang, "myposts.none"))
        await ui.track(user_id, sent)
        return

    b = InlineKeyboardBuilder()
    for p in posts:
        preview = _plain_preview(p["text"], lang)
        status = f"{p['published_count']}/{p['targets_count']}"
        b.button(text=f"#{p['id']} [{p['media_type']}] {preview} — {status}", callback_data=f"editpost:{p['id']}")
    b.adjust(1)
    b.row(home_button(lang))
    sent = await message.answer(t(lang, "myposts.header"), reply_markup=b.as_markup())
    await ui.track(user_id, sent)


@router.callback_query(F.data.startswith("editpost:"))
async def show_post(callback: CallbackQuery):
    post_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    lang = await get_user_lang(user_id)
    tz = await get_user_tz(user_id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        await callback.answer(t(lang, "myposts.not_found"), show_alert=True)
        return

    targets = await db.get_targets_for_post(post_id)
    if all(tt["status"] == "deleted" for tt in targets):
        b = InlineKeyboardBuilder()
        b.row(home_button(lang))
        await callback.message.edit_text(t(lang, "post.deleted_everywhere", id=post_id), reply_markup=b.as_markup())
        await callback.answer()
        return

    lines = [
        f"<b>Пост #{post_id}</b> ({html_lib.escape(post['media_type'] or '')})",
        "",
        html_lib.escape(post["text"]) if post["text"] else f"<i>{t(lang, 'post.no_text')}</i>",
        "",
        f"<b>{t(lang, 'post.channels_header')}</b>",
    ]
    status_key = {"scheduled": "status.scheduled", "published": "status.published", "deleted": "status.deleted", "failed": "status.failed"}
    for tt in targets:
        line = f"• {html_lib.escape(tt['title'])} — {t(lang, status_key.get(tt['status'], tt['status']))}"
        if tt["status"] == "scheduled" and tt["publish_at"]:
            local_dt = tt["publish_at"].astimezone(tz)
            date_str = local_dt.strftime("%d.%m.%Y")
            time_str = local_dt.strftime("%H:%M")
            tz_abbr = local_dt.tzname() or ""
            line += f" ({date_str} {t(lang, 'post.at')} {time_str} ({tz_abbr}))"
        if tt["status"] == "failed" and tt["error"]:
            line += f"\n   <code>{html_lib.escape(tt['error'][:200])}</code>"
        lines.append(line)

    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "btn.edit_text"), callback_data=f"edittext:{post_id}")
    b.button(text=t(lang, "btn.delete_post"), callback_data=f"delpost:{post_id}")
    b.adjust(1)
    b.row(home_button(lang))

    await callback.message.edit_text("\n".join(lines), reply_markup=b.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("edittext:"))
async def ask_new_text(callback: CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    lang = await get_user_lang(user_id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        await callback.answer(t(lang, "myposts.not_found"), show_alert=True)
        return

    await state.set_state(EditPost.waiting_text)
    await state.update_data(edit_post_id=post_id)

    hint = t(lang, "edittext.hint_media") if post["media_type"] in ("photo", "video", "album") else t(lang, "edittext.hint_text")
    b = InlineKeyboardBuilder()
    b.row(home_button(lang))
    await callback.message.edit_text(t(lang, "edittext.prompt", hint=hint), reply_markup=b.as_markup())
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
    errors = []
    for tt in targets:
        if tt["status"] != "published" or not tt["message_ids"]:
            continue
        first_id = tt["message_ids"][0]
        try:
            if post["media_type"] == "text":
                await bot.edit_message_text(
                    new_text, chat_id=tt["chat_id"], message_id=first_id, entities=entities, parse_mode=None
                )
            else:
                await bot.edit_message_caption(
                    chat_id=tt["chat_id"], message_id=first_id, caption=new_text,
                    caption_entities=entities, parse_mode=None,
                )
            updated += 1
        except Exception as e:
            logger.warning("Live edit failed for target %s: %s", tt["target_id"], e)
            errors.append(f"{tt['title']}: {e}")
            failed += 1

    await state.clear()

    user_id = await db.get_or_create_user(message.from_user.id)
    lang = await get_user_lang(user_id)

    reply = t(lang, "edittext.updated", updated=updated)
    if failed:
        reply += t(lang, "edittext.failed", failed=failed, errors="\n".join(errors[:5]))
    reply += t(lang, "edittext.scheduled_note")

    await ui.clear_previous(bot, message.chat.id, user_id)
    sent = await message.answer(reply)
    await ui.track(user_id, sent)


# ---------- удаление поста: везде или из одного канала ----------

@router.callback_query(F.data.startswith("delpost:"))
async def ask_delete_scope(callback: CallbackQuery):
    post_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    lang = await get_user_lang(user_id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        await callback.answer(t(lang, "myposts.not_found"), show_alert=True)
        return

    targets = await db.get_targets_for_post(post_id)
    active = [tt for tt in targets if tt["status"] != "deleted"]
    if not active:
        await callback.answer(t(lang, "delete.nowhere_active"), show_alert=True)
        return

    if len(active) == 1:
        await _delete_targets(callback, post_id, [active[0]["target_id"]], lang)
        return

    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "btn.delete_everywhere", n=len(active)), callback_data=f"delall:{post_id}")
    for tt in active:
        b.button(text=t(lang, "btn.only_channel", title=tt["title"]), callback_data=f"delone:{post_id}:{tt['target_id']}")
    b.button(text=t(lang, "btn.back_short"), callback_data=f"editpost:{post_id}")
    b.adjust(1)
    b.row(home_button(lang))
    await callback.message.edit_text(t(lang, "delete.where"), reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("delall:"))
async def delete_all(callback: CallbackQuery):
    post_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    lang = await get_user_lang(user_id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        await callback.answer(t(lang, "myposts.not_found"), show_alert=True)
        return

    targets = await db.get_targets_for_post(post_id)
    ids = [tt["target_id"] for tt in targets if tt["status"] != "deleted"]
    await _delete_targets(callback, post_id, ids, lang)


@router.callback_query(F.data.startswith("delone:"))
async def delete_one(callback: CallbackQuery):
    _, post_id_str, target_id_str = callback.data.split(":")
    post_id, target_id = int(post_id_str), int(target_id_str)
    user_id = await db.get_or_create_user(callback.from_user.id)
    lang = await get_user_lang(user_id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        await callback.answer(t(lang, "myposts.not_found"), show_alert=True)
        return
    await _delete_targets(callback, post_id, [target_id], lang)


async def _delete_targets(callback: CallbackQuery, post_id: int, target_ids: list[int], lang: str):
    bot = callback.bot
    targets = await db.get_targets_for_post(post_id)
    by_id = {tt["target_id"]: tt for tt in targets}

    removed = 0
    for tid in target_ids:
        tt = by_id.get(tid)
        if not tt:
            continue
        if tt["status"] == "published" and tt["message_ids"]:
            for mid in tt["message_ids"]:
                try:
                    await bot.delete_message(tt["chat_id"], mid)
                except Exception as e:
                    logger.warning("Manual delete failed target %s msg %s: %s", tid, mid, e)
        await db.mark_deleted(tid)
        removed += 1

    b = InlineKeyboardBuilder()
    b.row(home_button(lang))
    await callback.message.edit_text(t(lang, "delete.done", n=removed), reply_markup=b.as_markup())
    await callback.answer()
