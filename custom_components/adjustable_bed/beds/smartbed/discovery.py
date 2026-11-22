"""Ordered SmartBed selectors, using raw scan offsets only when actually available."""

from dataclasses import dataclass

from ...profiles.smartbed import PROFILES, signed


@dataclass(frozen=True, slots=True)
class Selection:
    profile: str
    motors: int = 2
    massage: bool = True
    light: bool = True
    massage_count: int = 2


def _digit(value: int) -> int:
    text = str(value)
    return int(text[0]) if text[0].isdigit() else 2


def discover(name: str | None, raw: bytes = b"") -> Selection | None:
    """Factory order; unsafe source lengths are rejected before reading any fields.

    HA's manufacturer-data dictionary is not a raw scan record. Never invent
    missing AD structures or treat an arbitrary company payload as raw offsets.
    """
    if not name or name == "UnNamed":
        return None
    if len(raw) >= 27 and raw[9:11] == b"OK":
        identifier = raw[11:27].decode("ascii", errors="replace")
        try:
            motors = int(identifier[1])
            massage = identifier[4:6] != "00"
        except ValueError:
            motors, massage = 2, True
        return Selection("standard", motors, massage)
    if len(raw) >= 12 and raw[7:10] == b"DOT":
        if raw[10] == 1:
            return Selection("dacheng", _digit(signed(raw[11])))
        if raw[11] != 1:
            return Selection("cb24", _digit(signed(raw[11])))
    if len(raw) >= 10 and raw[7:9] == b"OK":
        return Selection("cb27", _digit(raw[9] & 15))
    if len(raw) >= 12 and raw[7:9] == b"AB":
        count = raw[10] & 15
        return Selection("cb24_ab", _digit(raw[11] & 15), bool(count), bool(raw[9] & 15), count)
    if len(raw) >= 12 and raw[7:10] == b"DOT" and raw[10] != 1 and raw[11] == 1:
        return Selection("cb1221", 2, raw[10] != 3)
    if name.lower().startswith("smartbed") and len(name) == 18:
        return Selection("cb27new")
    if name.startswith("Headboard126"):
        return Selection("headboard126", massage=False, light=False)
    if name.startswith("Headboard265"):
        return Selection("headboard265", light=False)
    return Selection("cb", 0)


def select_profile(
    variant: str, name: str | None, *, motors: int = 2, raw: bytes = b""
) -> Selection:
    key = variant
    if key in PROFILES:
        return Selection(
            key,
            2 if key.startswith("headboard") or key == "cb1221" else motors,
            key != "headboard126",
            not key.startswith("headboard"),
        )
    # Raw scan records are normally unavailable in HA. For ambiguous old
    # receivers, retain the established CB24 route until the user chooses one.
    detected = discover(name, raw)
    if detected is not None and detected.profile != "cb":
        return detected
    return Selection("cb24", motors)
