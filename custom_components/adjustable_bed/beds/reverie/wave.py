"""The Reverie app's wave buttons, shared by its Protocol 108 and 110 controllers."""

from __future__ import annotations

from typing import Final

from ...controller_state import StateKey

# Stop is "off"; the four wave buttons send their own number.
WAVE_PATTERN: Final = StateKey[str | None]("reverie_massage_wave")
WAVE_PATTERNS: Final = ("off", "1", "2", "3", "4")
