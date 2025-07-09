from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from celery import Celery
import os

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CELERY_BROKER = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER)
celery_app = Celery('worker', broker=CELERY_BROKER, backend=CELERY_BACKEND)
tasks = {}
sample_log = "Running analysis...\nStep 1 completed\nStep 2 completed"

class DataResponse(BaseModel):
    x: list
    y: list

@app.get("/data", response_model=DataResponse)
def get_data():
    data = {"x": [1, 2, 3, 4, 5], "y": [1, 4, 9, 16, 25]}
    return data

@app.post("/tasks")
def start_task():
    task = celery_app.send_task("tasks.long_task")
    tasks[task.id] = None
    return {"task_id": task.id}

@app.get("/tasks")
def list_tasks():
    response = {}
    for task_id in list(tasks.keys()):
        result = celery_app.AsyncResult(task_id)
        response[task_id] = {
            "status": result.status,
            "result": result.result if result.ready() else None,
        }
        if result.ready():
            tasks[task_id] = result.result
    return response

@app.get("/tasks/{task_id}")
def task_status(task_id: str):
    result = celery_app.AsyncResult(task_id)
    return {
        "status": result.status,
        "result": result.result if result.ready() else None,
    }

@app.get("/tasks/{task_id}/log")
def task_log(task_id: str):
    # Return sample log lines. In real deployment this would stream task logs
    return {"log": sample_log}

