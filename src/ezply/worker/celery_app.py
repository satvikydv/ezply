import os
from celery import Celery
from celery.schedules import crontab

redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "ezply_worker",
    broker=redis_url,
    backend=redis_url,
    include=["ezply.worker.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Schedule for polling
celery_app.conf.beat_schedule = {
    "poll-companies-every-5-minutes": {
        "task": "ezply.worker.tasks.poll_all_companies",
        "schedule": crontab(minute="*/5"),
    },
}
