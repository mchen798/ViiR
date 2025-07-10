"""Utility helpers for ViiR."""
from __future__ import annotations

import logging
from pathlib import Path
from subprocess import CompletedProcess, run
from typing import List, Optional


log = logging.getLogger(__name__)


class CommandError(RuntimeError):
    """Raised when a subprocess fails."""


def run_cmd(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env: Optional[dict] = None,
    capture_output: bool = True,
    check: bool = True,
) -> CompletedProcess:
    """Call subprocess.run and log output."""
    log.info("Running command: %s", " ".join(cmd))
    result = run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=capture_output,
        text=True,
    )
    if check and result.returncode != 0:
        log.error("Command failed with exit code %s", result.returncode)
        log.error(result.stdout)
        log.error(result.stderr)
        raise CommandError("Command failed")
    return result
