import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Optional, Dict

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import PlainTextResponse, FileResponse, JSONResponse
from pydantic import BaseModel
from .settings import DATA_ROOT, PIPELINE_SH, DEFAULT_ARGS

app = FastAPI(title="Web-ViiR API (minimal)")

DATA_ROOT = Path(os.environ.get("VIIR_WORKFOLDER", "/workspace"))
PIPELINE_SH = os.environ.get("VIIR_PIPELINE_SH", "viir")

ENV_ACTIVATE = "source /opt/micromamba/etc/profile.d/micromamba.sh && micromamba activate viir"


JOB = {
    "status": "idle",      # idle|running|finished|failed
    "started_at": None,
    "finished_at": None,
    "returncode": None,
    "pid": None,
    "cmd": None,
}

def job_dirs():
    return {
        "input": DATA_ROOT / "input",
        "work": DATA_ROOT / "work",
        "results": DATA_ROOT / "results",
        "logs": DATA_ROOT / "logs",
    }

def prepare_dirs():
    d = job_dirs()
    for k, p in d.items(): p.mkdir(parents=True, exist_ok=True)
    return d

def run_pipeline(sample_list_path: Path, extra_params: list[str]):
    global JOB
    d = job_dirs()
    log_file = d["logs"] / "stdout.log"

    cmd = f"""{ENV_ACTIVATE} && bash {PIPELINE_SH} -l {sample_list_path} -o {d["results"]}"""
    if extra_params:
        cmd += " " + " ".join(extra_params)

    JOB.update({
        "status": "running",
        "started_at": time.time(),
        "finished_at": None,
        "returncode": None,
        "cmd": cmd,
    })

    with open(log_file, "wb") as lf:
        proc = subprocess.Popen(["bash", "-lc", cmd],
                                stdout=lf, stderr=subprocess.STDOUT,
                                cwd=d["work"])
    JOB["pid"] = proc.pid
    rc = proc.wait()
    JOB.update({
        "returncode": rc,
        "finished_at": time.time(),
        "status": "finished" if rc == 0 else "failed",
    })

@APP.get("/healthz", response_class=PlainTextResponse)
def healthz(): return "ok"

@APP.post("/run")
async def run(file: UploadFile = File(..., description="sample_list.txt"),
              params: Optional[str] = Form(default="")):
    if JOB["status"] == "running":
        return JSONResponse({"error": "busy"}, status_code=409)

    prepare_dirs()
    # 清空旧结果（可选：保留历史；为最简先清）
    for sub in ("work","results","logs"):
        p = DATA_ROOT / sub
        if p.exists():
            shutil.rmtree(p)
    prepare_dirs()

    # 保存 sample_list.txt
    sample_list = DATA_ROOT / "input" / "sample_list.txt"
    with sample_list.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    extra = params.strip().split() if params else []
    t = threading.Thread(target=run_pipeline, args=(sample_list, extra), daemon=True)
    t.start()
    return {"status": "started"}

@APP.get("/status")
def status():
    return {
        "status": JOB["status"],
        "started_at": JOB["started_at"],
        "finished_at": JOB["finished_at"],
        "returncode": JOB["returncode"],
    }

@APP.get("/logs", response_class=PlainTextResponse)
def logs(tail: int = 200):
    p = DATA_ROOT / "logs" / "stdout.log"
    if not p.exists(): return ""
    with p.open("rb") as f:
        return b"".join(f.readlines()[-tail:]).decode("utf-8", "ignore")
