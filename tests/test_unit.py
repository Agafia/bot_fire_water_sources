import datetime
import json
from unittest.mock import patch, Mock, MagicMock

import pytest
from freezegun import freeze_time

from handlers.survey_handlers import date_time_now
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
