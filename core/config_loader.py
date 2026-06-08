from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_KEYS = ("mode", "risk", "signals", "exits", "sources", "execution")


class ConfigError(ValueError):
    pass


def load_structured_file(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ConfigError(f"{file_path} is not JSON and PyYAML is unavailable") from exc
        loaded = yaml.safe_load(text)
        if not isinstance(loaded, dict):
            raise ConfigError(f"{file_path} must contain a mapping")
        return loaded


def load_config(path: str | Path = "config/config.yaml") -> dict[str, Any]:
    cfg = load_structured_file(path)
    validate_config(cfg)
    return cfg


def validate_config(cfg: dict[str, Any]) -> None:
    missing = [key for key in REQUIRED_KEYS if key not in cfg]
    if missing:
        raise ConfigError(f"Missing required config keys: {', '.join(missing)}")
    if cfg["mode"] not in {"paper", "live"}:
        raise ConfigError("mode must be paper or live")
    if cfg["mode"] == "live" and not cfg.get("execution", {}).get("allow_live"):
        raise ConfigError("live mode requires execution.allow_live=true")
    risk = cfg.get("risk", {})
    for key in ("account_equity", "risk_per_trade_pct", "max_position_pct", "max_positions"):
        if key not in risk:
            raise ConfigError(f"Missing risk.{key}")
    if risk["risk_per_trade_pct"] <= 0 or risk["max_position_pct"] <= 0:
        raise ConfigError("risk percentages must be positive")
