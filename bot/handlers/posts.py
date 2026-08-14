import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot import db
from bot.tzutil import get_user_tz, get_user_tz_name
from bot.states import NewPost
from bot.keyboards import channels_keyboard, delete_after_keyboard, when_keyboard

router = Router()
logger = logging.getLogger(__name__)

# Сбор альбомов: Telegram присылает медиагруппу как несколько отдельных апдейтов
# подряд — собираем их в буфер и обрабатываем одним постом через небольшую паузу.
ALBUM_WAIT_SECONDS = 1.3
_album_buffers: dict[str, list[Message]] = {}


def _delete_after_label(hours: int | None) -> str:
    return "не удалять" if not hours else f"удалить через {hours}ч"


async def _start_post_flow(
    message: Message,
    state: FSMContext,
    from_user_id: int,
    media_type: str,
    file_id: str | None,
    text: str | None,
    album_items: list[dict] | None = None,
):
    user_id = await db.get_or_create_user(from_user_id)
    channels = await db.list_channels(user_id)
    if not channels:
        await message.answer("Сначала подключи хотя бы один канал: /addchannel")
        return

    await state.update_data(
        media_type=media_type,
        file_id=file_id,
        text=text,
        album_items=album_items,
        selected_channels=[],
        user_id=user_id,
    )
    await state.set_state(NewPost.choosing_channels)
    await message.answer(
        "В какие каналы постим? Отметь один или несколько:",
        reply_markup=channels_keyboard(channels, set()),
    )


# ---------- шаг 1a: одиночное фото/видео (не альбом) ----------

@router.message((F.photo | F.video) & ~F.media_group_id, StateFilter(None))
async def receive_single_media(message: Message, state: FSMContext):
    media_type = "photo" if message.photo else "video"
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    await _start_post_flow(
        message, state, message.from_user.id, media_type, file_id, message.html_text
    )


# ---------- шаг 1b: альбом (несколько фото/видео) ----------

@router.message(F.media_group_id, StateFilter(None))
async def receive_album_part(message: Message, state: FSMContext, bot: Bot):
    gid = message.media_group_id
    buf = _album_buffers.setdefault(gid, [])
    buf.append(message)
    if len(buf) == 1:
        asyncio.create_task(_process_album(gid, message.chat.id, message.from_user.id, state, bot))


async def _process_album(gid: str, chat_id: int, from_user_id: int, state: FSMContext, bot: Bot):
    await asyncio.sleep(ALBUM_WAIT_SECONDS)
    messages = _album_buffers.pop(gid, [])
    if not messages:
        return
    messages.sort(key=lambda m: m.message_id)

    items = []
    caption_html = None
    for m in messages:
        if m.photo:
            items.append({"type": "photo", "file_id": m.photo[-1].file_id})
        elif m.video:
            items.append({"type": "video", "file_id": m.video.file_id})
        if m.caption and not caption_html:
            caption_html = m.html_text

    if not items:
        return

    user_id = await db.get_or_create_user(from_user_id)
    channels = await db.list_channels(user_id)
    if not channels:
        await bot.send_message(chat_id, "Сначала подключи хотя бы один канал: /addchannel")
        return

    await state.update_data(
        media_type="album",
        file_id=None,
        text=caption_html,
        album_items=items,
        selected_channels=[],
        user_id=user_id,
    )
    await state.set_state(NewPost.choosing_channels)
    await bot.send_message(
        chat_id,
        f"Альбом из {len(items)} медиафайлов. В какие каналы постим?",
        reply_markup=channels_keyboard(channels, set()),
    )


# ---------- шаг 1c: просто текст ----------

@router.message(F.text & ~F.text.startswith("/"), StateFilter(None))
async def receive_text_content(message: Message, state: FSMContext):
    await _start_post_flow(
        message, state, message.from_user.id, "text", None, message.html_text
    )


# ---------- шаг 2: выбор каналов (toggle) ----------

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


@router.callback_query(NewPost.choosing_channels, F.data == "channels_done")
async def channels_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("selected_channels"):
        await callback.answer("Выбери хотя бы один канал!", show_alert=True)
        return
    await state.set_state(NewPost.choosing_delete_after)
    user = await db.get_user(data["user_id"])
    default_hours = user["default_delete_after_hours"] if user else None
    await callback.message.edit_text(
        "Когда удалить пост после публикации?", reply_markup=delete_after_keyboard(default_hours)
    )
    await callback.answer()


# ---------- шаг 3: через сколько удалить ----------

@router.callback_query(NewPost.choosing_delete_after, F.data.startswith("del:"))
async def choose_delete_after(callback: CallbackQuery, state: FSMContext):
    hours = int(callback.data.split(":")[1]) or None
    await state.update_data(delete_after_hours=hours)
    await state.set_state(NewPost.choosing_time)
    await callback.message.edit_text(
        f"Отметка удаления: {_delete_after_label(hours)}.\nКогда публикуем?",
        reply_markup=when_keyboard(),
    )
    await callback.answer()


# ---------- шаг 4: когда публиковать ----------

@router.callback_query(NewPost.choosing_time, F.data.startswith("when:"))
async def choose_when(callback: CallbackQuery, state: FSMContext, bot: Bot):
    choice = callback.data.split(":")[1]
    data = await state.get_data()

    if choice == "custom":
        tz_name = await get_user_tz_name(data["user_id"])
        await state.set_state(NewPost.waiting_custom_time)
        await callback.message.edit_text(
            "Напиши дату и время публикации в формате:\n"
            "<code>31.12.2026 15:30</code>\n\n"
            f"Часовой пояс: {tz_name} (поменять — в ⚙️ Настройках)",
        )
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
    post_id = await db.create_post(data["user_id"], data.get("text"), data["media_type"], data.get("file_id"))

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
        "Бот проверяет расписание регулярно, публикация появится в течение "
        "пары десятков секунд после назначенного времени.\n\n"
        "Изменить текст поста позже можно в разделе «📋 Мои посты»"
    )

    if isinstance(message, Message) and message.text is None and message.caption is None:
        # это может быть message без возможности edit_text (на всякий случай)
        await message.answer(text)
    else:
        try:
            await message.edit_text(text)
        except Exception:
            await message.answer(text)

    await state.clear()


# ---------- отмена на любом шаге ----------

@router.callback_query(F.data == "cancel")
async def cancel_flow(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено.")
    await callback.answer()
