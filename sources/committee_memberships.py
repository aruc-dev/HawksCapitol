from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CommitteeSnapshot:
    as_of_date: date
    member_id: str
    committees: tuple[str, ...]


def visible_committees(snapshots: list[CommitteeSnapshot], member_id: str, as_of: date) -> tuple[str, ...]:
    visible = [s for s in snapshots if s.member_id == member_id and s.as_of_date <= as_of]
    if not visible:
        return ()
    return max(visible, key=lambda item: item.as_of_date).committees
