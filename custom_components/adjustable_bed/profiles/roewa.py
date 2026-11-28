"""RÖWA Fernbedienung 1.1.0: three explicit remotes over Okin N-frames."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from ..codec import okin_nframe as codec
from ..execution import ExecutionCapabilities
from .okin_nframe import Hold, OkinNFrameProfile

SERVICE_UUID: Final = "62741523-52f9-8864-b1ab-3b3a8d65950b"
WRITE_UUID: Final = "62741525-52f9-8864-b1ab-3b3a8d65950b"
FEEDBACK_UUID: Final = "62741625-52f9-8864-b1ab-3b3a8d65950b"
NAME_SERVICE_UUID: Final = "90311623-25fa-3346-12ef-3cfb7a2556ac"
NAME_UUID: Final = "90311625-25fa-3346-12ef-3cfb7a2556ac"
INFO_SERVICE_UUID: Final = "0000180a-0000-1000-8000-00805f9b34fb"
MODEL_UUID: Final = "00002a24-0000-1000-8000-00805f9b34fb"
FIRMWARE_UUID: Final = "00002a26-0000-1000-8000-00805f9b34fb"
SCAN_SERVICES: Final = (SERVICE_UUID, NAME_SERVICE_UUID, INFO_SERVICE_UUID)
rename_frame: Final = codec.device_name_record
INITIALIZE: Final = codec.parameter_record(4, (), size=1)
REFRESH_MS: Final = 80
LATCH_MS: Final = 250
LAYOUTS: Final = {
    "remote2Drive": "Two motors: back and legs",
    "remote3Drive": "Three motors: back, legs and feet",
    "remote4Drive": "Four motors: head, back, legs and feet",
}
DEFAULT_LAYOUT: Final = "remote2Drive"
MOTORS: Final = {
    "head": (1, 2),
    "back": (4, 8),
    "legs": (16, 32),
    "feet": (64, 128),
}
COMMON: Final = {
    "flat": 0xAA,
    "light_toggle": 0x20000,
    "memory_store": 0x10000,
    **{f"memory_{slot}": 0x800 << slot for slot in range(1, 5)},
}


@dataclass(frozen=True, kw_only=True)
class RoewaProfile(OkinNFrameProfile):
    refresh_ms: int = REFRESH_MS
    latch_ms: int = LATCH_MS


def _profile(layout: str, axes: tuple[str, ...]) -> RoewaProfile:
    keys = {
        **COMMON,
        **{
            f"{axis}_{direction}": word
            for axis in axes
            for direction, word in zip(("up", "down"), MOTORS[axis], strict=True)
        },
    }
    held = frozenset(keys) - {"light_toggle", "memory_store"}
    return RoewaProfile(
        key=layout,
        name=LAYOUTS[layout],
        bed_types=("roewa",),
        axes=axes,
        keys=MappingProxyType(keys),
        width=4,
        write="response",
        envelope="plain",
        hold=Hold(repeat_ms=REFRESH_MS, releases=0),
        memory_slots=4,
        execution=ExecutionCapabilities(hold="stream", hold_controls=held),
    )


PROFILES: Final = {
    "remote2Drive": _profile("remote2Drive", ("back", "legs")),
    "remote3Drive": _profile("remote3Drive", ("back", "legs", "feet")),
    "remote4Drive": _profile("remote4Drive", ("head", "back", "legs", "feet")),
}
