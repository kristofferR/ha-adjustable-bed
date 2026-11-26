"""Likimio setup, session ownership and live capability gates."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import _async_sync_profile_ids, button, const, services
from custom_components.adjustable_bed.beds.dreamsense.controller import ACK
from custom_components.adjustable_bed.beds.dreamsense.likimio import (
    CANCEL_ALARM,
    LikimioController,
    LikimioReceive,
)
from custom_components.adjustable_bed.beds.dreamsense.transport import LIKIMIO_ROUTES
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.profiles.likimio import ABM10, CHOICES, NO_PRODUCT, SCAN_WORDS
from tests.error_helpers import raises_key
from tests.form_helpers import finish_new_bed
from tests.test_dreamsense import make_client, written
from tests.test_richmat_family_flow import setup_flow

GATT = json.loads((Path(__file__).parent / "fixtures/likimio/gatt.json").read_text())


@pytest.mark.parametrize("word", SCAN_WORDS)
def test_shared_advertisement_suggests_likimio_without_selecting_its_product(word):
    def detect(name, alias=None, *, raw=None, cached=False):
        info = MagicMock(
            advertisement=SimpleNamespace(
                local_name=name, platform_data=() if cached else (object(),)
            ),
            raw=raw,
            service_uuids=[],
            manufacturer_data={},
            service_data={},
        )
        info.name = alias or name
        return detect_bed_type_detailed(info)

    result = detect("prefix" + word + "suffix")
    assert const.BED_TYPE_LIKIMIO in (result.ambiguous_types or ())
    for name in ("prefix" + word.lower() + "suffix", "UTRM"):
        result = detect(name)
        assert result.bed_type != const.BED_TYPE_LIKIMIO
        assert const.BED_TYPE_LIKIMIO not in (result.ambiguous_types or ())
    assert const.BED_TYPE_LIKIMIO not in (detect(None, alias=word).ambiguous_types or ())
    cached = detect(word, cached=True)
    assert cached.bed_type != const.BED_TYPE_LIKIMIO
    assert const.BED_TYPE_LIKIMIO not in (cached.ambiguous_types or ())
    packet_name = f"prefix{word}suffix".encode()
    raw = bytes((len(packet_name) + 1, 0x09)) + packet_name
    packet = detect("Unrelated name", raw=raw, cached=True)
    assert const.BED_TYPE_LIKIMIO in {packet.bed_type, *(packet.ambiguous_types or ())}



@pytest.mark.parametrize("product", CHOICES)
async def test_native_setup_persists_likimio_profile(hass, product):
    flow = setup_flow(hass, **{const.CONF_BED_TYPE: const.BED_TYPE_LIKIMIO})
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: product})
        result = await finish_new_bed(flow, result)
    entry = MockConfigEntry(domain=const.DOMAIN, data=result["data"])
    entry.add_to_hass(hass)
    _async_sync_profile_ids(hass, entry)
    assert entry.data[const.CONF_PROFILE_ID] == f"likimio:{product}"
    assert result["data"][const.CONF_HAS_MASSAGE] is (product == ABM10)


async def make_runtime(hass, product=ABM10, layout=1, *, notify=True, response=False):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Likimio",
        data={
            CONF_ADDRESS: "11:22:33:44:55:68",
            CONF_NAME: "Likimio",
            const.CONF_BED_TYPE: const.BED_TYPE_LIKIMIO,
            const.CONF_PROTOCOL_VARIANT: product,
            const.CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    c = AdjustableBedCoordinator(hass, entry)
    c._client = make_client(layout, without_response=not response)
    if not notify:
        c._client.services[0].characteristics.pop()
    ctrl = await create_controller(c, const.BED_TYPE_LIKIMIO, product, c._client)
    assert isinstance(ctrl, LikimioController)
    c._controller = ctrl
    ctrl._wait = AsyncMock()
    return c, ctrl


def notify_reply(c, hex_string):
    char, callback = c.client.start_notify.await_args.args
    callback(char, bytearray.fromhex(hex_string))


def test_gatt_selection_uses_the_six_frozen_routes():
    assert set(LIKIMIO_ROUTES) == {tuple(route) for route in GATT}


@pytest.mark.parametrize("layout", range(6))
async def test_startup_and_a_short_control_on_each_route(hass, layout):
    c, ctrl = await make_runtime(hass, layout=layout, response=bool(layout % 2))
    await ctrl.start_notify()
    await ctrl.start_notify()
    single = c.client.services[0].uuid == "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    assert written(c) == (
        ["00", "01", "01", "01"]
        if single
        else ["6e02010071", "6e08010178", "6e0a000179", "6e15010185"]
    )
    assert c.client.start_notify.await_count == 1
    assert all(
        tx.args[0] is c.client.services[0].characteristics[0]
        and tx.kwargs["response"] is bool(layout % 2)
        for tx in c.client.write_gatt_char.await_args_list
    )

    c.client.write_gatt_char.reset_mock()
    await ctrl.press("MotorReset")
    await ctrl.press("MemoryPosition2", save=True)
    assert written(c) == (
        ["31", "6e", "2c"] if single else ["6e010031a0", "6e01006edd", "6e01002c9b"]
    )


async def test_waits_for_subscription_and_rejects_non_writable_endpoint(hass):
    c, ctrl = await make_runtime(hass)
    pending, subscribed = asyncio.Event(), asyncio.Event()

    async def notify(_char, _cb):
        pending.set()
        await subscribed.wait()

    c.client.start_notify.side_effect = notify
    startup = asyncio.create_task(ctrl.start_notify())
    try:
        await pending.wait()
        with raises_key("dreamsense_session"):
            await ctrl.press("MotorReset")
        assert written(c) == []
    finally:
        subscribed.set()
        await startup
    ctrl.on_disconnect()
    c.client.write_gatt_char.reset_mock()
    c.client.services[0].characteristics[0].properties = ["write-without-response"]
    with raises_key("dreamsense_transport"):
        await ctrl.start_notify()
    assert written(c) == []


async def test_write_only_gatt_keeps_abm10_controls_but_has_no_light_capability(hass):
    c, ctrl = await make_runtime(hass, notify=False)
    await ctrl.start_notify()
    assert not c.client.start_notify.await_count
    assert not ctrl.controller_number_specs
    with raises_key("dreamsense_capability"):
        await ctrl.close_light()
    await ctrl.press("BedLight")
    assert written(c)[-2:] == ["6e01003cab", "6e01006edd"]


async def test_only_exact_current_light_reply_opens_advanced_abm10_controls(hass):
    c, ctrl = await make_runtime(hass)
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    notify_reply(c, "6e09010078 6e16010186 6e0e00037e")
    assert not ctrl.controller_number_specs
    assert not ctrl.alarm_capability and not ctrl.supports_clock_sync
    assert {CANCEL_ALARM, "dreamsense_vibration"}.isdisjoint(
        {spec.key for spec in ctrl.controller_button_specs}
    )
    notify_reply(c, "6e0e00037f")
    assert ctrl.controller_number_specs[0].native_max_value == 900
    await services.async_register_services(hass)
    with patch.object(
        services, "_resolve_sided_targets", return_value=([(c, const.SIDE_BOTH)], [])
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "dreamsense_light",
            {"device_id": "bed", "rgb_color": [18, 52, 86], "seconds": 300},
            blocking=True,
        )
    await c.async_execute_controller_command(lambda live: live.close_light(), cancel_running=False)
    assert written(c) == ["6e0b012ca6", "6e0cff128b6e0d345605", "6e010075e4"]

    _, old_callback = c.client.start_notify.await_args.args
    ctrl.on_disconnect()
    await ctrl.start_notify()
    old_callback(None, bytearray.fromhex("6e0e00037f"))
    with raises_key("dreamsense_capability"):
        await ctrl.close_light()


@pytest.mark.parametrize(
    ("product", "reply", "key"),
    (
        (NO_PRODUCT, "6e09010078", CANCEL_ALARM),
        (ABM10, "6e0e00037f", "dreamsense_light_close"),
    ),
)
async def test_late_capability_reply_adds_button(hass, product, reply, key):
    c, ctrl = await make_runtime(hass, product)
    hass.data.setdefault(const.DOMAIN, {})[c.entry.entry_id] = c
    await ctrl.start_notify()
    entities = []
    await button.async_setup_entry(hass, c.entry, entities.extend)

    unique_id = c.entity_unique_id(key)
    assert not any(entity.unique_id == unique_id for entity in entities)
    notify_reply(c, reply)
    await hass.async_block_till_done()

    (added,) = [entity for entity in entities if entity.unique_id == unique_id]
    if key == CANCEL_ALARM:
        assert added.entity_registry_enabled_default


@pytest.mark.parametrize("layout", (0, 1))
async def test_no_product_only_offers_confirmed_cancel_with_separate_writes(hass, layout):
    c, ctrl = await make_runtime(hass, NO_PRODUCT, layout)
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    assert not ctrl.controller_button_specs
    assert not ctrl.supports_stop_all and not ctrl.alarm_capability and not ctrl.supports_clock_sync
    assert not ctrl.held_control_options
    with raises_key("dreamsense_capability"):
        await ctrl.cancel_alarm()

    notify_reply(c, "6e09010078")
    (button,) = ctrl.controller_button_specs
    assert button.key == CANCEL_ALARM
    await c.async_execute_controller_command(button.press_fn, cancel_running=False)
    assert written(c) == ["6e05000073", "6e06000074"]
    notify_reply(c, "6e07010278")
    assert c.controller_state.get(ACK) == "alarm_cancelled"


async def test_stop_waits_for_inflight_movement_and_goes_to_its_original_session(hass):
    c, ctrl = await make_runtime(hass)
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    started, complete = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **_kwargs):
        if data == bytes.fromhex("6e01002493"):
            started.set()
            await complete.wait()

    c.client.write_gatt_char.side_effect = write
    move = asyncio.create_task(
        c.async_execute_controller_command(lambda live: live.hold_control("HeadUp", 1000))
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    stop = asyncio.create_task(c.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    complete.set()
    await asyncio.gather(move, stop, return_exceptions=True)
    frames = written(c)
    assert frames[0] == "6e01002493" and frames[1:]
    assert set(frames[1:]) == {"6e01006edd"}


def test_receive_preserves_extended_tails_and_matches_exact_common_events():
    receive = LikimioReceive()
    receive.feed(bytes.fromhex("00 11 6e0e00037f 6e20090b"))
    assert receive.capabilities == {"light"}
    assert receive.pending == bytes.fromhex("6e20090b")
    receive.feed(bytes.fromhex("02020002a8 6e07010278 6e20"))
    assert receive.split is False and receive.last_ack == "alarm_cancelled"
    receive.feed(bytes.fromhex("090b02030000a7"))
    assert receive.split is True
    receive.feed(bytes.fromhex("6e20090b02020002ff"))
    assert receive.split is True
    receive.feed(bytes.fromhex("6e2100 6e09010078"))
    assert receive.capabilities == {"light", "clock"}
