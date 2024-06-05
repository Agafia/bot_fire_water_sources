"""
Телеграм бот для:
 - сбора информации о местах забора воды мобильной пожарной техникой
 - сохранения сведений в сервисе NextGIS WEB
 - сохранения фотографий в сервисе GoogleDrive
Автор: Семенихин С.В.
Дата: 2024-03-22
"""

import pytz
import datetime
import telebot
from requests.exceptions import ConnectionError, RequestException
from telebot import types, apihelper
from telebot import custom_filters
from telebot.apihelper import ApiTelegramException
from telebot.storage import StateMemoryStorage  # Хранилище состояний
from telebot.handler_backends import State, StatesGroup  # Состояния
from time import sleep
from pyproj import Transformer  # Преобразование координат между проекциями
from loguru import logger
from notifiers.logging import NotificationHandler
from config import Config  # Параметры записаны в файл config.py
import nextgis  # Функции для запросов к NextGIS WEB
import pydrive

state_storage = StateMemoryStorage()
apihelper.ENABLE_MIDDLEWARE = True
apihelper.SESSION_TIME_TO_LIVE = 5 * 60

# Логирование
tg_handler = NotificationHandler(provider='telegram',
                                 defaults={'token': Config.bot_token, 'chat_id': Config.tg_admin_chat})
logger.add(tg_handler, level='ERROR', catch=True)
logger.add('logs/log.log', level='WARNING', rotation='10 MB', compression='zip', catch=True)
# logger.add(sys.stderr, level="DEBUG", catch=True)


# class ExceptionHandler(telebot.ExceptionHandler):
#     """ Обработчик исключений, в рамках библиотеки telebot """
#     def handle(self, exception):
#         print(f'Обработка исключений, в рамках библиотеки telebot: {exception}')
#         logger.warning(f'Обработка исключений, в рамках библиотеки telebot: {exception}')
#         return True


bot = telebot.TeleBot(token=Config.bot_token, state_storage=state_storage)

# Словарь списков для учёта существующих сообщений в чате
message_ids = dict()


class BotStates(StatesGroup):  # States group - Группа состояний
    fid = State()  # rename or not to a nickname ?
    position = State()  # renamed from location
    checkout = State()
    water = State()
    workable = State()
    work_note = State()
    entrance = State()
    entr_note = State()
    plate_exist = State()
    shot_medium = State()  # renamed from photo_1
    shot_full = State()  # renamed from photo_2
    shot_long = State()  # renamed from photo_3
    shot_plate = State()  # renamed from plate_photo
    save = State()


# Словарь для информирования о состоянии бота на русском
bot_states = {'None':                   'Шаг 0. Диалог не запущен',
              'BotStates:nickname':     'Шаг 1. Числовой ИД',
              'BotStates:position':     'Шаг 2. Геопозиция',
              'BotStates:checkout':     'Шаг 3. Вид контроля',
              'BotStates:water':        'Шаг 4. Наличие воды',
              'BotStates:workable':     'Шаг 5. Установка ПА',
              'BotStates:work_note':    'Шаг 5.1. Почему невозможно установить ПА',
              'BotStates:entrance':     'Шаг 6. Подъезд к ВИ',
              'BotStates:entr_note':    'Шаг 6.1. Почему невозможен подъезд ПА',
              'BotStates:plate_exist':  'Шаг 7. Указатель',
              'BotStates:shot_medium':  'Шаг 8. Узловой снимок',
              'BotStates:shot_full':    'Шаг 9. Обзорный снимок',
              'BotStates:shot_long':    'Шаг 10. Ориентирующий снимок',
              'BotStates:shot_plate':   'Шаг 11. Снимок указателя',
              'BotStates:save':         'Шаг 12. Ожидание сохранения'}

value_lists = {'checkout': ['установка с пуском воды', 'установка без пуска воды', 'осмотр полный', 'осмотр внешний'],
               'workable': ['возможна', 'невозможна', 'не установлено'],
               'entrance': ['возможен', 'невозможен', 'не установлено'],
               'water': ['имеется', 'отсутсвует', 'не установлено'],
               'plate': ['отсутствует', 'есть (по ГОСТ)', 'есть (не ГОСТ)']}


def inline_kb_delete():  # Inline кнопка для удаления текущего сообщения
    kb_rep = types.InlineKeyboardMarkup(row_width=1)
    btn_1 = types.InlineKeyboardButton('Удалить это сообщение', callback_data='delete_message')
    kb_rep.add(btn_1)
    return kb_rep


def msg_id_append(message):  # Добавление поступившего сообщения в список
    try:
        if message.chat.id not in message_ids:
            message_ids[message.chat.id] = []
        message_ids[message.chat.id].append(message.id)
    except Exception as exc:
        logger.critical(f'Ошибка при добавлении сообщения в список: {exc}')


def msg_id_remove(message, delay=0) -> None:  # Удаление 1-го сообщения из списка и чата
    try:
        sleep(delay)
        message_ids[message.chat.id].remove(message.id)
        bot.delete_message(message.chat.id, message.message_id)
    except Exception as exc:
        logger.warning(f'Ошибка удаления одного сообщения: {exc} ({message.content_type}: {message.text})')


def msg_all_delete(message):  # Удаление всех сообщений из списка и чата
    try:
        chunk_size = 100  # Возможно удаление от 1 до 100 сообщений
        chunks = [message_ids[message.chat.id][i:i + chunk_size]
                  for i in range(0, len(message_ids[message.chat.id]), chunk_size)]
        logger.info(f'Очистка чата: сообщений - {len(message_ids[message.chat.id])}, групп - {len(chunks)}')
        for chunk in chunks:
            bot.delete_messages(message.chat.id, chunk)
        del message_ids[message.chat.id]
    except Exception as exc:
        logger.warning(f'Ошибка при удаление всех сообщений: {exc}')


def date_time_now():  # Текущие дата и время
    try:
        current_time = datetime.datetime.now(pytz.timezone(Config.timezone))
        return {'year':     "{:02d}".format(current_time.year),
                'month':    "{:02d}".format(current_time.month),
                'day':      "{:02d}".format(current_time.day),
                'hour':     "{:02d}".format(current_time.hour),
                'minute':   "{:02d}".format(current_time.minute)}
    except Exception as exc:
        logger.critical(f'Ошибка при определении даты и времени: {exc}')


def verification_user(message):  # Верификация пользователя
    # Статус которым не доступна верификация: left-покинувший,  kicked-удалённый
    # Статусы участников группы, которым доступна верификация
    members_status = ['creator', 'administrator', 'member', 'restricted']
    try:
        member = bot.get_chat_member(Config.tg_group_id, message.from_user.id)
        if member.status in members_status:
            return True
        else:
            bot.send_message(message.chat.id,
                             '⚠ Бот доступен только участникам "Группы "ППВ СгМПСГ"', parse_mode='HTML')
            logger.critical(f'Сообщение от незарегистрированного пользователя: {message.from_user.id}')
    except ApiTelegramException as exc:
        logger.critical(f'Ошибка верификации пользователя: {exc.result_json["description"]}')


@logger.catch()
def check_content_type(message, content_type: str):  # Проверка типа контента
    try:
        # Словарь для передачи типа контента на русском
        dict_content_type = {'voice': 'голос', 'audio': 'аудио', 'document': 'файл',
                             'photo': 'фото', 'sticker': 'стикер', 'video': 'видео',
                             'video_note': 'видеозаметка', 'location': 'геопозиция',
                             'text': 'текст', 'contact': 'контакт', 'poll': 'опрос',
                             'dice': 'эмодзи', 'venue': 'место', 'animation': 'анимация',
                             'geolocation': 'геолокация', 'geoposition': 'геопозиция',
                             'media_group': 'медиа-группа', 'integer': 'число'}
        # Доп.типы 'media_group': 'медиагруппа', 'geolocation': 'геолокация', 'integer': 'число'
        my_type = ''
        if message.media_group_id:
            my_type = 'media_group'
        elif message.content_type == 'location' and message.location.live_period:
            my_type = 'geolocation'
        elif message.content_type == 'location' and not message.location.live_period:
            my_type = 'geoposition'
        elif message.content_type == 'text' and message.text.isdigit():
            my_type = 'integer'
        elif not message.media_group_id:
            my_type = message.content_type

        # logger.debug(f'Передан тип данных - {my_type}, ожидается - {content_type}')
        if my_type == content_type:
            return True
        else:
            # Получаем значение из словаря, если отсутсвует оставляем исходное
            typ1 = dict_content_type.get(my_type, my_type)
            typ2 = dict_content_type.get(content_type, content_type)
            msg = bot.send_message(message.chat.id,
                                   f'<i>      - отправлено: {typ1}\n      - ожидается: {typ2}</i>', parse_mode='HTML')
            msg_id_append(msg)
            msg_id_remove(message, 0)
            msg_id_remove(msg, 2)
    except Exception as exc:
        logger.critical(f'Ошибка при проверке типа контента: {exc}')


# Команда стоп при любом состояние
@logger.catch()
@bot.message_handler(state="*", commands=['stop'])
def cmd_stop(message):
    if verification_user(message) and message.chat.type == 'private':
        msg_id_append(message)
        msg_all_delete(message)
        bot.delete_state(bot.user.id, message.chat.id)


# Команда хелп при любом состояние
@logger.catch()
@bot.message_handler(state="*", commands=['help'])
def cmd_help(message):
    if verification_user(message) and message.chat.type == 'private':
        msg_id_append(message)
        kb_rep = types.InlineKeyboardMarkup(row_width=3)
        btn_1 = types.InlineKeyboardButton('БОТ по шагам', url=Config.url_help)
        btn_2 = types.InlineKeyboardButton('Инструкция', url=Config.url_help)
        btn_3 = types.InlineKeyboardButton('WEB карта', url=Config.url_map)
        btn_4 = types.InlineKeyboardButton('Удалить сообщение', callback_data='delete_message')
        kb_rep.add(btn_1, btn_2, btn_3, btn_4)
        msg_send = bot.send_message(message.chat.id,
                                    '📖 <b>Помощь</b>', parse_mode='HTML', reply_markup=kb_rep)
        msg_id_append(msg_send)
        msg_id_remove(message)


# Команда тест при любом состояние
@logger.catch()
@bot.message_handler(state="*", commands=['test'])
def cmd_test(message):
    if verification_user(message) and message.chat.type == 'private':
        msg_id_append(message)
        msg = f'<b>Текущие данные:</b>\n<i>' \
              f'Messages: {message_ids}\n'\
              f'Bot: {bot.user.id} || User: {message.from_user.id}\n' \
              f'Bot_state: {bot.get_state(bot.user.id, message.chat.id)}\n' \
              'Data: </i>'
        if bot.get_state(bot.user.id, message.chat.id):
            with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                msg += f'<i>{data}</i>'
        msg_send = bot.send_message(message.chat.id, msg, parse_mode="html", reply_markup=inline_kb_delete())
        msg_id_append(msg_send)
        msg_id_remove(message)


# Команда старт выполняется при любом состояние (проверка на state=None внутри)
@logger.catch()
@bot.message_handler(commands=['start'])
def cmd_start(message):
    logger.debug(f'Старт пользователя: username - {message.from_user.username}, '
                 f'first_name - {message.from_user.first_name}, last_name - {message.from_user.last_name}, '
                 f'id - {message.from_user.id}')
    if verification_user(message) and message.chat.type == 'private':
        msg_id_append(message)
        if not bot.get_state(bot.user.id, message.chat.id):
            msg_step = bot.send_message(message.chat.id,
                                        '🆔 <b>1. Числовой идентификатор </b>', parse_mode='HTML')
            msg_id_append(msg_step)
            bot.set_state(bot.user.id, BotStates.fid, message.chat.id)
            if len(message.text) > 6:
                arg = message.text.split(maxsplit=1)
                fid = arg[1]
                msg_fid = bot.send_message(message.chat.id, fid)
                msg_id_append(msg_fid)
                process_step(msg_fid)
        else:
            msg = bot.send_message(message.chat.id,
                                   f'<i>Диалог ввода данных уже запущен.\n'
                                   f'Текущий статус: {bot.get_state(bot.user.id, message.chat.id)}</i>',
                                   parse_mode='HTML', reply_markup=inline_kb_delete())
            msg_id_append(msg)
        msg_id_remove(message)


# Шаг 8. Сохранение данных
@logger.catch()
@bot.message_handler(commands=['save'])
def cmd_save(message):
    if verification_user(message) and message.chat.type == 'private':
        msg_id_append(message)
        if bot.get_state(bot.user.id, message.chat.id) == 'BotStates:save':
            with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                msg = f"<b>Передача данных...</b>\n<i>ИД: {data['fid']}</i>"
                msg_send = bot.send_message(message.chat.id, msg, parse_mode="html")
                msg_id_append(msg_send)

                # Заправшиваем feature и создаем для него folder в GoogleDrive
                msg_text = msg_send.text + "\n<i>1. Запрос к NextGIS WEB...</i>"
                bot.edit_message_text(chat_id=msg_send.chat.id,
                                      message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                json_object = nextgis.get_feature(Config.ngw_resource_wi_points, data['fid'], geom='no')
                folder_id = json_object['fields']['ИД_папки_Гугл_диск']
                name = json_object['fields']['name']
                locality = json_object['fields']['Поселение']
                street = json_object['fields']['Улица']
                building = json_object['fields']['Дом']
                landmark = json_object['fields']['Ориентир']
                specification = json_object['fields']['Исполнение']
                folder_name = f"ИД-{data['fid']} {name} {locality}, {street}, {building}"

                msg_text += "\n<i>2. Обращение к папке Google Drive...</i>"
                bot.edit_message_text(chat_id=msg_send.chat.id,
                                      message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                google_folder = pydrive.create_folder(file_id=folder_id, file_name=folder_name,
                                                      parent_folder=Config.parent_folder_id)
                if folder_id != google_folder:
                    msg_text += "\n<i>Добавление каталога в NextGIS WEB...</i>"
                    bot.edit_message_text(chat_id=msg_send.chat.id,
                                          message_id=msg_send.message_id, text=msg_text, parse_mode="html")

                    description = f'<p>Адрес: {locality}, {street}, {building}</p>' \
                                  f'<p>Ориентир: {landmark}</p>' \
                                  f'<p>Исполнение: {specification}</p>'
                    if json_object['fields']['Водоотдача_сети']:
                        description += f"<p>Водоотдача: {json_object['fields']['Водоотдача_сети']}</p>"
                    if json_object['fields']['ИД_папки_Гугл_диск']:
                        description += f"<p><a href='https://drive.google.com/drive/folders/" \
                                       f"{json_object['fields']['ИД_папки_Гугл_диск']}'>Фото на Google диске</a></p>"
                    if json_object['fields']['Ссылка_Гугл_улицы']:
                        description += f"<p><a href='{json_object['fields']['Ссылка_Гугл_улицы']}'>" \
                                       f"Просмотр улиц в Google</a></p>"
                    description += f"<hr><p><a href='{Config.bot_url}={data['fid']}'>Осмотр водоисточника с ИД-{data['fid']}</a></p>"

                    nextgis.ngw_put_feature(Config.ngw_resource_wi_points,
                                            data['fid'],
                                            {'ИД_папки_Гугл_диск': google_folder,
                                             'description': description})

                date_name = f"{data['date_time']['year']}-{data['date_time']['month']}-{data['date_time']['day']}" \
                            f"_{data['date_time']['hour']}:{data['date_time']['minute']}"

                msg_text += "\n<i>3. Передача узлового снимка...</i>"
                bot.edit_message_text(chat_id=msg_send.chat.id,
                                      message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                file_info = bot.get_file(data['shot_medium_id'])
                file_path = file_info.file_path
                file_url = f'https://api.telegram.org/file/bot{Config.bot_token}/{file_path}'
                file_name = f"1_{date_name}"
                pydrive.create_file_from_url(file_url, file_name=file_name, parent_folder=google_folder)

                msg_text += "\n<i>4. Передача обзорного снимка...</i>"
                bot.edit_message_text(chat_id=msg_send.chat.id,
                                      message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                file_info = bot.get_file(data['shot_full_id'])
                file_path = file_info.file_path
                file_url = f'https://api.telegram.org/file/bot{Config.bot_token}/{file_path}'
                file_name = f"2_{date_name}"
                pydrive.create_file_from_url(file_url, file_name=file_name, parent_folder=google_folder)

                msg_text += "\n<i>5. Передача ориентирующего снимка...</i>"
                bot.edit_message_text(chat_id=msg_send.chat.id,
                                      message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                file_info = bot.get_file(data['shot_long_id'])
                file_path = file_info.file_path
                file_url = f'https://api.telegram.org/file/bot{Config.bot_token}/{file_path}'
                file_name = f"3_{date_name}"
                pydrive.create_file_from_url(file_url, file_name=file_name, parent_folder=google_folder)

                if data['shot_plate']:
                    msg_text += "\n<i>6. Передача снимка указателя...</i>"
                    bot.edit_message_text(chat_id=msg_send.chat.id,
                                          message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                    file_info = bot.get_file(data['shot_plate'])
                    file_path = file_info.file_path
                    file_url = f'https://api.telegram.org/file/bot{Config.bot_token}/{file_path}'
                    file_name = f"4_{date_name}"
                    pydrive.create_file_from_url(file_url, file_name=file_name, parent_folder=google_folder)

                msg_text += "\n<i>7. Запись о проверке в NextGIS WEB...</i>"
                bot.edit_message_text(chat_id=msg_send.chat.id,
                                      message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                nextgis.ngw_post_wi_checkup(fid_wi=data['fid'], checkout=data['checkout'],
                                            water=data['water'], workable=data['workable'],
                                            entrance=data['entrance'], plate_exist=data['plate_exist'],
                                            date_time=data['date_time'], geom=data['EPSG_3857'])

                msg_in_grp = f"{data['name']}\n{date_name}"
                bot.send_message(Config.tg_group_id, msg_in_grp)

            bot.delete_state(bot.user.id, message.chat.id)
            msg_text += "\n<i>8. Сохранение данных завершено</i>"
            bot.edit_message_text(chat_id=msg_send.chat.id,
                                  message_id=msg_send.message_id, text=msg_text, parse_mode="html")
            sleep(2)
            msg_all_delete(message)
        else:
            msg_text = ("<i>Ввод данных ещё не завершен.\n"
                        f"Текущий статус: {bot.get_state(bot.user.id, message.chat.id)}</i>")
            msg_send = bot.send_message(message.chat.id, msg_text, parse_mode="html", reply_markup=inline_kb_delete())
            msg_id_append(msg_send)


def step_fid(message):
    if check_content_type(message, content_type='integer'):
        msg_fid = bot.send_message(message.chat.id, f'<i>Запрос к NextGIS WEB ...</i>', parse_mode='HTML')
        msg_id_append(msg_fid)
        feature = nextgis.get_feature(Config.ngw_resource_wi_points, message.text, geom='no')
        if feature:
            name = f"{feature['fields']['name']}\n{feature['fields']['Поселение']}, " \
                   f"{feature['fields']['Улица']}, {feature['fields']['Дом']}"
            bot.edit_message_text(chat_id=msg_fid.chat.id,
                                  message_id=msg_fid.message_id, text=f'<i>{name}</i>', parse_mode="html")
            with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                data['fid'] = int(message.text)
                data['name'] = name
                data['date_time'] = date_time_now()
            return True
        else:
            msg_text = '<i>NextGIS не ответил или не нашёл ИД. \nПроверьте ИД или попробуйте позже</i>'
            bot.edit_message_text(chat_id=msg_fid.chat.id,
                                  message_id=msg_fid.message_id, text=msg_text, parse_mode="html")
            msg_id_remove(msg_fid, 4)
            msg_id_remove(message, 1)


def step_position(message):
    if check_content_type(message, content_type='geoposition'):
        with bot.retrieve_data(bot.user.id, message.chat.id) as data:
            transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857")
            sm = transformer.transform(message.location.latitude, message.location.longitude)
            # data['EPSG_4326'] = message.location.latitude, message.location.longitude
            data['EPSG_3857'] = f'POINT({str(sm[0])} {str(sm[1])})'
        return True


def step_checkout(message):
    if check_content_type(message, content_type='text'):
        if message.text in value_lists['checkout']:
            with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                data['checkout'] = message.text
            return True
        else:  # Если ввели текст самостоятельно, отправим на проверку типа сразу с ошибкой
            check_content_type(message, content_type='из списка')


def step_water(message):
    if check_content_type(message, content_type='text'):
        if message.text in value_lists['water']:
            with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                data['water'] = message.text
            return True
        else:  # Если ввели текст самостоятельно, отправим на проверку типа сразу с ошибкой
            check_content_type(message, content_type='из списка')


def step_workable(message):
    if check_content_type(message, content_type='text'):
        if message.text in value_lists['workable']:
            with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                data['workable'] = message.text
            return True
        else:  # Если ввели текст самостоятельно, отправим на проверку типа сразу с ошибкой
            check_content_type(message, content_type='из списка')


def step_entrance(message):
    if check_content_type(message, content_type='text'):
        if message.text in value_lists['entrance']:
            with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                data['entrance'] = message.text
            return True
        else:  # Если ввели текст самостоятельно, отправим на проверку типа сразу с ошибкой
            check_content_type(message, content_type='из списка')


def step_shot(message, shot_name: str):
    if check_content_type(message, content_type='photo'):
        with bot.retrieve_data(bot.user.id, message.chat.id) as data:
            data[shot_name] = message.photo[-1].file_id
        return True


def step_plate_exist(message):
    if check_content_type(message, content_type='text'):
        if message.text == 'отсутствует':
            with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                data['plate_exist'] = message.text
                data['shot_plate'] = ''
            return 'no'
        elif message.text in value_lists['plate']:
            with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                data['plate_exist'] = message.text
            return 'yes'
        else:  # Если ввели текст самостоятельно, отправим на проверку типа сразу с ошибкой
            check_content_type(message, content_type='из списка')


# Шаги
@logger.catch()
@bot.message_handler(content_types=['voice', 'audio', 'document', 'photo', 'sticker', 'video', 'video_note',
                                    'location', 'text', 'contact', 'poll', 'dice', 'venue', 'animation'])
def process_step(message):
    if verification_user(message) and message.chat.type == 'private':
        msg_id_append(message)
        if bot.get_state(bot.user.id, message.chat.id) == 'BotStates:fid':  # Шаг 1. Идентификатор
            if step_fid(message):
                bot.set_state(bot.user.id, BotStates.position, message.chat.id)
                msg = bot.send_message(message.chat.id, '🌏 <b>2. Геопозиция водоисточника</b>', parse_mode='HTML')
                msg_id_append(msg)

        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:position':  # Шаг 2.Координаты
            if step_position(message):
                # bot.set_state(bot.user.id, BotStates.shot_medium, message.chat.id)
                # msg = bot.send_message(message.chat.id, '📸 💦 <b>Шаг 3. Узловой снимок</b>', parse_mode='HTML')
                # msg_id_append(msg)

                bot.set_state(bot.user.id, BotStates.checkout, message.chat.id)
                kb_rep = types.InlineKeyboardMarkup(row_width=1)
                btn_1 = types.InlineKeyboardButton(value_lists['checkout'][0]+' (🌡 +1°C и выше)',
                                                   callback_data=value_lists['checkout'][0])
                btn_2 = types.InlineKeyboardButton(value_lists['checkout'][1]+' (🌡 0°C и ниже)',
                                                   callback_data=value_lists['checkout'][1])
                btn_3 = types.InlineKeyboardButton(value_lists['checkout'][2]+' (🌡 -15°C и выше)',
                                                   callback_data=value_lists['checkout'][2])
                btn_4 = types.InlineKeyboardButton(value_lists['checkout'][3]+' (🌡 -16°C и ниже)',
                                                   callback_data=value_lists['checkout'][3])
                kb_rep.add(btn_1, btn_2, btn_3, btn_4)
                msg = bot.send_message(message.chat.id,
                                       '✅ <b>3. Способ контроля </b>', parse_mode='HTML', reply_markup=kb_rep)
                msg_id_append(msg)

        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:checkout':  # Шаг 3. Контроль
            if step_checkout(message):
                bot.set_state(bot.user.id, BotStates.water, message.chat.id)

                kb_rep = types.InlineKeyboardMarkup(row_width=3)
                buttons = []
                for i in range(0, len(value_lists['water'])):
                    button = types.InlineKeyboardButton(value_lists['water'][i], callback_data=value_lists['water'][i])
                    buttons.append(button)
                kb_rep.add(*buttons)
                msg = bot.send_message(message.chat.id, '💦 <b>4. Наличие воды </b>',
                                       parse_mode='HTML', reply_markup=kb_rep)
                msg_id_append(msg)

        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:water':  # Шаг 4. Вода
            if step_water(message):
                bot.set_state(bot.user.id, BotStates.workable, message.chat.id)

                kb_rep = types.InlineKeyboardMarkup(row_width=3)
                buttons = []
                for i in range(0, len(value_lists['workable'])):
                    button = types.InlineKeyboardButton(value_lists['workable'][i],
                                                        callback_data=value_lists['workable'][i])
                    buttons.append(button)
                kb_rep.add(*buttons)
                msg = bot.send_message(message.chat.id, '🛠 <b>5. Возможность установки</b>',
                                       parse_mode='HTML', reply_markup=kb_rep)
                msg_id_append(msg)

        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:workable':  # Шаг 5. Установка
            if step_workable(message):
                bot.set_state(bot.user.id, BotStates.entrance, message.chat.id)

                kb_rep = types.InlineKeyboardMarkup(row_width=3)
                buttons = []
                for i in range(0, len(value_lists['entrance'])):
                    button = types.InlineKeyboardButton(value_lists['entrance'][i],
                                                        callback_data=value_lists['entrance'][i])
                    buttons.append(button)
                kb_rep.add(*buttons)
                msg = bot.send_message(message.chat.id, '🚒 <b>6. Возможность подъезда</b>',
                                       parse_mode='HTML', reply_markup=kb_rep)
                msg_id_append(msg)

        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:entrance':  # Шаг 6. Подъезд
            if step_entrance(message):
                bot.set_state(bot.user.id, BotStates.shot_medium, message.chat.id)
                msg = bot.send_message(message.chat.id, '📸 💦 <b>7. Узловой снимок</b>', parse_mode='HTML')
                msg_id_append(msg)

        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:shot_medium':  # Шаг 7. Узловой снимок
            if step_shot(message, 'shot_medium_id'):
                bot.set_state(bot.user.id, BotStates.shot_full, message.chat.id)
                msg = bot.send_message(message.chat.id, '📸 🚒 <b>8. Обзорный снимок</b>', parse_mode='HTML')
                msg_id_append(msg)

        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:shot_full':  # Шаг 8. Обзорный снимок
            if step_shot(message, 'shot_full_id'):
                bot.set_state(bot.user.id, BotStates.shot_long, message.chat.id)
                msg = bot.send_message(message.chat.id, '📸 🏘 <b>9. Ориентирующий снимок</b>', parse_mode='HTML')
                msg_id_append(msg)

        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:shot_long':  # Шаг 9. Ориентирующий снимок
            if step_shot(message, 'shot_long_id'):
                bot.set_state(bot.user.id, BotStates.plate_exist, message.chat.id)

                kb_rep = types.InlineKeyboardMarkup(row_width=3)
                buttons = []
                for i in range(0, len(value_lists['plate'])):
                    button = types.InlineKeyboardButton(value_lists['plate'][i], callback_data=value_lists['plate'][i])
                    buttons.append(button)
                kb_rep.add(*buttons)
                msg = bot.send_message(message.chat.id, '🔀 <b>10. Наличие указателя</b>',
                                       parse_mode='HTML', reply_markup=kb_rep)
                msg_id_append(msg)

        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:plate_exist':  # Шаг 10. Наличие указателя
            plate_exist = step_plate_exist(message)
            if plate_exist == 'yes':
                bot.set_state(bot.user.id, BotStates.shot_plate, message.chat.id)
                msg = bot.send_message(message.chat.id, '📸 🔀 <b>11. Снимок указателя</b>', parse_mode='HTML')
                msg_id_append(msg)
            elif plate_exist == 'no':
                bot.set_state(bot.user.id, BotStates.save, message.chat.id)
                process_step(message)

        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:shot_plate':  # Шаг 11. Фото указателя
            if step_shot(message, 'shot_plate'):
                bot.set_state(bot.user.id, BotStates.save, message.chat.id)
                process_step(message)

        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:save':  # Шаг 12. Сохранеие
            msg = bot.send_message(message.chat.id, '💾 <b>12. Для сохранения введите /save</b>', parse_mode='HTML')
            msg_id_append(msg)

        elif not bot.get_state(bot.user.id, message.chat.id):  # Состояние не задано
            msg_id_remove(message, 2)
            msg = bot.send_message(message.chat.id, '<i>Для запуска введите команду /start</i>', parse_mode='HTML')
            msg_id_append(msg)
            msg_id_remove(msg, 3)
        else:
            msg_id_remove(message, 2)
            msg = bot.send_message(message.chat.id, '<i>Состояние не определено</i>', parse_mode='HTML')
            msg_id_append(msg)
            msg_id_remove(msg, 3)


@bot.callback_query_handler(func=lambda call: True)
def callback_keyboard(call):
    try:
        msg_text = None
        if call.data == 'delete_message':
            msg_id_remove(call.message)
        else:
            msg_text = call.data
        if msg_text:
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.id, reply_markup=None)
            msg = bot.send_message(call.message.chat.id, msg_text)
            msg_id_append(msg)
            process_step(msg)
    except Exception as exc:
        logger.critical(f"Неожиданное исключение: {exc}")


@logger.catch()
def main():
    # Регистрация фильтров
    bot.add_custom_filter(custom_filters.StateFilter(bot))
    bot.add_custom_filter(custom_filters.IsDigitFilter())
    while True:
        try:
            logger.info('Запуск бота')
            # bot.delete_webhook(drop_pending_updates=True)
            bot.infinity_polling(skip_pending=True, logger_level=10, timeout=10, long_polling_timeout=5)
        except ConnectionError as e:
            logger.critical(f'Ошибка подключения: {e}. Повторная попытка через 5 cекунд.')
            # sys.stdout.flush()
            # os.execv(sys.argv[0], sys.argv)
            sleep(5)
        except RequestException as e:
            print('===================================================================================')
            logger.critical(f"Ожиданное исключение: {e}")
            sleep(5)
        except Exception as e:
            logger.critical(f"Неожиданное исключение: {e}")
            # sys.stdout.flush()
            # os.execv(sys.argv[0], sys.argv)
            sleep(5)
            # break  # Завершить цикл на других исключениях


if __name__ == '__main__':
    main()
