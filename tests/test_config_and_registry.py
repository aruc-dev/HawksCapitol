from __future__ import annotations

from pathlib import Path
import re
import unittest

from core.config_loader import ConfigError, load_config
from core.source_registry import load_source_registry, validate_enabled_sources


class ConfigAndRegistryTests(unittest.TestCase):
    def test_default_config_loads_and_enabled_sources_are_allowed(self) -> None:
        cfg = load_config()
        registry = load_source_registry(cfg["source_registry_path"])
        validate_enabled_sources(cfg["sources"], registry)
        self.assertEqual(cfg["mode"], "paper")
        self.assertFalse(cfg["execution"]["allow_live"])
        self.assertEqual(cfg["promotion"]["hcec2l_secret_id"], "hawkscapitol/live/keys")
        self.assertNotIn("market_data_source", cfg["backtest"])

    def test_paid_source_cannot_be_enabled(self) -> None:
        cfg = load_config()
        registry = load_source_registry(cfg["source_registry_path"])
        toggles = dict(cfg["sources"])
        toggles["finnhub"] = True
        with self.assertRaises(ConfigError):
            validate_enabled_sources(toggles, registry)

    def test_manual_reference_and_terms_unreviewed_sources_cannot_be_enabled(self) -> None:
        cfg = load_config()
        registry = load_source_registry(cfg["source_registry_path"])
        for source in ("capitoltrades_reference", "fmp", "congressinvests"):
            toggles = dict(cfg["sources"])
            toggles[source] = True
            with self.assertRaises(ConfigError, msg=source):
                validate_enabled_sources(toggles, registry)

    def test_python310_compatible_datetime_utc_usage(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        offenders = []
        import_pattern = r"^from datetime import .*" + r"\bUTC\b"
        direct_reference = "datetime." + "UTC"
        for path in repo_root.rglob("*.py"):
            relative_path = path.relative_to(repo_root)
            if any(part in {".git", ".venv", "__pycache__"} for part in relative_path.parts):
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(import_pattern, text, flags=re.MULTILINE) or direct_reference in text:
                offenders.append(str(relative_path))

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
