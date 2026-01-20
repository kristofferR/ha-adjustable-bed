"""MattressFirm bed controller - backwards compatibility wrapper.

This module is maintained for backwards compatibility.
The implementation has been moved to okin_nordic.py.

For new code, import from okin_nordic instead:
    from .okin_nordic import OkinNordicController, OkinNordicCommands
"""

from .okin_nordic import (
    OkinNordicCommands,
    OkinNordicController,
)

# Backwards compatibility aliases
MattressFirmCommands = OkinNordicCommands
MattressFirmController = OkinNordicController

__all__ = [
    "MattressFirmCommands",
    "MattressFirmController",
    # Also export new names for gradual migration
    "OkinNordicCommands",
    "OkinNordicController",
]
