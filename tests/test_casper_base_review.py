"""Row101 independent-review regressions through coordinator, flow and live consumers."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import _async_ensure_paired_device_registry, button, cover
from custom_components.adjustable_bed.beds.casper_base.controller import CasperBaseController
from custom_components.adjustable_bed.beds.casper_base.protocol import Request
from custom_components.adjustable_bed.beds.casper_sleep.controller import (
    CasperRemoteController,
    CasperSleepController,
)
from custom_components.adjustable_bed.codec.richmat import record_20_len
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
from custom_components.adjustable_bed.pairing import supports_single_address_pairing
from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor
from tests.test_casper_base import make


@pytest.fixture(autouse=True)
def no_protocol_waits(monkeypatch):
    real_sleep = asyncio.sleep

    async def immediate(_delay):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", immediate)


def runtime(hass, model="hushl400sh", *, transport=1, kind=None):
    _, mocked = make(model, transport=transport, kind=kind)
    bed_type = "casper_sleep_" + kind if kind else "casper_base"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Casper",
        unique_id="AA:BB:CC:DD:EE:FF",
        version=4,
        data={
            "address": "AA:BB:CC:DD:EE:FF",
            "name": "Casper",
            "bed_type": bed_type,
            "protocol_variant": model,
            "disable_angle_sensing": True,
            "motor_pulse_count": 1,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = mocked.client
    controller = (
        CasperSleepController(coordinator, kind=kind)
        if kind
        else CasperBaseController(coordinator, product=model)
    )
    coordinator._controller = controller
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    return entry, coordinator, controller


@pytest.mark.parametrize("kind", ["mm", "sxb"])
async def test_sensor_translation_keys_preserve_case_sensitive_state(hass, kind):
    _, coordinator, controller = runtime(hass, kind=kind)
    root = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
    specs = controller.controller_state_sensor_specs
    for filename in ("strings.json", "translations/en.json"):
        translations = json.loads((root / filename).read_text())["entity"]["sensor"]
        assert all(
            re.fullmatch(r"[a-z0-9]+(?:[a-z0-9_-]*[a-z0-9])?", spec.translation_key)
            for spec in specs
        )
        assert all(spec.translation_key in translations for spec in specs)
    for spec in specs[1:]:
        assert spec.key == spec.state_key
        assert "_L_" in spec.state_key or "_R_" in spec.state_key
        entity = AdjustableBedControllerStateSensor(coordinator, spec)
        coordinator.handle_controller_state_update(spec.state_key, 42)
        assert entity.translation_key == spec.state_key.lower()
        assert entity.unique_id == coordinator.entity_unique_id(spec.state_key)
        assert entity.native_value == 42


@pytest.mark.parametrize("kind", [None, "mm", "sxb"])
async def test_coordinator_initializes_required_channel_with_angles_disabled(hass, kind):
    _, coordinator, controller = runtime(hass, kind=kind)
    assert coordinator._disable_angle_sensing
    await coordinator.async_start_notify()
    assert controller._write_char is not None
    assert controller._notify_char is not None
    coordinator.client.start_notify.assert_awaited_once()
    coordinator.client.write_gatt_char.assert_awaited()
    if isinstance(controller, CasperSleepController):
        coordinator.client.write_gatt_char.reset_mock()
        await controller._send("s_time", Request("sensor_time"))
        coordinator.client.write_gatt_char.assert_awaited()
    await controller.stop_notify()


async def test_remote_remains_connection_only_through_coordinator(hass):
    _, coordinator, _ = runtime(hass)
    controller = CasperRemoteController(coordinator)
    coordinator._controller = controller
    await coordinator.async_start_notify()
    await controller.async_execute_casper_base_request(Request("remote_find"))
    coordinator.client.start_notify.assert_not_awaited()
    coordinator.client.write_gatt_char.assert_not_awaited()
    assert coordinator.controller_state["casper_remote_status"] == "connected"


@pytest.mark.parametrize("model", ["hushl400sh", "hushl300sh"])
async def test_eligible_pair_options_create_side_entities_and_route_actions(
    hass, enable_custom_integrations, model
):
    entry, inner, controller = runtime(hass, model)
    assert not controller.supports_single_address_pairing
    await inner.async_start_notify()
    assert controller.supports_single_address_pairing
    assert supports_single_address_pairing("casper_base", model)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "pair_sides" in result["menu_options"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "pair_sides"}
    )
    assert not result["errors"]
    with (
        patch.object(hass.config_entries, "async_unload", AsyncMock(return_value=True)),
        patch.object(hass.config_entries, "async_setup", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"confirm": True}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
    assert entry.data["pair_mode"] == "single_address"
    assert {c["protocol_variant"] for c in entry.data["pair_children"]} == {model}
    paired = SingleAddressPairedCoordinator(hass, entry, inner)
    hass.data[DOMAIN][entry.entry_id] = paired
    _async_ensure_paired_device_registry(hass, entry, paired)
    buttons = []
    covers = []
    await button.async_setup_entry(hass, entry, buttons.extend)
    await cover.async_setup_entry(hass, entry, covers.extend)
    for side in ("left", "right"):
        assert any(entity.unique_id.endswith("_" + side) for entity in buttons)
        assert any(entity.unique_id.endswith("_" + side) for entity in covers)
    target = next(
        entity for entity in buttons if entity.unique_id.endswith("_casper_motorreset_right")
    )
    inner.client.write_gatt_char.reset_mock()
    with patch.object(inner, "async_connect", AsyncMock(return_value=True)):
        await target.async_press()
    assert bytes(inner.client.write_gatt_char.await_args.args[1]).hex() == "6e010131a1"
    inner._cancel_disconnect_timer()


@pytest.mark.parametrize(
    ("model", "transport", "connected", "menu", "error"),
    [
        ("casperpro", 1, True, False, None),
        ("caspermax", 1, True, False, None),
        ("hushl400sh", 0, True, True, "single_address_pairing_unsupported"),
    ],
)
async def test_pair_options_reject_unproved_or_unsupported_transport(
    hass, enable_custom_integrations, model, transport, connected, menu, error
):
    entry, inner, controller = runtime(hass, model, transport=transport)
    if connected:
        await inner.async_start_notify()
    else:
        inner._client = None
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert ("pair_sides" in result["menu_options"]) == menu
    if menu:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "pair_sides"}
        )
        assert result["errors"] == {"base": error}
        assert "pair_mode" not in entry.data


async def _open_pair_sides(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "pair_sides"}
    )
    assert result["type"] == FlowResultType.SHOW_PROGRESS
    await hass.async_block_till_done()
    return await hass.config_entries.options.async_configure(result["flow_id"])


@pytest.mark.parametrize(
    ("transport", "error"), [(1, None), (0, "single_address_pairing_unsupported")]
)
async def test_pair_options_connect_a_disconnected_bed_to_prove_its_transport(
    hass, enable_custom_integrations, transport, error
):
    entry, inner, controller = runtime(hass, "hushl300sh", transport=transport)
    client, inner._client = inner._client, None

    async def connect(reset_timer=True):
        inner._client = client
        await inner.async_start_notify()
        return True

    with patch.object(inner, "async_ensure_connected", side_effect=connect) as ensure:
        result = await _open_pair_sides(hass, entry)
    ensure.assert_awaited_once()
    assert result["step_id"] == "pair_sides"
    assert result.get("errors") == ({"base": error} if error else None)
    if error:
        return
    with (
        patch.object(hass.config_entries, "async_unload", AsyncMock(return_value=True)),
        patch.object(hass.config_entries, "async_setup", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"confirm": True}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data["pair_mode"] == "single_address"
    inner._cancel_disconnect_timer()


async def test_pair_options_report_a_failed_connection_and_retry_on_submit(
    hass, enable_custom_integrations
):
    entry, inner, _ = runtime(hass, "hushl300sh")
    inner._client = None
    with patch.object(inner, "async_ensure_connected", AsyncMock(return_value=False)) as ensure:
        result = await _open_pair_sides(hass, entry)
        assert result["errors"] == {"base": "casper_pairing_needs_connection"}
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"confirm": True}
        )
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_configure(result["flow_id"])
    assert ensure.await_count == 2
    assert result["errors"] == {"base": "casper_pairing_needs_connection"}
    assert "pair_mode" not in entry.data


def bt_ordinary(enabled):
    return bytes((0x6E, 0x90, 0xB0, 0x20 if enabled else 0, 0))


def bt_extended(enabled):
    return record_20_len(9, 3, 2, (0, int(enabled)))


@pytest.mark.parametrize("split", range(1, 6))
async def test_marker_checksum_notification_updates_music_source_state(split):
    controller, c = make("nisconup355b")
    await controller.start_notify()
    controller._on_notification(None, bytearray(bytes.fromhex("6e16010186")))
    controller._on_notification(None, bytearray(bt_extended(True)))
    assert controller._music_bluetooth
    packet = bytes.fromhex("6e90b0c06e")
    controller._on_notification(None, bytearray(packet[:split]))
    controller._on_notification(None, bytearray(packet[split:]))
    assert controller.events["accessories"] == {
        "usb": False,
        "play": True,
        "music_follow": True,
        "bluetooth": False,
    }
    assert not controller._music_bluetooth
    c.client.write_gatt_char.reset_mock()
    await controller.async_perform_casper_base_action("MusicSwitchSoundTrack", music_page=True)
    assert [bytes(call.args[1]).hex() for call in c.client.write_gatt_char.call_args_list] == [
        "6e0100c433"
    ]


@pytest.mark.parametrize(
    ("first", "second", "enabled"),
    [
        (bt_ordinary(True), bt_extended(False), False),
        (bt_extended(True), bt_ordinary(False), False),
        (bt_ordinary(False), bt_extended(True), True),
        (bt_extended(False), bt_ordinary(True), True),
    ],
)
async def test_music_consumers_merge_latest_bluetooth_before_usb(first, second, enabled):
    controller, c = make("nisconup355b")
    await controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    controller._on_notification(None, bytearray(bytes.fromhex("6e16010186")))
    for packet in (first, second):
        controller._on_notification(None, bytearray(packet))
    assert controller._music_bluetooth is enabled
    assert "accessories" in controller.events and "music_bluetooth" in controller.events
    await controller.async_perform_casper_base_action("MusicSwitchSoundTrack", music_page=True)
    frames = [bytes(call.args[1]).hex() for call in c.client.write_gatt_char.call_args_list]
    assert frames == (["6e0100d847", "6e0100c433"] if enabled else ["6e0100c433"])
    assert not controller._music_bluetooth


async def test_music_switch_optimism_and_later_reply_share_current_state():
    controller, c = make("nisconup355b")
    await controller.start_notify()
    controller._on_notification(None, bytearray(bytes.fromhex("6e16010186")))
    await controller.async_perform_casper_base_action("MusicBlueToothSwitch", music_page=True)
    assert controller._music_bluetooth
    c.client.write_gatt_char.reset_mock()
    await controller.async_perform_casper_base_action("MusicSwitchSoundTrack", music_page=True)
    assert [bytes(call.args[1]).hex() for call in c.client.write_gatt_char.call_args_list] == [
        "6e0100d847",
        "6e0100c433",
    ]
    assert not controller._music_bluetooth
    controller._on_notification(None, bytearray(bt_extended(True)))
    assert controller._music_bluetooth
