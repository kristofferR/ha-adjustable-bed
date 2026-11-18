"""Personal Comfort's air and Reverie builders, independent of controllers.

The Malouf route uses the existing Richmat codec. These formats do not:
the ASCII query, three-element air payload, XOR light exception and per-axis
destinations differ from the existing LOGICDATA and Reverie profiles.
"""

from dataclasses import dataclass
from typing import Final, Literal

Side = Literal["left", "right"]


def bluetooth_uuid(short: str) -> str:
    return f"0000{short}-0000-1000-8000-00805f9b34fb"


def reverie_uuid(prefix: str) -> str:
    return f"{prefix}-f324-29c3-38d1-85c0c2e86885"


RA_SERVICE: Final = "57e34968-7076-417f-b645-4789bd9e02df"
RA_NOTIFY: Final = "084103c2-3350-4fec-9900-84e468c702df"
RA_WRITE: Final[dict[Side, str]] = {
    "left": "95ae8e50-29af-47bc-aa34-55daac0202df",
    "right": "ace41e3d-1e48-4fac-bcae-43d7e7d202df",
}
RA_READ: Final[dict[Side, str]] = {
    "left": "a3cded49-47e6-4d77-8e10-3e2c5d6602df",
    "right": "0638f1b8-f242-4c47-b5b1-a07623cc02df",
}
V1_SERVICE: Final = "1b1d9641-b942-4da8-89cc-98e6a58fbd93"
V1_WRITE: Final = "6af87926-dc79-412e-a3e0-5f85c2d55de2"
AXES: Final = {"pillow": "db801020", "head": "db801021", "feet": "db801022"}
LEGACY_FIRMWARE: Final = frozenset(f"71RU2265.0{i}" for i in range(4))


def anm3(op: int, head_foot: int = 0, middle: int = 0, side: int = 0) -> bytes:
    return bytes(
        (
            0x55,
            4,
            op & 255,
            head_foot & 255,
            middle & 255,
            0,
            0,
            side & 255,
            (89 + op + head_foot + middle + side) & 255,
            0xAA,
        )
    )


def anm5(action: str, side: Side = "left", number: float = 5) -> bytes:
    if action == "set":
        pressure = int((min(50, max(5, number)) - 5) * 66 / 45)
        line = f"C>SETP>{0 if side == 'left' else 1}>{pressure}"
    else:
        line = {"select": "C>TPCH>0", "query": "R>SP", "stop": "C>STOPN"}[action]
    return (line + "\n").encode("ascii")


def ra(number: int) -> bytes:
    return bytes(((number * 2) & 255, 15, 15))


def xor(command: int, data: bytes = b"") -> bytes:
    packet = bytes((0x55, command)) + data
    checksum = 0
    for value in packet:
        checksum ^= value
    return packet + bytes((checksum,))


def next_wave(previous: int | None) -> int:
    return previous + 1 if previous is not None and 0 <= previous <= 4 else 1


BASE5: Final = {
    "head_up": 1,
    "head_down": 3,
    "feet_up": 2,
    "feet_down": 4,
    "zero_g": 0x15,
    "flat": 5,
    "anti_snore": 0x16,
    "massage_head": 0x31,
    "massage_foot": 0x32,
    "massage_off": 0x35,
}
BASE6: Final = {
    "head_up": ("db801021", 1),
    "head_down": ("db801021", 2),
    "feet_up": ("db801022", 1),
    "feet_down": ("db801022", 2),
    "pillow_up": ("db801020", 1),
    "pillow_down": ("db801020", 2),
    "zero_g": ("db8010d0", 1),
    "anti_snore": ("db8010d0", 2),
    "flat": ("db8010d0", 3),
    "memory_1": ("db8010d0", 4),
    "memory_2": ("db8010d0", 5),
    "save_1": ("db8010d0", 0x84),
    "save_2": ("db8010d0", 0x85),
    "massage_head": ("db801061", 50),
    "massage_foot": ("db801060", 50),
    "massage_off": ("db801080", 0),
}


def base5(action: str, *, wave: int = 1) -> bytes:
    if action == "light_toggle":
        return b"\x55\x5b"
    if action == "massage_mode":
        return xor(0x40 + wave, b"\xcc")
    if action == "stop":
        return xor(0xFF)
    return xor(BASE5[action])


def base6(action: str, *, wave: int = 1, light_on: bool = False) -> tuple[str, bytes]:
    if action == "light":
        prefix, value = "db8010a0", 100 if light_on else 0
    elif action == "massage_mode":
        prefix, value = "db801080", wave
    else:
        prefix, value = BASE6[action]
    return reverie_uuid(prefix), bytes((value,))


def release_axis(axis: str) -> tuple[str, bytes]:
    return reverie_uuid(AXES[axis]), b"\x00"


@dataclass(frozen=True)
class AirReply:
    status: int
    left: int | None = None
    right: int | None = None
    maximum: int | None = None
    left_memory: int | None = None
    right_memory: int | None = None
    status0: int | None = None


def parse_anm3(packet: bytes) -> AirReply | None:
    if len(packet) < 3:
        return None
    status = packet[2]
    if status == 0x83:
        if len(packet) < 6:
            return None
        return AirReply(status, packet[5] or None, packet[4] or None)
    return AirReply(status)


def parse_anm5(packet: bytes) -> AirReply | None:
    if not packet.startswith(b"RET>SP>") or len(packet) < 21:
        return None
    try:
        values = [int(packet[i : i + 2], 16) for i in range(7, 21, 2)]
    except ValueError:
        return None
    maximum, left, right, left_memory, right_memory = (
        int(5 + 45 * min(66, value) / 66) for value in values[2:]
    )
    return AirReply(values[1], left, right, maximum, left_memory, right_memory, values[0])


def ra_number(packet: bytes, firmware: str) -> int | None:
    if not packet:
        return None
    return packet[0] if firmware in LEGACY_FIRMWARE else packet[0] // 2


def ra_status(packet: bytes) -> int | None:
    return int.from_bytes(packet[:2], "big") if len(packet) >= 2 else None
