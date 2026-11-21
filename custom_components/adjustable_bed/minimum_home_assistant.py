"""Stop with one clear message on a Home Assistant older than this version supports.

The package imports helpers that older Home Assistant versions do not have, so
the check runs on import, before them, and needs nothing newer itself. Home
Assistant shows the message in its "Setup failed" log line. A translated repair
cannot be raised here: without the import there is no integration to load
translations for.
"""

from __future__ import annotations

from typing import Final

from awesomeversion import AwesomeVersion
from homeassistant.const import __version__ as HA_VERSION

# Keep in step with hacs.json.
MINIMUM: Final = "2026.11.0"


def require(version: str = HA_VERSION) -> None:
    """Raise ImportError when ``version`` is older than the minimum."""
    if AwesomeVersion(version) < AwesomeVersion(MINIMUM):
        raise ImportError(
            f"Adjustable Bed needs Home Assistant {MINIMUM} or newer, and this is "
            f"{version}. Update Home Assistant, then restart it."
        )


require()
