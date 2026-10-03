"""Which paired-side entity translation keys any code path can produce.

Side variants are where unused strings accumulate, so this models exactly how
each platform derives them:

* ``_left``/``_right``: a single-address paired side view appends its side via
  ``entity_translation_key``. Every platform does so, except controller-state
  sensors and binary sensors, which use their spec's key verbatim.
* ``_both``: only the paired parent's combined controls carry it: the stop
  button, combined preset/action and per-motor buttons, and combined position
  sliders. No other platform has a "both sides" entity.

Unsuffixed keys, and ``_left``/``_right`` variants on always-sided platforms,
are not judged: confirming their base would need every app profile's specs.
Run as a script to list (``--prune`` to delete) the side variants that no code
path reaches::

    uv run --no-sync python -m tests.entity_translation_reachability [--prune]
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

from homeassistant.helpers.entity import EntityDescription

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.binary_sensor import BINARY_SENSOR_DESCRIPTIONS
from custom_components.adjustable_bed.button import BUTTON_DESCRIPTIONS
from custom_components.adjustable_bed.const import SUPPORTED_BED_TYPES
from custom_components.adjustable_bed.sensor import (
    MASSAGE_SENSOR_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS,
)

INTEGRATION = Path(__file__).parents[1] / "custom_components/adjustable_bed"
TRANSLATION_FILES = (INTEGRATION / "strings.json", INTEGRATION / "translations/en.json")
SIDE_SUFFIXES = ("_left", "_right")
BOTH_SUFFIX = "_both"


def entity_strings(path: Path = TRANSLATION_FILES[0]) -> dict[str, dict[str, object]]:
    """Return the ``entity`` section of one translation file."""
    return json.loads(path.read_text())["entity"]


def literal_keys() -> set[str]:
    """Return every snake_case string literal in the integration source.

    A literal such as ``"bed_presence_left"`` or ``"elevate_both"`` is a key a
    description or spec states verbatim, whatever its suffix looks like.
    """
    source = "\n".join(path.read_text() for path in INTEGRATION.rglob("*.py"))
    return set(re.findall(r"""["']([a-z0-9_]+)["']""", source))


async def factory_controllers() -> list[BedController]:
    """Build one controller per supported bed type through the factory."""
    from tests.test_controller_contract import _create_controller_for_bed_type

    return [await _create_controller_for_bed_type(bed_type) for bed_type in SUPPORTED_BED_TYPES]


def _motion_bed_controllers() -> list[BedController]:
    """Motion Bed motor specs depend on the movement layout."""
    from tests.test_motion_bed_entity_keys import HOME_MOVEMENTS, controller

    return [controller(movement_override=movement) for movement in HOME_MOVEMENTS]


def _description_keys(descriptions: Iterable[EntityDescription]) -> set[str]:
    return {description.translation_key or description.key for description in descriptions}


def _spec_keys(controllers: Iterable[BedController]) -> dict[str, set[str]]:
    """Return the translation keys controller specs state, per platform."""
    keys: dict[str, set[str]] = {}
    for controller in controllers:
        for platform, specs in (
            ("cover", controller.motor_control_specs),
            ("button", controller.controller_button_specs),
            ("select", controller.controller_select_specs),
            ("number", (*controller.controller_number_specs, *controller.position_number_specs)),
            ("sensor", controller.controller_state_sensor_specs),
            ("binary_sensor", controller.controller_state_binary_sensor_specs),
        ):
            keys.setdefault(platform, set()).update(spec.translation_key for spec in specs)
    return keys


def _combined_bases(controllers: Iterable[BedController]) -> dict[str, set[str]]:
    """Return the per-platform bases a paired parent's ``_both`` entity extends."""
    controllers = tuple(controllers)
    motor_keys = {
        spec.translation_key
        for controller in (*controllers, *_motion_bed_controllers())
        for spec in controller.motor_control_specs
    }
    buttons = {
        description.translation_key or description.key
        for description in BUTTON_DESCRIPTIONS
        if not description.is_coordinator_action
        and description.press_fn is not None
        and description.key != "stop"
    }
    buttons |= {"massage_timer_step"}
    buttons |= {f"{key}_{direction}" for key in motor_keys for direction in ("up", "down")}
    positions = {
        spec.translation_key for controller in controllers for spec in controller.position_number_specs
    }
    return {"button": buttons, "number": positions}


def unreachable_side_variants(
    strings: dict[str, dict[str, object]],
    controllers: Iterable[BedController],
) -> dict[str, set[str]]:
    """Return side-variant keys no entity can be given, per platform."""
    controllers = tuple(controllers)
    exact = _spec_keys(controllers)
    literals = literal_keys()
    combined = _combined_bases(controllers)
    # Only these sensors are sided; controller-state sensors keep their spec key.
    sided_sensors = {
        "sensor": _description_keys((*SENSOR_DESCRIPTIONS, *MASSAGE_SENSOR_DESCRIPTIONS)),
        "binary_sensor": _description_keys(BINARY_SENSOR_DESCRIPTIONS),
    }
    unreachable: dict[str, set[str]] = {}
    for platform, keys in strings.items():
        for key in keys:
            if key in literals or key in exact.get(platform, ()):
                continue
            if key.endswith(BOTH_SUFFIX):
                reachable = key.removesuffix(BOTH_SUFFIX) in combined.get(platform, ())
            elif key.endswith(SIDE_SUFFIXES) and platform in sided_sensors:
                reachable = key.rsplit("_", 1)[0] in sided_sensors[platform]
            else:
                # Every other entity is sided; its unsuffixed base is not judged.
                continue
            if not reachable:
                unreachable.setdefault(platform, set()).add(key)
    return unreachable


def main(argv: list[str]) -> None:
    controllers = asyncio.run(factory_controllers())
    unreachable = unreachable_side_variants(entity_strings(), controllers)
    for platform, keys in sorted(unreachable.items()):
        print(f"{platform}: {len(keys)}")
        for key in sorted(keys):
            print(f"  {key}")
    print(f"total: {sum(map(len, unreachable.values()))}")
    if "--prune" not in argv:
        return
    for path in TRANSLATION_FILES:
        data = json.loads(path.read_text())
        for platform, keys in unreachable.items():
            for key in keys:
                del data["entity"][platform][key]
        path.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
