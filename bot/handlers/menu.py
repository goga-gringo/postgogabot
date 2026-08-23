from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot import db
from bot import ui
from bot.i18n import t, variants, get_user_lang
from bot.tzutil import get_user_tz_name
from bot.keyboards import settings_keyboard, main_menu_keyboard
from bot.handlers.channels import cmd_channels
from bot.handlers.edit import cmd_myposts
from bot.handlers.posts import start_new_post

router = Router()


@router.message(F.text.in_(variants("menu.create")))
async def menu_create(message: Message, state: FSMContext):
    await state.clear()
    await ui.delete_user_message(message)
    await start_new_post(message, state, message.from_user.id)


@router.message(F.text.in_(variants("menu.channels")))
async def menu_channels(message: Message, state: FSMContext):
    await state.clear()
    await ui.delete_user_message(message)
    await cmd_channels(message)


@router.message(F.text.in_(variants("menu.posts")))
async def menu_posts(message: Message, state: FSMContext):
    await state.clear()
    await ui.delete_user_message(message)
    await cmd_myposts(message)


async def _build_settings_kb(user_id: int, lang: str):
    user = await db.get_user(user_id)
    tz_name = await get_user_tz_name(user_id)
    default_hours = user["default_delete_after_hours"] if user else None
    delete_from_comments = bool(user and user["delete_from_comments"])
    return settings_keyboard(tz_name, default_hours, lang, delete_from_comments, lang)


async def _send_settings(message: Message, user_id: int):
    lang = await get_user_lang(user_id)
    await ui.clear_previous(message.bot, message.chat.id, user_id)
    sent = await message.answer(t(lang, "settings.header"), reply_markup=await _build_settings_kb(user_id, lang))
    await ui.track(user_id, sent)


@router.message(F.text.in_(variants("menu.settings")))
async def menu_settings(message: Message, state: FSMContext):
    await state.clear()
    user_id = await db.get_or_create_user(message.from_user.id)
    await ui.delete_user_message(message)
    await _send_settings(message, user_id)


@router.callback_query(F.data.startswith("tz:"))
async def cb_set_tz(callback: CallbackQuery):
    tz_name = callback.data.split(":", 1)[1]
    user_id = await db.get_or_create_user(callback.from_user.id)
    await db.set_user_timezone(user_id, tz_name)

    lang = await get_user_lang(user_id)
    await callback.message.edit_reply_markup(reply_markup=await _build_settings_kb(user_id, lang))
    await callback.answer(tz_name)


@router.callback_query(F.data.startswith("defdel:"))
async def cb_set_default_delete(callback: CallbackQuery):
    hours = int(callback.data.split(":")[1]) or None
    user_id = await db.get_or_create_user(callback.from_user.id)
    await db.set_user_default_delete_after(user_id, hours)

    lang = await get_user_lang(user_id)
    await callback.message.edit_reply_markup(reply_markup=await _build_settings_kb(user_id, lang))
    await callback.answer("✅")


@router.callback_query(F.data == "toggle_comments")
async def cb_toggle_comments(callback: CallbackQuery):
    user_id = await db.get_or_create_user(callback.from_user.id)
    user = await db.get_user(user_id)
    enabled = not bool(user and user["delete_from_comments"])
    await db.set_user_delete_from_comments(user_id, enabled)

    lang = await get_user_lang(user_id)
    await callback.message.edit_reply_markup(reply_markup=await _build_settings_kb(user_id, lang))
    await callback.answer("✅")


@router.callback_query(F.data.startswith("lang:"))
async def cb_set_language(callback: CallbackQuery):
    lang = callback.data.split(":")[1]
    user_id = await db.get_or_create_user(callback.from_user.id)
    await db.set_user_language(user_id, lang)

    # Меняем и клавиатуру настроек (на новом языке), и reply-меню внизу —
    # для него нужно отдельное сообщение, reply-клавиатуру нельзя просто отредактировать.
    await callback.message.edit_text(t(lang, "settings.header"), reply_markup=await _build_settings_kb(user_id, lang))
    await callback.bot.send_message(
        callback.message.chat.id, t(lang, "menu.text"), reply_markup=main_menu_keyboard(lang)
    )
    await callback.answer("✅")
