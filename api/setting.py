from pathlib import Path
import os

DATA_ROOT = Path(os.environ.get("VIIR_WORKFOLDER", "/workspace"))
DATA_ROOT.mkdir(parents=True, exist_ok=True)

# 你的脚本路径（按你的仓库约定改），这里假设在 /viir-core 里
PIPELINE_SH = os.environ.get("VIIR_PIPELINE_SH", "viir")

# 若需要，给 bash 传参的默认项（先留空，后面再扩）
DEFAULT_ARGS = []
