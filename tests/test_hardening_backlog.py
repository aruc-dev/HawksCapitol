from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class HardeningBacklogTests(unittest.TestCase):
    def test_phase_10_backlog_tracks_follow_up_beads_and_gates(self) -> None:
        text = (REPO_ROOT / "docs" / "hardening_backlog.md").read_text(encoding="utf-8")

        for bead_id in (
            "HawksCapitol-dxb",
            "HawksCapitol-3mn",
            "HawksCapitol-6hl",
            "HawksCapitol-88z",
            "HawksCapitol-0al",
            "HawksCapitol-7ud",
            "HawksCapitol-w62",
        ):
            self.assertIn(bead_id, text)
        for required in ("explicit human approval", "live_mode_guard", "network-free CI", "10-minute monitor"):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
