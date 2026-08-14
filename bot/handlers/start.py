from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from bot import db
from bot.keyboards import main_menu_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.get_or_create_user(message.from_user.id)
    await message.answer(
        "Привет! Я планировщик постов для твоих Telegram-каналов.\n\n"
        "Как пользоваться:\n"
        "1️⃣ «📢 Мои каналы» → добавь канал (сначала сделай меня админом канала с правами "
        "публикации, редактирования и удаления сообщений)\n"
        "2️⃣ «📝 Создать пост» → пришли текст, фото, видео или альбом — "
        "форматирование и premium-эмодзи сохранятся\n"
        "3️⃣ Выбери, в какие каналы постить (можно сразу несколько), когда удалить "
        "и когда опубликовать\n\n"
        "Меню внизу — основные разделы. «📋 Мои посты» — там же редактирование текста "
        "(в т.ч. уже опубликованных постов), «⚙️ Настройки» — часовой пояс и автоудаление по умолчанию.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state):
    await state.clear()
    await message.answer("Отменено.")
