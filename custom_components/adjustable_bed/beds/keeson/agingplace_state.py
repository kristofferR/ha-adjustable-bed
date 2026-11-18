"""Observed Dawn House indication consumers. No synthetic current telemetry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

from ...controller_state import StateKey, StateUpdate
from ...profiles.agingplace import CYCLE_TOTALS

NUMBER_FIELDS: Final = (
    "brightness",
    "massage_minutes",
    "motion_minutes",
    "dspsen",
    "bedmd",
    "version",
    "headPlus",
    "footPlus",
    "tiltPlus",
    "lumbPlus",
    "circulation_remaining",
    "sleep_remaining",
    "relax_cycle_remaining",
    "heart_rate",
    "breathing_rate",
)
NUMBERS: Final = {name: StateKey[int | None](f"agingplace_{name}") for name in NUMBER_FIELDS}
TEXT_FIELDS: Final = (
    "di",
    "MAC",
    "dspver",
    "hardver",
    "pcbver",
    "wifiver",
    "diagnostic_status",
    "diagnostic_raw",
)
TEXT: Final = {name: StateKey[str | None](f"agingplace_{name}") for name in TEXT_FIELDS}
OCCUPIED: Final = StateKey[bool | None]("agingplace_occupancy")
CONNECTION_MASKS: Final = {
    "head": 0x30,
    "foot": 0xC0,
    "lift1": 0xC00,
    "lift2": 0x300,
    "head_massage": 0x1000,
    "foot_massage": 0x2000,
}
CONNECTED: Final = {
    name: StateKey[bool | None](f"agingplace_{name}_connected") for name in CONNECTION_MASKS
}


def integer(data: Mapping[str, object], key: str, default: int = 0) -> int:
    """Gson primitive defaults are zero; Boolean is not an integer field."""
    value = data.get(key)
    return value if type(value) is int else default


class Observations:
    """One session's observations, filtered to the configured telemetry side."""

    def __init__(self, *, mode: int | None, bed_side: int, selected_side: int) -> None:
        self.mode = mode
        self.bed_side = bed_side
        self.selected_side = selected_side
        self.maxima = dict.fromkeys(("headPlus", "footPlus", "tiltPlus", "lumbPlus"), 0)

    def consume(self, payload: Mapping[str, object]) -> list[StateUpdate]:
        updates: list[StateUpdate] = []
        data = payload.get("data")
        fields = cast("Mapping[str, object]", data) if isinstance(data, Mapping) else {}
        if isinstance(payload.get("di"), str):
            updates.append(TEXT["di"](cast(str, payload["di"])))
        if "timer" in fields and isinstance(fields.get("key"), str):
            cycle = CYCLE_TOTALS.get(cast(str, fields["key"]).lower())
            if cycle is not None:
                name, total = cycle
                updates.append(NUMBERS[f"{name}_remaining"](total - integer(fields, "timer")))
        # MAC is the source setup parser's presence gate, not a command identity.
        if isinstance(fields.get("MAC"), str) and fields["MAC"]:
            for name in ("MAC", "dspver", "hardver", "pcbver", "wifiver"):
                value = fields.get(name)
                if isinstance(value, str):
                    updates.append(TEXT[name](value))
            for name in ("dspsen", "bedmd"):
                updates.append(NUMBERS[name](integer(fields, name)))
            if self.mode is None:
                self.mode = 0 if integer(fields, "dspsen") <= 2 else 1
        if type(fields.get("ver")) is int:
            # Java integer division truncates toward zero.
            version = integer(fields, "ver")
            updates.append(NUMBERS["version"]((abs(version) // 100) * (-1 if version < 0 else 1)))
        if any(name in fields for name in ("bm", "br", "hr", "lb", "si", "sn")):
            # Two-sensor beds (mode 1) report each side; keep only the configured
            # side. Single-sensor and single-display modes show every reading.
            mode = self.mode if self.mode is not None else 0
            side = self.selected_side if self.bed_side == 2 else self.bed_side
            if mode != 1 or integer(fields, "si") == side:
                occupied = integer(fields, "lb") == 0
                updates.extend(
                    (
                        OCCUPIED(occupied),
                        NUMBERS["heart_rate"](integer(fields, "hr") if occupied else None),
                        NUMBERS["breathing_rate"](integer(fields, "br") if occupied else None),
                    )
                )
        if "chkStatu" in payload:
            flag = integer(payload, "chkStatu")
            for name, mask in CONNECTION_MASKS.items():
                updates.append(CONNECTED[name]((flag & mask) == 0))
            for name in self.maxima:
                self.maxima[name] = max(self.maxima[name], integer(payload, name))
                updates.append(NUMBERS[name](self.maxima[name]))
            updates.append(
                TEXT["diagnostic_status"](
                    "complete" if flag >= 49152 else "running" if flag >= 1 else "idle"
                )
            )
        return updates
