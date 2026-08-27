import html as html_lib
import json
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InputMediaVideo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import db
from bot import ui
from bot.i18n import t, get_user_lang
from bot.tzutil import get_user_tz
from bot.states import EditPost
from bot.entities_util import serialize_entities, deserialize_entities
from bot.keyboards import home_button, link_buttons_only_markup
from bot.handlers.posts import parse_link_buttons
from bot.scheduler import _delete_comment_mirror

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
        if p["scheduled_count"] > 0:
            status_emoji = "⏰"
        elif p["published_count"] > 0:
            status_emoji = "✅"
        else:
            status_emoji = "⚠️"
        b.button(text=f"{status_emoji} {preview}", callback_data=f"editpost:{p['id']}")
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
    if post["media_type"] != "album":
        b.button(text=t(lang, "btn.edit_buttons"), callback_data=f"editbuttons:{post_id}")
    if post["media_type"] in ("photo", "video"):
        b.button(text=t(lang, "btn.edit_media"), callback_data=f"editmedia:{post_id}")
    b.button(text=t(lang, "btn.delete_post"), callback_data=f"delpost:{post_id}")
    b.adjust(1)
    b.row(home_button(lang))

    await callback.message.edit_text("\n".join(lines), reply_markup=b.as_markup(), parse_mode="HTML")
    await callback.answer()


# ---------- редактирование текста ----------

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

    await ui.delete_user_message(message)
    await ui.clear_previous(bot, message.chat.id, user_id)
    sent = await message.answer(reply)
    await ui.track(user_id, sent)


# ---------- редактирование кнопок-ссылок ----------

@router.callback_query(F.data.startswith("editbuttons:"))
async def ask_new_buttons(callback: CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    lang = await get_user_lang(user_id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        await callback.answer(t(lang, "myposts.not_found"), show_alert=True)
        return
    if post["media_type"] == "album":
        await callback.answer(t(lang, "editbuttons.not_for_album"), show_alert=True)
        return

    await state.set_state(EditPost.waiting_buttons)
    await state.update_data(edit_post_id=post_id)

    current_lines = []
    if post["button_json"]:
        try:
            for row in json.loads(post["button_json"]):
                current_lines.append(" | ".join(f"{btn['text']} - {btn['url']}" for btn in row))
        except Exception:
            current_lines = []
    current_block = "\n".join(html_lib.escape(line) for line in current_lines) if current_lines else t(lang, "editbuttons.none")

    b = InlineKeyboardBuilder()
    b.row(home_button(lang))
    await callback.message.edit_text(
        f"{t(lang, 'editbuttons.current_header')}\n{current_block}\n\n{t(lang, 'editbuttons.prompt')}",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.message(EditPost.waiting_buttons)
async def apply_new_buttons(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    post_id = data["edit_post_id"]
    user_id = await db.get_or_create_user(message.from_user.id)
    lang = await get_user_lang(user_id)

    raw = (message.text or "").strip()
    if raw in ("-", "0"):
        rows = None
    else:
        rows, bad_part = parse_link_buttons(raw)
        if rows is None:
            hint = t(lang, "newpost.link_buttons_bad_part", part=html_lib.escape(bad_part)) if bad_part else ""
            await message.answer(t(lang, "newpost.link_buttons_bad_format", hint=hint))
            return

    button_json = json.dumps(rows) if rows else None
    await db.update_post_buttons(post_id, button_json)

    targets = await db.get_targets_for_post(post_id)
    markup = link_buttons_only_markup(rows)

    updated, failed = 0, 0
    for tt in targets:
        if tt["status"] != "published" or not tt["message_ids"]:
            continue
        first_id = tt["message_ids"][0]
        try:
            await bot.edit_message_reply_markup(chat_id=tt["chat_id"], message_id=first_id, reply_markup=markup)
            updated += 1
        except Exception as e:
            logger.warning("Live button update failed for target %s: %s", tt["target_id"], e)
            failed += 1

    await state.clear()
    await ui.delete_user_message(message)

    reply = t(lang, "editbuttons.updated", updated=updated)
    if failed:
        reply += t(lang, "editbuttons.failed", failed=failed)

    await ui.clear_previous(bot, message.chat.id, user_id)
    sent = await message.answer(reply)
    await ui.track(user_id, sent)


# ---------- замена медиа ----------

@router.callback_query(F.data.startswith("editmedia:"))
async def ask_new_media(callback: CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    lang = await get_user_lang(user_id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        await callback.answer(t(lang, "myposts.not_found"), show_alert=True)
        return
    if post["media_type"] not in ("photo", "video"):
        await callback.answer(t(lang, "editmedia.not_supported"), show_alert=True)
        return

    await state.set_state(EditPost.waiting_media)
    await state.update_data(edit_post_id=post_id)

    b = InlineKeyboardBuilder()
    b.row(home_button(lang))
    await callback.message.edit_text(t(lang, "editmedia.prompt"), reply_markup=b.as_markup())
    await callback.answer()


@router.message(EditPost.waiting_media, F.photo | F.video)
async def apply_new_media(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    post_id = data["edit_post_id"]
    user_id = await db.get_or_create_user(message.from_user.id)
    lang = await get_user_lang(user_id)

    if message.photo:
        media_type, file_id = "photo", message.photo[-1].file_id
    else:
        media_type, file_id = "video", message.video.file_id

    await db.update_post_media(post_id, file_id, media_type)

    post = await db.get_post(post_id)
    targets = await db.get_targets_for_post(post_id)
    entities = deserialize_entities(post["entities_json"])
    button_rows = json.loads(post["button_json"]) if post["button_json"] else None
    markup = link_buttons_only_markup(button_rows)

    updated, failed = 0, 0
    for tt in targets:
        if tt["status"] != "published" or not tt["message_ids"]:
            continue
        first_id = tt["message_ids"][0]
        try:
            cls = InputMediaPhoto if media_type == "photo" else InputMediaVideo
            new_media = cls(media=file_id, caption=post["text"], caption_entities=entities)
            await bot.edit_message_media(chat_id=tt["chat_id"], message_id=first_id, media=new_media, reply_markup=markup)
            updated += 1
        except Exception as e:
            logger.warning("Live media update failed for target %s: %s", tt["target_id"], e)
            failed += 1

    await state.clear()
    await ui.delete_user_message(message)

    reply = t(lang, "editmedia.updated", updated=updated)
    if failed:
        reply += t(lang, "editmedia.failed", failed=failed)

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
    user_id = await db.get_or_create_user(callback.from_user.id)
    user = await db.get_user(user_id)
    delete_from_comments = bool(user and user["delete_from_comments"])

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
                if delete_from_comments:
                    await _delete_comment_mirror(bot, tt["chat_id"], mid)
        await db.mark_deleted(tid)
        removed += 1

    b = InlineKeyboardBuilder()
    b.row(home_button(lang))
    await callback.message.edit_text(t(lang, "delete.done", n=removed), reply_markup=b.as_markup())
    await callback.answer()
