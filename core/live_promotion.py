from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromotionEvidence:
    backtest_verdict: str
    paper_weeks: float
    paper_trades: int
    paper_hit_rate: float
    paper_max_drawdown_pct: float
    origin_remote: str
    branch: str
    human_approved: bool = False


def normalize_github_remote(remote: str | None) -> str:
    if not remote:
        return ""
    value = remote.strip().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    prefixes = (
        "https://github.com/",
        "http://github.com/",
        "ssh://git@github.com/",
        "git@github.com:",
    )
    for prefix in prefixes:
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def evaluate_live_promotion(cfg: dict, evidence: PromotionEvidence) -> dict:
    promotion = cfg.get("promotion", {})
    reasons: list[str] = []
    required_verdict = promotion.get("required_backtest_verdict", "pass")
    min_weeks = promotion.get("min_paper_weeks", 4)
    min_trades = promotion.get("min_paper_trades", 20)
    min_hit_rate = promotion.get("min_paper_hit_rate", 0.5)
    max_drawdown = promotion.get("max_paper_drawdown_pct", 0.08)
    expected_origin = promotion.get("expected_origin")

    if cfg.get("mode") != "paper":
        reasons.append("promotion_review_must_start_from_paper_mode")
    if evidence.backtest_verdict != required_verdict:
        reasons.append("backtest_verdict_not_passed")
    if evidence.paper_weeks < min_weeks:
        reasons.append("insufficient_paper_weeks")
    if evidence.paper_trades < min_trades:
        reasons.append("insufficient_paper_trades")
    if evidence.paper_hit_rate < min_hit_rate:
        reasons.append("paper_hit_rate_below_gate")
    if evidence.paper_max_drawdown_pct > max_drawdown:
        reasons.append("paper_drawdown_above_gate")
    if promotion.get("require_origin_main", True):
        if evidence.branch != "main":
            reasons.append("deployment_branch_not_main")
        if expected_origin and normalize_github_remote(evidence.origin_remote) != normalize_github_remote(expected_origin):
            reasons.append("deployment_origin_mismatch")
    if not evidence.human_approved:
        reasons.append("explicit_human_live_approval_missing")

    return {
        "eligible": not reasons,
        "reasons": reasons,
        "criteria": {
            "required_backtest_verdict": required_verdict,
            "min_paper_weeks": min_weeks,
            "min_paper_trades": min_trades,
            "min_paper_hit_rate": min_hit_rate,
            "max_paper_drawdown_pct": max_drawdown,
            "require_origin_main": promotion.get("require_origin_main", True),
            "expected_origin": expected_origin,
            "hcec2l_secret_id": promotion.get("hcec2l_secret_id"),
        },
        "evidence": evidence.__dict__,
        "next_step": (
            "manual_live_change_review"
            if not reasons
            else "continue_paper_validation"
        ),
    }
