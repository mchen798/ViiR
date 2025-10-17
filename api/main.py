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
from typing import Optional, Dict, Literal, List
import tempfile, zipfile
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, Request, HTTPException, Body
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

ROOT = Path("/workspace").resolve()
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

#------------------------
# 路径相关功能函数
#------------------------
def safe_rel(path_str: str) -> Path:
    """
    只允许写入 /workspace 下的相对路径；阻止 .. 、绝对路径等。
    """
    if not path_str:
        return ROOT
    rel = Path(path_str.strip().lstrip("/"))
    p = (ROOT / rel).resolve()
    if not str(p).startswith(str(ROOT)):
        raise HTTPException(status_code=400, detail="Illegal path")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def infer_out_dir(config_path: Path, workspace: Path) -> Path:
    # 读取 YAML（你已经引入了 yaml.safe_load）
    cfg = read_config()  # 已有函数
    out_val = cfg.get("out")
    if not out_val:
        raise HTTPException(status_code=400, detail="'out' not set in config.yaml")
    p = Path(out_val)
    return p if p.is_absolute() else (workspace / p)

def ensure_dir_exists(directory_path: Path):
    """
    检查目录是否存在。如果不存在，则创建它。
    如果目录已存在，则不做任何操作。
    """
    try:
        # parents=True 允许创建任何缺失的父目录
        # exist_ok=True 允许目录已经存在而不会引发 FileExistsError
        directory_path.mkdir(parents=True, exist_ok=True)
        log.info(f"[DIR_CHECK] Directory ensured: {directory_path}")
    except Exception as e:
        # 记录任何创建过程中发生的I/O错误或其他异常
        log.error(f"[DIR_ERROR] Failed to create directory {directory_path}: {e}")
        raise IOError(f"Failed to create directory {directory_path}") from e

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


#------------------------
# config相关功能函数
#------------------------
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

#-----------------------------------------
# 数据预处理相关功能函数 preprocessing
#-----------------------------------------

def split_run(cmd: list[str], cwd: Path | None = None):
    proc = subprocess.run(cmd, cwd=cwd or ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Command failed: {' '.join(cmd)}\n{proc.stdout[:4000]}")
    return proc.stdout

def split_detect_pairs(folder: Path) -> tuple[list[str], list[str]]:
    """
    简单匹配 R1/R2：优先 *_1.fq.gz / *_2.fq.gz；否则 *_R1* / *_R2*；再否则 *_1.fastq.gz / *_2.fastq.gz
    """
    pat1 = list(folder.glob("*_1.fq.gz"))
    pat2 = list(folder.glob("*_2.fq.gz"))
    if not pat1 or not pat2:
        pat1 = list(folder.glob("*_R1*.fq.gz")) or list(folder.glob("*_R1*.fastq.gz"))
        pat2 = list(folder.glob("*_R2*.fq.gz")) or list(folder.glob("*_R2*.fastq.gz"))
    if not pat1 or not pat2:
        pat1 = list(folder.glob("*_1.fastq.gz"))
        pat2 = list(folder.glob("*_2.fastq.gz"))
    return [str(p) for p in sorted(pat1)], [str(p) for p in sorted(pat2)]




# -----------------------------------------------------------
# API 路由
# -----------------------------------------------------------

@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"


@app.post("/api/upload")
async def upload_api(    
    file: UploadFile = File(...),
    dest: Optional[str] = Form(default="")  # 新增：允许前端传 /workspace 下的相对目标路径/文件名
):
    # 若 dest 为空 -> 使用原文件名；若 dest 是目录 -> 以原文件名落盘；若 dest 含文件名 -> 用它
    base_name = PurePath(file.filename).name
    if dest and dest.endswith("/"):
        target = safe_rel(dest) / base_name
    elif dest:
        target = safe_rel(dest)
    else:
        target = ROOT / base_name
    log.info(f"[UPLOAD_API] saving upload to {target} (from {file.filename})")
    # 流式写盘，避免一次性读入内存
    with open(target, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024 * 16)  # 16 MiB
            if not chunk:
                break
            f.write(chunk)
    return JSONResponse({"ok": True, "saved": str(dest)})

# 专用上传 NGS-FSTAQ 路由
@app.post("/api/upload_fastq")
async def upload_fastq(
    group: Literal["N", "V"] = Form(...),
    batch: str = Form(...),
    files: List[UploadFile] = File(...),
):
    if not batch.strip():
        raise HTTPException(status_code=400, detail="batch is required")
    saved = []
    up_fq_base_dir = f"NGS_data/{group}/{batch}/"
    ensure_dir_exists(ROOT / up_fq_base_dir)
    for uf in files:
        resp = await upload_api(uf, dest=up_fq_base_dir)  # 复用上面的逻辑
        saved.append(resp.body.decode() if hasattr(resp, "body") else resp)
    return {"ok": True, "dir": str(ROOT / up_fq_base_dir), "count": len(files)}

# 数据预处理: 分割FSTAQ并生成 sample_list.txt
@app.post("/prepare_fastq")
def prepare_fastq(parts: int = 3):
    """
    扫描 NGS_data/N 与 NGS_data/V 下的每个 batch：
    - 运行 seqkit split2 生成 splited_fastq/<batch> 下的 part_001..part_{parts}
    - 生成 /workspace/sample_list.txt
    """
    ngs = ROOT / "NGS_data"
    if not ngs.exists():
        raise HTTPException(status_code=404, detail="NGS_data not found")

    lines = []
    for group in ["N", "V"]:
        gdir = ngs / group
        if not gdir.exists():
            continue
        for batch_dir in sorted([p for p in gdir.iterdir() if p.is_dir()]):
            r1s, r2s = split_detect_pairs(batch_dir)
            if not r1s or not r2s:
                continue  # 跳过不完整的批次
            out_dir = ROOT / "splited_fastq" / batch_dir.name
            out_dir.mkdir(parents=True, exist_ok=True)

            # 用 micromamba 环境里的 seqkit
            cmd = [
                MAMBA, "run", "-n", "viir",
                "seqkit", "split2",
                "-1", r1s[0], "-2", r2s[0],
                "-p", str(parts), "-O", str(out_dir), "-f"
            ]
            split_run(cmd, cwd=ROOT)

            # 采集输出 part 文件名，按 part_001..part_{parts} 逐一写入行
            for i in range(1, parts + 1):
                pi = f"part_{i:03d}"
                r1p = next(out_dir.glob(f"*_1.{pi}.fq.gz"), None)
                r2p = next(out_dir.glob(f"*_2.{pi}.fq.gz"), None)
                if r1p and r2p:
                    lines.append(f"{group} {r1p} {r2p}")

    if not lines:
        raise HTTPException(status_code=400, detail="No FASTQ pairs found to split")

    sl = ROOT / "sample_list.txt"
    sl.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "sample_list": str(sl), "lines": len(lines)}


## 读取配置路由
@app.get("/get_config", summary="获取当前的 ViiR 配置")
def get_config_endpoint():
    """读取并返回 config.yaml 的当前内容。"""
    log.info(f"[GET] get current config at {CONFIG_PATH}")
    return read_config()

# 测试示例 (使用 curl):
# 1. GET: curl http://localhost:8000/get_config
# 2. POST (更新): 
# curl -X POST http://localhost:8000/update_config \
#      -H "Content-Type: application/json" \
#      -d '{"threads": 32, "pvalue": 0.05, "SS_lib_type": "No"}'

## 更新配置路由
    # 接收 JSON 请求体，用于更新 config.yaml 中的参数。
    # 只更新请求体中提供的非空字段，未提供的字段保持不变。
@app.post("/update_config", summary="更新 ViiR 配置中的特定参数")
def update_config_endpoint(new_params: ConfigUpdateParams):
    # 1. 读取现有配置
    current_config = read_config()
    # 将 Pydantic 模型转换为字典，并排除值为 None 的字段
    update_data = new_params.dict(by_alias=True, exclude_none=True)

    log.info(f"[UPDATE] update config with parameter {update_data}")
    
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

# 任务启动路由 (单任务)
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

# 任务状态路由
@app.get("/status")
def status():
    """查询任务状态"""
    return {
        "status": JOB["status"],
        "started_at": JOB["started_at"],
        "finished_at": JOB["finished_at"],
        "returncode": JOB["returncode"],
    }

# 读取日志路由
@app.get("/logs", response_class=PlainTextResponse)
def logs(tail: int = 300):
    """读取末尾日志"""
    log.info(f"[LOG] get log with tail {tail} at {time.asctime()}")
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

# 下载结果路由
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
