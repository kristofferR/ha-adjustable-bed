"""Personal Comfort 2.6.1's six routes and explicit base-model gates."""

from dataclasses import dataclass
from typing import Final

from ..codec import personal_comfort as codec
from ..execution import NO_EXECUTION_CAPABILITIES, STREAM_HOLD, ExecutionCapabilities
from .richmat import RichmatProfile


@dataclass(frozen=True, kw_only=True)
class PersonalComfortProfile(RichmatProfile):
    service: str
    write: str
    notify: str | None = None
    notify_service: str | None = None


MODELS: Final = {
    key.lower(): label
    for key, label in (
        ("PF2", "PF2"),
        ("PF3", "PF3"),
        ("PF4", "PF4"),
        ("PF42", "PF42"),
        ("PFE", "PFE"),
        ("PFD", "PFD"),
        ("PFB", "PFB"),
        ("PFA", "PFA"),
        ("Other", "Other"),
        ("None", "None"),
    )
}
ROUTES: Final = {
    "anm3": "Air unit ANM V3",
    "anm5": "Air unit ANM V5",
    "ra": "Air unit RA",
    "malouf": "Malouf base",
    "reverie_v1": "Reverie base",
    "reverie_v2": "Reverie base V2",
}
MALOUF: Final = PersonalComfortProfile(
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
    PROFILES[_key] = PersonalComfortProfile(
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


def air_route(name: str, services: set[str]) -> str | None:
    if codec.RA_SERVICE in services:
        return "ra"
    if codec.bluetooth_uuid("ffe0") in services or "ffe0" in services:
        return "anm5" if name.startswith(("2618", "2816")) else "anm3"
    broad = {
        codec.bluetooth_uuid(x)
        for x in (
            "ffe5",
            "fff0",
            "fe00",
            "ff90",
            "ffa0",
            "ffb0",
            "ffc0",
            "fc60",
            "ffd0",
            "180a",
            "180f",
        )
    }
    return "anm3" if name.startswith("ANM-") and services & broad else None
