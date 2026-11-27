"""MotionFlex model, native actions and exact-session safety contracts."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.motionflex.controller import (
    ALARM,
    MotionFlexController,
    select_link,
)
from custom_components.adjustable_bed.beds.motionflex.receive import Stream, parse
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.validators import (
    get_variants_for_bed_type,
    is_valid_variant_for_bed_type,
)
from tests.alarm_helpers import call_set_alarm
from tests.hold_lease_wire import virtual_clock
from tests.test_casper_base import char, frames
from tests.test_casper_base import make as casper_make
from tests.test_richmat_family_flow import setup_flow


@pytest.fixture(autouse=True)
async def clock():
    with virtual_clock():
        yield


def make(model="sn300", route="w1", response=False):
    _, coordinator = casper_make()
    coordinator.connection_generation = 0
    wire = codec.TRANSPORTS[route]
    tx = char(wire.write_uuid, "write", *(("write-without-response",) if not response else ()))
    coordinator.client.services = [
        SimpleNamespace(
            uuid=wire.service_uuid.upper(), characteristics=[tx, char("1234", "notify")]
        )
    ]
    controller = MotionFlexController(coordinator, product=model)
    coordinator.controller = controller
    return controller, coordinator


async def ready(*args, **kwargs):
    controller, coordinator = make(*args, **kwargs)
    await controller.async_discover_capabilities()
    await controller.start_notify()
    coordinator.client.write_gatt_char.reset_mock()
    return controller, coordinator


def notify(coordinator, data):
    callback = coordinator.client.start_notify.call_args.args[1]
    callback(char("1234", "notify"), bytearray.fromhex(data))


@pytest.mark.parametrize("route", ("n1", "w1", "w2", "w3", "w4", "w5"))
@pytest.mark.parametrize("response", (True, False))
async def test_startup_uses_selected_handles_and_independent_special_builders(route, response):
    controller, c = make(route=route, response=response)
    await controller.async_discover_capabilities()
    now = datetime(2026, 11, 27, 10, 20, 30, tzinfo=UTC)
    with patch(
        "custom_components.adjustable_bed.beds.motionflex.controller.dt_util.now", return_value=now
    ):
        await controller.start_notify()
    writes = frames(c)
    assert writes[0] == ("00" if route == "n1" else "6e02010071")
    assert writes[1:3] == [
        p.hex() for p in codec.time_sync(now, build=codec.record_20_len, first_hex=True)
    ]
    assert writes[3:] == (["01", "01"] if route == "n1" else ["6e08010178", "6e0a000179"])
    assert all(
        call.kwargs["response"] is response for call in c.client.write_gatt_char.call_args_list
    )
    assert c.client.start_notify.call_args.args[0].uuid == "1234"
    assert c.client.write_gatt_char.call_args.args[0] is c.client.services[0].characteristics[0]


def test_gatt_first_handles_but_last_service_encoding_and_exact_properties():
    controller, c = make()
    nordic = codec.TRANSPORTS["n1"]
    c.client.services.append(
        SimpleNamespace(
            uuid=nordic.service_uuid,
            characteristics=[char(nordic.write_uuid, "write"), char("later", "notify")],
        )
    )
    link = select_link(c.client, 0)
    assert link.tx is c.client.services[0].characteristics[0]
    assert link.rx.uuid == "1234" and link.compact
    c.client.services.reverse()
    link = select_link(c.client, 0)
    assert link.tx.uuid == nordic.write_uuid and not link.compact
    c.client.services = [
        SimpleNamespace(
            uuid=nordic.service_uuid,
            characteristics=[
                char(nordic.write_uuid, "write-without-response"),
                char("later", "notify"),
            ],
        )
    ]
    with pytest.raises(ValueError):
        select_link(c.client, 0)


@pytest.mark.parametrize(
    ("model", "axes", "slots", "tv"),
    [
        ("sn300", {"back", "legs", "head_feet"}, 1, True),
        ("sn500", {"back", "legs", "pillow", "lumbar"}, 0, False),
        ("hc800", {"back", "legs", "lumbar"}, 1, False),
    ],
)
async def test_actual_model_native_controls_and_separate_saves(model, axes, slots, tv):
    controller, c = await ready(model)
    assert {s.key for s in controller.motor_control_specs} == axes
    assert controller.memory_slot_count == slots
    assert controller.supports_preset_tv == tv
    for spec in controller.motor_control_specs:
        await spec.open_fn(controller)
        assert frames(c)[-1] == "6e01006edd"
    c.client.write_gatt_char.reset_mock()
    await controller.preset_zero_g()
    await controller.preset_anti_snore()
    for spec in controller.controller_button_specs:
        if not spec.key.startswith("motionflex_save_"):
            continue
        assert spec.requires_confirmation
        assert spec.card.section == "presets" and spec.card.role == "save"
        await spec.press_fn(controller)
    expected = ["6e010045b4", "6e010046b5", "6e010066d5", "6e010069d8"]
    if tv:
        expected.append("6e010064d3")
    assert frames(c) == expected
    c.client.write_gatt_char.reset_mock()
    await controller.preset_flat()
    await controller.massage_head_toggle()
    await controller.massage_foot_toggle()
    await controller.massage_mode_step()
    await controller.massage_off()
    for minute in (10, 20, 30):
        await controller.set_massage_timer(minute)
    await controller.lights_toggle()
    assert frames(c) == [
        codec.command(code).hex()
        for action in (0x31, 0x4C, 0x4E, 0x48, 0x5E, 0x5F, 0x63, 0x61, 0x3C)
        for code in (action, codec.STOP)
    ]
    assert not controller.position_number_specs
    assert not controller.supports_single_address_pairing


async def test_light_capability_native_color_duration_and_close():
    controller, c = await ready(route="n1")
    with pytest.raises(ValueError):
        await controller.set_light_color((18, 52, 86))
    notify(c, "6e0e00037f")
    await controller.set_light_color((18, 52, 86))
    await controller.set_light_timer("Always On")
    await controller.set_light_timer("15 min")
    close = next(s for s in controller.controller_button_specs if s.key.endswith("light_off"))
    assert close.card.section == "lighting"
    await close.press_fn(controller)
    assert frames(c) == ["6e0cff128b6e0d345605", "6e0bffff77", "6e0b038400", "75"]
    for invalid in ((True, 2, 3), (1.5, 2, 3), (-1, 2, 3), (256, 2, 3)):
        with pytest.raises(ValueError):
            await controller.set_light_color(invalid)
    with pytest.raises(ValueError):
        await controller.set_light_timer("16 min")
    await controller.stop_notify()
    assert not controller.supports_light_color_control


def alarm(**kwargs):
    return AlarmRequest(
        enabled=True,
        hour=12,
        wake_action="zero_g",
        reference_time=datetime(2026, 11, 27, 10, tzinfo=UTC),
        **kwargs,
    )


async def test_alarm_native_service_and_ack_only_after_complete_write(hass):
    controller, c = await ready(route="n1")
    with patch(
        "custom_components.adjustable_bed.beds.motionflex.controller.dt_util.now",
        return_value=datetime(2026, 11, 27, 10, tzinfo=UTC),
    ):
        await call_set_alarm(
            hass,
            controller,
            {"enabled": True, "time": "12:00", "wake_action": "tv"},
            bed_type="motionflex",
        )
    assert bytes(c.client.write_gatt_char.call_args_list[-1].args[1])[3] == 0x58
    assert c.controller_state[ALARM] is None
    notify(c, "6e07010177")
    assert c.controller_state[ALARM]["wake_action"] == "tv"
    c.client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await call_set_alarm(
            hass,
            controller,
            {"enabled": True, "time": "12:00", "wake_action": "zero_g", "weekdays": ["monday"]},
            bed_type="motionflex",
        )
    assert frames(c) == []
    await call_set_alarm(hass, controller, {"enabled": False}, bed_type="motionflex")
    assert frames(c) == ["6e05000073", "6e06000074"]
    notify(c, "6e07010278")
    assert c.controller_state[ALARM]["enabled"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"weekdays": (0,)},
        {"slot": 2},
        {"sound": "music_1"},
        {"light": True},
        {"wake_action": "flat"},
        {"hour": 24},
        {"minute": True},
        {"massage_duration": 10},
        {"mattress_side": "right"},
    ],
)
async def test_alarm_all_fields_preflight_before_write(changes):
    controller, c = await ready()
    with pytest.raises(ValueError):
        await controller.configure_alarm(replace(alarm(), **changes))
    assert frames(c) == []


async def test_stale_alarm_and_overflow_rejected_before_write():
    controller, c = await ready()
    for now in (datetime(2026, 11, 30, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)):
        with (
            patch(
                "custom_components.adjustable_bed.beds.motionflex.controller.dt_util.now",
                return_value=now,
            ),
            pytest.raises(ValueError),
        ):
            await controller.configure_alarm(alarm())
    assert frames(c) == []


async def test_cancelled_and_failed_movement_release_original_client():
    controller, c = await ready()
    old = c.client

    async def replace_client(*args, **kwargs):
        c.client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock())

    old.write_gatt_char.side_effect = replace_client
    with pytest.raises(ConnectionError):
        await controller.move_head_up()
    assert [bytes(call.args[1]).hex() for call in old.write_gatt_char.call_args_list] == [
        "6e01002493",
        "6e01006edd",
    ]
    assert not c.client.write_gatt_char.called


async def test_task_cancellation_settles_write_then_releases():
    controller, c = await ready()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def block(char, packet, **kwargs):
        if packet == codec.command(0x24):
            entered.set()
            await finish.wait()

    c.client.write_gatt_char.side_effect = block
    task = asyncio.create_task(controller.move_head_up())
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(c) == ["6e01002493", "6e01006edd"]


async def test_cancelled_successful_timer_write_still_updates_native_sent_state():
    from custom_components.adjustable_bed import command_scheduler as scheduler
    from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES
    from tests.test_shown_state import _running_command

    controller, c = await ready()
    c.controller_state[MASSAGE_TIMER_MINUTES] = 10
    entered, finish = asyncio.Event(), asyncio.Event()

    async def block(characteristic, packet, **kwargs):
        if packet == codec.command(0x63):
            entered.set()
            await finish.wait()

    c.client.write_gatt_char.side_effect = block
    token = scheduler._CURRENT_COMMAND_CONTEXT.set(_running_command(c.cancel_command))
    try:
        task = asyncio.create_task(controller.set_massage_timer(20))
        await entered.wait()
        task.cancel()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert frames(c) == ["6e010063d2", "6e01006edd"]
        assert c.controller_state[MASSAGE_TIMER_MINUTES] == 20
    finally:
        scheduler._CURRENT_COMMAND_CONTEXT.reset(token)


@pytest.mark.parametrize("change", ("cancel", "disconnect", "controller", "generation"))
async def test_mid_command_invalidation_stops_continuation_and_fences_callbacks(change):
    controller, c = await ready()
    raw = MagicMock()
    controller.set_raw_notify_callback(raw)
    old_callback = c.client.start_notify.call_args.args[1]
    old_client = c.client

    async def invalidate(characteristic, packet, **kwargs):
        if packet != codec.command(0x24):
            return
        if change == "cancel":
            c.cancel_command.set()
        elif change == "disconnect":
            old_client.is_connected = False
            controller.on_disconnect()
        elif change == "controller":
            c.controller = MotionFlexController(c, product="hc800")
        else:
            c.connection_generation += 1

    old_client.write_gatt_char.side_effect = invalidate
    with pytest.raises(asyncio.CancelledError if change == "cancel" else ConnectionError):
        await controller.move_head_up()
    expected = ["6e01002493"] + ([] if change == "disconnect" else ["6e01006edd"])
    assert frames(c) == expected
    if change != "cancel":
        old_callback(char("1234"), bytearray.fromhex("6e0e00037f"))
        raw.assert_not_called()
        assert not controller.supports_light_color_control


async def test_alarm_ack_cannot_confirm_just_the_low_frame():
    controller, c = await ready()

    async def acknowledge_low(characteristic, packet, **kwargs):
        if packet[1] == 5:
            notify(c, "6e07010177")

    c.client.write_gatt_char.side_effect = acknowledge_low
    with patch("custom_components.adjustable_bed.beds.motionflex.controller.dt_util.now", return_value=alarm().reference_time):
        await controller.configure_alarm(alarm())
    assert c.controller_state[ALARM] is None
    notify(c, "6e07010177")
    assert c.controller_state[ALARM]["enabled"] is True


async def test_side_and_missing_model_are_rejected_without_writes():
    controller, c = await ready()
    with controller.side_scope("right"), pytest.raises(ValueError):
        await controller.lights_toggle()
    assert frames(c) == []
    with pytest.raises(ValueError):
        MotionFlexController(c, product="auto")


async def test_partial_alarm_failure_discards_pending_and_stale_callbacks():
    controller, c = await ready()
    old_callback = c.client.start_notify.call_args.args[1]
    c.client.write_gatt_char.side_effect = [None, RuntimeError("second write failed")]
    with (
        patch(
            "custom_components.adjustable_bed.beds.motionflex.controller.dt_util.now",
            return_value=alarm().reference_time,
        ),
        pytest.raises(RuntimeError),
    ):
        await controller.configure_alarm(alarm())
    notify(c, "6e07010177")
    assert c.controller_state[ALARM] is None
    await controller.stop_notify()
    old_callback(char("1234"), bytearray.fromhex("6e0e00037f"))
    assert not controller.supports_light_color_control


@pytest.mark.parametrize("model", ("sn300", "sn500", "hc800"))
async def test_actual_setup_flow_owns_model_and_profile(hass, model):
    flow = setup_flow(hass)
    flow._manual_data.update({const.CONF_MOTOR_COUNT: 4, const.CONF_HAS_MASSAGE: False})
    with patch.object(flow, "_verification_possible", return_value=False):
        first = await flow.async_step_richmat_family({"choice": "motionflex"})
        assert first["step_id"] == "profile_questions"
        result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: model})
    assert result["type"] == "create_entry"
    data = result["data"]
    assert data[const.CONF_HAS_MASSAGE] is True
    assert data[const.CONF_MOTOR_COUNT] == {"sn300": 2, "sn500": 4, "hc800": 3}[model]
    assert resolve_profile_id(data) == "motionflex:" + model
    assert per_side_profile("motionflex", model).variant_owned
    assert get_variants_for_bed_type("motionflex") == {
        m: m.upper() for m in ("sn300", "sn500", "hc800")
    }
    assert not is_valid_variant_for_bed_type("motionflex", "auto")


def test_corrected_receive_offset_and_stream_boundaries():
    assert parse(bytes.fromhex("6e200e01020200012c022d006461")) == {
        "height": 30.0,
        "type": 2,
        "angle": 45,
        "monitorHeight": 10.0,
    }
    stream = Stream()
    assert stream.feed(bytes.fromhex("ff6e200903")) == []
    assert stream.feed(bytes.fromhex("010200019e6e0e00037f")) == [
        bytes.fromhex("6e200903010200019e"),
        bytes.fromhex("6e0e00037f"),
    ]
    assert Stream().feed(b"\x6e\x20\x00") == []


@pytest.mark.parametrize("route", ("n1", "w1"))
async def test_native_entities_use_real_coordinator_admission(
    hass, mock_coordinator_connected, mock_bleak_client, route
):

    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
    from custom_components.adjustable_bed.number import _position_number_specs

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="MotionFlex",
        data={
            "address": "AA:BB:CC:DD:EE:15",
            "name": "MotionFlex",
            "bed_type": "motionflex",
            const.CONF_PROTOCOL_VARIANT: "hc800",
            const.CONF_MOTOR_PULSE_COUNT: 2,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    _, stub = make("hc800", route=route)
    mock_bleak_client.services = stub.client.services
    for service in mock_bleak_client.services:
        for characteristic in service.characteristics:
            characteristic.descriptors = []
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    mock_bleak_client.disconnect = AsyncMock()
    try:
        await coordinator.async_prime_offline_controller()
        assert await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, MotionFlexController)
        assert not _position_number_specs(coordinator)
        buttons = _button_entities_for(hass, coordinator)
        mock_bleak_client.write_gatt_char.reset_mock()
        recall = next(b for b in buttons if b.unique_id.endswith("preset_zero_g"))
        await recall.async_press()
        save = next(b for b in buttons if b.unique_id.endswith("motionflex_save_zero_g"))
        await save.async_press()
        spec = next(s for s in controller.motor_control_specs if s.key == "lumbar")
        cover = AdjustableBedCover(coordinator, _build_cover_description(spec))
        cover.async_write_ha_state = MagicMock()
        await cover.async_open_cover()
        await cover.async_close_cover()
        values = [bytes(call.args[1]) for call in mock_bleak_client.write_gatt_char.call_args_list]
        expected = [0x45, 0x66, 0x3F, 0x3F, codec.STOP, 0x40, 0x40, codec.STOP]
        assert values == [codec.function(code, single=route == "n1") for code in expected]
    finally:
        await coordinator.async_shutdown()


@pytest.fixture
async def native_session(hass, mock_coordinator_connected, mock_bleak_client):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(domain=const.DOMAIN, title="MotionFlex", data={
        "address": "AA:BB:CC:DD:EE:15", "name": "MotionFlex", "bed_type": "motionflex",
        const.CONF_PROTOCOL_VARIANT: "hc800", const.CONF_MOTOR_PULSE_COUNT: 2,
        const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    _, stub = make("hc800")
    mock_bleak_client.services = stub.client.services
    for service in mock_bleak_client.services:
        for characteristic in service.characteristics:
            characteristic.descriptors = []
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    mock_bleak_client.disconnect = AsyncMock()
    try:
        await coordinator.async_prime_offline_controller()
        assert await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()
        yield coordinator, mock_bleak_client
    finally:
        mock_bleak_client.is_connected = False
        mock_bleak_client.disconnect = AsyncMock()
        await coordinator.async_shutdown()


@pytest.mark.parametrize("failure", ("still_connected", "error", "cancelled"))
async def test_real_failed_disconnect_restores_new_session_identity_and_fences_old_callback(native_session, failure):
    from bleak.exc import BleakError

    coordinator, client = native_session
    controller = coordinator.controller
    old_link = controller._link
    old_callback = client.start_notify.call_args.args[1]
    generation = coordinator.connection_generation
    raw = MagicMock()
    controller.set_raw_notify_callback(raw)
    notify(coordinator, "6e0e00037f")
    raw.reset_mock()
    client.disconnect = AsyncMock(side_effect={
        "still_connected": None, "error": BleakError("link stayed connected"),
        "cancelled": asyncio.CancelledError(),
    }[failure])
    if failure == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await coordinator.async_disconnect("idle_timeout")
    else:
        assert await coordinator.async_disconnect("idle_timeout") is False
    assert coordinator._link_ready and client.is_connected
    assert coordinator.connection_generation == generation
    assert controller._link is not None and controller._link is not old_link
    assert client.start_notify.await_count == 2
    assert not controller.supports_light_color_control
    old_callback(char("1234"), bytearray.fromhex("6e0e00037f"))
    raw.assert_not_called()
    assert not controller.supports_light_color_control
    notify(coordinator, "6e0e00037f")
    assert controller.supports_light_color_control
    raw.assert_called_once()
    client.write_gatt_char.reset_mock()
    await coordinator.async_execute_controller_command(lambda c: c.preset_zero_g())
    assert [bytes(call.args[1]) for call in client.write_gatt_char.call_args_list] == [codec.command(0x45)]


@pytest.mark.parametrize("change", ("client", "generation", "controller", "closed"))
async def test_retired_restore_metadata_cannot_attach_to_a_replacement(change):
    controller, c = await ready()
    old_client = c.client
    await controller.stop_notify()
    if change == "client":
        c.client = MagicMock(is_connected=True)
    elif change == "generation":
        c.connection_generation += 1
    elif change == "controller":
        c.controller = MotionFlexController(c, product="hc800")
    else:
        old_client.is_connected = False
    with pytest.raises(ConnectionError):
        await controller.start_notify()
    assert old_client.start_notify.await_count == 1
    assert controller._link is None and controller._resume_link is None


@pytest.mark.parametrize("assumed_on", (False, True))
async def test_native_rgb_color_on_and_idempotent_close_with_basic_toggle_retained(hass, native_session, assumed_on):
    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.light import AdjustableBedLight, _light_entities_for

    coordinator, client = native_session
    controller = coordinator.controller
    assert not controller.supports_discrete_light_control
    notify(coordinator, "6e0e00037f")
    assert controller.supports_discrete_light_control
    assert not controller.supports_explicit_light_on_control
    (entity,) = _light_entities_for(hass, coordinator)
    assert isinstance(entity, AdjustableBedLight)
    entity.async_write_ha_state = MagicMock()
    await entity.async_turn_on(rgb_color=(18, 52, 86))
    await entity.async_turn_on(rgb_color=(5, 6, 7))
    await entity.async_turn_on()
    entity._attr_is_on = assumed_on
    await entity.async_turn_off()
    await entity.async_turn_off()
    assert [bytes(call.args[1]) for call in client.write_gatt_char.call_args_list] == [
        codec.rgb(18, 52, 86), codec.rgb(5, 6, 7), codec.rgb(5, 6, 7), codec.command(0x75), codec.command(0x75),
    ]
    toggle, = [b for b in _button_entities_for(hass, coordinator) if b.unique_id.endswith("_toggle_light")]
    await toggle.async_press()
    assert [bytes(call.args[1]) for call in client.write_gatt_char.call_args_list][-2:] == [codec.command(0x3C), codec.command(codec.STOP)]
    client.write_gatt_char.reset_mock()
    await controller.stop_notify()
    assert not controller.supports_discrete_light_control
    assert not controller.supports_explicit_light_on_control
    with pytest.raises(NotImplementedError):
        await entity.async_turn_off()
    with pytest.raises(ValueError):
        await entity.async_turn_on(rgb_color=(1, 2, 3))
    assert not client.write_gatt_char.called
