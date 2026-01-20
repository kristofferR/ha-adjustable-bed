"""Nectar bed controller - backwards compatibility wrapper.

This module is maintained for backwards compatibility.
The implementation has been moved to okin_7byte.py.

For new code, import from okin_7byte instead:
    from .okin_7byte import Okin7ByteController, Okin7ByteCommands
"""

from .okin_7byte import (
    Okin7ByteCommands,
    Okin7ByteController,
)

# Backwards compatibility aliases
NectarCommands = Okin7ByteCommands
NectarController = Okin7ByteController

__all__ = [
    "NectarCommands",
    "NectarController",
    # Also export new names for gradual migration
    "Okin7ByteCommands",
    "Okin7ByteController",
]
