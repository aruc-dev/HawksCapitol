from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from xml.etree import ElementTree

from core.models import parse_date


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


def parse_committee_snapshot_rows(rows: list[dict], default_as_of: date | None = None) -> list[CommitteeSnapshot]:
    snapshots = []
    for row in rows:
        as_of = parse_date(row.get("as_of_date") or row.get("as_of") or row.get("effective_date")) or default_as_of
        member_id = row.get("member_id")
        committees = row.get("committees") or row.get("committee") or ()
        if as_of is None or not member_id:
            continue
        if isinstance(committees, str):
            committees = tuple(part.strip() for part in committees.split(";") if part.strip())
        snapshots.append(CommitteeSnapshot(as_of, str(member_id), tuple(committees)))
    return sorted(snapshots, key=lambda item: (item.member_id, item.as_of_date))


def parse_committee_snapshot_xml(xml_text: str, as_of: date) -> list[CommitteeSnapshot]:
    root = ElementTree.fromstring(xml_text)
    rows = []
    for member in root.iter():
        children = {_local_name(child.tag).lower(): (child.text or "").strip() for child in list(member)}
        member_id = children.get("member_id") or children.get("bioguideid") or children.get("id")
        committee = children.get("committee") or children.get("committees")
        if member_id and committee:
            rows.append({"member_id": member_id, "committees": committee, "as_of_date": as_of})
    return parse_committee_snapshot_rows(rows)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
