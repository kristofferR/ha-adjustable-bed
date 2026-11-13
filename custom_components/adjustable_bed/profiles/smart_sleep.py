"""OKIN Smart Sleep 2.4.9 (263), accepted row094. No inferred model anatomy.

Catalogs transcribed from the accepted report, without a generator. Models 3
and 67 deliberately retain distinct identity; P2 scan selection forces 80.
"""

from dataclasses import dataclass
from typing import Final

from ..codec import smart_sleep as codec
from ..execution import STREAM_HOLD, ExecutionCapabilities

MODELS: Final = {
    0: "unKnow",
    2: "sleep single",
    3: "sleep double",
    4: "sleep meise",
    5: "sleep dormimundo",
    6: "sleep singleOnlySound",
    7: "sleep noHX",
    8: "sleep aizero",
    11: "sleep wifi",
    67: "sleep double",
    80: "sleep 3 single",
}
AXES: Final = {
    "back": (1, "smart_sleep_head"),
    "legs": (2, "smart_sleep_foot"),
    "head": (3, "smart_sleep_headrest"),
    "lumbar": (4, "smart_sleep_lumbar"),
    "hips": (5, "smart_sleep_hips"),
}
ALARM_ACTIONS: Final = {
    "initial": 1,
    "lounge": 2,
    "tv": 3,
    "anti_snore": 4,
    "memory_1": 5,
    "memory_2": 6,
    "light": 7,
    "massage": 8,
    "flat": 9,
}
# These are the actual visible-label ordinals, including the app's mismatch.
APP_ALARM_LABELS: Final = {
    "app_zero_g": 0,
    "app_flat": 1,
    "app_memory_1": 2,
    "app_memory_2": 3,
    "app_vibration": 4,
}
LEGACY_ALARM_ACTIONS: Final = {"zero_g": 1, "flat": 9, "memory_1": 5, "memory_2": 6, "massage": 8}


@dataclass(frozen=True, slots=True)
class SmartSleepProfile:
    key: codec.Format
    refresh_ms: int = 100
    massage_ms: int = 300
    query_ms: int = 300
    save_ms: int = 5500
    execution: ExecutionCapabilities = STREAM_HOLD

    @property
    def release_ms(self) -> int:
        return 100 if self.key == "p1" else 0

    @property
    def frames(self) -> dict[str, bytes]:
        frames = {
            f"{axis}_{direction}": codec.motion(self.key, index, direction == "up")
            for axis, (index, _) in AXES.items()
            for direction in ("up", "down")
        }
        frames.update(
            {
                "stop": codec.stop(self.key),
                "release": codec.stop(self.key, motor=True),
                "query_alarm": codec.query(self.key, "alarm"),
                "query_settings": codec.query(self.key, "settings"),
                "query_massage": codec.query(self.key, "massage"),
            }
        )
        frames.update({name: codec.preset(self.key, name) for name in codec.PRESETS})
        if self.key == "p2":
            frames["initialize"] = codec.INITIALIZE
            frames.update(
                {
                    f"save_{name}": codec.preset(self.key, name, save=True)
                    for name in codec.PRESETS
                    if name != "flat"
                }
            )
        return frames


_P2_HELD: Final = frozenset(
    {
        *(f"{axis}_{direction}" for axis in AXES for direction in ("up", "down")),
        *(
            f"massage_{name}"
            for name in ("all", "off", "wave", "timer", "head_strength", "foot_strength")
        ),
    }
)
PROFILES: Final = {
    "p1": SmartSleepProfile("p1"),
    "p2": SmartSleepProfile(
        "p2", execution=ExecutionCapabilities(hold="stream", hold_controls=_P2_HELD)
    ),
}


@dataclass(frozen=True, slots=True)
class Advertisement:
    identifier: str
    format: codec.Format
    model: int


def advertisement(name: str, manufacturer: dict[int, bytes], address: str) -> Advertisement | None:
    if not ("SLEEP" in name or "Sleep" in name) or 89 not in manufacturer:
        return None
    data = manufacturer[89]
    identifier = (
        bytes(reversed(data))[1:7].hex() if len(data) >= 7 else address.lower().replace(":", "")
    )
    new = len(data) >= 7 and bool(data[6] & 128)
    model = 80 if new else data[6] + 1 if len(data) >= 7 else -1
    return Advertisement(identifier, "p2" if new else "p1", model if model in MODELS else 0)
