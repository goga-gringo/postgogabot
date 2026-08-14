from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot import db
from bot import ui
from bot.tzutil import get_user_tz_name
from bot.keyboards import (
    settings_keyboard,
    MENU_CREATE, MENU_CHANNELS, MENU_POSTS, MENU_SETTINGS,
)
from bot.handlers.channels import cmd_channels
from bot.handlers.edit import cmd_myposts
from bot.handlers.posts import start_new_post

router = Router()


@router.message(F.text == MENU_CREATE)
async def menu_create(message: Message, state: FSMContext):
    await state.clear()
    await start_new_post(message, state, message.from_user.id)


@router.message(F.text == MENU_CHANNELS)
async def menu_channels(message: Message, state: FSMContext):
    await state.clear()
    await cmd_channels(message)


@router.message(F.text == MENU_POSTS)
async def menu_posts(message: Message, state: FSMContext):
    await state.clear()
    await cmd_myposts(message)


@router.message(F.text == MENU_SETTINGS)
async def menu_settings(message: Message, state: FSMContext):
    await state.clear()
    user_id = await db.get_or_create_user(message.from_user.id)
    user = await db.get_user(user_id)
    tz_name = await get_user_tz_name(user_id)
    default_hours = user["default_delete_after_hours"] if user else None
    await ui.clear_previous(message.bot, message.chat.id, user_id)
    sent = await message.answer(
        "⚙️ Настройки\n\n"
        "Часовой пояс — используется для ручного ввода времени публикации.\n"
        "Автоудаление по умолчанию — какая опция будет отмечена звёздочкой ⭐ "
        "при создании поста (можно всегда выбрать другую вручную).",
        reply_markup=settings_keyboard(tz_name, default_hours),
    )
    await ui.track(user_id, sent)


@router.callback_query(F.data.startswith("tz:"))
async def cb_set_tz(callback: CallbackQuery):
    tz_name = callback.data.split(":", 1)[1]
    user_id = await db.get_or_create_user(callback.from_user.id)
    await db.set_user_timezone(user_id, tz_name)

    user = await db.get_user(user_id)
    default_hours = user["default_delete_after_hours"] if user else None
    await callback.message.edit_reply_markup(reply_markup=settings_keyboard(tz_name, default_hours))
    await callback.answer(f"Часовой пояс: {tz_name}")


@router.callback_query(F.data.startswith("defdel:"))
async def cb_set_default_delete(callback: CallbackQuery):
    hours = int(callback.data.split(":")[1]) or None
    user_id = await db.get_or_create_user(callback.from_user.id)
    await db.set_user_default_delete_after(user_id, hours)

    tz_name = await get_user_tz_name(user_id)
    await callback.message.edit_reply_markup(reply_markup=settings_keyboard(tz_name, hours))
    await callback.answer("Сохранено")
