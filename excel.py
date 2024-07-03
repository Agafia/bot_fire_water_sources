""" Загрузка первоначальных данных в таблицу водоисточники NextGIS WEB"""
import pandas as pd
from pyproj import Transformer  # Преобразование координат между проекциями
import nextgis
import templates

data = pd.read_excel('118_3.xlsx')  # Файл из которого осуществляется
# Заголовки столбцов для сопоставления и передачи данных
headers_int = ['ИД_хоз_субъекта', 'ИД_вид_ППВ', 'ИД_исп_ППВ', 'ИД_зоны_части',
               'ИД_верхего_МО', 'ИД_нижнего_МО', 'ИД_границ_НП']
headers_str = ['Поселение', 'Улица', 'Дом', 'Вид_ВИ', 'Номер', 'Характеристика', 'Исполнение',
               'Способ_обогрева', 'Указатель_место', 'Указатель_ГОСТ', 'Пирамида', 'Ориентир',
               'Состояние', 'Дефект_описание', 'Водоотдача_сети', 'Регистрация_повод', 'Исключение_повод']
headers_date = ['Дефект_выявлен', 'Дефект_устранён', 'Дата_испытания', 'Регистрация_дата', 'Исключение_дата']
headers_geom = ['Широта', 'Долгота']

fields_dict = {}
fields_geom = {}
for ind in data.index:  # Перебор строк
    for column in data:  # Перебор столбцов
        if column in headers_int:
            if pd.notnull(data[column][ind]):
                fields_dict[column] = int(data[column][ind])
        elif column in headers_str:
            if pd.notnull(data[column][ind]):
                fields_dict[column] = str(data[column][ind])
        elif column in headers_date:
            if pd.notnull(data[column][ind]):
                field_value = pd.to_datetime(data[column][ind])
                fields_date = {'year': "{:02d}".format(field_value.year),
                               'month': "{:02d}".format(field_value.month),
                               'day': "{:02d}".format(field_value.day)}
                fields_dict[column] = fields_date
        elif column == 'Широта':
            fields_geom['lat'] = float(data[column][ind])
        elif column == 'Долгота':
            fields_geom['lon'] = float(data[column][ind])

    # Преобразование географических координат в систему координат NextGIS WEB
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857")
    sm = transformer.transform(fields_geom['lat'], fields_geom['lon'])
    geom = f'POINT({str(sm[0])} {str(sm[1])})'

    result = nextgis.ngw_post_feature(resource_id=91, fields_values=fields_dict, geom=geom)
    print(fields_dict)
    if result:
        type = fields_dict.get('Вид_ВИ', None)
        num = fields_dict.get('Номер', None)
        specification = fields_dict.get('Характеристика', None)
        name = type
        if num: name += f'-{num}'
        if specification: name += f' ({specification})'

        description = templates.description_water_intake(fid=result,
                                                         locality=fields_dict.get('Поселение', None),
                                                         street=fields_dict.get('Улица', None),
                                                         building=fields_dict.get('Дом', None),
                                                         landmark=fields_dict.get('Ориентир', None),
                                                         specification=fields_dict.get('Исполнение', None),
                                                         flow_rate_water=fields_dict.get('Водоотдача_сети', None),
                                                         google_folder=fields_dict.get('ИД_папки_Гугл_диск', None),
                                                         google_street=fields_dict.get('Ссылка_Гугл_улицы', None),
                                                         fid_wi_company=fields_dict.get('ИД_хоз_субъекта', None))

        if description:
            fields_values = {'name': name, 'description': description, 'ИД': result}
            nextgis.ngw_put_feature(resource_id=91, feature_id=result, fields_values=fields_values,
                                    description=description)

    fields_dict.clear()
    fields_geom.clear()
