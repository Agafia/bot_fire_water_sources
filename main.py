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
import datetime
import pytz

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest

from pyproj import Transformer
from loguru import logger
from notifiers.logging import NotificationHandler


from config import Config
import nextgis
import pydrive
import templates

# Логирование
# tg_handler = NotificationHandler(provider='telegram',
#                                  defaults={'token': Config.bot_token, 'chat_id': Config.tg_admin_chat})
# logger.add(tg_handler, level='ERROR', catch=True)
logger.add('logs/log_aiogram.log', level='WARNING', rotation='10 MB', compression='zip', catch=True)

# Инициализация бота и диспетчера
bot = Bot(token=Config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


class BotStates(StatesGroup):
    fid = State()
    position = State()
    checkout = State()
    water = State()
    workable = State()
    work_note = State()
    entrance = State()
    entr_note = State()
    plate_exist = State()
    shot_medium = State()
    shot_full = State()
    shot_long = State()
    shot_plate = State()
    save = State()


# Словарь для информирования о состоянии бота на русском
bot_states = {'None': 'Шаг 0. Диалог не запущен',
              'BotStates:fid': 'Шаг 1. Числовой ИД',
              'BotStates:position': 'Шаг 2. Геопозиция',
              'BotStates:checkout': 'Шаг 3. Вид контроля',
              'BotStates:water': 'Шаг 4. Наличие воды',
              'BotStates:workable': 'Шаг 5. Установка ПА',
              'BotStates:work_note': 'Шаг 5.1. Почему невозможно установить ПА',
              'BotStates:entrance': 'Шаг 6. Подъезд к ВИ',
              'BotStates:entr_note': 'Шаг 6.1. Почему невозможен подъезд ПА',
              'BotStates:plate_exist': 'Шаг 7. Указатель',
              'BotStates:shot_medium': 'Шаг 8. Узловой снимок',
              'BotStates:shot_full': 'Шаг 9. Обзорный снимок',
              'BotStates:shot_long': 'Шаг 10. Ориентирующий снимок',
              'BotStates:shot_plate': 'Шаг 11. Снимок указателя',
              'BotStates:save': 'Шаг 12. Ожидание сохранения'}

value_lists = {'checkout': ['установка с пуском воды', 'установка без пуска воды', 'осмотр полный', 'осмотр внешний'],
               'workable': ['возможна', 'невозможна', 'не установлено'],
               'entrance': ['возможен', 'невозможен', 'не установлено'],
               'water': ['имеется', 'отсутствует', 'не установлено'],
               'plate': ['отсутствует', 'есть (по ГОСТ)', 'есть (не ГОСТ)']}


# --- Middleware для верификации пользователя ---
async def verification_user(handler, event, data):
    """Проверяет, является ли пользователь участником канала."""
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
            logger.warning(f'Пользователь {event.from_user.id} не н��йден в канале.')
        else:
            logger.critical(f'Ошибка API при верификации пользователя: {exc}')
            await event.answer(f'⚠ Ошибка API при верификации: {exc.message}. Убедитесь, что бот является администратором в канале.')
    except Exception as exc:
        logger.critical(f'Неожиданная ошибка верификации пользователя: {exc}')
        await event.answer('⚠ Произошла непредвиденная ошибка верификации. Обратитесь к администратору.')


# --- Вспомогательные функции ---
def date_time_now():
    """Возвращает текущие дату и время."""
    try:
        current_time = datetime.datetime.now(pytz.timezone(Config.timezone))
        return {'year':     "{:02d}".format(current_time.year),
                'month':    "{:02d}".format(current_time.month),
                'day':      "{:02d}".format(current_time.day),
                'hour':     "{:02d}".format(current_time.hour),
                'minute':   "{:02d}".format(current_time.minute)}
    except Exception as exc:
        logger.critical(f'Ошибка при определении даты и времени: {exc}')
        return None


# --- Обработчики команд ---
@dp.message(Command('stop'))
async def cmd_stop(message: Message, state: FSMContext):
    """Обработчик команды /stop."""
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer("Диалог прерван. Все данные удалены.")
    else:
        await message.answer("Нет активного диалога для остановки.")
    await message.delete()


@dp.message(Command('help'))
async def cmd_help(message: Message):
    """Обработчик команды /help."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text='БОТ по шагам', url=Config.url_help))
    builder.row(InlineKeyboardButton(text='Инструкция', url=Config.url_help))
    builder.row(InlineKeyboardButton(text='WEB карта', url=Config.url_map))
    builder.row(InlineKeyboardButton(text='Удалить сообщение', callback_data='delete_message'))
    await message.answer('📖 <b>Помощь</b>', reply_markup=builder.as_markup())


@dp.callback_query(F.data == 'delete_message')
async def delete_message_callback(callback: CallbackQuery):
    """Удаляет сообщение, к которому привязана кнопка."""
    await callback.message.delete()


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start."""
    logger.debug(f'Старт пользователя: username - {message.from_user.username}, '
                 f'first_name - {message.from_user.first_name}, last_name - {message.from_user.last_name}, '
                 f'id - {message.from_user.id}')

    current_state = await state.get_state()
    if current_state is not None:
        state_name = bot_states.get(current_state, "Неизвестное состояние")
        await message.answer(f'<i>Диалог ввода данных уже запущен.\n'
                             f'Текущий статус: {state_name}</i>')
        return

    # Проверяем, есть ли аргументы в команде /start
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        fid = args[1]
        await message.answer(f'🆔 <b>1. Числовой идентификатор:</b> {fid}')
        await state.set_state(BotStates.fid)
        # Создаем "фейковое" сообщение, чтобы передать его в следующий шаг
        fake_message = message
        fake_message.text = fid
        await process_step_fid(fake_message, state)
    else:
        await state.set_state(BotStates.fid)
        await message.answer('🆔 <b>1. Числовой идентификатор </b>')


# --- Обработчики состояний ---
@dp.message(BotStates.fid)
async def process_step_fid(message: Message, state: FSMContext):
    """Шаг 1. Обработка числового идентификатора."""
    if not message.text.isdigit():
        await message.answer("⚠ Ожидается числовой идентификатор.")
        return

    msg_fid = await message.answer('<i>Запрос к NextGIS WEB ...</i>')
    
    try:
        # Запускаем синхронную функцию в асинхронном контексте
        loop = asyncio.get_event_loop()
        feature = await loop.run_in_executor(
            None,
            lambda: nextgis.get_feature(Config.ngw_resource_wi_points, message.text, geom='no')
        )

        if feature:
            name = f"{feature['fields']['name']}\n{feature['fields']['Поселение']}, " \
                   f"{feature['fields']['Улица']}, {feature['fields']['Дом']}"
            await msg_fid.edit_text(f'<i>{name}</i>')
            await state.update_data(fid=int(message.text), name=name, date_time=date_time_now())
            await state.set_state(BotStates.position)
            await message.answer('🌏 <b>2. Геопозиция водоисточника</b>')
        else:
            await msg_fid.edit_text('<i>NextGIS не ответил или не нашёл ИД. \nПроверьте ИД или попробуйте позже</i>')
            await asyncio.sleep(4)
            await msg_fid.delete()
    except Exception as e:
        logger.critical(f"Ошибка на шаге 1 (fid): {e!r}")
        await msg_fid.edit_text(f"<b>Произошла ошибка при запросе к NextGIS.</b>\n"
                                f"<i>Пожалуйста, проверьте настройки и доступность сервиса.</i>\n"
                                f"<code>Ошибка: {e}</code>")
        await state.clear()


@dp.message(BotStates.position, F.location)
async def process_step_position(message: Message, state: FSMContext):

    """Шаг 2. Обработка геопозиции."""
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857")
    
    loop = asyncio.get_event_loop()
    sm = await loop.run_in_executor(None, transformer.transform, message.location.latitude, message.location.longitude)
    
    await state.update_data(EPSG_3857=f'POINT({str(sm[0])} {str(sm[1])})')
    await state.set_state(BotStates.checkout)

    builder = InlineKeyboardBuilder()
    builder.button(text=value_lists['checkout'][0]+' (🌡 +1°C и выше)', callback_data=value_lists['checkout'][0])
    builder.button(text=value_lists['checkout'][1]+' (🌡 0°C и ниже)', callback_data=value_lists['checkout'][1])
    builder.button(text=value_lists['checkout'][2]+' (🌡 -15°C и выше)', callback_data=value_lists['checkout'][2])
    builder.button(text=value_lists['checkout'][3]+' (🌡 -16°C и ниже)', callback_data=value_lists['checkout'][3])
    builder.adjust(1) # 1 кнопка в строке
    
    await message.answer('✅ <b>3. Способ контроля </b>', reply_markup=builder.as_markup())


@dp.callback_query(BotStates.checkout)
async def process_step_checkout(callback: CallbackQuery, state: FSMContext):
    """Шаг 3. Обработка способа контроля."""
    await callback.message.edit_text(f"Выбрано: {callback.data}", reply_markup=None)
    await state.update_data(checkout=callback.data)
    await state.set_state(BotStates.water)

    builder = InlineKeyboardBuilder()
    for item in value_lists['water']:
        builder.button(text=item, callback_data=item)
    builder.adjust(3) # 3 кнопки в строке

    await callback.message.answer('💦 <b>4. Наличие воды </b>', reply_markup=builder.as_markup())


@dp.callback_query(BotStates.water)
async def process_step_water(callback: CallbackQuery, state: FSMContext):
    """Шаг 4. Обработка наличия воды."""
    await callback.message.edit_text(f"Выбрано: {callback.data}", reply_markup=None)
    await state.update_data(water=callback.data)
    await state.set_state(BotStates.workable)

    builder = InlineKeyboardBuilder()
    for item in value_lists['workable']:
        builder.button(text=item, callback_data=item)
    builder.adjust(3)

    await callback.message.answer('🛠 <b>5. Возможность установки</b>', reply_markup=builder.as_markup())


@dp.callback_query(BotStates.workable)
async def process_step_workable(callback: CallbackQuery, state: FSMContext):
    """Шаг 5. Обработка возможности установки."""
    await callback.message.edit_text(f"Выбрано: {callback.data}", reply_markup=None)
    await state.update_data(workable=callback.data)
    await state.set_state(BotStates.entrance)

    builder = InlineKeyboardBuilder()
    for item in value_lists['entrance']:
        builder.button(text=item, callback_data=item)
    builder.adjust(3)

    await callback.message.answer('🚒 <b>6. Возможность подъезда</b>', reply_markup=builder.as_markup())


@dp.callback_query(BotStates.entrance)
async def process_step_entrance(callback: CallbackQuery, state: FSMContext):
    """Шаг 6. Обработка возможности подъезда."""
    await callback.message.edit_text(f"Выбрано: {callback.data}", reply_markup=None)
    await state.update_data(entrance=callback.data)
    await state.set_state(BotStates.shot_medium)
    await callback.message.answer('📸 💦 <b>7. Узловой снимок</b>')


async def process_shot(message: Message, state: FSMContext, shot_name: str, next_state: State, next_prompt: str):
    """Общая функция для обработки фотографий."""
    if not message.photo:
        await message.answer("⚠ Ожидается фотография.")
        return
    
    await state.update_data({shot_name: message.photo[-1].file_id})
    await state.set_state(next_state)
    if next_prompt:
        await message.answer(next_prompt)


@dp.message(BotStates.shot_medium, F.photo)
async def process_step_shot_medium(message: Message, state: FSMContext):
    """Шаг 7. Обработка узлового снимка."""
    await process_shot(message, state, 'shot_medium_id', BotStates.shot_full, '📸 🚒 <b>8. Обзорный снимок</b>')


@dp.message(BotStates.shot_full, F.photo)
async def process_step_shot_full(message: Message, state: FSMContext):
    """Шаг 8. Обработка обзорного снимка."""
    await process_shot(message, state, 'shot_full_id', BotStates.shot_long, '📸 🏘 <b>9. Ориентирующий снимок</b>')


@dp.message(BotStates.shot_long, F.photo)
async def process_step_shot_long(message: Message, state: FSMContext):
    """Шаг 9. Обработка ориентирующего снимка."""
    await process_shot(message, state, 'shot_long_id', BotStates.plate_exist, '')
    
    builder = InlineKeyboardBuilder()
    for item in value_lists['plate']:
        builder.button(text=item, callback_data=item)
    builder.adjust(3)
    await message.answer('🔀 <b>10. Наличие указателя</b>', reply_markup=builder.as_markup())


@dp.callback_query(BotStates.plate_exist)
async def process_step_plate_exist(callback: CallbackQuery, state: FSMContext):
    """Шаг 10. Обработка наличия указателя."""
    await callback.message.edit_text(f"Выбрано: {callback.data}", reply_markup=None)
    await state.update_data(plate_exist=callback.data)

    if callback.data == 'отсутствует':
        await state.update_data(shot_plate=None)
        await state.set_state(BotStates.save)
        await callback.message.answer('💾 <b>12. Для сохранения введите /save</b>')
    else:
        await state.set_state(BotStates.shot_plate)
        await callback.message.answer('📸 🔀 <b>11. Снимок указателя</b>')


@dp.message(BotStates.shot_plate, F.photo)
async def process_step_shot_plate(message: Message, state: FSMContext):
    """Шаг 11. Обработка снимка указателя."""
    await process_shot(message, state, 'shot_plate', BotStates.save, '💾 <b>12. Для сохранения введите /save</b>')


@dp.message(Command('save'))
async def cmd_save(message: Message, state: FSMContext):
    """Обработчик команды /save."""
    current_state = await state.get_state()
    if current_state != BotStates.save:
        state_name = bot_states.get(current_state, "Неизвестное состояние")
        await message.answer(f"<i>Ввод данных ещё не завершен.\nТекущий статус: {state_name}</i>")
        return

    data = await state.get_data()
    msg_text = f"<b>Передача данных...</b>\n<i>ИД: {data['fid']}</i>"
    msg = await message.answer(msg_text)

    loop = asyncio.get_event_loop()

    # try:
    # 1. Запрос к NextGIS WEB
    msg_text += "\n<i>1. Запрос к NextGIS WEB...</i>"
    await msg.edit_text(msg_text)
    json_object = await loop.run_in_executor(
        None,
        lambda: nextgis.get_feature(Config.ngw_resource_wi_points, data['fid'], geom='no')
    )
    folder_id = json_object['fields']['ИД_папки_Гугл_диск']
    folder_name = f"ИД-{data['fid']} {json_object['fields']['name']} {json_object['fields']['Поселение']}, {json_object['fields']['Улица']}, {json_object['fields']['Дом']}"

    # 2. Обращение к папке Google Drive
    msg_text += "\n<i>2. Обращение к папке Google Drive...</i>"
    await msg.edit_text(msg_text)
    google_folder = await loop.run_in_executor(None, pydrive.create_folder, folder_id, folder_name, Config.parent_folder_id)

    if folder_id != google_folder:
        msg_text += "\n<i>Добавление каталога в NextGIS WEB...</i>"
        await msg.edit_text(msg_text)
        description = await loop.run_in_executor(None, templates.description_water_intake,
                                                 data['fid'], json_object['fields']['Поселение'],
                                                 json_object['fields']['Улица'], json_object['fields']['Дом'],
                                                 json_object['fields']['Ориентир'], json_object['fields']['Исполнение'],
                                                 json_object['fields']['Водоотдача_сети'], google_folder,
                                                 json_object['fields']['Ссылка_Гугл_улицы'],
                                                 json_object['fields']['ИД_хоз_субъекта'])
        fields_values = {'description': description, 'ИД_папки_Гугл_диск': google_folder}
        await loop.run_in_executor(
            None,
            lambda: nextgis.ngw_put_feature(Config.ngw_resource_wi_points, data['fid'], fields_values, description=description)
        )

    date_name = f"{data['date_time']['year']}-{data['date_time']['month']}-{data['date_time']['day']}" \
                f"_{data['date_time']['hour']}:{data['date_time']['minute']}"

    # 3-6. Передача снимков
    photo_steps = [
        ('shot_medium_id', '3. Передача узлового снимка...'),
        ('shot_full_id', '4. Передача обзорного снимка...'),
        ('shot_long_id', '5. Передача ориентирующего снимка...'),
        ('shot_plate', '6. Передача снимка указателя...')
    ]

    for i, (shot_key, step_text) in enumerate(photo_steps):
        if data.get(shot_key):
            msg_text += f"\n<i>{step_text}</i>"
            await msg.edit_text(msg_text)
            file_info = await bot.get_file(data[shot_key])
            file_url = f'https://api.telegram.org/file/bot{Config.bot_token}/{file_info.file_path}'
            file_name = f"{i+1}_{date_name}"
            await loop.run_in_executor(None, pydrive.create_file_from_url, file_url, file_name, google_folder)

    # 7. Запись о проверке в NextGIS WEB
    msg_text += "\n<i>7. Запись о проверке в NextGIS WEB...</i>"
    await msg.edit_text(msg_text)
    # logger.info(data['fid'], data['checkout'], data['water'],
    #             data['workable'], data['entrance'], data['plate_exist'],
    #             data['date_time'], data['EPSG_3857'])
    await loop.run_in_executor(None, nextgis.ngw_post_wi_checkup,
                                data['fid'], data['checkout'], data['water'],
                                data['workable'], data['entrance'], data['plate_exist'],
                                data['date_time'], data['EPSG_3857'])


    # Отправка сообщения в канал
    msg_in_grp = f"{data['name']}\n{date_name}"
    await bot.send_message(Config.tg_canal_id, msg_in_grp)

    msg_text += "\n<i>8. Сохранение данных завершено</i>"
    await msg.edit_text(msg_text)
    await state.clear()
    await asyncio.sleep(2)
    await msg.delete()

    # except Exception as e:
    #     logger.error(f"Ошибка при сохранении: {e}")
    #     await msg.edit_text(f"<b>Произошла ошибка при сохранении данных.</b>\n"
    #                         f"<i>Обратитесь к администратору.</i>\n"
    #                         f"<code>{e}</code>")
    #     await state.clear()


@dp.message()
async def process_unknown_messages(message: Message, state: FSMContext):
    """Обработчик для любых других сообщений."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer('<i>Для запуска введите команду /start</i>')
    else:
        state_name = bot_states.get(current_state, "Неизвестное с��стояние")
        await message.answer(f'<i>Неверный ввод для текущего шага: {state_name}</i>\n'
                             f'<i>Для отмены введите /stop</i>')


async def main() -> None:
    """Точка входа в приложение"""
    # Регистрируем middleware для всех message и callback_query
    dp.message.middleware(verification_user)
    dp.callback_query.middleware(verification_user)

    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
