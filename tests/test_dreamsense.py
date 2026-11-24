"""Dream Sense frozen frames and actual HA scheduler/entity/action paths."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME, STATE_UNKNOWN
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.dreamsense import protocol as p
from custom_components.adjustable_bed.beds.dreamsense.controller import DreamSenseController
from custom_components.adjustable_bed.beds.dreamsense.receive import Receive
from custom_components.adjustable_bed.beds.dreamsense.transport import select
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.dreamsense import CHOICES, PROFILES
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES
from tests.dreamsense_vectors import CATALOG, GATT, VECTORS
from tests.error_helpers import raises_key


@pytest.mark.parametrize(
    "row", [v for v in VECTORS if not v["id"].startswith("excluded-")], ids=lambda r: r["id"]
)
def test_native_codec_matches_frozen_builder_literals(row):
    spec = row["inputs"]
    args, kw, builder = spec["args"], spec.get("kwargs", {}), spec["builder"]
    if builder == "generic":
        prefixes = {
            (110, 2, 1): "ExitLimit",
            (110, 8, 1): "CheckClock",
            (110, 10, 0): "CheckLight",
            (110, 21, 1): "CheckMusic",
        }
        action = "deviceFunctionItem" + prefixes[tuple(kw["prefix"])] if "prefix" in kw else ""
        result = codec.function(
            args[0], kw.get("side", 0), action=action, single=not kw.get("nordic", False)
        )
    elif builder == "single_clock":
        result = codec.countdown(*args)
    elif builder == "rgb":
        result = codec.rgb(*args)
    elif builder == "rgb_normalized":
        result = codec.rgb(*(int(n * 255 + 0.5) & 255 for n in args))
    elif builder == "time_sync":
        epoch, zone, year, month, day, hour, minute, second = args
        result = (
            codec.record_20_len(8, 2, 1, (*epoch.to_bytes(4, "big"), zone)),
            codec.calendar(
                datetime(year, month, day, hour, minute, second, tzinfo=UTC),
                build=codec.record_20_len,
            ),
        )
    else:
        result = getattr(p, builder)(*args)
    frames = result if isinstance(result, tuple) else (result,)
    assert [data.hex() for data in frames] == [
        part.replace(" ", "") for part in row["expected_bytes"].split("|")
    ]


def test_native_codec_matches_every_catalog_literal():
    for product, _section, action, save, code, raw, framed in CATALOG:
        assert codec.function(code, single=True).hex() == raw
        assert codec.function(code).hex() == framed
        profile = PROFILES[product]
        if _section == "off_30":
            assert profile.alarm[action] == code
        elif product != "none":
            control = next(a for a in profile.controls if a.action == action)
            assert (control.save if save else control.code) == code


def make_client(layout=0, *, without_response=True):
    row = GATT[layout]
    write = MagicMock(
        uuid=row["write"].lower(),
        properties=["write"] + (["write-without-response"] if without_response else []),
    )
    notify = MagicMock(uuid="11111111-0000-0000-0000-000000000000", properties=["notify"])
    service = SimpleNamespace(uuid=row["service"].lower(), characteristics=[write, notify])
    return MagicMock(
        is_connected=True,
        services=[service],
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )


async def runtime(hass, product="blue", layout=0):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Dream Sense",
        data={
            CONF_ADDRESS: "11:22:33:44:55:68",
            CONF_NAME: "Dream Sense",
            const.CONF_BED_TYPE: "dreamsense",
            const.CONF_PROTOCOL_VARIANT: product,
            const.CONF_PRODUCT_TYPE: product,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_MOTOR_PULSE_COUNT: 1,
        },
    )
    entry.add_to_hass(hass)
    c = AdjustableBedCoordinator(hass, entry)
    c._client = make_client(layout)
    ctrl = await create_controller(c, "dreamsense", product, c._client)
    assert isinstance(ctrl, DreamSenseController)
    c._controller = ctrl
    with patch.object(ctrl, "_wait", AsyncMock()):
        await ctrl.start_notify()
    c._client.write_gatt_char.reset_mock()
    ctrl._wait = AsyncMock()
    return c, ctrl


def written(c):
    return [call.args[1].hex() for call in c.client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("layout", range(6))
async def test_exact_startup_probes_and_gatt_properties(hass, layout):
    c, ctrl = await runtime(hass, "PB250", layout)
    ctrl.on_disconnect()
    with patch.object(ctrl, "_wait", AsyncMock()):
        await ctrl.start_notify()
        await ctrl.start_notify()  # no second initialization on this session
    assert written(c) == (
        ["6e02010071", "6e08010178", "6e0a000179", "6e15010185"]
        if layout == 0
        else ["00", "01", "01", "01"]
    )
    assert all(
        call.args[0] is c.client.services[0].characteristics[0] and call.kwargs["response"] is False
        for call in c.client.write_gatt_char.await_args_list
    )
    assert c.client.start_notify.call_args.args[0] is c.client.services[0].characteristics[1]


def test_gatt_first_endpoints_last_format_and_write_property():
    client = make_client(1, without_response=False)
    client.services += make_client(0).services
    selected = select(client, 2, "blue")
    assert selected.write is client.services[0].characteristics[0]
    assert selected.single is False and selected.response is True
    client.services[0].characteristics[0].properties = ["write-without-response"]
    client.services[1].characteristics[0].properties = ["write-without-response"]
    with raises_key("dreamsense_transport"):
        select(client, 2, "blue")


@pytest.mark.parametrize("product", tuple(PROFILES))
@pytest.mark.parametrize("layout", (0, 1))
async def test_all_product_actions_native_buttons_and_timer_shapes(hass, product, layout):
    c, ctrl = await runtime(hass, product, layout)
    entities = _button_entities_for(hass, c)
    ids = [e.unique_id for e in entities]
    assert len(set(ids)) == len(ids)
    for a in ctrl.profile.controls:
        with patch.object(ctrl, "_wait", AsyncMock()):
            await c.async_execute_controller_command(
                lambda live, action=a: live.press(action.action, duration_ms=100)
            )
        expected = [codec.function(a.code, single=layout == 1).hex()]
        if a.release:
            expected += ["6e" if layout == 1 else "6e01006edd"]
        assert written(c) == expected
        c.client.write_gatt_char.reset_mock()
        if a.save is not None:
            spec = next(s for s in ctrl.controller_button_specs if s.key == "save_" + a.action)
            assert spec.hold is None
            with patch.object(ctrl, "_wait", AsyncMock()):
                await c.async_execute_controller_command(spec.press_fn)
            assert written(c) == [codec.function(a.save, single=layout == 1).hex()]
            c.client.write_gatt_char.reset_mock()
    assert not any("MinuteTimer" in s.key for s in ctrl.controller_button_specs)
    if product == "L2RM":
        assert "HeadAndFootDown" not in [a.action for a in ctrl.profile.controls]
        assert not any("unknown" in s.name.lower() for s in ctrl.controller_button_specs)


async def test_cancel_after_actual_write_drains_release_on_owned_link(hass):
    c, ctrl = await runtime(hass)
    started, complete = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **_kwargs):
        if data == codec.function(0x24):
            started.set()
            await complete.wait()

    c.client.write_gatt_char.side_effect = write
    with patch.object(ctrl, "_wait", AsyncMock()):
        task = asyncio.create_task(ctrl.press("HeadUp", duration_ms=100))
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        complete.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert written(c) == ["6e01002493", "6e01006edd"]


async def test_subtick_release_and_stale_writer_do_not_transmit(hass):
    c, ctrl = await runtime(hass)
    first_tick = asyncio.Event()

    async def wait(_ms, event=None):
        first_tick.set()
        await event.wait()
        raise asyncio.CancelledError

    with patch.object(ctrl, "_wait", wait):
        task = asyncio.create_task(ctrl.press("HeadUp"))
        await first_tick.wait()
        c.cancel_command.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert written(c) == []
    c.cancel_command.clear()
    await ctrl.ble_lock.acquire()
    with patch.object(ctrl, "_wait", AsyncMock()):
        task = asyncio.create_task(ctrl.press("HeadUp", duration_ms=100))
        await asyncio.sleep(0)
        ctrl.on_disconnect()
        ctrl.ble_lock.release()
        with raises_key("dreamsense_session"):
            await task
    assert written(c) == []


async def test_cancelled_local_stop_never_sets_parent_scheduler_event(hass):
    c, ctrl = await runtime(hass)
    await ctrl.stop_all()
    assert not c.cancel_command.is_set()


def test_receive_fragment_expiry_and_exact_capability_signals():
    state = Receive()
    state.feed(bytes.fromhex("6e20"))
    state.expire()
    state.feed(bytes.fromhex("08050100009c"))
    assert state.alarm_revision == 0
    state.feed(bytes.fromhex("6e200d050201012e07001e00"))
    state.expire()
    assert not state.pending
    state.feed(bytes.fromhex("6e09010078"))
    state.feed(bytes.fromhex("6e0e00037f"))
    state.feed(bytes.fromhex("6e16010186"))
    assert state.capabilities == {"clock", "light", "music"}
    # Ordinary fragments are consumed early by the source framer, not fixed-length assembled.
    state = Receive()
    state.feed(bytes.fromhex("6e0901"))
    state.feed(bytes.fromhex("0078"))
    assert not state.capabilities
    state.feed(bytes.fromhex("6e2100008f"))  # reject source zero-length loop
    assert not state.pending


async def test_current_gates_light_close_default_side_rgb_and_stale_notifications(hass):
    c, ctrl = await runtime(hass, "orange")
    with raises_key("dreamsense_capability"):
        await ctrl.close_light()
    session = ctrl._session
    ctrl._notification(session, session.notify, bytearray.fromhex("6e0e00037f"))
    ctrl.select_side("right")
    await ctrl.close_light()
    await ctrl.light_settings(color=(1, 2, 3), seconds=300)
    assert written(c) == ["6e010075e4", "6e0b012ca6", "6e0cff017a6e0d020380"]
    ctrl.on_disconnect()
    ctrl._notification(session, session.notify, bytearray.fromhex("6e09010078"))
    assert not ctrl._receive.capabilities


async def test_delivered_timer_state_survives_release_failure(hass):
    c, ctrl = await runtime(hass)

    async def write(_char, data, **_kwargs):
        if data == codec.function(0x6E):
            raise OSError("release failed")

    c.client.write_gatt_char.side_effect = write
    with pytest.raises(OSError):
        await c.async_execute_controller_command(lambda live: live.set_massage_timer(10))
    assert c.controller_state.get(MASSAGE_TIMER_MINUTES) == 10


async def test_timer_unknown_is_distinct_from_off_and_owner_fences_publication(hass):
    from custom_components.adjustable_bed.command_scheduler import note_frame_skipped
    from custom_components.adjustable_bed.select import (
        MASSAGE_TIMER_DESCRIPTION,
        AdjustableBedMassageTimerSelect,
    )

    c, ctrl = await runtime(hass)
    timer = AdjustableBedMassageTimerSelect(
        c, MASSAGE_TIMER_DESCRIPTION, list(ctrl.massage_timer_options), has_off=True
    )
    await c.async_execute_controller_command(lambda live: live.set_massage_timer(10))
    assert timer.current_option == "10 min"

    async def stale_owner(live):
        with live.sent_state(MASSAGE_TIMER_MINUTES(20), is_current=lambda: False):
            await live._send(codec.function(0x5F), c.cancel_command)

    await c.async_execute_controller_command(stale_owner)
    assert timer.current_option == "10 min"

    async def partial(live):
        with live.sent_state(MASSAGE_TIMER_MINUTES(20), is_current=lambda: True):
            await live._send(codec.function(0x5F), c.cancel_command)
            note_frame_skipped()

    await c.async_execute_controller_command(partial)
    assert c.controller_state[MASSAGE_TIMER_MINUTES] == STATE_UNKNOWN
    assert timer.current_option is None
    c.handle_controller_state_updates(MASSAGE_TIMER_MINUTES(None))
    assert timer.current_option == "Off"
    ctrl.on_disconnect()
    assert c.controller_state[MASSAGE_TIMER_MINUTES] == STATE_UNKNOWN
    assert timer.current_option is None


async def test_repeat_list_observed_ids_update_delete_and_stale_fence(hass):
    c, ctrl = await runtime(hass, "AFEG300")
    session = ctrl._session
    ctrl._notification(session, session.notify, bytearray.fromhex("6e09010078"))
    request = AlarmRequest(
        enabled=True,
        hour=7,
        minute=30,
        wake_action="zero_g",
        slot=7,
        reference_time=datetime(2026, 11, 20, tzinfo=UTC),
    )

    async def reply(_char, data, **_kwargs):
        if data == p.alarm_list():
            ctrl._notification(
                session,
                session.notify,
                bytearray(codec.record_20_len(5, 2, 1, (7, 1, 69, 7, 30, 0))),
            )

    c.client.write_gatt_char.side_effect = reply
    await ctrl.check_alarm(request)
    identity = ctrl.alarm_record_identity(request)
    await ctrl.configure_alarm(replace(request, record_identity=identity))
    assert written(c) == [p.alarm_list().hex(), p.alarm_add(7, 1, 69, 7, 30).hex()]
    assert not ctrl._receive.alarms
    await ctrl.check_alarm(request)
    identity = ctrl.alarm_record_identity(request)
    await ctrl.configure_alarm(replace(request, enabled=False, record_identity=identity))
    assert written(c)[-1] == p.alarm_add(7, 0, 69, 7, 30).hex()
    await ctrl.check_alarm(request)
    identity = ctrl.alarm_record_identity(request)
    await ctrl.delete_alarm(7, identity)
    assert written(c)[-1] == p.alarm_delete(7).hex()
    with raises_key("dreamsense_alarm_record"):
        await ctrl.configure_alarm(replace(request, slot=8))
    ctrl._receive.alarm_revision += 1
    with raises_key("dreamsense_alarm_record"):
        await ctrl.configure_alarm(replace(request, record_identity=identity))


async def test_actual_shared_alarm_clock_and_lighting_action(hass):
    c, ctrl = await runtime(hass)
    session = ctrl._session
    for signal in ("6e09010078", "6e0e00037f"):
        ctrl._notification(session, session.notify, bytearray.fromhex(signal))
    await services.async_register_services(hass)
    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(c, const.SIDE_BOTH)], [])),
        patch.object(ctrl, "_wait", AsyncMock()),
    ):
        await hass.services.async_call(
            const.DOMAIN, "set_alarm", {"device_id": "bed", "enabled": False}, blocking=True
        )
        assert written(c) == ["6e05000073", "6e06000074"]
        c.client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "dreamsense_light",
            {"device_id": "bed", "rgb_color": [1, 2, 3]},
            blocking=True,
        )
        assert written(c) == ["6e0cff017a6e0d020380"]
        c.client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": "bed", "control": "HeadUp", "duration": 0.1},
            blocking=True,
        )
        assert written(c) == ["6e01002493", "6e01006edd"]


@pytest.mark.parametrize("product", CHOICES)
async def test_native_setup_persists_product_and_profile(hass, product):
    from custom_components.adjustable_bed import _async_sync_profile_ids
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from tests.form_helpers import finish_new_bed
    from tests.test_richmat_family_flow import setup_flow

    flow = setup_flow(hass, **{const.CONF_BED_TYPE: "dreamsense"})
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: product})
        result = await finish_new_bed(flow, result)
    saved = MockConfigEntry(domain=const.DOMAIN, data=result["data"])
    saved.add_to_hass(hass)
    _async_sync_profile_ids(hass, saved)
    assert saved.data[const.CONF_PROFILE_ID] == f"dreamsense:{product}"
    assert saved.data[const.CONF_PRODUCT_TYPE] == product
    assert {const.CONF_PROTOCOL_VARIANT, const.CONF_PRODUCT_TYPE} <= per_side_profile(
        "dreamsense", product
    ).keys
    c = AdjustableBedCoordinator(hass, saved)
    await c.async_prime_offline_controller()
    assert c.capability_controller.profile == PROFILES[product]


@pytest.mark.parametrize("word", ("QRRM", "COOL", "MPE_", "209A", "BED-"))
def test_discovery_offers_app_without_selecting_product(word):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    info = MagicMock(service_uuids=[], manufacturer_data={})
    info.name = "prefix" + word + "suffix"
    result = detect_bed_type_detailed(info)
    assert result.bed_type == "dreamsense" or "dreamsense" in (result.ambiguous_types or [])


async def test_pair_side_cleanup_and_physical_setting_rejection(hass):
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from tests.error_helpers import raises_key

    c, ctrl = await runtime(hass, "orange")
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Pair",
        data={**c.entry.data, const.CONF_PAIR_ID: "dreamsense-pair"},
    )
    entry.add_to_hass(hass)
    pair = SingleAddressPairedCoordinator(hass, entry, c)
    with patch.object(ctrl, "_wait", AsyncMock()):
        await pair.children[const.SIDE_RIGHT].async_execute_controller_command(
            lambda live: live.press("HeadUp", duration_ms=100)
        )
    assert written(c) == ["6e01012494", "6e01016ede"]
    with ctrl.side_scope(const.SIDE_RIGHT), raises_key("dreamsense_physical"):
        await ctrl.light_settings(color=(1, 2, 3))
    # Pair admission owns its scheduler event; controller-local stop leaves it alone.
    event = c.cancel_command
    before = event.is_set()
    await ctrl.stop_all()
    assert event.is_set() == before


async def test_startup_is_not_command_delivery_and_no_profile_switch_write(hass):
    from tests.error_helpers import raises_key

    c, ctrl = await runtime(hass, "PB250")

    async def startup(live):
        live.on_disconnect()
        with (
            delivered(lambda status: outcomes.append(status)),
            patch.object(live, "_wait", AsyncMock()),
        ):
            await live.start_notify()
            c.cancel_command.set()

    from custom_components.adjustable_bed.command_scheduler import Delivery, delivered

    outcomes = []
    await c.async_execute_controller_command(startup)
    assert outcomes == [Delivery.NONE]
    c.cancel_command.clear()
    c.client.write_gatt_char.reset_mock()
    hass.config_entries.async_update_entry(
        c.entry, data={**c.entry.data, const.CONF_PROTOCOL_VARIANT: "blue"}
    )
    with raises_key("dreamsense_session"), patch.object(ctrl, "_wait", AsyncMock()):
        await ctrl.press("HeadUp", duration_ms=100)
    assert written(c) == []


async def test_observed_record_fence_is_checked_inside_paced_writer(hass):
    from tests.error_helpers import raises_key

    c, ctrl = await runtime(hass, "AFEG300")
    session = ctrl._session
    ctrl._notification(session, session.notify, bytearray.fromhex("6e09010078"))
    ctrl._notification(
        session, session.notify, bytearray(codec.record_20_len(5, 2, 1, (7, 249, 69, 7, 30, 0)))
    )
    identity = (7, ctrl._receive.alarm_revision)
    entered, unblock = asyncio.Event(), asyncio.Event()

    async def pace(_ms, _event=None):
        entered.set()
        await unblock.wait()

    ctrl._wait = pace
    ctrl._last_write = asyncio.get_running_loop().time()
    task = asyncio.create_task(ctrl.delete_alarm(7, identity))
    await entered.wait()
    ctrl._notification(
        session, session.notify, bytearray(codec.record_20_len(5, 2, 1, (7, 249, 69, 7, 31, 0)))
    )
    unblock.set()
    with raises_key("dreamsense_alarm_record"):
        await task
    assert written(c) == []


async def test_shared_repeat_requires_explicit_observed_slot_and_delete_action(hass):
    from tests.error_helpers import raises_key

    c, ctrl = await runtime(hass, "AFEG300")
    session = ctrl._session
    ctrl._notification(session, session.notify, bytearray.fromhex("6e09010078"))
    ctrl._notification(
        session, session.notify, bytearray(codec.record_20_len(5, 2, 1, (7, 249, 69, 7, 30, 0)))
    )
    await services.async_register_services(hass)
    with patch.object(
        services, "_resolve_sided_targets", return_value=([(c, const.SIDE_BOTH)], [])
    ):
        with raises_key("alarm_slot_required"):
            await hass.services.async_call(
                const.DOMAIN, "set_alarm", {"device_id": "bed", "enabled": False}, blocking=True
            )
        assert written(c) == []
        await hass.services.async_call(
            const.DOMAIN,
            "dreamsense_delete_alarm",
            {"device_id": "bed", "alarm_number": 7},
            blocking=True,
        )
        assert written(c) == [p.alarm_delete(7).hex()]


def test_alarm_list_keeps_separately_notified_records_and_no_array_extension():
    state = Receive()
    state.feed(codec.record_20_len(5, 2, 1, (1, 1, 69, 7, 30, 0)))
    state.feed(codec.record_20_len(5, 2, 1, (7, 249, 46, 22, 45, 0)))
    assert set(state.alarms) == {1, 7}
    state.feed(codec.record_20_len(5, 3, 1, (7, 248, 46, 22, 45, 0)))
    assert state.alarms[7].repeat == 248


async def test_selection_survives_controller_rebuild_and_raw_link_rejects_right(hass):
    from custom_components.adjustable_bed.beds.dreamsense.controller import SELECTED_SIDE
    from custom_components.adjustable_bed.select import _select_entities_for

    c, ctrl = await runtime(hass, "orange")
    ctrl.select_side("right")
    selector = next(
        e
        for e in _select_entities_for(hass, c)
        if getattr(getattr(e, "_spec", None), "key", None) == "dreamsense_selected_side"
    )
    for layout in (0, 1):
        ctrl.on_disconnect()
        c._client = make_client(layout)
        replacement = await create_controller(c, "dreamsense", "orange", c._client)
        c._controller = replacement
        replacement._wait = AsyncMock()
        await replacement.start_notify()
        c.client.write_gatt_char.reset_mock()
        assert replacement._selection.side == "right"
        if layout == 0:
            await c.async_execute_controller_command(
                lambda live: live.press("HeadUp", duration_ms=100)
            )
            assert written(c) == ["6e01012494", "6e01016ede"]
        else:
            with raises_key("dreamsense_side"):
                await c.async_execute_controller_command(
                    lambda live: live.press("HeadUp", duration_ms=100)
                )
            assert written(c) == []
            assert replacement.controller_select_specs[0].options == ("left",)
            await replacement.stop_all()
            assert written(c) == ["6e"]
            c.client.write_gatt_char.reset_mock()
            await selector.async_select_option("left")
            assert c.controller_state[SELECTED_SIDE] == "left"
            await c.async_execute_controller_command(
                lambda live: live.press("HeadUp", duration_ms=100)
            )
            assert written(c) == ["24", "6e"]
        ctrl = replacement


async def test_product_change_rejects_movement_but_drains_original_stop(hass):
    c, ctrl = await runtime(hass)

    async def change_product(_char, data, **_kwargs):
        if data == codec.function(0x24):
            hass.config_entries.async_update_entry(
                c.entry,
                data={
                    **c.entry.data,
                    const.CONF_PRODUCT_TYPE: "orange",
                    const.CONF_PROTOCOL_VARIANT: "orange",
                },
            )

    c.client.write_gatt_char.side_effect = change_product
    await c.async_execute_controller_command(lambda live: live.press("HeadUp", duration_ms=100))
    assert written(c) == ["6e01002493", "6e01006edd"]
    with raises_key("dreamsense_session"):
        await ctrl.press("HeadUp", duration_ms=100)
    assert written(c) == ["6e01002493", "6e01006edd"]


async def test_cancelled_timer_final_write_preserves_delivery(hass):
    c, ctrl = await runtime(hass)
    entered, finish = asyncio.Event(), asyncio.Event()

    async def slow(_char, data, **_kwargs):
        if data == codec.function(0x5F):
            entered.set()
            await finish.wait()

    c.client.write_gatt_char.side_effect = slow
    task = asyncio.create_task(
        c.async_execute_controller_command(lambda live: live.set_massage_timer(10))
    )
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert c.controller_state[MASSAGE_TIMER_MINUTES] == 10
    assert written(c) == ["6e01005fce", "6e01006edd"]


async def test_sync_setting_delivery_finishes_before_release_failure(hass):
    from custom_components.adjustable_bed.beds.dreamsense.controller import SYNC

    c, ctrl = await runtime(hass, "E3RM")

    async def fail_stop(_char, data, **_kwargs):
        if data == codec.function(0x6E):
            raise OSError("release failed")

    c.client.write_gatt_char.side_effect = fail_stop
    spec = next(s for s in ctrl.controller_switch_specs if s.key == "dreamsense_sync")
    with pytest.raises(OSError):
        await c.async_execute_controller_command(lambda live: spec.set_fn(live, True))
    assert c.controller_state[SYNC] is True


@pytest.mark.parametrize("record", (False, True))
async def test_retired_delivery_never_repopulates_connection_state(hass, record):
    from custom_components.adjustable_bed.beds.dreamsense.controller import ALARMS
    from custom_components.adjustable_bed.state_keys import LIGHT_TIMER_OPTION

    c, ctrl = await runtime(hass, "AFEG300" if record else "blue")
    session = ctrl._session
    for signal in ("6e09010078", "6e0e00037f"):
        ctrl._notification(session, session.notify, bytearray.fromhex(signal))
    identity = None
    if record:
        ctrl._notification(
            session, session.notify, bytearray(codec.record_20_len(5, 2, 1, (7, 1, 69, 7, 30, 0)))
        )
        identity = (7, ctrl._receive.alarm_revision)
    entered, finish = asyncio.Event(), asyncio.Event()

    async def slow(_char, _data, **_kwargs):
        entered.set()
        await finish.wait()

    c.client.write_gatt_char.side_effect = slow

    async def command(live):
        if record:
            assert identity is not None
            await live.delete_alarm(7, identity)
        else:
            await live.light_settings(seconds=1800)

    task = asyncio.create_task(c.async_execute_controller_command(command))
    await entered.wait()
    ctrl.on_disconnect()
    finish.set()
    await task
    assert c.controller_state[ALARMS if record else LIGHT_TIMER_OPTION] is None


@pytest.mark.parametrize("number", (7.9, True))
async def test_delete_rejects_non_whole_id_before_any_write(hass, number):
    c, ctrl = await runtime(hass, "AFEG300")
    session = ctrl._session
    ctrl._notification(session, session.notify, bytearray.fromhex("6e09010078"))
    ctrl._notification(
        session, session.notify, bytearray(codec.record_20_len(5, 2, 1, (7, 1, 69, 7, 30, 0)))
    )
    await services.async_register_services(hass)
    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(c, const.SIDE_BOTH)], [])),
        raises_key("whole_number_required"),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "dreamsense_delete_alarm",
            {"device_id": "bed", "alarm_number": number},
            blocking=True,
        )
    assert written(c) == []


async def test_shared_alarm_accepts_observed_byte_id_without_inventing_capacity(hass):
    c, ctrl = await runtime(hass, "AFEG300")
    session = ctrl._session
    ctrl._notification(session, session.notify, bytearray.fromhex("6e09010078"))

    async def reply(_char, data, **_kwargs):
        if data == p.alarm_list():
            ctrl._notification(
                session,
                session.notify,
                bytearray(codec.record_20_len(5, 2, 1, (200, 1, 69, 7, 30, 0))),
            )

    c.client.write_gatt_char.side_effect = reply
    await services.async_register_services(hass)
    with patch.object(
        services, "_resolve_sided_targets", return_value=([(c, const.SIDE_BOTH)], [])
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {
                "device_id": "bed",
                "enabled": True,
                "slot": 200,
                "time": "07:30:00",
                "wake_action": "zero_g",
            },
            blocking=True,
        )
    assert written(c) == [p.alarm_list().hex(), p.alarm_add(200, 1, 69, 7, 30).hex()]


async def test_finite_hold_does_not_write_after_pacing_crosses_deadline(hass):
    from custom_components.adjustable_bed.beds.dreamsense import controller as module

    c, ctrl = await runtime(hass)
    clock = [0.0]

    async def advance(ms, _event=None):
        clock[0] += ms / 1000

    ctrl._wait = advance
    ctrl._last_write = None
    with patch.object(module, "monotonic", side_effect=lambda: clock[0]):
        await c.async_execute_controller_command(lambda live: live.hold_control("HeadUp", 150))
    assert written(c) == ["6e01002493", "6e01006edd"]


async def test_delayed_first_tick_sends_once_without_late_repeats(hass):
    from custom_components.adjustable_bed.beds.dreamsense import controller as module

    c, ctrl = await runtime(hass)
    clock = [0.0]

    async def overshoot(ms, _event=None):
        clock[0] += ms / 1000 + 0.075

    ctrl._wait = overshoot
    ctrl._last_write = None
    with patch.object(module, "monotonic", side_effect=lambda: clock[0]):
        await c.async_execute_controller_command(lambda live: live.hold_control("HeadUp", 150))
    assert written(c) == ["6e01002493", "6e01006edd"]


async def test_one_tick_finite_hold_sends_after_initial_timer_jitter(hass):
    from custom_components.adjustable_bed.beds.dreamsense import controller as module

    c, ctrl = await runtime(hass)
    clock = [0.0]

    async def advance(ms, _event=None):
        clock[0] += ms / 1000 + 0.001

    ctrl._wait = advance
    ctrl._last_write = None
    with patch.object(module, "monotonic", side_effect=lambda: clock[0]):
        await c.async_execute_controller_command(lambda live: live.hold_control("HeadUp", 100))
    assert written(c) == ["6e01002493", "6e01006edd"]


@pytest.mark.parametrize("operation", ("update", "delete"))
@pytest.mark.parametrize(
    ("incoming_number", "incoming_minute", "allowed"),
    ((8, 0, True), (7, 30, True), (7, 31, False)),
)
async def test_repeat_alarm_identity_ignores_other_records_but_fences_changes(
    hass, operation, incoming_number, incoming_minute, allowed
):
    c, ctrl = await runtime(hass, "AFEG300")
    session = ctrl._session
    ctrl._notification(session, session.notify, bytearray.fromhex("6e09010078"))

    def record(number, minute):
        ctrl._notification(
            session,
            session.notify,
            bytearray(codec.record_20_len(5, 2, 1, (number, 1, 69, 7, minute, 0))),
        )

    async def reply(_char, data, **_kwargs):
        if data == p.alarm_list():
            record(7, 30)

    c.client.write_gatt_char.side_effect = reply
    request = AlarmRequest(
        enabled=True,
        hour=7,
        minute=30,
        wake_action="zero_g",
        slot=7,
        reference_time=datetime(2026, 11, 20, tzinfo=UTC),
    )
    await ctrl.check_alarm(request)
    identity = ctrl.alarm_record_identity(request)
    assert identity is not None

    async def paced_reply(_ms, _event=None):
        record(incoming_number, incoming_minute)

    ctrl._wait = paced_reply
    ctrl._last_write = asyncio.get_running_loop().time()
    if operation == "update":
        command = ctrl.configure_alarm(replace(request, record_identity=identity))
        expected = p.alarm_add(7, 1, 69, 7, 30)
    else:
        command = ctrl.delete_alarm(7, identity)
        expected = p.alarm_delete(7)
    if allowed:
        await command
        assert written(c) == [p.alarm_list().hex(), expected.hex()]
    else:
        with raises_key("dreamsense_alarm_record"):
            await command
        assert written(c) == [p.alarm_list().hex()]


async def test_same_raw_created_selector_tracks_framed_and_raw_reconnects(hass):
    from custom_components.adjustable_bed.select import _select_entities_for

    c, ctrl = await runtime(hass, "orange", 1)
    selector = next(
        e
        for e in _select_entities_for(hass, c)
        if getattr(getattr(e, "_spec", None), "key", None) == "dreamsense_selected_side"
    )
    shown = []
    selector.async_write_ha_state = lambda: shown.append(selector.options)
    assert selector.options == ["left"]
    unsubscribe = c.register_controller_state_callback(selector._handle_controller_state_update)
    try:
        for layout in (0, 1):
            ctrl.on_disconnect()
            c._client = make_client(layout)
            ctrl = await create_controller(c, "dreamsense", "orange", c._client)
            c._controller = ctrl
            ctrl._wait = AsyncMock()
            await ctrl.start_notify()
            c.client.write_gatt_char.reset_mock()
            if layout == 0:
                assert selector.options == ["left", "right"]
                assert shown[-1] == ["left", "right"]
                await selector.async_select_option("right")
                assert selector.current_option == "right"
                await c.async_execute_controller_command(
                    lambda live: live.press("HeadUp", duration_ms=100)
                )
                assert written(c) == ["6e01012494", "6e01016ede"]
            else:
                assert selector.options == ["left"]
                assert shown[-1] == ["left"]
                assert selector.current_option is None
                with raises_key("option_unavailable"):
                    await selector.async_select_option("right")
                await selector.async_select_option("left")
                assert selector.current_option == "left"
                await c.async_execute_controller_command(
                    lambda live: live.press("HeadUp", duration_ms=100)
                )
                assert written(c) == ["24", "6e"]
    finally:
        unsubscribe()


async def test_raw_cached_selector_stays_left_only_during_disconnect(hass):
    from custom_components.adjustable_bed.beds.dreamsense.controller import DreamSenseController
    from custom_components.adjustable_bed.select import _select_entities_for

    c, ctrl = await runtime(hass, "orange", 1)
    selector = next(
        e
        for e in _select_entities_for(hass, c)
        if getattr(getattr(e, "_spec", None), "key", None) == "dreamsense_selected_side"
    )
    snapshot = ctrl.capability_snapshot()
    ctrl.on_disconnect()
    c._offline_controller = ctrl
    c._controller = None
    c._client = None
    assert selector.options == ["left"]
    with raises_key("option_unavailable"):
        await selector.async_select_option("right")
    assert ctrl._selection.side == "left"
    await selector.async_select_option("left")
    assert snapshot["single"] is True
    # A matching stored snapshot also gates a fresh process's offline controller.
    other = AdjustableBedCoordinator(
        hass,
        MockConfigEntry(
            domain=const.DOMAIN,
            title="Restored",
            data={**c.entry.data, CONF_ADDRESS: "11:22:33:44:55:69"},
        ),
    )
    restored = DreamSenseController(other, product="orange", capability_snapshot=snapshot)
    assert restored.controller_select_specs[0].options == ("left",)
    with raises_key("dreamsense_side"):
        restored.select_side("right")


LIGHT_REPLY = "6e0e00037f"


async def test_blue_light_timer_offers_what_the_app_shows_and_sends_its_stop(hass):
    from custom_components.adjustable_bed.state_keys import LIGHT_TIMER_OPTION

    c, ctrl = await runtime(hass, "blue")
    assert not ctrl.supports_light_timer
    session = ctrl._session
    ctrl._notification(session, session.notify, bytearray.fromhex(LIGHT_REPLY))
    assert ctrl.controller_number_specs == ()
    assert ctrl.light_timer_options == [
        "30 min", "40 min", "50 min", "1 hour", *(f"{n} hours" for n in range(2, 9))
    ]  # fmt: skip
    # The app shows 40 minutes for the slider position 4500 it sends.
    await c.async_execute_controller_command(lambda live: live.set_light_timer("40 min"))
    assert c.controller_state[LIGHT_TIMER_OPTION] == "40 min"
    # Two hours is the fifth stop, which sends 12600.
    await c.async_execute_controller_command(lambda live: live.light_settings(seconds=7200))
    assert c.controller_state[LIGHT_TIMER_OPTION] == "2 hours"
    # The range the action always took goes out as given and is no stop of the slider.
    await c.async_execute_controller_command(lambda live: live.light_settings(seconds=30))
    assert c.controller_state[LIGHT_TIMER_OPTION] is None
    assert written(c) == [p.light_seconds(n).hex() for n in (4500, 12600, 30)]
    for seconds in (301, 4500, 28801):
        with raises_key("dreamsense_action"):
            ctrl.validate_light(seconds=seconds)


async def test_other_products_keep_the_seconds_number_up_to_the_sliders_end(hass):
    from custom_components.adjustable_bed.beds.dreamsense.controller import LIGHT_SECONDS

    c, ctrl = await runtime(hass, "orange")
    session = ctrl._session
    ctrl._notification(session, session.notify, bytearray.fromhex(LIGHT_REPLY))
    assert not ctrl.supports_light_timer
    (spec,) = ctrl.controller_number_specs
    assert (spec.key, spec.native_min_value, spec.native_max_value, spec.native_step) == (
        "dreamsense_light_seconds", 0, 900, 1
    )  # fmt: skip
    for seconds in (30, 900):
        await c.async_execute_controller_command(lambda live, n=seconds: spec.set_fn(live, n))
        assert c.controller_state[LIGHT_SECONDS] == seconds
    assert written(c) == [p.light_seconds(n).hex() for n in (30, 900)]
    with raises_key("dreamsense_action"):
        ctrl.validate_light(seconds=901)


async def test_an_entry_without_a_stored_product_keeps_the_seconds_number(hass):
    c, _ = await runtime(hass, "blue")
    ctrl = DreamSenseController(c, product="blue", product_known=False)
    ctrl._known = {"light"}
    assert not ctrl.supports_light_timer
    assert [spec.key for spec in ctrl.controller_number_specs] == ["dreamsense_light_seconds"]
