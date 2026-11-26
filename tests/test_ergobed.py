"""Verified ErgoBed wire frames, selector gates and live Home Assistant paths."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS, STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import State
from homeassistant.exceptions import ConfigEntryError, ServiceValidationError
from homeassistant.helpers.entity_component import EntityComponent

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.bedgear.controller import ALARM, STRENGTH
from custom_components.adjustable_bed.beds.bedgear.ergobed import LIGHT_TIMER, ErgoBedController
from custom_components.adjustable_bed.beds.bedgear.protocol import ErgoBedReceiver, token_fields
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.codec import motomotion
from custom_components.adjustable_bed.config_flow import _confident_auto_detect
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight
from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
from custom_components.adjustable_bed.pairing import side_owned_profile_fields
from custom_components.adjustable_bed.profiles.ergobed import (
    COLOR_COMMANDS,
    ErgoBedProfile,
    alarm_frame,
    clock_frame,
    color_frame,
    timer_frame,
)
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from tests import test_bedgear as bedgear
from tests import test_moodbase as moodbase
from tests.form_helpers import answer_app, select_options, suggested
from tests.test_bedgear import name, writes
from tests.test_detection import _make_service_info

clock = bedgear.clock
runtime = bedgear.runtime
CASES = json.loads((Path(__file__).parent / "fixtures/ergobed.json").read_text())


@pytest.mark.parametrize("vector", CASES["wire"], ids=lambda vector: vector["id"])
def test_frozen_wire(vector):
    fields = vector["inputs"]
    match vector["builder"]:
        case "wire":
            frame = motomotion.short_transport(fields["text"], wrapped=False)
        case "clock":
            frame = clock_frame(datetime(2026, 1, 1, **fields))
        case "rgb_channel":
            index = ("red", "green", "blue").index(fields["channel"])
            frame = color_frame(COLOR_COMMANDS[index], fields["value"])
        case "light_timer":
            frame = timer_frame(**fields)
        case "alarm":
            frame = alarm_frame(**fields)
        case _:
            pytest.fail(f"Unexpected frame: {vector['id']}")
    assert frame == bytes.fromhex(vector["expected_bytes"])


@pytest.mark.parametrize("case", CASES["notifications"], ids=lambda case: case["id"])
def test_frozen_status(case):
    receiver = ErgoBedReceiver()
    texts = [text for chunk in case["chunks_ascii"] for text in receiver.feed(chunk.encode())]
    expected = case["expected_cache"]
    if expected is None:
        assert not texts
    else:
        (text,) = texts
        fields = token_fields(text, alarm_indices=ErgoBedProfile.alarm_indices)
        assert fields == {
            "rgb_timer": [*expected["rgb"], expected["light_timer"]],
            "alarm": expected["alarm"],
        }


@pytest.mark.parametrize(
    ("pair", "panel", "axes", "presets", "slots", "massage"),
    [
        ("01", "PanelZero", "head:KL foot:MN combined:pq tilt:PQ", "O", 2, "GHJEFI"),
        ("11", "PanelOne", "head:KL", "O", 0, ""),
        ("12", "PanelOne", "head:KL foot:MN", "O", 0, ""),
        ("19", "PanelOne", "neck:PQ head:KL foot:MN", "O", 0, ""),
        ("15", "PanelA", "head:KL foot:MN lumbar:PQ", "ORST", 2, ""),
        ("21", "PanelTwo", "head:KL", "O", 2, "CBD"),
        ("23", "PanelTwo", "neck:PQ head:KL foot:MN", "O", 2, "CBD"),
        ("29", "PanelTwo", "head:KL foot:MN", "O", 2, "CBD"),
        ("25", "PanelFour", "head:KL lumbar:PQ foot:MN", "ORST", 2, "CBD"),
        ("31", "PanelThree", "head:KL", "ORST", 2, ""),
        ("33", "PanelThree", "neck:PQ head:KL foot:MN", "ORST", 2, ""),
        ("34", "PanelThree", "head:KL foot:MN", "ORST", 2, ""),
        ("35", "PanelD", "head:KL foot:MN neck:PQ", "O", 2, "CBD"),
        ("41", "PanelFour", "head:KL", "ORST", 2, "CBD"),
        ("43", "PanelFour", "neck:PQ head:KL foot:MN", "ORST", 2, "CBD"),
        ("44", "PanelFour", "neck:PQ head:KL lumbar:pq foot:MN", "ORST", 2, "CBD"),
        ("45", "PanelD", "head:KL foot:MN lumbar:PQ", "O", 2, "CBD"),
        ("46", "PanelFour", "head:KL foot:MN", "ORST", 2, "CBD"),
        ("51", "PanelFive", "head:KL", "O", 0, ""),
        ("55", "PanelFour", "neck:PQ head:KL foot:MN tilt:pq", "ORST", 2, "CBD"),
        ("61", "PanelSix", "head:KL foot:MN", "O", 0, ""),
        ("65", "PanelThree", "head:KL lumbar:PQ foot:MN", "ORST", 2, ""),
        ("71", "PanelSeven", "head:KL foot:MN", "O", 2, "CBD"),
        ("75", "PanelThree", "neck:PQ head:KL lumbar:pq foot:MN", "ORST", 2, ""),
        ("81", "PanelEight", "head:KL foot:MN", "ORST", 2, ""),
        ("85", "PanelD", "head:KL foot:MN tilt:PQ", "O", 2, "CBD"),
        ("91", "PanelNine", "head:KL foot:MN", "O", 0, ""),
        ("95", "WR1140", "head:KL foot:MN tilt:PQ", "ORST", 2, "CBD"),
        ("96", "WR1140", "head:KL foot:MN", "ORST", 2, "CBD"),
        ("97", "WR1140", "neck:PQ head:KL lumbar:pq foot:MN", "ORST", 2, "CBD"),
        ("98", "WR1140", "head:KL lumbar:pq foot:MN", "ORST", 2, "CBD"),
        ("A1", "PanelA", "head:KL foot:MN lumbar:PQ", "ORST", 2, ""),
        ("B1", "PanelFour", "head:KL foot:MN", "ORST", 2, "CBD"),
        ("C1", "PanelD", "head:KL foot:MN neck:PQ", "O", 2, "CBD"),
        ("D1", "PanelSixZG", "head:KL foot:MN", "T", 0, ""),
    ],
)
def test_selector_and_control_gates(pair, panel, axes, presets, slots, massage):
    profile = ErgoBedProfile(name(pair, mode="M", flag="H"))
    assert profile.panel == panel
    assert [f"{axis}:{up}{down}" for axis, up, down in profile.axes] == axes.split()
    assert "".join(letter for _, letter in profile.presets) == presets
    assert profile.memory_slots == slots and profile.light is bool(slots)
    controls = profile.controls
    massage_controls = [control for control in controls if control.key.startswith("massage_")]
    assert "".join(control.letter for control in massage_controls) == massage
    assert all(control.held == (panel == "PanelZero") for control in massage_controls)
    assert all(control.release == "none" for control in controls)
    assert profile.rgb and profile.timer and not profile.wrapped and not profile.sync


@pytest.mark.parametrize(
    ("advertised", "candidate"),
    [
        ("😀12HHC7A1DE0X", True),
        ("0123HHC7A1DE0X", True),
        ("0123HHC7E1DE0X", False),
        ("0123hhc7A1DE0X", False),
        ("😀0123HHC7A1DE0X", False),
        (None, False),
    ],
)
def test_discovery_uses_raw_name_and_only_offers_an_app(advertised, candidate):
    service_info = _make_service_info(name=name())
    service_info.raw = None
    service_info.advertisement = SimpleNamespace(local_name=advertised, platform_data=("scan",))
    result = detect_bed_type_detailed(service_info)
    assert (const.BED_TYPE_ERGOBED in (result.ambiguous_types or ())) is candidate
    assert _confident_auto_detect(result) != const.BED_TYPE_ERGOBED
    service_info.advertisement.platform_data = ()
    cached = detect_bed_type_detailed(service_info)
    assert const.BED_TYPE_ERGOBED not in (cached.ambiguous_types or ())


@pytest.mark.parametrize("source", (SOURCE_USER, SOURCE_BLUETOOTH))
@pytest.mark.parametrize(
    ("cached_name", "services"),
    (
        ("Generic BLE Receiver", []),
        ("AA:BB:CC:DD:EE:FF", ["0000ffe0-0000-1000-8000-00805f9b34fb"]),
    ),
)
async def test_raw_name_with_cached_display_name_requires_app_choice(
    hass, enable_custom_integrations, source, cached_name, services
):
    raw_name = "0123HHC7A1DE0X"
    info = _make_service_info(name=cached_name, service_uuids=services)
    info.raw = None
    info.advertisement = SimpleNamespace(local_name=raw_name, platform_data=("scan",))
    info.service_data = {}
    info.connectable = True
    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
        return_value=[info],
    ):
        flow = await hass.config_entries.flow.async_init(
            const.DOMAIN,
            context={"source": source},
            data=info if source == SOURCE_BLUETOOTH else None,
        )
        if source == SOURCE_USER:
            assert info.address in select_options(flow, CONF_ADDRESS)
            flow = await hass.config_entries.flow.async_configure(
                flow["flow_id"], {CONF_ADDRESS: info.address}
            )
        assert flow["step_id"] == "bluetooth_disambiguate"
        assert set(select_options(flow, "bed_type_choice")) == {const.BED_TYPE_ERGOBED, "show_all"}
        flow = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"bed_type_choice": const.BED_TYPE_ERGOBED}
        )
        assert flow["step_id"] == "bluetooth_confirm"
        flow = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {const.CONF_BED_TYPE: const.BED_TYPE_ERGOBED}
        )
    assert flow["step_id"] == "profile_questions"
    assert suggested(flow, const.CONF_BLE_DEVICE_NAME) == raw_name


async def test_manual_setup_rejects_unsupported_selector(hass, enable_custom_integrations):
    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info", return_value=[]
    ):
        flow = await hass.config_entries.flow.async_init(const.DOMAIN, context={"source": "user"})
        flow = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {CONF_ADDRESS: "manual"}
        )
        flow = await answer_app(hass, flow, const.BED_TYPE_ERGOBED)
        flow = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {CONF_ADDRESS: "AA:BB:CC:DD:EE:12"}
        )
    assert flow["step_id"] == "profile_questions"
    invalid = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {const.CONF_BLE_DEVICE_NAME: name("E1")}
    )
    assert invalid["errors"] == {const.CONF_BLE_DEVICE_NAME: "ergobed_profile"}
    valid = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {const.CONF_BLE_DEVICE_NAME: name("D1")}
    )
    assert valid["step_id"] == "finish_settings"
    assert const.CONF_BLE_DEVICE_NAME in side_owned_profile_fields(
        {const.CONF_BED_TYPE: const.BED_TYPE_ERGOBED}
    )


async def install(co, selected):
    await co.controller.stop_notify()
    co.client.services[0].characteristics[0].properties = ["notify", "write-without-response"]
    co.hass.config_entries.async_update_entry(
        co.entry, data={**co.entry.data, const.CONF_BLE_DEVICE_NAME: selected}
    )
    bed = await create_controller(co, const.BED_TYPE_ERGOBED, None, co.client)
    assert isinstance(bed, ErgoBedController)
    co._controller = bed
    await bed.start_notify()
    co.client.write_gatt_char.reset_mock()
    return bed


async def test_native_hold_release_save_and_massage_stop(runtime, clock):
    hass, co = runtime
    bed = await install(co, name("71", mode="M"))
    trace = []
    started = clock.time()
    co.client.write_gatt_char.side_effect = lambda _, data, **kw: trace.append(
        (round((clock.time() - started) * 1000), bytes(data), kw["response"])
    )
    assert bed.execution.hold_for("ergobed_head_up") == "stream"
    await hass.services.async_call(
        const.DOMAIN,
        "hold_control",
        {"device_id": ["bed"], "control": "ergobed_head_up", "duration": 0.25},
        blocking=True,
    )
    assert trace == [(100, b"$K", False), (200, b"$K", False)]
    # The held control uses the profile axis name "foot", independently of its cover label.
    with pytest.raises(ValueError, match="Choose a control"):
        bed.validate_hold_control("ergobed_feet_up", 700)
    task = asyncio.create_task(
        co.async_execute_controller_command(lambda ctrl: ctrl.hold_control("ergobed_foot_up", 700))
    )
    await asyncio.sleep(0.15)
    await co.async_stop_command()
    await task
    await co.async_execute_controller_command(lambda ctrl: ctrl.program_memory(2))
    await co.async_execute_controller_command(lambda ctrl: ctrl.recall_memory(2, hold_ms=150))
    massage_stop = next(
        spec for spec in bed.controller_button_specs if spec.key == "ergobed_massage_stop"
    )
    await ControllerActionButton(co, massage_stop).async_press()
    assert writes(co) == [b"$K", b"$K", b"$M", b"$a", b"$V", b"$D"]


async def test_settings_and_startup_use_current_link(runtime, clock):
    hass, co = runtime
    bed = await install(co, name(mode="E"))
    trace = []
    started = clock.time()
    co.client.write_gatt_char.side_effect = lambda _, data, **kw: trace.append(
        (round((clock.time() - started) * 1000), bytes(data), kw["response"])
    )
    session = SimpleNamespace(hass=hass, is_current=lambda: co.controller is bed)
    with patch(
        "custom_components.adjustable_bed.beds.bedgear.ergobed.dt_util.now",
        return_value=datetime(2026, 1, 1, 9, 7, 5),
    ):
        await bed.async_after_connect(session)
        task = bed._startup_task
        assert task is not None and not trace
        await task
    assert trace == [(500, b"$z", False), (500, b"$#975110000011A\r", False)]

    started = clock.time()
    trace.clear()
    await co.async_execute_controller_command(lambda ctrl: ctrl.set_light_color((255, 128, 0)))
    assert trace == [
        (0, b"$z", False),
        (50, b"$#003150012000004R\r", False),
        (100, b"$z", False),
        (150, b"$#003160006000002R\r", False),
        (200, b"$z", False),
        (250, b"$#003170000000005R\r", False),
    ]
    number = AdjustableBedControllerNumber(co, bed.controller_number_specs[0])
    await number.async_set_native_value(120)
    await hass.services.async_call(
        const.DOMAIN,
        "set_alarm",
        {"device_id": ["bed"], "enabled": False, "time": "07:30:00"},
        blocking=True,
    )
    assert writes(co)[-4:] == [b"$z", b"$#003190012000008R\r", b"$z", b"$#001707300000002R\r"]
    assert timer_frame(119.5) == timer_frame(120)

    await bed.async_after_connect(session)
    task = bed._startup_task
    await install(co, name("51", light="B"))
    assert task is not None
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not writes(co)
    assert not co.controller.supports_light_color_control and co.controller.alarm_capability is None
    await co.controller.async_after_connect(session)
    assert co.controller._startup_task is None


def status_sender(co, bed):
    link = bed._current()
    receive = co.client.start_notify.await_args.args[1]

    def send(count=75, *, start=False, rgb=("120", "60", "0"), timer="600", hour="07", minute="30"):
        tokens = ["0"] * count
        tokens[8:12] = [hour, minute, "0", "2"]
        tokens[28:31] = rgb
        tokens[54] = timer
        body = " ".join(tokens).encode()
        if start:
            receive(link.write, bytearray(b"$" + body))
            receive(link.write, bytearray(b"\r"))
        else:
            receive(link.write, bytearray(body + b"\r"))

    return send


async def test_rejected_records_and_stale_callbacks_preserve_state(runtime):
    _hass, co = runtime
    bed = await install(co, name(mode="E"))
    status = status_sender(co, bed)
    status(start=True)
    state = co.controller_state.copy()
    assert state.get(LIGHT_TIMER) == 540
    assert state.get(ALARM) == "07:30" and state.get(STRENGTH) == 2
    assert state.get(UNDER_BED_LIGHTS_RGB) == (255, 127, 0)
    assert state.get(UNDER_BED_LIGHTS_ON) is True
    status(timer="90", hour="08")
    state = co.controller_state.copy()
    assert state.get(LIGHT_TIMER) == 90
    assert state.get(ALARM) == "08:30"
    for count in (55, 74, 76):
        status(count, timer="5", hour="09")
        assert co.controller_state == state
    await install(co, name("51"))
    status(start=True)
    assert co.controller_state.get(LIGHT_TIMER) is None
    assert co.controller_state.get(ALARM) is None


async def test_alarm_off_keeps_observed_time_or_requires_explicit_time(runtime, clock):
    hass, co = runtime
    bed = await install(co, name(mode="E"))

    async def turn_off(**fields):
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {"device_id": ["bed"], "enabled": False, **fields},
            blocking=True,
        )

    with pytest.raises(ServiceValidationError) as missing:
        await turn_off()
    assert missing.value.translation_key == "alarm_time_required_to_turn_off"
    assert not writes(co)

    status = status_sender(co, bed)
    status(start=True)
    await turn_off()
    await turn_off(time="00:00:00")
    assert writes(co) == [b"$z", b"$#001707300000002R\r", b"$z", b"$#001700000000006R\r"]
    status(hour="bad")
    co.client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError) as invalid_time:
        await turn_off()
    assert invalid_time.value.translation_key == "alarm_time_required_to_turn_off"
    assert not writes(co)


@pytest.mark.parametrize("reported_power_only", (True, False))
async def test_light_entity_keeps_unknown_power_only_for_ergobed(runtime, reported_power_only):
    hass, co = runtime
    if reported_power_only:
        bed = await install(co, name())
    else:
        bed = await moodbase.install(co, name(mode="M"))
    lamp = AdjustableBedLight(co, LIGHT_DESCRIPTION)
    if reported_power_only:
        lamp.async_get_last_state = AsyncMock(return_value=State("light.bed", STATE_ON))
    component = EntityComponent(logging.getLogger(__name__), "light", hass)
    await component.async_add_entities([lamp])
    assert hass.states.get(lamp.entity_id).state == (
        STATE_UNKNOWN if reported_power_only else STATE_OFF
    )

    if reported_power_only:
        status = status_sender(co, bed)
        status(start=True)
        assert hass.states.get(lamp.entity_id).state == STATE_ON
        status(rgb=("bad", "60", "0"))
        assert hass.states.get(lamp.entity_id).state == STATE_UNKNOWN
        with pytest.raises(ServiceValidationError) as error:
            await lamp.async_toggle()
        assert error.value.translation_key == "light_toggle_state_unknown"
        assert not writes(co)
        status(rgb=("0", "0", "0"))
    else:
        co.handle_controller_state_updates(UNDER_BED_LIGHTS_ON(True))
        assert hass.states.get(lamp.entity_id).state == STATE_ON
        co.handle_controller_state_updates(UNDER_BED_LIGHTS_ON(None))
    assert hass.states.get(lamp.entity_id).state == STATE_OFF


async def test_lost_link_cannot_send_remaining_settings(runtime, clock):
    _hass, co = runtime
    bed = await install(co, name())
    sent = asyncio.Event()
    client = co.client
    client.write_gatt_char.side_effect = lambda *args, **kwargs: sent.set()
    task = asyncio.create_task(bed.set_light_color((255, 128, 0)))
    await sent.wait()
    await install(co, name())
    with pytest.raises(ConnectionError):
        await task
    client.write_gatt_char.assert_not_awaited()


async def test_transport_requires_one_duplex_characteristic(runtime):
    _hass, co = runtime
    bed = await install(co, name())
    assert bed._current().notify == (bed._current().write,)
    await bed.stop_notify()
    co.client.services[0].characteristics[0].properties = ["notify"]
    with pytest.raises(BedNotConnectedError):
        await bed.start_notify()
    co.client.start_notify = AsyncMock(side_effect=RuntimeError("Subscription failed"))
    co.client.services[0].characteristics[0].properties.append("write-without-response")
    with pytest.raises(RuntimeError, match="Subscription failed"):
        await bed.start_notify()
    with pytest.raises(ConnectionError):
        await bed.press("light_toggle")
    assert not writes(co)


async def test_live_name_mismatch_never_switches_the_saved_layout(runtime):
    _hass, co = runtime
    await install(co, name("01"))
    with pytest.raises(ConfigEntryError) as exc:
        await create_controller(
            co, const.BED_TYPE_ERGOBED, None, co.client, advertisement_local_name=name("97")
        )
    assert exc.value.translation_key == "ergobed_name_mismatch"
    assert not writes(co)
