"""Model routes and timing for the trueMotion SUTA text profile."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, Literal

from ..const import SUTA_SERVICE_UUID as SERVICE_UUID
from ..execution import ExecutionCapabilities

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic
    from bleak.backends.service import BleakGATTServiceCollection

__all__ = ["SERVICE_UUID"]

PREFIX: Final = "SUTA-"
HOLD_TICKS: Final = 400
REPEAT_MS: Final = 100
SAVE_DELAY_MS: Final = 3000
TIMERS: Final = ("00", "20", "33", "50")
LEVELS: Final = ("00", "10", "20", "30")
STOP: Final = "AT+CTRL=BOTH STOP"
VERSION: Final = "AT+GETSYSTEM=VERSION"
BEEP: Final = "AT+ENABLE=BEEP"

type Zone = Literal["HEAD", "FOOT"]


def preset(mode: str, *, save: bool = False) -> str:
    return f"AT+{'SETMODE' if save else 'MODE'}=BOTH {mode}"


def massage(zone: Zone, setting: Literal["DT", "LV"], code: str) -> str:
    return f"AT+MASS=BOTH {zone} {setting}{code}"


def light(enabled: bool) -> str:
    return f"AT+{'ENABLE' if enabled else 'DISABLE'}=LIGHT"


def lock(enabled: bool) -> str:
    return f"AT+SETLOCK={'ON' if enabled else 'OFF'}"


@dataclass(frozen=True, slots=True)
class Axis:
    key: str
    token: str
    interval_ms: int = 150

    def text(self, direction: str) -> str:
        return f"AT+CTRL=BOTH {self.token} {direction.upper()}"


@dataclass(frozen=True, slots=True)
class Profile:
    model: str
    axes: tuple[Axis, ...]
    presets: tuple[str, ...] = ()
    saves: tuple[str, ...] = ()
    massage_schedule: Literal["b202", "delayed_foot", "b603"] | None = None
    light: bool = False
    lock: bool = False
    dedicated_stop: bool = False
    split: bool = False

    @property
    def has_beep(self) -> bool:
        return any(axis.interval_ms == 150 for axis in self.axes)

    @property
    def controls(self) -> dict[str, tuple[Axis, str]]:
        return {
            f"{axis.key}_{direction}": (axis, direction)
            for axis in self.axes
            for direction in ("up", "down")
        }

    @property
    def execution(self) -> ExecutionCapabilities:
        return ExecutionCapabilities(hold="stream", hold_controls=frozenset(self.controls))


TWO = Axis("combined", "TWO")
HEAD = Axis("head", "HEAD", 100)
STANDARD_AXES = (Axis("back", "BACK"), Axis("legs", "FOOT"), TWO)
TILT = Axis("tl", "T/L", 100)
STANDARD_PRESETS = ("FLAT", "M1", "M2", "SNORE", "TV", "ZEROG")
STANDARD_SAVES = ("M1", "M2", "SNORE", "TV", "ZEROG")

PROFILES: Final = {
    "B202": Profile(
        "B202",
        STANDARD_AXES,
        STANDARD_PRESETS,
        STANDARD_SAVES,
        "b202",
        light=True,
        dedicated_stop=True,
    ),
    "B206": Profile("B206", STANDARD_AXES, STANDARD_PRESETS, STANDARD_SAVES),
    "B206A": Profile(
        "B206A",
        STANDARD_AXES,
        ("FLAT", "M1", "M8", "SNORE", "SWING", "TV", "ZEROG"),
        ("M1",),
        "delayed_foot",
        dedicated_stop=True,
    ),
    "B207": Profile(
        "B207", STANDARD_AXES, ("FLAT", "M1", "SNORE", "TV", "ZEROG"), ("M1",), lock=True
    ),
    "B301": Profile("B301", (replace(TWO, interval_ms=100),), ("FLAT", "TV")),
    "B402": Profile("B402", (replace(TWO, interval_ms=100),)),
    "B603": Profile(
        "B603",
        (*STANDARD_AXES, HEAD, TILT),
        ("FLAT", "M1", "TV", "ZEROG"),
        ("M1", "TV", "ZEROG"),
        "b603",
        dedicated_stop=True,
    ),
    "B903": Profile(
        "B903",
        (*STANDARD_AXES[:2], HEAD, replace(TILT, interval_ms=150)),
        ("FLAT", "M1", "M2", "TV", "ZEROG"),
        ("M1", "M2"),
        "delayed_foot",
        light=True,
    ),
    "M510": Profile(
        "M510",
        STANDARD_AXES,
        (*STANDARD_PRESETS, "PILATES"),
        ("M1", "M2"),
        "delayed_foot",
        dedicated_stop=True,
    ),
}

# Longer prefixes win when a name belongs to more than one family.
NAMED_ROUTES: Final = (
    ("B202", "B202"),
    ("B205", "B206"),
    ("B206B", "B206"),
    ("B206F", "B206"),
    ("B206", "B206A"),
    ("B207", "B207"),
    ("B301", "B301"),
    ("B402", "B402"),
    ("B603", "B603"),
    ("B604", "B603"),
    ("B701", "B207"),
    ("B903", "B903"),
)
DUAL_PREFIXES: Final = (
    "B205",
    "B202D",
    "B206B",
    "B206H",
    "B206G",
    "B206E",
    "B206A",
    "B206D",
    "B206C",
    "B604",
)


def name_matches(name: object) -> bool:
    return isinstance(name, str) and name.startswith(PREFIX)


def supports_pair_primary(name: object) -> bool:
    return (
        isinstance(name, str)
        and name.strip().startswith(tuple(PREFIX + suffix for suffix in DUAL_PREFIXES))
        and name_matches(name)
    )


def profile_for_name(name: str, *, split: bool = False) -> Profile:
    if split:
        # The Unicode B603 editor needs a pre-existing type-2 Android row.
        # Home Assistant's fresh pairing path only accepts ASCII SUTA names.
        model = (
            "B206"
            if name.startswith(("SUTA-B205", "SUTA-B206B"))
            else "B202"
            if name.startswith("SUTA-B202")
            else "B206A"
        )
        return replace(PROFILES[model], split=True)
    return next(
        (PROFILES[model] for prefix, model in NAMED_ROUTES if name.startswith(PREFIX + prefix)),
        PROFILES["M510"],
    )


def gatt_roles(
    services: BleakGATTServiceCollection,
) -> tuple[BleakGATTCharacteristic, BleakGATTCharacteristic] | None:
    """Choose the last writer and last Notify role in the exact service."""
    service = services.get_service(SERVICE_UUID)
    if service is None:
        return None
    tx = rx = None
    for characteristic in service.characteristics:
        properties = set(characteristic.properties)
        if properties & {"write-without-response", "write"}:
            tx = characteristic
        if "notify" in properties:
            rx = characteristic
    return (tx, rx) if tx is not None and rx is not None else None
