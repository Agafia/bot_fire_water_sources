"""
Телеграм бот для:
 - сбора информации о местах забора воды мобильной пожарной техникой
 - сохранения сведений в сервисе NextGIS WEB
 - сохранения фотографий в сервисе GoogleDrive

Переписано на aiogram
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from config import Config
from handlers import common_handlers, survey_handlers
from handlers.admin_handlers import admin_router
from middlewares import verification_user, admin_check

# Логирование
logger.add('logs/log_aiogram.log', level='WARNING', rotation='10 MB', compression='zip', catch=True)


async def main() -> None:
    """Точка входа в приложение"""
    # Инициализация бота и диспетчера
    bot = Bot(token=Config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # --- РЕГИСТРАЦИЯ MIDDLEWARE ---
    # Это middleware будет применяться ко всем хендлерам, кроме админских
    dp.message.middleware(verification_user)
    dp.callback_query.middleware(verification_user)

    # Middleware для проверки прав администратора. Применяется только к admin_router
    admin_router.message.middleware(admin_check)

    # --- ПОДКЛЮЧЕНИЕ РОУТЕРОВ ---
    # Сначала регистрируем админский роутер, чтобы его команды имели приоритет
    dp.include_router(admin_router)
    # Затем остальные роутеры
    dp.include_router(survey_handlers.router)
    dp.include_router(common_handlers.router)

    # Запускаем polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
