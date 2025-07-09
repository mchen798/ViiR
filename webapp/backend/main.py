from fastapi import FastAPI
from pydantic import BaseModel
from celery import Celery
import os

app = FastAPI()

CELERY_BROKER = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
celery_app = Celery('worker', broker=CELERY_BROKER)

class DataResponse(BaseModel):
    x: list
    y: list

@app.get("/data", response_model=DataResponse)
def get_data():
    data = {"x": [1, 2, 3, 4, 5], "y": [1, 4, 9, 16, 25]}
    return data

@app.post("/process")
def process_data():
    task = celery_app.send_task("tasks.long_task")
    return {"task_id": task.id}
