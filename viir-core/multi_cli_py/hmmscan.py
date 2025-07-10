"""hmmscan step for viral detection."""
from pathlib import Path
from .config import Settings
from .utils import run_cmd


def do_hmmscan(transcripts: Path, settings: Settings) -> Path:
    """Scan transcripts with HMM models."""
    # TODO: build hmmscan command
    out_tbl = Path(settings.output_dir) / "hmmscan.tbl"
    cmd = ["hmmscan", "--tblout", str(out_tbl), "models.hmm", str(transcripts)]
    run_cmd(cmd)
    return out_tbl
