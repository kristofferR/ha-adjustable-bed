"""Which entity translation keys code can give an entity.

A key an entity can be given that has no translation leaves Home Assistant
naming the entity after its device alone (#711). The keys come from every
offline controller variant's specs, including each side of a single-address
pair, and from the platforms' own entity descriptions.
"""

from __future__ import annotations

import json
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
                if bed_type == "dorsal":
                    coordinator.entry.data["product_type"] = "A3RM" if variant == "restored" else ""
                    coordinator.entry.data[CONF_BLE_DEVICE_NAME] = "QRRM0001"
                if bed_type == "instant_comfort":
                    coordinator.entry.data["product_type"] = "two" if variant == "anm5" else "pf4"
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
    from custom_components.adjustable_bed.beds.enso2.controller import Enso2Controller

    enso2 = next(controller for controller in controllers if isinstance(controller, Enso2Controller))
    enso2._light_present = True
    for layout in ("ONRM", "A3RM", "GVRM", "R2RM"):
        legacy = await _create_controller_for_bed_type("enso2", layout)
        assert isinstance(legacy, Enso2Controller)
        legacy._raw = True
        controllers.append(legacy)
    from custom_components.adjustable_bed.beds.instant_comfort.air import InstantComfortAir
    from custom_components.adjustable_bed.profiles.instant_comfort import (
        PROFILES as INSTANT_PROFILES,
    )
    controllers.append(InstantComfortAir(_FactoryCoordinator(), INSTANT_PROFILES["anm5"], "four"))
    # Both Comfy (komfyD and ComfyDS) product routes: the dual route adds the local side selector.
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
    # Bedgear's exact names select single-actuator, dynamic-zone and alarm controls.
    from custom_components.adjustable_bed.beds.bedgear.controller import BedgearController
    bedgear = await _create_controller_for_bed_type("bedgear")
    for pair in ("E1", "44", "97", "15", "35"):
        controllers.append(BedgearController(bedgear._coordinator, name="HHC00000" + pair + "DE0X"))
    from custom_components.adjustable_bed.profiles.l2motion import L2MotionProfile
    for pair in ("E1", "44", "97", "15", "35", "01"):
        for mode in ("E", "M", "D"):
            selected = "HHC00000" + pair + "D" + mode + "0X"
            controllers.append(BedgearController(bedgear._coordinator, name=selected, profile=L2MotionProfile(selected)))
    from custom_components.adjustable_bed.beds.bedgear.moodbase import MoodBaseController
    from custom_components.adjustable_bed.profiles.moodbase import MoodBaseProfile

    for name in ("HHC00000E1DE0X", "HHC0000001DM0X", "HHC0000015BM0H"):
        controllers.append(MoodBaseController(_FactoryCoordinator(), profile=MoodBaseProfile(name)))
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
    from custom_components.adjustable_bed.beds.cheerssleep.controller import CheersSleepController
    from custom_components.adjustable_bed.profiles.cheerssleep import MODELS as CHEERSSLEEP_MODELS
    for model in CHEERSSLEEP_MODELS.values():
        controllers.append(CheersSleepController(_FactoryCoordinator(), model))
    # Every GM Control product and RMControl product lists its own app catalog.
    from custom_components.adjustable_bed.beds.gmmotor.controller import GmmotorController
    from custom_components.adjustable_bed.beds.gmmotor.profiles import profile_choices
    from custom_components.adjustable_bed.beds.rmcontrol.controller import RmcontrolController
    from custom_components.adjustable_bed.beds.rmcontrol.profiles import RICHMAT_PRODUCT_CODES

    for product in profile_choices():
        controllers.append(GmmotorController(_FactoryCoordinator(), profile=product))
    for product in RICHMAT_PRODUCT_CODES:
        if product not in ("FWRM", "WFRM"):  # The desk protocol is its own controller.
            controllers.append(RmcontrolController(_FactoryCoordinator(), product))
    # A Sleep Number MCR foundation reports its per-side motors once connected.
    controller = await _create_controller_for_bed_type(BED_TYPE_SLEEP_NUMBER_MCR)
    assert isinstance(controller, SleepNumberMcrController)
    controller._foundation_features = FoundationFeatures(2, True, True, True, True, "360", "FF3")
    controllers.append(controller)
    return controllers


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
        ("switch", controller.controller_switch_specs),
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

