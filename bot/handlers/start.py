from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import db
from bot import ui
from bot.i18n import t, get_user_lang
from bot.keyboards import main_menu_keyboard

router = Router()


def _language_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text=t("ru", "btn.lang_ru"), callback_data="setlang:ru")
    b.button(text=t("en", "btn.lang_en"), callback_data="setlang:en")
    b.adjust(2)
    return b.as_markup()


async def _send_welcome(bot, chat_id: int, lang: str):
    await bot.send_message(chat_id, t(lang, "start.welcome"), reply_markup=main_menu_keyboard(lang))
    # само приветствие не трекаем — у него есть постоянная reply-клавиатура,
    # его не нужно чистить как промежуточный экран


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = await db.get_or_create_user(message.from_user.id)
    await ui.clear_previous(message.bot, message.chat.id, user_id)
    await ui.delete_user_message(message)

    user = await db.get_user(user_id)
    if not user or not user["language"]:
        await message.answer(
            t("ru", "start.choose_language") + "\n" + t("en", "start.choose_language"),
            reply_markup=_language_keyboard(),
        )
        return

    await _send_welcome(message.bot, message.chat.id, user["language"])


@router.callback_query(F.data.startswith("setlang:"))
async def set_language_first_time(callback: CallbackQuery):
    lang = callback.data.split(":")[1]
    user_id = await db.get_or_create_user(callback.from_user.id)
    await db.set_user_language(user_id, lang)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await _send_welcome(callback.bot, callback.message.chat.id, lang)
    await callback.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    user_id = await db.get_or_create_user(message.from_user.id)
    lang = await get_user_lang(user_id)
    await ui.delete_user_message(message)
    await message.answer(t(lang, "start.cancelled"))
