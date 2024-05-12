"""
Телеграм бот для:
 - сбора информации о местах забора воды мобильной пожарной техникой
 - сохранения сведений в сервисе NextGIS WEB
 - сохранения фотографий в сервисе GoogleDrive
Автор: Семенихин С.В.
Дата: 2024-03-22
"""
from requests.exceptions import ConnectionError, ConnectTimeout, RequestException
import pytz
import datetime
import telebot
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


class ExceptionHandler(telebot.ExceptionHandler):
    """ Обработчик исключений, в рамках библиотеки telebot """
    def handle(self, exception):
        print(f'Обработка исключений, в рамках библиотеки telebot: {exception}')
        logger.warning(f'Обработка исключений, в рамках библиотеки telebot: {exception}')
        return True


bot = telebot.TeleBot(token=Config.bot_token, state_storage=state_storage)

# Словарь списков для учёта существующих сообщений в чате
message_ids = dict()


class BotStates(StatesGroup):  # States group - Группа состояний
    fid = State()
    location = State()
    photo_1 = State()
    photo_2 = State()
    photo_3 = State()
    plate_exist = State()
    plate_photo = State()
    save = State()


# Словарь для информирования о состоянии бота на русском
bot_states = {'None':                'Шаг 0. Диалог не запущен',
              'BotStates:fid':       'Шаг 1. Числовой ИД',
              'BotStates:location':  'Шаг 1. Числовой ИД',
              'BotStates:photo_1':   'Шаг 1. Числовой ИД',
              'BotStates:photo_2':   'Шаг 1. Числовой ИД',
              'BotStates:photo_3':   'Шаг 1. Числовой ИД',
              'BotStates:plate_exist':   'Шаг 1. Числовой ИД',
              'BotStates:plate_photo':   'Шаг 1. Числовой ИД',
              'BotStates:save':      'Шаг 1. Числовой ИД'}


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
        # logger.warning(f'Ошибка при добавлении сообщения в список: {exc}')
        logger.critical(f'Ошибка при добавлении сообщения в список: {exc}')


def msg_id_remove(message, delay=0) -> None:  # Удаление 1-го сообщения из списка и чата
    try:
        sleep(delay)
        message_ids[message.chat.id].remove(message.id)
        bot.delete_message(message.chat.id, message.message_id)
    except Exception as exc:
        logger.warning(f'Ошибка удаления одного сообщения: {exc}')


def msg_ids_clear(message):  # Удаление всех сообщений из списка и чата
    try:
        chunk_size = 100  # Возможно удаление от 1 до 100 сообщений
        chunks = [message_ids[message.chat.id][i:i + chunk_size]
                  for i in range(0, len(message_ids[message.chat.id]), chunk_size)]
        logger.info(f'Очистка чата: сообщений - {len(message_ids[message.chat.id])}, групп - {len(chunks)}')
        for chunk in chunks:
            # bot.delete_messages(message.chat.id, message_ids[message.chat.id])
            bot.delete_messages(message.chat.id, chunk)
        del message_ids[message.chat.id]
    except Exception as exc:
        logger.warning(f'Ошибка при удаление всех сообщений: {exc}')


def date_time_now():  # Текущие дата и время
    try:
        current_time = datetime.datetime.now(pytz.timezone(Config.timezone))
        return {'year': "{:02d}".format(current_time.year),
                'month': "{:02d}".format(current_time.month),
                'day': "{:02d}".format(current_time.day),
                'hour': "{:02d}".format(current_time.hour),
                'minute': "{:02d}".format(current_time.minute)}
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
        # Доп. типы 'media_group': 'медиагруппа', 'geolocation': 'геолокация', 'integer': 'число'
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
                                   f'<i>      - отправлен: {typ1}\n      - ожидается: {typ2}</i>', parse_mode='HTML')
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
        msg_ids_clear(message)
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
                                        '🆔 <b>Шаг 1. Числовой ИД водоисточника</b>', parse_mode='HTML')
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
                msg = f"<b>Отправка данных:</b>\n<i>ИД: {data['fid']}</i>"
                msg_send = bot.send_message(message.chat.id, msg, parse_mode="html")
                msg_id_append(msg_send)

                # Заправшиваем feature и создаем для него folder в GoogleDrive
                msg_text = msg_send.text + "\n<i>1. Запрос к NextGIS WEB...</i>"
                bot.edit_message_text(chat_id=msg_send.chat.id,
                                      message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                json_object = nextgis.get_feature(Config.ngw_resource_wi_points, data['fid'], geom='no')
                folder_id = json_object['fields']['google_folder_id']
                name = json_object['fields']['name']
                locality = json_object['fields']['wi_addr_locality']
                street = json_object['fields']['wi_addr_street']
                building = json_object['fields']['wi_addr_building']
                landmark = json_object['fields']['wi_landmark']
                specification = json_object['fields']['wi_specification']
                folder_name = f"ИД-{data['fid']} {name} {locality}, {street}, {building}"

                msg_text += "\n<i>2. Обращение к папке Google Drive...</i>"
                bot.edit_message_text(chat_id=msg_send.chat.id,
                                      message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                google_folder = pydrive.create_folder(file_id=folder_id, file_name=folder_name,
                                                      parent_folder=Config.parent_folder_id)
                if folder_id != google_folder:
                    msg_text += "\n<i>Запись папки в NextGIS WEB...</i>"
                    bot.edit_message_text(chat_id=msg_send.chat.id,
                                          message_id=msg_send.message_id, text=msg_text, parse_mode="html")

                    description = f'<p>Адрес: {locality}, {street}, {building}</p>' \
                                  f'<p>Ориентир: {landmark}</p>' \
                                  f'<p>Исполнение: {specification}</p>'
                    if json_object['fields']['ws_flow_rate_water']:
                        description += f"<p>Водоотдача: {json_object['fields']['ws_flow_rate_water']}</p>"
                    if json_object['fields']['link_google_drive']:
                        description += f"<p><a href='{json_object['fields']['link_google_drive']}'>" \
                                       f"Фото на Google диске</a></p>"
                    if json_object['fields']['link_google_street']:
                        description += f"<p><a href='{json_object['fields']['link_google_street']}'>" \
                                       f"Просмотр улиц в Google</a></p>"
                    description += f"<hr><p><a href='{Config.bot_url}={data['fid']}'>Осмотр водоисточника</a></p>"

                    nextgis.ngw_put_feature(Config.ngw_resource_wi_points,
                                            data['fid'],
                                            {'google_folder_id': google_folder,
                                             'link_google_drive':
                                                 f'https://drive.google.com/drive/folders/{google_folder}',
                                             'description': description})

                date_name = f"{data['date_time']['year']}-{data['date_time']['month']}-{data['date_time']['day']}" \
                            f"_{data['date_time']['hour']}:{data['date_time']['minute']}"

                msg_text += "\n<i>3. Передача узлового снимка...</i>"
                bot.edit_message_text(chat_id=msg_send.chat.id,
                                      message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                file_info = bot.get_file(data['photo_1_id'])
                file_path = file_info.file_path
                file_url = f'https://api.telegram.org/file/bot{Config.bot_token}/{file_path}'
                file_name = f"1_{date_name}"
                pydrive.create_file_from_url(file_url, file_name=file_name, parent_folder=google_folder)

                msg_text += "\n<i>4. Передача обзорного снимка...</i>"
                bot.edit_message_text(chat_id=msg_send.chat.id,
                                      message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                file_info = bot.get_file(data['photo_2_id'])
                file_path = file_info.file_path
                file_url = f'https://api.telegram.org/file/bot{Config.bot_token}/{file_path}'
                file_name = f"2_{date_name}"
                pydrive.create_file_from_url(file_url, file_name=file_name, parent_folder=google_folder)

                msg_text += "\n<i>5. Передача ориентирующего снимка...</i>"
                bot.edit_message_text(chat_id=msg_send.chat.id,
                                      message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                file_info = bot.get_file(data['photo_3_id'])
                file_path = file_info.file_path
                file_url = f'https://api.telegram.org/file/bot{Config.bot_token}/{file_path}'
                file_name = f"3_{date_name}"
                pydrive.create_file_from_url(file_url, file_name=file_name, parent_folder=google_folder)

                if data['plate_photo']:
                    msg_text += "\n<i>6. Передача снимка указателя...</i>"
                    bot.edit_message_text(chat_id=msg_send.chat.id,
                                          message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                    file_info = bot.get_file(data['plate_photo'])
                    file_path = file_info.file_path
                    file_url = f'https://api.telegram.org/file/bot{Config.bot_token}/{file_path}'
                    file_name = f"4_{date_name}"
                    pydrive.create_file_from_url(file_url, file_name=file_name, parent_folder=google_folder)

                msg_text += "\n<i>7. Запись о проверке в NextGIS WEB...</i>"
                bot.edit_message_text(chat_id=msg_send.chat.id,
                                      message_id=msg_send.message_id, text=msg_text, parse_mode="html")
                nextgis.ngw_post_wi_checkup(data['fid'], data['plate_exist'], data['date_time'], data['EPSG_3857'])

                msg_in_grp = f"{data['name']}\n{date_name}"
                bot.send_message(Config.tg_group_id, msg_in_grp)

            bot.delete_state(bot.user.id, message.chat.id)
            msg_text += "\n<i>8. Сохранение данных выполнено</i>"
            bot.edit_message_text(chat_id=msg_send.chat.id,
                                  message_id=msg_send.message_id, text=msg_text, parse_mode="html")
            sleep(2)
            msg_ids_clear(message)
        else:
            msg_text = ("<i>Ввод данных ещё не завершен.\n"
                        f"Текущий статус: {bot.get_state(bot.user.id, message.chat.id)}</i>")
            msg_send = bot.send_message(message.chat.id, msg_text, parse_mode="html", reply_markup=inline_kb_delete())
            msg_id_append(msg_send)
        msg_id_remove(message)


# Шаги
@logger.catch()
@bot.message_handler(content_types=['voice', 'audio', 'document', 'photo', 'sticker', 'video', 'video_note',
                                    'location', 'text', 'contact', 'poll', 'dice', 'venue', 'animation'])
def process_step(message):
    # print('process_step', bot.get_state(bot.user.id, message.chat.id), message)
    if verification_user(message) and message.chat.type == 'private':
        msg_id_append(message)

        # Шаг 1. Получение идентификатора
        if bot.get_state(bot.user.id, message.chat.id) == 'BotStates:fid':
            if check_content_type(message, content_type='integer'):
                msg = bot.send_message(message.chat.id, f'<i>Запрос к NextGIS...</i>', parse_mode='HTML')
                msg_id_append(msg)
                feature = nextgis.get_feature(Config.ngw_resource_wi_points, message.text, geom='no')
                if feature:
                    name = f"{feature['fields']['name']}\n{feature['fields']['wi_addr_locality']}, " \
                           f"{feature['fields']['wi_addr_street']}, {feature['fields']['wi_addr_building']}"
                    bot.edit_message_text(chat_id=msg.chat.id,
                                          message_id=msg.message_id, text=f'<i>{name}</i>', parse_mode="html")
                    msg = bot.send_message(message.chat.id,
                                           '🌏 <b>Шаг 2. Геопозиция</b>', parse_mode='HTML')
                    msg_id_append(msg)
                    bot.set_state(bot.user.id, BotStates.location, message.chat.id)
                    with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                        data['fid'] = int(message.text)
                        data['name'] = name
                        data['date_time'] = date_time_now()
                else:
                    msg_text = '<i>NextGIS не ответил или не нашёл ИД. \nПроверьте ИД или попробуйте позже</i>'
                    bot.edit_message_text(chat_id=msg.chat.id,
                                          message_id=msg.message_id, text=msg_text, parse_mode="html")
                    msg_id_append(msg)
                    msg_id_remove(msg, 4)
                    msg_id_remove(message, 1)

        # Шаг 2. Получение координат
        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:location':
            if check_content_type(message, content_type='geoposition'):
                msg = bot.send_message(message.chat.id,
                                       '📸 💦 <b>Шаг 3. Узловой снимок</b>', parse_mode='HTML')
                msg_id_append(msg)
                bot.set_state(bot.user.id, BotStates.photo_1, message.chat.id)
                with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857")
                    sm = transformer.transform(message.location.latitude, message.location.longitude)
                    data['EPSG_4326'] = message.location.latitude, message.location.longitude
                    data['EPSG_3857'] = f'POINT({str(sm[0])} {str(sm[1])})'

        # Шаг 3. Получение узлового фото
        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:photo_1':
            if check_content_type(message, content_type='photo'):
                msg = bot.send_message(message.chat.id,
                                       '📸 🚒 <b>Шаг 4. Обзорный снимок</b>', parse_mode='HTML')
                msg_id_append(msg)
                bot.set_state(bot.user.id, BotStates.photo_2, message.chat.id)
                with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                    data['photo_1_id'] = message.photo[-1].file_id

        # Шаг 4. Получение обзорного фото
        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:photo_2':
            if check_content_type(message, content_type='photo'):
                msg = bot.send_message(message.chat.id,
                                       '📸 🏘 <b>Шаг 5. Ориентирующий снимок</b>', parse_mode='HTML')
                msg_id_append(msg)
                bot.set_state(bot.user.id, BotStates.photo_3, message.chat.id)
                with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                    data['photo_2_id'] = message.photo[-1].file_id

        # Шаг 5. Получение ориентирующего фото
        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:photo_3':
            if check_content_type(message, content_type='photo'):
                kb_rep = types.InlineKeyboardMarkup(row_width=3)
                btn_1 = types.InlineKeyboardButton('отсутствует', callback_data='btn1')
                btn_2 = types.InlineKeyboardButton('не правильный', callback_data='btn2')
                btn_3 = types.InlineKeyboardButton('соответствует', callback_data='btn3')
                kb_rep.add(btn_1, btn_2, btn_3)
                msg = bot.send_message(message.chat.id,
                                       '🔀 <b>Шаг 6. Наличие указателя</b>', parse_mode='HTML', reply_markup=kb_rep)
                msg_id_append(msg)
                bot.set_state(bot.user.id, BotStates.plate_exist, message.chat.id)
                with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                    data['photo_3_id'] = message.photo[-1].file_id

        # Шаг 6. Наличие указателя
        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:plate_exist':
            if check_content_type(message, content_type='text'):
                if message.text == 'отсутсвует':
                    msg = bot.send_message(message.chat.id,
                                           '💾 <b>Чтобы сохранить введите команду /save</b>', parse_mode='HTML')
                    msg_id_append(msg)
                    bot.set_state(bot.user.id, BotStates.save, message.chat.id)
                    with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                        data['plate_exist'] = message.text
                        data['plate_photo'] = ''
                elif message.text == 'не правильный' or message.text == 'соответсвует':
                    msg = bot.send_message(message.chat.id,
                                           '📸 🔀 <b>Шаг 7. Снимок указателя</b>', parse_mode='HTML')
                    msg_id_append(msg)
                    bot.set_state(bot.user.id, BotStates.plate_photo, message.chat.id)
                    with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                        data['plate_exist'] = message.text
                else:
                    check_content_type(message, content_type='список')
        # Шаг 7. Фото указателя
        elif bot.get_state(bot.user.id, message.chat.id) == 'BotStates:plate_photo':
            if check_content_type(message, content_type='photo'):
                msg = bot.send_message(message.chat.id,
                                       '💾 <b>Чтобы сохранить введите команду /save</b>', parse_mode='HTML')
                msg_id_append(msg)
                bot.set_state(bot.user.id, BotStates.save, message.chat.id)
                with bot.retrieve_data(bot.user.id, message.chat.id) as data:
                    data['plate_photo'] = message.photo[-1].file_id

        elif not bot.get_state(bot.user.id, message.chat.id):
            msg_id_remove(message, 2)
            msg = bot.send_message(message.chat.id,
                                   '<i>Для запуска введите команду /start</i>', parse_mode='HTML')
            msg_id_append(msg)
            msg_id_remove(msg, 3)
        else:
            msg_id_remove(message, 2)
            msg = bot.send_message(message.chat.id,
                                   '<i>Состояние не определено</i>', parse_mode='HTML')
            msg_id_append(msg)
            msg_id_remove(msg, 3)


@bot.callback_query_handler(func=lambda call: True)
def callback_keyboard(call):
    try:
        msg_text = None
        if call.data == 'btn1':
            msg_text = 'отсутсвует'
        elif call.data == 'btn2':
            msg_text = 'не правильный'
        elif call.data == 'btn3':
            msg_text = 'соответсвует'
        elif call.data == 'delete_message':
            msg_id_remove(call.message)

        if msg_text:
            msg = bot.send_message(call.message.chat.id, msg_text)
            process_step(msg)
            msg_id_append(msg)
            bot.edit_message_reply_markup(chat_id=call.message.chat.id,
                                          message_id=call.message.id, reply_markup=None)
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
            # bot.polling(skip_pending=True, non_stop=True)
            # bot.infinity_polling(timeout=60, long_polling_timeout=60, none_stop=True)
        except OSError as exc:
            logger.critical(f'Ошибка OSError: {exc}')
        except ConnectionError as e:
            logger.critical(f'Ошибка подключения: {e}. Повторная попытка через 5 cекунд.')
            # sys.stdout.flush()
            # os.execv(sys.argv[0], sys.argv)
            sleep(5)
        except ConnectTimeout as e:
            logger.critical(f'Timeout: {e}. Повторная попытка через 5 cекунд.')
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
