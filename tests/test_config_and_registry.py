from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
