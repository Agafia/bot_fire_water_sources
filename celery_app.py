from celery import Celery
from config import Config

# Инициализация Celery
# Указываем broker'а (Redis) и backend (также Redis для хранения результатов)
celery_app = Celery(
    'bot_tasks',
    broker=Config.redis_url,
    backend=Config.redis_url,
    include=['nextgis']  # Указываем, где искать задачи (в нашем случае, в файле nextgis.py)
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Moscow',
    enable_utc=True,
)
