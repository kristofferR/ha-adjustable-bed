"""Where each entity the integration can create sits in the Lovelace card.

Builds the entities offline controllers and the static descriptions produce and
reads the placement each publishes. The frontend tests attach these placements
to their mock entities by translation key, so the card is tested against what
the integration really publishes.

Regenerate the fixture after adding or moving an entity::

    uv run --no-sync python -m tests.card_placements
"""

from __future__ import annotations

import ast
import asyncio
import copy
import json
from collections.abc import Iterable, Iterator
from dataclasses import fields, replace
from pathlib import Path
from unittest.mock import MagicMock

from homeassistant.helpers.entity import Entity

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.entity_specs import MotorControlSpec, ProductButtonSpec
from custom_components.adjustable_bed.beds.sleeptracker import protocol as sleeptracker_protocol
from custom_components.adjustable_bed.binary_sensor import (
    BINARY_SENSOR_DESCRIPTIONS,
    AdjustableBedConnectionSensor,
    AdjustableBedControllerStateBinarySensor,
    AdjustableBedPresenceSensor,
)
from custom_components.adjustable_bed.button import (
    BUTTON_DESCRIPTIONS,
    AdjustableBedButton,
    AdjustableBedProductButton,
    ControllerActionButton,
    PairedBedCombinedButton,
    PairedBedCombinedMotorButton,
    PairedBedStopButton,
)
from custom_components.adjustable_bed.climate import (
    FOOTWARMING_CLIMATE_DESCRIPTION,
    SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION,
    AdjustableBedClimate,
    _build_side_footwarming_climate_description,
    _build_side_thermal_climate_description,
)
from custom_components.adjustable_bed.cover import (
    COVER_DESCRIPTIONS,
    AdjustableBedCover,
    _build_cover_description,
)
from custom_components.adjustable_bed.entity import PlacedInCard
from custom_components.adjustable_bed.light import (
    LIGHT_DESCRIPTION,
    AdjustableBedAssumedLight,
    AdjustableBedLight,
    AdjustableBedOnOffLight,
)
from custom_components.adjustable_bed.number import (
    FAN_LEVEL_DESCRIPTION,
    LIGHT_LEVEL_DESCRIPTION,
    MASSAGE_NUMBER_DESCRIPTIONS,
    NUMBER_DESCRIPTIONS,
    SLEEP_NUMBER_SETTING_DESCRIPTION,
    SLEEP_NUMBER_SETTING_LEFT_DESCRIPTION,
    SLEEP_NUMBER_SETTING_RIGHT_DESCRIPTION,
    AdjustableBedControllerNumber,
    AdjustableBedLevelNumber,
    AdjustableBedMassageNumber,
    AdjustableBedPositionNumber,
    AdjustableBedSideStateNumber,
    AdjustableBedSleepNumberSettingNumber,
    PairedBedCombinedPositionNumber,
    _build_position_description,
)
from custom_components.adjustable_bed.position_estimate_entities import (
    EstimatedPositionNumber,
    RemoteUsedButton,
    SavedPositionButton,
    SavedPositionsSensor,
    SetReferenceButton,
)
from custom_components.adjustable_bed.position_estimate_services import ESTIMATED_MOTORS
from custom_components.adjustable_bed.select import (
    FOOTWARMING_TIMER_DESCRIPTION,
    FOOTWARMING_TIMER_LEFT_DESCRIPTION,
    FOOTWARMING_TIMER_RIGHT_DESCRIPTION,
    FOUNDATION_PRESET_LEFT_DESCRIPTION,
    FOUNDATION_PRESET_RIGHT_DESCRIPTION,
    LIGHT_TIMER_DESCRIPTION,
    MASSAGE_TIMER_DESCRIPTION,
    THERMAL_TIMER_DESCRIPTION,
    THERMAL_TIMER_LEFT_DESCRIPTION,
    THERMAL_TIMER_RIGHT_DESCRIPTION,
    AdjustableBedControllerSelect,
    AdjustableBedControllerStateSelect,
    AdjustableBedMassageTimerSelect,
    AdjustableBedSideStateSelect,
)
from custom_components.adjustable_bed.sensor import (
    MASSAGE_SENSOR_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS,
    AdjustableBedAngleSensor,
    AdjustableBedControllerStateSensor,
    AdjustableBedMassageSensor,
)
from custom_components.adjustable_bed.switch import SWITCH_DESCRIPTIONS, AdjustableBedSwitch
from tests.entity_translation_reachability import (
    INTEGRATION,
    SPEC_PLATFORMS,
    _motion_bed_controllers,
    factory_controllers,
)

FIXTURE = Path(__file__).parent / "fixtures/card_placements.json"


def _runtime() -> MagicMock:
    runtime = MagicMock()
    runtime.entity_side = None
    runtime.capability_controller = None
    return runtime


def motor_entities(specs: Iterable[MotorControlSpec]) -> list[Entity]:
    """Build each motor's cover and its combined both-sides buttons."""
    runtime = _runtime()
    entities: list[Entity] = []
    for spec in specs:
        entities.append(AdjustableBedCover(runtime, _build_cover_description(spec)))
        # A natively sided motor differs between sides, so it is never combined.
        if not spec.translation_key.endswith(("_left", "_right")):
            entities.extend(
                PairedBedCombinedMotorButton(runtime, spec, d) for d in ("up", "down")
            )
    return entities


def runtime_variants(controllers: Iterable[BedController]) -> Iterator[BedController]:
    """Yield each controller, plus copies in states only a live bed reports.

    Some controls exist only for a reported model, layout or page, which no
    offline configuration reaches.
    """
    from custom_components.adjustable_bed.beds.paramount.controller import ParamountController
    from custom_components.adjustable_bed.beds.ruf_richmat.controller import RufRichmatController
    from custom_components.adjustable_bed.beds.sleeptracker.controller import SleeptrackerController
    from custom_components.adjustable_bed.beds.sleepys.app import (
        _APP_STATE_FIELDS_BY_SELECTOR,
        SleepysEliteAppController,
    )
    from custom_components.adjustable_bed.beds.smart_comfort.controller import (
        SmartComfortController,
    )
    from custom_components.adjustable_bed.beds.starcode.abm5_4 import (
        _POSITIVE_SELECTORS,
        StarcodeAbm5_4Controller,
    )
    from custom_components.adjustable_bed.beds.vibradorm.app import VibradormAppController
    from custom_components.adjustable_bed.beds.vmatbasic.controller import VMatBasicController
    from custom_components.adjustable_bed.profiles import vmatbasic as vmat_profiles

    def variant(controller: BedController, **attributes: object) -> BedController:
        clone = copy.copy(controller)
        for name, value in attributes.items():
            setattr(clone, name, value)
        return clone

    for controller in controllers:
        yield controller
        if isinstance(controller, ParamountController):
            yield variant(controller, _mask=31, _height_bounds=(20, 70))
        elif isinstance(controller, SleeptrackerController):
            for model in sleeptracker_protocol.MODELS.values():
                for restricted in (False, True):
                    yield variant(controller, _model=model, _restricted=restricted)
        elif isinstance(controller, VMatBasicController):
            for profile in vmat_profiles.PROFILES.values():
                yield variant(controller, profile=profile)
        elif isinstance(controller, VibradormAppController):
            # The VMAT app profile also syncs both sides.
            profile = replace(
                controller.profile, app_profile="vmat", rgb=True, massage=True, floor_light=True
            )
            yield variant(controller, profile=profile)
        elif isinstance(controller, SleepysEliteAppController):
            for selector in _APP_STATE_FIELDS_BY_SELECTOR:
                yield variant(controller, selector=selector)
        elif isinstance(controller, StarcodeAbm5_4Controller):
            for selector in _POSITIVE_SELECTORS:
                yield variant(controller, command_selector=selector)
        elif isinstance(controller, SmartComfortController):
            yield variant(controller, _model=0x89, _flags=(7, 7, 7), _ready=True)
        elif isinstance(controller, RufRichmatController):
            yield variant(controller, _normal_ready=True)


def controller_entities(controllers: Iterable[BedController]) -> list[Entity]:
    """Build the entities every controller's specs declare."""
    runtime = _runtime()
    entities: list[Entity] = []
    for controller in runtime_variants(controllers):
        entities.extend(motor_entities(controller.motor_control_specs))
        entities.extend(
            AdjustableBedPositionNumber(runtime, _build_position_description(spec))
            for spec in controller.position_number_specs
        )
        entities.extend(
            AdjustableBedProductButton(runtime, spec)
            if isinstance(spec, ProductButtonSpec)
            else ControllerActionButton(runtime, spec)
            for spec in controller.controller_button_specs
        )
        entities.extend(
            AdjustableBedControllerSelect(runtime, spec)
            for spec in controller.controller_select_specs
        )
        entities.extend(
            AdjustableBedControllerNumber(runtime, spec)
            for spec in controller.controller_number_specs
        )
        entities.extend(
            AdjustableBedControllerStateSensor(runtime, spec)
            for spec in controller.controller_state_sensor_specs
        )
        entities.extend(
            AdjustableBedControllerStateBinarySensor(runtime, spec)
            for spec in controller.controller_state_binary_sensor_specs
        )
    return entities


def description_entities() -> list[Entity]:
    """Build every entity a static description or a fixed class declares."""
    runtime = _runtime()
    sides = ("left", "right")
    presence = BINARY_SENSOR_DESCRIPTIONS[1]
    return [
        *(AdjustableBedButton(runtime, description) for description in BUTTON_DESCRIPTIONS),
        *(PairedBedCombinedButton(runtime, description) for description in BUTTON_DESCRIPTIONS),
        PairedBedStopButton(runtime),
        # Product actions come from the selected product's catalog.
        AdjustableBedProductButton(runtime, ProductButtonSpec("action", "Action", MagicMock())),
        *(
            entity
            for motor in ESTIMATED_MOTORS
            for entity in (
                EstimatedPositionNumber(runtime, MagicMock(), MagicMock(), motor),
                SetReferenceButton(runtime, MagicMock(), MagicMock(), motor),
            )
        ),
        RemoteUsedButton(runtime, MagicMock()),
        SavedPositionsSensor(runtime, MagicMock()),
        SavedPositionButton(runtime, MagicMock(), MagicMock()),
        *(AdjustableBedCover(runtime, description) for description in COVER_DESCRIPTIONS),
        *(AdjustableBedPositionNumber(runtime, d) for d in NUMBER_DESCRIPTIONS),
        *(PairedBedCombinedPositionNumber(runtime, d) for d in NUMBER_DESCRIPTIONS),
        *(AdjustableBedMassageNumber(runtime, d) for d in MASSAGE_NUMBER_DESCRIPTIONS),
        *(AdjustableBedLevelNumber(runtime, d) for d in (LIGHT_LEVEL_DESCRIPTION, FAN_LEVEL_DESCRIPTION)),
        AdjustableBedSleepNumberSettingNumber(runtime, SLEEP_NUMBER_SETTING_DESCRIPTION),
        *(
            AdjustableBedSideStateNumber(runtime, d)
            for d in (SLEEP_NUMBER_SETTING_LEFT_DESCRIPTION, SLEEP_NUMBER_SETTING_RIGHT_DESCRIPTION)
        ),
        AdjustableBedMassageTimerSelect(runtime, MASSAGE_TIMER_DESCRIPTION, [10]),
        *(
            AdjustableBedControllerStateSelect(runtime, d, [])
            for d in (LIGHT_TIMER_DESCRIPTION, THERMAL_TIMER_DESCRIPTION, FOOTWARMING_TIMER_DESCRIPTION)
        ),
        *(
            AdjustableBedSideStateSelect(runtime, d, [])
            for d in (
                THERMAL_TIMER_LEFT_DESCRIPTION,
                THERMAL_TIMER_RIGHT_DESCRIPTION,
                FOOTWARMING_TIMER_LEFT_DESCRIPTION,
                FOOTWARMING_TIMER_RIGHT_DESCRIPTION,
                FOUNDATION_PRESET_LEFT_DESCRIPTION,
                FOUNDATION_PRESET_RIGHT_DESCRIPTION,
            )
        ),
        *(AdjustableBedSwitch(runtime, d) for d in SWITCH_DESCRIPTIONS),
        *(AdjustableBedAngleSensor(runtime, d) for d in SENSOR_DESCRIPTIONS),
        *(AdjustableBedMassageSensor(runtime, d) for d in MASSAGE_SENSOR_DESCRIPTIONS),
        AdjustableBedConnectionSensor(runtime, BINARY_SENSOR_DESCRIPTIONS[0]),
        AdjustableBedPresenceSensor(runtime, presence),
        *(
            AdjustableBedPresenceSensor(
                runtime,
                replace(presence, key=f"{presence.key}_{side}", translation_key=f"{presence.key}_{side}"),
            )
            for side in sides
        ),
        *(
            AdjustableBedClimate(runtime, d)
            for d in (
                SLEEP_NUMBER_THERMAL_CLIMATE_DESCRIPTION,
                FOOTWARMING_CLIMATE_DESCRIPTION,
                *map(_build_side_thermal_climate_description, sides),
                *map(_build_side_footwarming_climate_description, sides),
            )
        ),
        AdjustableBedLight(runtime, LIGHT_DESCRIPTION),
        AdjustableBedOnOffLight(runtime, LIGHT_DESCRIPTION),
        AdjustableBedAssumedLight(runtime),
    ]


def placements(entities: Iterable[Entity]) -> dict[str, dict[str, str | int]]:
    """Map ``domain:translation_key`` to the placement its entities publish."""
    result: dict[str, dict[str, str | int]] = {}
    for entity in entities:
        assert isinstance(entity, PlacedInCard), type(entity).__name__
        if not entity.translation_key:
            continue
        key = f"{_domain(entity)}:{entity.translation_key}"
        attributes = entity._card.attributes
        if result.setdefault(key, attributes) != attributes:
            raise ValueError(f"{key} is placed as both {result[key]} and {attributes}")
    return dict(sorted(result.items()))


def _domain(entity: Entity) -> str:
    for cls in type(entity).__mro__:
        module = cls.__module__
        if module.startswith("homeassistant.components."):
            return module.split(".")[2]
    raise TypeError(type(entity).__name__)


def literal_spec_placements() -> dict[str, dict[str, str | int]]:
    """Return the placement of every spec a bed states with a literal key.

    This reaches specs a bed builds only for what it reports at runtime. A
    placement that is not a plain card expression is left to the live specs.
    """
    from custom_components.adjustable_bed import card
    from custom_components.adjustable_bed.beds import base

    namespace = vars(card)
    result: dict[str, dict[str, str | int]] = {}
    for path in INTEGRATION.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in SPEC_PLATFORMS and name != "ProductButtonSpec":
                continue
            platform, position = SPEC_PLATFORMS.get(name, ("button", 4))
            keys = [kw.value for kw in node.keywords if kw.arg == "translation_key"]
            if len(node.args) > position:
                keys.append(node.args[position])
            if not keys or not isinstance(keys[0], ast.Constant) or not isinstance(keys[0].value, str):
                continue
            key = keys[0].value
            if name == "MotorControlSpec":
                placement = card.motor_card(key)
            elif name == "ProductButtonSpec":
                continue
            else:
                expressions = [kw.value for kw in node.keywords if kw.arg == "card"]
                try:
                    placement = (
                        eval(ast.unparse(expressions[0]), dict(namespace))
                        if expressions
                        else next(
                            f.default for f in fields(getattr(base, name)) if f.name == "card"
                        )
                    )
                except NameError:
                    continue
            result[f"{platform}:{key}"] = placement.attributes
    return result


async def built_entities() -> list[Entity]:
    """Build every entity offline controllers and descriptions create."""
    # Motion Bed motors depend on the movement layout; its other specs do not.
    motion_bed_motors = [
        spec for controller in _motion_bed_controllers() for spec in controller.motor_control_specs
    ]
    return [
        *controller_entities(await factory_controllers()),
        *motor_entities(motion_bed_motors),
        *description_entities(),
    ]


def all_placements(entities: Iterable[Entity]) -> dict[str, dict[str, str | int]]:
    """Return the placement of every built entity and every literal spec."""
    result = placements(entities)
    for key, attributes in literal_spec_placements().items():
        if result.setdefault(key, attributes) != attributes:
            raise ValueError(f"{key} is placed as both {result[key]} and {attributes}")
    return dict(sorted(result.items()))


def main() -> None:
    entities = asyncio.run(built_entities())
    FIXTURE.write_text(json.dumps(all_placements(entities), indent=1) + "\n")


if __name__ == "__main__":
    main()
