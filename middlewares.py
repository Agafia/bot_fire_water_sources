import logging
from aiogram.exceptions import TelegramBadRequest
from config import Config
from loguru import logger


async def verification_user(handler, event, data):
    """Проверяет, является ли пользователь участником канала."""
    bot = data['bot']
    members_status = ['creator', 'administrator', 'member', 'restricted']
    try:
        member = await bot.get_chat_member(Config.tg_canal_id, event.from_user.id)
        if member.status in members_status:
            return await handler(event, data)
        else:
            await event.answer('⚠ Бот доступен только участникам "Группы "ППВ СгМПСГ"')
            logger.warning(f'Пользователь {event.from_user.id} не является участником канала.')
    except TelegramBadRequest as exc:
        if "user not found" in exc.message:
            await event.answer('⚠ Вы не являетесь участником канала, необходимого для работы с ботом.')
            logger.warning(f'Пользователь {event.from_user.id} н�� найден в канале.')
        else:
            logger.critical(f'Ошибка API при верификации пользователя: {exc}')
            await event.answer(f'⚠ Ошибка API при верификации: {exc.message}. Убедитесь, что бот является администратором в канале.')
    except Exception as exc:
        logger.critical(f'Неожиданная ошибка верификации пользователя: {exc}')
        await event.answer('⚠ Произошла непредвиденная ошибка верификации. Обратитесь к администратору.')
