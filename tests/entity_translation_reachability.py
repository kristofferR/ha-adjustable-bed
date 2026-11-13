"""Which entity translation keys code can give an entity.

Both directions are checked: a side-suffixed key no entity can be given is dead
weight, and a key an entity can be given but that has no translation leaves
Home Assistant naming the entity after its device alone (#711).

Paired side devices carry their side in the device name, and combined controls
sit on the parent device, so no entity appends ``_left``, ``_right`` or
``_both`` to its key. A key with one of those suffixes is reachable only when
code states it: a literal, or a spec or description a bed builds for a side it
controls natively (such as Sleep Number's per-side climate). Unsuffixed keys
are not judged as dead weight: confirming every base would need every app
profile's specs.

Run as a script to list both::

    uv run --no-sync python -m tests.entity_translation_reachability
"""

from __future__ import annotations

import ast
import asyncio
import json
import re
from collections.abc import Iterable
from pathlib import Path

from homeassistant.helpers.entity import EntityDescription

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.binary_sensor import (
    BINARY_SENSOR_DESCRIPTIONS,
    _build_side_presence_description,
)
from custom_components.adjustable_bed.button import BUTTON_DESCRIPTIONS
from custom_components.adjustable_bed.climate import (
    FOOTWARMING_CLIMATE_DESCRIPTION,
    SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION,
    _build_side_footwarming_climate_description,
    _build_side_thermal_climate_description,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_MOTOMOTION,
    BED_TYPE_SLEEP_NUMBER_MCR,
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
    SLEEP_NUMBER_SETTING_LEFT_DESCRIPTION,
    SLEEP_NUMBER_SETTING_RIGHT_DESCRIPTION,
)
from custom_components.adjustable_bed.select import (
    FOOTWARMING_TIMER_LEFT_DESCRIPTION,
    FOOTWARMING_TIMER_RIGHT_DESCRIPTION,
    FOUNDATION_PRESET_LEFT_DESCRIPTION,
    FOUNDATION_PRESET_RIGHT_DESCRIPTION,
    MASSAGE_TIMER_DESCRIPTION,
    THERMAL_TIMER_LEFT_DESCRIPTION,
    THERMAL_TIMER_RIGHT_DESCRIPTION,
)
from custom_components.adjustable_bed.sensor import (
    MASSAGE_SENSOR_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS,
)
from custom_components.adjustable_bed.switch import SWITCH_DESCRIPTIONS

INTEGRATION = Path(__file__).parents[1] / "custom_components/adjustable_bed"
TRANSLATION_FILES = (INTEGRATION / "strings.json", INTEGRATION / "translations/en.json")
SIDE_SUFFIXES = ("_left", "_right", "_both")


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
    from custom_components.adjustable_bed.beds.comfort_enhancement3.controller import (
        ComfortEnhancement3Controller,
    )
    from custom_components.adjustable_bed.beds.sleep_number.mcr import SleepNumberMcrController
    from custom_components.adjustable_bed.beds.sleep_number.mcr_protocol import (
        FoundationFeatures,
    )
    from custom_components.adjustable_bed.config_flow import _motor_count_options
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.profiles.comfort_enhancement3 import REMOTES
    from custom_components.adjustable_bed.validators import get_variants_for_bed_type
    from tests.test_controller_contract import (
        _create_controller_for_bed_type,
        _FactoryCoordinator,
        _make_connected_client,
    )
    controllers: list[BedController] = []
    controllers.extend(ComfortEnhancement3Controller(_FactoryCoordinator(), i) for i in range(len(REMOTES)))
    from custom_components.adjustable_bed.beds.symphony.controller import SymphonyController
    from custom_components.adjustable_bed.profiles.symphony import PRODUCTS, SymphonyProfile

    for product in PRODUCTS.values():
        for selector in (4, 9):
            coordinator = _FactoryCoordinator()
            controllers.append(SymphonyController(coordinator, SymphonyProfile(product, selector)))
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
    # Both row084 product routes: the dual route adds the local side selector.
    for bed_type in ("komfyd", "comfyds"):
        controller = await _create_controller_for_bed_type(bed_type)
        controller._coordinator.entry.data = {**controller._coordinator.entry.data, "product_type": 130}
        from custom_components.adjustable_bed.beds.kaidi.comfy import ComfyController
        controllers.append(ComfyController(controller._coordinator))
    # Rize's extended product adds motion actions and mode4 to the basic panel.
    from custom_components.adjustable_bed.beds.kaidi.rize import RizeController
    from custom_components.adjustable_bed.const import BED_TYPE_RIZE, CONF_PRODUCT_TYPE

    controller = await _create_controller_for_bed_type(BED_TYPE_RIZE)
    controller._coordinator.entry.data = {**controller._coordinator.entry.data, CONF_PRODUCT_TYPE: 140}
    controllers.append(RizeController(controller._coordinator))
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
    # Smart Sleep's legacy model gates add AI-zero and flexible-wake state.
    from custom_components.adjustable_bed.beds.smart_sleep.controller import SmartSleepController
    from custom_components.adjustable_bed.profiles.smart_sleep import PROFILES as SMART_SLEEP
    for model in (8, 67):
        controllers.append(SmartSleepController(_FactoryCoordinator(), SMART_SLEEP["p1"], model))
    # A Sleep Number MCR foundation reports its per-side motors once connected.
    controller = await _create_controller_for_bed_type(BED_TYPE_SLEEP_NUMBER_MCR)
    assert isinstance(controller, SleepNumberMcrController)
    controller._foundation_features = FoundationFeatures(2, True, True, True, True, "360", "FF3")
    controllers.append(controller)
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


def _native_side_keys(descriptions: Iterable[EntityDescription]) -> set[str]:
    """Return natively sided keys and the base each takes on its single-address side device."""
    keys = _description_keys(descriptions)
    return keys | {
        key.removesuffix(suffix) for key in keys for suffix in ("_left", "_right") if key.endswith(suffix)
    }


def _spec_keys(controllers: Iterable[BedController]) -> dict[str, set[str]]:
    """Return the translation keys controller specs state, per platform.

    A controller bound to one side of a single-address pair names its specs for
    that side's device, so each side binding counts too.
    """
    keys: dict[str, set[str]] = {}
    for controller in controllers:
        _add_spec_keys(keys, controller)
        if controller.supports_single_address_pairing:
            for side in ("left", "right"):
                with controller.side_scope(side):
                    _add_spec_keys(keys, controller)
    return keys


def _add_spec_keys(keys: dict[str, set[str]], controller: BedController) -> None:
    for platform, specs in (
        ("cover", controller.motor_control_specs),
        ("button", controller.controller_button_specs),
        ("select", controller.controller_select_specs),
        ("number", (*controller.controller_number_specs, *controller.position_number_specs)),
        ("sensor", controller.controller_state_sensor_specs),
        ("binary_sensor", controller.controller_state_binary_sensor_specs),
    ):
        keys.setdefault(platform, set()).update(
            spec.translation_key for spec in specs if spec.translation_key is not None
        )


def _is_side_variant(key: str, keys: Iterable[str]) -> bool:
    """Return whether a key is a base in ``keys`` with a side suffix appended."""
    return any(key.endswith(suffix) and key.removesuffix(suffix) in keys for suffix in SIDE_SUFFIXES)


def required_keys(
    controllers: Iterable[BedController], strings: dict[str, dict[str, object]]
) -> dict[str, set[str]]:
    """Return the translation keys entities can be given, per platform.

    A paired parent's combined motor button is named after its cover's key plus
    the direction. Some covers exist only for a layout or motor a bed reports at
    runtime, so every translated cover counts as a possible combined motor.
    """
    required = _spec_keys(controllers)
    required["cover"] |= {
        spec.translation_key
        for controller in _motion_bed_controllers()
        for spec in controller.motor_control_specs
    }
    for platform, keys in literal_spec_keys().items():
        required.setdefault(platform, set()).update(keys)
    sides = ("left", "right")
    descriptions = {
        # Product actions all share one translation, named by a placeholder.
        "button": _description_keys(BUTTON_DESCRIPTIONS) | {"product_action"},
        "light": _description_keys((LIGHT_DESCRIPTION, ASSUMED_LIGHT_DESCRIPTION)),
        "climate": _description_keys(
            (SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION, FOOTWARMING_CLIMATE_DESCRIPTION)
        )
        | _native_side_keys(
            (
                *map(_build_side_thermal_climate_description, sides),
                *map(_build_side_footwarming_climate_description, sides),
            )
        ),
        "select": _description_keys((MASSAGE_TIMER_DESCRIPTION,))
        | _native_side_keys(
            (
                THERMAL_TIMER_LEFT_DESCRIPTION,
                THERMAL_TIMER_RIGHT_DESCRIPTION,
                FOOTWARMING_TIMER_LEFT_DESCRIPTION,
                FOOTWARMING_TIMER_RIGHT_DESCRIPTION,
                FOUNDATION_PRESET_LEFT_DESCRIPTION,
                FOUNDATION_PRESET_RIGHT_DESCRIPTION,
            )
        ),
        "cover": _description_keys(COVER_DESCRIPTIONS),
        "number": _description_keys((*NUMBER_DESCRIPTIONS, *MASSAGE_NUMBER_DESCRIPTIONS))
        | _native_side_keys(
            (SLEEP_NUMBER_SETTING_LEFT_DESCRIPTION, SLEEP_NUMBER_SETTING_RIGHT_DESCRIPTION)
        ),
        "switch": _description_keys(SWITCH_DESCRIPTIONS),
        "sensor": _description_keys((*SENSOR_DESCRIPTIONS, *MASSAGE_SENSOR_DESCRIPTIONS)),
        "binary_sensor": _description_keys(BINARY_SENSOR_DESCRIPTIONS)
        | _native_side_keys(map(_build_side_presence_description, sides)),
    }
    for platform, keys in descriptions.items():
        required.setdefault(platform, set()).update(keys)
    # A natively sided motor differs between sides, so it is never combined.
    covers = required["cover"] | strings.get("cover", {}).keys()
    required["button"] |= {
        f"{motor}_{direction}"
        for motor in covers
        if not _is_side_variant(motor, covers)
        for direction in ("up", "down")
    }
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


def unreachable_side_keys(
    strings: dict[str, dict[str, object]],
    controllers: Iterable[BedController],
) -> dict[str, set[str]]:
    """Return side-suffixed copies of a translated base that no entity is given."""
    required = required_keys(controllers, strings)
    literals = literal_keys()
    unreachable: dict[str, set[str]] = {}
    for platform, keys in strings.items():
        for key in keys:
            if (
                _is_side_variant(key, keys)
                and key not in literals
                and key not in required.get(platform, ())
            ):
                unreachable.setdefault(platform, set()).add(key)
    return unreachable


def _report(title: str, keys_by_platform: dict[str, set[str]]) -> None:
    print(title)
    for platform, keys in sorted(keys_by_platform.items()):
        print(f"{platform}: {len(keys)}")
        for key in sorted(keys):
            print(f"  {key}")
    print(f"total: {sum(map(len, keys_by_platform.values()))}")


def main() -> None:
    controllers = asyncio.run(factory_controllers())
    _report("unreachable:", unreachable_side_keys(entity_strings(), controllers))
    _report("missing:", missing_translations(entity_strings(), controllers))


if __name__ == "__main__":
    main()
