"""Where each entity the integration can create sits in the Lovelace card.

Reads the placement of every entity offline controllers' specs declare, and of
the entities static descriptions build. The frontend tests attach these placements
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
from collections.abc import Callable, Iterable, Iterator
from dataclasses import fields, replace
from inspect import signature
from itertools import chain
from pathlib import Path
from typing import NamedTuple, cast
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
from custom_components.adjustable_bed.card import CardPlacement, CardRole, motor_card
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
from custom_components.adjustable_bed.switch import (
    SWITCH_DESCRIPTIONS,
    AdjustableBedControllerSwitch,
    AdjustableBedSwitch,
)
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


class Placed(NamedTuple):
    """An entity a spec declares: its class, constructor arguments, key and placement.

    Reading these from specs, instead of building the entity, keeps the full
    catalog walk (hundreds of thousands of entities) cheap. ``sample_entities``
    builds the distinct ones for real to prove they agree.
    """

    cls: type[PlacedInCard]
    args: tuple[object, ...]
    translation_key: str | None
    card: CardPlacement

    def build(self, runtime: MagicMock) -> Entity:
        # Each entity class takes the runtime and its spec or description, which
        # PlacedInCard, a mixin without a constructor, cannot state.
        return cast("Callable[..., Entity]", self.cls)(runtime, *self.args)


def motor_entities(specs: Iterable[MotorControlSpec]) -> Iterator[Placed]:
    """Each motor's cover and its combined both-sides buttons."""
    for spec in specs:
        key = spec.translation_key or spec.key
        yield Placed(AdjustableBedCover, (_build_cover_description(spec),), key, motor_card(key))
        # A natively sided motor differs between sides, so it is never combined.
        if not spec.translation_key.endswith(("_left", "_right")):
            for direction, role in (("up", CardRole.UP), ("down", CardRole.DOWN)):
                yield Placed(
                    PairedBedCombinedMotorButton,
                    (spec, direction),
                    f"{spec.translation_key}_{direction}",
                    motor_card(spec.translation_key, role),
                )


def spec_entities(controller: BedController) -> Iterator[Placed]:
    """Every entity a controller's specs declare, as its platform builds it."""
    yield from motor_entities(controller.motor_control_specs)
    for spec in controller.position_number_specs:
        yield Placed(
            AdjustableBedPositionNumber,
            (_build_position_description(spec),),
            spec.translation_key or spec.key,
            motor_card(spec.motor),
        )
    for spec in controller.controller_button_specs:
        if isinstance(spec, ProductButtonSpec):
            yield Placed(AdjustableBedProductButton, (spec,), "product_action", spec.card)
        else:
            # An untranslated action takes the class's shared "remote_action" key.
            key = "remote_action" if spec.translation_key is None else spec.translation_key
            yield Placed(ControllerActionButton, (spec,), key, spec.card)
    for cls, specs in (
        (AdjustableBedControllerSelect, controller.controller_select_specs),
        (AdjustableBedControllerNumber, controller.controller_number_specs),
        (AdjustableBedControllerSwitch, controller.controller_switch_specs),
        (AdjustableBedControllerStateSensor, controller.controller_state_sensor_specs),
        (AdjustableBedControllerStateBinarySensor, controller.controller_state_binary_sensor_specs),
    ):
        yield from (Placed(cls, (spec,), spec.translation_key, spec.card) for spec in specs)


def runtime_variants(controllers: Iterable[BedController]) -> Iterator[BedController]:
    """Yield each controller, plus copies in states only a live bed reports.

    Some controls exist only for a reported model, layout or page, which no
    offline configuration reaches.
    """
    from custom_components.adjustable_bed.beds.dreamsense.controller import DreamSenseController
    from custom_components.adjustable_bed.beds.keeson.enso import EnsoController
    from custom_components.adjustable_bed.beds.okimiki.controller import OkimikiController
    from custom_components.adjustable_bed.beds.onlysnore.controller import OnlySnoreController
    from custom_components.adjustable_bed.beds.ore_ultramatic.controller import (
        OreUltramaticController,
    )
    from custom_components.adjustable_bed.beds.paramount.controller import ParamountController
    from custom_components.adjustable_bed.beds.richmat_classic.bedsmart import BedSmartController
    from custom_components.adjustable_bed.beds.richmat_classic.jerome import JeromeController
    from custom_components.adjustable_bed.beds.richmat_classic.jerome_controls import (
        actions,
        inverse_pairs,
    )
    from custom_components.adjustable_bed.beds.richmat_classic.lp2 import Lp2Controller
    from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
    from custom_components.adjustable_bed.beds.richmat_classic.receive import ReceiveState
    from custom_components.adjustable_bed.beds.richmat_classic.resource_controller import (
        ResourceBedController,
    )
    from custom_components.adjustable_bed.beds.richmat_classic.resource_receive import (
        ResourceReceiveState,
    )
    from custom_components.adjustable_bed.beds.richmat_mh.app_controller import (
        RichmatMHAppController,
    )
    from custom_components.adjustable_bed.beds.ruf_richmat.controller import RufRichmatController
    from custom_components.adjustable_bed.beds.sleeptracker.controller import SleeptrackerController
    from custom_components.adjustable_bed.beds.sleepys.app import (
        SLEEPYS_ELITE_SELECTORS,
        SleepysEliteAppController,
    )
    from custom_components.adjustable_bed.beds.smart_comfort.controller import (
        SmartComfortController,
    )
    from custom_components.adjustable_bed.beds.starcode.abm5_4 import (
        _POSITIVE_SELECTORS,
        StarcodeAbm5_4Controller,
    )
    from custom_components.adjustable_bed.beds.suta.controller import SutaController
    from custom_components.adjustable_bed.beds.vibradorm.app import VibradormAppController
    from custom_components.adjustable_bed.beds.vmatbasic.controller import VMatBasicController
    from custom_components.adjustable_bed.profiles import ore_ultramatic as ultramatic
    from custom_components.adjustable_bed.profiles import vmatbasic as vmat_profiles
    from custom_components.adjustable_bed.profiles.dreamsense import PROFILES as DREAMSENSE_PROFILES
    from custom_components.adjustable_bed.profiles.enso import PROFILES as ENSO_PROFILES
    from custom_components.adjustable_bed.profiles.suta import ROUTES as SUTA_ROUTES

    def variant(controller: BedController, **attributes: object) -> BedController:
        clone = copy.copy(controller)
        for name, value in attributes.items():
            setattr(clone, name, value)
        return clone

    for controller in controllers:
        yield controller
        if isinstance(controller, DreamSenseController):
            for profile in DREAMSENSE_PROFILES.values():
                yield variant(controller, profile=profile, _known={"clock", "light", "music"})
        if isinstance(controller, EnsoController):
            for profile in ENSO_PROFILES.values():
                yield variant(controller, profile=profile)
        if isinstance(controller, SutaController):
            for route in SUTA_ROUTES:
                name = "SUTA-unknown" if route == "fallback" else "SUTA" if route == "short-name" else route.split("*")[0]
                yield SutaController(controller._coordinator, name=name)
        elif isinstance(controller, OreUltramaticController):
            for route in ("P1", "P2"):
                yield variant(controller, _route=route, profile=ultramatic.profile(route))
        elif isinstance(controller, OnlySnoreController):
            yield variant(controller, _alarm_count=3)
        elif isinstance(controller, ParamountController):
            yield variant(controller, _mask=31, _height_bounds=(20, 70))
        elif isinstance(controller, OkimikiController):
            yield variant(controller, _menus={"light", "alarm"})
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
            for selector in SLEEPYS_ELITE_SELECTORS:
                yield variant(controller, selector=selector)
        elif isinstance(controller, StarcodeAbm5_4Controller):
            for selector in _POSITIVE_SELECTORS:
                yield variant(controller, command_selector=selector)
        elif isinstance(controller, SmartComfortController):
            yield variant(controller, _model=0x89, _flags=(7, 7, 7), _ready=True)
        elif isinstance(controller, RichmatMHAppController):
            for version in ("0000", "0001"):
                reported = variant(
                    controller, _version=version, _call_page=version == "0001",
                    _dev={"led": True, "alarm": True, "snore": True},
                    _detection=True, _waist=controller.app == "mlily_supreme",
                )
                for group in controller._mode_groups or (None,):
                    yield variant(reported, _group_type=group)
                if controller.app == "mlily_supreme" and controller._normal_selected:
                    yield variant(reported, _normal_ready=True)
        elif isinstance(controller, RufRichmatController):
            yield variant(controller, _normal_ready=True)
        elif isinstance(controller, BedSmartController):
            # Each command format lists its own controls once the bed connected.
            for layout in ("DHRM", "D1RM", "U3RM", "GVRM"):
                model = load_catalog(controller.app).models[layout]
                for wire in ("RAW", "FRAMED"):
                    yield variant(controller, layout=layout, _model=model, _controls=model.controls,
                                  _receive=ReceiveState(light_capable=True, aroma_capable=True),
                                  _wire=wire)
        elif isinstance(controller, Lp2Controller):
            for wire in ("RAW", "FRAMED"):
                yield variant(controller, _wire=wire)
        elif isinstance(controller, JeromeController):
            for layout in ("D1RM", "D9RM", "Y6RM", "R2RM", "DXRM", "B9TT"):
                model = load_catalog("jerome2").models[layout]
                yield variant(controller, layout=layout, _model=model, _controls=model.controls,
                              _actions=actions(layout), _pairs=inverse_pairs(layout),
                              _receive=ReceiveState(light_capable=True, aroma_capable=True))
        elif isinstance(controller, ResourceBedController):
            model = load_catalog(controller.app).models["D1RM"]
            yield variant(controller, layout="D1RM", _model=model, _controls=model.controls,
                          _receive=ResourceReceiveState(light_capable=True))


def controller_entities(controllers: Iterable[BedController]) -> list[Entity]:
    """Build the entities every controller's specs declare."""
    runtime = _runtime()
    return [
        placed.build(runtime)
        for controller in runtime_variants(controllers)
        for placed in spec_entities(controller)
    ]


def sample_entities(declared: Iterable[Placed]) -> list[Entity]:
    """Build each declared entity for real and check it publishes what was declared."""
    runtime = _runtime()
    entities: list[Entity] = []
    for placed in declared:
        entity = placed.build(runtime)
        assert isinstance(entity, PlacedInCard), placed.cls.__name__
        assert (entity.translation_key, entity._card) == (placed.translation_key, placed.card), (
            f"{placed.cls.__name__} builds {entity.translation_key} {entity._card}, "
            f"not {placed.translation_key} {placed.card}"
        )
        entities.append(entity)
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
    declared: list[Placed] = []
    for entity in entities:
        assert isinstance(entity, PlacedInCard), type(entity).__name__
        declared.append(Placed(type(entity), (), entity.translation_key, entity._card))
    return declared_placements(declared)


def declared_placements(declared: Iterable[Placed]) -> dict[str, dict[str, str | int]]:
    """Map ``domain:translation_key`` to the placement its entities publish."""
    result: dict[str, dict[str, str | int]] = {}
    domains: dict[type[PlacedInCard], str] = {}
    for placed in declared:
        if not placed.translation_key:
            continue
        domain = domains.get(placed.cls) or domains.setdefault(placed.cls, _domain(placed.cls))
        key = f"{domain}:{placed.translation_key}"
        attributes = placed.card.attributes
        if result.setdefault(key, attributes) != attributes:
            raise ValueError(f"{key} is placed as both {result[key]} and {attributes}")
    return dict(sorted(result.items()))


def _domain(cls: type[Entity]) -> str:
    for base in cls.__mro__:
        module = base.__module__
        if module.startswith("homeassistant.components."):
            return module.split(".")[2]
    raise TypeError(cls.__name__)


def _default_card(declare: Callable[..., object]) -> CardPlacement:
    """The card a spec class or a shared spec builder places its entity in by default."""
    if isinstance(declare, type):
        return cast(CardPlacement, next(f.default for f in fields(declare) if f.name == "card"))
    return signature(declare).parameters["card"].default


def literal_spec_placements() -> dict[str, dict[str, str | int]]:
    """Return the placement of every spec a bed states with a literal key.

    This reaches specs a bed builds only for what it reports at runtime. A
    placement that is not a plain card expression is left to the live specs.
    """
    from custom_components.adjustable_bed import card
    from custom_components.adjustable_bed.beds import base, entity_specs

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
                        else _default_card(getattr(entity_specs, name, None) or getattr(base, name))
                    )
                except NameError:
                    continue
            result[f"{platform}:{key}"] = placement.attributes
    return result


async def declared_entities() -> list[Placed]:
    """Every distinct entity offline controllers declare, without building them.

    A placement depends only on the class, key and card, so one record of each
    is kept; the catalog walk yields hundreds of thousands of duplicates.
    """
    # Motion Bed motors depend on the movement layout; its other specs do not.
    motion_bed_motors = [
        spec for controller in _motion_bed_controllers() for spec in controller.motor_control_specs
    ]
    declared = chain(
        (
            placed
            for controller in runtime_variants(await factory_controllers())
            for placed in spec_entities(controller)
        ),
        motor_entities(motion_bed_motors),
    )
    distinct: dict[tuple[type[PlacedInCard], str | None, CardPlacement], Placed] = {}
    for placed in declared:
        distinct.setdefault((placed.cls, placed.translation_key, placed.card), placed)
    return list(distinct.values())


def all_placements(declared: Iterable[Placed]) -> dict[str, dict[str, str | int]]:
    """Return the placement of every declared entity, every description and every literal spec."""
    result = declared_placements(declared)
    for key, attributes in (*placements(description_entities()).items(), *literal_spec_placements().items()):
        if result.setdefault(key, attributes) != attributes:
            raise ValueError(f"{key} is placed as both {result[key]} and {attributes}")
    return dict(sorted(result.items()))


def main() -> None:
    declared = asyncio.run(declared_entities())
    FIXTURE.write_text(json.dumps(all_placements(declared), indent=1) + "\n")


if __name__ == "__main__":
    main()
