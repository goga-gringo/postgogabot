import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN
from bot import db
from bot.scheduler import publisher_loop, cleaner_loop, old_posts_cleanup_loop, broadcast_cleaner_loop
from bot.handlers import start, common, broadcast, channels, edit, menu, posts

logging.basicConfig(level=logging.INFO)


async def main():
    await db.init_pool()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(common.router)
    dp.include_router(broadcast.router)
    dp.include_router(channels.router)
    dp.include_router(edit.router)
    dp.include_router(menu.router)
    dp.include_router(posts.router)

    asyncio.create_task(publisher_loop(bot))
    asyncio.create_task(cleaner_loop(bot))
    asyncio.create_task(old_posts_cleanup_loop())
    asyncio.create_task(broadcast_cleaner_loop(bot))

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
