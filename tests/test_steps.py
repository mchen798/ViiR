import pathlib
from viir_core import trimming, assembly, quantification, rrna_filter, hmmscan, diffexpr


class DummyResult:
    returncode = 0
    stdout = ""
    stderr = ""

def fake_run(cmd, cwd=None, env=None, capture_output=True, check=True):
    fake_run.last_cmd = cmd
    return DummyResult()


def test_do_trim(monkeypatch):
    monkeypatch.setattr(trimming, "run_cmd", fake_run)
    settings = trimming.Settings()
    trimming.do_trim(pathlib.Path("reads.fq"), settings)
    assert fake_run.last_cmd[0] == "trimmomatic"


def test_do_assemble(monkeypatch):
    monkeypatch.setattr(assembly, "run_cmd", fake_run)
    settings = assembly.Settings()
    assembly.do_assemble(pathlib.Path("trimmed.fq"), settings)
    assert fake_run.last_cmd[0] == "trinity"


def test_do_quant(monkeypatch):
    monkeypatch.setattr(quantification, "run_cmd", fake_run)
    settings = quantification.Settings()
    quantification.do_quant(pathlib.Path("transcripts.fa"), settings)
    assert fake_run.last_cmd[0] == "salmon"


def test_do_rrna(monkeypatch):
    monkeypatch.setattr(rrna_filter, "run_cmd", fake_run)
    settings = rrna_filter.Settings()
    rrna_filter.do_rrna_filter(pathlib.Path("transcripts.fa"), settings)
    assert fake_run.last_cmd[0] == "barrnap"


def test_do_hmmscan(monkeypatch):
    monkeypatch.setattr(hmmscan, "run_cmd", fake_run)
    settings = hmmscan.Settings()
    hmmscan.do_hmmscan(pathlib.Path("transcripts.fa"), settings)
    assert fake_run.last_cmd[0] == "hmmscan"


def test_do_diffexpr(monkeypatch):
    monkeypatch.setattr(diffexpr, "run_cmd", fake_run)
    settings = diffexpr.Settings()
    diffexpr.do_diffexpr(pathlib.Path("counts.tsv"), settings)
    assert fake_run.last_cmd[0] == "Rscript"
