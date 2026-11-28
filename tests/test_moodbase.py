"""MoodBase layout selection and BLE commands through Home Assistant."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.bedgear.controller import ALARM, TIMER
from custom_components.adjustable_bed.beds.bedgear.moodbase import (
    SYNC_ENABLED,
    SYNC_MODE,
    VIBRATION_LEVEL,
    MoodBaseController,
)
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.command_scheduler import CommandOutcome, Delivery, delivered
from custom_components.adjustable_bed.config_flow import _confident_auto_detect
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight
from custom_components.adjustable_bed.pairing import side_owned_profile_fields
from custom_components.adjustable_bed.profile_recommendations import recommend_profile
from custom_components.adjustable_bed.profiles.moodbase import CARRIER_SERVICE_UUID, MoodBaseProfile
from custom_components.adjustable_bed.state_keys import (
    LIGHT_LEVEL,
    UNDER_BED_LIGHTS_ON,
    UNDER_BED_LIGHTS_RGB,
)
from tests import test_bedgear as bedgear
from tests.entry_entities import async_add_entry_entities
from tests.form_helpers import answer_app
from tests.test_bedgear import name, notification, writes

runtime = bedgear.runtime
clock = bedgear.clock


async def install(co, selected):
    await co.controller.stop_notify()
    co.client.services[0].characteristics[0].properties = ["notify", "write-without-response"]
    co.hass.config_entries.async_update_entry(
        co.entry, data={**co.entry.data, const.CONF_BLE_DEVICE_NAME: selected}
    )
    bed = await create_controller(co, const.BED_TYPE_MOODBASE, None, co.client)
    assert isinstance(bed, MoodBaseController)
    co._controller = bed
    await bed.start_notify()
    co.client.write_gatt_char.reset_mock()
    return bed


@pytest.mark.parametrize(
    "selector,layout,axes,presets,slots,massage",
    [
        ("15", "PanelA", "head:KL foot:MN lumbar:PQ", "ORST", 2, ""),
        ("35", "PanelD", "head:KL foot:MN neck:PQ", "O", 2, "CBD"),
        ("E1", "PanelE", "head:KL", "OR", 0, ""),
        ("81", "PanelEight", "head:KL foot:MN", "ORST", 2, ""),
        ("51", "PanelFive", "head:KL", "O", 0, ""),
        ("44", "PanelFour", "neck:PQ head:KL lumbar:pq foot:MN", "ORST", 2, "CBD"),
        ("91", "PanelNine", "head:KL foot:MN", "O", 0, ""),
        ("14", "PanelOne", "neck:PQ head:KL foot:MN", "O", 0, ""),
        ("71", "PanelSeven", "head:KL foot:MN", "O", 2, "CBD"),
        ("61", "PanelSix", "head:KL foot:MN", "O", 0, ""),
        ("D1", "PanelSixZG", "head:KL foot:MN", "T", 0, ""),
        ("34", "PanelThree", "neck:PQ head:KL lumbar:pq foot:MN", "ORST", 2, ""),
        ("23", "PanelTwo", "neck:PQ head:KL foot:MN", "O", 2, "CBD"),
        ("01", "PanelZero", "head:KL foot:MN combined:pq tilt:PQ", "O", 2, "GHJEFI"),
        ("97", "WR1140", "neck:PQ head:KL lumbar:pq foot:MN", "ORST", 2, "CBD"),
    ],
)
def test_layout(selector, layout, axes, presets, slots, massage):
    profile = MoodBaseProfile(name(selector))
    assert profile.panel == layout
    assert [f"{axis}:{up}{down}" for axis, up, down in profile.axes] == axes.split()
    assert "".join(cmd for _, cmd in profile.presets) == presets
    assert profile.memory_slots == slots
    assert [c.letter for c in profile.controls if c.key.startswith("massage_")] == list(massage)
    assert all(not c.held for c in profile.controls if c.key.startswith("massage_"))


@pytest.mark.parametrize(
    ("selector", "flag", "axis", "letters"),
    [
        ("15", "H", "lumbar", "pq"),
        ("35", "H", "neck", "pq"),
        ("C1", "H", "neck", "pq"),
        ("45", "H", "lumbar", "pq"),
        ("85", "H", "tilt", "pq"),
        ("25", "X", "lumbar", "PQ"),
        ("65", "X", "lumbar", "PQ"),
        ("55", "X", "tilt", "pq"),
        ("95", "X", "tilt", "PQ"),
        ("98", "X", "lumbar", "pq"),
    ],
)
def test_extra_axis(selector, flag, axis, letters):
    assert (axis, *letters) in MoodBaseProfile(name(selector, flag=flag)).axes


@pytest.mark.parametrize(
    "light,mode,flag,capabilities",
    [
        ("D", "M", "H", (True, True, False, False, False)),
        ("C", "M", "X", (False, True, False, False, True)),
        ("B", "M", "X", (False, True, True, False, True)),
        ("D", "E", "X", (False, False, False, True, True)),
        ("B", "0", "0", (False, False, True, False, False)),
    ],
)
def test_independent_flags(light, mode, flag, capabilities):
    p = MoodBaseProfile(name(light=light, mode=mode, flag=flag))
    assert (p.rgb, p.timer, p.vibration, p.alarm, p.sync) == capabilities


def advertise(local_name, services=()):
    advertisement = MagicMock(
        address="AA:BB:CC:DD:EE:12",
        service_uuids=list(services),
        manufacturer_data={},
        service_data={},
    )
    advertisement.name = local_name
    return advertisement


@pytest.mark.parametrize(
    "local_name,eligible",
    [
        ("0123HHC789ABCD", True),
        ("😀123HHC89ABCD", True),
        ("0123hhc789ABCD", False),
        ("😀0123HHC789ABCD", False),
    ],
)
def test_discovery_keeps_shared_name_an_app_hint(local_name, eligible):
    uncorroborated = detect_bed_type_detailed(advertise(local_name))
    supported = advertise(local_name, [CARRIER_SERVICE_UUID])
    corroborated = detect_bed_type_detailed(supported)
    assert ("moodbase" in (uncorroborated.ambiguous_types or ())) is eligible
    assert ("service:moodbase_app_candidate" in corroborated.signals) is eligible
    assert _confident_auto_detect(corroborated) != "moodbase"
    if eligible:
        assert recommend_profile({const.CONF_BED_TYPE: "moodbase"}, supported, {}) is None


def test_app_hint_does_not_corroborate_a_receiver_recommendation(monkeypatch):
    from custom_components.adjustable_bed import profile_recommendations as recommendations
    from custom_components.adjustable_bed.detection import DetectionResult

    monkeypatch.setattr(
        recommendations,
        "detect_bed_type_detailed",
        lambda info: DetectionResult(
            bed_type=const.BED_TYPE_MOTOSLEEP,
            confidence=0.6,
            signals=["uuid:ffe0", "name:moodbase_app_candidate", "service:moodbase_app_candidate"],
            ambiguous_types=[const.BED_TYPE_MOODBASE],
        ),
    )
    assert (
        recommend_profile({const.CONF_BED_TYPE: const.BED_TYPE_LINAK}, advertise(name()), {})
        is None
    )


async def test_manual_setup_and_side_name(hass, enable_custom_integrations):
    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info", return_value=[]
    ):
        flow = await hass.config_entries.flow.async_init(const.DOMAIN, context={"source": "user"})
        flow = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {CONF_ADDRESS: "manual"}
        )
        flow = await answer_app(hass, flow, const.BED_TYPE_MOODBASE)
        flow = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {CONF_ADDRESS: "AA:BB:CC:DD:EE:12"}
        )
    assert flow["step_id"] == "profile_questions"
    wrong = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {const.CONF_BLE_DEVICE_NAME: name().lower()}
    )
    assert wrong["errors"] == {const.CONF_BLE_DEVICE_NAME: "moodbase_profile"}
    accepted = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {const.CONF_BLE_DEVICE_NAME: name("15", mode="M")}
    )
    assert accepted["step_id"] == "finish_settings"
    assert const.CONF_BLE_DEVICE_NAME in side_owned_profile_fields(
        {
            const.CONF_BED_TYPE: const.BED_TYPE_MOODBASE,
        }
    )


async def test_hold_release_and_single_press(runtime, clock):
    hass, co = runtime
    bed = await install(co, name(mode="M"))
    trace = []
    started = clock.time()
    co.client.write_gatt_char.side_effect = lambda char, payload, **kw: trace.append(
        (round((clock.time() - started) * 1000), bytes(payload))
    )
    await hass.services.async_call(
        const.DOMAIN,
        "hold_control",
        {
            "device_id": ["bed"],
            "control": "moodbase_head_up",
            "duration": 0.25,
        },
        blocking=True,
    )
    assert trace == [(100, b"$#$KR\r"), (200, b"$#$KR\r")] + [
        (delay, b"$#$bR\r") for delay in (250, 280, 310, 340, 370)
    ]
    co.client.write_gatt_char.reset_mock()
    await co.async_execute_controller_command(
        lambda ctrl: ctrl.hold_control("moodbase_tilt_down", 20)
    )
    await co.async_execute_controller_command(lambda ctrl: bed.press("massage_head_up"))
    assert writes(co) == [b"$#$QR\r"] * 3 + [b"$#$GR\r"]
    assert all(not call.kwargs["response"] for call in co.client.write_gatt_char.await_args_list)


@pytest.mark.parametrize("ending", ("release", "cancel", "stale", "expired"))
async def test_card_scoped_lease_keeps_native_tilt_release_semantics(runtime, clock, ending):
    hass, co = runtime
    await install(co, name())
    task = asyncio.create_task(
        hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {
                "device_id": ["bed"],
                "control": "moodbase_tilt_down",
                "duration": 0.75,
                "hold_owner": "card-native",
                "hold_generation": 2,
            },
            blocking=True,
        )
    )
    # Release before the native first refresh: normal up still has a three-frame tail.
    await asyncio.sleep(0.02 if ending != "expired" else 0.8)
    await hass.services.async_call(
        const.DOMAIN,
        "stop_all",
        {
            "device_id": ["bed"],
            "hold_owner": "card-native",
            "hold_generation": 1 if ending == "stale" else 2,
            "hold_cancelled": ending == "cancel",
        },
        blocking=True,
    )
    if ending == "stale":
        assert not task.done()
        assert writes(co) == []
        await hass.services.async_call(
            const.DOMAIN,
            "stop_all",
            {
                "device_id": ["bed"],
                "hold_owner": "card-native",
                "hold_generation": 2,
                "hold_cancelled": True,
            },
            blocking=True,
        )
    await task
    assert writes(co) == (
        [b"$Q"] * 3 if ending == "release" else [b"$Q"] * 7 if ending == "expired" else []
    )


async def test_native_card_cancel_action_uses_real_ha_entity_routing(runtime, clock):
    hass, co = runtime
    bed = await install(co, name())
    release_spec = next(spec for spec in bed.controller_button_specs if spec.release_only)
    release = ControllerActionButton(co, release_spec)
    await async_add_entry_entities(hass, co.entry, "button", [release])
    task = asyncio.create_task(
        hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": ["bed"], "control": "moodbase_tilt_down", "duration": 1},
            blocking=True,
        )
    )
    await asyncio.sleep(0.02)
    await hass.services.async_call(
        const.DOMAIN,
        "cancel_hold",
        {"entity_id": release.entity_id},
        blocking=True,
    )
    await task
    assert writes(co) == []


async def test_save_and_recall_are_separate(runtime, clock):
    _hass, co = runtime
    bed = await install(co, name("E1"))
    spec = next(spec for spec in bed.controller_button_specs if spec.key == "moodbase_save_snore")
    assert spec.requires_confirmation and spec.hold is None
    await co.async_execute_controller_command(spec.press_fn)
    assert writes(co) == [b"$W"]

    bed = await install(co, name("15"))
    await co.async_execute_controller_command(lambda ctrl: ctrl.program_memory(2))
    assert writes(co) == [b"$a"]
    assert bed.standard_button_hold_spec("program_memory_2") is None
    await co.async_execute_controller_command(lambda ctrl: ctrl.recall_memory(2, hold_ms=150))
    assert writes(co) == [b"$a", b"$V"]


async def test_rgb_native_light_and_timer(runtime, clock):
    hass, co = runtime
    bed = await install(co, name("15", mode="M"))
    light = AdjustableBedLight(co, LIGHT_DESCRIPTION)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    trace = []
    started = clock.time()
    co.client.write_gatt_char.side_effect = lambda char, payload, **kw: trace.append(
        (round((clock.time() - started) * 1000), bytes(payload))
    )
    await light.async_turn_on(rgb_color=(44, 128, 255), brightness=128)
    assert trace == [
        (0, b"$#000100031500006R\r"),
        (100, b"$#000300031600007R\r"),
        (200, b"$#000600031700003R\r"),
    ]
    (timer,) = bed.controller_number_specs
    await co.async_execute_controller_command(lambda ctrl: timer.set_fn(ctrl, 90))
    assert trace[-1] == (350, b"$#000900031900002R\r")
    assert co.controller_state.get(TIMER) == 90
    await light.async_turn_off()
    assert writes(co)[-3:] == [
        b"$#000000031500007R\r",
        b"$#000000031600004R\r",
        b"$#000000031700005R\r",
    ]


async def test_alarm_on_and_off_use_shared_action(runtime, clock):
    hass, co = runtime
    bed = await install(co, name(mode="E"))
    tokens = ["0"] * 75
    tokens[8], tokens[9], tokens[11] = "7", "30", "2"
    notification(bed, tokens)
    assert co.controller_state.get(ALARM) == "7:30"
    for data, expected in (
        ({"enabled": True, "time": "06:45", "massage_intensity": 2}, b"$#064500021900013R\r"),
        ({"enabled": False}, b"$#073000001700002R\r"),
    ):
        await hass.services.async_call(
            const.DOMAIN, "set_alarm", {"device_id": ["bed"], **data}, blocking=True
        )
        assert writes(co)[-2:] == [b"$z", expected]


async def test_vibration_sync_and_malformed_status(runtime, clock):
    _hass, co = runtime
    bed = await install(co, name(light="B", mode="M"))
    vibration = next(s for s in bed.controller_number_specs if s.state_key is VIBRATION_LEVEL)
    await co.async_execute_controller_command(lambda ctrl: vibration.set_fn(ctrl, 22))
    assert writes(co) == [b"$#V22\rR\r"]
    assert co.controller_state.get(VIBRATION_LEVEL) == 22
    with pytest.raises(ServiceValidationError, match="report whether"):
        await co.async_execute_controller_command(lambda ctrl: bed.set_sync_mode("wired"))
    assert writes(co) == [b"$#V22\rR\r"]

    tokens = ["0"] * 39
    notification(bed, tokens)
    assert co.controller_state.get(SYNC_MODE) == "wireless"
    await co.async_execute_controller_command(lambda ctrl: bed.set_sync_mode("wired"))
    assert writes(co)[-1] == b"$#330490000100012R\r"
    assert co.controller_state.get(SYNC_MODE) == "wired"

    tokens[24], tokens[27] = "000000000001", "00066"
    notification(bed, tokens)
    assert bed.protocol_diagnostics["sync_type"] == 1
    assert co.controller_state.get(SYNC_ENABLED) is False
    await co.async_execute_controller_command(lambda ctrl: bed.set_sync(True))
    assert writes(co)[-1] == b"$#000120000000003R\r"
    tokens[24], tokens[27] = "", "00065"
    notification(bed, tokens)
    assert bed.protocol_diagnostics["sync_type"] == 1
    assert co.controller_state.get(SYNC_ENABLED) is True
    with pytest.raises(ServiceValidationError, match="Unbind"):
        await co.async_execute_controller_command(lambda ctrl: bed.set_sync_mode("wireless"))
    await co.async_execute_controller_command(lambda ctrl: bed.set_sync(False))
    assert writes(co)[-1] == b"$#000150000000004R\r"


async def test_lost_link_never_finishes_color_on_replacement(runtime, clock):
    _hass, co = runtime
    bed = await install(co, name(mode="M"))
    old = co.client
    replacement = bedgear.client()
    old_callback = old.start_notify.await_args.args[1]
    task = asyncio.create_task(
        co.async_execute_controller_command(lambda ctrl: ctrl.set_light_color((255, 255, 255)))
    )
    await asyncio.sleep(0.05)
    co._client = replacement
    old_callback(old.services[0].characteristics[0], bytearray(b"$99"))
    with pytest.raises(ConnectionError):
        await task
    assert old.write_gatt_char.await_count == 1
    replacement.write_gatt_char.assert_not_awaited()
    assert bed._receiver.buffer == b""


async def test_missing_or_failed_notify_never_allows_motion(runtime):
    _hass, co = runtime
    bed = await install(co, name())
    await bed.stop_notify()
    char = co.client.services[0].characteristics[0]
    char.properties = ["write-without-response"]
    with pytest.raises(BedNotConnectedError):
        await bed.start_notify()
    char.properties.append("notify")
    co.client.start_notify = AsyncMock(side_effect=RuntimeError("Subscription failed"))
    with pytest.raises(RuntimeError, match="Subscription failed"):
        await bed.start_notify()
    with pytest.raises(ConnectionError):
        await bed.press("light_toggle")
    co.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("release_button", [False, True])
async def test_stop_interrupts_short_release_motion(runtime, clock, release_button):
    _hass, co = runtime
    bed = await install(co, name())
    first = asyncio.Event()
    outcomes = []

    async def write(_char, data, **_kwargs):
        if bytes(data) == b"$Q":
            first.set()

    async def hold(ctrl):
        with delivered(outcomes.append):
            await ctrl.hold_control("moodbase_tilt_down", 1000 if release_button else 20)

    co.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(co.async_execute_controller_command(hold))
    release_task = None
    if release_button:
        await asyncio.sleep(0.02)
        spec = next(s for s in bed.controller_button_specs if s.release_only)
        release_task = asyncio.create_task(ControllerActionButton(co, spec).async_press())

    await first.wait()
    await co.async_stop_command()
    await task
    if release_task is not None:
        await release_task
    assert writes(co) == [b"$Q"] + [b"$b"] * 5
    assert outcomes == [Delivery.PARTIAL]


@pytest.mark.parametrize("pair", ["E1", "51"])
async def test_head_and_back_methods_drive_the_layout_axis(runtime, clock, pair):
    _hass, co = runtime
    await install(co, name(pair))
    await co.async_execute_controller_command(lambda ctrl: ctrl.move_head_up())
    await co.async_execute_controller_command(lambda ctrl: ctrl.move_back_down())
    assert writes(co) == [b"$K"] * 10 + [b"$b"] * 5 + [b"$L"] * 10 + [b"$b"] * 5


async def test_brightness_readback_does_not_rescale_color_after_off(runtime, clock):
    hass, co = runtime
    bed = await install(co, name("15", mode="M"))
    light = AdjustableBedLight(co, LIGHT_DESCRIPTION)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(rgb_color=(255, 255, 255), brightness=128)
    initial = writes(co)
    assert co.controller_state.get(LIGHT_LEVEL) == 128

    tokens = ["0"] * 39
    tokens[18:21] = ["60", "60", "60"]
    notification(bed, tokens)
    assert co.controller_state.get(UNDER_BED_LIGHTS_RGB) == (255, 255, 255)
    light._handle_light_state(co.controller_state)

    await light.async_turn_off()
    tokens[18:21] = ["0", "0", "0"]
    notification(bed, tokens)
    light._handle_light_state(co.controller_state)
    await light.async_turn_on()
    assert writes(co)[-3:] == initial


async def test_disconnect_clears_projected_state_and_blocks_late_publication(runtime, clock):
    _hass, co = runtime
    bed = await install(co, name(light="B", mode="M"))
    tokens = ["0"] * 39
    tokens[24], tokens[27], tokens[30] = "1", "00065", "90"
    notification(bed, tokens)
    assert co.controller_state.get(SYNC_MODE) == "wired"
    assert co.controller_state.get(SYNC_ENABLED) is True
    assert co.controller_state.get(TIMER) == 90

    client = co.client
    started = asyncio.Event()
    completed = asyncio.Event()

    async def vibration_write(_char, _data, **_kwargs):
        started.set()
        await completed.wait()

    client.write_gatt_char.side_effect = vibration_write
    task = asyncio.create_task(
        co.async_execute_controller_command(lambda ctrl: bed.set_vibration(7))
    )
    await started.wait()
    co._on_disconnect(client)
    completed.set()
    await task
    assert all(
        co.controller_state.get(key) is None
        for key in (SYNC_MODE, SYNC_ENABLED, TIMER, VIBRATION_LEVEL)
    )
    assert bed._link is None


async def test_sync_mode_rechecks_binding_before_write(runtime, clock):
    _hass, co = runtime
    bed = await install(co, name())
    tokens = ["0"] * 39
    notification(bed, tokens)
    ready_to_write = asyncio.Event()
    writer = bed._write_gatt_with_retry

    async def write(*args, **kwargs):
        ready_to_write.set()
        await writer(*args, **kwargs)

    with patch.object(bed, "_write_gatt_with_retry", side_effect=write):
        async with bed.ble_lock:
            task = asyncio.create_task(
                co.async_execute_controller_command(lambda ctrl: bed.set_sync_mode("wired"))
            )
            await ready_to_write.wait()
            tokens[27] = "00066"
            notification(bed, tokens)
        with pytest.raises(ServiceValidationError, match="Unbind"):
            await task
    assert writes(co) == []


async def test_stop_at_last_successful_fallback_keeps_sent_delivery(runtime, clock):
    _hass, co = runtime
    await install(co, name())
    outcomes = []
    count = 0

    async def write(_char, data, **_kwargs):
        nonlocal count
        if bytes(data) == b"$Q":
            count += 1
            if count == 3:
                co.command_scheduler.request_cancel(outcome=CommandOutcome.STOPPED)

    async def hold(ctrl):
        with delivered(outcomes.append):
            await ctrl.hold_control("moodbase_tilt_down", 20)

    co.client.write_gatt_char.side_effect = write
    await co.async_execute_controller_command(hold)
    assert writes(co) == [b"$Q"] * 3
    assert outcomes == [Delivery.SENT]


async def test_inflight_color_report_and_timer_cannot_restore_old_power(runtime, clock):
    hass, co = runtime
    bed = await install(co, name("15", mode="M"))
    light = AdjustableBedLight(co, LIGHT_DESCRIPTION)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    co.register_controller_state_callback(light._handle_light_state)
    observed = False

    async def report_on_blue(_char, data, **_kwargs):
        nonlocal observed
        if bytes(data) == b"$#000600031700003R\r":
            observed = True
            tokens = ["0"] * 39
            tokens[18:21] = ["60", "60", "60"]
            notification(bed, tokens)
            assert co.controller_state.get(UNDER_BED_LIGHTS_ON) is not True

    co.client.write_gatt_char.side_effect = report_on_blue
    await light.async_turn_on(rgb_color=(255, 255, 255), brightness=128)
    assert observed
    assert bed.protocol_diagnostics["rgb"] == (127, 127, 127)
    assert co.controller_state.get(UNDER_BED_LIGHTS_ON) is True
    assert co.controller_state.get(UNDER_BED_LIGHTS_RGB) == (255, 255, 255)
    assert co.controller_state.get(LIGHT_LEVEL) == 128
    assert light.is_on

    await light.async_turn_off()
    assert co.controller_state.get(UNDER_BED_LIGHTS_ON) is False
    assert not light.is_on
    await co.async_execute_controller_command(lambda ctrl: bed.set_timer(10))
    assert not light.is_on


async def test_late_light_completion_cannot_restore_state_after_disconnect(runtime, clock):
    hass, co = runtime
    await install(co, name("15", mode="M"))
    light = AdjustableBedLight(co, LIGHT_DESCRIPTION)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    co.register_controller_state_callback(light._handle_light_state)
    client = co.client

    async def disconnect_on_blue(_char, data, **_kwargs):
        if bytes(data) == b"$#000600031700003R\r":
            co._on_disconnect(client)

    client.write_gatt_char.side_effect = disconnect_on_blue
    await light.async_turn_on(rgb_color=(255, 255, 255), brightness=128)
    assert client.write_gatt_char.await_count == 3
    assert co.controller_state.get(UNDER_BED_LIGHTS_ON) is None
    assert co.controller_state.get(UNDER_BED_LIGHTS_RGB) is None
    assert co.controller_state.get(LIGHT_LEVEL) is None
    assert not light.is_on
    assert light.rgb_color is None
    assert light.brightness is None


async def test_color_report_while_first_write_waits_is_not_lost(runtime, clock):
    hass, co = runtime
    bed = await install(co, name(mode="M"))
    light = AdjustableBedLight(co, LIGHT_DESCRIPTION)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    co.register_controller_state_callback(light._handle_light_state)
    ready_to_write = asyncio.Event()
    writer = bed._write_gatt_with_retry

    async def write(*args, **kwargs):
        ready_to_write.set()
        await writer(*args, **kwargs)

    with patch.object(bed, "_write_gatt_with_retry", side_effect=write):
        async with bed.ble_lock:
            task = asyncio.create_task(light.async_turn_on(rgb_color=(255, 255, 255)))
            await ready_to_write.wait()
            tokens = ["0"] * 39
            tokens[18] = "120"
            notification(bed, tokens)
            co.request_command_cancel()
        await task
    assert writes(co) == []
    assert light.is_on
    assert light.rgb_color == (255, 0, 0)


async def test_color_report_after_last_frame_wins_during_final_pacing(runtime, clock):
    hass, co = runtime
    bed = await install(co, name(mode="M"))
    light = AdjustableBedLight(co, LIGHT_DESCRIPTION)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    co.register_controller_state_callback(light._handle_light_state)

    task = asyncio.create_task(light.async_turn_on(rgb_color=(255, 255, 255)))
    await asyncio.sleep(0.25)
    assert co.client.write_gatt_char.await_count == 3
    assert not task.done()
    assert light.is_on
    notification(bed, ["0"] * 39)
    await task
    assert not light.is_on
    assert co.controller_state.get(UNDER_BED_LIGHTS_ON) is False
