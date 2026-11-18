"""Dawn House / Aging in Place 1.1.0 (87), one direct JSON BED profile."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from ..codec import keeson as codec
from ..execution import STREAM_HOLD
from .keeson import KeesonProfile, Release

REFRESH_MS: Final = 200
CHUNK_BYTES: Final = 260
REQUESTED_MTU: Final = 260
CONNECT_WAIT: Final = 0.3
INDICATION_WAIT: Final = 0.1
SELF_CHECK_TIMEOUT: Final = 20.0
DIAGNOSTIC_QUIET: Final = 2.0
CONFIG_KEYS: Final = frozenset(
    {"agingplace_bed_mode", "agingplace_bed_side", "agingplace_selected_side"}
)
NAMES: Final = ("KSWF07S", "KSWF19S")


@dataclass(frozen=True, slots=True)
class Action:
    label: str
    word: int
    held: bool = False
    ctrm: int = 1
    km: int = 1
    keykt: int = 0
    code: int = 2

    def frame(self, device_id: str | None) -> bytes:
        fields: dict[str, int | str] = {"key": f"{self.word:08x}", "km": self.km}
        if self.km != 2:
            fields.update(ctrm=self.ctrm, keykt=self.keykt)
        return codec.json_packet(self.code, fields, device_id)


ACTIONS: Final = MappingProxyType(
    {
        "light": Action("Underbed light", 0x20000),
        "massage": Action("Massage cycle", 0x100),
        "zero_g": Action("Zero gravity", 0x1000),
        "anti_snore": Action("Anti snore", 0x8000),
        "read": Action("Read", 0x8000),
        "flat": Action("Flat", 0x8000000),
        "head_up": Action("Head up", 0x01, True, 0, 5, 1),
        "head_down": Action("Head down", 0x02, True, 0, 5, 1),
        "foot_up": Action("Foot up", 0x04, True, 0, 5, 1),
        "foot_down": Action("Foot down", 0x08, True, 0, 5, 1),
        "bed_up": Action("Bed height up", 0x50, True, 0, 5, 1),
        "bed_down": Action("Bed height down", 0xA0, True, 0, 5, 1),
        "in": Action("In", 0x40000000, True, 1, 6, 0),
        "out": Action("Out", 0x80000000, True, 1, 6, 0),
        "release": Action("Release held control", 0, ctrm=0),
        "circulation": Action("Circulation cycle", 0x20000000, km=2),
        "sleep": Action("Sleep cycle", 0x10000000, km=2),
        "relax_cycle": Action("Relax cycle", 0x08020000, km=2),
        "diagnostic": Action("Self check", 0x00400000, km=2, code=4),
    }
)
CYCLE_TOTALS: Final = MappingProxyType(
    {
        "20000000": ("circulation", 5400),
        "10000000": ("sleep", 930),
        "08020000": ("relax_cycle", 600),
    }
)
PROFILE: Final = KeesonProfile(
    key="agingplace",
    carrier="json",
    transport="json",
    notify="json",
    fixed_write=True,
    execution=STREAM_HOLD,
    hold=(5, REFRESH_MS),
    refresh_ms=REFRESH_MS,
    release=Release(guarded=True),
    presets={"flat": 0x8000000, "zero_g": 0x1000, "anti_snore": 0x8000},
    lights="toggle",
    massage="none",
    tilt=False,
    lumbar=False,
    keeson_motor_names=False,
)


def setting(name: str, value: int, device_id: str | None) -> bytes:
    """Retain typed zero defaults and the source's massagT spelling."""
    if type(value) is not int:
        raise ValueError("Setting must be an integer")
    fields: dict[str, int | str] = {"bright": 0, "dummy": 0, "key": "00000000"}
    if name == "brightness" and 0 <= value <= 100:
        fields.update(B=0, G=0, R=0, bright=255 - int(value * 2.5), cmd=187)
        code = 10
    elif name in ("massage_minutes", "motion_minutes") and 1 <= value <= (
        60 if name == "massage_minutes" else 30
    ):
        code = 8 if name == "massage_minutes" else 9
        fields.update(cmd=16 if code == 8 else 17, massagT=60 * value)
    else:
        raise ValueError("Unsupported Dawn House setting or value")
    return codec.json_packet(code, fields, device_id)


def device_info(device_id: str | None) -> bytes:
    return codec.json_packet(4, {"sw": 1}, device_id)


def selected_device_id(stored: object, advertised: str | None) -> str | None:
    """The selected local identity wins; never substitute a MAC or title."""
    if isinstance(stored, str) and stored:
        return stored
    return advertised or None
