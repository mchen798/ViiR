"""Transcriptome assembly step."""
from pathlib import Path
from .config import Settings
from .utils import run_cmd


def do_assemble(trimmed_fastq: Path, settings: Settings) -> Path:
    """Run assembly step and return transcript fasta."""
    # TODO: build Trinity command
    assembly = Path(settings.output_dir) / "assembly.fasta"
    cmd = ["trinity", "--left", str(trimmed_fastq), "--output", str(assembly)]
    run_cmd(cmd)
    return assembly
