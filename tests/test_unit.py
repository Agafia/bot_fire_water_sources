import datetime
import json
from unittest.mock import patch, Mock, MagicMock, AsyncMock

import pytest
from aiogram.types import Message, User
from freezegun import freeze_time

from handlers.admin_handlers import cmd_update
from handlers.survey_handlers import date_time_now
from middlewares import admin_check
from nextgis import get_feature, ngw_post_wi_checkup
from pydrive import create_folder


@pytest.fixture
def mock_datetime_now():
    """Фикстура для заморозки времени."""
    return datetime.datetime(2025, 8, 15, 12, 30, 0)


@freeze_time("2025-08-15 12:30:00")
def test_date_time_now(mock_datetime_now):
    """Тестирование функции date_time_now."""
    # Мокируем pytz.timezone, чтобы избежать зависимости от конфигурации
    with patch('handlers.survey_handlers.pytz.timezone') as mock_timezone:
        mock_timezone.return_value = datetime.timezone.utc

        # Вызываем функцию
        result = date_time_now()

        # Проверяем, что результат - это словарь
        assert isinstance(result, dict)

        # Проверяем наличие и типы ключей
        expected_keys = ['year', 'month', 'day', 'hour', 'minute']
        assert all(key in result for key in expected_keys)
        assert all(isinstance(result[key], int) for key in expected_keys)

        # Проверяем значения
        assert result['year'] == 2025
        assert result['month'] == 8
        assert result['day'] == 15
        assert result['hour'] == 12
        assert result['minute'] == 30


def test_get_feature_success(mocker):
    """Тестирование функции get_feature при успешном ответе от API."""
    # Мокируем requests.get
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content.decode.return_value = json.dumps({'id': 1, 'fields': {'name': 'Test Feature'}})
    mocker.patch('nextgis.requests.get', return_value=mock_response)

    # Вызываем функцию
    result = get_feature(1, 1)

    # Проверяем результат
    assert result is not None
    assert result['id'] == 1
    assert result['fields']['name'] == 'Test Feature'


def test_get_feature_not_found(mocker):
    """Тестирование функции get_feature при ответе 404 от API."""
    # Мокируем requests.get
    mock_response = Mock()
    mock_response.status_code = 404
    mocker.patch('nextgis.requests.get', return_value=mock_response)

    # Вызываем функцию
    result = get_feature(1, 1)

    # Проверяем, что функция возвращает None
    assert result is None


def test_ngw_post_wi_checkup_success(mocker):
    """Тестирование функции ngw_post_wi_checkup при успешном ответе от API."""
    # Мокируем requests.post и requests.put
    mock_post_response = Mock()
    mock_post_response.status_code = 200
    mock_post_response.content.decode.return_value = json.dumps({'id': 123})
    mocker.patch('nextgis.requests.post', return_value=mock_post_response)

    mock_put_response = Mock()
    mock_put_response.status_code = 200
    mocker.patch('nextgis.requests.put', return_value=mock_put_response)

    # Вызываем функцию
    result = ngw_post_wi_checkup(1, 'checkout', 'water', 'workable', 'entrance', 'plate_exist', date_time_now(), 'geom')

    # Проверяем результат
    assert result is True


def test_ngw_post_wi_checkup_post_fails(mocker):
    """Тестирование функции ngw_post_wi_checkup, когда POST-запрос не удался."""
    # Мокируем requests.post, чтобы он возвращал ошибку
    mock_post_response = Mock()
    mock_post_response.status_code = 500
    mocker.patch('nextgis.requests.post', return_value=mock_post_response)

    # Вызываем функцию
    result = ngw_post_wi_checkup(1, 'checkout', 'water', 'workable', 'entrance', 'plate_exist', date_time_now(), 'geom')

    # Проверяем, что функция возвращает None
    assert result is None


def test_ngw_post_wi_checkup_put_fails(mocker):
    """Тестирование функции ngw_post_wi_checkup, когда PUT-запрос не удался."""
    # Мокируем requests.post и requests.put
    mock_post_response = Mock()
    mock_post_response.status_code = 200
    mock_post_response.content.decode.return_value = json.dumps({'id': 123})
    mocker.patch('nextgis.requests.post', return_value=mock_post_response)

    mock_put_response = Mock()
    mock_put_response.status_code = 500
    mocker.patch('nextgis.requests.put', return_value=mock_put_response)

    # Вызываем функцию
    result = ngw_post_wi_checkup(1, 'checkout', 'water', 'workable', 'entrance', 'plate_exist', date_time_now(), 'geom')

    # Проверяем, что функция возвращает None
    assert result is None


@patch('pydrive.GoogleAuth')
@patch('pydrive.GoogleDrive')
def test_create_folder_success(mock_google_drive, mock_google_auth):
    """Тестирование функции create_folder при успешном создании папки."""
    # Настройка моков
    mock_drive_instance = mock_google_drive.return_value
    mock_file = MagicMock()
    mock_file.__getitem__.side_effect = lambda key: {'id': 'new_folder_id', 'labels': {'trashed': False}}[key]
    mock_drive_instance.CreateFile.return_value = mock_file

    # Вызов функции
    folder_id = create_folder(file_name='Test Folder')

    # Проверка
    assert folder_id == 'new_folder_id'
    mock_file.Upload.assert_called_once()


@patch('pydrive.GoogleAuth')
@patch('pydrive.GoogleDrive')
def test_create_folder_trashed(mock_google_drive, mock_google_auth, mocker):
    """Тестирование функции create_folder, когда папка находится в корзине."""
    # Настройка моков
    mock_drive_instance = mock_google_drive.return_value
    mock_file = MagicMock()
    mock_file.__getitem__.side_effect = lambda key: {'id': 'trashed_folder_id', 'labels': {'trashed': True}}[key]
    mock_drive_instance.CreateFile.return_value = mock_file
    mocker.patch('pydrive.create_folder', return_value='new_folder_id_recursive')

    # Вызов функции
    folder_id = create_folder(file_id='trashed_folder_id', file_name='Test Folder')

    # Проверка
    assert folder_id == 'new_folder_id_recursive'

# --- Новые тесты для админ-функционала ---

@pytest.mark.asyncio
async def test_admin_check_middleware_is_admin(mocker):
    """Тест: middleware admin_check пропускает администратора."""
    # Создаем mock для следующего обработчика в цепочке
    handler_mock = AsyncMock()

    # Мокируем get_chat_member, чтобы он возвращал администратора
    bot_mock = MagicMock()
    admin_member = MagicMock()
    admin_member.status = 'administrator'
    bot_mock.get_chat_member = AsyncMock(return_value=admin_member)

    # Готовим данные для middleware
    event = MagicMock()
    event.from_user.id = 123
    data = {'bot': bot_mock}

    # Вызываем middleware
    await admin_check(handler_mock, event, data)

    # Проверяем, что следующий обработчик был вызван
    handler_mock.assert_called_once_with(event, data)


@pytest.mark.asyncio
async def test_admin_check_middleware_not_admin(mocker):
    """Тест: middleware admin_check НЕ пропускает обычного пользователя."""
    handler_mock = AsyncMock()

    # Мокируем get_chat_member, чтобы он возвращал обычного участника
    bot_mock = MagicMock()
    member = MagicMock()
    member.status = 'member'
    bot_mock.get_chat_member = AsyncMock(return_value=member)

    event = MagicMock()
    event.from_user.id = 456
    data = {'bot': bot_mock}

    await admin_check(handler_mock, event, data)

    # Проверяем, что следующий обработчик НЕ был вызван
    handler_mock.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_update_calls_celery_task(mocker):
    """Тест: команда /update вызывает Celery задачу."""
    # Мокируем метод delay у задачи Celery
    mock_celery_task = mocker.patch('handlers.admin_handlers.update_nextgis_data.delay')

    # Создаем мок сообщения от пользователя
    message_mock = AsyncMock(spec=Message)
    message_mock.from_user = User(id=123, is_bot=False, first_name="Admin")

    # Вызываем обработчик команды
    await cmd_update(message_mock)

    # Проверяем, что метод answer был вызван для информирования пользователя
    message_mock.answer.assert_called_once()

    # Проверяем, что задача Celery была вызвана
    mock_celery_task.assert_called_once()
