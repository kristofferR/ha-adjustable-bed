"""Source-prepared naming/exposure and app-local diagnostic action coverage."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed.beds.keeson import betterliving2_services as actions
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.light import AdjustableBedOnOffLight, _light_entities_for
from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
from custom_components.adjustable_bed.paired_coordinator import entity_runtimes
from custom_components.adjustable_bed.profiles import betterliving2 as wire
from custom_components.adjustable_bed.select import _select_entities_for
from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.switch import _switch_entities_for
from tests.hold_lease_wire import virtual_clock
from tests.test_betterliving2_delivery import startup
from tests.test_betterliving2_holds_and_sides import observed, ready
from tests.test_betterliving2_runtime import bed, pair, writes
from tests.test_entity_sweep import async_setup_platforms_and_sweep

STRINGS = json.loads(
    (Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json").read_text()
)["entity"]
REMOVED = (
    ("button", "betterliving2_refresh_alarm"),
    ("button", "betterliving2_sync_clock"),
    ("button", "betterliving2_refresh_massage"),
    ("number", "betterliving2_massage_timer"),
    ("sensor", "betterliving2_alarm_selection"),
)


async def test_p1_light_is_one_assumed_on_off_light_without_a_timer(hass):
    child, _, _, _ = await bed(hass)
    try:
        lights = _light_entities_for(hass, child)
        assert len(lights) == 1
        light = lights[0]
        assert isinstance(light, AdjustableBedOnOffLight)
        assert light.supported_color_modes == {ColorMode.ONOFF}
        assert light.assumed_state is True
        assert light.is_on is None
        assert all(
            entity.translation_key != "under_bed_lights"
            for entity in _switch_entities_for(hass, child)
        )
        assert not _select_entities_for(hass, child)
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("cancel_at", (None, "before", "after"))
async def test_real_p1_light_shows_only_its_sent_command(hass, cancel_at):
    from custom_components.adjustable_bed.command_scheduler import current_command_context

    child, controller, client, _ = await bed(hass)
    light = _light_entities_for(hass, child)[0]
    light.async_write_ha_state = MagicMock()
    original = controller.lights_on
    contexts = []

    async def turn_on():
        context = current_command_context()
        assert context is not None
        if cancel_at == "before":
            context.cancel_event.set()
        await original()

    async def sent(*_args, **_kwargs):
        if cancel_at == "after":
            context = current_command_context()
            assert context is not None
            contexts.append(context)
            context.cancel_event.set()

    try:
        with ready(child), virtual_clock():
            await startup(controller)
            client.write_gatt_char.reset_mock()
            client.write_gatt_char.side_effect = sent
            with patch.object(controller, "lights_on", turn_on):
                await light.async_turn_on()
        assert len(writes(client)) == (0 if cancel_at == "before" else 1)
        if cancel_at == "after":
            assert len(contexts) == 1
            assert contexts[0].frames_written == 1
            assert contexts[0].frames_skipped == 0
        assert light.is_on is (None if cancel_at == "before" else True)
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("zone", ("head", "feet"))
async def test_real_p1_intensity_number_can_send_its_zero_minimum(hass, zone):
    child, controller, client, _ = await bed(hass)
    spec = next(
        spec
        for spec in controller.controller_number_specs
        if spec.key == f"betterliving2_massage_{zone}"
    )
    number = AdjustableBedControllerNumber(child, spec)
    frozen = json.loads((Path(__file__).parent / "fixtures/betterliving2/vectors.json").read_text())
    expected = next(
        row["expected_bytes"]
        for row in frozen
        if row["protocol"] == "P1"
        and row["kind"] == "command"
        and row["inputs"]["opcode"] == wire.P1_MASSAGE_BASES[zone]
    )
    try:
        assert number.native_min_value == 0
        assert number.native_max_value == 3
        with ready(child), virtual_clock():
            await startup(controller)
            client.write_gatt_char.reset_mock()
            await number.async_set_native_value(0)
        assert [frame.hex() for frame in writes(client)] == [expected]
        assert number.native_value == 0
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("protocol", ("p1", "p2", "p3"))
@pytest.mark.parametrize("layout", ("2", "3"))
async def test_native_names_types_exposure_and_retained_ids(hass, protocol, layout):
    child, controller, client, _ = await bed(hass, protocol, layout)
    view = next(iter(entity_runtimes(child)))
    entities = []
    try:
        for spec in controller.motor_control_specs:
            entity = AdjustableBedCover(view, _build_cover_description(spec))
            assert entity.unique_id == view.entity_unique_id(spec.key)
            entities.append(("cover", entity))
            if spec.key == "both":
                assert entity.translation_key == "betterliving2_all_sections"
        for spec in controller.controller_button_specs:
            entity = ControllerActionButton(view, spec)
            assert entity.unique_id == view.entity_unique_id(spec.key)
            assert entity.translation_key == spec.translation_key
            entities.append(("button", entity))
        for spec in controller.controller_number_specs:
            entity = AdjustableBedControllerNumber(view, spec)
            assert entity.unique_id == view.entity_unique_id(f"controller_number_{spec.key}")
            entities.append(("number", entity))
        for spec in controller.controller_state_sensor_specs:
            entity = AdjustableBedControllerStateSensor(view, spec)
            assert entity.unique_id == view.entity_unique_id(spec.key)
            # Every massage reading is dashboard state; only head and foot sit on the card.
            assert entity.entity_category is None
            assert entity.entity_registry_enabled_default
            if spec.key.endswith(("_wave", "_timer")):
                assert entity._card.attributes["card_section"] == "hidden"
            entities.append(("sensor", entity))
        names = [
            STRINGS[domain][entity.translation_key]["name"].format_map(
                getattr(entity, "_attr_translation_placeholders", None) or {}
            )
            for domain, entity in entities
        ]
        assert len(names) == len(set(names))
        assert "All sections" in names and "Save Zero Gravity" in names
        assert not {(domain, entity.translation_key) for domain, entity in entities} & set(REMOVED)
        if protocol == "p1":
            assert "Cycle massage timer" not in names
            assert {spec.key for spec in controller.controller_number_specs} == {
                "betterliving2_massage_head",
                "betterliving2_massage_feet",
                "betterliving2_massage_wave",
            }
        else:
            assert {spec.name for spec in controller.controller_button_specs} >= {
                "Cycle massage timer",
                "Toggle massage",
                "Cycle massage wave",
            }
        details = controller.protocol_diagnostics
        assert {"alarm_selection", "alarm_preferences", "massage_settings"} <= details.keys()
        assert not writes(client)
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("protocol", ("p1", "p2", "p3"))
async def test_native_sweep_removes_retired_entities_and_keeps_retained_identity(hass, protocol):
    child, _, _, device = await bed(hass, protocol)
    view = next(iter(entity_runtimes(child)))
    registry = er.async_get(hass)
    old_rows = [
        registry.async_get_or_create(
            domain,
            DOMAIN,
            view.entity_unique_id(f"controller_number_{key}" if domain == "number" else key),
            config_entry=child.entry,
            device_id=device.id,
        )
        for domain, key in REMOVED
    ]
    domain = "number" if protocol == "p1" else "sensor"
    retained = registry.async_get_or_create(
        domain,
        DOMAIN,
        view.entity_unique_id(
            "controller_number_betterliving2_massage_head"
            if domain == "number"
            else "betterliving2_massage_head"
        ),
        config_entry=child.entry,
        device_id=device.id,
    )
    try:
        await async_setup_platforms_and_sweep(hass, child.entry, child)
        await hass.async_block_till_done()
        assert all(registry.async_get(row.entity_id) is None for row in old_rows)
        assert registry.async_get(retained.entity_id).id == retained.id
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("protocol", ("p2", "p3"))
async def test_registered_diagnostic_massage_query_remains_reachable(hass, protocol):
    child, _, client, device = await bed(hass, protocol)
    await async_register_services(hass)
    try:
        with ready(child), virtual_clock():
            await hass.services.async_call(
                DOMAIN,
                "betterliving2_diagnostic_action",
                {"device_id": [device.id], "action": "refresh_massage"},
                blocking=True,
            )
        assert writes(client) == [wire.massage_query(protocol.upper())]
    finally:
        await child.async_shutdown()


async def test_diagnostic_capability_preflight_validates_every_native_child(hass):
    parent, attached, ids = await pair(hass)
    await async_register_services(hass)
    try:
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "betterliving2_diagnostic_action",
                {
                    "device_id": [ids["right"], ids["left"]],
                    "action": "refresh_massage",
                },
                blocking=True,
            )
        assert all(not writes(client) for _, client in attached.values())
    finally:
        await parent.async_shutdown()


async def test_diagnostic_stop_during_lazy_import_retires_original_admission(hass):
    child, _, client, device = await bed(hass, "p2")
    await async_register_services(hass)
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_import(*_args):
        entered.set()
        async with asyncio.timeout(15):
            await release.wait()

    try:
        with (
            patch.object(actions, "async_import_modules", delayed_import),
            ready(child),
            virtual_clock(),
        ):
            call = asyncio.create_task(
                hass.services.async_call(
                    DOMAIN,
                    "betterliving2_diagnostic_action",
                    {"device_id": [device.id], "action": "refresh_massage"},
                    blocking=True,
                )
            )
            await observed(entered, call)
            await child.async_stop_command()
            boundary = len(writes(client))
            release.set()
            await call
            assert len(writes(client)) == boundary
    finally:
        release.set()
        await child.async_shutdown()


@pytest.mark.parametrize("drift", ("session", "profile"))
async def test_diagnostic_query_rejects_replacement_before_admission(hass, drift):
    child, controller, client, device = await bed(hass, "p2")
    await async_register_services(hass)
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_import(*_args):
        entered.set()
        async with asyncio.timeout(15):
            await release.wait()

    try:
        with (
            patch.object(actions, "async_import_modules", delayed_import),
            ready(child),
            virtual_clock(),
        ):
            call = asyncio.create_task(
                hass.services.async_call(
                    DOMAIN,
                    "betterliving2_diagnostic_action",
                    {"device_id": [device.id], "action": "refresh_massage"},
                    blocking=True,
                )
            )
            await observed(entered, call)
            if drift == "session":
                controller.on_disconnect()
                await controller.async_discover_capabilities()
            else:
                hass.config_entries.async_update_entry(
                    child.entry,
                    data={**child.entry.data, "product_type": "3"},
                )
            release.set()
            with pytest.raises(ServiceValidationError):
                await call
            assert not writes(client)
    finally:
        release.set()
        await child.async_shutdown()
