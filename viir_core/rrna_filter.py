"""rRNA filtering step."""
from pathlib import Path
from .config import Settings
from .utils import run_cmd


def do_rrna_filter(transcripts: Path, settings: Settings) -> Path:
    """Filter rRNA sequences."""
    # TODO: build rRNA filtering command
    filtered = Path(settings.output_dir) / "rrna_filtered.fasta"
    cmd = ["barrnap", str(transcripts), "-o", str(filtered)]
    run_cmd(cmd)
    return filtered
