"""DewertOkin bed controller - backwards compatibility wrapper.

This module is maintained for backwards compatibility.
The implementation has been moved to okin_handle.py.

For new code, import from okin_handle instead:
    from .okin_handle import OkinHandleController, OkinHandleCommands
"""

from .okin_handle import (
    OkinHandleCommands,
    OkinHandleController,
)

# Backwards compatibility aliases
DewertOkinCommands = OkinHandleCommands
DewertOkinController = OkinHandleController

__all__ = [
    "DewertOkinCommands",
    "DewertOkinController",
    # Also export new names for gradual migration
    "OkinHandleCommands",
    "OkinHandleController",
]
