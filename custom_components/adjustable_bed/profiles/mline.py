"""M Line com.okin.mline 1.2.2 (38).

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
