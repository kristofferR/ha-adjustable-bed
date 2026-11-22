"""ComfortFurniture in HA setup/Configure, entity/service scheduling and paired runtimes."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow, _per_side_refusal
from custom_components.adjustable_bed.const import (
    BED_TYPE_KEESON,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
    KEESON_VARIANT_COMFORTFURNITURE,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.detection import bed_type_choice, get_bed_type_options
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.profile_id import entry_profile_id
from custom_components.adjustable_bed.services import async_register_services
from tests.form_helpers import NEW_BED_ROUTES, finish_new_bed, start_new_bed
from tests.hold_lease_wire import virtual_clock
from tests.test_comfortfurniture import make_bed
from tests.test_ore_comfort_bed import _char, _entry, _written

APP = KEESON_VARIANT_COMFORTFURNITURE


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_new_install_route_has_fixed_capabilities(hass, route):
    choice = bed_type_choice(BED_TYPE_KEESON, APP)
    assert "ComfortFurniture" in {o["value"]: o["label"] for o in get_bed_type_options()}[choice]
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    from tests.test_detection import _make_service_info

    flow._discovery_info = _make_service_info(name="Selected receiver", service_uuids=[])
    flow._async_transport_note = AsyncMock(return_value="")
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    form = await start_new_bed(flow, route, choice)
    assert form["step_id"] == "finish_settings"
    await finish_new_bed(flow, form)
    data = flow._finish_with_verify.await_args.args[0]
    assert (data[CONF_BED_TYPE], data[CONF_PROTOCOL_VARIANT], data[CONF_MOTOR_COUNT]) == (
        BED_TYPE_KEESON,
        APP,
        4,
    )
    assert data[CONF_HAS_MASSAGE] and CONF_DISABLE_ANGLE_SENSING not in data
    assert data[CONF_MOTOR_PULSE_DELAY_MS] == 100
    assert hidden_generic_fields(BED_TYPE_KEESON, APP) == {
        CONF_MOTOR_COUNT,
        CONF_HAS_MASSAGE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_MOTOR_PULSE_DELAY_MS,
    }
    assert _per_side_refusal(
        (BED_TYPE_KEESON, APP), [(BED_TYPE_KEESON, APP)] * 2, {CONF_PROTOCOL_VARIANT: "sino"}
    ) == (CONF_PROTOCOL_VARIANT, "ComfortFurniture bedding")


async def test_configure_family_can_choose_app_and_stage_fixed_fields(hass):
    entry = _entry(hass, "base", 2)
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": "reconfigure", "entry_id": entry.entry_id}
    await flow.async_step_reconfigure()
    result = await flow.async_step_keeson_family({"choice": "ore_apps"})
    assert result["step_id"] == "keeson_app"
    result = await flow.async_step_keeson_app({"choice": f"keeson:{APP}"})
    assert result["step_id"] == "migration_confirm"
    assert flow._pending_entry[CONF_MOTOR_COUNT] == 4
    assert flow._manual_data[CONF_PROTOCOL_VARIANT] == APP
    # Configure stages changes, keeping the working entry intact.
    assert entry.data[CONF_PROTOCOL_VARIANT] == "base"


async def test_cross_service_gatt_uses_last_roles_without_setup_writes(
    hass, mock_coordinator_connected, mock_bleak_client
):
    first = _char(KEESON_BASE_WRITE_CHAR_UUID, ["write"])
    last = _char(KEESON_BASE_WRITE_CHAR_UUID, ["write-without-response"])
    notify = _char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    mock_bleak_client.services = [
        SimpleNamespace(uuid="arbitrary-one", characteristics=[first]),
        SimpleNamespace(uuid="arbitrary-two", characteristics=[notify, last]),
    ]
    coord = AdjustableBedCoordinator(hass, _entry(hass, APP, 2))
    await coord.async_connect()
    c = coord.controller
    assert c.profile.key == APP and entry_profile_id(coord.entry.data).endswith(APP)
    assert c.requires_notification_channel and not c.supports_single_address_pairing
    mock_bleak_client.write_gatt_char.assert_not_called()
    assert mock_bleak_client.start_notify.call_args.args[0] is notify
    with virtual_clock():
        await c.preset_flat()
    assert mock_bleak_client.write_gatt_char.call_args.args[0] is last
    assert mock_bleak_client.write_gatt_char.call_args.kwargs["response"] is False


@pytest.fixture
async def runtime(hass, mock_coordinator_connected, mock_bleak_client):
    c = await make_bed(hass, mock_bleak_client)
    coordinator = c._coordinator
    hass.data.setdefault(DOMAIN, {})[coordinator.entry.entry_id] = coordinator
    await async_register_services(hass)
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(coordinator, "async_ensure_connected", AsyncMock(return_value=True))
        )
        stack.enter_context(
            patch.object(coordinator, "_async_refresh_controller_auth", AsyncMock())
        )
        stack.enter_context(
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(coordinator, "both")], []),
            )
        )
        yield hass, coordinator, mock_bleak_client
    await coordinator.async_shutdown()


async def test_native_cover_publishes_hold_and_real_scheduler_releases(runtime):
    hass, coord, client = runtime
    spec = next(s for s in coord.controller.motor_control_specs if s.key == "waist")
    cover = AdjustableBedCover(coord, _build_cover_description(spec))
    cover.hass, cover.async_write_ha_state = hass, MagicMock()
    with virtual_clock():
        await cover.async_open_cover()
    assert _written(client) == ["e5fe1600000040c6"] * 2 + ["e5fe160000000006"]
    assert cover.extra_state_attributes["held_control_up"] == "waist_up"
    assert cover.extra_state_attributes["held_stop_scope"] == "side"
    assert cover.extra_state_attributes["hold_lease_mode"] == "stream"


async def test_card_lease_stop_invalidates_generation(runtime):
    hass, coord, client = runtime
    call = {
        "device_id": ["bed"],
        "motor": "back",
        "direction": "up",
        "duration_ms": 300,
        "hold_owner": "comfortfurniture-card",
        "hold_generation": 7,
    }
    with virtual_clock():
        first = asyncio.create_task(
            hass.services.async_call(DOMAIN, "timed_move", call, blocking=True)
        )
        await asyncio.sleep(0.2)
        count = len(_written(client))
        await hass.services.async_call(DOMAIN, "timed_move", call, blocking=True)
        assert len(_written(client)) == count
        await coord.async_stop_command()
        await first
        count = len(_written(client))
        with pytest.raises(ServiceValidationError, match="already stopped"):
            await hass.services.async_call(DOMAIN, "timed_move", call, blocking=True)
        assert len(_written(client)) == count
    frames = _written(client)
    index = frames.index("e5fe160000000006")
    assert frames[0] == "e5fe160000000105"
    assert all(frame == "e5fe160000000006" for frame in frames[index:])


async def test_all_target_memory_admission_precedes_any_command(runtime):
    hass, coord, client = runtime
    other = MagicMock(spec=AdjustableBedCoordinator)
    other.name, other.capability_controller = (
        "Other",
        MagicMock(memory_slot_count=0, supports_memory_presets=False),
    )
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coord, "both"), (other, "both")], []),
        ),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(
            DOMAIN, "goto_preset", {"device_id": ["bed", "other"], "preset": 1}, blocking=True
        )
    assert not _written(client)


@pytest.mark.parametrize("mode", ["concurrent", "sequential"])
async def test_two_receiver_pair_routes_only_requested_side(runtime, mode):
    hass, left, left_client = runtime
    right = AdjustableBedCoordinator(hass, _entry(hass, APP, 4, "AA:BB:CC:DD:08:51"))
    right_client = MagicMock(
        is_connected=True,
        services=left_client.services,
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        disconnect=AsyncMock(),
    )

    async def disconnect_right():
        right_client.is_connected = False

    right_client.disconnect.side_effect = disconnect_right
    right._client = right_client
    right._controller = await create_controller(right, BED_TYPE_KEESON, APP, right_client)
    await right.controller.start_notify()
    pair_entry = MockConfigEntry(domain=DOMAIN, data={"pair_id": "furniture-two-receiver"})
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, pair_entry, {"left": left, "right": right}, connection_mode=mode
    )

    async def disconnect_left(*_args, **_kwargs):
        left_client.is_connected = False
        left.controller.on_disconnect()

    try:
        with (
            patch.object(right, "async_ensure_connected", AsyncMock(return_value=True)),
            patch.object(right, "_async_refresh_controller_auth", AsyncMock()),
            patch.object(left, "async_disconnect", AsyncMock(side_effect=disconnect_left)),
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(pair, "right")], []),
            ),
            virtual_clock(),
        ):
            await hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["pair"], "control": "waist_down", "duration": 0.25},
                blocking=True,
            )
        assert not _written(left_client)
        assert _written(right_client)[0] == "e5fe160000008086"
        assert _written(right_client)[-1] == "e5fe160000000006"
    finally:
        await pair.async_shutdown()


async def test_real_ha_install_imports_profile_and_exposes_entities(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import entity_registry as er

    from tests.test_ore_comfort_bed import _services

    mock_bleak_client.services = _services(
        _char(KEESON_BASE_WRITE_CHAR_UUID, ["write-without-response"]),
        _char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"]),
    )
    entry = _entry(hass, APP, 4)
    await AdjustableBedCoordinator.async_import_tables(hass, entry.data)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    coord = hass.data[DOMAIN][entry.entry_id]
    assert await coord.async_connect()
    await hass.async_block_till_done()
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len([e for e in entities if e.domain == "cover"]) == 5
    wave = next(
        e.entity_id
        for e in entities
        if e.domain == "number" and "comfortfurniture_wave_level" in e.unique_id
    )
    mock_bleak_client.write_gatt_char.reset_mock()
    with virtual_clock():
        await hass.services.async_call(
            "number", "set_value", {"entity_id": wave, "value": 3}, blocking=True
        )
    assert _written(mock_bleak_client) == ["e5fe1610000023d3"]
    assert coord.controller.persisted_app_state["wave"] == 20
    await hass.config_entries.async_unload(entry.entry_id)


async def test_disconnect_clears_timer_selection(runtime):
    from custom_components.adjustable_bed.select import (
        MASSAGE_TIMER_DESCRIPTION,
        AdjustableBedMassageTimerSelect,
    )

    hass, coord, client = runtime
    controller = coord.controller
    assert not controller.massage_timer_can_turn_off
    timer = AdjustableBedMassageTimerSelect(
        coord, MASSAGE_TIMER_DESCRIPTION, controller.massage_timer_options, has_off=False
    )
    assert timer.options == ["10 min", "20 min", "30 min"]
    timer.hass = hass
    timer.async_write_ha_state = MagicMock()
    with virtual_clock():
        await timer.async_select_option("20 min")
    assert timer.current_option == "20 min"

    await coord.async_disconnect()
    assert timer.current_option is None
    assert await coord.async_connect()
    assert timer.current_option is None


async def _massage_switch(hass, coord):
    from custom_components.adjustable_bed.switch import (
        AdjustableBedControllerSwitch,
        _switch_entities_for,
    )

    (switch,) = [e for e in _switch_entities_for(hass, coord) if isinstance(e, AdjustableBedControllerSwitch)]
    switch.hass = hass
    switch.entity_id = "switch.massage"
    switch.async_write_ha_state = MagicMock()
    await switch.async_added_to_hass()
    return switch


async def test_massage_switch_shows_the_last_sent_command(runtime):
    hass, coord, client = runtime
    assert not coord.controller.supports_massage_off_control  # the switch replaces it
    switch = await _massage_switch(hass, coord)
    try:
        # The bed never reports massage, so the switch shows what it sent.
        assert switch.is_on is None and switch.assumed_state
        client.write_gatt_char.reset_mock()
        with virtual_clock():
            await switch.async_turn_on()
        assert _written(client) == ["e5fe1610000011e5", "e5fe1610000022d4", "e5fe1610000012e4"]
        assert switch.is_on is True
        with virtual_clock():
            await switch.async_turn_off()
        assert _written(client)[-1] == "e5fe1610000010e6"
        assert switch.is_on is False
        # The integration's own disconnect says nothing about the bed.
        await coord.async_disconnect()
        assert switch.is_on is False
    finally:
        await switch.async_will_remove_from_hass()


async def test_massage_switch_keeps_its_state_when_nothing_was_sent(runtime):
    from bleak.exc import BleakError

    hass, coord, client = runtime
    switch = await _massage_switch(hass, coord)
    try:
        with virtual_clock():
            await switch.async_turn_on()
        assert switch.is_on is True
        # A write the bed rejects leaves the shown state unchanged.
        client.write_gatt_char.side_effect = BleakError("rejected")
        with virtual_clock(), pytest.raises(BleakError):
            await switch.async_turn_off()
        assert switch.is_on is True
        client.write_gatt_char.side_effect = None

        # STOP during the real Off command's pre-write wait: no frame, no new state.
        client.write_gatt_char.reset_mock()
        turning_off = asyncio.create_task(switch.async_turn_off())
        for _ in range(5):
            await asyncio.sleep(0)
        await coord.async_stop_command()
        await asyncio.gather(turning_off, return_exceptions=True)
        assert "e5fe1610000010e6" not in _written(client)
        assert switch.is_on is True
    finally:
        await switch.async_will_remove_from_hass()
