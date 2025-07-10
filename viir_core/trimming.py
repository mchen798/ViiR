"""Read trimming step."""
from pathlib import Path
from .config import Settings
from .utils import run_cmd


def do_trim(input_fastq: Path, settings: Settings) -> Path:
    """Run adapter trimming and quality filtering."""
    # TODO: build actual trimmomatic command using settings
    trimmed = Path(settings.output_dir) / "trimmed.fastq.gz"
    cmd = ["trimmomatic", "SE", str(input_fastq), str(trimmed)]  # Placeholder
    run_cmd(cmd)
    return trimmed
