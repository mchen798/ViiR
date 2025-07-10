"""Differential expression step."""
from pathlib import Path
from .config import Settings
from .utils import run_cmd


def do_diffexpr(counts: Path, settings: Settings) -> Path:
    """Perform differential expression analysis."""
    # TODO: build DESeq2 or edgeR command
    result = Path(settings.output_dir) / "diffexpr.tsv"
    cmd = ["Rscript", "run_diffexpr.R", str(counts), str(result)]
    run_cmd(cmd)
    return result
