"""Saatva's shipped codec, controller and native Home Assistant paths."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import _async_sync_profile_ids, const, services
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.codec.richmat import command
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.detection import (
    detect_bed_type_detailed,
    get_bed_type_options,
)
from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
from custom_components.adjustable_bed.profiles.saatva import (
    CHOICES,
    LAYOUTS,
    PROFILES,
    SCAN_UUIDS,
    WRITE_UUID,
)
from custom_components.adjustable_bed.select import _select_entities_for
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES
from tests.form_helpers import finish_new_bed
from tests.saatva_vectors import CASES
from tests.test_richmat_family_flow import setup_flow

METHODS = {
    "head_up": "move_back_up",
    "head_down": "move_back_down",
    "right_head_up": "move_back_up",
    "right_head_down": "move_back_down",
    "foot_up": "move_legs_up",
    "foot_down": "move_legs_down",
    "flat": "preset_flat",
    "zero_g": "preset_zero_g",
    "anti_snore": "preset_anti_snore",
    "tv": "preset_tv",
    "head_massage_up": "massage_head_up",
    "head_massage_down": "massage_head_down",
    "right_head_massage_up": "massage_head_up",
    "right_head_massage_down": "massage_head_down",
    "foot_massage_up": "massage_foot_up",
    "foot_massage_down": "massage_foot_down",
    "massage_toggle": "massage_toggle",
    "massage_mode": "massage_mode_step",
    "light_toggle": "lights_toggle",
}


async def runtime(hass, product="bt3000fh_split_top"):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Saatva",
        data={
            CONF_ADDRESS: "11:22:33:44:55:68",
            CONF_NAME: "Saatva",
            const.CONF_BED_TYPE: "saatva",
            const.CONF_PROTOCOL_VARIANT: product,
            const.CONF_PRODUCT_TYPE: LAYOUTS[product],
            const.CONF_MOTOR_COUNT: 2,
            const.CONF_HAS_MASSAGE: product.startswith("bt3000"),
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_MOTOR_PULSE_COUNT: 1,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    c = AdjustableBedCoordinator(hass, entry)
    await c.async_prime_offline_controller()
    c._client = MagicMock(is_connected=True)
    c._client.write_gatt_char = AsyncMock()
    c._client.stop_notify = AsyncMock()
    c._client.disconnect = AsyncMock()
    c._controller = await create_controller(c, "saatva", product, c._client)
    return c


def written(c):
    return [call.args[1].hex() for call in c.client.write_gatt_char.await_args_list]


@pytest.mark.parametrize(("product", "action", "token", "literal"), CASES)
async def test_live_vectors_through_codec_and_actual_controller(
    hass, product, action, token, literal
):
    side = 1 if token.startswith("_") and len(token) == 2 else 0
    assert command(ord(token[-1]), side).hex() == literal
    c = await runtime(hass, product)
    try:

        async def execute(ctrl):
            if action.startswith("memory"):
                slot = int(action[6])
                await (
                    ctrl.program_memory(slot)
                    if action.endswith("save")
                    else ctrl.preset_memory(slot)
                )
            elif action.startswith("massage_timer"):
                await ctrl.set_massage_timer(int(action[-2:]))
            else:
                await getattr(ctrl, METHODS[action])()

        with c.controller.side_scope(const.SIDE_RIGHT if side else const.SIDE_LEFT):
            await c.async_execute_controller_command(execute)
        assert written(c) == [literal]
        call = c.client.write_gatt_char.await_args
        assert call.args[0] == WRITE_UUID
        assert call.kwargs["response"] is (
            action
            not in {
                "head_up",
                "head_down",
                "right_head_up",
                "right_head_down",
                "foot_up",
                "foot_down",
            }
        )
    finally:
        await c.async_shutdown()


@pytest.mark.parametrize("product", CHOICES)
async def test_native_setup_persists_concrete_profile_and_layout(hass, product):
    assert any(
        row["value"] == "saatva" and "Saatva" in row["label"] for row in get_bed_type_options()
    )
    flow = setup_flow(hass, **{const.CONF_BED_TYPE: "saatva"})
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: product})
        result = await finish_new_bed(flow, result)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    saved = MockConfigEntry(domain=const.DOMAIN, data=data)
    saved.add_to_hass(hass)
    _async_sync_profile_ids(hass, saved)
    assert saved.data[const.CONF_PROFILE_ID] == f"saatva:{product}"
    assert data[const.CONF_PRODUCT_TYPE] == LAYOUTS[product]
    assert data[const.CONF_MOTOR_COUNT] == 2
    assert data[const.CONF_HAS_MASSAGE] is product.startswith("bt3000")
    assert {const.CONF_PROTOCOL_VARIANT, const.CONF_PRODUCT_TYPE} <= per_side_profile(
        "saatva", product
    ).keys
    c = await runtime(hass, product)
    try:
        assert c.controller.profile is PROFILES[product]
        assert c.controller.supports_single_address_pairing is product.endswith("split_top")
        assert c.controller.supports_preset_tv is product.startswith("bt3000")
        assert c.controller.supports_massage is product.startswith("bt3000")
        assert not c.controller.supports_massage_off_control
        assert not c.controller.supports_head_massage_toggle_control
        assert not c.controller.supports_foot_massage_toggle_control
        assert not c.controller.supports_preset_lounge
    finally:
        await c.async_shutdown()


@pytest.mark.parametrize("uuid", SCAN_UUIDS)
def test_shared_uuid_offers_app_without_guessing_model(uuid):
    info = MagicMock(name="", service_uuids=[uuid.upper()], manufacturer_data={})
    info.name = "Receiver"
    result = detect_bed_type_detailed(info)
    assert result.bed_type == "saatva" or "saatva" in (result.ambiguous_types or [])
    assert result.bed_type != "saatva" or result.confidence < 0.7


async def test_native_entities_services_and_split_top_fanout(hass):
    c = await runtime(hass)
    pair_entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Saatva pair",
        data={
            **c.entry.data,
            const.CONF_PAIR_ID: "saatva-pair",
        },
    )
    pair_entry.add_to_hass(hass)
    pair = SingleAddressPairedCoordinator(hass, pair_entry, c)
    try:
        # Parent fan-out must deduplicate the shared foot and common actions.
        await pair.async_execute_controller_command(lambda ctrl: ctrl.move_back_up())
        assert written(c) == ["6e01002493", "6e01012494"]
        c.client.write_gatt_char.reset_mock()
        await pair.async_execute_controller_command(lambda ctrl: ctrl.move_legs_up())
        assert written(c) == ["6e01002695"]
        c.client.write_gatt_char.reset_mock()
        await pair.children[const.SIDE_RIGHT].async_execute_controller_command(
            lambda ctrl: ctrl.massage_head_down()
        )
        assert written(c) == ["6e01014dbd"]
        c.client.write_gatt_char.reset_mock()
        # Exercise the native cover and generic memory service callers.
        cover = AdjustableBedCover(c, _build_cover_description(c.controller.motor_control_specs[1]))
        cover.async_write_ha_state = MagicMock()
        await cover.async_open_cover()
        assert written(c) == ["6e01002695"]
        await services.async_register_services(hass)
        with patch.object(services, "_resolve_sided_targets", return_value=([(pair, "both")], [])):
            await hass.services.async_call(
                const.DOMAIN, "save_preset", {"device_id": "bed", "preset": 2}, blocking=True
            )
        assert written(c)[-1:] == ["6e01002c9b"]
        selects = _select_entities_for(hass, c)
        timer = next(
            entity for entity in selects if entity.entity_description.key == "massage_timer"
        )
        timer.async_write_ha_state = MagicMock()
        assert timer.options == ["10 min", "20 min"]
        await timer.async_select_option("10 min")
        assert written(c)[-1] == "6e01005fce"
        assert c.controller_state.get(MASSAGE_TIMER_MINUTES) == 10
        c.client.write_gatt_char.reset_mock()
        with pytest.raises(ServiceValidationError):
            await c.async_execute_controller_command(lambda ctrl: ctrl.set_massage_timer(0))
        assert written(c) == []
        buttons = _button_entities_for(hass, c)
        test = next(entity for entity in buttons if entity.unique_id.endswith("test_head"))
        assert test.extra_state_attributes["requires_confirmation"]
        assert test._spec.hold is None
    finally:
        await pair.async_shutdown()


async def test_stop_cancels_refresh_and_never_invents_release_or_subscriptions(hass):
    c = await runtime(hass)
    try:
        await c.controller.start_notify()
        await c.controller.read_positions()
        assert written(c) == []
        c.client.start_notify.assert_not_called()
        entered = asyncio.Event()

        async def write(_uuid, _packet, **_kwargs):
            entered.set()

        c.client.write_gatt_char.side_effect = write
        await services.async_register_services(hass)
        with patch.object(services, "_resolve_sided_targets", return_value=([(c, "both")], [])):
            task = asyncio.create_task(
                hass.services.async_call(
                    const.DOMAIN,
                    "timed_move",
                    {
                        "device_id": "bed",
                        "motor": "back",
                        "direction": "up",
                        "duration_ms": 5000,
                    },
                    blocking=True,
                )
            )
            await asyncio.wait_for(entered.wait(), 1)
            await c.async_stop_command()
            await task
        assert set(written(c)) <= {"6e01002493", "6e01012494"}
        count = len(written(c))
        await c.controller.stop_all()
        assert len(written(c)) == count
    finally:
        await c.async_shutdown()


async def test_setup_test_uses_first_head_and_no_release_frame(hass):
    c = await runtime(hass)
    try:
        seen = []

        async def pulse(packet, **kwargs):
            seen.append((packet.hex(), c.controller.command_side, kwargs))

        with patch.object(c.controller, "write_command", side_effect=pulse):
            button = next(
                entity
                for entity in _button_entities_for(hass, c)
                if entity.unique_id.endswith("test_head")
            )
            await button.async_press()
        assert seen == [("6e01002493", "left", {"repeat_count": 21})]
        with c.controller.side_scope(const.SIDE_RIGHT), pytest.raises(ServiceValidationError):
            await c.controller.test_head()
        assert written(c) == []
    finally:
        await c.async_shutdown()


async def test_two_receiver_side_and_synchronized_targeting(hass):
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    left = await runtime(hass, "bt2000_split")
    right = await runtime(hass, "bt3000_split")
    entry = MockConfigEntry(domain=const.DOMAIN, data={const.CONF_PAIR_ID: "saatva-dual"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, entry, {const.SIDE_LEFT: left, const.SIDE_RIGHT: right})
    try:
        # None: use the selected child. Feet sync: parent feet, child head.
        await pair.children[const.SIDE_RIGHT].async_execute_controller_command(
            lambda ctrl: ctrl.move_back_up()
        )
        assert written(left) == [] and written(right) == ["6e01002493"]
        right.client.write_gatt_char.reset_mock()
        await pair.async_execute_controller_command(lambda ctrl: ctrl.move_legs_down())
        assert written(left) == written(right) == ["6e01002796"]
        left.client.write_gatt_char.reset_mock()
        right.client.write_gatt_char.reset_mock()
        # All: the parent dispatches to each physical receiver, bank zero.
        await pair.async_execute_controller_command(lambda ctrl: ctrl.preset_flat())
        assert written(left) == written(right) == ["6e010031a0"]
    finally:
        await pair.async_shutdown()


async def test_normal_connection_starts_without_handshake_queries_or_notify(
    hass, mock_coordinator_connected, mock_bleak_client
):
    c = await runtime(hass, "bt2000_standard")
    c._client = None
    c._controller = None
    try:
        assert await c.async_connect()
        mock_bleak_client.write_gatt_char.assert_not_called()
        mock_bleak_client.read_gatt_char.assert_not_called()
        mock_bleak_client.start_notify.assert_not_called()
    finally:
        await c.async_shutdown()
