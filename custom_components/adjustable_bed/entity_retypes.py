"""Carry a user's settings over when v5 changes an entity's type.

An entity that becomes another platform (the under-bed light switch became a
light) or gets a new unique ID gets a new registry row. Before the platforms
add entities, the old row is replaced by a new one with its object ID and the
settings the user gave it.
Automations cannot be rewritten across a domain change, so a repair lists the
ones that still name an old entity. The new row remembers the old entity ID in
its own options, so the repair is raised again after every startup, also after
a restart that cut the first one short, until nothing names the old entity.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, split_entity_id
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.start import async_at_started

from .automation_references import entity_users
from .const import (
    BED_TYPE_DREAMSENSE,
    BED_TYPE_OCTO,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    BED_TYPE_SCOTT_LIVING,
    DOMAIN,
)
from .paired_coordinator import entity_runtimes

if TYPE_CHECKING:
    from .beds.base import BedController
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
    # When set, the only bed types the change applies to.
    only_on: frozenset[str] = frozenset()
    # When set, the change applies only to a bed whose controller says so
    # (a product of the bed type, known before the first connection).
    applies: Callable[[BedController], bool] | None = None
    # A same-domain key rename whose action and arguments stay the same.
    identity_only: bool = False


def _same_key(old_domain: str, new_domain: str, keys: Iterable[str]) -> tuple[Retype, ...]:
    return tuple(Retype(old_domain, key, new_domain, key) for key in keys)


def _tss_fixed_timer(controller: BedController, *, key: str) -> bool:
    from .beds.richmat_classic.tss_remote import TssRemoteController

    return (
        isinstance(controller, TssRemoteController)
        and key in controller.fixed_massage_timer_button_keys
    )


RETYPES: Final[tuple[Retype, ...]] = (
    # Catalog node IDs with a fixed-duration appearance in the accepted TSS app.
    # The live layout predicate prevents retyping another action at the same node.
    *(
        Retype(
            "button", key, "select", "massage_timer",
            only_on=frozenset({BED_TYPE_RICHMAT_CLASSIC_APPS}),
            applies=partial(_tss_fixed_timer, key=key),
        )
        for node in (1, 2, 3, 6, 11, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 32, 34)
        for key in (f"tss_{node}", f"tss_{node}_raw")
    ),
    # Scott Living's catalog presets replace its standard preset buttons.
    *(
        Retype(
            "button", f"preset_{key}", "button", key,
            only_on=frozenset({BED_TYPE_SCOTT_LIVING}), identity_only=True,
        )
        for key in ("zero_g", "tv", "anti_snore")
    ),
    Retype(
        "button", "toggle_light", "button", "light",
        only_on=frozenset({BED_TYPE_SCOTT_LIVING}), identity_only=True,
    ),
    Retype(
        "number",
        "controller_number_ergobq_light_minutes",
        "select",
        "light_timer",
        only_on=frozenset({"ergobq"}),
    ),
    *(
        Retype(
            "number",
            f"controller_number_ergobq_{zone}_minutes",
            "select",
            f"controller_select_ergobq_{zone}_timer",
            only_on=frozenset({"ergobq"}),
        )
        for zone in ("head", "legs")
    ),
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
    # A massage state that was a text sensor.
    Retype(
        "sensor", "starcode_abm5_4_massage_on", "binary_sensor", "starcode_abm5_4_massage_active"
    ),
    # Two-option settings that became switches.
    *(
        Retype(
            "select", f"controller_select_okin_app_{s}", "switch", f"controller_switch_okin_app_{s}"
        )
        for s in ("installation", "actuator_1", "actuator_2")
    ),
    *(
        Retype("select", f"controller_select_{old}", "switch", f"controller_switch_{new}")
        for old, new in (
            ("reverie_pairlink_massage_rhythm", "reverie_pairlink_massage_rhythm"),
            ("doublesleep_child_lock", "doublesleep_child_lock"),
            ("adjustamattress_snore_control", "adjustamattress_snore_control"),
            ("adjustamattress_alarm_commit", "adjustamattress_alarm"),
        )
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
    Retype("button", "adjustamattress_sleep", "switch", "controller_switch_adjustamattress_sleep"),
    # Light readings of beds that report their light: the light shows that state.
    *(
        Retype("binary_sensor", key, "light", "under_bed_lights")
        for key in (
            "under_bed_lights",
            "furnimove_ubl",
            "innova_light",
            "adjustable_lite_light",
        )
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
            "goodvibe_massage_timer",
            "jerome_massage_timer",
        )
    ),
    # The Reverie Pairlink timer byte is the app's five minute buttons.
    Retype(
        "number", "controller_number_reverie_pairlink_massage_timer", "select", "massage_timer"
    ),
    # Bed-specific light durations that became the shared light timer.
    Retype("select", "controller_select_goodvibe_light_duration", "select", "light_timer"),
    # Light colors that were a 1-7 number are the app's seven swatches.
    Retype(
        "number",
        "controller_number_sleepys_app_color_code",
        "select",
        "controller_select_sleepys_app_light_color",
    ),
    Retype(
        "number",
        "controller_number_symphony_light_color",
        "select",
        "controller_select_symphony_light_color",
    ),
    # DreamSense's Blue product has the app's durations instead of seconds.
    Retype(
        "number",
        "controller_number_dreamsense_light_seconds",
        "select",
        "light_timer",
        only_on=frozenset({BED_TYPE_DREAMSENSE}),
        applies=lambda controller: controller.supports_light_timer,
    ),
    # The Reverie app's wave is a pattern choice, not an intensity.
    Retype(
        "number",
        "massage_wave_intensity",
        "select",
        "controller_select_reverie_massage_wave",
        only_on=frozenset({BED_TYPE_REVERIE, BED_TYPE_REVERIE_NIGHTSTAND}),
    ),
    # Richmat massage sliders that were a 0-5 number are the app's four stops.
    *(
        Retype("number", f"controller_number_{key}", "select", "massage_timer")
        for key in (
            "bedsmart_massage_index",
            "dreamlab_massage_progress",
            "enso2_massage_timer",
            "maxprime_massage_position",
            "richmat_resource_massage_timer",
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
# Kept in the new registry row's options (namespace DOMAIN) until nothing names
# the old entity: its entity ID and registry ID, and whether only the options changed.
RETYPED_FROM: Final = "retyped_from"
RETYPED_FROM_ID: Final = "retyped_from_id"
RETYPED_OPTIONS: Final = "retyped_options_changed"


@callback
def async_carry_over_retyped_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator | PairedBedCoordinator,
) -> None:
    """Give each retyped entity's new row the old row's ID and user settings."""
    registry = er.async_get(hass)
    for runtime in entity_runtimes(coordinator):
        for retype in RETYPES:
            if runtime.bed_type in retype.keep_on or (
                retype.only_on and runtime.bed_type not in retype.only_on
            ):
                continue
            if retype.applies is not None:
                controller = runtime.capability_controller
                if controller is None or not retype.applies(controller):
                    continue
            _carry_over(
                registry,
                entry,
                retype,
                runtime.entity_unique_id(retype.old_key),
                runtime.entity_unique_id(retype.new_key),
            )
        for domain, key in NOW_ENABLED:
            entity_id = registry.async_get_entity_id(domain, DOMAIN, runtime.entity_unique_id(key))
            row = registry.async_get(entity_id) if entity_id else None
            if row is not None and row.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                registry.async_update_entity(row.entity_id, disabled_by=None)

    @callback
    def report(_hass: HomeAssistant) -> None:
        _async_report_references(hass, entry)

    # Automations and scripts load after integrations at startup. Every startup
    # reports from the rows' own record, so a cut-short first one loses nothing.
    async_at_started(hass, report)


@callback
def async_retyped_entities_built(
    hass: HomeAssistant,
    entry: ConfigEntry,
    built: Collection[tuple[str, str]],
    retained: Collection[tuple[str, str]],
) -> None:
    """Withdraw repair lines for replacements the bed turned out not to provide.

    Called by the sweep with the (domain, unique ID) pairs the entry's platforms
    built and those a controller says may still appear, once that record is
    authoritative. The sweep removes any other replacement row.
    """
    moves = _reported_moves(hass, entry)
    kept = [move for move in moves if (move["domain"], move["unique_id"]) in {*built, *retained}]
    if kept != moves:
        _async_update_issue(hass, entry, kept)


def _reported_moves(hass: HomeAssistant, entry: ConfigEntry) -> list[dict[str, str]]:
    """The repair's lines, with the replacement each one names; stored with the issue."""
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_PREFIX + entry.entry_id)
    stored = (issue.data or {}).get("moves") if issue is not None else None
    try:
        moves = json.loads(stored) if isinstance(stored, str) else []
    except ValueError:
        return []
    return [
        {
            key: str(move[key])
            for key in ("line", "domain", "unique_id", "kept", "tracked")
            if key in move
        }
        for move in moves
        if isinstance(move, dict) and {"line", "domain", "unique_id"} <= move.keys()
    ]


@callback
def _async_update_issue(
    hass: HomeAssistant, entry: ConfigEntry, moves: list[dict[str, str]]
) -> None:
    issue_id = ISSUE_PREFIX + entry.entry_id
    if not moves:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        config_entry_id=entry.entry_id,
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="retyped_entities",
        translation_placeholders={
            "bed": entry.title,
            "entities": "\n".join(move["line"] for move in moves),
        },
        # Issue data holds plain values, so the lines are stored as JSON.
        data={"moves": json.dumps(moves)},
    )


def _carry_over(
    registry: er.EntityRegistry,
    entry: ConfigEntry,
    retype: Retype,
    old_unique_id: str,
    new_unique_id: str,
) -> None:
    """Move the old row's identity and user settings to the new entity."""
    old_id = registry.async_get_entity_id(retype.old_domain, DOMAIN, old_unique_id)
    if old_id is None or registry.async_get_entity_id(retype.new_domain, DOMAIN, new_unique_id):
        return
    old = registry.async_get(old_id)
    assert old is not None
    if retype.old_domain == retype.new_domain:
        # The row itself carries over, with its entity ID and every setting.
        registry.async_update_entity(old_id, new_unique_id=new_unique_id)
        if not retype.identity_only:
            _remember(registry, old_id, old_id, old.id, options_changed=True)
        return
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
    _remember(registry, new.entity_id, old_id, old.id, options_changed=False)


@callback
def _remember(
    registry: er.EntityRegistry,
    entity_id: str,
    old_entity_id: str,
    old_registry_id: str,
    *,
    options_changed: bool,
) -> None:
    """Record on the new row which entity it replaced, until nothing names that one."""
    row = registry.async_get(entity_id)
    assert row is not None
    registry.async_update_entity_options(
        entity_id,
        DOMAIN,
        {
            **row.options.get(DOMAIN, {}),
            RETYPED_FROM: old_entity_id,
            RETYPED_FROM_ID: old_registry_id,
            RETYPED_OPTIONS: options_changed,
        },
    )


@callback
def _async_report_references(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Raise one repair per bed naming the automations and scripts to update.

    Built from the rows that still record an old entity. A row whose old entity
    nothing names any more forgets it, so its line and the repair go away. A
    row that kept its entity ID and only changed its options is still named by
    automations the user already fixed, so its line is raised once and kept.
    """
    registry = er.async_get(hass)
    reported = _reported_moves(hass, entry)
    rows = er.async_entries_for_config_entry(registry, entry.entry_id)
    recorded = {
        (row.domain, row.unique_id)
        for row in rows
        if isinstance(row.options.get(DOMAIN, {}).get(RETYPED_FROM), str)
    }
    # Kept lines stay, and so do lines an earlier version raised without a row
    # record. A tracked line whose record is gone was resolved: it goes, even if
    # a crash saved the cleared record before the issue.
    moves = [
        move
        for move in reported
        if move.get("kept")
        or not move.get("tracked")
        and (move["domain"], move["unique_id"]) not in recorded
    ]
    for row in rows:
        options = row.options.get(DOMAIN, {})
        old_entity_id = options.get(RETYPED_FROM)
        if not isinstance(old_entity_id, str):
            continue
        references = (old_entity_id, options.get(RETYPED_FROM_ID))
        users = entity_users(hass, [ref for ref in references if isinstance(ref, str)])
        options_changed = bool(options.get(RETYPED_OPTIONS))
        if not users or options_changed:
            # Reported once (an options change), or nothing names the old entity.
            registry.async_update_entity_options(
                row.entity_id,
                DOMAIN,
                {
                    key: value
                    for key, value in options.items()
                    if key not in (RETYPED_FROM, RETYPED_FROM_ID, RETYPED_OPTIONS)
                },
            )
            if not users:
                continue
        change = (
            f"{old_entity_id} (its options changed)"
            if options_changed
            else f"{old_entity_id} → {row.entity_id}"
        )
        line = f"- {change}: {', '.join(sorted(users))}"
        if all(move["line"] != line for move in moves):
            moves.append(
                {
                    "line": line,
                    "domain": row.domain,
                    "unique_id": row.unique_id,
                    **({"kept": "1"} if options_changed else {"tracked": "1"}),
                }
            )
    if moves != reported:
        _async_update_issue(hass, entry, moves)
