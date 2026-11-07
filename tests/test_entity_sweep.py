"""The registry sweep that retires rows an entry's platforms no longer create.

It replaced 19 per-platform cleanup helpers. ``RETIRED_HELPER_CASES`` maps
each helper to a row it used to remove, built from the controller state that
helper handled, and proves the sweep removes the same row.
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib import import_module
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import _build_paired_children
from custom_components.adjustable_bed.beds.base import (
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    build_position_number_spec,
)
from custom_components.adjustable_bed.beds.rmcontrol.protocol import Notification
from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    BED_TYPE_MOTION_BED,
    BED_TYPE_OKIMAT,
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    BED_TYPE_SLEEP_NUMBER,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    DOMAIN,
    PAIR_MODE_SINGLE_ADDRESS,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.entity_discovery import async_setup_dynamic_entities
from custom_components.adjustable_bed.entity_sweep import (
    _LEDGERS,
    EntityLedger,
    PlatformEntities,
    async_sweep_after_setup,
)
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    SingleAddressPairedCoordinator,
)
from custom_components.adjustable_bed.paired_devices import async_register_children
from tests.conftest import make_controller_mock
from tests.test_paired_setup import LEFT_ADDR, PAIR_ID, RIGHT_ADDR, _paired_entry

ADDRESS = "AA:BB:CC:DD:EE:5A"
PLATFORMS = (
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
)


async def async_setup_platforms_and_sweep(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator | PairedBedCoordinator,
    platforms: Iterable[Platform] = PLATFORMS,
) -> list[Entity]:
    """Set up the platforms as entry setup does, sweep, and return the created entities."""
    platforms = tuple(platforms)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    # Each call is a fresh setup of the entry.
    hass.data.get(_LEDGERS, {}).pop(entry.entry_id, None)
    if isinstance(coordinator, PairedBedCoordinator):
        dr.async_get(hass).async_get_or_create_from_info(
            config_entry_id=entry.entry_id, device_info=coordinator.device_info
        )
        async_register_children(hass, coordinator)
    created: list[Entity] = []

    def add(entities: Iterable[Entity], update_before_add: bool = False) -> None:
        created.extend(entities)

    for platform in platforms:
        module = import_module(f"custom_components.adjustable_bed.{platform}")
        await module.async_setup_entry(hass, entry, add)
    async_sweep_after_setup(hass, entry, platforms)
    return created


def _entry(hass: HomeAssistant, **data: Any) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sweep Bed",
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Sweep Bed",
            CONF_BED_TYPE: BED_TYPE_OKIMAT,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            **data,
        },
        unique_id=ADDRESS,
    )
    entry.add_to_hass(hass)
    return entry


def _coordinator(hass: HomeAssistant, entry: MockConfigEntry, controller: object) -> AdjustableBedCoordinator:
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._controller = controller  # type: ignore[assignment]
    return coordinator


def _row(hass: HomeAssistant, entry: MockConfigEntry, domain: str, key: str) -> er.RegistryEntry:
    return er.async_get(hass).async_get_or_create(
        domain, DOMAIN, f"{ADDRESS}_{key}", config_entry=entry
    )


def _exists(hass: HomeAssistant, row: er.RegistryEntry) -> bool:
    return er.async_get(hass).async_get(row.entity_id) is not None


# --- The mechanism -----------------------------------------------------------


async def test_sweep_removes_only_this_entrys_uncreated_rows(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    coordinator = _coordinator(hass, entry, make_controller_mock())
    stale = _row(hass, entry, "number", "massage_head_intensity")
    created = _row(hass, entry, "binary_sensor", "ble_connection")
    disabled = er.async_get(hass).async_update_entity(
        _row(hass, entry, "button", "stop").entity_id,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    other_entry = MockConfigEntry(domain=DOMAIN, data={})
    other_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    other_entrys = registry.async_get_or_create(
        "number", DOMAIN, f"{ADDRESS}_x_massage_head_intensity", config_entry=other_entry
    )
    other_platform = registry.async_get_or_create(
        "number", "other", f"{ADDRESS}_massage_head_intensity", config_entry=entry
    )

    await async_setup_platforms_and_sweep(hass, entry, coordinator)

    assert not _exists(hass, stale)
    assert _exists(hass, created)
    # A disabled entity the platform still creates keeps its row.
    assert _exists(hass, disabled)
    assert _exists(hass, other_entrys)
    assert _exists(hass, other_platform)


async def test_sweep_waits_for_every_forwarded_platform(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    coordinator = _coordinator(hass, entry, make_controller_mock())
    stale = _row(hass, entry, "number", "massage_head_intensity")
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    number = import_module("custom_components.adjustable_bed.number")
    button = import_module("custom_components.adjustable_bed.button")

    await number.async_setup_entry(hass, entry, MagicMock())
    with (
        patch.object(button, "_button_entities_for", side_effect=RuntimeError),
        pytest.raises(RuntimeError),
    ):
        await button.async_setup_entry(hass, entry, MagicMock())
    # The button platform raised, so what it did not create proves nothing.
    async_sweep_after_setup(hass, entry, (Platform.NUMBER, Platform.BUTTON))

    assert _exists(hass, stale)


@pytest.mark.parametrize("state", ["no_controller", "discovery_incomplete"])
async def test_unknown_capabilities_keep_every_row(hass: HomeAssistant, state: str) -> None:
    entry = _entry(hass, **{CONF_HAS_MASSAGE: True})
    controller = (
        None
        if state == "no_controller"
        else make_controller_mock(controller_entity_discovery_complete=False)
    )
    coordinator = _coordinator(hass, entry, controller)
    stale = _row(hass, entry, "number", "massage_head_intensity")

    await async_setup_platforms_and_sweep(hass, entry, coordinator)

    assert _exists(hass, stale)


class _DynamicPlatforms:
    """Dynamic builders on several platforms of one entry, as Home Assistant runs them."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MockConfigEntry,
        coordinator: AdjustableBedCoordinator,
        offered: dict[str, set[str]],
    ) -> None:
        self._hass = hass
        self.offered = offered
        self.added: list[str] = []
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        ledger = EntityLedger(hass, entry, coordinator)
        ledger.platforms_forwarded(offered)
        self._callbacks: list[Any] = []
        with patch.object(
            coordinator,
            "register_controller_state_callback",
            side_effect=lambda fn: self._callbacks.append(fn) or (lambda: None),
        ):
            for domain in offered:
                sink = PlatformEntities(ledger, domain, self._add_for(domain))
                async_setup_dynamic_entities(entry, coordinator, sink, self._builder(domain))
                ledger.platform_finished(domain)
        ledger.async_sweep()

    def _builder(self, domain: str) -> Any:
        def build() -> list[Entity]:
            entities = []
            for key in sorted(self.offered[domain]):
                entity = Entity()
                entity._attr_unique_id = f"{ADDRESS}_{key}"
                entities.append(entity)
            return entities

        return build

    def _add_for(self, domain: str) -> Any:
        def add(entities: Iterable[Entity], update_before_add: bool = False) -> None:
            for entity in entities:
                entity.entity_id = f"{domain}.{entity.unique_id}".lower().replace(":", "_")
                self.added.append(str(entity.unique_id))

        return add

    async def report(self) -> None:
        """Deliver one controller report to every builder, then let a sweep run."""
        for callback in self._callbacks:
            callback({})
        await self._hass.async_block_till_done()


async def test_dynamic_builder_retires_and_restores_a_withdrawn_entity(
    hass: HomeAssistant,
) -> None:
    entry = _entry(hass)
    controller = make_controller_mock(
        has_dynamic_controller_entities=True, controller_entity_discovery_complete=False
    )
    platforms = _DynamicPlatforms(
        hass, entry, _coordinator(hass, entry, controller), {"sensor": {"a", "b"}}
    )
    rows = {key: _row(hass, entry, "sensor", key) for key in ("a", "b")}
    assert len(platforms.added) == 2

    # Unfinished discovery is no proof that "b" is gone.
    platforms.offered["sensor"].discard("b")
    await platforms.report()
    assert _exists(hass, rows["b"])

    controller.controller_entity_discovery_complete = True
    await platforms.report()
    assert not _exists(hass, rows["b"])
    assert _exists(hass, rows["a"])

    # A later report brings the capability back under the same identity.
    platforms.offered["sensor"].add("b")
    await platforms.report()
    assert platforms.added[2:] == [f"{ADDRESS}_b"]


async def test_sweep_waits_for_every_builder_answering_a_report(hass: HomeAssistant) -> None:
    """A builder refreshed later in the same report keeps its row."""
    entry = _entry(hass)
    controller = make_controller_mock(
        has_dynamic_controller_entities=True, controller_entity_discovery_complete=False
    )
    # The sensor builder answers first; the light appears with the same report.
    platforms = _DynamicPlatforms(
        hass, entry, _coordinator(hass, entry, controller), {"sensor": {"a"}, "light": set()}
    )
    light = _row(hass, entry, "light", "lamp")

    controller.controller_entity_discovery_complete = True
    platforms.offered["light"].add("lamp")
    await platforms.report()

    assert _exists(hass, light)
    assert platforms.added[-1] == f"{ADDRESS}_lamp"


# --- Every case the retired helpers handled -----------------------------------


async def _set(_controller: object, _value: object) -> None:
    """Never called: the sweep only reads specs."""


_KEPT_NUMBER = ControllerNumberSpec("kept", "kept", "kept", 0, 10, 1, _set)
_KEPT_SELECT = ControllerSelectSpec("kept", "kept", "kept", ("a",), _set)
_KEPT_SENSOR = ControllerStateSensorSpec("kept_state", "kept_state", "kept_state", "mdi:bed")
_KEPT_BINARY = ControllerStateBinarySensorSpec("kept_flag", "kept_flag", "kept_flag", "mdi:bed")

# (retired helper, entry data, controller state, rows it removed, rows that stay)
RETIRED_HELPER_CASES = [
    pytest.param(
        {CONF_BED_TYPE: BED_TYPE_RICHMAT_CLASSIC_APPS},
        {},
        [("number", "back_position"), ("number", "legs_position_left")],
        [],
        id="number._async_remove_stale_position_entities-no_feedback",
    ),
    pytest.param(
        {CONF_BED_TYPE: BED_TYPE_LINAK, CONF_DISABLE_ANGLE_SENSING: False},
        {"position_number_specs": (build_position_number_spec("back", max_value=68, unit="°"),)},
        [("number", "legs_position")],
        [("number", "back_position")],
        id="number._async_remove_stale_position_entities-pruned_axes",
    ),
    pytest.param(
        {},
        {},
        [("number", "massage_head_intensity"), ("number", "massage_right_intensity")],
        [],
        id="number._async_remove_stale_massage_entities",
    ),
    pytest.param(
        {},
        {},
        [("number", "light_level"), ("number", "fan_level")],
        [],
        id="number._async_remove_stale_level_entity",
    ),
    pytest.param(
        {},
        {
            "sleep_number_setting_sides": ("left", "right"),
            "sleep_number_setting_min": 5,
            "sleep_number_setting_max": 100,
            "sleep_number_setting_step": 5,
        },
        [("number", "sleep_number_setting")],
        [("number", "sleep_number_setting_left"), ("number", "sleep_number_setting_right")],
        id="number._async_remove_stale_sleep_number_entity",
    ),
    pytest.param(
        {},
        {"controller_number_specs": (_KEPT_NUMBER,)},
        [("number", "controller_number_retired")],
        [("number", "controller_number_kept")],
        id="number._async_remove_stale_controller_numbers",
    ),
    pytest.param(
        {CONF_BED_TYPE: BED_TYPE_RICHMAT_CLASSIC_APPS, CONF_DISABLE_ANGLE_SENSING: False},
        {},
        [("sensor", "back_angle"), ("sensor", "legs_angle")],
        [],
        id="sensor._async_remove_stale_angle_entities",
    ),
    pytest.param(
        {},
        {"controller_state_sensor_specs": (_KEPT_SENSOR,)},
        [
            ("sensor", "serenity_status_code"),
            ("sensor", "linak_model_variant"),
            ("sensor", "motion_bed_retired"),
        ],
        [("sensor", "kept_state")],
        id="sensor._async_remove_stale_sensor_entities",
    ),
    pytest.param(
        {},
        {"controller_select_specs": (_KEPT_SELECT,)},
        [("select", "controller_select_retired")],
        [("select", "controller_select_kept")],
        id="select._async_remove_stale_controller_selects",
    ),
    pytest.param(
        {},
        {},
        [("select", "massage_timer"), ("select", "light_timer")],
        [],
        id="select._async_remove_stale_select_entity",
    ),
    pytest.param(
        {},
        {},
        [("light", "under_bed_lights")],
        [],
        id="light._async_remove_stale_light_entity",
    ),
    pytest.param(
        {},
        {
            "supports_light_color_control": True,
            "supports_discrete_light_control": True,
            "supported_color_modes": frozenset({"rgb"}),
        },
        [("switch", "under_bed_lights")],
        [("light", "under_bed_lights")],
        id="light._async_remove_stale_switch_entity",
    ),
    pytest.param(
        {},
        {},
        [("cover", "motor_1"), ("cover", "motion_bed_hip")],
        [],
        id="cover._async_remove_stale_cover_entities",
    ),
    pytest.param(
        {CONF_BED_TYPE: BED_TYPE_SLEEP_NUMBER},
        {"thermal_climate_sides": ("left", "right")},
        [("climate", "sleep_number_thermal_climate")],
        [("climate", "sleep_number_thermal_climate_left")],
        id="climate._async_remove_stale_split_climate_entity",
    ),
    pytest.param(
        {},
        {"memory_slot_count": 2},
        [
            ("button", "preset_memory_4"),
            ("button", "product_action_retired"),
            ("button", "octo_retired"),
        ],
        [("button", "stop")],
        id="button._async_remove_stale_button_entities",
    ),
    pytest.param(
        {},
        {"supports_bed_presence": True, "bed_presence_sides": ("left", "right")},
        [("binary_sensor", "bed_presence")],
        [("binary_sensor", "bed_presence_left")],
        id="binary_sensor._async_remove_stale_presence_entity",
    ),
    pytest.param(
        {},
        {"controller_state_binary_sensor_specs": (_KEPT_BINARY,)},
        [("binary_sensor", "furnimove_ubl"), ("binary_sensor", "bedsense_retired")],
        [("binary_sensor", "kept_flag")],
        id="binary_sensor._async_remove_stale_controller_state_binary_sensor_entities",
    ),
    pytest.param(
        {},
        {},
        [("sensor", "rmcontrol_capability_light"), ("binary_sensor", "rmcontrol_alarm_on")],
        [],
        id="entity_discovery.async_remove_retired_rmcontrol_telemetry",
    ),
    pytest.param(
        {},
        {},
        [("switch", "automatic_light")],
        [],
        id="switch-unsupported_inline_removal",
    ),
]


@pytest.mark.parametrize(("data", "state", "removed", "kept"), RETIRED_HELPER_CASES)
async def test_sweep_removes_what_each_retired_helper_removed(
    hass: HomeAssistant,
    data: dict[str, Any],
    state: dict[str, Any],
    removed: list[tuple[str, str]],
    kept: list[tuple[str, str]],
) -> None:
    entry = _entry(hass, **data)
    coordinator = _coordinator(hass, entry, make_controller_mock(**state))
    stale = [_row(hass, entry, domain, key) for domain, key in removed]
    current = [_row(hass, entry, domain, key) for domain, key in kept]

    created = await async_setup_platforms_and_sweep(hass, entry, coordinator)

    assert {row.unique_id for row in current} <= {entity.unique_id for entity in created}
    assert [row.entity_id for row in stale if _exists(hass, row)] == []
    assert all(_exists(hass, row) for row in current)


# --- Paired entries ------------------------------------------------------------


def _pair(
    hass: HomeAssistant, controllers: dict[str, object | None]
) -> tuple[MockConfigEntry, PairedBedCoordinator]:
    entry = _paired_entry(hass)
    children = _build_paired_children(hass, entry)
    for side, child in children.items():
        child._controller = controllers.get(side)  # type: ignore[assignment]
    present = {side: child for side, child in children.items() if side in controllers}
    return entry, PairedBedCoordinator(hass, entry, present)


def _pair_rows(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, er.RegistryEntry]:
    registry = er.async_get(hass)
    rows = {
        "left_stale": ("number", f"{LEFT_ADDR}_massage_head_intensity"),
        "right_stale": ("number", f"{RIGHT_ADDR}_massage_head_intensity"),
        "left_current": ("binary_sensor", f"{LEFT_ADDR}_ble_connection"),
        "right_current": ("binary_sensor", f"{RIGHT_ADDR}_ble_connection"),
        "both_slider": ("number", f"{PAIR_ID}_back_position_both"),
        "both_button": ("button", f"{PAIR_ID}_preset_memory_4_both"),
    }
    return {
        name: registry.async_get_or_create(domain, DOMAIN, unique_id, config_entry=entry)
        for name, (domain, unique_id) in rows.items()
    }


async def test_known_pair_retires_each_sides_and_combined_rows(hass: HomeAssistant) -> None:
    """Covers the combined number and button helpers; each side keeps its own rows."""
    entry, pair = _pair(
        hass,
        {
            "left": make_controller_mock(memory_slot_count=4),
            "right": make_controller_mock(memory_slot_count=2),
        },
    )
    rows = _pair_rows(hass, entry)

    await async_setup_platforms_and_sweep(hass, entry, pair)

    gone = {name for name, row in rows.items() if not _exists(hass, row)}
    assert gone == {"left_stale", "right_stale", "both_slider", "both_button"}


@pytest.mark.parametrize("unknown", ["offline_side", "side_kept_by_original_entry"])
async def test_pair_with_an_unknown_side_keeps_every_row(hass: HomeAssistant, unknown: str) -> None:
    controllers: dict[str, object | None] = {"left": make_controller_mock()}
    if unknown == "offline_side":
        controllers["right"] = None
    entry, pair = _pair(hass, controllers)
    rows = _pair_rows(hass, entry)

    await async_setup_platforms_and_sweep(hass, entry, pair)

    assert all(_exists(hass, row) for row in rows.values())


async def test_single_address_pair_keeps_both_sides_rows(hass: HomeAssistant) -> None:
    entry = _entry(hass, **{CONF_PAIR_ID: "pair_sweep", CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS})
    pair = SingleAddressPairedCoordinator(
        hass, entry, _coordinator(hass, entry, make_controller_mock())
    )
    registry = er.async_get(hass)

    def row(key: str) -> er.RegistryEntry:
        return registry.async_get_or_create("number", DOMAIN, f"{ADDRESS}_{key}", config_entry=entry)

    stale = [row("massage_head_intensity_left"), row("massage_head_intensity_right")]
    current = [
        registry.async_get_or_create(
            "binary_sensor", DOMAIN, f"{ADDRESS}_ble_connection_{side}", config_entry=entry
        )
        for side in ("left", "right")
    ]

    await async_setup_platforms_and_sweep(hass, entry, pair)

    assert not any(_exists(hass, entity) for entity in stale)
    assert all(_exists(hass, entity) for entity in current)


# --- Rows kept for a later report ------------------------------------------------


async def test_rows_a_controller_still_expects_are_kept(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    controller = make_controller_mock(
        retained_entity_keys=frozenset({("sensor", "reported_later")})
    )
    coordinator = _coordinator(hass, entry, controller)
    expected = _row(hass, entry, "sensor", "reported_later")
    other_domain = _row(hass, entry, "binary_sensor", "reported_later")

    await async_setup_platforms_and_sweep(hass, entry, coordinator)

    assert _exists(hass, expected)
    assert not _exists(hass, other_domain)


async def test_motion_bed_hub_expects_every_module_control(hass: HomeAssistant) -> None:
    """Replaces the button helper's hub allowance: modules report after connecting."""
    from custom_components.adjustable_bed.beds.motion_bed.controller import MotionBedController
    from custom_components.adjustable_bed.beds.motion_bed.models import select_motion_bed

    entry = _entry(hass, **{CONF_BED_TYPE: BED_TYPE_MOTION_BED})
    coordinator = AdjustableBedCoordinator(hass, entry)
    hub = MotionBedController(coordinator, selection=select_motion_bed("TL-Q"))
    module = MotionBedController(coordinator, selection=select_motion_bed("TL-A"))

    expected = {key for domain, key in hub.retained_entity_keys if domain == "button"}
    # Before any module reports, the hub builds only a strict subset of them.
    assert {spec.key for spec in hub.controller_button_specs} < expected
    assert module.retained_entity_keys == frozenset()


def test_rmcontrol_expects_reported_telemetry_and_pending_light() -> None:
    """Replaces the RMControl telemetry helper and the pending-light allowances."""
    from tests.test_rmcontrol import controller

    strip = controller("6ERM", nordic=True)
    expected = strip.retained_entity_keys
    assert {("sensor", "rmcontrol_music_volume"), ("binary_sensor", "rmcontrol_music_playing")} <= expected
    assert {("light", "under_bed_lights"), ("select", "light_timer")} <= expected
    strip._accept_notification(Notification("capability", {"light": True}))
    assert not {("light", "under_bed_lights"), ("select", "light_timer")} & strip.retained_entity_keys
