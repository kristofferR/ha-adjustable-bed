"""The entities each offline controller variant creates, as a person sees them.

Builds every controller variant ``tests.card_placements.runtime_variants``
reaches through the real platform builders, with massage enabled, and resolves
each entity's shown name the way Home Assistant does: its own name, else its
translated name with the placeholders filled in.

Dump the surface of one bed type for a review::

    uv run --no-sync python -m tests.entity_surface goodvibe
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.helpers.entity import Entity

from custom_components.adjustable_bed import (
    binary_sensor,
    button,
    climate,
    cover,
    light,
    number,
    select,
    sensor,
    switch,
)
from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
)
from tests.card_placements import runtime_variants
from tests.entity_translation_reachability import entity_strings, factory_controllers

_PLATFORMS = {
    "binary_sensor": binary_sensor._binary_sensor_entities_for,
    "button": button._button_entities_for,
    "climate": climate._climate_entities_for,
    "cover": cover._cover_entities_for,
    "light": light._light_entities_for,
    "number": number._number_entities_for,
    "select": select._select_entities_for,
    "sensor": sensor._sensor_entities_for,
    "switch": switch._switch_entities_for,
}


@dataclass(frozen=True, slots=True)
class ShownEntity:
    """One entity as it appears on a device."""

    domain: str
    unique_id: str | None
    translation_key: str | None
    name: str | None
    card: tuple[tuple[str, str | int], ...]
    enabled: bool
    requires_confirmation: bool
    # Publishes a held gesture the card would send on press-and-hold.
    held: bool
    category: str | None

    @property
    def section(self) -> str | int | None:
        return dict(self.card).get("card_section")

    @property
    def role(self) -> str | int | None:
        return dict(self.card).get("card_role")


@dataclass(frozen=True, slots=True)
class Device:
    """The entities one controller variant gives one device."""

    bed: str
    entities: tuple[ShownEntity, ...]


class _Runtime:
    """A standalone entry's runtime, offline: what the platform builders read."""

    def __init__(self, controller: BedController) -> None:
        self.capability_controller = controller
        self.controller = controller
        coordinator = getattr(controller, "_coordinator", None)
        data = dict(getattr(getattr(coordinator, "entry", None), "data", None) or {})
        self.bed_type = data.get(CONF_BED_TYPE) or type(controller).__name__
        data[CONF_HAS_MASSAGE] = True
        data.setdefault(CONF_MOTOR_COUNT, getattr(coordinator, "motor_count", 2))
        self.has_massage = True
        self.disable_angle_sensing = False
        self.entity_side = None
        self.controller_side = None
        self.address = "AA:BB:CC:DD:EE:FF"
        self.name = "Bed"
        self.position_data: dict[str, float] = {}
        self.controller_state: dict[str, object] = {}
        self.is_connected = True
        self.is_connecting = False
        self.entry = SimpleNamespace(
            data=data, options={}, entry_id="surface", title="Bed", async_on_unload=lambda _: None
        )
        self.device_info: dict[str, object] = {}

    def entity_unique_id(self, key: str) -> str:
        return f"aa:{key}"

    def __getattr__(self, name: str) -> Any:
        if name.startswith("register_"):
            return lambda *_args, **_kwargs: lambda: None
        if name.startswith("async_"):

            async def noop(*_args: object, **_kwargs: object) -> None:
                return None

            return noop
        raise AttributeError(name)


def _shown_name(entity: Entity, domain: str, strings: Mapping[str, Any]) -> str | None:
    # Home Assistant's own order: a set name, the description's, then the translation.
    if hasattr(entity, "_attr_name"):
        return entity._attr_name
    description = getattr(entity, "entity_description", None)
    if description is not None and isinstance(description.name, str):
        return description.name
    key = entity.translation_key
    if key is None:
        return None
    template = (strings.get(domain, {}).get(key) or {}).get("name")
    if template is None:
        return None
    placeholders = getattr(entity, "_attr_translation_placeholders", None) or {}
    return str(template).format_map(dict(placeholders))


def _shown(entity: Entity, domain: str, strings: Mapping[str, Any]) -> ShownEntity:
    category = entity.entity_category
    # Only controller-declared buttons ask first; read what such a button publishes.
    confirm = isinstance(entity, ControllerActionButton) and entity._spec.requires_confirmation
    attributes = entity.extra_state_attributes or {} if confirm else {}
    return ShownEntity(
        domain=domain,
        unique_id=entity.unique_id,
        translation_key=entity.translation_key,
        name=_shown_name(entity, domain, strings),
        card=tuple(sorted(entity._card.attributes.items())),  # type: ignore[attr-defined]
        enabled=entity.entity_registry_enabled_default,
        requires_confirmation=bool(attributes.get("requires_confirmation")),
        held="held_control" in attributes,
        category=category.value if category is not None else None,
    )


def _devices(controllers: list[BedController]) -> Iterator[Device]:
    strings = entity_strings()
    hass = MagicMock()
    hass.data = {}
    seen: set[tuple[str, tuple[ShownEntity, ...]]] = set()
    for controller in runtime_variants(controllers):
        runtime = _Runtime(controller)
        entities = tuple(
            _shown(entity, domain, strings)
            for domain, build in _PLATFORMS.items()
            for entity in build(hass, runtime)  # type: ignore[arg-type]
        )
        signature = (runtime.bed_type, entities)
        if signature not in seen:
            seen.add(signature)
            yield Device(runtime.bed_type, entities)


async def devices() -> list[Device]:
    """Every distinct entity set a bed type's offline variants create."""
    registry = MagicMock()
    registry.async_get_entity_id.return_value = None
    registry.async_get.return_value = None
    registry.entities = {}
    with (
        patch("homeassistant.helpers.entity_registry.async_get", return_value=registry),
        patch("homeassistant.helpers.device_registry.async_get", return_value=MagicMock()),
    ):
        controllers = await factory_controllers()
        return list(_devices(controllers))


def main() -> None:
    beds = set(sys.argv[1:])
    for device in asyncio.run(devices()):
        if beds and device.bed not in beds:
            continue
        print(f"== {device.bed}")
        for entity in device.entities:
            print(
                f"  {entity.domain}:{entity.translation_key} {entity.name!r} "
                f"{json.dumps(dict(entity.card))} enabled={entity.enabled}"
                f"{' confirm' if entity.requires_confirmation else ''}"
                f"{f' {entity.category}' if entity.category else ''}"
            )


if __name__ == "__main__":
    main()
