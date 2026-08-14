from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from bot import db

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.get_or_create_user(message.from_user.id)
    await message.answer(
        "Привет! Я планировщик постов для твоих Telegram-каналов.\n\n"
        "Как пользоваться:\n"
        "1️⃣ Добавь канал: /addchannel (сначала сделай меня админом канала с правами "
        "публикации и удаления сообщений)\n"
        "2️⃣ Пришли мне текст, фото, видео или альбом (несколько фото/видео разом) — "
        "форматирование и premium-эмодзи сохранятся\n"
        "3️⃣ Выбери, в какие каналы постить (можно сразу несколько), когда удалить "
        "и когда опубликовать\n\n"
        "Команды:\n"
        "/addchannel — подключить канал\n"
        "/channels — список подключённых каналов\n"
        "/removechannel — отключить канал\n"
        "/myposts — список постов, редактирование текста (в т.ч. уже опубликованных)\n"
        "/cancel — отменить текущее действие"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state):
    await state.clear()
    await message.answer("Отменено.")
