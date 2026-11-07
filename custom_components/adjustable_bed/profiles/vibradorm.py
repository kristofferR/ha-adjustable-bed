"""Profiles over the Vibradorm VMAT codec: the generic route and the app layouts.

- ``LEGACY`` (``legacy``) is the generic ``vibradorm`` route, from the VIBRADORM
  Remote (``de.vibradorm.vra``) and V-MAT Basic apps as the pre-v5 controller
  sent them.
- ``VibradormAppProfile`` serves the ``vibradorm_app`` bed type: one validated
  layout of the Caresse Remote or Werkmeister app (accepted row031 report) or of
  the VMAT 1.11 (49) app, keyed by app.

V-MAT Basic has its own profile module, ``profiles/vmatbasic.py``. Each app keeps
its own command table and timing; none reuses a sibling's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar, Final, Literal

from ..codec import vibradorm as codec
from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

# ---------------------------------------------------------------------------
# Generic route (``vibradorm`` bed type)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class VibradormProfile:
    """The generic route's motor bytes, command words and timing.

    ``back`` is the Kopf motor (head on two-motor beds), ``head`` the Nacken motor
    and ``feet`` the Fuß motor of three- and four-motor beds.
    """

    execution: ClassVar[ExecutionCapabilities] = NO_EXECUTION_CAPABILITIES
    """Finite pulses and serialized motors."""
    key: str
    back_up: int
    back_down: int
    legs_up: int
    legs_down: int
    head_up: int
    head_down: int
    feet_up: int
    feet_down: int
    flat: int
    memory: Mapping[int, int]
    """Slot -> recall byte, also the command word that saves it."""
    store: int
    vibration: int
    status_request: tuple[int, bytes]
    """The command word and parameters that ask for a motor status reply."""
    light_on: int
    preset_repeats: int
    preset_delay_ms: int
    store_repeats: int
    release_repeats: int


LEGACY: Final = VibradormProfile(
    key="legacy",
    back_up=0x0B,
    back_down=0x0A,
    legs_up=0x09,
    legs_down=0x08,
    head_up=0x03,
    head_down=0x02,
    feet_up=0x05,
    feet_down=0x04,
    flat=0x00,
    memory={1: 0x0E, 2: 0x0F, 3: 0x0C, 4: 0x1A, 5: 0x1B, 6: 0x1C},
    store=0x0D,
    vibration=0x34,
    status_request=(0x3D, b"\x3f"),
    light_on=0xFF,
    preset_repeats=200,
    preset_delay_ms=100,
    store_repeats=4,
    release_repeats=4,
)

# ---------------------------------------------------------------------------
# App layouts (``vibradorm_app`` bed type)
# ---------------------------------------------------------------------------

ControlType = int | Literal["other"]
MOTORS: Final = {
    "head_up": 3,
    "head_down": 2,
    "back_up": 11,
    "back_down": 10,
    "legs_up": 9,
    "legs_down": 8,
    "feet_up": 5,
    "feet_down": 4,
    "all_up": 16,
    "all_down": 0,
}
MEMORY: Final = (14, 15, 12, 26, 27, 28)
STORE: Final = 0x0D
SYNC_REQUEST: Final = (0x3D, b"\x3f")
SYNC_ACTIVE: Final = 0x19
SYNC_INACTIVE: Final = 0x18
FLOOR: Final = 0x11
MOOD: Final = 0x77
MASSAGE: Final = 0x30
MASSAGE_OFF: Final = 0x34
EXTENSION: Final = 0x1000
"""Set on the mood and massage words of CBI layouts and on every mood toggle."""
MOOD_EFFECTS: Final = ("sunrise", "rainbow", "disco")
MASSAGE_WAVES: Final = ("1", "2", "3", "4")
# The shipped fixed-100 HSV conversion has truncation, so retain its outputs.
MOOD_PALETTE: Final = {
    "#008a00": (0, 138, 0),
    "#00aba9": (0, 171, 169),
    "#1ba1e2": (26, 161, 226),
    "#0050ef": (0, 80, 239),
    "#6a00ff": (106, 0, 255),
    "#aa00ff": (170, 0, 255),
    "#f472d0": (244, 114, 208),
    "#d80073": (216, 0, 115),
    "#a20025": (162, 0, 36),
    "#e51400": (229, 19, 0),
    "#fa6800": (250, 104, 0),
    "#f0a30a": (240, 163, 9),
    "#e3c800": (227, 200, 0),
    "#825a2c": (130, 90, 44),
    "#6d8764": (109, 135, 100),
    "#647687": (100, 118, 135),
    "#76708a": (118, 112, 138),
    "#ffffff": (255, 255, 255),
}
ARTICLE_REQUEST: Final = codec.command(0x01A0, b"\xc8")
"""Caresse and Werkmeister ask for the main firmware article three times."""

VMAT_METADATA_FIELDS: Final = (
    "xmc_status",
    "opmode",
    "device_name",
    "revision_id",
    "revision_string",
    "variant",
)
# Field, request, reply prefix and reply timeout (s) of each VMAT onboarding stage.
VMAT_QUERY_STAGES: Final = (
    ("xmc_status", codec.command(0x01B3, b"\x4c\x01"), bytes.fromhex("21b3"), 2.0),
    ("opmode", codec.command(0x01B3, b"\xf4\x01"), bytes.fromhex("21b3"), 1.0),
    ("main_firmware_article", ARTICLE_REQUEST, bytes.fromhex("21a0c8"), 1.0),
    ("device_name", codec.command(0x01A0, b"\xc9"), bytes.fromhex("21a0c9"), 1.0),
    ("revision_id", codec.command(0x01A0, b"\xca\x00"), bytes.fromhex("21a0ca"), 1.0),
    ("revision_string", codec.command(0x01A0, b"\xca"), bytes.fromhex("21a0ca"), 1.0),
    ("variant", codec.command(0x01A0, b"\xcc"), bytes.fromhex("21a0cc"), 1.0),
)
VMAT_CLOSE: Final = codec.command(0x01A7)


@dataclass(frozen=True, slots=True)
class VmatRemote:
    asset: str
    control_type: int
    floor_light: bool = False
    rgb: bool = False
    massage: bool = False
    light_extension: bool = False

    @property
    def groups(self) -> tuple[str, ...]:
        if self.control_type in (2, 8):
            return ("back", "legs")
        if self.control_type == 9:
            return ("head", "back", "legs")
        return ("head", "back", "legs", "feet")


VMAT_REMOTES: Final = {
    "00": VmatRemote("sender_010", 2),
    "01": VmatRemote("sender_020", 2, floor_light=True),
    "02": VmatRemote("sender_180", 2),
    "03": VmatRemote("sender_190", 2),
    "04": VmatRemote("sender_200", 2, floor_light=True),
    "05": VmatRemote("sender_210", 2, floor_light=True),
    "06": VmatRemote("sender_220", 2, floor_light=True),
    "07": VmatRemote("sender_230", 8, floor_light=True),
    "08": VmatRemote("sender_240", 8, floor_light=True),
    "09": VmatRemote("sender_250", 8, floor_light=True),
    "10": VmatRemote("sender_260", 8, floor_light=True),
    "11": VmatRemote("sender_270", 9),
    "12": VmatRemote("sender_090", 2, rgb=True, massage=True, light_extension=True),
    "13": VmatRemote("sender_100", 1, rgb=True, massage=True, light_extension=True),
}

# VMAT's shipped floating-point conversion has its own truncation results.
VMAT_MOOD_PALETTE: Final = {
    "#008a00": (0, 138, 0),
    "#00aba9": (0, 170, 168),
    "#1ba1e2": (26, 161, 226),
    "#0050ef": (0, 80, 238),
    "#6a00ff": (106, 0, 255),
    "#aa00ff": (170, 0, 255),
    "#f472d0": (244, 114, 208),
    "#d80073": (216, 0, 115),
    "#a20025": (162, 0, 36),
    "#e51400": (229, 19, 0),
    "#fa6800": (250, 104, 0),
    "#f0a30a": (239, 162, 9),
    "#e3c800": (227, 200, 0),
    "#825a2c": (130, 90, 44),
    "#6d8764": (109, 135, 100),
    "#647687": (100, 118, 135),
    "#76708a": (118, 112, 138),
    "#ffffff": (255, 255, 255),
}


def get_vmat_remote(remote: str | None) -> VmatRemote:
    """Require the exact ordinal, never guess a product from its asset name."""
    if not isinstance(remote, str) or remote not in VMAT_REMOTES:
        raise ValueError("Select one of the fourteen shipped VMAT remotes")
    return VMAT_REMOTES[remote]


@dataclass(frozen=True, slots=True)
class VibradormAppProfile:
    execution: ClassVar[ExecutionCapabilities] = NO_EXECUTION_CAPABILITIES
    """The controller declares its own (#483)."""
    app_profile: str
    control_type: ControlType
    restored: bool
    floor_light: bool
    rgb: bool
    massage: bool
    light_extension: bool
    groups: tuple[str, ...]
    basic: bool
    memory_slots: int
    remote: str | None = None

    @property
    def key(self) -> str:
        return self.app_profile

    @property
    def article_requests(self) -> bool:
        return self.control_type in (5, 6, 7)

    @property
    def sync(self) -> bool:
        return (
            self.app_profile == "werkmeister"
            and self.control_type == 7
            or self.app_profile == "vmat"
            and self.control_type in (8, 9)
        )


def validate_vibradorm_app_profile(
    app_profile: str,
    control_type: ControlType,
    *,
    restored: bool = False,
    floor_light: bool | None = None,
    rgb: bool = False,
    massage: bool = False,
    light_extension: bool = False,
    remote: str | None = None,
) -> VibradormAppProfile:
    """Validate an explicit app layout without consulting BLE or generic options."""
    if app_profile == "vmat":
        selected = get_vmat_remote(remote)
        if (
            isinstance(control_type, bool)
            or control_type != selected.control_type
            or restored is not False
            or floor_light is not selected.floor_light
            or rgb is not selected.rgb
            or massage is not selected.massage
            or light_extension is not selected.light_extension
        ):
            raise ValueError("VMAT flags and controls must match the selected remote")
        return VibradormAppProfile(
            app_profile,
            selected.control_type,
            False,
            selected.floor_light,
            selected.rgb,
            selected.massage,
            selected.light_extension,
            selected.groups,
            selected.control_type == 2,
            0 if selected.control_type == 2 else 6,
            remote,
        )
    if remote is not None:
        raise ValueError("Remote ordinals belong only to the VMAT app")
    if app_profile not in ("caresse", "werkmeister"):
        raise ValueError("App profile must be caresse or werkmeister")
    if isinstance(control_type, bool) or (
        control_type != "other"
        and (not isinstance(control_type, int) or control_type not in (-1, 0, 1, 2, 3, 4, 5, 6, 7))
    ):
        raise ValueError("Use an exact control type or the explicit other layout")
    if any(type(flag) is not bool for flag in (restored, rgb, massage, light_extension)):
        raise ValueError("Retained feature flags must be booleans")
    if floor_light is not None and type(floor_light) is not bool:
        raise ValueError("Floor-light flag must be boolean")
    floor = app_profile == "werkmeister" if floor_light is None else floor_light
    if app_profile == "werkmeister":
        if control_type not in (5, 7) or restored or not floor or rgb or massage or light_extension:
            raise ValueError("Werkmeister exposes only its two shipped floor-light profiles")
    elif not restored and (control_type != 2 or floor or rgb or massage or light_extension):
        raise ValueError("Fresh Caresse is type 2 with all optional features disabled")
    groups = (
        ()
        if control_type == "other"
        else ("back", "legs")
        if control_type in (0, 2, 5)
        else ("head", "back", "legs")
        if control_type in (3, 4, 6)
        else ("head", "back", "legs", "feet")
    )
    basic = control_type in (2, 3)
    slots = 0 if control_type == 2 else 3 if control_type == 3 else 6
    return VibradormAppProfile(
        app_profile,
        control_type,
        restored,
        floor,
        rgb,
        massage,
        light_extension,
        groups,
        basic,
        slots,
    )
