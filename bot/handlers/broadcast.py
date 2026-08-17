import asyncio
import logging
import re

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import db
from bot.config import ADMIN_TG_IDS
from bot.entities_util import serialize_entities, deserialize_entities

router = Router()
logger = logging.getLogger(__name__)

# Небольшая пауза между отправками, чтобы не упереться в лимиты Telegram
# (примерно 30 сообщений/сек в разные чаты) — 0.05с ≈ 20/сек, с запасом.
BROADCAST_DELAY_SECONDS = 0.05

BROADCAST_CMD_RE = re.compile(r"^/post_all(?:_(\d+))?(?:@\w+)?(?:\s|$)")


class Broadcast(StatesGroup):
    waiting_content = State()
    confirming = State()


def _is_admin(tg_id: int) -> bool:
    return tg_id in ADMIN_TG_IDS


def _delete_label(hours: int | None) -> str:
    return "никогда" if not hours else f"через {hours}ч"


@router.message(F.text.regexp(BROADCAST_CMD_RE))
async def cmd_post_all(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return  # тихо игнорируем — не палим посторонним, что команда вообще есть

    m = BROADCAST_CMD_RE.match(message.text)
    hours = int(m.group(1)) if m.group(1) else None

    await state.clear()
    await state.update_data(broadcast_delete_hours=hours)
    await state.set_state(Broadcast.waiting_content)

    count = await db.count_users()
    await message.answer(
        f"📣 Режим рассылки всем пользователям бота ({count} чел.)\n"
        f"Автоудаление: {_delete_label(hours)}\n\n"
        "Пришли текст, фото или видео — это уйдёт всем в личку.\n"
        "/cancel — отменить"
    )


@router.message(Broadcast.waiting_content, F.photo | F.video | (F.text & ~F.text.startswith("/")))
async def receive_broadcast_content(message: Message, state: FSMContext):
    if message.photo:
        media_type, file_id = "photo", message.photo[-1].file_id
        text, entities_json = message.caption, serialize_entities(message.caption_entities)
    elif message.video:
        media_type, file_id = "video", message.video.file_id
        text, entities_json = message.caption, serialize_entities(message.caption_entities)
    else:
        media_type, file_id = "text", None
        text, entities_json = message.text, serialize_entities(message.entities)

    await state.update_data(media_type=media_type, file_id=file_id, text=text, entities_json=entities_json)
    await state.set_state(Broadcast.confirming)

    data = await state.get_data()
    count = await db.count_users()
    hours = data.get("broadcast_delete_hours")
    entities = deserialize_entities(entities_json)

    if media_type == "photo":
        await message.answer_photo(file_id, caption=text, caption_entities=entities, parse_mode=None)
    elif media_type == "video":
        await message.answer_video(file_id, caption=text, caption_entities=entities, parse_mode=None)
    else:
        await message.answer(text or "—", entities=entities, parse_mode=None)

    b = InlineKeyboardBuilder()
    b.button(text="✅ Разослать всем", callback_data="broadcast_confirm")
    b.button(text="✖️ Отмена", callback_data="broadcast_cancel")
    b.adjust(1)
    await message.answer(
        f"👆 Так это увидят пользователи.\n\n"
        f"Получателей: {count}\n"
        f"Автоудаление: {_delete_label(hours)}\n\n"
        "Подтвердить рассылку?",
        reply_markup=b.as_markup(),
    )


@router.callback_query(Broadcast.confirming, F.data == "broadcast_confirm")
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    await callback.message.edit_text("🚀 Рассылка запущена в фоне — пришлю отчёт, когда закончится.")
    await callback.answer()
    asyncio.create_task(_run_broadcast(bot, callback.from_user.id, data))


@router.callback_query(Broadcast.confirming, F.data == "broadcast_cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено.")
    await callback.answer()


async def _run_broadcast(bot: Bot, admin_tg_id: int, data: dict):
    media_type = data["media_type"]
    text = data.get("text")
    entities_json = data.get("entities_json")
    entities = deserialize_entities(entities_json)
    delete_after_hours = data.get("broadcast_delete_hours")

    broadcast_id = await db.create_broadcast(
        admin_tg_id, text, entities_json, media_type, data.get("file_id"), delete_after_hours
    )
    tg_ids = await db.get_all_user_tg_ids()
    await db.create_broadcast_targets(broadcast_id, tg_ids)

    targets = await db.get_pending_broadcast_targets(broadcast_id)
    sent, failed = 0, 0

    for target in targets:
        try:
            if media_type == "photo":
                msg = await bot.send_photo(
                    target["user_tg_id"], data["file_id"], caption=text,
                    caption_entities=entities, parse_mode=None,
                )
            elif media_type == "video":
                msg = await bot.send_video(
                    target["user_tg_id"], data["file_id"], caption=text,
                    caption_entities=entities, parse_mode=None,
                )
            else:
                msg = await bot.send_message(target["user_tg_id"], text, entities=entities, parse_mode=None)

            await db.mark_broadcast_sent(target["target_id"], msg.message_id, delete_after_hours)
            sent += 1
        except Exception as e:
            logger.warning("Broadcast send failed for user %s: %s", target["user_tg_id"], e)
            await db.mark_broadcast_failed(target["target_id"], str(e))
            failed += 1
        await asyncio.sleep(BROADCAST_DELAY_SECONDS)

    try:
        await bot.send_message(
            admin_tg_id,
            f"✅ Рассылка #{broadcast_id} завершена.\nОтправлено: {sent}\nНе удалось: {failed}",
        )
    except Exception:
        pass
