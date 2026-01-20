"""Okimat bed controller - backwards compatibility wrapper.

This module is maintained for backwards compatibility.
The implementation has been moved to okin_uuid.py.

For new code, import from okin_uuid instead:
    from .okin_uuid import OkinUuidController, OkinUuidRemoteConfig
"""

from .okin_uuid import (
    OkinUuidController,
    OkinUuidRemoteConfig,
    OkinUuidComplexCommand,
    OKIN_UUID_REMOTES,
    # Backwards compatibility aliases exported from okin_uuid.py
    OkimatRemoteConfig,
    OkimatComplexCommand,
    OkimatController,
    OKIMAT_REMOTES,
)

# Additional wrapper-level aliases for different naming conventions
REMOTE_CONFIGS = OKIN_UUID_REMOTES  # Some code may use this name

__all__ = [
    # Legacy names
    "OkimatController",
    "OkimatRemoteConfig",
    "OkimatComplexCommand",
    "OKIMAT_REMOTES",
    "REMOTE_CONFIGS",
    # New names for gradual migration
    "OkinUuidController",
    "OkinUuidRemoteConfig",
    "OkinUuidComplexCommand",
    "OKIN_UUID_REMOTES",
]
