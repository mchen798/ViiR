"""Typer-based CLI for ViiR."""
from pathlib import Path
import typer

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.yml"

from .config import load_settings
from .trimming import do_trim
from .assembly import do_assemble
from .quantification import do_quant
from .rrna_filter import do_rrna_filter
from .hmmscan import do_hmmscan
from .diffexpr import do_diffexpr


app = typer.Typer(help="ViiR bioinformatics pipeline")


@app.command()
def trim(
    input: Path = typer.Argument(..., help="Input FASTQ file"),
    config: Path = typer.Option(DEFAULT_CONFIG, help="Path to config YAML"),
) -> None:
    """Run trimming step."""
    settings = load_settings(config)
    do_trim(input_fastq=input, settings=settings)


@app.command()
def assemble(
    input: Path = typer.Argument(..., help="Trimmed FASTQ file"),
    config: Path = typer.Option(DEFAULT_CONFIG, help="Path to config YAML"),
) -> None:
    """Run assembly step."""
    settings = load_settings(config)
    do_assemble(trimmed_fastq=input, settings=settings)


@app.command()
def quant(
    input: Path = typer.Argument(..., help="Assembled transcripts"),
    config: Path = typer.Option(DEFAULT_CONFIG, help="Path to config YAML"),
) -> None:
    """Run quantification step."""
    settings = load_settings(config)
    do_quant(transcripts=input, settings=settings)


@app.command()
def rrna(
    input: Path = typer.Argument(..., help="Assembled transcripts"),
    config: Path = typer.Option(DEFAULT_CONFIG, help="Path to config YAML"),
) -> None:
    """Filter rRNA reads."""
    settings = load_settings(config)
    do_rrna_filter(transcripts=input, settings=settings)


@app.command()
def hmmscan(
    input: Path = typer.Argument(..., help="Transcripts to scan"),
    config: Path = typer.Option(DEFAULT_CONFIG, help="Path to config YAML"),
) -> None:
    """Run hmmscan step."""
    settings = load_settings(config)
    do_hmmscan(transcripts=input, settings=settings)


@app.command()
def diff(
    input: Path = typer.Argument(..., help="Counts matrix"),
    config: Path = typer.Option(DEFAULT_CONFIG, help="Path to config YAML"),
) -> None:
    """Differential expression analysis."""
    settings = load_settings(config)
    do_diffexpr(counts=input, settings=settings)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
