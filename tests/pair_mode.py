"""Test-only key that starts a pair in an explicit connection mode.

The integration never reads it; ``conftest`` applies it to new pairs so tests
can exercise the sequential topology through a full setup.
"""

from typing import Final

CONF_PAIR_CONNECTION_MODE: Final = "pair_connection_mode"
