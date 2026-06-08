from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config_loader import load_config
from core.source_registry import load_source_registry, validate_enabled_sources


def run(dry_run: bool = False) -> dict:
    cfg = load_config()
    registry = load_source_registry(cfg["source_registry_path"])
    validate_enabled_sources(cfg["sources"], registry)
    enabled = sorted(name for name, active in cfg["sources"].items() if active)
    return {"ok": True, "enabled_sources": enabled, "mode": cfg["mode"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.dry_run), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
