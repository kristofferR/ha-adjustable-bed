"""S&S native controls, accepted catalog overrides and physical-link ownership."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.casper_base.silksnow import (
    Receive,
    SilkSnowController,
    decode,
)
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.pairing import supports_single_address_pairing
from custom_components.adjustable_bed.profiles.silksnow import (
    ACTIONS,
    EXCLUDED_ACTIONS,
    PROFILES,
)
from tests.alarm_helpers import call_set_alarm
from tests.test_casper_base import char, frames, make
from tests.test_silksnow_vectors import FROZEN


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    real = asyncio.sleep

    async def sleep(_):
        await real(0)

    monkeypatch.setattr(asyncio, "sleep", sleep)


def bed(model="slikpremier", *, transport=1):
    _, c = make(transport=transport)
    ctrl = SilkSnowController(c, product=model)
    c.controller = ctrl
    return ctrl, c


def native_runtime(ctrl, c):
    c.capability_controller = ctrl
    c.entity_side = c.controller_side = None
    c.device_info = {}
    c.entity_unique_id.side_effect = lambda key: "silksnow_" + key

    async def dispatch(command, **_kwargs):
        await command(ctrl)

    c.async_execute_controller_command = AsyncMock(side_effect=dispatch)


@pytest.mark.parametrize("model", ["slikenhanced", "slikpremier"])
async def test_native_first_white_turn_on_chooses_white_without_assumed_power(model):
    from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight
    from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON

    ctrl, c = bed(model)
    native_runtime(ctrl, c)
    await ctrl.start_notify()
    ctrl.events["light_available"] = {}
    c.client.write_gatt_char.reset_mock()
    light = AdjustableBedLight(c, LIGHT_DESCRIPTION)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on()
    assert frames(c) == [codec.rgb(255, 255, 255).hex()]
    assert ctrl.current_light_rgb_color == (255, 255, 255)
    assert c.controller_state.get(UNDER_BED_LIGHTS_ON) is None


async def test_alarm_refresh_and_model_use_their_native_meaningful_surfaces():
    from homeassistant.const import EntityCategory

    from custom_components.adjustable_bed.button import ControllerActionButton

    ctrl, c = bed("nisconup300")
    native_runtime(ctrl, c)
    refresh = next(
        spec for spec in ctrl.controller_button_specs if spec.key == "silksnow_alarm_refresh"
    )
    button = ControllerActionButton(c, refresh)
    assert button.entity_category is EntityCategory.DIAGNOSTIC
    assert not button.entity_registry_enabled_default
    assert not ctrl.controller_state_sensor_specs[0].attribute_keys
    ctrl.events["rgb_timer"] = {"minutes": 104}
    assert ctrl.protocol_diagnostics["events"] == ctrl.events


async def test_native_white_color_is_reused_without_inventing_power():
    from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight
    from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON

    ctrl, c = bed("slikenhanced")
    native_runtime(ctrl, c)
    await ctrl.start_notify()
    ctrl.events["light_available"] = {}
    c.client.write_gatt_char.reset_mock()
    light = AdjustableBedLight(c, LIGHT_DESCRIPTION)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(rgb_color=(18, 52, 86))
    light._handle_light_state(c.controller_state)
    assert light.rgb_color == ctrl.current_light_rgb_color == (18, 52, 86)
    assert c.controller_state.get(UNDER_BED_LIGHTS_ON) is None
    await light.async_turn_on()
    assert frames(c) == ["6e0cff128b6e0d345605"] * 2


@pytest.mark.parametrize("model,option", [("slikenhanced", "7.5 min"), ("nisconup355b", "300 min")])
async def test_native_timer_publishes_sent_and_received_options(model, option):
    from custom_components.adjustable_bed.beds.casper_base.protocol import Event
    from custom_components.adjustable_bed.select import (
        LIGHT_TIMER_DESCRIPTION,
        AdjustableBedControllerStateSelect,
    )

    ctrl, c = bed(model)
    native_runtime(ctrl, c)
    await ctrl.start_notify()
    ctrl.events["light_available"] = {}
    timer = AdjustableBedControllerStateSelect(c, LIGHT_TIMER_DESCRIPTION, ctrl.light_timer_options)
    await timer.async_select_option(option)
    assert timer.current_option == option
    if ctrl.product[7]:
        ctrl._consume(Event("rgb_timer", {"minutes": 390}))
        assert timer.current_option == "390 min"
        ctrl._consume(Event("rgb_timer", {"minutes": 301}))
        assert timer.current_option is None
    ctrl.on_disconnect()
    assert timer.current_option is None


async def test_literal_timer_reply_retains_artifact_directional_encoding():
    from custom_components.adjustable_bed.select import (
        LIGHT_TIMER_DESCRIPTION,
        AdjustableBedControllerStateSelect,
    )

    ctrl, c = bed("nisconup355b")
    native_runtime(ctrl, c)
    await ctrl.start_notify()
    ctrl.events["light_available"] = {}
    timer = AdjustableBedControllerStateSelect(c, LIGHT_TIMER_DESCRIPTION, ctrl.light_timer_options)
    await timer.async_select_option("300 min")
    assert timer.current_option == "300 min"
    data = bytes.fromhex("6e200a04020200012ccd")
    assert decode(data).values["minutes"] == 104
    c.client.start_notify.call_args.args[1](ctrl._link.notify, bytearray(data))
    assert timer.current_option is None


async def test_empty_alarm_refresh_removes_old_published_records():
    from custom_components.adjustable_bed.beds.casper_base.controller import CASPER_BASE_ALARMS
    from custom_components.adjustable_bed.beds.casper_base.protocol import Event

    ctrl, c = bed("nisconup300")
    await ctrl.start_notify()
    ctrl.events["clock_available"] = {}
    alarm = {"id": 1, "hour": 7, "minute": 30, "mode": 69, "mask": 130}
    ctrl._consume(Event("alarm_list", alarm))
    ctrl._publish()
    assert c.controller_state[CASPER_BASE_ALARMS] == [alarm]
    await ctrl.refresh_alarms()
    assert ctrl.alarms == c.controller_state[CASPER_BASE_ALARMS] == []


@pytest.mark.parametrize("kind", ["color", "timer"])
@pytest.mark.parametrize("delivery", ["unsent", "cancelled", "replaced"])
async def test_sent_light_settings_follow_delivery_and_original_link(kind, delivery):
    from custom_components.adjustable_bed import command_scheduler as scheduler
    from custom_components.adjustable_bed.state_keys import LIGHT_TIMER_OPTION, UNDER_BED_LIGHTS_RGB

    ctrl, c = bed("slikenhanced")
    await ctrl.start_notify()
    ctrl.events["light_available"] = {}
    c.client.write_gatt_char.reset_mock()
    key, value = (
        (UNDER_BED_LIGHTS_RGB, (18, 52, 86)) if kind == "color" else (LIGHT_TIMER_OPTION, "7.5 min")
    )

    async def send():
        context = scheduler.CommandContext(
            scheduler_token=object(),
            cancel_event=c.cancel_command,
            admitted_stop_epoch=0,
            intent_id="silksnow-setting",
            kind=scheduler.CommandKind.COMMAND,
            group_id=None,
            resources=frozenset({"*"}),
        )
        token = scheduler._CURRENT_COMMAND_CONTEXT.set(context)
        try:
            if kind == "color":
                await ctrl.set_light_color((18, 52, 86))
            else:
                await ctrl.set_light_timer("7.5 min")
        finally:
            scheduler._CURRENT_COMMAND_CONTEXT.reset(token)

    if delivery == "unsent":
        c.cancel_command.set()
        await send()
        assert frames(c) == []
    else:
        entered, acknowledged = asyncio.Event(), asyncio.Event()

        async def write(*_args, **_kwargs):
            entered.set()
            await acknowledged.wait()

        c.client.write_gatt_char.side_effect = write
        task = asyncio.create_task(send())
        await asyncio.wait_for(entered.wait(), 2)
        if delivery == "cancelled":
            task.cancel()
        else:
            c.client = MagicMock(is_connected=True)
            ctrl.on_disconnect()
        acknowledged.set()
        if delivery == "cancelled":
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
    assert c.controller_state.get(key) == (value if delivery == "cancelled" else None)


@pytest.mark.parametrize("key", PROFILES)
def test_exact_accepted_product_membership_and_overrides(key):
    ctrl, c = bed(key)
    raw = FROZEN["products"][key]
    assert ctrl.product[0] == raw[0]
    assert list(ctrl.product[6:]) == raw[6:]
    for group, details in zip(ctrl.product[1:6], raw[1:6], strict=True):
        assert [list(ACTIONS[i]) for i in group] == [
            [x["action"].removeprefix("deviceFunctionItem"), x["opcode"], x["long_opcode"]]
            for detail in details
            for x in FROZEN["commands"]
            if x["detail"] == detail
        ]
    assert EXCLUDED_ACTIONS.isdisjoint(ctrl.actions)
    assert supports_single_address_pairing("silksnow", key) == raw[11]
    assert not ctrl.supports_single_address_pairing
    assert not frames(c)
    assert not any("music" in spec.key for spec in ctrl.controller_button_specs)
    for spec in ctrl.controller_button_specs:
        if spec.key.startswith("silksnow_") and spec.key != "silksnow_alarm_refresh":
            assert spec.card.section == "lighting"


@pytest.mark.parametrize("transport", range(6))
async def test_six_gatt_routes_initialize_and_send_exact_premier_overrides(transport):
    ctrl, c = bed(transport=transport)
    await ctrl.start_notify()
    assert frames(c) == (
        ["00", "01", "01"] if transport == 0 else ["6e02010071", "6e08010178", "6e0a000179"]
    )
    c.client.write_gatt_char.reset_mock()
    for method in (ctrl.move_head_up, ctrl.move_back_up, ctrl.move_legs_up):
        await method()
    expected = [op for code in (0x3F, 0x24, 0x26) for op in [code] * 3 + [0x6E]]
    assert frames(c) == [codec.function(op, single=transport == 0).hex() for op in expected]
    assert all(call.kwargs["response"] is False for call in c.client.write_gatt_char.call_args_list)


async def test_nullable_writer_and_stored_encoding_are_independent():
    ctrl, c = bed(transport=0)
    raw_service = c.client.services[0]
    unknown = SimpleNamespace(
        uuid="00000000-0000-0000-0000-000000000001",
        characteristics=[char(codec.TRANSPORTS["w1"].write_uuid, "write"), char("other", "notify")],
    )
    c.client.services = [unknown, raw_service, unknown]
    await ctrl.start_notify()
    assert ctrl._write_char is raw_service.characteristics[0]
    assert ctrl._notify_char is unknown.characteristics[1]
    assert frames(c) == ["6e02010071", "6e08010178", "6e0a000179"]
    ctrl.on_disconnect()
    c.client.services = [unknown]
    c.client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError, match="writable"):
        await ctrl.start_notify()
    assert not frames(c)


async def test_cancel_before_attempt_sends_no_cleanup():
    ctrl, c = bed()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    c.cancel_command.set()
    await ctrl.move_back_up()
    assert not frames(c)


async def test_move_cancel_releases_only_original_link():
    ctrl, c = bed()
    await ctrl.start_notify()
    old = c.client
    old.write_gatt_char.reset_mock()

    async def replace_link(*args, **kwargs):
        ctrl.on_disconnect()
        c.client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock())
        raise asyncio.CancelledError

    old.write_gatt_char.side_effect = replace_link
    with pytest.raises(asyncio.CancelledError):
        await ctrl.move_back_up()
    assert len(old.write_gatt_char.call_args_list) == 1
    c.client.write_gatt_char.assert_not_called()


async def test_task_cancel_releases_attempted_side_with_fresh_event():
    ctrl, c = bed()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    first = True

    async def cancel(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            c.cancel_command.set()
            raise asyncio.CancelledError

    c.client.write_gatt_char.side_effect = cancel
    with pytest.raises(asyncio.CancelledError):
        await ctrl.move_back_up()
    assert frames(c) == ["6e01002493", "6e01006edd"]


@pytest.mark.parametrize("model", ["slikenhanced", "hushs375"])
async def test_massage_short_and_long_null_fallback_and_empty_release(model):
    ctrl, c = bed(model)
    await ctrl.start_notify()
    for action in ctrl.held_control_options:
        c.client.write_gatt_char.reset_mock()

        async def elapsed(coro, timeout):
            coro.close()
            assert timeout == 3
            raise TimeoutError

        with patch("asyncio.wait_for", side_effect=elapsed):
            await ctrl.hold_control(action, 3001)
        assert frames(c) == ["6e0100006f"]
        c.client.write_gatt_char.reset_mock()
        c.cancel_command.set()
        await ctrl.hold_control(action, 1000)
        assert frames(c) == [codec.function(ctrl.actions[action][0]).hex()]
        c.cancel_command.clear()
    c.client.write_gatt_char.reset_mock()
    await ctrl.async_perform_casper_base_action("MassageHeadInstensityStrengthen")
    assert frames(c) == ["6e01004cbb"]  # immediate icon has an empty release


async def test_native_buttons_memory_and_timer_route_to_real_actions():
    ctrl, c = bed("slikenhanced")
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    await ctrl.program_memory(1)
    await ctrl.preset_memory(1)
    await ctrl.set_massage_timer(10)
    for spec in ctrl.controller_button_specs:
        if spec.key == "casper_tvposition":
            await spec.press_fn(ctrl)
    assert frames(c) == ["6e01002b9a", "6e01002e9d", "6e01005fce", "6e010058c7"]


@pytest.mark.parametrize("rgb", [False, True])
async def test_native_light_builders_require_fresh_live_permission(rgb):
    ctrl, c = bed("nisconup355b" if rgb else "slikenhanced")
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError, match="reported"):
        await ctrl.set_light_color((18, 52, 86))
    ctrl.events["light_available"] = {}
    await ctrl.set_light_color((18, 52, 86))
    await ctrl.set_light_timer("300 min" if rgb else "7.5 min")
    await ctrl.lights_off()
    assert frames(c) == (
        ["6e0b20040101001234563b", "6e0a2004020100012ccc", "6e09200404010000a0"]
        if rgb
        else ["6e0cff128b6e0d345605", "6e0b01c23c", "6e010075e4"]
    )
    if rgb:
        c.client.write_gatt_char.reset_mock()
        await ctrl.light_effect("scroll")
        assert frames(c) == ["6e0a20040501000204a8"]
    ctrl.on_disconnect()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError, match="reported"):
        await ctrl.lights_off()
    assert not frames(c)


async def test_native_set_alarm_cancel_and_reconnect_permission(hass):
    ctrl, c = bed("nisconup300")
    await ctrl.start_notify()
    ctrl.events["clock_available"] = {}
    c.client.write_gatt_char.reset_mock()
    await call_set_alarm(
        hass, ctrl, {"enabled": False, "slot": 2}, side="both", bed_type="silksnow"
    )
    assert frames(c) == ["6e082005020102a0"]
    request = AlarmRequest(enabled=False, slot=2, reference_time=datetime.now(UTC))
    await ctrl.check_alarm(request)
    ctrl.on_disconnect()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError, match="Refresh"):
        await ctrl.configure_alarm(request)
    assert not frames(c)
    with pytest.raises(ServiceValidationError, match="selection"):
        ctrl.validate_alarm(AlarmRequest(enabled=True, reference_time=request.reference_time))


async def test_legacy_cancel_low_then_high_and_repeat_query_clock():
    ctrl, c = bed()
    await ctrl.start_notify()
    ctrl.events["clock_available"] = {}
    c.client.write_gatt_char.reset_mock()
    await ctrl.configure_alarm(AlarmRequest(enabled=False, reference_time=datetime.now(UTC)))
    assert frames(c) == ["6e05000073", "6e06000074"]
    repeat, c = bed("nisconup300")
    await repeat.start_notify()
    repeat.events["clock_available"] = {}
    c.client.write_gatt_char.reset_mock()
    await repeat.refresh_alarms()
    with patch(
        "custom_components.adjustable_bed.beds.casper_base.silksnow.dt_util.now",
        return_value=datetime(2026, 11, 27, 8, 30, 15, tzinfo=UTC),
    ):
        await repeat.sync_clock()
    assert frames(c) == ["6e0820050100009c", "6e0d20080301380b1b081e0f3a"]


def test_parser_keeps_only_direct_bed_events_and_raw_motor_identity():
    for vector in FROZEN["vectors"]:
        if vector["action"] == "parse":
            assert decode(bytes.fromhex(vector["expected_bytes"])) is not None
    assert decode(bytes.fromhex("6e16010186")) is None
    parser = Receive()
    packet = bytes.fromhex("6e200b040102001234563c")
    assert not parser.feed(packet[:4])
    assert parser.feed(packet[4:]) == [packet]
    assert parser.feed(bytes.fromhex("6e9036")) == [bytes.fromhex("6e9036")]
    assert parser.feed(bytes.fromhex("2d00")) == []
    assert decode(bytes.fromhex("6e90362d00")).values == {"index": 1, "status": 2, "angle": 45}
    assert not parser.feed(bytes.fromhex("6e200b040102001234563d"))


async def test_task_cancel_before_text_threshold_dispatches_short_on_original_link():
    ctrl, c = bed("slikenhanced")
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    entered = asyncio.Event()
    real_wait = asyncio.wait_for

    async def wait(coro, timeout):
        entered.set()
        return await real_wait(coro, timeout)

    with patch("asyncio.wait_for", side_effect=wait):
        task = asyncio.create_task(ctrl.hold_control("Massage10MinuteTimer", 5000))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert frames(c) == ["6e01005fce"]


async def test_record_settings_reject_a_single_address_child_target():
    ctrl, c = bed("hushl300sh")
    await ctrl.start_notify()
    ctrl.events.update(light_available={}, clock_available={})
    c.client.write_gatt_char.reset_mock()
    with ctrl.side_scope("right"):
        assert ctrl.alarm_capability is None
        with pytest.raises(ServiceValidationError, match="whole receiver"):
            await ctrl.set_light_color((1, 2, 3))
        with pytest.raises(ServiceValidationError, match="whole receiver"):
            await ctrl.configure_alarm(
                AlarmRequest(enabled=False, reference_time=datetime.now(UTC))
            )
    assert not frames(c)


@pytest.mark.parametrize("key", PROFILES)
@pytest.mark.parametrize("transport", [0, 1])
async def test_every_product_action_dispatches_accepted_detail_not_another_product(key, transport):
    ctrl, c = bed(key, transport=transport)
    await ctrl.start_notify()
    details = {row["detail"]: row for row in FROZEN["commands"]}
    accepted = {
        row["action"].removeprefix("deviceFunctionItem"): row
        for group in (1, 2, 3, 5)
        for detail in FROZEN["products"][key][group]
        for row in (details[detail],)
        if row["scope"] == "BED"
    }
    for action, detail in accepted.items():
        c.client.write_gatt_char.reset_mock()
        await ctrl.async_perform_casper_base_action(action)
        movement = action.endswith(("Up", "Down"))
        expected = [detail["opcode"]] * (3 if movement else 1)
        if movement:
            expected.append(110)
        assert frames(c) == [
            codec.function(opcode, single=transport == 0).hex() for opcode in expected
        ], (key, action)
        if detail["long_opcode"] is not None:
            c.client.write_gatt_char.reset_mock()
            await ctrl.async_perform_casper_base_action(action, save=True)
            assert frames(c) == [codec.function(detail["long_opcode"], single=transport == 0).hex()]


async def test_both_sides_cleanup_does_not_target_the_unattempted_side():
    ctrl, c = bed("hushl300sh")
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    c.client.write_gatt_char.side_effect = lambda *args, **kwargs: c.cancel_command.set()
    with ctrl.side_scope("both"):
        await ctrl.move_back_up()
    assert frames(c) == ["6e01002493", "6e01006edd"]
