"""Transcript quantification step."""
from pathlib import Path
from .config import Settings
from .utils import run_cmd


def do_quant(transcripts: Path, settings: Settings) -> Path:
    """Quantify transcript expression."""
    # TODO: build Salmon or similar command
    quant_dir = Path(settings.output_dir) / "quant"
    cmd = ["salmon", "quant", "-i", str(transcripts), "-o", str(quant_dir)]
    run_cmd(cmd)
    return quant_dir
