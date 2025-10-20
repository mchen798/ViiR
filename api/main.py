import os
import time
from datetime import datetime
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
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query,BackgroundTasks, Request, Body
from fastapi.responses import PlainTextResponse, FileResponse, JSONResponse, HTMLResponse, StreamingResponse
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
# WORKSPACE = Path(os.environ.get("WORKSPACE", "/workspace"))
WORKSPACE = ROOT
LOG_FILE = WORKSPACE / "run_viir.log"

VIIR_BIN = os.environ.get("VIIR_BIN", "/usr/local/bin/viir")
MAMBA = os.environ.get("MAMBA_BIN", "/usr/local/bin/micromamba")
PARTS = 3  # 默认分割数


SAMPLE_LIST_DIR = ROOT / "sample_lists"

CONFIG_PATH = WORKSPACE / "config.yaml"
CONFIG_DIR = ROOT / "configs"

RUN_ID_KEY = "run-id"
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
# 路径/命名相关功能函数
#------------------------
def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "").strip("_")[:80]

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


def new_run_id(n_batch: str, v_batch: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{n_batch}_vs_{v_batch}__{ts}"

def infer_run_id_from_cfg(cfg: dict) -> str:
    # 1) 明确字段优先
    rid = (cfg.get(RUN_ID_KEY) or "").strip()
    if rid:
        return rid
    # 2) 从 out 目录推断：/workspace/viir_out/viir__<suffix>
    out = str(cfg.get("out") or "")
    m = re.search(r"viir__([^/]+)$", out)  # 取最后一段
    if m:
        return m.group(1)
    # 3) 从 fastq-list 推断：.../sample_list__<suffix>.txt
    fl = str(cfg.get("fastq-list") or "")
    m = re.search(r"sample_list__([^/]+)\.txt$", fl)
    if m:
        return m.group(1)
    # 4) 兜底：时间戳
    return datetime.now().strftime("%Y%m%d-%H%M%S")

def has_cmd(name: str) -> bool:
    return shutil.which(name) is not None

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

def save_upload_file(uf: UploadFile, dest_dir: Path) -> Path:
    ensure_dir_exists(dest_dir)
    target = dest_dir / PurePath(uf.filename).name
    with open(target, "wb") as f:
        while True:
            chunk = uf.file.read(1024 * 1024 * 16)
            if not chunk: break
            f.write(chunk)
    return target


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
    batch = slug(batch)
    if not batch.strip():
        raise HTTPException(status_code=400, detail="batch is required")
    saved = []
    up_fq_base_dir = f"NGS_data/{group}/{batch}/"
    ensure_dir_exists(ROOT / up_fq_base_dir)
    for uf in files:
        resp = await upload_api(uf, dest=up_fq_base_dir)  # 复用上面的逻辑
        # p = save_upload_file(uf, dest_dir)
        saved.append(resp.body.decode() if hasattr(resp, "body") else resp)
        # saved.append(str(p))
    return {"ok": True, "dir": str(ROOT / up_fq_base_dir), "count": len(files), "files": saved}

# 数据预处理: 分割FSTAQ并生成 sample_list.txt
@app.post("/prepare_fastq")
# def prepare_fastq(parts: int = 3):
def prepare_fastq(sel: dict = Body(...)):
    """
    接收: {"N": "dsRNA_3", "V": "dsRNA_4"}，仅对这两个批次处理
    生成: /workspace/sample_lists/sample_list__N_vs_V__TS.txt
    """
    nb = slug(sel.get("N", ""))
    vb = slug(sel.get("V", ""))
    if not nb or not vb:
        raise HTTPException(400, "Both 'N' and 'V' batch names are required")

    run_id = new_run_id(nb, vb)

    pairs = [("N", nb), ("V", vb)]
    lines = []

    for group, batch in pairs:
    # for group in ["N", "V"]:
        batch_dir = ROOT / "NGS_data" / group / batch
        if not batch_dir.exists():
            raise HTTPException(404, f"{batch_dir} not found")

        r1s, r2s = split_detect_pairs(batch_dir)
        if not r1s or not r2s:
            raise HTTPException(400, f"No R1/R2 detected in {batch_dir}")

        out_dir = ROOT / "splited_fastq" / batch_dir.name
        ensure_dir_exists(out_dir)

        # 用 micromamba 环境里的 seqkit
        cmd = [
            MAMBA, "run", "-n", "viir",
            "seqkit", "split2",
            "-1", r1s[0], "-2", r2s[0],
            "-p", str(PARTS), "-O", str(out_dir), "-f"
        ]
        split_run(cmd, cwd=ROOT)

        # 采集输出 part 文件名，按 part_001..part_{parts} 逐一写入行
        for i in range(1, PARTS + 1):
            pi = f"part_{i:03d}"
            r1p = next(out_dir.glob(f"*_1.{pi}.fq.gz"), None)
            r2p = next(out_dir.glob(f"*_2.{pi}.fq.gz"), None)
            if r1p and r2p:
                lines.append(f"{group} {r1p} {r2p}")

    if not lines:
        raise HTTPException(status_code=400, detail="No FASTQ pairs found to split")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    # suffix = f"{nb}_vs_{vb}__{ts}"
    ensure_dir_exists(SAMPLE_LIST_DIR)
    sl = SAMPLE_LIST_DIR / f"sample_list__{run_id}.txt"
    sl.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"ok": True, "sample_list": str(sl), "lines": len(lines), "run_id": run_id}

@app.get("/read_file", response_class=PlainTextResponse)
def read_file(path: str):
    p = Path(path)
    if not str(p).startswith(str(WORKSPACE)):
        raise HTTPException(400, "Only /workspace files are readable")
    if not p.exists() or not p.is_file(): raise HTTPException(404, "Not found")
    return p.read_text("utf-8", "ignore")



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

# ========== 新增：保存并激活带后缀的 config ==========
@app.post("/save_config")
def save_config(payload: dict = Body(...)):
    """
    接收:
      {
        "yml": "<完整的config.yaml文本>",
        "suffix": "dsRNA_3_vs_dsRNA_4__20251020-0932",
        "activate": true  # 可选, 为 true 时将其作为活动配置写入 /workspace/config.yaml
      }
    返回:
      {"ok": true, "path": "/workspace/configs/config__<suffix>.yaml", "activated": true/false}
    """
    yml_text = payload.get("yml", "")
    suffix = payload.get("suffix", "").strip()
    activate = bool(payload.get("activate", False))
    if not yml_text:
        raise HTTPException(status_code=400, detail="yml is required")
    if not suffix:
        raise HTTPException(status_code=400, detail="suffix is required")

    # 确保目录
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # 写入带后缀的配置
    out_cfg = CONFIG_DIR / f"config__{suffix}.yaml"
    try:
        out_cfg.write_text(yml_text, encoding="utf-8")
        # 验证 YAML 基本格式
        _ = yaml.safe_load(yml_text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid yaml or write failed: {e}")

    activated = False
    if activate:
        try:
            # 将该配置设为“活动配置”，覆盖 /workspace/config.yaml
            shutil.copyfile(out_cfg, CONFIG_PATH)
            activated = True
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"activate failed: {e}")

    return {"ok": True, "path": str(out_cfg),"run_id": suffix,"activated": activated}


# ========== 新增：用“活动配置”直接启动 ==========
@app.post("/run_active")
async def run_active(request: Request):
    """
    使用 /workspace/config.yaml（活动配置）直接启动。
    不需要再上传文件，避免重复覆盖。
    """
    if JOB["status"] == "running":
        return JSONResponse({"error": "busy"}, status_code=409)

    # 清理旧日志
    if LOG_FILE.exists():
        LOG_FILE.unlink(missing_ok=True)

    # 简单校验活动配置是否存在
    if not CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail=f"Active config not found at {CONFIG_PATH}")


    # 兼容不同 Content-Type
    params = ""
    try:
      ct = request.headers.get("content-type", "")
      if "application/json" in ct:
          data = await request.json()
          params = (data.get("params") or "").strip()
      elif "application/x-www-form-urlencoded" in ct or "multipart/form-data" in ct:
          form = await request.form()
          params = (form.get("params") or "").strip()
      else:
          # 无 body 的情况
          params = ""
    except Exception:
      params = ""


    # 启动后台线程
    extra = params.strip().split() if params else []
    t = threading.Thread(target=run_viir, args=(extra,), daemon=True)
    t.start()
    return {"status": "started"}



# 任务启动路由 (单任务)
@app.post("/run")
async def run(
    file: UploadFile = File(..., description="Upload config.yaml for ViiR pipeline"),
    params: Optional[str] = Form(default="", description="Extra parameters (optional)")
):
    """上传配置文件并启动单任务"""
    if JOB["status"] == "running":
        return JSONResponse({"error": "busy"}, status_code=409)

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
def logs(tail: int = 300, compact: bool = Query(True), max_bytes: int = 65536):
    """读取末尾日志,compact=True 时会把 \r 进度行压成单行。"""
    log.info(f"[LOG] get log with tail {tail} at {time.asctime()}")
    if not LOG_FILE.exists():
        return ""
    try:
        data = LOG_FILE.read_bytes()[-max_bytes:]
        text = data.decode("utf-8", "ignore")
        if compact:
            # 逐行清理：保留每行中最后一次 \r 之后的内容
            cleaned = []
            for ln in text.splitlines():
                if "\r" in ln:
                    ln = ln.split("\r")[-1]
                cleaned.append(ln)
            text = "\n".join(cleaned[-tail:])
        else:
            # 维持原逻辑（按行尾）
            text = "\n".join(text.splitlines()[-tail:])
        return text
        # with open(LOG_FILE, "rb") as f:
        #     return b"".join(f.readlines()[-tail:]).decode("utf-8", "ignore")
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
    cfg = read_config()  
    out_path = infer_out_dir(CONFIG_PATH, WORKSPACE)
    if not out_path.exists():
        return JSONResponse({"error": "[download func] out dir not found"}, status_code=404)

    run_id = infer_run_id_from_cfg(cfg)
    zipname = f"viir_results__{run_id}.zip"
    tmpzip = Path(tempfile.gettempdir()) / zipname
    if tmpzip.exists(): tmpzip.unlink()
    with zipfile.ZipFile(tmpzip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in out_path.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(out_path))
    return FileResponse(tmpzip, filename=zipname, media_type="application/zip")


def collect_lite_paths_by_folder(out_path: Path, cfg: dict) -> list[Path]:
    """
    收集指定文件夹（白名单）内的所有文件。
    """
    WANTED_DIRS = [
        "10_trinity",
        "30_count_matrix",
        "40_DESeq2",
        "60_fasta",
        "70_barrnap",
        "80_kmer",
        "90_blastn"
        # ... 其他你想要的文件夹
    ]
    
    paths_to_zip = []
    # 1. 遍历白名单文件夹，并递归查找其中的所有文件
    for target_dir in WANTED_DIRS:
        # 构造目标文件夹的完整路径
        dir_path = out_path / target_dir
        # 检查目标文件夹是否存在
        if dir_path.is_dir():
            # 使用 rglob("*") 递归查找该文件夹下的所有文件
            for p in dir_path.rglob("*"):
                if p.is_file():
                    paths_to_zip.append(p)

    # 2. 加上日志、配置、sample_list（保持不变）
    if LOG_FILE.exists(): paths_to_zip.append(LOG_FILE)
    run_id = infer_run_id_from_cfg(cfg)
    cfg_file = (CONFIG_DIR / f"config__{run_id}.yaml")
    if cfg_file.exists(): paths_to_zip.append(cfg_file)
    sl_guess = SAMPLE_LIST_DIR / f"sample_list__{run_id}.txt"
    if sl_guess.exists(): paths_to_zip.append(sl_guess)
    
    return paths_to_zip

def stream_cmd(cmd: list[str], cwd: Path | None = None, chunk_size: int = 1024 * 1024 * 16):
    proc = subprocess.Popen(cmd, cwd=cwd or WORKSPACE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=chunk_size)
    try:
        while True:
            chunk = proc.stdout.read(chunk_size)
            if not chunk: break
            yield chunk
        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read().decode("utf-8", "ignore")
            raise RuntimeError(f"Archive command failed: {err[:2000]}")
    finally:
        try:
            proc.stdout.close(); proc.stderr.close()
        except Exception:
            pass


@app.get("/download2")
def download2(preset: str = "lite", format: str = "tar"):
    cfg = read_config()
    out_path = infer_out_dir(CONFIG_PATH, WORKSPACE)
    if not out_path.exists():
        return JSONResponse({"error": "[download func] out dir not found"}, status_code=404)

    run_id = infer_run_id_from_cfg(cfg)
    base_name = f"viir_results__{run_id}"

    preset = preset.lower()
    format = format.lower()
    if preset not in ("lite", "full"):
        raise HTTPException(400, "preset must be lite or full")

    # --- tar / tar.gz / tar.zst （推荐，流式） ---
    if format in ("tar", "tar.gz", "tar.zst"):
        if preset == "full":
            # 打整个 out 目录
            if format == "tar":
                cmd = ["tar", "-C", str(out_path), "-cf", "-", "."]
                filename = f"{base_name}.tar"
                media = "application/x-tar"
            elif format == "tar.gz":
                cmd = ["tar", "-C", str(out_path), "-czf", "-", "."]
                filename = f"{base_name}.tar.gz"
                media = "application/gzip"
            else:  # tar.zst
                if has_cmd("zstd"):
                    cmd = ["tar", "-C", str(out_path), "--zstd", "-cf", "-", "."]
                else:
                    # 退化为 tar.gz
                    cmd = ["tar", "-C", str(out_path), "-czf", "-", "."]
                    format = "tar.gz"
                filename = f"{base_name}.tar.zst" if format == "tar.zst" else f"{base_name}.tar.gz"
                media = "application/zstd" if format == "tar.zst" else "application/gzip"
        else:
            # lite：只打选中文件（放到临时 staging 目录下的相对路径结构）
            files = collect_lite_paths_by_folder(out_path, cfg)
            if not files:
                raise HTTPException(404, "No lite artifacts found")
            # 构造 tar 命令（传相对路径，保持扁平或按相对 out 的路径）
            # 这里用 -T 从列表读更简单，但为流式我们直接把相对列表拼到命令
            rels = []
            for p in files:
                try:
                    rels.append(str(p.relative_to(out_path)))
                except ValueError:
                    # 非 out_path 下的文件（如 run_viir.log/config），放在根
                    rels.append(str(p))

            if format == "tar":
                cmd = ["tar", "-C", str(out_path), "-cf", "-"] + rels
                filename = f"{base_name}__lite.tar"
                media = "application/x-tar"
            elif format == "tar.gz":
                cmd = ["tar", "-C", str(out_path), "-czf", "-"] + rels
                filename = f"{base_name}__lite.tar.gz"
                media = "application/gzip"
            else:
                if has_cmd("zstd"):
                    cmd = ["tar", "-C", str(out_path), "--zstd", "-cf", "-"] + rels
                    filename = f"{base_name}__lite.tar.zst"
                    media = "application/zstd"
                else:
                    cmd = ["tar", "-C", str(out_path), "-czf", "-"] + rels
                    filename = f"{base_name}__lite.tar.gz"
                    media = "application/gzip"

        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(stream_cmd(cmd), media_type=media, headers=headers)

    # --- zip（保留原逻辑；可选无压缩提升速度） ---
    elif format == "zip":
        # 注意：zip 不支持“流式添加+流式下载”，需要先落地。40GB 会很慢且占用两倍空间。
        compression = zipfile.ZIP_DEFLATED  # 或改成 ZIP_STORED 追求速度
        tmpdir = Path(tempfile.gettempdir())
        if preset == "full":
            zipname = tmpdir / f"{base_name}.zip"
            if zipname.exists(): zipname.unlink()
            with zipfile.ZipFile(zipname, "w", compression=compression) as zf:
                for p in out_path.rglob("*"):
                    if p.is_file():
                        zf.write(p, p.relative_to(out_path))
            return FileResponse(zipname, filename=zipname.name, media_type="application/zip")
        else:
            files = collect_lite_paths_by_folder(out_path, cfg)
            if not files:
                raise HTTPException(404, "No lite artifacts found")
            zipname = tmpdir / f"{base_name}__lite.zip"
            if zipname.exists(): zipname.unlink()
            with zipfile.ZipFile(zipname, "w", compression=compression) as zf:
                for p in files:
                    try:
                        arc = p.relative_to(out_path)
                    except ValueError:
                        arc = Path(p.name)
                    zf.write(p, arc)
            return FileResponse(zipname, filename=zipname.name, media_type="application/zip")
    else:
        raise HTTPException(400, "format must be one of: tar, tar.gz, tar.zst, zip")


# -----------------------------------------------------------
# 启动信息
# -----------------------------------------------------------
@app.on_event("startup")
def startup_event():
    log.info("=== Web-ViiR backend ready ===")
    log.info(f"WORKSPACE: {WORKSPACE}")
    log.info(f"VIIR_BIN : {VIIR_BIN}")
    log.info(f"MAMBA_BIN: {MAMBA}")
