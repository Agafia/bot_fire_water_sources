import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()


@dataclass()
class Config:
    # Параметры Telegram бота
    bot_token = os.environ.get('BOT_TOKEN')
    bot_url: str = 'https://t.me/surgutfire_ppv_bot?start'

    # Параметры Telegram группы

    tg_group_id: str = '-1002004220590' # ППВ СгМПСГ (чат)
    tg_canal_id: str = '-1002389637778' # ППВ СгМПСГ (канал)
    tg_error_id: str = '-1002015129960' # Ошибки ботов (канал)
    tg_admin_id: str = '478031430'      # @SurgutFire
    tg_admin_chat: str = '-1002015129960' # Ошибки ботов (канал)

    # Параметры NextGIS WEB (ngw)
    ngw_host: str = 'https://spt-surgut.nextgis.com'
    ngw_user: str = os.environ.get('NGW_USER')
    ngw_password: str =  os.environ.get('NGW_PASSWORD')
    # ИД ресурса - основной таблицы > точки забора воды (Водоисточники)
    ngw_resource_wi_points: int = 91
    # ИД ресурса - таблицы > проверка точек забора воды (Контроль состояния ВИ)
    ngw_resource_wi_checkup: int = 90
    # ИД ресурса - таблицы > хозяйствующие субъекты
    ngw_resource_organization: int = 88

    # Часовой пояс для определения текущего времени в модуле pytz
    timezone = 'Asia/Yekaterinburg'

    # Ссылка на статью - инструкцию
    url_help = 'https://doc.clickup.com/24397675/d/h/q8hvb-2252/c438f0d13115c17'
    url_map = 'https://spt-surgut.nextgis.com/resource/1/display?panel=none'

    # ИД родительской папки на Googke диске, в которой расположены подпапки водоисточников
    parent_folder_id = '1qESxdsWZ0R-2D9IszYW0JfCNHNdtw_UH'