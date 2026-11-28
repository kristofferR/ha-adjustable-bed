"""VivaSleep through public HA setup, entities, command lanes and live sessions."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.bed_traits import reads_positions
from custom_components.adjustable_bed.beds.bedgear.vivasleep import (
    SYNC_ENABLED,
    SYNC_MODE,
    VivaSleepController,
)
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    _confident_auto_detect,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.errors import setup_stopped
from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight
from custom_components.adjustable_bed.pairing import side_owned_profile_fields
from custom_components.adjustable_bed.profiles import vivasleep as app
from custom_components.adjustable_bed.state_keys import (
    LIGHT_TIMER_OPTION,
    UNDER_BED_LIGHTS_ON,
    UNDER_BED_LIGHTS_RGB,
)
from tests import test_bedgear as bedgear
from tests.form_helpers import answer_app
from tests.test_bedgear import name, notification, writes
from tests.test_moodbase import advertise

runtime = bedgear.runtime
clock = bedgear.clock
FIXTURES = Path(__file__).parent / "fixtures" / "vivasleep"
VECTORS = json.loads((FIXTURES / "full-vectors.json").read_text())
WIDGETS = json.loads((FIXTURES / "widgets.json").read_text())
EXAMPLES = dict(
    zip(
        (
            "panel_zero",
            "panel_one",
            "panel_two",
            "panel_three",
            "panel_four",
            "panel_five",
            "panel_six",
            "panel_six_zg",
            "panel_seven",
            "panel_eight",
            "panel_nine",
            "panel_a",
            "panel_d",
            "panel_e",
            "wr1140",
        ),
        ("00", "13", "23", "34", "44", "50", "60", "D0", "70", "80", "90", "15", "35", "E0", "97"),
        strict=True,
    )
)


async def install(co, selected):
    await co.controller.stop_notify()
    co.hass.config_entries.async_update_entry(
        co.entry,
        data={
            **co.entry.data,
            const.CONF_BED_TYPE: const.BED_TYPE_VIVASLEEP,
            const.CONF_BLE_DEVICE_NAME: selected,
        },
    )
    bed = await create_controller(
        co, const.BED_TYPE_VIVASLEEP, None, co.client, advertisement_local_name=selected
    )
    assert isinstance(bed, VivaSleepController)
    co._controller = bed
    co.client.write_gatt_char.reset_mock()
    await bed.start_notify()
    co.client.write_gatt_char.assert_not_awaited()
    return bed


@pytest.mark.parametrize("selector", EXAMPLES.values())
async def test_public_setup_owns_exact_original_name(hass, enable_custom_integrations, selector):
    selected = name(selector, mode="E")
    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info", return_value=[]
    ):
        flow = await hass.config_entries.flow.async_init(const.DOMAIN, context={"source": "user"})
        flow = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {CONF_ADDRESS: "manual"}
        )
        flow = await answer_app(hass, flow, const.BED_TYPE_VIVASLEEP)
        flow = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {CONF_ADDRESS: "AA:BB:CC:DD:EE:12"}
        )
    assert flow["step_id"] == "profile_questions"
    invalid = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {const.CONF_BLE_DEVICE_NAME: "Nickname"}
    )
    assert invalid["errors"] == {const.CONF_BLE_DEVICE_NAME: "vivasleep_profile"}
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {const.CONF_BLE_DEVICE_NAME: selected}
    )
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False),
        patch("custom_components.adjustable_bed.async_setup_entry", return_value=True),
    ):
        flow = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {CONF_NAME: "My bed", const.CONF_PREFERRED_ADAPTER: "auto"}
        )
    assert flow["type"] is FlowResultType.CREATE_ENTRY
    assert flow["data"][const.CONF_BLE_DEVICE_NAME] == selected
    assert not reads_positions(flow["data"])
    assert const.CONF_BLE_DEVICE_NAME in side_owned_profile_fields(flow["data"])
    with patch("custom_components.adjustable_bed.async_unload_entry", return_value=True):
        await hass.config_entries.async_unload(flow["result"].entry_id)


def test_discovery_is_an_app_candidate_not_an_assumed_sibling():
    result = detect_bed_type_detailed(advertise(name()))
    assert const.BED_TYPE_VIVASLEEP in (result.ambiguous_types or ())
    assert _confident_auto_detect(result) != const.BED_TYPE_VIVASLEEP
    assert const.BED_TYPE_VIVASLEEP not in (
        detect_bed_type_detailed(advertise("HHC-short")).ambiguous_types or ()
    )


@pytest.mark.parametrize("mode", ("0", "M"))
@pytest.mark.parametrize("selector", EXAMPLES.values())
async def test_every_model_control_uses_its_own_gate_and_cleanup(runtime, clock, selector, mode):
    _hass, co = runtime
    bed = await install(co, name(selector, mode=mode))
    assert not bed.supports_position_feedback
    assert not bed.supports_clock_sync
    for control in bed.profile.controls:
        co.client.write_gatt_char.reset_mock()
        if control.held:
            await co.async_execute_controller_command(
                lambda ctrl, key=control.key: ctrl.hold_control("vivasleep_" + key, 250)
            )
            command = bed.profile.writer_bytes("$" + control.letter)
            expected = [command] * 2
            if control.release == "stop":
                expected += [bed.profile.writer_bytes("$b")] * 5
            elif control.release == "fallback":
                expected += [command] * 3
            assert writes(co) == expected
        else:
            await co.async_execute_controller_command(lambda ctrl, key=control.key: ctrl.press(key))
            assert writes(co) == [bed.profile.writer_bytes("$" + control.letter)]
    for slot in range(1, bed.memory_slot_count + 1):
        co.client.write_gatt_char.reset_mock()
        await co.async_execute_controller_command(
            lambda ctrl, selected_slot=slot: ctrl.program_memory(selected_slot)
        )
        assert writes(co) == [bed.profile.writer_bytes("$" + "Za"[slot - 1])]


@pytest.mark.parametrize("row", WIDGETS, ids=lambda row: row["panel"] + row["va"])
async def test_each_frozen_widget_resolves_to_admitted_physical_controls(runtime, clock, row):
    _hass, co = runtime
    bed = await install(co, name(EXAMPLES[row["panel"]]))
    text = row["command_input"]
    if text is None:
        # Local selected-axis navigation has no BLE action; HA exposes each
        # physical axis directly instead of a second UI selection state.
        assert all(c.letter is not None for c in bed.profile.controls)
        return
    if text.startswith("selected physical"):
        letter = bed.profile.axes[0][2 if "down" in row["action"].lower() else 1]
    else:
        letter = text.rsplit("$", 1)[-1]
    control = next(c for c in bed.profile.controls if c.letter == letter)
    assert control.held is (row["held"] != "false")
    assert control.tap_up_write is (row["tap_up_write"] == "true")
    release = (
        "stop"
        if "send_stop" in row["release"]
        else "fallback"
        if "tail" in row["release"] and "no generic" not in row["release"]
        else "none"
    )
    assert control.release == release
    await co.async_execute_controller_command(
        lambda ctrl: (
            ctrl.hold_control("vivasleep_" + control.key, 100)
            if control.held
            else ctrl.press(control.key)
        )
    )
    assert bed.profile.writer_bytes("$" + letter) in writes(co)


@pytest.mark.parametrize(
    "row", [v for v in VECTORS if v["kind"] == "gesture"], ids=lambda r: r["id"]
)
async def test_frozen_gesture_windows_use_the_real_command_lane(runtime, clock, row):
    _hass, co = runtime
    inp = row["inputs"]
    await install(co, name("35" if not inp["held"] and not inp["tap_up_write"] else "15"))
    start = clock.time()
    emissions = []
    co.client.write_gatt_char.side_effect = lambda _char, data, **_kw: emissions.append(
        round((clock.time() - start) * 1000)
    )
    if not inp["held"]:
        if inp["tap_up_write"]:
            await asyncio.sleep(inp["release_ms"] / 1000)
        await co.async_execute_controller_command(
            lambda ctrl: ctrl.press("light_toggle" if inp["tap_up_write"] else "massage_head")
        )
    else:
        key = "memory_1" if inp.get("custom_up") else "preset_flat"
        if inp.get("cancelled"):
            task = asyncio.create_task(
                co.async_execute_controller_command(
                    lambda ctrl: ctrl.hold_control("vivasleep_" + key, 1000)
                )
            )
            await asyncio.sleep(inp["release_ms"] / 1000)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        else:
            await co.async_execute_controller_command(
                lambda ctrl: ctrl.hold_control("vivasleep_" + key, inp["release_ms"])
            )
    assert emissions == row["expected"]


@pytest.mark.parametrize("wrapped", (False, True))
async def test_native_rgb_timer_alarm_and_confirmed_coupling(runtime, clock, wrapped):
    hass, co = runtime
    await install(co, name("15", mode="M" if wrapped else "E"))
    emissions = []
    start = clock.time()
    co.client.write_gatt_char.side_effect = lambda _char, data, **kw: emissions.append(
        (round((clock.time() - start) * 1000), bytes(data), kw["response"])
    )
    await co.async_execute_controller_command(lambda ctrl: ctrl.set_light_color((255, 128, 0)))
    assert [t for t, data, _response in emissions if data.startswith(b"$#003")] == (
        [0, 100, 200] if wrapped else [100, 300, 500]
    )
    assert not any(response for _t, _data, response in emissions)
    assert clock.time() - start == pytest.approx(0.3 if wrapped else 0.6)
    co.client.write_gatt_char.reset_mock()
    await co.async_execute_controller_command(lambda ctrl: ctrl.set_light_timer("90 min"))
    assert writes(co) == ([] if wrapped else [b"$z"]) + [b"$#003190009000002R\r"]
    if not wrapped:
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {"device_id": ["bed"], "enabled": True, "time": "07:30:00", "massage_intensity": 2},
            blocking=True,
        )
        assert writes(co)[-1] == app.alarm_frame("07", "30", 2)
    with pytest.raises(ServiceValidationError):
        await co.async_execute_controller_command(lambda ctrl: ctrl.set_sync_mode("wired"))
    await co.async_execute_controller_command(
        lambda ctrl: ctrl.set_sync_mode("wired", confirmed=True)
    )
    assert writes(co)[-1] == b"$#330490000100012R\r"


async def test_fresh_readback_partial_parse_and_disconnect_fencing(runtime, clock):
    hass, co = runtime
    bed = await install(co, name(mode="E"))
    assert co.controller_state.get(UNDER_BED_LIGHTS_ON) is None
    tokens = ["0"] * 75
    for index, value in zip(
        (28, 29, 30, 54, 8, 9, 11), ("120", "45", "60", "90", "00008", "00009", "2"), strict=True
    ):
        tokens[index] = value
    notification(bed, tokens)
    assert co.controller_state[UNDER_BED_LIGHTS_RGB] == (255, 95, 127)
    assert co.controller_state[LIGHT_TIMER_OPTION] == "90 min"
    await hass.services.async_call(
        const.DOMAIN, "set_alarm", {"device_id": ["bed"], "enabled": False}, blocking=True
    )
    assert writes(co)[-1] == app.alarm_frame("00008", "00009", 0)
    tokens = ["0"] * 39
    tokens[24], tokens[27] = "1", "00066"
    notification(bed, tokens)
    assert co.controller_state[SYNC_ENABLED] is False
    assert co.controller_state[SYNC_MODE] == "wired"
    await co.async_execute_controller_command(lambda ctrl: ctrl.set_sync(True))
    assert writes(co)[-1] == b"$#000120000000003R\r"
    tokens[24], tokens[27] = "", "00065"
    notification(bed, tokens)
    assert co.controller_state[SYNC_ENABLED] is True
    assert bed.protocol_diagnostics["sync_type"] == 1
    callback = co.client.start_notify.await_args.args[1]
    old = co.client
    await bed.stop_notify()
    co._client = bedgear.client()
    await bed.start_notify()
    callback(old.services[0].characteristics[0], bytearray(b"$123R\r"))
    assert co.controller_state.get(UNDER_BED_LIGHTS_ON) is None
    assert bed._receiver.buffer == b""


async def test_link_replacement_drops_delayed_channels_and_subscription_failure_blocks(
    runtime, clock
):
    _hass, co = runtime
    bed = await install(co, name(mode="M"))
    old = co.client
    task = asyncio.create_task(
        co.async_execute_controller_command(lambda ctrl: ctrl.set_light_color((255, 255, 255)))
    )
    await asyncio.sleep(0.05)
    co._client = bedgear.client()
    with pytest.raises(ConnectionError):
        await task
    assert old.write_gatt_char.await_count == 1
    co.client.write_gatt_char.assert_not_awaited()
    co.client.start_notify = AsyncMock(side_effect=RuntimeError("subscription failed"))
    with pytest.raises(RuntimeError, match="subscription failed"):
        await bed.start_notify()
    with pytest.raises(ConnectionError):
        await bed.press("head_up")


async def test_stale_entities_and_profile_mismatch_fail_before_writing(runtime):
    _hass, co = runtime
    bed = await install(co, name("50", light="B"))
    for action in (
        lambda: bed.press("foot_up"),
        lambda: bed.program_memory(1),
        lambda: bed.set_light_color((255, 0, 0)),
    ):
        with pytest.raises(ServiceValidationError):
            await action()
    co.client.write_gatt_char.assert_not_awaited()
    with pytest.raises(type(setup_stopped("vivasleep_name_mismatch"))):
        await create_controller(
            co, const.BED_TYPE_VIVASLEEP, None, co.client, advertisement_local_name=name("00")
        )


async def test_public_hold_service_and_native_early_release_stop_fences_tail(runtime, clock):
    hass, co = runtime
    bed = await install(co, name("00"))
    await hass.services.async_call(
        const.DOMAIN,
        "hold_control",
        {"device_id": ["bed"], "control": "vivasleep_head_up", "duration": 0.25},
        blocking=True,
    )
    assert writes(co) == [b"$K"] * 2 + [b"$b"] * 5
    co.client.write_gatt_char.reset_mock()
    first = asyncio.Event()

    async def write(_char, data, **_kwargs):
        if bytes(data) == b"$Q":
            first.set()

    co.client.write_gatt_char.side_effect = write
    hold = asyncio.create_task(
        co.async_execute_controller_command(
            lambda ctrl: ctrl.hold_control("vivasleep_tilt_down", 1000)
        )
    )
    await asyncio.sleep(0.02)
    spec = next(s for s in bed.controller_button_specs if s.release_only)
    release = asyncio.create_task(ControllerActionButton(co, spec).async_press())
    await first.wait()
    await co.async_stop_command()
    await hold
    await release
    assert writes(co) == [b"$Q"] + [b"$b"] * 5


@pytest.mark.parametrize("after_channel", (1, 2))
async def test_native_light_does_not_publish_a_partial_rgb_command(runtime, clock, after_channel):
    hass, co = runtime
    bed = await install(co, name(mode="M"))
    light = AdjustableBedLight(co, LIGHT_DESCRIPTION)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    count = 0

    async def write(_char, data, **_kwargs):
        nonlocal count
        count += 1
        if count == after_channel:
            co.cancel_command.set()

    co.client.write_gatt_char.side_effect = write
    await light.async_turn_on(rgb_color=(255, 255, 255), brightness=128)
    assert len(writes(co)) == after_channel
    assert co.controller_state[UNDER_BED_LIGHTS_ON] is None
    assert co.controller_state[UNDER_BED_LIGHTS_RGB] is None
    assert bed.current_light_rgb_color is None


async def test_stop_and_disconnect_clear_cache_without_a_reconnect_query(runtime, clock):
    _hass, co = runtime
    bed = await install(co, name(mode="E"))
    tokens = ["0"] * 39
    tokens[24], tokens[27] = "1", "00065"
    notification(bed, tokens)
    assert co.controller_state[SYNC_ENABLED] is True
    bed.on_disconnect()
    assert co.controller_state[SYNC_ENABLED] is None
    assert co.controller_state[SYNC_MODE] is None
    assert co.controller_state[UNDER_BED_LIGHTS_ON] is None
    await bed.start_notify()
    assert not writes(co)
    with pytest.raises(ServiceValidationError):
        await co.async_execute_controller_command(lambda ctrl: ctrl.set_sync(False))


async def test_native_rgb_off_preserves_the_last_on_color(runtime, clock):
    hass, co = runtime
    bed = await install(co, name(mode="M"))
    light = AdjustableBedLight(co, LIGHT_DESCRIPTION)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    light.async_get_last_state = AsyncMock(return_value=None)
    await light.async_added_to_hass()
    await light.async_turn_on(rgb_color=(255, 0, 0), brightness=128)
    first_frames = writes(co).copy()
    assert light.rgb_color == (255, 0, 0)
    assert light.brightness == 128
    await light.async_turn_off()
    # Real subscribed feedback must also preserve the requested hue/level.
    tokens = ["0"] * 39
    tokens[27] = "00066"
    notification(bed, tokens)
    assert light.is_on is False
    assert light.rgb_color == (255, 0, 0)
    assert light.brightness == 128
    assert bed.current_light_rgb_color == (255, 0, 0)
    co.client.write_gatt_char.reset_mock()
    await light.async_turn_on()
    assert light.is_on is True
    assert writes(co) == first_frames
    assert writes(co)[0] == bed.profile.writer_bytes("$#003150006000001R\r")
    await light.async_will_remove_from_hass()


async def test_queued_sync_rechecks_live_binding_before_gatt_dispatch(runtime):
    _hass, co = runtime
    bed = await install(co, name())
    tokens = ["0"] * 39
    tokens[27] = "00066"
    notification(bed, tokens)
    entered = asyncio.Event()

    async def change(ctrl):
        entered.set()
        await ctrl.set_sync(True)

    async with bed.ble_lock:
        task = asyncio.create_task(co.async_execute_controller_command(change))
        await entered.wait()
        await asyncio.sleep(0)
        tokens[27] = "0"
        notification(bed, tokens)
    with pytest.raises(ServiceValidationError) as error:
        await task
    assert error.value.translation_key == "vivasleep_sync_unavailable"
    assert not writes(co)


@pytest.mark.parametrize("control, expected", (("tilt_down", []), ("head_up", [b"$b"] * 5)))
async def test_public_cancel_hold_before_first_tick(
    runtime, enable_custom_integrations, control, expected
):
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.entity_platform import async_get_platforms

    hass, co = runtime
    bed = await install(co, name("00"))
    co.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.config.components.add(const.DOMAIN)
    await hass.config_entries.async_forward_entry_setups(co.entry, ["button"])

    await hass.async_block_till_done()

    spec = next(s for s in bed.controller_button_specs if s.release_only)
    entity_id = er.async_get(hass).async_get_entity_id(
        "button", const.DOMAIN, co.entity_unique_id(spec.key)
    )
    assert entity_id
    with bedgear.virtual_clock() as fake, patch.object(bedgear.module, "monotonic", fake.time):
        hold = asyncio.create_task(
            hass.services.async_call(
                const.DOMAIN,
                "hold_control",
                {"device_id": ["bed"], "control": "vivasleep_" + control, "duration": 1},
                blocking=True,
            )
        )
        await asyncio.sleep(0.02)

        await hass.services.async_call(
            const.DOMAIN, "cancel_hold", {"entity_id": entity_id}, blocking=True
        )
        await hold

        assert writes(co) == expected
    for platform in list(async_get_platforms(hass, const.DOMAIN)):
        await platform.async_reset()


@pytest.mark.parametrize("mode, value", (("wireless", 0), ("wired", 1)))
async def test_sync_mode_requires_explicit_public_confirmation(
    runtime, enable_custom_integrations, mode, value
):
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.entity_platform import async_get_platforms

    hass, co = runtime
    bed = await install(co, name())
    spec = next(s for s in bed.controller_button_specs if s.key == "vivasleep_sync_" + mode)
    er.async_get(hass).async_get_or_create(
        "button",
        const.DOMAIN,
        co.entity_unique_id(spec.key),
        config_entry=co.entry,
        disabled_by=None,
    )
    co.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.config.components.add(const.DOMAIN)
    await hass.config_entries.async_forward_entry_setups(co.entry, ["button"])
    await hass.async_block_till_done()
    spec = next(s for s in bed.controller_button_specs if s.key == "vivasleep_sync_" + mode)
    entity_id = er.async_get(hass).async_get_entity_id(
        "button", const.DOMAIN, co.entity_unique_id(spec.key)
    )
    assert entity_id
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
    import voluptuous as vol

    for acknowledgment in ({}, {"confirmed": False}):
        with pytest.raises(vol.Invalid):
            await hass.services.async_call(
                const.DOMAIN,
                "press_confirmed",
                {"entity_id": entity_id, **acknowledgment},
                blocking=True,
            )
    stop_id = er.async_get(hass).async_get_entity_id(
        "button", const.DOMAIN, co.entity_unique_id("stop")
    )
    assert stop_id
    for service, data, key in (
        ("cancel_hold", {}, "held_cancel_unavailable"),
        ("press_confirmed", {"confirmed": True}, "button_confirmation_required"),
    ):
        with pytest.raises(ServiceValidationError) as error:
            await hass.services.async_call(
                const.DOMAIN, service, {"entity_id": stop_id, **data}, blocking=True
            )
        assert error.value.translation_key == key
    assert not writes(co)
    await hass.services.async_call(
        const.DOMAIN, "press_confirmed", {"entity_id": entity_id, "confirmed": True}, blocking=True
    )
    assert writes(co) == [b"$#330490000000013R\r" if value == 0 else b"$#330490000100012R\r"]
    for platform in list(async_get_platforms(hass, const.DOMAIN)):
        await platform.async_reset()


async def test_explicit_sync_directions_do_not_compare_stale_feedback(runtime):
    from custom_components.adjustable_bed.switch import AdjustableBedControllerSwitch

    hass, co = runtime
    bed = await install(co, name())
    tokens = ["0"] * 39
    tokens[27] = "00066"
    notification(bed, tokens)
    switch = AdjustableBedControllerSwitch(co, bed.controller_switch_specs[0])
    switch.hass = hass
    switch.async_write_ha_state = MagicMock()
    await switch.async_turn_on()
    await switch.async_turn_off()
    await switch.async_turn_off()
    assert writes(co) == [b"$#000120000000003R\r", b"$#000150000000004R\r", b"$#000150000000004R\r"]


@pytest.mark.parametrize("size, accepted", ((8192, True), (8193, False)))
def test_shared_receiver_bounds_final_fragment_before_parsing(size, accepted):
    from custom_components.adjustable_bed.beds.bedgear.protocol import Receiver

    receiver = Receiver()
    assert receiver.feed(b"$" + b"1" * 8190) == ()
    assert receiver.feed(b"2" * (size - 8190) + b"R\r") == (
        ("1" * 8190 + "2" * (size - 8190),) if accepted else ()
    )
    assert not receiver.buffer
    assert receiver.collecting is accepted


async def test_native_card_discovery_metadata_matches_ha(
    runtime, enable_custom_integrations, tmp_path
):
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.entity_platform import async_get_platforms

    hass, co = runtime
    await install(co, name("00"))
    co.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.config.components.add(const.DOMAIN)
    await hass.config_entries.async_forward_entry_setups(co.entry, ["button", "cover"])
    await hass.async_block_till_done()
    # With a real button platform loaded, the complete action census must match.
    described = yaml.safe_load(
        (FIXTURES.parents[2] / "custom_components" / "adjustable_bed" / "services.yaml").read_text()
    )
    assert set(hass.services.async_services()[const.DOMAIN]) == set(described)
    snapshot = {"entities": {}, "states": {}}
    for entry in er.async_entries_for_config_entry(er.async_get(hass), co.entry.entry_id):
        state = hass.states.get(entry.entity_id)
        if state is None:
            continue
        attributes = {
            key: value
            for key, value in state.attributes.items()
            if key.startswith(("hold_", "held_", "card_"))
        }
        if not attributes and entry.translation_key != "bedgear_release":
            continue
        snapshot["entities"][entry.entity_id] = {
            "entity_id": entry.entity_id,
            "platform": entry.platform,
            "translation_key": entry.translation_key,
            "device_id": "receiver",
        }
        snapshot["states"][entry.entity_id] = {
            "entity_id": entry.entity_id,
            "state": state.state,
            "attributes": attributes,
        }
    actual = tmp_path / "vivasleep-card-metadata.json"
    actual.write_text(json.dumps(snapshot, indent=2) + "\n")
    release = next(
        entry
        for entry in snapshot["entities"].values()
        if entry["translation_key"] == "bedgear_release"
    )
    declarations = [
        state["attributes"]["hold_release_button_key"]
        for state in snapshot["states"].values()
        if "hold_release_button_key" in state["attributes"]
    ]
    assert declarations and all(key == release["translation_key"] for key in declarations)
    for platform in list(async_get_platforms(hass, const.DOMAIN)):
        await platform.async_reset()
    assert snapshot == json.loads((FIXTURES / "card-metadata.json").read_text()), str(actual)


@pytest.mark.parametrize("rebuild", (False, True))
async def test_subscribed_light_selection_survives_reconnect_and_new_feedback(
    runtime, clock, rebuild
):
    hass, co = runtime
    selected_name = name(mode="M")
    bed = await install(co, selected_name)
    light = AdjustableBedLight(co, LIGHT_DESCRIPTION)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    light.async_get_last_state = AsyncMock(return_value=None)
    await light.async_added_to_hass()
    await light.async_turn_on(rgb_color=(255, 0, 0), brightness=128)
    red = writes(co).copy()
    await light.async_turn_off()
    bed.on_disconnect()
    assert co.controller_state[UNDER_BED_LIGHTS_ON] is None
    assert light.is_on is None
    if rebuild:
        bed = await create_controller(
            co, const.BED_TYPE_VIVASLEEP, "auto", co.client, advertisement_local_name=selected_name
        )
        co._controller = bed
    await bed.start_notify()
    assert bed.protocol_diagnostics["rgb"] is None
    co.client.write_gatt_char.reset_mock()
    await light.async_turn_on()
    assert writes(co) == red
    assert light.rgb_color == (255, 0, 0) and light.brightness == 128
    # Matching effective feedback must not apply brightness a second time.
    tokens = ["0"] * 39
    tokens[18:21] = ["60", "0", "0"]
    notification(bed, tokens)
    assert light.rgb_color == (255, 0, 0) and light.brightness == 128
    # A physical remote's changed nonblack output updates the subscribed entity.
    tokens[18:21] = ["0", "120", "0"]
    notification(bed, tokens)
    assert light.rgb_color == (0, 255, 0) and light.brightness == 255
    await light.async_turn_off()
    tokens[18:21] = ["0", "0", "0"]
    notification(bed, tokens)
    assert light.is_on is False and light.rgb_color == (0, 255, 0)
    co.client.write_gatt_char.reset_mock()
    await light.async_turn_on()
    assert writes(co) == [b"$#003150000000007R\r", b"$#003160012000007R\r", b"$#003170000000005R\r"]
    await light.async_will_remove_from_hass()


def test_shared_receiver_keeps_complete_record_when_suffix_overflows():
    from custom_components.adjustable_bed.beds.bedgear.protocol import Receiver

    receiver = Receiver()
    assert receiver.feed(b"$1") == ()
    assert receiver.feed(b"23R\r$" + b"7" * 8193) == ("123",)
    assert not receiver.buffer and not receiver.collecting
    assert receiver.feed(b"$4") == ()
    assert receiver.feed(b"56R\r") == ("456",)


async def test_light_selection_is_scoped_to_receiver_and_original_profile(runtime, clock):
    _hass, co = runtime
    bed = await install(co, name(mode="M"))
    await co.async_execute_controller_command(
        lambda ctrl: ctrl.set_light_color_with_level((255, 0, 0), 128)
    )
    with patch.object(co, "_address", "AA:BB:CC:DD:EE:13"):
        other = VivaSleepController(co, profile=bed.profile)
    assert other.current_light_rgb_color is None
    assert bed.current_light_rgb_color == (255, 0, 0)
    another_profile = VivaSleepController(co, profile=app.VivaSleepProfile(name("13", mode="M")))
    assert another_profile.current_light_rgb_color is None
    returned = VivaSleepController(co, profile=bed.profile)
    assert returned.current_light_rgb_color is None
