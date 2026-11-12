"""M Line com.okin.mline 1.2.2 (38), accepted standalone row147.

No hardware models or single-address side routing are inferred from these enums.
"""

from dataclasses import dataclass
from typing import Final

from ..codec.mline import PROTOCOLS, Protocol
from ..const import CONF_MLINE_CHILD_MODE
from ..execution import STREAM_HOLD, ExecutionCapabilities

LAYOUTS: Final = {
    "two": ("back", "legs", "both"),
    "triple": ("back", "legs", "head"),
    "four": ("back", "legs", "head", "lumbar"),
}
LAYOUT_LABELS: Final = {
    "two": "Head, foot and combined",
    "triple": "Head, foot and neck",
    "four": "Head, foot, neck and lumbar",
}
MOTORS: Final = {
    "back": ("headUp", "headDown"),
    "legs": ("footUp", "footDown"),
    "head": ("machinery3Up", "machinery3Down"),
    "lumbar": ("machinery4Up", "machinery4Down"),
    "both": ("hfUp", "hfDown"),
}
PRESETS: Final = {
    "flat": "flatPosition",
    "zero_g": "zeroGravity",
    "anti_snore": "antiSnore",
    "memory_1": "memory5_M1",
    "memory_2": "memory6_M2",
}
MASSAGE: Final = {
    "start": "massageAll",
    "wave": "waveAdd",
    "intensity": "meanwhileStrengthAdd",
    "timer": "timerSwitch",
}
CHILD_MODE: Final = CONF_MLINE_CHILD_MODE


@dataclass(frozen=True)
class MLineProfile:
    key: Protocol
    refresh_ms: int = 200
    execution: ExecutionCapabilities = STREAM_HOLD

    @property
    def release_ms(self) -> int:
        return 300 if self.key == "okin" else 100

    @property
    def status_retry_ms(self) -> int | None:
        return None if self.key == "okin" else 1000 if self.key == "smartsainuo" else 300


PROFILES: Final = {key: MLineProfile(key) for key in PROTOCOLS}


def resolve_protocol(
    name: str, manufacturer: dict[int, bytes], cached: Protocol = "unknown"
) -> Protocol:
    if cached != "unknown":
        return cached
    upper = name.upper()
    result: Protocol = "sleep" if not name or "SLEEP" in upper else "unknown"
    if "SMART" in upper:
        result = "smart"
        data = manufacturer.get(89, b"")
        if len(data) == 5 and data[-1] == 5:
            result = "smartsainuo"
    return "okin" if "OKIN" in upper else result


def admitted_name(name: str) -> bool:
    return bool(name) and any(word in name.upper() for word in ("SLEEP", "SMARTBED", "OKIN"))


def scan_first(
    batch: tuple[tuple[str, str], ...], seen: set[str], requested_name: str | None = None
) -> tuple[str, str] | None:
    """Source FIRST-batch rule and ID dedup, independent of protocol selection."""
    if not batch:
        return None
    device_id, name = batch[0]
    if not admitted_name(name) or device_id in seen:
        return None
    seen.add(device_id)
    return (device_id, name) if requested_name is None or name == requested_name else None


def imported_layout(type_tag: int) -> str:
    return {2: "two", 3: "triple", 4: "four"}.get(type_tag % 10, "four")


def persisted_type(protocol: Protocol, layout: str) -> int:
    return {"sleep": 2, "smart": 3, "smartsainuo": 5, "okin": 4}.get(protocol, 2) * 10 + {
        "two": 2,
        "triple": 3,
    }.get(layout, 4)
