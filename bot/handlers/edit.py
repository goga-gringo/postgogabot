import asyncio
import html as html_lib
import json
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InputMediaVideo, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.text_decorations import html_decoration

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
    tz = await get_user_tz(user_id)
    posts = await db.list_user_posts(user_id)
    await ui.clear_previous(message.bot, message.chat.id, user_id)
    if not posts:
        sent = await message.answer(t(lang, "myposts.none"))
        await ui.track(user_id, sent)
        return

    b = InlineKeyboardBuilder()
    for p in posts:
        preview = _plain_preview(p["text"], lang)
        date_str = p["created_at"].astimezone(tz).strftime("%d.%m %H:%M")
        if p["scheduled_count"] > 0:
            status_emoji = "⏰"
        elif p["published_count"] > 0:
            status_emoji = "✅"
        else:
            status_emoji = "⚠️"
        b.button(text=f"{date_str} {status_emoji} {preview}", callback_data=f"editpost:{p['id']}")
    b.adjust(1)
    b.row(home_button(lang))
    sent = await message.answer(t(lang, "myposts.header"), reply_markup=b.as_markup())
    await ui.track(user_id, sent)


async def _build_post_view(post_id: int, user_id: int, lang: str):
    """Собирает (post, targets, текст/подпись, клавиатуру) для карточки поста.
    Возвращает None вместо post, если пост не найден/чужой."""
    tz = await get_user_tz(user_id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        return None, None, None, None

    targets = await db.get_targets_for_post(post_id)

    lines = [
        f"<b>Пост #{post_id}</b>",
        "",
        html_decoration.unparse(post["text"], deserialize_entities(post["entities_json"]))
        if post["text"] else f"<i>{t(lang, 'post.no_text')}</i>",
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

    text = "\n".join(lines)

    b = InlineKeyboardBuilder()
    button_rows = json.loads(post["button_json"]) if post["button_json"] else None
    for row in (button_rows or []):
        b.row(*[InlineKeyboardButton(text=btn["text"], url=btn["url"]) for btn in row])

    b.button(text=t(lang, "btn.edit_text"), callback_data=f"edittext:{post_id}")
    if post["media_type"] != "album":
        b.button(text=t(lang, "btn.edit_buttons"), callback_data=f"editbuttons:{post_id}")
    if post["media_type"] in ("photo", "video", "album"):
        b.button(text=t(lang, "btn.edit_media"), callback_data=f"editmedia:{post_id}")
    b.button(text=t(lang, "btn.delete_post"), callback_data=f"delpost:{post_id}")
    b.adjust(1)
    b.row(home_button(lang))

    return post, targets, text, b.as_markup()


async def _render_post(bot: Bot, chat_id: int, user_id: int, post_id: int, lang: str):
    """Показывает карточку поста — с реальным фото/видео, если оно есть
    (через file_id, сервер бота файл не хранит). Удаляет прошлый экран
    и присылает свежий, чтобы не зависеть от того, был ли он текстом или медиа."""
    post, targets, text, kb = await _build_post_view(post_id, user_id, lang)
    if post is None:
        return False

    await ui.clear_previous(bot, chat_id, user_id)

    if all(tt["status"] == "deleted" for tt in targets):
        b = InlineKeyboardBuilder()
        b.row(home_button(lang))
        sent = await bot.send_message(chat_id, t(lang, "post.deleted_everywhere", id=post_id), reply_markup=b.as_markup())
        await ui.track(user_id, sent)
        return True

    sent_messages = []
    try:
        if post["media_type"] == "photo":
            sent = await bot.send_photo(chat_id, post["file_id"], caption=text, parse_mode="HTML", reply_markup=kb)
        elif post["media_type"] == "video":
            sent = await bot.send_video(chat_id, post["file_id"], caption=text, parse_mode="HTML", reply_markup=kb)
        else:
            sent = await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)
        sent_messages = [sent]
    except Exception as e:
        # Скорее всего текст не влез в лимит подписи (1024 символа у фото/видео) —
        # НЕ обрезаем HTML вручную (можно перерезать тег пополам и получить битую
        # разметку), а показываем медиа без подписи + текст отдельным сообщением
        # (там лимит уже 4096, риска почти нет).
        logger.warning("Caption send failed for post %s (media_type=%s), splitting: %s", post_id, post["media_type"], e)
        try:
            if post["media_type"] == "photo":
                media_sent = await bot.send_photo(chat_id, post["file_id"])
                status_sent = await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)
                sent_messages = [media_sent, status_sent]
            elif post["media_type"] == "video":
                media_sent = await bot.send_video(chat_id, post["file_id"])
                status_sent = await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)
                sent_messages = [media_sent, status_sent]
            else:
                # Текстовый пост — тут уже сам лимит 4096 виноват (огромный текст),
                # в этом случае безопасно режем ПРОСТОЙ (экранированный) текст без разметки.
                status_sent = await bot.send_message(chat_id, html_lib.escape(text)[:3900], reply_markup=kb)
                sent_messages = [status_sent]
        except Exception as e2:
            logger.exception("Fallback render also failed for post %s: %s", post_id, e2)
            return False

    await ui.track(user_id, sent_messages)
    return True


@router.callback_query(F.data.startswith("editpost:"))
async def show_post(callback: CallbackQuery):
    post_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    lang = await get_user_lang(user_id)

    try:
        ok = await _render_post(callback.bot, callback.message.chat.id, user_id, post_id, lang)
    except Exception as e:
        logger.exception("show_post crashed for post %s user %s: %s", post_id, user_id, e)
        await callback.answer("⚠️ Ошибка при отображении поста, попробуй ещё раз", show_alert=True)
        return

    if not ok:
        await callback.answer(t(lang, "myposts.not_found"), show_alert=True)
        return
    await callback.answer()


async def _send_prompt(bot: Bot, chat_id: int, user_id: int, text: str, reply_markup=None):
    """Небольшая текстовая подсказка поверх карточки поста — убираем
    предыдущий экран (не важно, текст он или медиа) и шлём свежий."""
    await ui.clear_previous(bot, chat_id, user_id)
    sent = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    await ui.track(user_id, sent)


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
    await _send_prompt(callback.bot, callback.message.chat.id, user_id, t(lang, "edittext.prompt", hint=hint), b.as_markup())
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
    await _send_prompt(bot, message.chat.id, user_id, reply)


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
    text = f"{t(lang, 'editbuttons.current_header')}\n{current_block}\n\n{t(lang, 'editbuttons.prompt')}"
    await _send_prompt(callback.bot, callback.message.chat.id, user_id, text, b.as_markup())
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

    await _send_prompt(bot, message.chat.id, user_id, reply)


# ---------- замена медиа ----------

_edit_album_buffers: dict[str, list[Message]] = {}
EDIT_ALBUM_WAIT_SECONDS = 1.3


@router.callback_query(F.data.startswith("editmedia:"))
async def ask_new_media(callback: CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split(":")[1])
    user_id = await db.get_or_create_user(callback.from_user.id)
    lang = await get_user_lang(user_id)
    post = await db.get_post(post_id)
    if not post or post["owner_id"] != user_id:
        await callback.answer(t(lang, "myposts.not_found"), show_alert=True)
        return
    if post["media_type"] not in ("photo", "video", "album"):
        await callback.answer(t(lang, "editmedia.not_supported"), show_alert=True)
        return

    await state.set_state(EditPost.waiting_media)
    await state.update_data(edit_post_id=post_id)

    prompt_key = "editmedia.album_prompt" if post["media_type"] == "album" else "editmedia.prompt"
    b = InlineKeyboardBuilder()
    b.row(home_button(lang))
    await _send_prompt(callback.bot, callback.message.chat.id, user_id, t(lang, prompt_key), b.as_markup())
    await callback.answer()


@router.message(EditPost.waiting_media, (F.photo | F.video) & ~F.media_group_id)
async def apply_new_media_single(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    post_id = data["edit_post_id"]
    post = await db.get_post(post_id)

    if message.photo:
        item_type, file_id = "photo", message.photo[-1].file_id
    else:
        item_type, file_id = "video", message.video.file_id

    if post["media_type"] == "album":
        # Заменяем альбом одним элементом — остаётся альбомом (пусть и из одной штуки),
        # чтобы логика публикации (post_media) не путалась.
        reply = await _apply_album_replacement(bot, post_id, [{"type": item_type, "file_id": file_id}])
    else:
        await db.update_post_media(post_id, file_id, item_type)
        reply = await _apply_single_media_live_update(bot, post_id, item_type, file_id)

    await state.clear()
    await ui.delete_user_message(message)
    user_id = await db.get_or_create_user(message.from_user.id)
    await _send_prompt(bot, message.chat.id, user_id, reply)


@router.message(EditPost.waiting_media, F.media_group_id)
async def apply_new_media_album_part(message: Message, state: FSMContext, bot: Bot):
    gid = message.media_group_id
    buf = _edit_album_buffers.setdefault(gid, [])
    buf.append(message)
    if len(buf) == 1:
        asyncio.create_task(_process_edit_album(gid, state, bot))


async def _process_edit_album(gid: str, state: FSMContext, bot: Bot):
    await asyncio.sleep(EDIT_ALBUM_WAIT_SECONDS)
    messages = _edit_album_buffers.pop(gid, [])
    if not messages:
        return
    messages.sort(key=lambda m: m.message_id)

    items = []
    for m in messages:
        if m.photo:
            items.append({"type": "photo", "file_id": m.photo[-1].file_id})
        elif m.video:
            items.append({"type": "video", "file_id": m.video.file_id})
    if not items:
        return

    data = await state.get_data()
    post_id = data["edit_post_id"]
    reply = await _apply_album_replacement(bot, post_id, items)

    await state.clear()
    chat_id = messages[0].chat.id
    for m in messages:
        await ui.delete_user_message(m)
    user_id = await db.get_or_create_user(messages[0].from_user.id)
    await _send_prompt(bot, chat_id, user_id, reply)


async def _apply_single_media_live_update(bot: Bot, post_id: int, media_type: str, file_id: str) -> str:
    """Обновляет уже опубликованные посты 'вживую' и возвращает готовый текст отчёта."""
    post = await db.get_post(post_id)
    targets = await db.get_targets_for_post(post_id)
    lang = await get_user_lang(post["owner_id"])
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
            new_media = cls(media=file_id, caption=post["text"], caption_entities=entities, parse_mode=None)
            await bot.edit_message_media(chat_id=tt["chat_id"], message_id=first_id, media=new_media, reply_markup=markup)
            updated += 1
        except Exception as e:
            logger.warning("Live media update failed for target %s: %s", tt["target_id"], e)
            failed += 1

    reply = t(lang, "editmedia.updated", updated=updated)
    if failed:
        reply += t(lang, "editmedia.failed", failed=failed)
    return reply


async def _apply_album_replacement(bot: Bot, post_id: int, items: list[dict]) -> str:
    """Заменяет элементы альбома в БД, пробует обновить уже опубликованные посты
    'вживую' (только там, где число фото/видео совпадает с прежним — Telegram не
    позволяет менять размер уже готового альбома через editMessageMedia) и
    возвращает готовый текст отчёта."""
    await db.replace_album_items(post_id, items)

    post = await db.get_post(post_id)
    targets = await db.get_targets_for_post(post_id)
    lang = await get_user_lang(post["owner_id"])
    entities = deserialize_entities(post["entities_json"])

    updated, failed, mismatched = 0, 0, 0
    for tt in targets:
        if tt["status"] != "published" or not tt["message_ids"]:
            continue
        if len(tt["message_ids"]) != len(items):
            mismatched += 1
            continue
        ok = True
        for idx, (mid, item) in enumerate(zip(tt["message_ids"], items)):
            try:
                cls = InputMediaPhoto if item["type"] == "photo" else InputMediaVideo
                kwargs = {"parse_mode": None}
                if idx == 0 and post["text"]:
                    kwargs["caption"] = post["text"]
                    kwargs["caption_entities"] = entities
                new_media = cls(media=item["file_id"], **kwargs)
                await bot.edit_message_media(chat_id=tt["chat_id"], message_id=mid, media=new_media)
            except Exception as e:
                logger.warning("Live album item update failed for target %s msg %s: %s", tt["target_id"], mid, e)
                ok = False
        if ok:
            updated += 1
        else:
            failed += 1

    reply = t(lang, "editmedia.updated", updated=updated)
    if failed:
        reply += t(lang, "editmedia.failed", failed=failed)
    if mismatched:
        reply += t(lang, "editmedia.mismatch", n=mismatched)
    return reply


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
        await _delete_targets(callback.bot, callback.message.chat.id, user_id, post_id, [active[0]["target_id"]], lang)
        await callback.answer()
        return

    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "btn.delete_everywhere", n=len(active)), callback_data=f"delall:{post_id}")
    for tt in active:
        b.button(text=t(lang, "btn.only_channel", title=tt["title"]), callback_data=f"delone:{post_id}:{tt['target_id']}")
    b.button(text=t(lang, "btn.back_short"), callback_data=f"editpost:{post_id}")
    b.adjust(1)
    b.row(home_button(lang))
    await _send_prompt(callback.bot, callback.message.chat.id, user_id, t(lang, "delete.where"), b.as_markup())
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
    await _delete_targets(callback.bot, callback.message.chat.id, user_id, post_id, ids, lang)
    await callback.answer()


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
    await _delete_targets(callback.bot, callback.message.chat.id, user_id, post_id, [target_id], lang)
    await callback.answer()


async def _delete_targets(bot: Bot, chat_id: int, user_id: int, post_id: int, target_ids: list[int], lang: str):
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
    await _send_prompt(bot, chat_id, user_id, t(lang, "delete.done", n=removed), b.as_markup())
