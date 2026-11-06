"""Which paired-side entity translation keys any code path can produce.

Both directions are checked: a side variant no entity can be given is dead
weight, and a key an entity can be given but that has no translation leaves
Home Assistant naming the entity after its device alone (#711).

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

For the same reason, every translated control on an always-sided platform must
have both side variants, whether or not an offline controller shows it: app
catalogs and runtime capabilities add controls no offline configuration
reaches, and a missing side variant names the control after its device.
Run as a script to list (``--prune`` to delete) the side variants that no code
path reaches, and (``--fill`` to add) the side variants an entity can be given
that have no translation::

    uv run --no-sync python -m tests.entity_translation_reachability [--prune] [--fill]
"""

from __future__ import annotations

import ast
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
from custom_components.adjustable_bed.climate import (
    FOOTWARMING_CLIMATE_DESCRIPTION,
    SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_MOTOMOTION,
    CONF_BLE_DEVICE_NAME,
    CONF_PROTOCOL_VARIANT,
    SUPPORTED_BED_TYPES,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.cover import COVER_DESCRIPTIONS
from custom_components.adjustable_bed.light import (
    ASSUMED_LIGHT_DESCRIPTION,
    LIGHT_DESCRIPTION,
)
from custom_components.adjustable_bed.number import (
    MASSAGE_NUMBER_DESCRIPTIONS,
    NUMBER_DESCRIPTIONS,
)
from custom_components.adjustable_bed.select import MASSAGE_TIMER_DESCRIPTION
from custom_components.adjustable_bed.sensor import (
    MASSAGE_SENSOR_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS,
)
from custom_components.adjustable_bed.switch import SWITCH_DESCRIPTIONS

INTEGRATION = Path(__file__).parents[1] / "custom_components/adjustable_bed"
TRANSLATION_FILES = (INTEGRATION / "strings.json", INTEGRATION / "translations/en.json")
SIDE_SUFFIXES = ("_left", "_right")
BOTH_SUFFIX = "_both"
SIDE_PREFIXES = {"_left": "Left: ", "_right": "Right: ", BOTH_SUFFIX: "Both sides: "}


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
    """Build a controller per bed type, protocol variant and selectable motor count.

    Layouts differ by variant and motor count, so one default controller per
    bed type misses the controls only some layouts have.
    """
    from custom_components.adjustable_bed.config_flow import _motor_count_options
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.validators import get_variants_for_bed_type
    from tests.test_controller_contract import (
        _create_controller_for_bed_type,
        _FactoryCoordinator,
        _make_connected_client,
    )

    controllers: list[BedController] = []
    for bed_type in SUPPORTED_BED_TYPES:
        default = await _create_controller_for_bed_type(bed_type)
        controllers.append(default)
        for motor_count in _motor_count_options(bed_type):
            controller = await _create_controller_for_bed_type(bed_type)
            controller._coordinator.motor_count = motor_count
            controllers.append(controller)
        for variant in get_variants_for_bed_type(bed_type) or ():
            if variant == VARIANT_AUTO:
                # Auto selection needs a live advertisement; the default covers it.
                continue
            for motor_count in _motor_count_options(bed_type, variant):
                coordinator = _FactoryCoordinator()
                coordinator.entry.data = {
                    **default._coordinator.entry.data,
                    CONF_PROTOCOL_VARIANT: variant,
                }
                coordinator.entry.options = {}
                coordinator.entry.entry_id = f"{bed_type}-{variant}-{motor_count}"
                coordinator.motor_count = motor_count
                controllers.append(
                    await create_controller(
                        coordinator,
                        bed_type,
                        variant,
                        _make_connected_client(),
                        device_name=coordinator.entry.data.get(CONF_BLE_DEVICE_NAME),
                    )
                )
    # MotoMotion decodes its panels from the advertised name. This name adds the
    # users, RGB and music panels that the default name lacks.
    controller = await _create_controller_for_bed_type(BED_TYPE_MOTOMOTION)
    controller._coordinator.entry.data = {
        **controller._coordinator.entry.data,
        CONF_BLE_DEVICE_NAME: "SOFA00000MAD00H",
    }
    controllers.append(
        await create_controller(
            controller._coordinator,
            BED_TYPE_MOTOMOTION,
            None,
            _make_connected_client(),
            device_name="SOFA00000MAD00H",
        )
    )
    return controllers


# Each spec class's platform and the position of its translation_key field.
SPEC_PLATFORMS = {
    "MotorControlSpec": ("cover", 1),
    "ControllerButtonSpec": ("button", 4),
    "ControllerSelectSpec": ("select", 1),
    "ControllerNumberSpec": ("number", 1),
    "ControllerStateSensorSpec": ("sensor", 1),
    "ControllerStateBinarySensorSpec": ("binary_sensor", 1),
}


def literal_spec_keys() -> dict[str, set[str]]:
    """Return the translation keys spec constructors state literally, per platform.

    This reaches specs a bed adds only for a capability it reports at runtime,
    which no offline controller configuration exposes.
    """
    keys: dict[str, set[str]] = {}
    for path in INTEGRATION.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in SPEC_PLATFORMS:
                continue
            platform, position = SPEC_PLATFORMS[name]
            values = [kw.value for kw in node.keywords if kw.arg == "translation_key"]
            if len(node.args) > position:
                values.append(node.args[position])
            for value in values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    keys.setdefault(platform, set()).add(value.value)
    return keys


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


# Platforms whose every entity takes its side's suffix on a one-address pair.
SIDED_PLATFORMS = ("button", "cover", "number", "select", "switch", "light", "climate")


def _translated_bases(strings: dict[str, dict[str, object]], platform: str) -> set[str]:
    """Return one platform's translated keys, without their side variants."""
    keys = strings.get(platform, {})
    return {
        key
        for key in keys
        if not any(
            key.endswith(suffix) and key.removesuffix(suffix) in keys for suffix in SIDE_PREFIXES
        )
    }


def _combined_bases(
    controllers: Iterable[BedController], strings: dict[str, dict[str, object]]
) -> dict[str, set[str]]:
    """Return the per-platform bases a paired parent's ``_both`` entity extends.

    A combined motor button is named after its cover, and some covers exist only
    for a layout or motor a bed reports at runtime, so every translated cover
    counts as a possible combined motor.
    """
    controllers = tuple(controllers)
    motor_keys = {
        spec.translation_key
        for controller in (*controllers, *_motion_bed_controllers())
        for spec in controller.motor_control_specs
    } | _translated_bases(strings, "cover")
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
    combined = _combined_bases(controllers, strings)
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


def required_keys(
    controllers: Iterable[BedController], strings: dict[str, dict[str, object]]
) -> dict[str, set[str]]:
    """Return the translation keys entities can be given, per platform.

    Every key code states needs its base. Every base on an always-sided
    platform, and every sided sensor, needs both side variants; every combined
    base needs its ``_both`` variant. Controller-state sensors keep their spec
    key on every side, so only their base is needed.
    """
    controllers = tuple(controllers)
    specs = _spec_keys(controllers)
    for platform, keys in literal_spec_keys().items():
        specs.setdefault(platform, set()).update(keys)
    sided_specs = {
        platform: keys
        for platform, keys in specs.items()
        if platform not in ("sensor", "binary_sensor")
    }
    sided_specs["cover"] |= {
        spec.translation_key
        for controller in _motion_bed_controllers()
        for spec in controller.motor_control_specs
    }
    descriptions = {
        # Product actions all share one translation, named by a placeholder.
        "button": _description_keys(BUTTON_DESCRIPTIONS) | {"product_action"},
        "light": _description_keys((LIGHT_DESCRIPTION, ASSUMED_LIGHT_DESCRIPTION)),
        "climate": _description_keys(
            (SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION, FOOTWARMING_CLIMATE_DESCRIPTION)
        ),
        "select": _description_keys((MASSAGE_TIMER_DESCRIPTION,)),
        "cover": _description_keys(COVER_DESCRIPTIONS),
        "number": _description_keys((*NUMBER_DESCRIPTIONS, *MASSAGE_NUMBER_DESCRIPTIONS)),
        "switch": _description_keys(SWITCH_DESCRIPTIONS),
        "sensor": _description_keys((*SENSOR_DESCRIPTIONS, *MASSAGE_SENSOR_DESCRIPTIONS)),
        "binary_sensor": _description_keys(BINARY_SENSOR_DESCRIPTIONS),
    }
    required: dict[str, set[str]] = {}
    for source in (sided_specs, descriptions):
        for platform, keys in source.items():
            required.setdefault(platform, set()).update(
                f"{key}{suffix}"
                for key in keys
                if key is not None
                for suffix in ("", *SIDE_SUFFIXES)
            )
    for platform in ("sensor", "binary_sensor"):
        required[platform].update(key for key in specs[platform] if key is not None)
    for platform in SIDED_PLATFORMS:
        required.setdefault(platform, set()).update(
            f"{base}{suffix}"
            for base in _translated_bases(strings, platform)
            if not base.endswith(SIDE_SUFFIXES)
            for suffix in SIDE_SUFFIXES
        )
    for platform, bases in _combined_bases(controllers, strings).items():
        required.setdefault(platform, set()).update(
            f"{base}{suffix}" for base in bases for suffix in ("", BOTH_SUFFIX)
        )
    return required


def missing_translations(
    strings: dict[str, dict[str, object]],
    controllers: Iterable[BedController],
) -> dict[str, set[str]]:
    """Return keys an entity can be given that have no translation, per platform."""
    missing: dict[str, set[str]] = {}
    for platform, keys in required_keys(controllers, strings).items():
        absent = keys - strings.get(platform, {}).keys()
        if absent:
            missing[platform] = absent
    return missing


def _side_variant(base: dict[str, object], suffix: str) -> dict[str, object]:
    """Return a side variant of one translation, named after its side."""
    return {**base, "name": f"{SIDE_PREFIXES[suffix]}{base['name']}"}


def _fill(entity: dict[str, dict[str, object]], missing: dict[str, set[str]]) -> None:
    """Add each missing translation that a translated base determines.

    A motor's up/down button is named after its cover, and a side variant
    after its base. Other missing bases need a name written by hand.
    """
    buttons = entity["button"]
    for key in missing.get("button", ()):
        motor, _, direction = key.rpartition("_")
        cover = entity["cover"].get(motor)
        if direction in ("up", "down") and isinstance(cover, dict) and "name" in cover:
            buttons[key] = {"name": f"{cover['name']} {direction.capitalize()}"}
    for platform, keys in missing.items():
        strings = entity[platform]
        added = {}
        for key in keys - strings.keys():
            for suffix in SIDE_PREFIXES:
                base = strings.get(key.removesuffix(suffix)) if key.endswith(suffix) else None
                if isinstance(base, dict) and "name" in base:
                    added[key] = _side_variant(base, suffix)
                    break
        entity[platform] = _insert_after_bases(strings, added)


def _insert_after_bases(strings: dict[str, object], added: dict[str, object]) -> dict[str, object]:
    """Insert each added variant after its base's existing entries, in side order."""
    rank = {suffix: order for order, suffix in enumerate(SIDE_PREFIXES)}

    def split(key: str) -> tuple[str, int]:
        for suffix in SIDE_PREFIXES:
            if key.endswith(suffix) and key.removesuffix(suffix) in strings:
                return key.removesuffix(suffix), rank[suffix]
        return key, -1

    pending: dict[str, list[str]] = {}
    for key in added:
        pending.setdefault(split(key)[0], []).append(key)
    keys = list(strings)
    result: dict[str, object] = {}
    for index, key in enumerate(keys):
        result[key] = strings[key]
        base = split(key)[0]
        if index + 1 == len(keys) or split(keys[index + 1])[0] != base:
            for variant in sorted(pending.pop(base, ()), key=lambda variant: split(variant)[1]):
                result[variant] = added[variant]
    return result


def _report(title: str, keys_by_platform: dict[str, set[str]]) -> None:
    print(title)
    for platform, keys in sorted(keys_by_platform.items()):
        print(f"{platform}: {len(keys)}")
        for key in sorted(keys):
            print(f"  {key}")
    print(f"total: {sum(map(len, keys_by_platform.values()))}")


def main(argv: list[str]) -> None:
    controllers = asyncio.run(factory_controllers())
    unreachable = unreachable_side_variants(entity_strings(), controllers)
    missing = missing_translations(entity_strings(), controllers)
    _report("unreachable:", unreachable)
    _report("missing:", missing)
    if "--prune" not in argv and "--fill" not in argv:
        return
    for path in TRANSLATION_FILES:
        data = json.loads(path.read_text())
        if "--prune" in argv:
            for platform, keys in unreachable.items():
                for key in keys:
                    del data["entity"][platform][key]
        if "--fill" in argv:
            _fill(data["entity"], missing)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
