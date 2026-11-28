"""VivaSleep 1.0.4: independently declared HHC layouts and optional gates."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Final, Literal

from ..codec import motomotion as codec
from ..execution import STREAM_HOLD, ExecutionCapabilities
from .bedgear import Control

SERVICE_MARKER: Final = "FFE0"
CHARACTERISTIC_MARKER: Final = "FFE1"
NAME_LENGTH: Final = 14
REPEAT_INTERVAL_MS: Final = 100
SHORT_UP_THRESHOLD: Final = 5
SHORT_UP_OFFSETS_MS: Final = (0, 100, 200)
STOP_OFFSETS_MS: Final = (0, 30, 60, 90, 120)
SYNC_COMMANDS: Final = MappingProxyType({False: "00012", True: "00015"})
SYNC_PARAMETER: Final = "00000"
RGB_FIELD_INDICES: Final = MappingProxyType(
    {75: (28, 29, 30, 54), 71: (18, 19, 20, 30), 39: (18, 19, 20, 30), 44: (18, 19, 20, 30)}
)
ALARM_FIELD_INDICES: Final = (8, 9, 11)
BIND_FIELD_INDEX: Final = 27
SYNC_TYPE_INDEX: Final = 24
COLOR_COMMANDS: Final = (315, 316, 317)
TIMER_COMMAND: Final = 319
TIMER_MAX_MINUTES: Final = 1439
SETTINGS_DELAY_MS: Final = 50
ALARM_SUFFIXES: Final = ("0017", "0118", "0219")
LAYOUT_EXAMPLES: Final = (
    "00",
    "11",
    "12",
    "13",
    "19",
    "21",
    "22",
    "23",
    "29",
    "31",
    "32",
    "33",
    "34",
    "39",
    "41",
    "42",
    "43",
    "44",
    "49",
    "25",
    "55",
    "65",
    "75",
    "50",
    "60",
    "D0",
    "70",
    "80",
    "90",
    "15",
    "35",
    "45",
    "85",
    "A0",
    "B0",
    "C0",
    "E0",
    "95",
    "96",
    "97",
    "98",
    "X0",
)


def decimal(value: str) -> int:
    if not value or not value.isascii() or not value.isdecimal():
        raise ValueError("Invalid VivaSleep decimal token")
    value = value.lstrip("0") or "0"
    if len(value) > 19 or len(value) == 19 and value > "9223372036854775807":
        raise ValueError("Invalid VivaSleep decimal token")
    return int(value)


def alarm_frame(hour: str, minute: str, strength: int) -> bytes:
    """Preserve the app's cached variable-width fields; callers validate UI time."""
    return codec.decimal_fields(hour + minute + "00", ALARM_SUFFIXES[strength])


def _code_units(name: str) -> tuple[str, ...]:
    encoded = name.encode("utf-16-le", errors="surrogatepass")
    return tuple(
        chr(int.from_bytes(encoded[i : i + 2], "little")) for i in range(0, len(encoded), 2)
    )


def accepts_name(name: str | None) -> bool:
    """The app accepts uppercase HHC anywhere in exactly 14 UTF-16 units."""
    return name is not None and len(_code_units(name)) == NAME_LENGTH and "HHC" in name


def matches_service(uuid: str) -> bool:
    return SERVICE_MARKER in uuid.upper()


def matches_characteristic(uuid: str) -> bool:
    """Apply only within a matching service; retain the original runtime UUID."""
    return CHARACTERISTIC_MARKER in uuid.upper()


@dataclass(frozen=True, slots=True)
class VivaSleepState:
    """Raw app cache fields before consumer validation, not fresh HA state."""

    field_count: int
    rgb_fields_7_b_f_13: tuple[str, str, str, str] | None = None
    alarm_fields_7_b_f: tuple[str, str, str] | None = None
    bind_fields_7_b: tuple[bool, bool] | None = None
    sync_type: int | None = None
    stream_event: Literal["OK"] | None = None


def parse_accumulated(data: bytes) -> VivaSleepState:
    """Parse one already-accumulated buffer, never individual GATT fragments.

    The shared receiver owns fragment collection. There is no checksum
    validation here, and OK is an app event, not a hardware ACK.
    """
    fields = codec.decimal_tokens(data)
    count = len(fields)
    indices = RGB_FIELD_INDICES.get(count)
    rgb = None
    if indices is not None:
        a, b, c, d = indices
        rgb = (fields[a], fields[b], fields[c], fields[d])
    a, b, c = ALARM_FIELD_INDICES
    alarm = (fields[a], fields[b], fields[c]) if count == 75 else None
    bind = None
    sync_type = None
    if count == 39:
        token = fields[BIND_FIELD_INDEX]
        bind = (token in ("00065", "00066"), token == "00065")
        sync_token = fields[SYNC_TYPE_INDEX]
        if not sync_token or not sync_token.isascii() or not sync_token.isdecimal():
            raise ValueError("Invalid VivaSleep decimal sync token")
        sync_token = sync_token.lstrip("0") or "0"
        if len(sync_token) > 19 or (len(sync_token) == 19 and sync_token > "9223372036854775807"):
            raise ValueError("Invalid VivaSleep decimal sync token")
        sync_type = int(sync_token, 10)
    return VivaSleepState(
        field_count=count,
        rgb_fields_7_b_f_13=rgb,
        alarm_fields_7_b_f=alarm,
        bind_fields_7_b=bind,
        sync_type=sync_type,
        stream_event="OK" if count == 39 else None,
    )


def select_panel(name: str | None) -> str:
    units = _code_units(name) if name is not None else ()
    if len(units) < 10:
        return "PanelOne"
    c8, c9 = units[8:10]
    if (c8 == "1" and c9 == "5") or c8 == "A":
        return "PanelA"
    if (c8 in "348" and c9 == "5") or c8 == "C":
        return "PanelD"
    if c8 == "4" or (c8 in "25" and c9 == "5") or c8 == "B":
        return "PanelFour"
    if c8 == "9" and c9 in "5678":
        return "WR1140"
    if c8 == "3" or (c8 in "67" and c9 == "5"):
        return "PanelThree"
    return {
        "0": "PanelZero",
        "1": "PanelOne",
        "2": "PanelTwo",
        "5": "PanelFive",
        "6": "PanelSix",
        "7": "PanelSeven",
        "8": "PanelEight",
        "9": "PanelNine",
        "D": "PanelSixZG",
        "E": "PanelE",
    }.get(c8, "PanelOne")


def axes_for_name(name: str) -> tuple[tuple[str, str, str], ...]:
    units = _code_units(name)
    p, a, b = select_panel(name), units[8], units[9]
    zones = ("head", "foot")
    if p in ("PanelE", "PanelFive"):
        zones = ("head",)
    elif p == "PanelZero":
        zones = ("head", "foot", "combined", "tilt")
    elif p == "PanelA":
        zones = ("head", "foot", "lumbar")
    elif p == "PanelD":
        zones = ("head", "foot", {"4": "lumbar", "8": "tilt"}.get(a, "neck"))
    elif p == "WR1140":
        zones = {
            "5": ("head", "foot", "tilt"),
            "6": ("head", "foot"),
            "7": ("neck", "head", "lumbar", "foot"),
            "8": ("head", "lumbar", "foot"),
        }[b]
    elif p in ("PanelOne", "PanelTwo"):
        zones = {"1": ("head",), "2": ("head", "foot"), "3": ("neck", "head", "foot")}.get(
            b, ("neck", "head", "foot") if p == "PanelOne" else ("head", "foot")
        )
    elif p in ("PanelThree", "PanelFour"):
        if a == ("3" if p == "PanelThree" else "4"):
            zones = {
                "1": ("head",),
                "2": ("head", "foot"),
                "3": ("neck", "head", "foot"),
                "4": ("neck", "head", "lumbar", "foot"),
            }.get(b, zones)
        elif a + b in ("25", "65"):
            zones = ("head", "lumbar", "foot")
        elif a + b == "55":
            zones = ("neck", "head", "foot", "tilt")
        elif a + b == "75":
            zones = ("neck", "head", "lumbar", "foot")
    result = []
    for zone in zones:
        letters = {
            "head": "KL",
            "foot": "MN",
            "neck": "PQ",
            "lumbar": "pq",
            "tilt": "pq",
            "combined": "pq",
        }[zone]
        if zone == "tilt" and p in ("PanelZero", "PanelD", "WR1140"):
            letters = "PQ"
        if zone == "lumbar" and (
            p == "PanelD" or a + b in ("25", "65") or p == "PanelA" and units[13] != "H"
        ):
            letters = "PQ"
        result.append((zone, *letters))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class VivaSleepProfile:
    """One original advertisement, never a display nickname or sibling layout."""

    key: ClassVar[str] = "vivasleep"
    name: str
    write_with_response: ClassVar[bool] = False
    execution: ExecutionCapabilities = STREAM_HOLD
    refresh_ms: ClassVar[int] = REPEAT_INTERVAL_MS
    stop_count: ClassVar[int] = len(STOP_OFFSETS_MS)
    stop_interval_ms: ClassVar[int] = 30
    fallback_count: ClassVar[int] = len(SHORT_UP_OFFSETS_MS)
    delayed_first_tick: ClassVar[bool] = True
    alarm_indices: ClassVar[tuple[int, int, int]] = ALARM_FIELD_INDICES

    def __post_init__(self) -> None:
        if not accepts_name(self.name):
            raise ValueError("VivaSleep requires an HHC name of 14 UTF-16 units")

    @property
    def wrapped(self) -> bool:
        return _code_units(self.name)[11] == "M"

    def char(self, index: int) -> str:
        return _code_units(self.name)[index]

    @property
    def rgb(self) -> bool:
        return self.char(10) != "B"

    @property
    def brightness(self) -> bool:
        return self.char(10) == "D"

    @property
    def timer(self) -> bool:
        return self.rgb

    @property
    def alarm(self) -> bool:
        return self.char(11) == "E"

    @property
    def sync(self) -> bool:
        return self.char(13) == "X"

    @property
    def axes(self) -> tuple[tuple[str, str, str], ...]:
        return axes_for_name(self.name)

    @property
    def memory_slots(self) -> int:
        return (
            2
            if self.panel
            in {
                "PanelZero",
                "PanelTwo",
                "PanelThree",
                "PanelFour",
                "PanelSeven",
                "PanelEight",
                "PanelA",
                "PanelD",
                "WR1140",
            }
            else 0
        )

    @property
    def light(self) -> bool:
        return self.memory_slots > 0 or self.panel == "PanelE"

    @property
    def presets(self) -> tuple[tuple[str, str], ...]:
        if self.panel in {"PanelA", "PanelThree", "PanelFour", "PanelEight", "WR1140"}:
            return (("flat", "O"), ("anti_snore", "R"), ("tv", "S"), ("zero_g", "T"))
        if self.panel == "PanelE":
            return (("flat", "O"), ("anti_snore", "R"))
        return (("zero_g", "T"),) if self.panel == "PanelSixZG" else (("flat", "O"),)

    @property
    def controls(self) -> tuple[Control, ...]:
        controls = [
            Control(
                axis + "_" + direction,
                letter,
                "fallback"
                if self.panel == "PanelZero" and axis == "tilt" and direction == "down"
                else "stop",
            )
            for axis, up, down in self.axes
            for direction, letter in (("up", up), ("down", down))
        ]
        for key, letter in self.presets:
            tail = (
                self.panel
                in {
                    "PanelA",
                    "PanelD",
                    "PanelEight",
                    "PanelSeven",
                    "PanelZero",
                    "PanelFive",
                    "PanelSix",
                    "PanelSixZG",
                }
                or self.panel == "PanelE"
                and key == "flat"
            )
            controls.append(Control("preset_" + key, letter, "fallback" if tail else "none"))
        controls.extend(
            Control(f"memory_{slot}", letter)
            for slot, letter in enumerate("UV"[: self.memory_slots], 1)
        )
        if self.light:
            controls.append(Control("light_toggle", "A", held=False, tap_up_write=True))
        if self.panel in {"PanelD", "PanelFour", "PanelSeven", "PanelTwo", "WR1140"}:
            controls.extend(
                Control("massage_" + key, letter, held=False)
                for key, letter in (("head", "C"), ("foot", "B"), ("stop", "D"))
            )
        elif self.panel == "PanelZero":
            controls.extend(
                Control("massage_" + key, letter, "fallback")
                for key, letter in (
                    ("head_up", "G"),
                    ("head_down", "H"),
                    ("head_stop", "J"),
                    ("foot_up", "E"),
                    ("foot_down", "F"),
                    ("foot_stop", "I"),
                )
            )
        return tuple(controls)

    @property
    def panel(self) -> str:
        return select_panel(self.name)

    def writer_bytes(self, command: str) -> bytes | None:
        """Format the shared writer; the live controller owns session admission."""
        return codec.utf16_transport(command, wrapped=self.wrapped)

    def sync_frame(self, *, field_7: bool, field_b: bool, field_13: int) -> bytes | None:
        """The toolbar's conditional coupling toggle from recognized bind state."""
        if not field_7 or field_13 != 0:
            return None
        return codec.decimal_fields(SYNC_COMMANDS[field_b], SYNC_PARAMETER)

    def short_up_schedule(
        self, command: str, *, repeat: bool, count: int, has_up_callback: bool, cancelled: bool
    ) -> tuple[tuple[int, bytes], ...]:
        """Extra copies on short up only, with no assumed per-button flags."""
        if cancelled or not repeat or count >= SHORT_UP_THRESHOLD or has_up_callback:
            return ()
        frame = self.writer_bytes(command)
        return () if frame is None else tuple((offset, frame) for offset in SHORT_UP_OFFSETS_MS)

    @property
    def stop_schedule(self) -> tuple[tuple[int, bytes], ...]:
        """Shared routine's nominal offsets, not a per-action release contract."""
        frame = codec.letter_command("b", wrapped=self.wrapped)
        return tuple((offset, frame) for offset in STOP_OFFSETS_MS)
