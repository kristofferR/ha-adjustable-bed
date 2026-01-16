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


class OkinCommandConstants:
    """Shared Okin protocol command constants (32-bit values).

    These values are shared across Okimat, DewertOkin, and Leggett Okin beds.
    Individual controllers may define additional commands or use different
    values for specific features.
    """

    # Motor controls - standard across all Okin protocol beds
    MOTOR_HEAD_UP = 0x1
    MOTOR_HEAD_DOWN = 0x2
    MOTOR_FEET_UP = 0x4
    MOTOR_FEET_DOWN = 0x8
    MOTOR_TILT_UP = 0x10
    MOTOR_TILT_DOWN = 0x20
    MOTOR_LUMBAR_UP = 0x40
    MOTOR_LUMBAR_DOWN = 0x80

    # Stop command
    STOP = 0x0

    # Presets - values may vary by remote/controller
    PRESET_ZERO_G = 0x1000
    PRESET_MEMORY_1 = 0x2000
    PRESET_MEMORY_2 = 0x4000
    PRESET_MEMORY_3 = 0x8000
    PRESET_MEMORY_4 = 0x10000
    PRESET_FLAT = 0x8000000  # Most common flat value

    # Lights
    TOGGLE_LIGHTS = 0x20000

    # Massage
    MASSAGE_STEP = 0x100
    MASSAGE_TIMER_STEP = 0x200
    MASSAGE_FOOT_UP = 0x400
    MASSAGE_HEAD_UP = 0x800
    MASSAGE_HEAD_DOWN = 0x800000
    MASSAGE_FOOT_DOWN = 0x1000000


class OkinMotorStateMachine:
    """Tracks motor state for combined Okin commands.

    The Okin protocol allows combining multiple motor commands into a single
    command by OR-ing the command values together. This class tracks which
    motors are currently being commanded and generates the combined command.
    """

    def __init__(self) -> None:
        """Initialize the motor state machine."""
        self._motor_state: dict[str, bool | None] = {}

    def set_motor(self, motor: str, direction: bool | None) -> None:
        """Set the state of a motor.

        Args:
            motor: Motor name ('head', 'feet', 'tilt', 'lumbar')
            direction: True for up, False for down, None to stop
        """
        self._motor_state[motor] = direction

    def clear(self) -> None:
        """Clear all motor states."""
        self._motor_state = {}

    def get_combined_command(self) -> int:
        """Calculate the combined motor movement command.

        Returns:
            Combined 32-bit command value
        """
        command = 0
        state = self._motor_state

        if state.get("head") is True:
            command |= OkinCommandConstants.MOTOR_HEAD_UP
        elif state.get("head") is False:
            command |= OkinCommandConstants.MOTOR_HEAD_DOWN

        if state.get("feet") is True:
            command |= OkinCommandConstants.MOTOR_FEET_UP
        elif state.get("feet") is False:
            command |= OkinCommandConstants.MOTOR_FEET_DOWN

        if state.get("tilt") is True:
            command |= OkinCommandConstants.MOTOR_TILT_UP
        elif state.get("tilt") is False:
            command |= OkinCommandConstants.MOTOR_TILT_DOWN

        if state.get("lumbar") is True:
            command |= OkinCommandConstants.MOTOR_LUMBAR_UP
        elif state.get("lumbar") is False:
            command |= OkinCommandConstants.MOTOR_LUMBAR_DOWN

        return command
