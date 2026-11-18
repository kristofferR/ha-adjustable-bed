"""Carry a user's settings over when v5 changes an entity's type.

An entity that becomes another platform (the under-bed light switch became a
light) or gets a new unique ID gets a new registry row. Before the platforms
add entities, the old row is replaced by a new one with its object ID and the
settings the user gave it.
Automations cannot be rewritten across a domain change, so a repair lists the
ones that still name an old entity.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, split_entity_id
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.start import async_at_started
from homeassistant.util.hass_dict import HassKey

from .const import BED_TYPE_OCTO, DOMAIN
from .paired_coordinator import entity_runtimes

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator
    from .paired_coordinator import PairedBedCoordinator


@dataclass(frozen=True, slots=True)
class Retype:
    """One old entity that is now one new entity the user sees as the same thing."""

    old_domain: str
    old_key: str
    new_domain: str
    new_key: str
    # Bed types that keep the old entity.
    keep_on: frozenset[str] = frozenset()


def _same_key(old_domain: str, new_domain: str, keys: Iterable[str]) -> tuple[Retype, ...]:
    return tuple(Retype(old_domain, key, new_domain, key) for key in keys)


RETYPES: Final[tuple[Retype, ...]] = (
    # Octo's on/off light stays a switch.
    Retype("switch", "under_bed_lights", "light", "under_bed_lights", frozenset({BED_TYPE_OCTO})),
    # Sleep readings that were text sensors.
    *_same_key(
        "sensor",
        "binary_sensor",
        (
            *(f"casper_sleep_{s}_{f}" for s in "LR" for f in ("on_bed", "body_move", "snoring")),
            *(f"goodvibe_{s}_{f}" for s in "LR" for f in ("occupancy", "movement", "snore")),
            *(
                f"ruf_richmat_sleep_{s}_{f}"
                for s in ("left", "right")
                for f in ("occupancy", "movement")
            ),
        ),
    ),
    # Two-option settings that became switches.
    *(
        Retype(
            "select", f"controller_select_okin_app_{s}", "switch", f"controller_switch_okin_app_{s}"
        )
        for s in ("installation", "actuator_1", "actuator_2")
    ),
    # Toggle buttons whose state the bed reports.
    Retype(
        "button",
        "motion_bed_night_light",
        "switch",
        "controller_switch_motion_bed_night_light_enabled",
    ),
    Retype(
        "button", "motion_bed_sleepmian", "switch", "controller_switch_motion_bed_sleep_enabled"
    ),
    # Massage level selects that became numbers.
    *(
        Retype(
            "select",
            f"controller_select_adjustamattress_{zone}_selector",
            "number",
            f"controller_number_adjustamattress_{zone}_massage",
        )
        for zone in ("head", "foot", "wave")
    ),
    # Bed-specific massage timers that became the shared one.
    *(
        Retype("select", f"controller_select_{key}", "select", "massage_timer")
        for key in (
            "starcode_abm5_4_massage_timer",
            "ore_comfort_massage_timer",
            "comfortfurniture_massage_timer",
            "sleepys_app_massage_timer_code",
        )
    ),
)

# Readings v5 enables by default that earlier versions created disabled.
NOW_ENABLED: Final[tuple[tuple[str, str], ...]] = (
    *(
        ("binary_sensor", key)
        for key in ("bed_presence", "bed_presence_left", "bed_presence_right")
    ),
    *(
        (domain, f"cheerssleep_{side}_{field}")
        for side in ("left", "right")
        for domain, field in (
            ("sensor", "heart"),
            ("sensor", "breath"),
            ("binary_sensor", "on_bed"),
        )
    ),
)

ISSUE_PREFIX: Final = "retyped_entities_"
_PENDING: HassKey[dict[str, list[Moved]]] = HassKey(f"{DOMAIN}_retyped_entities")


@callback
def async_carry_over_retyped_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator | PairedBedCoordinator,
) -> None:
    """Give each retyped entity's new row the old row's ID and user settings."""
    registry = er.async_get(hass)
    moved: list[Moved] = []
    for runtime in entity_runtimes(coordinator):
        for retype in RETYPES:
            if runtime.bed_type in retype.keep_on:
                continue
            new = _carry_over(
                registry,
                entry,
                retype,
                runtime.entity_unique_id(retype.old_key),
                runtime.entity_unique_id(retype.new_key),
            )
            if new is not None:
                moved.append(new)
        for domain, key in NOW_ENABLED:
            entity_id = registry.async_get_entity_id(domain, DOMAIN, runtime.entity_unique_id(key))
            row = registry.async_get(entity_id) if entity_id else None
            if row is not None and row.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                registry.async_update_entity(row.entity_id, disabled_by=None)
    if moved:
        # Reported once the entity sweep confirms which replacements the bed builds.
        hass.data.setdefault(_PENDING, {}).setdefault(entry.entry_id, []).extend(moved)


@callback
def async_retyped_entities_built(
    hass: HomeAssistant, entry: ConfigEntry, created: Collection[tuple[str, str]]
) -> None:
    """Report the automations that still name an old entity the bed has replaced.

    Called by the sweep with every (domain, unique ID) the entry's platforms
    built, once that record is authoritative. A replacement the bed does not
    build is dropped: the sweep removes it.
    """
    moved = hass.data.get(_PENDING, {}).pop(entry.entry_id, [])
    built = [item for item in moved if (item.new_domain, item.new_unique_id) in created]
    if not built:
        return

    @callback
    def report(_hass: HomeAssistant) -> None:
        _async_report_references(hass, entry, built)

    # Automations and scripts load after integrations at startup.
    async_at_started(hass, report)


@dataclass(frozen=True, slots=True)
class Moved:
    """An old entity a user's automations may still name, and what replaced it."""

    old_entity_id: str
    old_registry_id: str
    new_entity_id: str
    new_domain: str
    new_unique_id: str
    # The same platform with a new unique ID: only the options changed.
    options_changed: bool


def _carry_over(
    registry: er.EntityRegistry,
    entry: ConfigEntry,
    retype: Retype,
    old_unique_id: str,
    new_unique_id: str,
) -> Moved | None:
    """Move the old row's identity and user settings to the new entity."""
    old_id = registry.async_get_entity_id(retype.old_domain, DOMAIN, old_unique_id)
    if old_id is None or registry.async_get_entity_id(retype.new_domain, DOMAIN, new_unique_id):
        return None
    old = registry.async_get(old_id)
    assert old is not None
    if retype.old_domain == retype.new_domain:
        # The row itself carries over, with its entity ID and every setting.
        registry.async_update_entity(old_id, new_unique_id=new_unique_id)
        return Moved(
            old_id, old.id, old_id, retype.new_domain, new_unique_id, options_changed=True
        )
    object_id = split_entity_id(old_id)[1]
    taken = registry.async_is_registered(f"{retype.new_domain}.{object_id}")
    user = er.RegistryEntryDisabler.USER
    new = registry.async_get_or_create(
        retype.new_domain,
        DOMAIN,
        new_unique_id,
        config_entry=entry,
        device_id=old.device_id,
        suggested_object_id=None if taken else object_id,
        # Only the user's choices carry over; v5 decides its own defaults.
        disabled_by=user if old.disabled_by is user else None,
        hidden_by=er.RegistryEntryHider.USER
        if old.hidden_by is er.RegistryEntryHider.USER
        else None,
        # The name Home Assistant shows until the platform adds the entity.
        has_entity_name=old.has_entity_name,
        original_name=old.original_name,
        translation_key=old.translation_key,
    )
    registry.async_update_entity(
        new.entity_id,
        name=old.name,
        icon=old.icon,
        area_id=old.area_id,
        labels=set(old.labels),
        aliases=list(old.aliases),
        categories=dict(old.categories),
    )
    for namespace, options in old.options.items():
        # The old platform's own options (units, precision) mean nothing to the new one.
        if namespace != retype.old_domain:
            registry.async_update_entity_options(new.entity_id, namespace, dict(options))
    # Nothing builds the old entity any more.
    registry.async_remove(old_id)
    return Moved(
        old_id, old.id, new.entity_id, retype.new_domain, new_unique_id, options_changed=False
    )


@callback
def _async_report_references(hass: HomeAssistant, entry: ConfigEntry, moved: list[Moved]) -> None:
    """Raise one repair per bed naming the automations and scripts to update."""
    from homeassistant.components.automation import automations_with_entity  # noqa: PLC0415
    from homeassistant.components.script import scripts_with_entity  # noqa: PLC0415

    lines: list[str] = []
    for item in moved:
        users = {
            user
            for reference in (item.old_entity_id, item.old_registry_id)
            for user in (
                *automations_with_entity(hass, reference),
                *scripts_with_entity(hass, reference),
            )
        }
        if not users:
            continue
        change = (
            f"{item.old_entity_id} (its options changed)"
            if item.options_changed
            else f"{item.old_entity_id} → {item.new_entity_id}"
        )
        lines.append(f"- {change}: {', '.join(sorted(users))}")
    if not lines:
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_PREFIX + entry.entry_id,
        config_entry_id=entry.entry_id,
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="retyped_entities",
        translation_placeholders={"bed": entry.title, "entities": "\n".join(lines)},
    )
