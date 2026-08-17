from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot import db
from bot import ui
from bot.i18n import t, get_user_lang
from bot.keyboards import main_menu_keyboard

router = Router()


@router.callback_query(F.data.in_({"cancel", "go_home"}))
async def go_home(callback: CallbackQuery, state: FSMContext):
    """Универсальный выход: сбрасывает любой активный сценарий и возвращает
    в главное меню. Заодно 'разворачивает' reply-клавиатуру внизу, если она
    была случайно свёрнута — отправка любого сообщения с reply_markup делает это."""
    await state.clear()
    user_id = await db.get_or_create_user(callback.from_user.id)
    lang = await get_user_lang(user_id)

    await ui.clear_previous(callback.bot, callback.message.chat.id, user_id)
    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.bot.send_message(
        callback.message.chat.id,
        t(lang, "menu.text"),
        reply_markup=main_menu_keyboard(lang),
    )
    # не трекаем: это 'стартовое' сообщение с reply-клавиатурой, как /start
    await callback.answer()
