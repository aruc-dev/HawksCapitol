from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config_loader import load_config
from core.live_promotion import PromotionEvidence, evaluate_live_promotion
from core.serialization import to_jsonable
from scheduler.run_backtest import run as run_backtest_report


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def run(
    dry_run: bool = False,
    paper_weeks: float = 0.0,
    paper_trades: int = 0,
    paper_hit_rate: float = 0.0,
    paper_max_drawdown_pct: float = 1.0,
    human_approved: bool = False,
) -> dict:
    cfg = load_config()
    backtest = run_backtest_report(dry_run=True, days=1095)
    evidence = PromotionEvidence(
        backtest_verdict=backtest["validation"]["verdict"],
        paper_weeks=paper_weeks,
        paper_trades=paper_trades,
        paper_hit_rate=paper_hit_rate,
        paper_max_drawdown_pct=paper_max_drawdown_pct,
        origin_remote=_git_value("remote", "get-url", "origin"),
        branch=_git_value("branch", "--show-current"),
        human_approved=human_approved,
    )
    result = evaluate_live_promotion(cfg, evidence)
    result["mode"] = cfg["mode"]
    result["live_guard"] = {
        "allow_live": cfg.get("execution", {}).get("allow_live", False),
        "require_human_live_approval": cfg.get("execution", {}).get("require_human_live_approval", True),
        "live_orders_blocked_until_manual_config_change": True,
    }
    result["dry_run"] = dry_run
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--paper-weeks", type=float, default=0.0)
    parser.add_argument("--paper-trades", type=int, default=0)
    parser.add_argument("--paper-hit-rate", type=float, default=0.0)
    parser.add_argument("--paper-max-drawdown-pct", type=float, default=1.0)
    parser.add_argument("--human-approved", action="store_true")
    args = parser.parse_args()
    payload = run(
        dry_run=args.dry_run,
        paper_weeks=args.paper_weeks,
        paper_trades=args.paper_trades,
        paper_hit_rate=args.paper_hit_rate,
        paper_max_drawdown_pct=args.paper_max_drawdown_pct,
        human_approved=args.human_approved,
    )
    print(json.dumps(to_jsonable(payload), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
