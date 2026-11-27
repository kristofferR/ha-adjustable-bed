"""Ronco Motion 1.2 (com.richmat.ronco_motion), accepted row175 evidence.

The two user-selected layouts are independent of name and transport. No
checked-in generator: this small table is transcribed from the accepted audit.
"""

from dataclasses import dataclass
from typing import Final

from ..codec import richmat as codec
from ..execution import STREAM_HOLD, ExecutionCapabilities


@dataclass(frozen=True)
class RoncoMotionProfile:
    key: str
    label: str
    motors: tuple[str, ...]
    light: bool
    refresh_ms: int = 100
    short_ms: int = 100
    alarm_ms: int = 120
    startup_ms: int = 300
    execution: ExecutionCapabilities = STREAM_HOLD


PROFILES: Final = {
    "economy": RoncoMotionProfile("economy", "ECONOMY (Fk9rm)", ("head", "legs"), False),
    "premium": RoncoMotionProfile("premium", "PREMIUM (Fk8rm)", ("head", "legs", "pillow"), True),
}
CHOICES: Final = {key: profile.label for key, profile in PROFILES.items()}
MOTORS: Final = {"head": (0x24, 0x25), "legs": (0x26, 0x27), "pillow": (0x3F, 0x40)}
SHORT: Final = {
    "flat": 0x31,
    "light_toggle": 0x3C,
    "zero_g": 0x45,
    "save_zero_g": 0x66,
    "anti_snore": 0x46,
    "save_anti_snore": 0x69,
    "memory": 0x2E,
    "save_memory": 0x2B,
}
END: Final = codec.command(0x6E)
STARTUP: Final = tuple(codec.frame(0x6E, *fields) for fields in ((8, 1, 1), (10, 0, 1), (21, 1, 1)))
# These are five-byte 6E frames even on the Nordic UUIDs, never bare keys.
TRANSPORTS: Final = (
    codec.Transport(
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
    ),
    codec.TRANSPORTS["w1"],
    codec.TRANSPORTS["w2"],
    codec.TRANSPORTS["w3"],
    codec.TRANSPORTS["w4"],
)
PREFIXES: Final = frozenset(
    [
        "qrrm",
        "farm",
        "jgrm",
        "jhrm",
        "jjrm",
        "jvrm",
        "k8rm",
        "k9rm",
        "kzrm",
        "l2rm",
        "v1rm",
        "vjrm",
        "d3rm",
        "djrm",
        "dkrm",
        "dlrm",
        "hfrm",
        "hgrm",
        "hhrm",
        "hjrm",
        "jarm",
        "karm",
        "kor2",
        "korm",
        "wlm3",
        "wlrm",
        "wlrs",
        "y6rm",
    ]
)


def accepts_name(name: str) -> bool:
    return len(name) > 4 and name[:4].lower() in PREFIXES
