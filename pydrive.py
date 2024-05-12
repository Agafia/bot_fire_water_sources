""" Модуль для работы с сервисом Google Drive
Документация PyDrive2: https://docs.iterative.ai/PyDrive2/
"""
import requests
from io import BytesIO
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive


def login_with_service_account():
    """ Подключение к сервису Google Drive с сервисным аккаунтом.
    Примечание: для работы сервисного аккаунта вам необходимо предоставить
    доступ к папке или файлам указав электронную почту сервисного аккаунта """
    settings = {
                "client_config_backend": "service",
                "service_config": {
                    "client_json_file_path": "service-secrets.json",
                    }
                }
    # Создание экземпляра GoogleAuth и аутентификация
    gauth = GoogleAuth(settings=settings)
    gauth.ServiceAuth()
    return gauth


def create_folder(file_id=None, file_name='Не указано', parent_folder='root'):
    """ Получение папки
    Функция обращается к папке:
    - при наличии ИД (т.е. папка существуеь) обновляет имя
    - при наличии ИД и нахождении в корзине создает новую папку
    - при отсуствии ИД создает папку
    :param file_id: ИД существующей (искомой) папки
    :param file_name: Новое имя папки
    :param parent_folder: Родительский каталог (папка)
    :return: Возвращает ИД папки
    """
    drive = GoogleDrive(login_with_service_account())
    metadata = {
        'parents': [
            {"id": parent_folder}
        ],
        'id': file_id,
        'title': file_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    file = drive.CreateFile(metadata)
    file.Upload()
    file.FetchMetadata()
    if file['labels']['trashed']:  # Если файл удалён (в корзине), создаём новый
        folder_id = create_folder(file_name=file_name,  parent_folder=parent_folder)
    else:
        folder_id = file['id']
    return folder_id


def create_file_from_url(file_url, file_name='Не указано', parent_folder='root'):
    drive = GoogleDrive(login_with_service_account())
    metadata = {
        'parents': [
            {"id": parent_folder}
        ],
        'title': file_name,
        'mimeType': 'image/jpeg'
    }
    new_file = drive.CreateFile(metadata=metadata)
    response = requests.get(file_url)
    # Реализация буферизованного ввода-вывода с использованием буфера байтов в памяти.
    image_file = BytesIO(response.content)
    # Устанавливает содержимое файла
    new_file.content = image_file
    # Загружает файл на Google Диск
    new_file.Upload()


def find_folder(find_name=None, parent_folder='root'):
    drive = GoogleDrive(login_with_service_account())
    query = {'q': f"'{parent_folder}' in parents"}
    # query = {'q': f"title contains '{find_name}'"}
    file_list = drive.ListFile(query).GetList()
    for file1 in file_list:
        print(f"title: {file1['title']}, id: {file1['id']}")
    return True
