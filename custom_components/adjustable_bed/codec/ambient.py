"""M3 Ambient P1 position frames and typed bed notifications."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Final, Literal, cast

from .motomotion import binary_command


class Side(IntEnum):
    """The logical selectors for the two sides of one connection."""

    LEFT = 0xAA
    RIGHT = 0xBB


type RGB = tuple[int, int, int]
type MassageZone = Literal["shoulder", "feet"]

_TARGET_TAIL: Final = bytes.fromhex("00 00 41 0A 13")
_ONE_TARGET: Final = bytes.fromhex("24 23 80 09")
_SPLIT_TARGET: Final = bytes.fromhex("26 25 80 09")
_ONE_STATE: Final = bytes.fromhex("24 23 9F 79")
_SPLIT_STATE: Final = bytes.fromhex("26 25 9F 79")
_ONE_TEMPLATE: Final = _ONE_TARGET + bytes(8) + _TARGET_TAIL

HOME_FLAT: Final = binary_command(0x5555)
LIGHT_ON: Final = binary_command(0x80F1)
LIGHT_OFF: Final = binary_command(0x80F2)
BED_STATE_QUERY: Final = binary_command(0x9C42)
_RGB_OPCODES: Final = {"red": 0x80E8, "green": 0x80E9, "blue": 0x80EA}
_MASSAGE: Final[dict[MassageZone, tuple[int, tuple[int, ...]]]] = {
    "shoulder": (0x8279, (0, 0x15, 0x3D, 0x78)),
    "feet": (0x827A, (0, 0x17, 0x3C, 0x78)),
}


def signed(value: int) -> int:
    return value if value < 128 else value - 256


def rgb(channel: str, value: int) -> bytes:
    """Encode a raw channel byte. Picker scaling belongs to the caller."""
    if not 0 <= value <= 255:
        raise ValueError("Expected a raw RGB byte")
    return binary_command(_RGB_OPCODES[channel], value)


def massage(zone: MassageZone, level: int) -> bytes:
    opcode, values = _MASSAGE[zone]
    if not 0 <= level < len(values):
        raise ValueError("Expected a massage level from 0 to 3")
    return binary_command(opcode, values[level])


_MASSAGE_ECHOES: Final[dict[bytes, tuple[MassageZone, int]]] = {
    massage(zone, level): (zone, level) for zone in _MASSAGE for level in range(4)
}


def parse_massage_echo(data: bytes) -> tuple[MassageZone, int] | None:
    return _MASSAGE_ECHOES.get(data)


def _massage_level(zone: MassageZone, value: int) -> int:
    _, values = _MASSAGE[zone]
    return values.index(value) if value in values else 0


@dataclass(frozen=True, slots=True)
class Coordinates:
    head: int
    feet: int
    neck: int


@dataclass(frozen=True, slots=True)
class Position:
    side: Side | None
    coordinates: Coordinates
    lumbar: int
    template: bytes | None = None


@dataclass(frozen=True, slots=True)
class BedState:
    position: Position
    shoulder: int
    feet_massage: int
    rgb: RGB


def position(
    coordinates: Coordinates, side: Side | None = None, *, template: bytes | None = None
) -> bytes:
    head, feet, neck = coordinates.head, coordinates.feet, coordinates.neck
    if side is not None:
        return _SPLIT_TARGET + bytes((side, 0, head, 0, feet, 0, neck, 0, 0)) + _TARGET_TAIL
    outgoing = bytearray(template if template is not None else _ONE_TEMPLATE)
    outgoing[5], outgoing[7], outgoing[9] = head, feet, neck
    return bytes(outgoing)


def parse_bed_state(data: bytes) -> Position | BedState | None:
    """Decode strict target-shaped or combined reports from one notification."""
    if len(data) == 17 and data.startswith((_ONE_TARGET, _ONE_STATE)):
        side, offset = None, 0
    elif len(data) == 18 and data.startswith((_SPLIT_TARGET, _SPLIT_STATE)):
        if data[4] not in (Side.LEFT, Side.RIGHT):
            return None
        side, offset = Side(data[4]), 1
    else:
        return None

    if data.startswith((_ONE_TARGET, _SPLIT_TARGET)):
        if not data.endswith(_TARGET_TAIL):
            return None
        head, feet, neck, lumbar = (signed(data[index + offset]) for index in (5, 7, 9, 11))
        return Position(side, Coordinates(head, feet, neck), lumbar, data if side is None else None)

    head, feet, neck, lumbar = (signed(value) for value in data[4 + offset : 8 + offset])
    return BedState(
        Position(side, Coordinates(head, feet, neck), lumbar),
        _massage_level("shoulder", data[8 + offset]),
        _massage_level("feet", data[9 + offset]),
        cast(RGB, tuple(data[10 + offset : 13 + offset])),
    )
