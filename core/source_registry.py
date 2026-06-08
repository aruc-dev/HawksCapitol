from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.config_loader import ConfigError, load_structured_file


ALLOWED_COSTS = {"free", "free_key"}
BLOCKED_STATUSES = {"disabled", "manual_reference", "history_only"}


@dataclass(frozen=True)
class SourceRegistryEntry:
    name: str
    owner: str
    url: str
    official: bool
    cost: str
    terms_url: str
    terms_reviewed_at: str | None
    automated_access_allowed: bool
    production_status: str
    rate_limit: str = ""


def load_source_registry(path: str | Path = "config/source_registry.yaml") -> dict[str, SourceRegistryEntry]:
    data = load_structured_file(path)
    entries = {}
    for item in data.get("sources", []):
        entry = SourceRegistryEntry(**item)
        entries[entry.name] = entry
    return entries


def validate_enabled_sources(
    source_toggles: dict[str, bool],
    registry: dict[str, SourceRegistryEntry],
) -> None:
    for name, enabled in source_toggles.items():
        if not enabled:
            continue
        entry = registry.get(name)
        if entry is None:
            raise ConfigError(f"Enabled source {name} is missing from source registry")
        if entry.cost not in ALLOWED_COSTS:
            raise ConfigError(f"Enabled source {name} has blocked cost status {entry.cost}")
        if not entry.terms_reviewed_at:
            raise ConfigError(f"Enabled source {name} is missing terms_reviewed_at")
        if not entry.automated_access_allowed:
            raise ConfigError(f"Enabled source {name} does not allow automated access")
        if entry.production_status in BLOCKED_STATUSES:
            raise ConfigError(f"Enabled source {name} has blocked status {entry.production_status}")
