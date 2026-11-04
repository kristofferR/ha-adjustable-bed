"""Okin command-word helpers for the routes not yet on ``codec/okin_nframe.py``.

The 32-bit routes (Okimat, DewertOkin, Customatic, Leggett Okin, RF ECO BT)
frame through the codec, as do the 40-bit routes. The 96-bit routes still build
their frames here until they move onto it (#759).
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
        raise ValueError(f"Command value must be 0 <= value <= 0xFFFFFFFF, got {value:#x}")
    return [
        (value >> 24) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
    ]


def build_cst_command(
    motor_value: int = 0, control_value: int = 0
) -> bytes:
    """Build a 14-byte CSTProtocol command.

    CSTProtocol uses two separate 32-bit command fields. The first field carries
    motor movement plus several remote actions; the second carries the remaining
    remote actions. Field placement comes from the CST app's protocol mapping.

    Args:
        motor_value: 32-bit first-field command
        control_value: 32-bit second-field command

    Returns:
        14-byte command: [0x0C, 0x02, motor[4], control[4], 0x00*4]
    """
    return bytes(
        [0x0C, 0x02]
        + int_to_bytes(motor_value)
        + int_to_bytes(control_value)
        + [0x00, 0x00, 0x00, 0x00]
    )
