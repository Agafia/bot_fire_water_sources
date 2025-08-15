from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from lexicon import value_lists
from config import Config

def get_help_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text='БОТ по шагам', url=Config.url_help))
    builder.row(InlineKeyboardButton(text='Инструкция', url=Config.url_help))
    builder.row(InlineKeyboardButton(text='WEB карта', url=Config.url_map))
    builder.row(InlineKeyboardButton(text='Удалить сообщение', callback_data='delete_message'))
    return builder.as_markup()

def get_checkout_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text=value_lists['checkout'][0] + ' (🌡 +1°C и выше)', callback_data=value_lists['checkout'][0])
    builder.button(text=value_lists['checkout'][1] + ' (🌡 0°C и ниже)', callback_data=value_lists['checkout'][1])
    builder.button(text=value_lists['checkout'][2] + ' (🌡 -15°C и выше)', callback_data=value_lists['checkout'][2])
    builder.button(text=value_lists['checkout'][3] + ' (🌡 -16°C и ниже)', callback_data=value_lists['checkout'][3])
    builder.adjust(1)  # 1 кнопка в строке
    return builder.as_markup()

def get_water_keyboard():
    builder = InlineKeyboardBuilder()
    for item in value_lists['water']:
        builder.button(text=item, callback_data=item)
    builder.adjust(3)  # 3 кнопки в строке
    return builder.as_markup()

def get_workable_keyboard():
    builder = InlineKeyboardBuilder()
    for item in value_lists['workable']:
        builder.button(text=item, callback_data=item)
    builder.adjust(3)
    return builder.as_markup()

def get_entrance_keyboard():
    builder = InlineKeyboardBuilder()
    for item in value_lists['entrance']:
        builder.button(text=item, callback_data=item)
    builder.adjust(3)
    return builder.as_markup()

def get_plate_keyboard():
    builder = InlineKeyboardBuilder()
    for item in value_lists['plate']:
        builder.button(text=item, callback_data=item)
    builder.adjust(3)
    return builder.as_markup()
