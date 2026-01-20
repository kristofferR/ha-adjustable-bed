"""Leggett & Platt MLRM bed controller - backwards compatibility wrapper.

This module is maintained for backwards compatibility.
The implementation has been moved to leggett_wilinke.py.

For new code, import from leggett_wilinke instead:
    from .leggett_wilinke import LeggettWilinkeController, LeggettWilinkeCommands
"""

from .leggett_wilinke import (
    LeggettWilinkeCommands,
    LeggettWilinkeController,
)

# Backwards compatibility aliases
LeggettPlattMlrmCommands = LeggettWilinkeCommands
LeggettPlattMlrmController = LeggettWilinkeController

__all__ = [
    "LeggettPlattMlrmCommands",
    "LeggettPlattMlrmController",
    # Also export new names for gradual migration
    "LeggettWilinkeCommands",
    "LeggettWilinkeController",
]
