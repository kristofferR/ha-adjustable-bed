"""AVEK Ergo System B0 controls, B1 identity and unsolicited raw counts."""

from dataclasses import dataclass
from typing import Final

SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY_UUID: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
IDENTITY_REQUEST: Final = bytes.fromhex("b0 02 01 01 b4")


def _summed(body: bytes) -> bytes:
    return body + bytes((sum(body) & 255,))


def control(word: int) -> bytes:
    return _summed(bytes((0xB0, 5, 0x10, 0, 0xC0)) + word.to_bytes(2, "little"))


def identity(app_id: bytes) -> bytes:
    if len(app_id) != 6:
        raise ValueError("AVEK identity requires six bytes")
    return _summed(bytes((0xB1, 7, 0)) + app_id)


@dataclass(frozen=True, slots=True)
class Count:
    index: int
    value: int


def parse_count(data: bytes) -> Count | None:
    """The app consumes the first record, including when trailing bytes exist.

    Reject short records and signed negative indexes rather than reproducing
    the app's out-of-bounds access. No physical unit or axis is inferred.
    """
    if (
        len(data) < 9
        or data[:2] != b"\xb0\x06"
        or sum(data[:8]) & 255 != data[8]
        or data[4] & 0xC3 != 0xC3
        or data[5] >= 3
    ):
        return None
    return Count(data[5], int.from_bytes(data[6:8], "little", signed=True))


def display_level(count: int) -> int:
    """The app's seven image bins, not a measured firmness scale."""
    return max(0, min(6, (count - 10000) // 66))
