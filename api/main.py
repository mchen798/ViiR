import os
import time
import uuid
import yaml
import shutil
import subprocess
import threading
import logging
import re
from pathlib import Path, PurePath
from typing import Optional, Dict, Literal
import tempfile, zipfile
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, Request, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel, field_validator, Field  
# from .settings import DATA_ROOT, PIPELINE_SH, DEFAULT_ARGS

from fastapi.staticfiles import StaticFiles

# -----------------------------------------------------------
# 基本配置
# -----------------------------------------------------------
app = FastAPI(
    title="Web-ViiR minimal backend",
    description="API for reading, updating, run the ViiR pipeline.",
    version="1.0.0"
    )


WORKSPACE = Path(os.environ.get("WORKSPACE", "/workspace"))
LOG_FILE = WORKSPACE / "run_viir.log"
CONFIG_PATH = WORKSPACE / "config.yaml"
VIIR_BIN = os.environ.get("VIIR_BIN", "/usr/local/bin/viir")
MAMBA = os.environ.get("MAMBA_BIN", "/usr/local/bin/micromamba")

# DATA_ROOT = Path(os.environ.get("VIIR_WORKFOLDER", "/workspace"))
# PIPELINE_SH = os.environ.get("VIIR_PIPELINE_SH", "viir")
# DEFAULT_ARGS = []
# ENV_ACTIVATE = "source /opt/micromamba/etc/profile.d/micromamba.sh && micromamba activate viir"



# 单任务状态
JOB = {
    "status": "idle",          # idle | running | finished | failed
    "started_at": None,
    "finished_at": None,
    "returncode": None,
    "pid": None,
    "cmd": None,
}



# 统一日志对象（输出到 Docker 控制台）
log = logging.getLogger("uvicorn")
log.setLevel(logging.INFO)

# 计算静态目录的绝对路径：
# __file__ = /workspace/api/main.py
# BASE_DIR  = /workspace/api
# STATIC_DIR= /workspace/app/static
BASE_DIR   = Path(__file__).resolve().parent
STATIC_DIR = (BASE_DIR.parent / "app" / "static").resolve()


# 打印一下，方便你在容器日志里确认
log.info(f"[STATIC] BASE_DIR={BASE_DIR}")
log.info(f"[STATIC] STATIC_DIR={STATIC_DIR} (exists={STATIC_DIR.exists()})")
# 只挂 /static（不要 mount "/" 避免遮住 API）
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 根路径返回 index.html（用绝对路径）
@app.get("/", response_class=FileResponse)
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))




# ====================================================================
# Pydantic 数据模型 - 用于规范化输入和输出
# ====================================================================

# 1. 定义可选参数的模型 (Partial Update)
# 我们只包含需要通过界面修改的常用参数
class ConfigUpdateParams(BaseModel):
    """用于 /update_config 路由的数据模型"""
    
    # 必填项 (可选在更新时设置为Optional)
    fastq_list: Optional[str] = Field(
        None, 
        alias='fastq-list', 
        description='Path to the fastq list file.'
    )
    out: Optional[str] = None
    
    # 可选参数
    threads: Optional[int] = None
    adapter: Optional[str] = None
    pfam: Optional[str] = None
    hmm_folder: Optional[str] = Field(
        None, 
        alias='hmm-folder', 
        description='Path to the HMM folder.'
    )
    
    # 使用 Literal 限制字符串输入，提高数据安全性
    ss_lib_type: Optional[Literal["No", "FR", "RF"]] = Field(
        None, 
        alias='SS-lib-type', 
        description='Strand-specific library type.'
    )
    blastndb: Optional[str] = Field(
        None, 
        alias='blastndb', 
        description='Path to the BLASTN database.'
    )
    pvalue: Optional[float] = None
    max_memory: Optional[str] = Field(
        None, 
        alias='max-memory', 
        description='Maximum memory limit for certain steps.'
    ) # 保持字符串以支持 '32G' 格式

    model_config = {
        "populate_by_name": True,
    }

    # V2 模型配置：用 model_config 字典替代 V1 的 class Config
    # ModuleNotFoundError: No module named 'pydantic_settings'
    # from pydantic_settings import SettingsConfigDict # 导入 V2 的配置类型
    # model_config = SettingsConfigDict(
    #     # 替代 V1 的 populate_by_name = True: 允许通过字段名（Python名）进行赋值
    #     populate_by_name=True, 
    #     # 其他可能的 V2 配置...
    # )

    # 字段验证器 (Field Validator)
    @field_validator('threads')
    def threads_must_be_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError('threads must be a positive integer')
        return v
    



# -----------------------------------------------------------
# 核心执行函数
# -----------------------------------------------------------

def run_viir(extra_params: list[str]):
    """后台线程中执行 viir pipeline"""
    global JOB
    cmd_list = [MAMBA, "run", "-n", "viir", VIIR_BIN, str(CONFIG_PATH)]
    if extra_params:
        cmd_list += extra_params

    JOB.update({
        "status": "running",
        "started_at": time.time(),
        "finished_at": None,
        "returncode": None,
        "cmd": " ".join(cmd_list),
    })

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    log.info(f"[RUN] starting: {' '.join(cmd_list)}")

    try:
        with open(LOG_FILE, "wb") as lf:
            proc = subprocess.Popen(
                cmd_list,
                stdout=lf,
                stderr=subprocess.STDOUT,
                cwd=WORKSPACE
            )
        JOB["pid"] = proc.pid
        log.info(f"[RUN] pid={proc.pid}")

        rc = proc.wait()
        JOB.update({
            "returncode": rc,
            "finished_at": time.time(),
            "status": "finished" if rc == 0 else "failed",
        })
        log.info(f"[RUN] finished with return code {rc}")

    except Exception as e:
        JOB.update({
            "status": "failed",
            "finished_at": time.time(),
            "returncode": -1,
        })
        log.error(f"[RUN] exception: {e}")


def read_config() -> dict:
    """从文件中安全读取 YAML 配置"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            # 使用 safe_load 保证安全
            return yaml.safe_load(f)
    except FileNotFoundError:
        # 如果文件不存在，则抛出 404
        raise HTTPException(status_code=404, detail=f"Config file not found at {CONFIG_PATH}")
    except yaml.YAMLError:
        # 如果 YAML 格式错误
        raise HTTPException(status_code=500, detail="Error parsing config.yaml format")

def write_config(config_data: dict):
    """将配置数据安全写入文件"""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            # 使用 default_flow_style=False 使输出格式更接近原始 YAML
            yaml.safe_dump(config_data, f, sort_keys=False, default_flow_style=False)
    except Exception as e:
        # 写入失败
        raise HTTPException(status_code=500, detail=f"Failed to write config file: {e}")

# 功能函数
def infer_out_dir(config_path: Path, workspace: Path) -> Path:
    # 读取 YAML（你已经引入了 yaml.safe_load）
    cfg = read_config()  # 已有函数
    out_val = cfg.get("out")
    if not out_val:
        raise HTTPException(status_code=400, detail="'out' not set in config.yaml")
    p = Path(out_val)
    return p if p.is_absolute() else (workspace / p)

# -----------------------------------------------------------
# API 路由
# -----------------------------------------------------------

@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"




UPLOAD_DIR = Path("/workspace")
@app.get("/upload", response_class=HTMLResponse)
def upload_page():
    return """
<!doctype html>
<html>
  <body>
    <h3>Upload to /workspace</h3>
    <input id="f" type="file" />
    <button onclick="start()">Upload</button>
    <div id="p"></div>
    <script>
      function start() {
        const f = document.getElementById('f').files[0];
        if (!f) { alert('pick a file'); return; }
        const form = new FormData();
        form.append('file', f, f.name);
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/upload');
        xhr.upload.onprogress = (e)=> {
          if (e.lengthComputable) {
            const pct = (e.loaded / e.total * 100).toFixed(1);
            document.getElementById('p').innerText = `${pct}% (${(e.loaded/1024/1024).toFixed(1)} MiB)`;
          }
        };
        xhr.onload = ()=> { document.getElementById('p').innerText += '\\n' + xhr.responseText; };
        xhr.onerror = ()=> { document.getElementById('p').innerText += '\\nError'; };
        xhr.send(form);
      }
    </script>
  </body>
</html>
"""

@app.post("/api/upload")
async def upload_api(file: UploadFile = File(...)):
    name = PurePath(file.filename).name
    dest = UPLOAD_DIR / name
    # 流式写盘，避免一次性读入内存
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)  # 1 MiB
            if not chunk:
                break
            f.write(chunk)
    return JSONResponse({"ok": True, "saved": str(dest)})


## 读取配置路由
@app.get("/get_config", summary="获取当前的 ViiR 配置")
def get_config_endpoint():
    """读取并返回 config.yaml 的当前内容。"""
    return read_config()

# 测试示例 (使用 curl):
# 1. GET: curl http://localhost:8000/get_config
# 2. POST (更新): 
# curl -X POST http://localhost:8000/update_config \
#      -H "Content-Type: application/json" \
#      -d '{"threads": 32, "pvalue": 0.05, "SS_lib_type": "No"}'

## 更新配置路由
@app.post("/update_config", summary="更新 ViiR 配置中的特定参数")
def update_config_endpoint(new_params: ConfigUpdateParams):
    """
    接收 JSON 请求体，用于更新 config.yaml 中的参数。
    只更新请求体中提供的非空字段，未提供的字段保持不变。
    """
    # 1. 读取现有配置
    current_config = read_config()
    
    # 将 Pydantic 模型转换为字典，并排除值为 None 的字段
    update_data = new_params.dict(by_alias=True, exclude_none=True)
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid parameters provided for update.")

    # 2. 遍历更新数据，并应用到当前配置
    for key, value in update_data.items():
        # 只有当键存在于当前配置中时才进行更新（防止意外添加新的顶级键）
        if key in current_config:
            current_config[key] = value
        else:
            print(f"Warning: Key '{key}' not found in existing config. Skipping update.")

    # 3. 写入更新后的配置
    write_config(current_config)

    # 4. 返回成功信息和更新后的配置
    return {
        "status": "success", 
        "message": f"Config updated successfully. {len(update_data)} fields changed.",
        "updated_fields": list(update_data.keys()),
        "current_config": current_config
    }



@app.post("/run")
async def run(
    file: UploadFile = File(..., description="Upload config.yaml for ViiR pipeline"),
    params: Optional[str] = Form(default="", description="Extra parameters (optional)")
):
    """上传配置文件并启动单任务"""
    if JOB["status"] == "running":
        return JSONResponse({"error": "busy"}, status_code=409)

    WORKSPACE.mkdir(parents=True, exist_ok=True)

    # 清理旧日志
    if LOG_FILE.exists():
        LOG_FILE.unlink(missing_ok=True)

    # 保存配置文件
    with open(CONFIG_PATH, "wb") as f:
        shutil.copyfileobj(file.file, f)
    log.info(f"[UPLOAD] config saved to {CONFIG_PATH}")

    # 启动后台线程
    extra = params.strip().split() if params else []
    t = threading.Thread(target=run_viir, args=(extra,), daemon=True)
    t.start()

    return {"status": "started"}

@app.get("/status")
def status():
    """查询任务状态"""
    return {
        "status": JOB["status"],
        "started_at": JOB["started_at"],
        "finished_at": JOB["finished_at"],
        "returncode": JOB["returncode"],
    }

@app.get("/logs", response_class=PlainTextResponse)
def logs(tail: int = 300):
    """读取末尾日志"""
    if not LOG_FILE.exists():
        return ""
    try:
        with open(LOG_FILE, "rb") as f:
            return b"".join(f.readlines()[-tail:]).decode("utf-8", "ignore")
    except Exception as e:
        log.error(f"[LOG] read error: {e}")
        return ""

# 方便前端列清单
@app.get("/results")
def results():
    out_path = infer_out_dir(CONFIG_PATH, WORKSPACE)
    if not out_path.exists():
        return []
    wanted = [
        "40_DESeq2/volcano.tsv",
        "60_fasta/summary_table.txt",
        "70_barrnap/rRNA_summary_table.txt",
        "80_kmer/kmer_summary_table.txt",
        "90_blastn/blastn_result.tsv",
    ]
    out = [{"path": "run_viir.log", "size": LOG_FILE.stat().st_size, "mtime": LOG_FILE.stat().st_mtime}] if LOG_FILE.exists() else []
    for rel in wanted:
        p = out_path / rel
        if p.exists():
            s = p.stat()
            out.append({"path": str(p), "size": s.st_size, "mtime": s.st_mtime})
    return out



@app.get("/download")
def download():
    out_path = infer_out_dir(CONFIG_PATH, WORKSPACE)
    if not out_path.exists():
        return JSONResponse({"error": "[download func] out dir not found"}, status_code=404)

    tmpzip = Path(tempfile.gettempdir()) / f"viir_results.zip"
    if tmpzip.exists(): tmpzip.unlink()
    with zipfile.ZipFile(tmpzip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in out_path.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(out_path))
    return FileResponse(tmpzip, filename="viir_results.zip", media_type="application/zip")



# -----------------------------------------------------------
# 启动信息
# -----------------------------------------------------------
@app.on_event("startup")
def startup_event():
    log.info("=== Web-ViiR backend ready ===")
    log.info(f"WORKSPACE: {WORKSPACE}")
    log.info(f"VIIR_BIN : {VIIR_BIN}")
    log.info(f"MAMBA_BIN: {MAMBA}")
