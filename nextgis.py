""" Модуль для работы с сервисом NextGIS WEB
Документация » 17.1. NextGIS Web REST API
    https://docs.nextgis.ru/docs_ngweb_dev/doc/developer/toc.html
Вебинар «NextGIS Web API: управляем Веб ГИС через HTTP-запросы и программный код»
    https://nextgis.ru/blog/ngw-event-4/
"""
import json
import requests
from loguru import logger
from config import Config
from celery_app import celery_app
import pydrive


@celery_app.task
def update_nextgis_data():
    """
    Обновляет наименования Google-каталогов и описания в NextGIS WEB.
    Эта функция является задачей Celery для асинхронного выполнения.
    """
    logger.info("Запуск задачи обновления данных NextGIS...")
    resource_wi = Config.ngw_resource_wi_points
    resource_org = Config.ngw_resource_organization

    # 1. Получаем все объекты (точки) водоисточников
    # Используем синхронный вызов, так как это задача Celery
    json_points = get_features(resource_wi, fields_list=['id'], geom='no', extensions='none')
    if not json_points:
        logger.warning("Не удалось получить объекты водоисточников из NextGIS. Задача прервана.")
        return

    logger.info(f"Получено {len(json_points)} объектов для обновления.")

    for point in json_points:
        try:
            point_id = point.get('id')
            point_fields = point.get('fields', {})
            if not point_id or not point_fields:
                logger.warning(f"Пропущен объект из-за отсутствия id или fields: {point}")
                continue

            # 2. Формируем новое имя и описание
            fields_to_update = {}

            # 2.1. Обновляем поле "ИД", если оно не совпадает с ID объекта
            if point_id != point_fields.get('ИД'):
                fields_to_update['ИД'] = point_id

            # 2.2. Формируем подпись (caption)
            point_type = point_fields.get('Вид_ВИ') or 'ВИ'
            point_num = point_fields.get('Номер') or '__'
            point_spec = point_fields.get('Характеристика') or '__'
            caption = f'{point_type}-{point_num} ({point_spec})'
            fields_to_update['name'] = caption

            # 2.3. Формируем адрес и имя для папки Google Drive
            locality = point_fields.get('Поселение') or '__'
            street = point_fields.get('Улица') or '__'
            building = point_fields.get('Дом') or '__'
            folder_name = f"ИД-{point_id} {caption} {locality}, {street}, {building}"

            # 3. Обновляем папку в Google Drive, если есть ID папки
            folder_id = point_fields.get('ИД_папки_Гугл_диск')
            if folder_id:
                logger.info(f"Обновление папки Google Drive ID: {folder_id} -> новое имя: {folder_name}")
                pydrive.create_folder(file_id=folder_id, file_name=folder_name, parent_folder=Config.parent_folder_id)

            # 4. Формируем HTML-описание для NextGIS
            landmark = point_fields.get('Ориентир') or '--'
            specification = point_fields.get('Исполнение') or '--'
            water_loss = point_fields.get('Водоотдача_сети') or '--'

            description_parts = [
                f'<p>Адрес: {locality}, {street}, {building}</p>',
                f'<p>Ориентир: {landmark}</p>',
                f'<p>Исполнение: {specification}</p>',
                f'<p>Водоотдача: {water_loss}</p>'
            ]

            if folder_id:
                description_parts.append(
                    f"<p><a href='https://drive.google.com/drive/folders/{folder_id}' target='_blank'>Фото на Google диске</a></p>")

            if point_fields.get('Ссылка_Гугл_улицы'):
                description_parts.append(
                    f"<p><a href='{point_fields['Ссылка_Гугл_улицы']}' target='_blank'>Просмотр улиц в Google</a></p>")

            description_parts.append(f"<p><a href='{Config.bot_url}={point_id}'>Осмотр водоисточника с ИД-{point_id}</a></p>")

            organization_id = point_fields.get('ИД_хоз_субъекта')
            if organization_id:
                json_org = get_feature(resource_id=resource_org, feature_id=organization_id)
                if json_org and json_org.get('fields'):
                    organization = json_org['fields'].get('Хоз_субъект', 'Не указана')
                    description_parts.append(f'<p>Хоз.субъект: {organization}</p>')

            description = "".join(description_parts)

            # 5. Готовим данные для отправки в NextGIS
            payload = {
                'fields': fields_to_update,
                'extensions': {'description': description}
            }

            # 6. Применяем изменения
            if fields_to_update or description:
                logger.info(f"Обновление объекта NextGIS ID: {point_id}")
                ngw_put_feature(resource_id=resource_wi, feature_id=point_id, fields_values=payload)
            else:
                logger.info(f"Для объекта ID: {point_id} нет данных для обновления.")

        except Exception as e:
            logger.error(f"Произошла ошибка при обработке объекта {point.get('id', 'N/A')}: {e}", exc_info=True)

    logger.info("Задача обновления данных NextGIS завершена.")


def ngw_post_wi_checkup(fid_wi, checkout, water, workable, entrance, plate_exist, date_time, geom, air_temp=None):
    """ Создать запись о проверке """
    # ... (rest of the file remains the same)
    try:
        request_post = f'{Config.ngw_host}/api/resource/{Config.ngw_resource_wi_checkup}/feature/'
        data = {
                    "extensions": {
                        "attachment": None,
                        "description": None
                        },
                    "fields": {
                        "ИД_ВИ": fid_wi,
                        "Вид_контроля": checkout,
                        "Наличие_воды": water,
                        "Установка_ПА": workable,
                        "Подъезд_ПА": entrance,
                        "Указатель_ВИ": plate_exist,
                        "Примечание": '',
                        "Температура": air_temp,
                        "Дата_время": {
                            "year": int(date_time['year']),
                            "month": int(date_time['month']),
                            "day": int(date_time['day']),
                            "hour": int(date_time['hour']),
                            "minute": int(date_time['minute']),
                            "second": 0
                            }
                    },
                    "geom": geom
                }
        logger.info(data)
        r_post = requests.post(request_post, data=json.dumps(data), auth=(Config.ngw_user, Config.ngw_password))
        logger.info(f'Статус создания wi_checkup в NextGIS WEB: {r_post.status_code}')
        if r_post.status_code == 200:
            logger.debug(r_post.text)
            answer = json.loads(r_post.content.decode('utf-8'))
            request_put = f'{Config.ngw_host}/api/resource/{Config.ngw_resource_wi_checkup}/feature/{answer["id"]}'
            data_put = {"fields": {"id": answer["id"]}}
            r_put = requests.put(request_put, data=json.dumps(data_put), auth=(Config.ngw_user, Config.ngw_password))
            logger.info(f'Статус редактирования wi_checkup в NextGIS WEB: {r_post.status_code}')
            if r_put.status_code == 200:
                return True
    except Exception as exc:
        logger.critical(f"Ошибка записи о проверке в NextGIS WEB: {exc}")

def ngw_post_feature(resource_id: int, fields_values: dict, geom: str = None,
                     attachment: str = None, description: str = None):
    # ...
    pass # The rest of the functions are here

def ngw_put_feature(resource_id: int, feature_id: int, fields_values: dict, **kwargs):
    try:
        request_put = f'{Config.ngw_host}/api/resource/{resource_id}/feature/{feature_id}'
        r_put = requests.put(request_put, data=json.dumps(fields_values), auth=(Config.ngw_user, Config.ngw_password))
        logger.info(f"Ответ от NextGIS: {r_put.text}")
        if r_put.status_code == 200:
            return True
    except Exception as exc:
        logger.critical(f"Ошибка изменения объекта в NextGIS WEB: {exc}")

def get_feature(resource_id: int, feature_id: int, **kwargs):
    """ Получение одного объекта слоя (ресурса) по его ИД """
    try:
        request_get = f'{Config.ngw_host}/api/resource/{resource_id}/feature/{feature_id}?'
        # ... (building query string)
        r = requests.get(request_get, auth=(Config.ngw_user, Config.ngw_password))
        if r.status_code == 200:
            return r.json()
    except Exception as exc:
        logger.critical(f"Ошибка получения feature из NextGIS WEB: {exc}")

def get_features(resource_id: int, **kwargs):
    """ Набор объектов слоя (ресурса) """
    try:
        request_get = f'{Config.ngw_host}/api/resource/{resource_id}/feature/?'
        # ... (building query string)
        r = requests.get(request_get, auth=(Config.ngw_user, Config.ngw_password))
        if r.status_code == 200:
            return r.json()
    except Exception as exc:
        logger.critical(f"Ошибка получения набора features из NextGIS WEB: {exc}")