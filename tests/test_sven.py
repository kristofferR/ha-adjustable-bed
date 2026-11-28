"""Sven's independent literals, live services, local state and captured-session release."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.richmat.sven import SvenController, select_link
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.codec.richmat import command
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles import sven as p
from custom_components.adjustable_bed.select import _select_entities_for
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.state_keys import FOUNDATION_PRESET
from tests.error_helpers import raises_key
from tests.hold_lease_wire import leased_hold, virtual_clock
from tests.test_atlas_lift import client_on, frames, packet_info, session_for
from tests.test_richmat_family_flow import setup_flow

VECTORS = json.loads((Path(__file__).parent / "fixtures/sven/vectors.json").read_text())
ACTION_KEYS = {
    "pillowUp": "pillow_up",
    "pillowDown": "pillow_down",
    "lumbarUp": "lumbar_up",
    "lumbarDown": "lumbar_down",
}


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["id"])
def test_every_frozen_literal_matches_existing_codec(vector):
    inputs = vector["inputs"]
    code = inputs.get("opcode")
    if code is None:
        code = p.MODELS[inputs["model"]].profile.codes[ACTION_KEYS[vector["action"]]]
    assert command(code) == bytes.fromhex(vector["expected_bytes"])


def service(index=0, *, notify=True, props=("write", "write-without-response")):
    uuid, tx = p.TARGETS[index]
    chars = [SimpleNamespace(uuid=tx, properties=list(props), handle=1, descriptors=[])]
    if notify:
        chars += [
            SimpleNamespace(
                uuid="0000fff1-0000-1000-8000-00805f9b34fb",
                properties=["notify"],
                handle=2,
                descriptors=[],
            )
        ]
    return SimpleNamespace(uuid=uuid, characteristics=chars)


def make_controller(model="bliss", *services):
    client = client_on(*(services or (service(),)))
    coordinator = MagicMock(client=client, cancel_command=asyncio.Event(), motor_count=4)
    coordinator.entry.data = {"protocol_variant": model}
    controller = SvenController(coordinator)
    coordinator.controller = controller
    return controller, client


@pytest.mark.parametrize("index", range(5))
@pytest.mark.parametrize("props", [("write",), ("write-without-response",)])
async def test_actual_gatt_properties_select_mode_without_startup_writes(index, props):
    c, client = make_controller("classic", service(index, props=props))
    await c.async_on_connect(session_for(c, client))
    client.write_gatt_char.assert_not_awaited()
    with virtual_clock():
        await c.preset_flat()
    assert frames(client) == [bytes.fromhex("6e010031a0"), bytes.fromhex("6e01006edd")]
    assert all(
        call.kwargs["response"] is (props == ("write",))
        for call in client.write_gatt_char.await_args_list
    )
    c.on_disconnect()


def test_known_target_priority_and_discovered_order_fallback():
    first, last = service(0), service(4)
    assert select_link(client_on(last, first)).tx is first.characteristics[0]
    first.characteristics[0].properties = ["read"]
    assert select_link(client_on(first, last)).tx is last.characteristics[0]
    excluded = SimpleNamespace(
        uuid="0000180a-0000-1000-8000-00805f9b34fb", characteristics=last.characteristics
    )
    fallback = SimpleNamespace(
        uuid="other", characteristics=first.characteristics + last.characteristics
    )
    link = select_link(client_on(excluded, fallback))
    assert link.tx is last.characteristics[0]
    assert link.notify is first.characteristics[1]
    with raises_key("sven_gatt"):
        select_link(client_on(excluded))


@pytest.mark.parametrize("model", p.MODELS)
async def test_model_axes_commands_and_raw_notification_have_no_feedback(model):
    c, client = make_controller(model)
    await c.async_on_connect(session_for(c, client))
    raw = MagicMock()
    c.set_raw_notify_callback(raw)
    sender, receive = client.start_notify.await_args.args
    receive(sender, bytearray.fromhex("6e01002493"))
    raw.assert_called_once()
    assert c.position_number_specs == () or not c.supports_position_feedback
    assert [s.key for s in c.motor_control_specs] == list(p.MODELS[model].axes)
    with virtual_clock():
        for spec in c.motor_control_specs:
            await spec.open_fn(c)
    expected = [command(p.MODELS[model].profile.codes[p.MOTOR_BUTTONS[a][0]]) for a in c.model.axes]
    assert frames(client)[::2] == expected
    assert all(
        frames(client)[i] == bytes.fromhex("6e01006edd") for i in range(1, len(frames(client)), 2)
    )
    c.on_disconnect()


async def test_cancelled_hold_settles_write_then_releases_captured_client():
    c, client = make_controller()
    await c.async_on_connect(session_for(c, client))
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **kwargs):
        if data == bytes.fromhex("6e01002493"):
            entered.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(c._move_with_stop(0x24, duration_ms=5000))
    await entered.wait()
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(client) == [bytes.fromhex("6e01002493"), bytes.fromhex("6e01006edd")]
    c.on_disconnect()


async def test_replacement_session_never_receives_old_release_or_notification():
    c, old = make_controller()
    await c.async_on_connect(session_for(c, old))
    sender, receive = old.start_notify.await_args.args
    raw = MagicMock()
    c.set_raw_notify_callback(raw)
    new = client_on(service())

    async def replace(_char, _data, **kwargs):
        c.on_disconnect()
        c._coordinator.client = new
        c._link = select_link(new)
        c._is_current = lambda: True

    old.write_gatt_char.side_effect = replace
    with virtual_clock(), pytest.raises(ConnectionError):
        await c.preset_flat()
    receive(sender, bytearray.fromhex("6e01002493"))
    raw.assert_not_called()
    new.write_gatt_char.assert_not_awaited()
    c.on_disconnect()


async def test_massage_reconciliation_cycle_compound_off_pattern_and_cooldown():
    c, client = make_controller()
    await c.async_on_connect(session_for(c, client))
    with virtual_clock():
        with raises_key("sven_massage_uncertain"):
            await c.massage_head_toggle()
        c.confirm_massage_off(False)
        with raises_key("sven_massage_rest"):
            await c.massage_head_toggle()
        c.confirm_massage_off(True)
        await c.set_massage_intensity("head", 2)
        await c.set_massage_intensity("foot", 3)
        await c.massage_mode_step()
        assert c._levels == [1, 1]
        client.write_gatt_char.reset_mock()
        # Reaching the allowance must still permit the exact step-based OFF.
        c._used = 1800
        await c.massage_off()
        assert frames(client) == [command(k) for k in (0x4C, 0x6E) * 3 + (0x4E, 0x6E) * 3]
        assert c._levels == [0, 0]
        assert c._timer is None
        with raises_key("sven_massage_rest"):
            await c.massage_foot_toggle()
    c.on_disconnect()


async def test_timer_captured_session_and_stale_notification_do_not_invent_state():
    c, client = make_controller()
    await c.async_on_connect(session_for(c, client))
    with virtual_clock():
        c.confirm_massage_off(True)
        await c.massage_head_toggle()
        assert c._timer is not None

        async def execute(fn, **_kwargs):
            await fn(c)

        c._coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
        await c._timer_off(c._link)
        assert c._levels == [0, 0]
        c.on_disconnect()
        assert c._levels == [None, None]


@pytest.mark.parametrize(
    ("name", "local", "admitted"),
    [
        ("QRRMABCD", None, True),
        ("QJ-1234", None, True),
        ("LW-12", None, True),
        ("QR-ABCD", None, True),
        ("qrrm1234", None, False),
        ("other", "QRRMABCD", False),
        ("", "QRRMABCD", True),
    ],
)
def test_discovery_name_precedence_and_candidate_only(name, local, admitted):
    assert p.admits(name, local) is admitted
    result = detect_bed_type_detailed(packet_info(name, local))
    assert (result.bed_type == "sven" or "sven" in (result.ambiguous_types or ())) is admitted


@pytest.mark.parametrize("model", p.MODELS)
async def test_public_setup_questions_own_model_and_profile_id(hass, model):
    flow = setup_flow(hass)
    flow._manual_data.update({const.CONF_MOTOR_COUNT: 4, const.CONF_HAS_MASSAGE: False})
    flow._discovery_info = packet_info("QRRMABCD", "QRRMABCD")
    flow._app_after_device = "device"
    result = await flow.async_step_select_app({const.CONF_BED_TYPE: "sven"})
    assert result["step_id"] == "profile_questions"
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: model})
        if result.get("step_id") == "finish_settings":
            result = await flow.async_step_finish_settings({})
    assert result["type"] == "create_entry"
    assert result["data"][const.CONF_MOTOR_COUNT] == len(p.MODELS[model].axes)
    assert result["data"][const.CONF_HAS_MASSAGE] is True
    assert resolve_profile_id(result["data"]) == f"sven:{model}"


@pytest.fixture
async def runtime(hass, mock_coordinator_connected, mock_bleak_client):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Sven",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:15",
            CONF_NAME: "Sven",
            const.CONF_BED_TYPE: "sven",
            const.CONF_PROTOCOL_VARIANT: "bliss",
            const.CONF_MOTOR_COUNT: 4,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coordinator
    mock_bleak_client.services = [service()]
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    await coordinator.async_prime_offline_controller()
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, "both")], []),
    ):
        try:
            yield coordinator, mock_bleak_client
        finally:
            await coordinator.async_shutdown()


async def test_real_ha_services_and_existing_cover_use_current_controller(hass, runtime):
    coordinator, client = runtime
    assert await coordinator.async_connect()
    old = coordinator.controller
    cover = AdjustableBedCover(coordinator, _build_cover_description(old.motor_control_specs[2]))
    cover.hass = hass
    cover.async_write_ha_state = MagicMock()
    replacement = SvenController(coordinator)
    coordinator._controller = replacement
    old.on_disconnect()
    await replacement.async_on_connect(session_for(replacement, client))
    with virtual_clock():
        await cover.async_open_cover()
        await hass.services.async_call(
            const.DOMAIN, "save_preset", {"device_id": ["bed"], "preset": 2}, blocking=True
        )
    assert bytes.fromhex("6e010041b0") in frames(client)
    assert bytes.fromhex("6e01002c9b") in frames(client)
    assert frames(client)[-1] == bytes.fromhex("6e01006edd")
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {
                "device_id": ["bed"],
                "motor": "pillow",
                "direction": "down",
                "duration_ms": 200,
            },
            blocking=True,
        )
    assert frames(client) == [bytes.fromhex("6e010042b1")] * 4 + [bytes.fromhex("6e01006edd")]
    assert not any(
        "lounge" in b.unique_id or "massage_all_toggle" in b.unique_id
        for b in _button_entities_for(hass, coordinator)
    )


@pytest.mark.parametrize("end", ("expire", "stop"))
async def test_card_motor_hold_uses_source_refresh_and_end(end):
    result = await leased_hold(
        "sven:bliss", lambda c: c.move_pillow_up(), end_after_s=0.18, end=end
    )
    assert [w.data for w in result.held] == [bytes.fromhex("6e010041b0")] * 4
    assert [w.data for w in result.after] == [bytes.fromhex("6e01006edd")] * (
        2 if end == "stop" else 1
    )


async def test_native_massage_numbers_timer_and_commanded_preset_state(hass, runtime):
    coordinator, client = runtime
    assert await coordinator.async_connect()
    c = coordinator.controller
    head = next(
        n
        for n in _number_entities_for(hass, coordinator)
        if n.entity_description.key == "massage_head_intensity"
    )
    timer = next(
        s
        for s in _select_entities_for(hass, coordinator)
        if s.entity_description.key == "massage_timer"
    )
    for entity in (head, timer):
        entity.hass = hass
        entity.async_write_ha_state = MagicMock()
    assert head.native_value is None
    buttons = _button_entities_for(hass, coordinator)
    reconcile = next(b for b in buttons if b.unique_id.endswith("sven_massage_rested"))
    reconcile.hass = hass
    with virtual_clock():
        await reconcile.async_press()
        await head.async_set_native_value(2)
        assert head.native_value == 2
        await timer.async_select_option("20 min")
        assert timer.current_option == "20 min"
        await timer.async_select_option("Off")
        assert timer.current_option == "Off"
        assert head.native_value == 0
        await coordinator.async_execute_controller_command(lambda ctrl: ctrl.preset_tv())
        assert coordinator.controller_state.get(FOUNDATION_PRESET) == "TV"
        assert c.persisted_app_state == {"last_preset": "TV"}
        await coordinator.async_execute_controller_command(lambda ctrl: ctrl.move_head_up())
        assert coordinator.controller_state.get(FOUNDATION_PRESET) is None


async def test_stale_timer_revision_cannot_stop_a_new_massage_session():
    c, client = make_controller()
    await c.async_on_connect(session_for(c, client))

    async def execute(fn, **_kwargs):
        await fn(c)

    c._coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    with virtual_clock():
        c.confirm_massage_off(True)
        await c.massage_head_toggle()
        link, epoch = c._link, c._timer_epoch
        c.confirm_massage_off(True)
        await c.massage_foot_toggle()
        timer = c._timer
        c._expire_timer(link, epoch)
        assert c._timer is timer
        client.write_gatt_char.reset_mock()
        await c._timer_off(link, epoch)
        client.write_gatt_char.assert_not_awaited()
        assert c._levels == [0, 1]
        c.on_disconnect()


async def test_cancelled_compound_off_preserves_uncertainty_and_does_not_touch_foot():
    c, client = make_controller()
    await c.async_on_connect(session_for(c, client))
    with virtual_clock():
        c.confirm_massage_off(True)
        c._levels = [1, 1]

        async def cancel_after_head(_char, data, **kwargs):
            if data == bytes.fromhex("6e01004cbb"):
                c._coordinator.cancel_command.set()

        client.write_gatt_char.side_effect = cancel_after_head
        with pytest.raises(asyncio.CancelledError):
            await c.massage_off()
        assert frames(client) == [bytes.fromhex("6e01004cbb"), bytes.fromhex("6e01006edd")]
        assert c._levels == [None, None]
        assert c._timer is None
        c.on_disconnect()


def test_app_candidate_preserves_a_dedicated_receiver():
    info = packet_info(
        "QRRMABCD",
        "QRRMABCD",
        (const.BEDTECH_SERVICE_UUID,),
        {const.BEDTECH_MANUFACTURER_ID: bytes.fromhex("54307651")},
    )
    result = detect_bed_type_detailed(info)
    assert result.bed_type == const.BED_TYPE_BEDTECH
    assert "sven" in result.ambiguous_types


@pytest.mark.parametrize(
    ("alias", "key"),
    [
        (" 200S ", "classic"),
        ("Harmony", "harmony"),
        ("Bliss - adjustable", "bliss"),
        ("500s", "platinum"),
        ("unrecognized", "unknown"),
        (None, "unknown"),
    ],
)
def test_model_aliases_never_infer_from_transport(alias, key):
    assert p.model_key(alias) == key
