import asyncio
import html
import json
import logging
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InputMediaVideo

from bot import db
from bot import ui
from bot.i18n import t, get_user_lang
from bot.tzutil import get_user_tz, get_user_tz_name
from bot.states import NewPost
from bot.entities_util import serialize_entities, deserialize_entities
from bot.keyboards import channels_keyboard, delete_after_keyboard, preview_keyboard, back_only_keyboard

router = Router()
logger = logging.getLogger(__name__)

# Сбор альбомов: Telegram присылает медиагруппу как несколько отдельных апдейтов
# подряд — собираем их в буфер и обрабатываем одним постом через небольшую паузу.
# Два отдельных буфера: контент уже после выбора каналов, и контент, присланный
# ДО того как каналы выбраны (тогда он идёт в 'pending_content' и ждёт).
ALBUM_WAIT_SECONDS = 1.3
_album_buffers: dict[str, list[Message]] = {}
_pending_album_buffers: dict[str, list[Message]] = {}


def _delete_after_label(hours: int | None, lang: str) -> str:
    return t(lang, "newpost.delete_never") if not hours else t(lang, "newpost.delete_in_hours", h=hours)


def parse_link_buttons(text: str):
    """'Текст - ссылка' построчно, несколько кнопок в строке через '|'.
    Если ссылка без схемы (например t.me/...) — подставляем https:// сама.
    Возвращает (rows, None) при успехе или (None, offending_part) при ошибке."""
    rows = []
    for line in (text or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        row = []
        for part in line.split("|"):
            part = part.strip()
            if " - " not in part:
                return None, part
            label, url = part.split(" - ", 1)
            label, url = label.strip(), url.strip()
            if not label or not url:
                return None, part
            if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
                if " " in url or "." not in url:
                    return None, part
                url = "https://" + url
            row.append({"text": label, "url": url})
        if row:
            rows.append(row)
    if not rows:
        return None, None
    return rows, None


def _extract_url_buttons(reply_markup):
    """Если у входящего сообщения (например, пересланного поста) уже была
    инлайн-клавиатура — вытаскиваем из неё только кнопки-ссылки (url), чтобы
    сохранить их в новом посте. Кнопки с callback_data пропускаем — они всё
    равно ведут на чужого бота и не будут работать."""
    if not reply_markup or not getattr(reply_markup, "inline_keyboard", None):
        return None
    rows = []
    for row in reply_markup.inline_keyboard:
        r = [{"text": btn.text, "url": btn.url} for btn in row if btn.url]
        if r:
            rows.append(r)
    return rows or None


def _content_fields_from_single(message: Message) -> dict:
    """Собираем поля контента из одиночного сообщения (фото/видео/текст)."""
    if message.photo:
        media_type, file_id = "photo", message.photo[-1].file_id
        text, entities_json = message.caption, serialize_entities(message.caption_entities)
    elif message.video:
        media_type, file_id = "video", message.video.file_id
        text, entities_json = message.caption, serialize_entities(message.caption_entities)
    else:
        media_type, file_id = "text", None
        text, entities_json = message.text, serialize_entities(message.entities)

    return {
        "media_type": media_type,
        "file_id": file_id,
        "text": text,
        "entities_json": entities_json,
        "album_items": None,
        "source_chat_id": message.chat.id,
        "source_message_ids": [message.message_id],
        "link_buttons": _extract_url_buttons(message.reply_markup),
    }


def _collect_album_items(messages: list[Message]):
    items = []
    caption_text = None
    caption_entities_json = None
    for m in messages:
        if m.photo:
            items.append({"type": "photo", "file_id": m.photo[-1].file_id})
        elif m.video:
            items.append({"type": "video", "file_id": m.video.file_id})
        if m.caption and not caption_text:
            caption_text = m.caption
            caption_entities_json = serialize_entities(m.caption_entities)
    return items, caption_text, caption_entities_json


def _content_fields_from_album(messages: list[Message]) -> dict | None:
    items, caption_text, caption_entities_json = _collect_album_items(messages)
    if not items:
        return None
    return {
        "media_type": "album",
        "file_id": None,
        "text": caption_text,
        "entities_json": caption_entities_json,
        "album_items": items,
        "source_chat_id": messages[0].chat.id,
        "source_message_ids": [m.message_id for m in messages],
        "link_buttons": None,
    }


# ---------- запуск сценария: сначала выбор каналов ----------

async def start_new_post(message: Message, state: FSMContext, from_user_id: int):
    user_id = await db.get_or_create_user(from_user_id)
    lang = await get_user_lang(user_id)
    channels = await db.list_channels(user_id)
    if not channels:
        await message.answer(t(lang, "newpost.no_channels"))
        return

    await ui.clear_previous(message.bot, message.chat.id, user_id)
    await state.update_data(selected_channels=[], user_id=user_id, pending_content=None)
    await state.set_state(NewPost.choosing_channels)
    sent = await message.answer(
        t(lang, "newpost.choose_channels"),
        reply_markup=channels_keyboard(channels, set(), lang),
    )
    await ui.track(user_id, sent)


@router.callback_query(NewPost.choosing_channels, F.data.startswith("ch:"))
async def toggle_channel(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    lang = await get_user_lang(data["user_id"])
    selected = set(data.get("selected_channels", []))
    if channel_id in selected:
        selected.discard(channel_id)
    else:
        selected.add(channel_id)
    await state.update_data(selected_channels=list(selected))

    channels = await db.list_channels(data["user_id"])
    await callback.message.edit_reply_markup(reply_markup=channels_keyboard(channels, selected, lang))
    await callback.answer()


@router.callback_query(NewPost.choosing_channels, F.data == "toggle_all")
async def toggle_all_channels(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = await get_user_lang(data["user_id"])
    channels = await db.list_channels(data["user_id"])
    all_ids = {c["id"] for c in channels}
    selected = set(data.get("selected_channels", []))
    selected = set() if selected == all_ids else set(all_ids)
    await state.update_data(selected_channels=list(selected))
    await callback.message.edit_reply_markup(reply_markup=channels_keyboard(channels, selected, lang))
    await callback.answer()


@router.callback_query(NewPost.choosing_channels, F.data == "channels_done")
async def channels_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = await get_user_lang(data["user_id"])
    if not data.get("selected_channels"):
        await callback.answer(t(lang, "newpost.select_at_least_one"), show_alert=True)
        return

    pending = data.get("pending_content")
    if pending:
        # Контент уже прислали до того, как выбрали каналы — не спрашиваем повторно.
        await state.update_data(**pending, pending_content=None)
        await callback.message.edit_text(t(lang, "newpost.channels_selected_using_pending"))
        await _go_to_delete_after(callback.message, state)
        await callback.answer()
        return

    await state.set_state(NewPost.waiting_content)
    await callback.message.edit_text(t(lang, "newpost.channels_selected_send_content"))
    await callback.answer()


# Прислали контент, ещё не выбрав каналы — запоминаем его (чтобы не спрашивать
# повторно) и напоминаем выбрать каналы.

@router.message(NewPost.choosing_channels, F.media_group_id)
async def album_before_channels(message: Message, state: FSMContext, bot: Bot):
    gid = message.media_group_id
    buf = _pending_album_buffers.setdefault(gid, [])
    buf.append(message)
    if len(buf) == 1:
        asyncio.create_task(_process_pending_album(gid, state, bot))


async def _process_pending_album(gid: str, state: FSMContext, bot: Bot):
    await asyncio.sleep(ALBUM_WAIT_SECONDS)
    messages = _pending_album_buffers.pop(gid, [])
    if not messages:
        return
    messages.sort(key=lambda m: m.message_id)
    fields = _content_fields_from_album(messages)
    if not fields:
        return

    await state.update_data(pending_content=fields)
    data = await state.get_data()
    user_id = data["user_id"]
    lang = await get_user_lang(user_id)
    channels = await db.list_channels(user_id)
    selected = set(data.get("selected_channels", []))

    chat_id = messages[0].chat.id
    await ui.clear_previous(bot, chat_id, user_id)
    sent = await bot.send_message(
        chat_id,
        t(lang, "newpost.pending_album_prompt", n=len(fields["album_items"])),
        reply_markup=channels_keyboard(channels, selected, lang),
    )
    await ui.track(user_id, sent)


@router.message(NewPost.choosing_channels)
async def content_before_channels(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        return

    fields = _content_fields_from_single(message)
    await state.update_data(pending_content=fields)

    data = await state.get_data()
    user_id = data["user_id"]
    lang = await get_user_lang(user_id)
    channels = await db.list_channels(user_id)
    selected = set(data.get("selected_channels", []))

    await ui.clear_previous(message.bot, message.chat.id, user_id)
    sent = await message.answer(
        t(lang, "newpost.pending_prompt"),
        reply_markup=channels_keyboard(channels, selected, lang),
    )
    await ui.track(user_id, sent)


# ---------- контент принимаем после того, как выбраны каналы ----------

@router.message((F.photo | F.video) & ~F.media_group_id, NewPost.waiting_content)
async def receive_single_media(message: Message, state: FSMContext):
    await state.update_data(**_content_fields_from_single(message))
    await _go_to_delete_after(message, state)


@router.message(F.media_group_id, NewPost.waiting_content)
async def receive_album_part(message: Message, state: FSMContext, bot: Bot):
    gid = message.media_group_id
    buf = _album_buffers.setdefault(gid, [])
    buf.append(message)
    if len(buf) == 1:
        asyncio.create_task(_process_album(gid, state, bot))


async def _process_album(gid: str, state: FSMContext, bot: Bot):
    await asyncio.sleep(ALBUM_WAIT_SECONDS)
    messages = _album_buffers.pop(gid, [])
    if not messages:
        return
    messages.sort(key=lambda m: m.message_id)
    fields = _content_fields_from_album(messages)
    if not fields:
        return

    await state.update_data(**fields)
    data = await state.get_data()
    lang = await get_user_lang(data["user_id"])
    await bot.send_message(messages[0].chat.id, t(lang, "newpost.album_received", n=len(fields["album_items"])))
    await _go_to_delete_after(messages[0], state)


@router.message(F.text & ~F.text.startswith("/"), NewPost.waiting_content)
async def receive_text_content(message: Message, state: FSMContext):
    await state.update_data(**_content_fields_from_single(message))
    await _go_to_delete_after(message, state)


# ---------- дружелюбная подсказка, если контент прислали без активного сценария ----------

@router.message(F.photo | F.video | F.text | F.media_group_id, StateFilter(None))
async def stray_content(message: Message):
    if message.text and message.text.startswith("/"):
        return
    user_id = await db.get_or_create_user(message.from_user.id)
    lang = await get_user_lang(user_id)
    await message.answer(t(lang, "newpost.stray_reminder"))


# ---------- шаг: через сколько удалить → показываем предпросмотр ----------

async def _go_to_delete_after(message: Message, state: FSMContext):
    await state.set_state(NewPost.choosing_delete_after)
    data = await state.get_data()
    user_id = data["user_id"]
    lang = await get_user_lang(user_id)

    await ui.clear_previous(message.bot, message.chat.id, user_id)
    user = await db.get_user(user_id)
    default_hours = user["default_delete_after_hours"] if user else None
    sent = await message.answer(
        t(lang, "newpost.delete_after_prompt"), reply_markup=delete_after_keyboard(default_hours, lang)
    )
    await ui.track(user_id, sent)


@router.callback_query(NewPost.choosing_delete_after, F.data.startswith("del:"))
async def choose_delete_after(callback: CallbackQuery, state: FSMContext):
    hours = int(callback.data.split(":")[1]) or None
    await state.update_data(delete_after_hours=hours)
    await state.set_state(NewPost.choosing_time)

    data = await state.get_data()
    user_id = data["user_id"]
    await ui.clear_previous(callback.bot, callback.message.chat.id, user_id)
    await _send_preview(callback.message, data, state)
    await callback.answer()


async def _send_preview(message: Message, data: dict, state: FSMContext):
    """Показываем пост так, как он реально будет выглядеть, вешаем кнопки
    'когда публикуем' + опционально кнопки-ссылки. Запоминаем id этого
    сообщения, чтобы потом можно было менять его клавиатуру на месте."""
    user_id = data["user_id"]
    lang = await get_user_lang(user_id)
    media_type = data["media_type"]
    text = data.get("text")
    entities = deserialize_entities(data.get("entities_json"))
    link_buttons = data.get("link_buttons")
    silent = data.get("silent", False)
    allow_link_buttons = media_type != "album"  # Telegram не поддерживает reply_markup в альбомах
    kb = preview_keyboard(link_buttons, allow_link_buttons, lang, silent)

    if media_type == "photo":
        sent = await message.answer_photo(
            data["file_id"], caption=text, caption_entities=entities, parse_mode=None, reply_markup=kb
        )
    elif media_type == "video":
        sent = await message.answer_video(
            data["file_id"], caption=text, caption_entities=entities, parse_mode=None, reply_markup=kb
        )
    elif media_type == "album":
        items = data.get("album_items") or []
        media = []
        for i, item in enumerate(items):
            cls = InputMediaPhoto if item["type"] == "photo" else InputMediaVideo
            kwargs = {}
            if i == 0 and text:
                kwargs["caption"] = text
                kwargs["caption_entities"] = entities
                kwargs["parse_mode"] = None
            media.append(cls(media=item["file_id"], **kwargs))
        await message.answer_media_group(media)
        sent = await message.answer(t(lang, "newpost.album_preview_note"), reply_markup=kb)
    else:
        sent = await message.answer(text or "—", entities=entities, parse_mode=None, reply_markup=kb)

    await ui.track(user_id, sent)
    await state.update_data(preview_message_id=sent.message_id)


async def _return_to_preview(bot: Bot, chat_id: int, state: FSMContext, data: dict, trigger_message: Message):
    """Убираем подсказку-ввод (и устаревший предпросмотр, если был) и
    показываем свежий предпросмотр с текущими кнопками — сразу видно
    результат, а не тихое редактирование сообщения где-то выше по чату."""
    await state.set_state(NewPost.choosing_time)
    await ui.clear_previous(bot, chat_id, data["user_id"])

    old_preview_id = data.get("preview_message_id")
    if old_preview_id:
        try:
            await bot.delete_message(chat_id, old_preview_id)
        except Exception:
            pass

    data = await state.get_data()
    await _send_preview(trigger_message, data, state)


@router.callback_query(NewPost.choosing_time, F.data == "toggle_silent")
async def toggle_silent(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    silent = not data.get("silent", False)
    await state.update_data(silent=silent)
    data = await state.get_data()

    # Тот же надёжный паттерн, что и у 'назад'/кнопок-ссылок: убираем старый
    # предпросмотр и шлём свежий — тихое редактирование клавиатуры на месте
    # у нас в проекте нестабильно (уже сталкивались с этим раньше).
    await _return_to_preview(callback.bot, callback.message.chat.id, state, data, callback.message)
    await callback.answer()


# ---------- кнопки-ссылки под постом ----------

@router.callback_query(NewPost.choosing_time, F.data == "add_link_buttons")
async def start_add_link_buttons(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = await get_user_lang(data["user_id"])
    await state.set_state(NewPost.waiting_buttons)

    preview_id = data.get("preview_message_id")
    if preview_id:
        try:
            await callback.bot.edit_message_reply_markup(
                callback.message.chat.id, preview_id, reply_markup=back_only_keyboard(lang)
            )
        except Exception:
            pass

    # Не чистим предыдущее сообщение здесь: сейчас 'последнее' — это сам
    # предпросмотр, его нужно оставить (только что поменяли ему клавиатуру).
    sent = await callback.message.answer(
        t(lang, "newpost.link_buttons_prompt"),
        reply_markup=back_only_keyboard(lang),
    )
    await ui.track(data["user_id"], sent)
    await callback.answer()


@router.message(NewPost.waiting_buttons)
async def receive_link_buttons(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = await get_user_lang(data["user_id"])
    rows, bad_part = parse_link_buttons(message.text or "")
    if rows is None:
        hint = t(lang, "newpost.link_buttons_bad_part", part=html.escape(bad_part)) if bad_part else ""
        await message.answer(t(lang, "newpost.link_buttons_bad_format", hint=hint))
        return

    await state.update_data(link_buttons=rows)
    data = await state.get_data()
    await ui.delete_user_message(message)
    await _return_to_preview(message.bot, message.chat.id, state, data, message)


@router.callback_query(NewPost.waiting_buttons, F.data == "preview_back")
async def back_from_buttons(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await _return_to_preview(callback.bot, callback.message.chat.id, state, data, callback.message)
    await callback.answer()


# ---------- шаг: когда публиковать ----------

@router.callback_query(NewPost.choosing_time, F.data.startswith("when:"))
async def choose_when(callback: CallbackQuery, state: FSMContext, bot: Bot):
    choice = callback.data.split(":")[1]
    data = await state.get_data()
    lang = await get_user_lang(data["user_id"])

    if choice == "custom":
        tz_name = await get_user_tz_name(data["user_id"])
        await state.set_state(NewPost.waiting_custom_time)

        preview_id = data.get("preview_message_id")
        if preview_id:
            try:
                await bot.edit_message_reply_markup(
                    callback.message.chat.id, preview_id, reply_markup=back_only_keyboard(lang)
                )
            except Exception:
                pass

        sent = await callback.message.answer(
            t(lang, "newpost.custom_time_prompt", tz=tz_name),
            reply_markup=back_only_keyboard(lang),
        )
        await ui.track(data["user_id"], sent)
        await callback.answer()
        return

    tz = await get_user_tz(data["user_id"])
    now = datetime.now(tz)
    publish_at = {
        "now": now,
        "1h": now + timedelta(hours=1),
        "3h": now + timedelta(hours=3),
    }[choice]

    await _finalize(callback.message, state, bot, publish_at, tz)
    await callback.answer()


@router.callback_query(NewPost.waiting_custom_time, F.data == "preview_back")
async def back_from_custom_time(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await _return_to_preview(callback.bot, callback.message.chat.id, state, data, callback.message)
    await callback.answer()


@router.message(NewPost.waiting_custom_time)
async def custom_time_entered(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    lang = await get_user_lang(data["user_id"])
    tz = await get_user_tz(data["user_id"])
    try:
        naive = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        publish_at = naive.replace(tzinfo=tz)
    except ValueError:
        await message.answer(t(lang, "newpost.custom_time_bad_format"))
        return

    if publish_at < datetime.now(tz):
        await message.answer(t(lang, "newpost.custom_time_past"))
        return

    await ui.delete_user_message(message)
    await _finalize(message, state, bot, publish_at, tz)


# ---------- финал: создаём пост и таргеты ----------

async def _finalize(message: Message, state: FSMContext, bot: Bot, publish_at: datetime, tz):
    data = await state.get_data()
    lang = await get_user_lang(data["user_id"])
    link_buttons = data.get("link_buttons")
    button_json = json.dumps(link_buttons) if link_buttons else None
    silent = data.get("silent", False)

    post_id = await db.create_post(
        data["user_id"], data.get("text"), data["media_type"], data.get("file_id"),
        data.get("entities_json"), data.get("source_chat_id"), data.get("source_message_ids"),
        button_json, silent,
    )

    if data["media_type"] == "album" and data.get("album_items"):
        await db.add_album_items(post_id, data["album_items"])

    await db.create_targets(
        post_id, data["selected_channels"], publish_at, data.get("delete_after_hours")
    )

    channels = await db.list_channels(data["user_id"])
    names = [c["title"] for c in channels if c["id"] in set(data["selected_channels"])]

    when_str = t(lang, "newpost.finalize_now") if publish_at <= datetime.now(tz) + timedelta(seconds=30) \
        else publish_at.strftime("%d.%m.%Y %H:%M")

    text = t(
        lang, "newpost.finalize",
        channels=", ".join(names), when=when_str,
        delete_label=_delete_after_label(data.get("delete_after_hours"), lang),
        sound_label=t(lang, "newpost.sound_off" if silent else "newpost.sound_on"),
    )
    await ui.clear_previous(bot, message.chat.id, data["user_id"])

    old_preview_id = data.get("preview_message_id")
    if old_preview_id:
        try:
            await bot.delete_message(message.chat.id, old_preview_id)
        except Exception:
            pass

    sent = await message.answer(text)
    await ui.track(data["user_id"], sent)
    await state.clear()


# ---------- отмена на любом шаге ----------
# (обработчик 'cancel'/'go_home' общий, живёт в bot/handlers/common.py)
