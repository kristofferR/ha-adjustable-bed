"""Leggett & Platt bed controller - backwards compatibility wrapper.

This module is maintained for backwards compatibility.
The implementations have been split into separate protocol files:
- leggett_gen2.py - Gen2 ASCII protocol beds
- leggett_okin.py - Okin binary protocol beds

For new code, import from the specific protocol file:
    from .leggett_gen2 import LeggettGen2Controller, LeggettGen2Commands
    from .leggett_okin import LeggettOkinController, LeggettOkinCommands
"""

from .leggett_gen2 import (
    LeggettGen2Commands,
    LeggettGen2Controller,
)
from .leggett_okin import (
    LeggettOkinCommands,
    LeggettOkinController,
)

# Backwards compatibility aliases
# The original module exported both variants under LeggettPlatt* names
LeggettPlattGen2Commands = LeggettGen2Commands
LeggettPlattOkinCommands = LeggettOkinCommands

# LeggettPlattController defaults to Gen2 for backwards compatibility.
# Users with Okin-variant beds should use LeggettOkinController directly:
#   from .leggett_okin import LeggettOkinController
LeggettPlattController = LeggettGen2Controller

__all__ = [
    # Legacy names
    "LeggettPlattGen2Commands",
    "LeggettPlattOkinCommands",
    "LeggettPlattController",
    # New names for gradual migration
    "LeggettGen2Commands",
    "LeggettGen2Controller",
    "LeggettOkinCommands",
    "LeggettOkinController",
]
