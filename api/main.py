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
import psutil
import signal
from contextlib import contextmanager
from pathlib import Path, PurePath
from typing import Optional, Dict, Literal, List
import tempfile, zipfile
from tempfile import NamedTemporaryFile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query,BackgroundTasks, Request, Body
from fastapi.responses import PlainTextResponse, FileResponse, JSONResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, field_validator, Field  
# from .settings import DATA_ROOT, PIPELINE_SH, DEFAULT_ARGS
from starlette.background import BackgroundTask
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
LOG_FILE = WORKSPACE / "pipeline_run_viir.log"

VIIR_BIN = os.environ.get("VIIR_BIN", "/usr/local/bin/viir")
MAMBA = os.environ.get("MAMBA_BIN", "/usr/local/bin/micromamba")
PARTS = 3  # 默认分割数


SAMPLE_LIST_DIR = ROOT / "sample_lists"

CONFIG_PATH = WORKSPACE / "config.yaml"
CONFIG_DIR = ROOT / "configs"
DEFAULT_CONFIG_FILES_FOLDER = "/opt/viir/resources/"

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
    log.info(f"[SAFE_REL] input={path_str} => resolved={p}")
    if not str(p).startswith(str(ROOT)):
        raise HTTPException(status_code=400, detail="Illegal path")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def infer_out_dir(config_path: Path, workspace: Path) -> Path:
    # 读取 YAML（你已经引入了 yaml.safe_load）
    cfg = read_config()  # 已有函数
    out_val = cfg.get("out")
    log.info(f"[OUT_DIR] inferred 'out' from config.yaml: {out_val}")
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

def stream_cmd(cmd: list[str], cwd: Path | None = None, chunk_size: int = 16 * 1024 * 1024):
    """将外部命令 stdout 以生成器形式流式返回，避免落地大文件。"""
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd or WORKSPACE),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=chunk_size,
    )
    try:
        while True:
            chunk = proc.stdout.read(chunk_size)
            if not chunk:
                break
            yield chunk
        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read().decode("utf-8", "ignore")
            raise RuntimeError(f"Archive command failed: {err[:2000]}")
    finally:
        try:
            proc.stdout.close()
            proc.stderr.close()
        except Exception:
            pass


def iter_files(root: Path) -> list[Path]:
    """递归枚举 root 下所有文件。"""
    return [p for p in root.rglob("*") if p.is_file()]

def collect_lite_paths_by_folder(out_path: Path, cfg: dict) -> list[Path]:
    """
    从白名单目录收集文件 + 元信息（日志/配置/sample_list）。
    """
    WANTED_DIRS = [
        # "10_trinity",
        "30_count_matrix",
        "40_DESeq2",
        "60_fasta",
        "70_barrnap",
        "80_kmer",
        "90_blastn"
        # ... 其他你想要的文件夹
    ]
    run_id = infer_run_id_from_cfg(cfg)
    picks: List[Path] = []
    # 1) 白名单目录内文件
    for d in WANTED_DIRS:
        dp = out_path / d
        if dp.is_dir():
            picks.extend(iter_files(dp))
    # 2) 附加元信息
    if LOG_FILE.exists():
        picks.append(LOG_FILE)
    cfg_file = CONFIG_DIR / f"config__{run_id}.yaml"
    if cfg_file.exists():
        picks.append(cfg_file)
    sl_guess = SAMPLE_LIST_DIR / f"sample_list__{run_id}.txt"
    if sl_guess.exists():
        picks.append(sl_guess)
    return picks

def safe_rel_to(p: Path, base: Path) -> Path:
    """
    计算相对路径；不在 base 下的文件放到 meta/ 下，避免 tar -C 时路径失效。
    """
    try:
        return p.relative_to(base)
    except ValueError:
        return Path("meta") / p.name


def create_staging_tree(out_dir: Path, files: list[Path]) -> Path:
    """
    创建 staging 目录并把 files 映射进去：
      - 同盘：硬链接；跨盘：拷贝
    由调用者负责删除（配合 BackgroundTask）。
    """
    staging = Path(tempfile.mkdtemp(prefix="viir_lite_"))
    for src in files:
        rel = safe_rel_to(src, out_dir)
        dst = staging / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    return staging


# @contextmanager
# def build_staging_tree(out_path: Path, files: list[Path]):
#     """
#     为 lite 模式构建临时“只包含所需文件”的树：
#     - 同盘则硬链接（极快 & 几乎不占空间）
#     - 跨盘则拷贝
#     退出自动清理。
#     """
#     staging = Path(tempfile.mkdtemp(prefix="viir_lite_"))
#     try:
#         for src in files:
#             rel = safe_rel_to(src, out_path)
#             dst = staging / rel
#             dst.parent.mkdir(parents=True, exist_ok=True)
#             try:
#                 os.link(src, dst)  # 硬链接
#             except OSError:
#                 shutil.copy2(src, dst)  # 退化为拷贝
#         yield staging
#     finally:
#         shutil.rmtree(staging, ignore_errors=True)

def tar_name_and_media(fmt: str, base_name: str, lite: bool) -> tuple[list[str], str, str]:
    """
    返回：['tar', ...] 命令参数片段（不含 -C 和 '.'）、下载文件名、媒体类型。
    （真正命令由 make_tar_cmd 再拼 -C base '.'）
    """
    suffix = "__lite" if lite else ""
    if fmt == "tar":
        return (["-cf", "-"], f"{base_name}{suffix}.tar", "application/x-tar")
    if fmt == "tar.gz":
        return (["-czf", "-"], f"{base_name}{suffix}.tar.gz", "application/gzip")
    if fmt == "tar.zst":
        if has_cmd("zstd"):
            return (["--zstd", "-cf", "-"], f"{base_name}{suffix}.tar.zst", "application/zstd")
        # 无 zstd 回退 gzip
        return (["-czf", "-"], f"{base_name}{suffix}.tar.gz", "application/gzip")
    raise ValueError("unsupported tar format")


def make_tar_cmd(base_dir: Path, fmt: str, base_name: str, lite: bool) -> tuple[list[str], str, str]:
    """
    统一构建 tar 命令：tar -C <base_dir> <fmt_flags> - .   —— argv 永远短，不会 E2BIG
    """
    fmt_flags, filename, media = tar_name_and_media(fmt, base_name, lite)
    cmd = ["tar", "-C", str(base_dir)] + fmt_flags + ["."]
    return cmd, filename, media

def zip_to_tmp(base_dir: Path, base_name: str, lite: bool) -> Path:
    """
    将 base_dir 写成 zip 临时文件（zip 无法像 tar 一样流式组合目录）。
    """
    tmpdir = Path(tempfile.gettempdir())
    zipname = tmpdir / (f"{base_name}__lite.zip" if lite else f"{base_name}.zip")
    if zipname.exists():
        zipname.unlink()
    with zipfile.ZipFile(zipname, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in iter_files(base_dir):
            zf.write(p, p.relative_to(base_dir))
    return zipname


# -------------  log used ------
# 正则定义：匹配典型的重复进度行
_PATTERNS_PROGRESS = [
    re.compile(r"^succeeded\(\d+\)\s+\d+\.\d+% completed"),  # ParaFly
    re.compile(r"^\s*\[\d+M\]\s+Kmers parsed"),              # Jellyfish 等
    re.compile(r"^ROUND\s*=\s*\d+,"),                        # RNA assembly 循环
]

def compress_log_lines(lines: list[str]) -> list[str]:
    """
    去除连续重复的进度输出，只保留最后一行。
    """
    filtered = []
    last_match = None

    for line in lines:
        # 检查是否是进度类输出
        if any(p.match(line) for p in _PATTERNS_PROGRESS):
            last_match = line.strip()
            continue  # 暂不写入，等遇到不同内容再输出最后一个
        else:
            # 遇到非进度行，先 flush 上一个进度
            if last_match:
                filtered.append(last_match)
                last_match = None
            filtered.append(line.rstrip())

    # 文件末尾还有挂起的进度行
    if last_match:
        filtered.append(last_match)

    return filtered



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

    # WORKSPACE.mkdir(parents=True, exist_ok=True)
    log.info(f"[RUN] starting: {' '.join(cmd_list)}")

    try:
        with open(LOG_FILE, "wb") as lf:
            proc = subprocess.Popen(
                cmd_list,
                stdout=lf,
                stderr=subprocess.STDOUT,
                cwd=WORKSPACE,
                preexec_fn=os.setsid     # ★ 这句非常关键！
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

# def _find_first_match(folder: Path, patterns: list[str]) -> Path | None:
#     for pat in patterns:
#         hit = next(sorted(folder.glob(pat)), None)
#         if hit:
#             return hit
#     return None
def _find_first_match(folder: Path, patterns: list[str]) -> Path | None:
    for pat in patterns:
        for hit in folder.glob(pat):
            return hit
    return None




def collect_split_pairs(out_dir: Path, parts: int) -> list[tuple[Path, Path]]:
    """
    Gather already-split R1/R2 pairs from out_dir without re-running split2.
    Supports filenames like:
      *_1.part_001.fastq.gz
      *_R1_*.part_001.fastq.gz
      *.1.part_001.fastq.gz
      (and fq.gz variants)
    """
    pairs: list[tuple[Path, Path]] = []
    for i in range(1, parts + 1):
        pi = f"part_{i:03d}"
        r1p = _find_first_match(out_dir, [
            f"*_1.{pi}.fq.gz", f"*_1.{pi}.fastq.gz",
            f"*_R1*.{pi}.fq.gz", f"*_R1*.{pi}.fastq.gz",
            f"*.1.{pi}.fq.gz", f"*.1.{pi}.fastq.gz",
        ])
        r2p = _find_first_match(out_dir, [
            f"*_2.{pi}.fq.gz", f"*_2.{pi}.fastq.gz",
            f"*_R2*.{pi}.fq.gz", f"*_R2*.{pi}.fastq.gz",
            f"*.2.{pi}.fq.gz", f"*.2.{pi}.fastq.gz",
        ])
        if r1p and r2p:
            pairs.append((r1p, r2p))
    return pairs

def resolve_batch_dir(group: str, requested: str) -> tuple[Path, str]:
    """
    根据请求的 batch 名查找目录；若不存在，则在该 group 下尝试唯一子目录。
    返回 (batch_dir, resolved_batch_name)
    """
    group_dir = ROOT / "NGS_data" / group
    cand = group_dir / requested
    if cand.exists():
        return cand, cand.name

    # fallback: 找到包含 FASTQ 的唯一子目录
    subdirs = [p for p in group_dir.iterdir() if p.is_dir()]
    fastq_dirs = []
    for d in subdirs:
        r1s, r2s = split_detect_pairs(d)
        if r1s and r2s:
            fastq_dirs.append(d)
    if len(fastq_dirs) == 1:
        return fastq_dirs[0], fastq_dirs[0].name

    opts = ", ".join(p.name for p in fastq_dirs) or "none"
    raise HTTPException(404, f"Batch '{requested}' not found under {group_dir}. Available with FASTQ: {opts}")

def split_detect_pairs(folder: Path) -> tuple[list[str], list[str]]:
    """
    更宽松的 R1/R2 匹配，兼容常见命名：
      *_R1*.fastq.gz / *_R2*.fastq.gz
      *_1.fastq.gz / *_2.fastq.gz
      *.1.fastq.gz / *.2.fastq.gz
      以及 fq.gz 变体
    """
    patterns_r1 = [
        "*_R1*.fastq.gz", "*_R1*.fq.gz",
        "*_1.fastq.gz", "*_1.fq.gz",
        "*.1.fastq.gz", "*.1.fq.gz",
        "R1*.fastq.gz", "R1*.fq.gz",
    ]
    patterns_r2 = [
        "*_R2*.fastq.gz", "*_R2*.fq.gz",
        "*_2.fastq.gz", "*_2.fq.gz",
        "*.2.fastq.gz", "*.2.fq.gz",
        "R2*.fastq.gz", "R2*.fq.gz",
    ]
    pat1: list[Path] = []
    pat2: list[Path] = []
    for pat in patterns_r1:
        pat1 = list(folder.glob(pat))
        if pat1:
            break
    for pat in patterns_r2:
        pat2 = list(folder.glob(pat))
        if pat2:
            break
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
def prepare_fastq(sel: dict = Body(...)):
    """
    接收: {"N": "dsRNA_3", "V": "dsRNA_4"}，仅对这两个批次处理
    生成: /workspace/sample_lists/sample_list__N_vs_V__TS.txt
    """
    nb = slug(sel.get("N", ""))
    vb = slug(sel.get("V", ""))
    if not nb or not vb:
        raise HTTPException(400, "Both 'N' and 'V' batch names are required")

    # 解析实际 batch 目录（若用户未输入正确批次名，则尝试唯一可用目录）
    n_dir, n_batch = resolve_batch_dir("N", nb)
    v_dir, v_batch = resolve_batch_dir("V", vb)

    run_id = new_run_id(n_batch, v_batch)
    pairs = [("N", n_batch, n_dir), ("V", v_batch, v_dir)]
    lines = []

    for group, batch, batch_dir in pairs:
        r1s, r2s = split_detect_pairs(batch_dir)
        if not r1s or not r2s:
            raise HTTPException(400, f"No R1/R2 detected in {batch_dir}")

        out_dir = ROOT / "splited_fastq" / batch_dir.name
        ensure_dir_exists(out_dir)

        # 优先使用已存在的 split 结果
        pairs_ready = collect_split_pairs(out_dir, PARTS)

        # 如果不存在，则运行 split2 再收集
        if not pairs_ready:
            cmd = [
                MAMBA, "run", "-n", "viir",
                "seqkit", "split2",
                "-1", r1s[0], "-2", r2s[0],
                "-p", str(PARTS), "-O", str(out_dir), "-f"
            ]
            split_run(cmd, cwd=ROOT)
            pairs_ready = collect_split_pairs(out_dir, PARTS)

        if not pairs_ready:
            raise HTTPException(status_code=400, detail=f"No FASTQ pairs found in {out_dir} (looked for part_XXX R1/R2)")

        for r1p, r2p in pairs_ready:
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
    log.info(f"[READ_FILE] reading file at {p}, {str(p).startswith(str(WORKSPACE))} and {str(p).startswith(str(DEFAULT_CONFIG_FILES_FOLDER))}")
    if not str(p).startswith(str(WORKSPACE)) and not str(p).startswith(str(DEFAULT_CONFIG_FILES_FOLDER)):
        raise HTTPException(400, "Only /workspace files are readable")
    if not p.exists() or not p.is_file(): raise HTTPException(404, "Not found")
    return p.read_text("utf-8", "ignore")



## 读取配置路由
# @app.get("/get_config", summary="获取当前的 ViiR 配置")
@app.get("/get_config", summary="Got current ViiR config")
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


@app.get("/api/file/{filename}", response_class=PlainTextResponse)
async def get_file_content(filename: str):
    """
    根据文件名返回文件的纯文本内容。
    """
    # 确保只允许读取指定目录下的文件，防止路径遍历攻击
    file_path = os.path.join(WORKSPACE, filename)
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
        
    # 检查文件是否在允许的目录下
    if not file_path.startswith(WORKSPACE):
        raise HTTPException(status_code=403, detail="Forbidden path access")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 返回纯文本响应
        return PlainTextResponse(content)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")


# 最近任务（扫描 /workspace/configs & 输出）
@app.get("/list_runs")
def list_runs():
    items=[]
    for p in sorted((CONFIG_DIR).glob("config__*.yaml"), reverse=True)[:20]:
        run = p.stem.replace("config__","")
        out = infer_out_dir(CONFIG_PATH, WORKSPACE)  # 或者按 run 拼出 out，随你
        # st = JOB["status"] if JOB.get("cmd","").endswith(run) else "pending"
        cmd = JOB.get("cmd") or ""
        st = JOB["status"] if cmd.endswith(run) else "pending"
        items.append({"run":run,"status":st})
    return items

# 枚举批次目录
@app.get("/list_batches")
def list_batches():
    root = ROOT/"NGS_data"
    out={}
    for g in ["N","V"]:
        d = root/g
        out[g] = [p.name for p in d.iterdir() if p.is_dir()] if d.exists() else []
    return out

@app.get("/list_sample_lists")
def list_sample_lists():
    items=[]
    if SAMPLE_LIST_DIR.exists():
        for p in sorted(SAMPLE_LIST_DIR.glob("sample_list__*.txt")):
            run = p.stem.replace("sample_list__","")
            items.append({"run_id": run, "sample_list_path": str(p)})
    return items





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
def logs(tail: int = 300, compact: bool = Query(True), max_bytes: int = 65536*4):
    """读取末尾日志,compact=True 时会把 \r 进度行压成单行。"""
    log.info(f"[LOG] get log with tail {tail} at {time.asctime()}")
    if not LOG_FILE.exists():
        return ""
    try:
        data = LOG_FILE.read_bytes()[-max_bytes:]
        text = data.decode("utf-8", "ignore")
        if compact:
            # 逐行清理：保留每行中最后一次 \r 之后的内容
            # cleaned = []
            # for ln in text.splitlines():
            #     if "\r" in ln:
            #         ln = ln.split("\r")[-1]
            #     cleaned.append(ln)
            # text = "\n".join(cleaned[-tail:])
            text = "\n".join(compress_log_lines(text.splitlines())[-tail*10:])
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
        "10_trinity/trinity_assembly.Trinity.fasta",
        "40_DEGseq2/DEGseq2_isoform_result/RSEM.isoform.counts.matrix.N_vs_V.DESeq2.DE_results",
        "60_fasta/summary_table.txt",
        "60_fasta/all.fasta",
        "70_barrnap/rRNA_summary_table.txt",
        "80_kmer/kmer_summary_table.txt",
        "90_blastn/blastn_result.tsv",
        "run_viir.log"
    ]
    out = [{"path": "web_run_viir.log", "size": LOG_FILE.stat().st_size, "mtime": LOG_FILE.stat().st_mtime}] if LOG_FILE.exists() else []
    for rel in wanted:
        p = out_path / rel
        if p.exists():
            s = p.stat()
            out.append({"path": str(p), "size": s.st_size, "mtime": s.st_mtime})
    return out


@app.post("/stop")
def stop_pipeline():
    pid = JOB.get("pid")
    if not pid:
        return {"status": "no-process"}

    try:
        # os.kill(pid, 9)  # 强制终止
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGKILL)
        JOB["status"] = "failed"
        JOB["finished_at"] = time.time()
        JOB["returncode"] = -9
        return {"status": "stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/usage")
def usage():
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent

    if JOB["started_at"]:
        runtime = time.time() - JOB["started_at"]
    else:
        runtime = 0

    return {
        "cpu": cpu,
        "mem": mem,
        "runtime": runtime
    }


# 下载结果路由
# @app.get("/download")
# def download():
#     cfg = read_config()  
#     out_path = infer_out_dir(CONFIG_PATH, WORKSPACE)
#     if not out_path.exists():
#         return JSONResponse({"error": "[download func] out dir not found"}, status_code=404)

#     run_id = infer_run_id_from_cfg(cfg)
#     zipname = f"viir_results__{run_id}.zip"
#     tmpzip = Path(tempfile.gettempdir()) / zipname
#     if tmpzip.exists(): tmpzip.unlink()
#     with zipfile.ZipFile(tmpzip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
#         for p in out_path.rglob("*"):
#             if p.is_file():
#                 zf.write(p, p.relative_to(out_path))
#     return FileResponse(tmpzip, filename=zipname, media_type="application/zip")


def _add_file_header(path: Path, filename: str) -> dict:
    st = path.stat()
    return {
        "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        "Content-Length": str(st.st_size),
        "ETag": f'W/"{st.st_ino}-{st.st_size}-{int(st.st_mtime)}"',
    }



@app.get("/download2")
def download2(preset: str = "lite", format: str = "tar.gz"):
    """
    下载工件：
      preset: lite | full
      format: tar | tar.gz | tar.zst | zip
    - full:对 out_dir 直接打包
    - lite:先构建 staging 树，再对 staging 打包
    - tar 系列:全走流式;zip:落地临时文件
    """
    cfg = read_config()
    out_dir = infer_out_dir(CONFIG_PATH, WORKSPACE)
    if not out_dir.exists():
        return JSONResponse({"error": "[download] out dir not found"}, status_code=404)

    run_id = infer_run_id_from_cfg(cfg)
    base = f"viir_results__{run_id}"

    preset = (preset or "").lower()
    fmt = (format or "").lower()
    if preset not in ("lite", "full"):
        raise HTTPException(400, "preset must be lite or full")
    if fmt not in ("tar", "tar.gz", "tar.zst", "zip"):
        raise HTTPException(400, "format must be one of: tar, tar.gz, tar.zst, zip")

    is_lite = (preset == "lite")

    # 1) 准备 base_dir：full 直接用 out_dir；lite 构建 staging
    # ✅ 新：构建 staging，但不立刻清理；延长到响应完成后
    staging_path: Path | None = None
    if is_lite:
        picks = collect_lite_paths_by_folder(out_dir, cfg)
        if not picks:
            raise HTTPException(404, "No lite artifacts found")
        staging_path = create_staging_tree(out_dir, picks)
        base_dir = staging_path
    else:
        base_dir = out_dir

    if fmt in ("tar", "tar.gz", "tar.zst"):
        cmd, filename, media = make_tar_cmd(base_dir, fmt, base, is_lite)
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        
        # ✅ 新：把清理动作交给 BackgroundTask（传输完成后执行）
        bg = BackgroundTask(shutil.rmtree, base_dir, True) if staging_path else None
        return StreamingResponse(stream_cmd(cmd), media_type=media, headers=headers, background=bg)

    # zip：必须落地，再清理 zip（以及 staging）
    zip_path = zip_to_tmp(base_dir, base, is_lite)
    if staging_path:
        def cleanup(zip_p: Path, stage_p: Path):
            try: os.remove(zip_p)
            except Exception: pass
            shutil.rmtree(stage_p, ignore_errors=True)
        bg = BackgroundTask(cleanup, zip_path, staging_path)
    else:
        bg = BackgroundTask(os.remove, zip_path)
    return FileResponse(zip_path, filename=zip_path.name, media_type="application/zip", background=bg)


# -----------------------------------------------------------
# 启动信息
# -----------------------------------------------------------
@app.on_event("startup")
def startup_event():
    log.info("=== Web-ViiR backend ready ===")
    log.info(f"WORKSPACE: {WORKSPACE}")
    log.info(f"VIIR_BIN : {VIIR_BIN}")
    log.info(f"MAMBA_BIN: {MAMBA}")
