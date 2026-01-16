"""Shared Okin protocol implementation.

This module provides the core Okin BLE protocol used by multiple bed types:
- Okimat (UUID-based writes)
- DewertOkin (handle-based writes)
- Leggett & Platt Okin variant (UUID-based writes)

All use the same 6-byte command format: [0x04, 0x02, <4-byte-command-big-endian>]

The protocol was originally developed by OKIN (now part of DewertOkin GmbH).
"""

from __future__ import annotations


def int_to_bytes(value: int) -> list[int]:
    """Convert an integer to 4 bytes (big-endian).

    Args:
        value: 32-bit unsigned integer command value (0 to 0xFFFFFFFF)

    Returns:
        List of 4 bytes in big-endian order

    Raises:
        TypeError: If value is not an integer
        ValueError: If value is outside the valid 32-bit unsigned range
    """
    if not isinstance(value, int):
        raise TypeError(f"Command value must be an integer, got {type(value).__name__}")
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError(
            f"Command value must be 0 <= value <= 0xFFFFFFFF, got {value:#x}"
        )
    return [
        (value >> 24) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
    ]


def build_okin_command(command_value: int) -> bytes:
    """Build a 6-byte Okin protocol command.

    Args:
        command_value: 32-bit integer representing the command

    Returns:
        6-byte command: [0x04, 0x02, <4-byte-command>]
    """
    return bytes([0x04, 0x02] + int_to_bytes(command_value))
