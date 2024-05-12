""" Модуль для работы с сервисом NextGIS WEB
Документация » 17.1. NextGIS Web REST API
    https://docs.nextgis.ru/docs_ngweb_dev/doc/developer/toc.html
Вебинар «NextGIS Web API: управляем Веб ГИС через HTTP-запросы и программный код»
    https://nextgis.ru/blog/ngw-event-4/
"""
import json
import requests
from loguru import logger
from config import Config  # Параметры записаны в файл config.py


# def ngw_name_wi_point(feature_fid=None):
#     """ Наименование точки водозабора
#     Функция принимает числовой идентификатор, выполняет запрос к NextGIS WEB
#     возвращает строку: наименование и адрес при успехе, информацию об ошибке при неудаче"""
#     try:
#         request_url = f'{Config.ngw_host}/api/resource/{Config.ngw_resource_wi_points}/feature/{feature_fid}'
#         r = requests.get(request_url, auth=(Config.ngw_user, Config.ngw_password))
#         # print(request_url)
#         # print(u'Статус (Status): %s' % r.status_code, type(r.status_code))
#         # print(r.content.decode('utf-8'))
#         if r.status_code == 200:
#             content = json.loads(r.content.decode('utf-8'))
#             print(content['geom'])
#             name = f"{content['fields']['name']}\n{content['fields']['wi_addr_locality']}, " \
#                    f"{content['fields']['wi_addr_street']}, {content['fields']['wi_addr_building']}"
#             return name
#         else:
#             return f'⚠ Ошибка (ресурс вернул - {r.status_code})'
#     except Exception as exc:
#         print('Ошибка в ngw_name_wi_point:', exc)
#         return f'⚠ Ошибка (ресурс вернул - {exc})'


def ngw_post_wi_checkup(fid_wi_point, plate_exist, date_time, geom, air_temp=None):
    """ Создать запись о проверке
    Функция выполняет запрос к NextGIS WEB - создает запись о проверке в таблице.
    При удачном запросе вернувшийся ИД новой записи вносит в поле id таблицы
    (id таблицы - дублер ИД NextGIS WEB, который не отображанется в настольной QGIS) """
    try:
        request_post = f'{Config.ngw_host}/api/resource/{Config.ngw_resource_wi_checkup}/feature/'
        data = {
                    "extensions": {
                        "attachment": None,
                        "description": None
                        },
                    "fields": {
                        "id_wi_point": fid_wi_point,
                        "plate_exist": plate_exist,
                        "date_time": {
                            "year": date_time['year'],
                            "month": date_time['month'],
                            "day": date_time['day'],
                            "hour": date_time['hour'],
                            "minute": date_time['minute'],
                            "second": 0
                            },
                        "air_temp": air_temp
                    },
                    "geom": geom
                }
        r_post = requests.post(request_post, data=json.dumps(data), auth=(Config.ngw_user, Config.ngw_password))
        if r_post.status_code == 200:
            answer = json.loads(r_post.content.decode('utf-8'))
            request_put = f'{Config.ngw_host}/api/resource/{Config.ngw_resource_wi_checkup}/feature/{answer["id"]}'
            data_put = {"fields": {"id": answer["id"]}}
            r_put = requests.put(request_put, data=json.dumps(data_put), auth=(Config.ngw_user, Config.ngw_password))
            if r_put.status_code == 200:
                return True
    except Exception as exc:
        logger.critical(f"Ошибка записи о проверке в NextGIS WEB: {exc}")


def ngw_put_feature(resource_id: int, feature_id: int, fields_values: dict):
    try:
        request_put = f'{Config.ngw_host}/api/resource/{resource_id}/feature/{feature_id}'
        data_put = {"fields": fields_values}
        r_put = requests.put(request_put, data=json.dumps(data_put), auth=(Config.ngw_user, Config.ngw_password))
        if r_put.status_code == 200:
            return True
    except Exception as exc:
        logger.critical(f"Ошибка изменения объекта в NextGIS WEB: {exc}")


def get_feature(resource_id: int, feature_id: int, **kwargs):
    """ Получение одного объекта слоя (ресурса) по его ИД
    Параметры:
    geom_format – 'geojson' - выводит геометрию в формате geojson вместо WKT (пример: geom_format='geojson')
    srs         – код EPSG перепроектирует геометрию в формат EPSG (пример: srs='4326' для WGS 84 latitude/longitude)
    geom        – 'yes' - возвращает геометрию, 'no' - не возвращает геометрию (по умолчанию: 'yes' / пример: geom='no')
    dt_format   – 'iso' - возвращает дату и время в формате ISO (пример: dt_format='iso')
                  'obj' - возвращает дату и время в виде объекта JSON (по умолчанию: 'obj')
    """
    try:
        request_get = f'{Config.ngw_host}/api/resource/{resource_id}/feature/{feature_id}?'

        if isinstance(kwargs.get('geom_format'), str):
            request_get += f"geom_format={kwargs.get('geom_format')}&"
        if isinstance(kwargs.get('srs'), str):
            request_get += f"srs={kwargs.get('srs')}&"
        if isinstance(kwargs.get('geom'), str):
            request_get += f"geom={kwargs.get('geom')}&"
        if isinstance(kwargs.get('dt_format'), str):
            request_get += f"dt_format={kwargs.get('dt_format')}&"

        r = requests.get(request_get, auth=(Config.ngw_user, Config.ngw_password))
        logger.info(f'Статус получения feature из NextGIS WEB: {r.status_code}')
        if r.status_code == 200:
            content = json.loads(r.content.decode('utf-8'))
            return content
    except Exception as exc:
        logger.critical(f"Ошибка получения feature из NextGIS WEB: {exc}")


def get_features(resource_id: int, **kwargs):
    """ Набор объектов слоя (ресурса)
    https://docs.nextgis.ru/docs_ngweb_dev/doc/developer/resource.html
    Параметры:
    limit       – ограничивает количество объектов, добавляемых в возвращаемый массив
                    limit=5
    offset      – пропускает количество объектов перед созданием массива объектов
                    offset=200
    order_by    – упорядочивает результаты по полям (символ минус - по убыванию)
                    order_by=['field_1', 'field_2']
    intersects  – геометрия в виде строки WKT в EPSG:3857.
                  Объекты, пересекающиеся с этой геометрией, будут добавлены в массив
                    intersects="point(8171735.614178087 8680155.021816246)")
    fields      – список полей (разделяются запятыми без пробелов) в возвращаемом массиве
                    fields=['field_1', 'field_2']
    fld_equals  - fld_{имя_поля_1}...fld_{имя_поля_n} – имя поля и значение для фильтрации возвращаемых признаков.
                  Имя параметра формируется в виде fld_ + реальное имя поля (keyname).
                  Все пары name=value формируют набор AND SQL-запроса.
                    fld_equals=['fld_id=245']
    fld_filter  - fld_{имя_поля_1}__{операция}...fld_{имя_поля_n}__{операция} – имя поля и значение для фильтрации
                  возвращаемых признаков с помощью инструкции operation.
                  Поддерживаются следующие операции: gt, lt, ge, le, eq, ne, like, ilike.
                  Все пары name-operation-value формируют набор AND SQL-запроса.
                    fld_filter=['fld_id__gt=582'] или fld_filter=['fld_name__ne=Null']
    geom_format – geojson - выводит геометрию в формате geojson вместо WKT
                    geom_format='geojson')
    srs         – код EPSG - перепроектирует геометрию в формат EPSG
                    srs='4326' (EPSG:4326 - WGS 84, latitude/longitude coordinate)
    geom        – да - возвращает геометрию, нет - не возвращает геометрию (по умолчанию да)
                    geom='no'
    dt_format   – iso - возвращает дату, время, временную метку в формате ISO,
                  obj - возвращает дату, время, временную метку в виде объекта JSON (obj по умолчанию)
                    dt_format='iso'
    extensions  – список дополнений разделенных запятыми, доступно описание и вложения.
                  По умолчанию используется: описание,вложения -> description,attachments
                    extensions='attachment'
    Операции фильтрации:
        gt - больше (>)
        lt - меньше (<)
        ge - больше или равно (>=)
        le - меньше или равно (<=)
        eq - равно (=)
        ne - не равно (!=)
        like - оператор SQL LIKE (для сравнения строк)
        ilike - оператор SQL ILIKE (для сравнения строк)
        Для фильтрации части поля используйте знак процента. Может быть в начале строки, в конце или в обоих вариантах.
        Работает только для операций like и ilike.
    """
    try:
        logger.info(f'Список переменных: {kwargs}')
        request_get = f'{Config.ngw_host}/api/resource/{resource_id}/feature/?'

        if isinstance(kwargs.get('limit'), int):
            request_get += f"&limit={kwargs.get('limit')}&"
        if isinstance(kwargs.get('offset'), int):
            request_get += f"&offset={kwargs.get('offset')}&"
        if isinstance(kwargs.get('order_by'), list):
            request_get += f"order_by={','.join(kwargs.get('order_by'))}&"
        if isinstance(kwargs.get('intersects'), str):
            request_get += f"&intersects={kwargs.get('intersects')}&"
        if isinstance(kwargs.get('fields'), list):
            request_get += f"fields={','.join(kwargs.get('fields'))}&"
        if isinstance(kwargs.get('fld_equals'), list):
            for fld_e in kwargs.get('fld_equals'):
                request_get += f"{fld_e}&"
        if isinstance(kwargs.get('fld_filter'), list):
            for fld_f in kwargs.get('fld_filter'):
                request_get += f"{fld_f}&"
        if isinstance(kwargs.get('geom_format'), str):
            request_get += f"geom_format={kwargs.get('geom_format')}&"
        if isinstance(kwargs.get('srs'), str):
            request_get += f"srs={kwargs.get('srs')}&"
        if isinstance(kwargs.get('geom'), str):
            request_get += f"geom={kwargs.get('geom')}&"
        if isinstance(kwargs.get('dt_format'), str):
            request_get += f"dt_format={kwargs.get('dt_format')}&"
        if isinstance(kwargs.get('extensions'), str):
            request_get += f"extensions={kwargs.get('extensions')}&"

        r = requests.get(request_get, auth=(Config.ngw_user, Config.ngw_password))
        if r.status_code == 200:
            content = json.loads(r.content.decode('utf-8'))
            return content
    except Exception as exc:
        logger.critical(f"Ошибка получения набора features из NextGIS WEB: {exc}")
