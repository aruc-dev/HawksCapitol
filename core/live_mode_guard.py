from __future__ import annotations


class LiveModeBlocked(RuntimeError):
    pass


def assert_live_allowed(cfg: dict, human_approved: bool = False) -> None:
    if cfg.get("mode") != "live":
        return
    execution = cfg.get("execution", {})
    if not execution.get("allow_live") or not human_approved:
        raise LiveModeBlocked("live mode requires allow_live=true and explicit human approval")
