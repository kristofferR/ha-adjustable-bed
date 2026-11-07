"""Controller-state keys of the StarCode M5X5 and M1X12 status parsers.

The parsers name their fields; the fields entities read publish under typed
keys and the rest under their parser names.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from ..controller_state import AnyStateKey, StateKey, StateUpdate
from ..state_keys import UNDER_BED_LIGHTS_ON

FIRMWARE_VERSION: Final = StateKey[str | None]("firmware")
LIGHT_BRIGHTNESS: Final = StateKey[int | None]("light_brightness")
LIGHT_COLOR_OPTION: Final = StateKey[str | None]("light_color_option")


def field_key(name: str) -> StateKey[object]:
    """A parsed diagnostic field."""
    return StateKey[object](name)


def spec_key(name: str) -> AnyStateKey:
    """The key an entity spec reads for parsed field ``name``."""
    typed: dict[str, AnyStateKey] = {
        FIRMWARE_VERSION: FIRMWARE_VERSION,
        LIGHT_BRIGHTNESS: LIGHT_BRIGHTNESS,
    }
    return typed.get(name, field_key(name))


def state_updates(values: Mapping[str, object]) -> list[StateUpdate]:
    """Updates for parsed ``values``; ``None`` clears a field."""
    updates: list[StateUpdate] = []
    for name, value in values.items():
        if name == FIRMWARE_VERSION:
            updates.append(FIRMWARE_VERSION(value if isinstance(value, str) else None))
        elif name == LIGHT_BRIGHTNESS:
            level = value if isinstance(value, int) and not isinstance(value, bool) else None
            updates.append(LIGHT_BRIGHTNESS(level))
        elif name == LIGHT_COLOR_OPTION:
            updates.append(LIGHT_COLOR_OPTION(value if isinstance(value, str) else None))
        elif name == "light_on":
            # The parser's field feeds its binary sensor, the shared key the light.
            updates.append(field_key(name)(value))
            updates.append(UNDER_BED_LIGHTS_ON(value if isinstance(value, bool) else None))
        else:
            updates.append(field_key(name)(value))
    return updates
