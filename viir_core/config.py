"""Configuration handling for ViiR."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict
import os

try:  # optional dependency
    import yaml as _yaml
except Exception:  # pragma: no cover
    _yaml = None


@dataclass
class Settings:
    """Application settings."""

    # Paths
    input_dir: Path = Path("input")
    output_dir: Path = Path("output")

    # Resources
    threads: int = 1
    memory_gb: int = 4

    # Thresholds
    kmers_min_count: int = 2
    hmmscan_evalue: float = 1e-5


def _naive_yaml_parse(path: Path) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    current: Dict[str, Any] | None = None
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith(":"):
                current = data.setdefault(line[:-1], {})
                continue
            key, val = line.split(":", 1)
            target = current if current is not None else data
            val = val.strip()
            if val.lower() in {"true", "false"}:
                parsed: Any = val.lower() == "true"
            else:
                try:
                    parsed = int(val)
                except ValueError:
                    try:
                        parsed = float(val)
                    except ValueError:
                        parsed = val
            target[key.strip()] = parsed
    return data


def _load_yaml(path: Path) -> Dict[str, Any]:
    if _yaml is not None:
        with path.open("r") as fh:
            return _yaml.safe_load(fh) or {}
    return _naive_yaml_parse(path)


def _flatten_config(data: Dict[str, Any]) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for section in data.values():
        if isinstance(section, dict):
            flat.update(section)
    return flat


def load_settings(config_path: Path | str | None = None) -> Settings:
    """Load settings from YAML file and environment variables."""
    if config_path is None:
        config_path = Path(__file__).resolve().parent / "config.yml"
    cfg_path = Path(config_path)
    data: Dict[str, Any] = {}
    if cfg_path.is_file():
        data = _load_yaml(cfg_path)
    flat = _flatten_config(data)
    # environment overrides
    for field in Settings.__dataclass_fields__:
        env_key = f"VIIR_{field.upper()}"
        if env_key in os.environ:
            flat[field] = os.environ[env_key]
    return Settings(**flat)
