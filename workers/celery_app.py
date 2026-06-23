"""
Celery Configuration for Async Task Processing
"""

from celery import Celery
from config import config

celery_app = Celery(
    'studio_ia',
    broker=config.celery_broker_url,
    backend=config.celery_result_backend,
    include=['workers.tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,         # 1 heure max par tâche
    task_soft_time_limit=3000,    # 50 min soft limit
    worker_max_tasks_per_child=10,
    worker_prefetch_multiplier=1,
    # Supprime le warning de dépréciation Celery 6.0
    broker_connection_retry_on_startup=True,
    database_engine_options={'connect_args': {'timeout': 20}},
)