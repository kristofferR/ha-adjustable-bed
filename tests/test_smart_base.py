"""Smart Base's selected native panel, setup, reports and captured link ownership."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.richmat.smart_base import SmartBaseController
from custom_components.adjustable_bed.button import (
    _button_entities_for,
    _combined_motor_buttons_for,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles import smart_base as p
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from tests.error_helpers import raises_key
from tests.form_helpers import finish_new_bed
from tests.hold_lease_wire import virtual_clock
from tests.test_atlas_lift import client_on, frames, packet_info, session_for
from tests.test_richmat_family_flow import setup_flow


def service():
    return SimpleNamespace(
        uuid=p.SERVICE,
        characteristics=[
            SimpleNamespace(uuid=p.TX, properties=["write"], handle=1, descriptors=[]),
            SimpleNamespace(uuid=p.RX, properties=["notify"], handle=2, descriptors=[]),
        ],
    )


def controller(client=None):
    client = client or client_on(service())
    coordinator = MagicMock(client=client, cancel_command=asyncio.Event(), motor_pulse_count=3)
    coordinator.entry.data = {const.CONF_PRODUCT_TYPE: p.PRODUCT}
    return SmartBaseController(coordinator), client


def report(c, client, value):
    sender, receive = client.start_notify.await_args.args
    receive(sender, bytearray.fromhex(value))


async def test_existing_cover_moves_replacement_controller(hass, runtime):
    coordinator, client = runtime
    old = coordinator.controller
    cover = AdjustableBedCover(coordinator, _build_cover_description(old.motor_control_specs[0]))
    cover.hass = hass
    cover.async_write_ha_state = MagicMock()
    old.on_disconnect()
    replacement = SmartBaseController(coordinator)
    coordinator._controller = replacement
    with virtual_clock():
        await replacement.async_on_connect(session_for(replacement, client))
        client.write_gatt_char.reset_mock()
        await cover.async_open_cover()
    assert bytes.fromhex("6e01002493") in frames(client)


async def test_paired_motor_callback_moves_each_supplied_controller(hass):
    from tests.test_shared_action_hardening import beds

    async with beds(hass, topology="concurrent") as made:
        with virtual_clock():
            for target in made.items:
                hass.config_entries.async_update_entry(
                    target.entry, data={**target.entry.data, "product_type": p.PRODUCT}
                )
                client = target.client
                client.services = [service()]
                client.start_notify = AsyncMock()
                client.write_gatt_char = AsyncMock()
                controller = SmartBaseController(target)
                target._controller = controller
                await controller.async_on_connect(session_for(controller, client))
                client.write_gatt_char.reset_mock()
            button = next(
                button for button in _combined_motor_buttons_for(made.pair, made.items)
                if button._motor_key == "motor_1" and button._direction == "up"
            )
            button.hass = hass
            await button.async_press()
        assert all(bytes.fromhex("6e01002493") in frames(target.client) for target in made.items)


async def test_native_rgb_completion_preserves_newer_led_off_report(hass, runtime):
    coordinator, client = runtime
    c = coordinator.controller
    report(c, client, "6e0e00037f")
    light = _light_entities_for(hass, coordinator)[0]
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    unregister = coordinator.register_controller_state_callback(light._handle_light_state)

    async def write(_char, packet, **_kwargs):
        if packet == bytes.fromhex("6e0cff017a6e0d020380"):
            report(c, client, "6e0e00017d")

    client.write_gatt_char.side_effect = write
    try:
        with virtual_clock():
            await light.async_turn_on(rgb_color=(1, 2, 3))
        assert coordinator.controller_state.get(UNDER_BED_LIGHTS_ON) is False
        assert light.is_on is False
    finally:
        unregister()


@pytest.mark.parametrize(
    ("value", "flag"),
    [
        ("6e09010078", "alarm"),
        ("6e0e00037f", "led_on"),
        ("6e0e00017d", "led_off"),
        ("6e1a000189", "aroma"),
        ("6e0e00037e", None),
    ],
)
async def test_exact_report_classifier_and_current_connection_only(value, flag):
    c, client = controller()
    with virtual_clock():
        await c.async_on_connect(session_for(c, client))
    assert frames(client) == [p.INITIALIZE]
    report(c, client, value)
    assert c.protocol_diagnostics["settings_flags"] == ([flag] if flag else [])
    c.on_disconnect()
    report(c, client, value)
    assert not c.protocol_diagnostics["settings_flags"]
    assert not c.supports_light_color_control


async def test_unproven_buffers_and_stale_subscription_cannot_admit_settings():
    c, client = controller()
    with virtual_clock():
        await c.async_on_connect(session_for(c, client))
        old_sender, old_callback = client.start_notify.await_args.args
        for value in ("6e0e", "00037f", "6e0e00037f6e09010078", "6d0e00037e", "0000000000"):
            report(c, client, value)
        assert not c.supports_light_color_control
        await c.async_on_connect(session_for(c, client))
        old_callback(old_sender, bytearray.fromhex("6e0e00037f"))
        assert not c.supports_light_color_control
        report(c, client, "6e0e00037f")
        assert c.supports_light_color_control
        await c.stop_notify()
        report(c, client, "6e0e00037f")
        assert not c.supports_light_color_control


@pytest.mark.parametrize("defect", ["service", "tx", "rx", "duplicate", "properties"])
async def test_gatt_failures_have_no_subscription_or_write(defect):
    gatt = service()
    if defect == "service":
        gatt.uuid = "other"
    elif defect in ("tx", "rx"):
        gatt.characteristics[defect == "rx"].uuid = "other"
    elif defect == "duplicate":
        gatt.characteristics.append(gatt.characteristics[0])
    else:
        gatt.characteristics[0].properties = ["write-without-response"]
    c, client = controller(client_on(gatt))
    with raises_key("smart_base_gatt"):
        await c.async_on_connect(session_for(c, client))
    client.start_notify.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()


async def test_subscription_failure_revokes_the_connection():
    c, client = controller()
    client.start_notify.side_effect = BleakError("subscription failed")
    with pytest.raises(BleakError), virtual_clock():
        await c.async_on_connect(session_for(c, client))
    assert c._link is None
    client.write_gatt_char.assert_not_awaited()


async def test_held_motion_and_taps_use_selected_timing_and_release():
    c, client = controller()
    with virtual_clock():
        await c.async_on_connect(session_for(c, client))
        client.write_gatt_char.reset_mock()
        await c.motor_control_specs[0].open_fn(c)
        assert frames(client) == [bytes.fromhex("6e01002493")] * 3 + [bytes.fromhex("6e01006edd")]
        client.write_gatt_char.reset_mock()
        await c.preset_flat()
        await c.preset_zero_g()
        await c.lights_toggle()
        await c._save_zero_g()
    assert frames(client) == [
        bytes.fromhex(s)
        for s in (
            "6e010031a0",
            "6e01006edd",
            "6e010045b4",
            "6e01006edd",
            "6e01003cab",
            "6e01006edd",
            "6e010066d5",
            "6e01006edd",
        )
    ]
    assert all(
        call.args[0].uuid == p.TX and call.kwargs["response"] is True
        for call in client.write_gatt_char.await_args_list
    )
    assert [s.translation_key for s in c.motor_control_specs] == ["motor_1", "motor_2"]
    assert (
        not c.supports_single_address_pairing and not c.supports_massage and not c.memory_slot_count
    )


@pytest.mark.parametrize("action", ["move", "save"])
async def test_cancel_never_leaves_a_stream_or_programs_an_early_save(action):
    c, client = controller()
    with virtual_clock():
        await c.async_on_connect(session_for(c, client))
        client.write_gatt_char.reset_mock()
        task = asyncio.create_task(
            c.motor_control_specs[0].open_fn(c) if action == "move" else c._save_zero_g()
        )
        await asyncio.sleep(0.2)
        c._coordinator.cancel_command.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert frames(client) == (
        [bytes.fromhex("6e01002493"), bytes.fromhex("6e01006edd")] if action == "move" else []
    )


async def test_failed_motion_still_releases_without_retry():
    c, client = controller()
    with virtual_clock():
        await c.async_on_connect(session_for(c, client))
        client.write_gatt_char.reset_mock()
        client.write_gatt_char.side_effect = [BleakError("failed"), None]
        with pytest.raises(BleakError):
            await c.motor_control_specs[0].open_fn(c)
    assert frames(client) == [bytes.fromhex("6e01002493"), bytes.fromhex("6e01006edd")]


async def test_commands_and_cleanup_never_borrow_replacement_link():
    c, client = controller()
    replacement = client_on(service())
    with virtual_clock():
        await c.async_on_connect(session_for(c, client))
        client.write_gatt_char.reset_mock()
        task = asyncio.create_task(c.motor_control_specs[0].open_fn(c))
        await asyncio.sleep(0.2)
        c._coordinator.client = replacement
        c.on_disconnect()
        with pytest.raises(ConnectionError):
            await task
    replacement.write_gatt_char.assert_not_awaited()
    assert frames(client) == [bytes.fromhex("6e01002493")]


async def test_settings_query_optional_controls_and_preference_restore():
    c, client = controller()
    with virtual_clock():
        await c.async_on_connect(session_for(c, client))
        client.write_gatt_char.reset_mock()
        await c._query()
        assert frames(client) == list(p.QUERIES)
        with raises_key("smart_base_settings"):
            await c.set_light_color((255, 255, 255))
        assert not c.controller_number_specs
        report(c, client, "6e0e00037f")
        client.write_gatt_char.reset_mock()
        await c.set_light_color((255, 255, 255))
        await c._set_seconds(0)
        await c._set_seconds(300)
        assert frames(client) == [
            bytes.fromhex(s) for s in ("6e0cffff786e0dffff79", "6e0bffff77", "6e0b012ca6")
        ]
        saved = dict(c.persisted_app_state)
        c.on_disconnect()
        c.restore_persisted_app_state(saved)
        assert not c.supports_light_color_control
        assert c.persisted_app_state == saved
        report(c, client, "6e09010078")
        assert all(s.key != "smart_base_cancel_alarm" for s in c.controller_button_specs)
        await c.async_on_connect(session_for(c, client))
        report(c, client, "6e09010078")
        client.write_gatt_char.reset_mock()
        await c._cancel_alarm()
        assert frames(client) == [bytes.fromhex("6e05000073"), bytes.fromhex("6e06000074")]
        client.write_gatt_char.side_effect = BleakError("failed")
        report(c, client, "6e0e00017d")
        with pytest.raises(BleakError):
            await c._set_seconds(12)
        assert c.persisted_app_state == saved


async def test_actual_final_setup_persists_explicit_app_and_product(hass):
    flow = setup_flow(hass)
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_richmat_family({"choice": "smart_base"})
        if result.get("step_id") == "profile_questions":
            result = await flow.async_step_profile_questions({const.CONF_PRODUCT_TYPE: p.PRODUCT})
        result = await finish_new_bed(flow, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[const.CONF_BED_TYPE] == "smart_base"
    assert data[const.CONF_PRODUCT_TYPE] == p.PRODUCT
    assert data[const.CONF_MOTOR_COUNT] == 2 and not data[const.CONF_HAS_MASSAGE]
    assert resolve_profile_id(data) == "smart_base"


def test_discovery_only_offers_the_exact_accepted_app_candidate():
    for name in ("200IV2", "FC200", "A8RM", "200IV2-other"):
        result = detect_bed_type_detailed(packet_info(name, name, (p.SERVICE,)))
        offered = {result.bed_type, *(result.ambiguous_types or ())}
        assert ("smart_base" in offered) == (name == "200IV2")


@pytest.fixture
async def runtime(hass, mock_coordinator_connected, mock_bleak_client):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Smart Base",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:39",
            CONF_NAME: "Smart Base",
            const.CONF_BED_TYPE: "smart_base",
            const.CONF_PRODUCT_TYPE: p.PRODUCT,
            const.CONF_MOTOR_COUNT: 2,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    mock_bleak_client.services = [service()]
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.write_gatt_char = AsyncMock()
    await coordinator.async_prime_offline_controller()
    try:
        with virtual_clock():
            assert await coordinator.async_connect()
        yield coordinator, mock_bleak_client
    finally:
        await coordinator.async_shutdown()


async def test_native_entities_are_gated_and_commands_use_real_scheduler(hass, runtime):
    coordinator, client = runtime
    c = coordinator.controller
    assert isinstance(c, SmartBaseController)
    assert not _light_entities_for(hass, coordinator)
    assert not any(
        e.entity_description.key == "controller_number_smart_base_lamp_seconds"
        for e in _number_entities_for(hass, coordinator)
    )
    report(c, client, "6e0e00037f")
    assert len(_light_entities_for(hass, coordinator)) == 1
    numbers = [
        e
        for e in _number_entities_for(hass, coordinator)
        if e.entity_description.key == "controller_number_smart_base_lamp_seconds"
    ]
    assert len(numbers) == 1
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        await numbers[0].async_set_native_value(0)
    assert frames(client) == [bytes.fromhex("6e0bffff77")]
    buttons = {
        e._spec.key: e for e in _button_entities_for(hass, coordinator) if hasattr(e, "_spec")
    }
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        await buttons["smart_base_light_toggle"].async_press()
    assert frames(client) == [bytes.fromhex("6e01003cab"), bytes.fromhex("6e01006edd")]


def test_explicit_app_is_not_replaced_by_shared_receiver_recommendations():
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile

    info = packet_info("200IV2", "200IV2", (p.SERVICE,))
    assert (
        recommend_profile(
            {const.CONF_BED_TYPE: "smart_base", const.CONF_PRODUCT_TYPE: p.PRODUCT}, info, {}
        )
        is None
    )


async def test_inflight_write_settles_before_stop(runtime):
    coordinator, client = runtime
    c = coordinator.controller
    assert isinstance(c, SmartBaseController)
    began, finish = asyncio.Event(), asyncio.Event()
    client.write_gatt_char.reset_mock()

    async def write(_char, data, **kwargs):
        if data == bytes.fromhex("6e01002493"):
            began.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    movement = asyncio.create_task(
        coordinator.async_execute_controller_command(
            lambda ctrl: ctrl.motor_control_specs[0].open_fn(ctrl)
        )
    )
    await asyncio.wait_for(began.wait(), 2)
    stop = asyncio.create_task(coordinator.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    finish.set()
    await asyncio.gather(movement, stop)
    assert frames(client) == [bytes.fromhex("6e01002493"), bytes.fromhex("6e01006edd")]


async def test_pair_child_ownership_and_selected_side_settings(hass):
    from custom_components.adjustable_bed.pairing import build_pair_entry_data, effective_child_data
    from tests.test_shared_action_hardening import beds

    left = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
        CONF_NAME: "Left",
        const.CONF_BED_TYPE: "smart_base",
        const.CONF_PRODUCT_TYPE: p.PRODUCT,
    }
    right = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:02",
        CONF_NAME: "Right",
        const.CONF_BED_TYPE: "comfort_bed",
        const.CONF_PRODUCT_TYPE: "86",
    }
    paired = build_pair_entry_data(left, right, name="Pair")
    assert (
        effective_child_data(paired, "left", {const.CONF_PRODUCT_TYPE: "86"})[
            const.CONF_PRODUCT_TYPE
        ]
        == p.PRODUCT
    )
    assert effective_child_data(paired, "right")[const.CONF_PRODUCT_TYPE] == "86"
    async with beds(hass, topology="concurrent") as made:
        assert made.pair is not None
        with virtual_clock():
            for bed in made.items:
                hass.config_entries.async_update_entry(
                    bed.entry, data={**bed.entry.data, const.CONF_PRODUCT_TYPE: p.PRODUCT}
                )
                client = bed.client
                client.services = [service()]
                client.start_notify = AsyncMock()
                client.write_gatt_char = AsyncMock()
                c = SmartBaseController(bed)
                bed._controller = c
                await c.async_on_connect(session_for(c, client))
                report(c, client, "6e0e00037f")
                client.write_gatt_char.reset_mock()
            await made.pair.async_execute_controller_command(
                lambda ctrl: ctrl.set_light_color((1, 2, 3)), side="right"
            )
        assert frames(made.items[0].client) == []
        assert frames(made.items[1].client) == [bytes.fromhex("6e0cff017a6e0d020380")]


async def test_profile_motion_and_release_offsets():
    c, client = controller()
    with virtual_clock() as clock:
        await c.async_on_connect(session_for(c, client))
        began = clock.now
        written = []

        async def write(_char, packet, **_kwargs):
            written.append((round((clock.now - began) * 1000), packet.hex()))

        client.write_gatt_char.side_effect = write
        await c.motor_control_specs[1].close_fn(c)
    assert written == [
        (150, "6e01002796"),
        (300, "6e01002796"),
        (450, "6e01002796"),
        (500, "6e01006edd"),
    ]


async def test_gatt_property_policy_and_cancelled_settings_do_not_change_preferences():
    c, client = controller()
    client.services[0].characteristics[0].properties.append("write-without-response")
    with virtual_clock():
        await c.async_on_connect(session_for(c, client))
        assert client.write_gatt_char.await_args.kwargs["response"] is False
        report(c, client, "6e0e00037f")
        client.write_gatt_char.reset_mock()
        c._coordinator.cancel_command.set()
        await c._set_seconds(12)
    client.write_gatt_char.assert_not_awaited()
    assert c.persisted_app_state == {"lamp_seconds": None}
