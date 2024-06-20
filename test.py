import nextgis
import pydrive
from config import Config  # Параметры записаны в файл config.py
import datetime
import pytz
import templates

if __name__ == "__main__":
    resource = 91
    # print(nextgis.get_features_array(55, limit=5, offset=55, order_by=['name', 'wi_addr_building'],
    #                                  fields_list=['id']))
    # print(nextgis.get_features_array(51))
    # json_object = nextgis.get_features(55, fields=['id', 'name', 'google_folder_id', 'wi_addr_locality',
    #                                                'wi_addr_street', 'wi_addr_building', 'link_google_drive'],
    #                                    fld_filter=['fld_google_folder_id__ne=Null'], geom='no', extensions='none')
    json_object = nextgis.get_features(resource, fields_list=['id'], geom='no', extensions='none')

    # json_object = nextgis.get_feature(55, 15, fields=['id'])
    # print(json_object['id'], json_object['fields']['id'])

    # json_object = nextgis.get_feature(55, 15, fields=['id', 'name'],
    #                                    dt_format='iso', geom_format='geojson', srs='4326', extensions='none')

    # print(json_object)
    # resource_id = 55
    # print(json_object[0]['id'], json_object[0]['fields']['id'])

    # ================================================================= Цикл по json_object
    for song in json_object:
        feature_id = song['id']

        # ============================================================= Задать копию ИД водоисточника
        # fields = {'ИД': feature_id}

        # ============================================================= Задать подпись водоисточника
        # feature_caption = song['fields']['Вид_ВИ']
        # if song['fields']['Номер']:
        #     feature_caption += f"-{song['fields']['Номер']}"
        # if song['fields']['Характеристика']:
        #     feature_caption += f" ({song['fields']['Характеристика']})"
        # fields = {'name': feature_caption}

        # ============================================================= Задать описание водоисточника
        description = templates.description_water_intake(fid=feature_id,
                                                            locality=song['fields']['Поселение'],
                                                            street=song['fields']['Улица'],
                                                            building=song['fields']['Дом'],
                                                            landmark=song['fields']['Ориентир'],
                                                            specification=song['fields']['Исполнение'],
                                                            flow_rate_water=song['fields']['Водоотдача_сети'],
                                                            google_folder=song['fields']['ИД_папки_Гугл_диск'],
                                                            google_street=song['fields']['Ссылка_Гугл_улицы'],
                                                            fid_wi_company=song['fields']['ИД_хоз_субъекта'])
        fields_values = {'description': description}

        # description = f"<p>Адрес: {song['fields']['Поселение']}, " \
        #               f"{song['fields']['Улица']}, {song['fields']['Дом']}</p>" \
        #               f"<p>Ориентир: {song['fields']['Ориентир']}</p>" \
        #               f"<p>Исполнение: {song['fields']['Исполнение']}</p>"
        # if song['fields']['Водоотдача_сети']:
        #     description += f"<p>Водоотдача: {song['fields']['Водоотдача_сети']}</p>"
        # if song['fields']['ИД_папки_Гугл_диск']:
        #     description += f"<p><a href='https://drive.google.com/drive/folders/" \
        #                    f"{song['fields']['ИД_папки_Гугл_диск']}'>Фото на Google диске</a></p>"
        # if song['fields']['Ссылка_Гугл_улицы']:
        #     description += f"<p><a href='{song['fields']['Ссылка_Гугл_улицы']}'>" \
        #                    f"Просмотр улиц в Google</a></p>"
        # description += f"<hr><p><a href='{Config.bot_url}={song['id']}'>" \
        #                f"Осмотр водоисточника с ИД-{song['id']}</a></p>"
        # fields = {'description': description}

        # ============================================================= Обновить названия Гугл каталогов
        # folder_name = f"ИД-{feature_id} {song['fields']['name']} " \
        #               f"{song['fields']['Поселение']}, {song['fields']['Улица']}, {song['fields']['Дом']}"
        # print(folder_name)
        # google_folder = pydrive.create_folder(file_id=song['fields']['ИД_папки_Гугл_диск'],
        #                                       file_name=folder_name,
        #                                       parent_folder=Config.parent_folder_id)

    #     locality = song['fields']['wi_addr_locality']
    #     street = song['fields']['wi_addr_street']
    #     building = song['fields']['wi_addr_building']
    #     landmark = song['fields']['wi_landmark']
    #     specification = song['fields']['wi_specification']
    #
    #     name_folder = f"ИД-{feature_id} {name} {locality}, {street}, {building}"

        # print(folder_id, name_folder)

        # print(PyDrive.create_folder(file_id=folder_id, file_name=name_folder, parent_folder=Config.parent_folder_id))
        # print(song['id'], song['fields']['name'])

        # ============================================================= Применить изменения
        # nextgis.ngw_put_feature(resource, feature_id, fields)
        nextgis.ngw_put_feature(resource_id=resource, feature_id=feature_id,
                                fields_values=fields_values, description=description)

        # for attribute, value in song.items():
        #     print(attribute, value)

    # current_time = datetime.datetime.now(pytz.timezone(Config.timezone))
    # print({'year': "{:02d}".format(current_time.year),
    #        'month': "{:02d}".format(current_time.month),
    #        'day': "{:02d}".format(current_time.day),
    #        'hour': "{:02d}".format(current_time.hour),
    #        'minute': "{:02d}".format(current_time.minute)})
