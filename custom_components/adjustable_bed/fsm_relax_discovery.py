"""FSM Relax's candidate predicate, never an automatic app/profile selector."""
from __future__ import annotations


def matches_fsm_relax_candidate(name: str | None, raw_scan_record: bytes | None = None) -> bool:
    """Match exact case-sensitive source behavior when a raw record is available.

    HA's advertisement object does not retain Android's complete raw scan record.
    Do not synthesize that record from manufacturer/service fields. The name route
    remains available; explicit manual profile selection handles other devices.
    """
    if name is None:
        return False
    return (raw_scan_record is not None and raw_scan_record.decode("utf-8", errors="replace").find("limoss") > 0) or "limoss" in name
