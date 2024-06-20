import nextgis
from config import Config  # Параметры записаны в файл config.py


def description_water_intake(fid: int,  locality: str = None, street: str = None, building: str = None,
                             landmark: str = None, specification: str = None, flow_rate_water: str = None,
                             google_folder: str = None, google_street: str = None, fid_wi_company: int = None):

    description = f'<p>Адрес: {locality}, {street}, {building}</p>' \
                  f'<p>Ориентир: {landmark}</p>' \
                  f'<p>Исполнение: {specification}</p>'

    if flow_rate_water:
        description += f"<p>Водоотдача: {flow_rate_water} л/с</p>"

    if google_folder:
        description += f"<p><a href='https://drive.google.com/drive/folders/{google_folder}'>Фото на Google диске</a></p>"

    if google_street:
        description += f"<p><a href='{google_street}'>Просмотр улиц в Google</a></p>"

    description += f"<p><a href='{Config.bot_url}={str(fid)}'>Осмотр водоисточника с ИД-{str(fid)}</a></p>"

    json_company = nextgis.get_feature(Config.ngw_resource_wi_company, feature_id=fid_wi_company)
    if json_company:
        description += f"<p>Обслуживает: {json_company['fields']['Хоз_субъект']}</p>"

    return description

