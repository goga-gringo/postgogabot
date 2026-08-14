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
from bot.tzutil import get_user_tz, get_user_tz_name
from bot.states import NewPost
from bot.entities_util import serialize_entities, deserialize_entities
from bot.keyboards import channels_keyboard, delete_after_keyboard, preview_keyboard, back_only_keyboard

router = Router()
logger = logging.getLogger(__name__)

# Сбор альбомов: Telegram присылает медиагруппу как несколько отдельных апдейтов
# подряд — собираем их в буфер и обрабатываем одним постом через небольшую паузу.
ALBUM_WAIT_SECONDS = 1.3
_album_buffers: dict[str, list[Message]] = {}


def _delete_after_label(hours: int | None) -> str:
    return "не удалять" if not hours else f"удалить через {hours}ч"


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


# ---------- запуск сценария: сначала выбор каналов ----------

async def start_new_post(message: Message, state: FSMContext, from_user_id: int):
    user_id = await db.get_or_create_user(from_user_id)
    channels = await db.list_channels(user_id)
    if not channels:
        await message.answer("Сначала подключи хотя бы один канал: «📢 Мои каналы»")
        return

    await ui.clear_previous(message.bot, message.chat.id, user_id)
    await state.update_data(selected_channels=[], user_id=user_id)
    await state.set_state(NewPost.choosing_channels)
    sent = await message.answer(
        "В какие каналы постим? Отметь один или несколько:",
        reply_markup=channels_keyboard(channels, set()),
    )
    await ui.track(user_id, sent)


@router.callback_query(NewPost.choosing_channels, F.data.startswith("ch:"))
async def toggle_channel(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected = set(data.get("selected_channels", []))
    if channel_id in selected:
        selected.discard(channel_id)
    else:
        selected.add(channel_id)
    await state.update_data(selected_channels=list(selected))

    channels = await db.list_channels(data["user_id"])
    await callback.message.edit_reply_markup(reply_markup=channels_keyboard(channels, selected))
    await callback.answer()


@router.callback_query(NewPost.choosing_channels, F.data == "toggle_all")
async def toggle_all_channels(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    channels = await db.list_channels(data["user_id"])
    all_ids = {c["id"] for c in channels}
    selected = set(data.get("selected_channels", []))
    selected = set() if selected == all_ids else set(all_ids)
    await state.update_data(selected_channels=list(selected))
    await callback.message.edit_reply_markup(reply_markup=channels_keyboard(channels, selected))
    await callback.answer()


@router.callback_query(NewPost.choosing_channels, F.data == "channels_done")
async def channels_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("selected_channels"):
        await callback.answer("Выбери хотя бы один канал!", show_alert=True)
        return
    await state.set_state(NewPost.waiting_content)
    await callback.message.edit_text(
        "Каналы выбраны ✅\n\nТеперь пришли текст, фото, видео или альбом — "
        "это станет содержимым поста."
    )
    await callback.answer()


# ---------- контент принимаем только после того, как выбраны каналы ----------

@router.message((F.photo | F.video) & ~F.media_group_id, NewPost.waiting_content)
async def receive_single_media(message: Message, state: FSMContext):
    media_type = "photo" if message.photo else "video"
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    await state.update_data(
        media_type=media_type,
        file_id=file_id,
        text=message.caption,
        entities_json=serialize_entities(message.caption_entities),
        album_items=None,
        source_chat_id=message.chat.id,
        source_message_ids=[message.message_id],
        link_buttons=None,
    )
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

    if not items:
        return

    await state.update_data(
        media_type="album",
        file_id=None,
        text=caption_text,
        entities_json=caption_entities_json,
        album_items=items,
        source_chat_id=messages[0].chat.id,
        source_message_ids=[m.message_id for m in messages],
        link_buttons=None,
    )
    await bot.send_message(messages[0].chat.id, f"Альбом из {len(items)} медиафайлов принят.")
    await _go_to_delete_after(messages[0], state)


@router.message(F.text & ~F.text.startswith("/"), NewPost.waiting_content)
async def receive_text_content(message: Message, state: FSMContext):
    await state.update_data(
        media_type="text",
        file_id=None,
        text=message.text,
        entities_json=serialize_entities(message.entities),
        album_items=None,
        source_chat_id=message.chat.id,
        source_message_ids=[message.message_id],
        link_buttons=None,
    )
    await _go_to_delete_after(message, state)


# ---------- дружелюбная подсказка, если контент прислали без активного сценария ----------

@router.message((F.photo | F.video | F.text | F.media_group_id) & StateFilter(None))
async def stray_content(message: Message):
    if message.text and message.text.startswith("/"):
        return
    await message.answer(
        "Чтобы создать пост, сначала нажми «📝 Создать пост» внизу — "
        "там сперва выбираем каналы, потом присылаем контент."
    )


# ---------- шаг: через сколько удалить → показываем предпросмотр ----------

async def _go_to_delete_after(message: Message, state: FSMContext):
    await state.set_state(NewPost.choosing_delete_after)
    data = await state.get_data()
    user_id = data["user_id"]

    await ui.clear_previous(message.bot, message.chat.id, user_id)
    user = await db.get_user(user_id)
    default_hours = user["default_delete_after_hours"] if user else None
    sent = await message.answer(
        "Когда удалить пост после публикации?", reply_markup=delete_after_keyboard(default_hours)
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
    сообщения, чтобы потом можно было менять его клавиатуру на месте
    (не плодя новые сообщения при 'указать время вручную' / 'назад')."""
    user_id = data["user_id"]
    media_type = data["media_type"]
    text = data.get("text")
    entities = deserialize_entities(data.get("entities_json"))
    link_buttons = data.get("link_buttons")
    allow_link_buttons = media_type != "album"  # Telegram не поддерживает reply_markup в альбомах
    kb = preview_keyboard(link_buttons, allow_link_buttons)

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
        sent = await message.answer(
            f"👆 Так будет выглядеть альбом (кнопки под альбомом Telegram не поддерживает).\n"
            f"Когда публикуем?",
            reply_markup=kb,
        )
    else:
        sent = await message.answer(text or "(пусто)", entities=entities, parse_mode=None, reply_markup=kb)

    await ui.track(user_id, sent)
    await state.update_data(preview_message_id=sent.message_id)


async def _restore_preview_markup(bot: Bot, chat_id: int, data: dict):
    """Возвращаем предпросмотру его обычную клавиатуру (после 'назад')."""
    preview_id = data.get("preview_message_id")
    if not preview_id:
        return
    media_type = data.get("media_type")
    allow_link_buttons = media_type != "album"
    try:
        await bot.edit_message_reply_markup(
            chat_id, preview_id,
            reply_markup=preview_keyboard(data.get("link_buttons"), allow_link_buttons),
        )
    except Exception as e:
        logger.debug("Could not restore preview markup: %s", e)


# ---------- кнопки-ссылки под постом ----------

@router.callback_query(NewPost.choosing_time, F.data == "add_link_buttons")
async def start_add_link_buttons(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(NewPost.waiting_buttons)

    preview_id = data.get("preview_message_id")
    if preview_id:
        try:
            await callback.bot.edit_message_reply_markup(
                callback.message.chat.id, preview_id, reply_markup=back_only_keyboard()
            )
        except Exception:
            pass

    await ui.clear_previous(callback.bot, callback.message.chat.id, data["user_id"])
    sent = await callback.message.answer(
        "Пришли кнопки-ссылки под постом. Формат — одна кнопка на строку:\n"
        "<code>Текст - ссылка</code>\n"
        "Несколько кнопок в один ряд — через <code>|</code>\n\n"
        "Например:\n"
        "<code>Sweet - t.me/+TrZYZoeqUbQ2M</code>\n"
        "<code>Сайт - https://example.com | Чат - https://t.me/chat</code>",
        reply_markup=back_only_keyboard(),
    )
    await ui.track(data["user_id"], sent)
    await callback.answer()


@router.message(NewPost.waiting_buttons)
async def receive_link_buttons(message: Message, state: FSMContext):
    data = await state.get_data()
    rows, bad_part = parse_link_buttons(message.text or "")
    if rows is None:
        hint = f"Не понял часть: <code>{html.escape(bad_part)}</code>\n" if bad_part else ""
        await message.answer(
            hint + "Формат: <code>Текст - ссылка</code>. Ссылка должна начинаться с "
            "http://, https:// или tg://. Попробуй ещё раз, или «🔙 Назад»."
        )
        return

    await state.update_data(link_buttons=rows)
    await state.set_state(NewPost.choosing_time)
    data = await state.get_data()

    await _restore_preview_markup(message.bot, message.chat.id, data)
    await ui.clear_previous(message.bot, message.chat.id, data["user_id"])
    sent = await message.answer(f"✅ Кнопок добавлено: {sum(len(r) for r in rows)}")
    await ui.track(data["user_id"], sent)


@router.callback_query(NewPost.waiting_buttons, F.data == "preview_back")
async def back_from_buttons(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(NewPost.choosing_time)
    await _restore_preview_markup(callback.bot, callback.message.chat.id, data)
    await ui.clear_previous(callback.bot, callback.message.chat.id, data["user_id"])
    await callback.answer()


# ---------- шаг: когда публиковать ----------

@router.callback_query(NewPost.choosing_time, F.data.startswith("when:"))
async def choose_when(callback: CallbackQuery, state: FSMContext, bot: Bot):
    choice = callback.data.split(":")[1]
    data = await state.get_data()

    if choice == "custom":
        tz_name = await get_user_tz_name(data["user_id"])
        await state.set_state(NewPost.waiting_custom_time)

        preview_id = data.get("preview_message_id")
        if preview_id:
            try:
                await bot.edit_message_reply_markup(
                    callback.message.chat.id, preview_id, reply_markup=back_only_keyboard()
                )
            except Exception:
                pass

        sent = await callback.message.answer(
            "Напиши дату и время публикации в формате:\n"
            "<code>31.12.2026 15:30</code>\n\n"
            f"Часовой пояс: {tz_name} (поменять — в ⚙️ Настройках)",
            reply_markup=back_only_keyboard(),
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
    await state.set_state(NewPost.choosing_time)
    await _restore_preview_markup(callback.bot, callback.message.chat.id, data)
    await ui.clear_previous(callback.bot, callback.message.chat.id, data["user_id"])
    await callback.answer()


@router.message(NewPost.waiting_custom_time)
async def custom_time_entered(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    tz = await get_user_tz(data["user_id"])
    try:
        naive = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        publish_at = naive.replace(tzinfo=tz)
    except ValueError:
        await message.answer("Не понял формат. Пример: 31.12.2026 15:30")
        return

    if publish_at < datetime.now(tz):
        await message.answer("Это время уже в прошлом. Введи время в будущем.")
        return

    await _finalize(message, state, bot, publish_at, tz)


# ---------- финал: создаём пост и таргеты ----------

async def _finalize(message: Message, state: FSMContext, bot: Bot, publish_at: datetime, tz):
    data = await state.get_data()
    link_buttons = data.get("link_buttons")
    button_json = json.dumps(link_buttons) if link_buttons else None

    post_id = await db.create_post(
        data["user_id"], data.get("text"), data["media_type"], data.get("file_id"),
        data.get("entities_json"), data.get("source_chat_id"), data.get("source_message_ids"),
        button_json,
    )

    if data["media_type"] == "album" and data.get("album_items"):
        await db.add_album_items(post_id, data["album_items"])

    await db.create_targets(
        post_id, data["selected_channels"], publish_at, data.get("delete_after_hours")
    )

    channels = await db.list_channels(data["user_id"])
    names = [c["title"] for c in channels if c["id"] in set(data["selected_channels"])]

    when_str = "сейчас" if publish_at <= datetime.now(tz) + timedelta(seconds=30) \
        else publish_at.strftime("%d.%m.%Y %H:%M")

    text = (
        "✅ Готово!\n\n"
        f"Каналы: {', '.join(names)}\n"
        f"Публикация: {when_str}\n"
        f"Удаление: {_delete_after_label(data.get('delete_after_hours'))}\n\n"
        "Изменить текст поста позже можно в разделе «📋 Мои посты»"
    )
    await ui.clear_previous(bot, message.chat.id, data["user_id"])
    sent = await message.answer(text)
    await ui.track(data["user_id"], sent)
    await state.clear()


# ---------- отмена на любом шаге ----------

@router.callback_query(F.data == "cancel")
async def cancel_flow(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено.")
    await callback.answer()
