"""StarCode/legacy dialect dispatch shared by the M5X5 and M1X12 StarCode apps.

The Device Information manufacturer string selects the dialect. StarCode-dialect
frames come from ``codec/okin_5a.py`` and legacy-dialect frames from
``codec/okin_nframe.py``.
"""

from __future__ import annotations

from ..codec import okin_5a, okin_nframe


def is_star(dialect: str) -> bool:
    """Return whether ``dialect`` is the StarCode dialect, rejecting unknown names."""
    if dialect not in ("legacy", "star"):
        raise ValueError(f"Unknown StarCode dialect: {dialect}")
    return dialect == "star"


def manufacturer_dialect(data: bytes) -> str:
    """Decode exact raw character codes; only case-insensitive ``star`` selects it.

    Substring matching or UTF-8 decoding would classify differently.
    """
    return "star" if "".join(chr(value) for value in data).lower() == "star" else "legacy"


def normal_packet(key: int, dialect: str) -> bytes:
    """Build one normal control frame, keeping the key's low 32 bits (negatives included)."""
    if is_star(dialect):
        return okin_5a.normal(key & 0xFFFFFFFF)
    return okin_nframe.frame40(key & 0xFFFFFFFF)


def long_packet(key: int) -> bytes:
    """Build the ten-byte light command, a 64-bit Okin N-frame in both dialects."""
    return okin_nframe.frame(key & 0xFFFFFFFF, 8)


def extended_packet(command: int, value: int, dialect: str) -> bytes:
    """Build one extended (brightness, color or duration) frame."""
    if is_star(dialect):
        return okin_5a.extended(command & 0xFF, value & 0xFF)
    return okin_nframe.extended(command & 0xFF, value & 0xFF)


def position_packet(axis: int, target: int, dialect: str) -> bytes:
    """Build a raw Part target frame, clamping both byte arguments."""
    pair = (max(0, min(axis, 255)), max(0, min(target, 255)))
    if is_star(dialect):
        return okin_5a.position_target(*pair)
    return okin_nframe.position_target(*pair)


def query_packet(dialect: str) -> bytes:
    """Build the status query."""
    return okin_5a.request(0xB0) if is_star(dialect) else okin_nframe.request(0xB0)
