"""VivaSleep 1.0.4's static HHC subset, intentionally not a runnable bed profile.

No complete panel action/cleanup contract is known. These helpers describe only
the app's predicates, writer, two Sync branches and post-accumulation fields.
They confer no capabilities and do not register discovery, entities or actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Final, Literal

from ..codec import motomotion as codec

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
    """Neutral Dart object fields, without physical units or entity semantics."""

    field_count: int
    rgb_fields_7_b_f_13: tuple[str, str, str, str] | None = None
    alarm_fields_7_b_f: tuple[str, str, str] | None = None
    bind_fields_7_b: tuple[bool, bool] | None = None
    sync_type: int | None = None
    stream_event: Literal["OK"] | None = None


def parse_accumulated(data: bytes) -> VivaSleepState:
    """Parse one already-accumulated buffer, never individual GATT fragments.

    The upstream accumulator's boundaries and validation remain unknown. There
    is no checksum validation here, and OK is an app event, not a hardware ACK.
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


@dataclass(frozen=True, slots=True)
class VivaSleepProfile:
    """App-local selection and formatting only, with no controller inheritance."""

    key: ClassVar[str] = "vivasleep"
    write_with_response: ClassVar[bool] = False
    name: str

    def __post_init__(self) -> None:
        if not accepts_name(self.name):
            raise ValueError("VivaSleep requires an HHC name of 14 UTF-16 units")

    @property
    def wrapped(self) -> bool:
        return _code_units(self.name)[11] == "M"

    @property
    def panel(self) -> str:
        """The primary factory target alone, without its unresolved capabilities."""
        c8, c9 = _code_units(self.name)[8:10]
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

    def writer_bytes(self, command: str) -> bytes | None:
        """ASCII subset only; selection/connection admission belongs to a future runtime."""
        return codec.short_transport(command, wrapped=self.wrapped)

    def sync_frame(self, *, field_7: bool, field_b: bool, field_13: int) -> bytes | None:
        """One conditional toolbar callback; no physical sync effect is asserted."""
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
