#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" Обработчики команд администратора """

from aiogram import Router, types
from aiogram.filters import Command
from loguru import logger

from nextgis import update_nextgis_data

# Создаем новый роутер для обработчиков администратора
admin_router = Router()


@admin_router.message(Command("update"))
async def cmd_update(message: types.Message):
    """
    Обработчик команды /update.
    Запускает фоновую задачу обновления данных из NextGIS.
    """
    user_id = message.from_user.id
    logger.info(f"Администратор {user_id} запустил команду /update.")

    # Запускаем задачу Celery асинхронно
    update_nextgis_data.delay()

    # Отправляем пользователю подтверждение
    await message.answer(
        "✅ Команда принята. Запущено фоновое обновление данных из NextGIS. "
        "Это может занять несколько минут."
    )
