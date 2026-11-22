"""Instant Comfort 2.6.1's independently chosen air and base routes."""

from dataclasses import dataclass
from typing import Final

from ..codec import personal_comfort as codec
from ..execution import NO_EXECUTION_CAPABILITIES, STREAM_HOLD, ExecutionCapabilities
from .personal_comfort import PersonalComfortProfile


@dataclass(frozen=True, kw_only=True)
class InstantComfortProfile(PersonalComfortProfile):
    """The Instant Comfort app's route, separate from Personal Comfort settings."""


MODELS: Final = {
    key.lower(): key for key in ("PF2", "PF3", "PF4", "PF42", "PFE", "PFD", "PFB", "PFA", "Other")
}
ROUTES: Final = {
    "anm3": "Air unit ANM V3",
    "anm5": "Air unit ANM V5",
    "ra": "Air unit RA",
    "malouf": "Malouf base",
    "reverie_v1": "Reverie base",
    "reverie_v2": "Reverie base V2",
}
MALOUF: Final = InstantComfortProfile(
    key="malouf",
    service=codec.bluetooth_uuid("fee9"),
    write="d44bc439-abfd-45a2-b575-925416129600",
    transports=("w1",),
    execution=STREAM_HOLD,
    stop=None,
    motor_repeat_ms=200,
    codes={
        "head_up": 0x24,
        "head_down": 0x25,
        "feet_up": 0x26,
        "feet_down": 0x27,
        "pillow_up": 0x3F,
        "pillow_down": 0x40,
        "flat": 0x31,
        "zero_g": 0x45,
        "anti_snore": 0x46,
        "light_toggle": 0x3C,
        "massage_head": 0x4C,
        "massage_head_down": 0x4D,
        "massage_foot": 0x4E,
        "massage_foot_down": 0x4F,
        "massage_mode": 0x48,
        "massage_off": 0x47,
    },
    memory=((0x2E, 0x2B), (0x2F, 0x2C)),
)
PROFILES: Final = {"malouf": MALOUF}
for _key, _service, _write, _notify, _notify_service in (
    (
        "anm3",
        codec.bluetooth_uuid("ffe5"),
        codec.bluetooth_uuid("ffe9"),
        codec.bluetooth_uuid("ffe4"),
        codec.bluetooth_uuid("ffe0"),
    ),
    (
        "anm5",
        codec.bluetooth_uuid("ffe0"),
        codec.bluetooth_uuid("ffe1"),
        codec.bluetooth_uuid("ffe2"),
        codec.bluetooth_uuid("ffe0"),
    ),
    ("ra", codec.RA_SERVICE, codec.RA_WRITE["left"], codec.RA_NOTIFY, codec.RA_SERVICE),
    ("reverie_v1", codec.V1_SERVICE, codec.V1_WRITE, None, None),
    ("reverie_v2", codec.reverie_uuid("db801000"), codec.reverie_uuid("db8010d0"), None, None),
):
    PROFILES[_key] = InstantComfortProfile(
        key=_key,
        service=_service,
        write=_write,
        notify=_notify,
        notify_service=_notify_service,
        transports=(),
        stop=None,
        execution=ExecutionCapabilities(hold="latched")
        if _key.startswith("reverie")
        else NO_EXECUTION_CAPABILITIES,
    )
