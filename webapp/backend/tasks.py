from celery import Celery
import os
import time
import random

CELERY_BROKER = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER)
celery_app = Celery('tasks', broker=CELERY_BROKER, backend=CELERY_BACKEND)

@celery_app.task(name="tasks.long_task")
def long_task():
    time.sleep(5)
    return {"result": random.randint(0, 100)}
