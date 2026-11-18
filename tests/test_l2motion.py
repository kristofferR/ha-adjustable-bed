"""Leon's L2Motion controls through the shared runtime and HA command lane."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.bedgear.controller import (
    ALARM,
    L2SYNC,
    TIMER,
    BedgearController,
    Request,
)
from custom_components.adjustable_bed.beds.bedgear.music import MODE, VIBRATION, VOLUME
from custom_components.adjustable_bed.beds.bedgear.protocol import Receiver, token_fields
from custom_components.adjustable_bed.profiles.bedgear import BedgearProfile
from custom_components.adjustable_bed.profiles.l2motion import L2MotionProfile, eligible, panel
from tests import test_bedgear as bedgear_tests
from tests.test_bedgear import (
    name,
    notification,
    writes,
)

shared_runtime = bedgear_tests.runtime
clock = bedgear_tests.clock


async def install(co, selected):
    await co.controller.stop_notify()
    co._controller = BedgearController(co, name=selected, profile=L2MotionProfile(selected))
    await co.controller.start_notify()
    co.client.write_gatt_char.reset_mock()
    return co.controller


@pytest.fixture
async def runtime(shared_runtime):
    hass, co = shared_runtime
    await install(co, name())
    yield hass, co


# Independent layout and capability expectations, including the earlier rules.
@pytest.mark.parametrize(
    "pair,layout,axes,slots,presets,massage",
    [
        ("15", "PanelA", "head foot lumbar", 2, "flat anti_snore tv zero_g", False),
        ("35", "PanelD", "head foot neck", 2, "flat", True),
        ("45", "PanelD", "head foot lumbar", 2, "flat", True),
        ("85", "PanelD", "head foot tilt", 2, "flat", True),
        ("25", "PanelFour", "head lumbar foot", 2, "flat anti_snore tv zero_g", True),
        ("55", "PanelFour", "neck head foot tilt", 2, "flat anti_snore tv zero_g", True),
        ("95", "WR1140", "head foot tilt", 2, "flat anti_snore tv zero_g", True),
        ("96", "WR1140", "head foot", 2, "flat anti_snore tv zero_g", True),
        ("97", "WR1140", "neck head lumbar foot", 2, "flat anti_snore tv zero_g", True),
        ("98", "WR1140", "head lumbar foot", 2, "flat anti_snore tv zero_g", True),
        ("01", "PanelZero", "head foot combined tilt", 2, "flat", True),
        ("11", "PanelOne", "head", 0, "flat", False),
        ("12", "PanelOne", "head foot", 0, "flat", False),
        ("13", "PanelOne", "neck head foot", 0, "flat", False),
        ("14", "PanelOne", "neck head foot", 0, "flat", False),
        ("Z9", "PanelOne", "neck head foot", 0, "flat", False),
        ("21", "PanelTwo", "head", 2, "flat", True),
        ("22", "PanelTwo", "head foot", 2, "flat", True),
        ("23", "PanelTwo", "neck head foot", 2, "flat", True),
        ("24", "PanelTwo", "head foot", 2, "flat", True),
        ("31", "PanelThree", "head", 2, "flat anti_snore tv zero_g", False),
        ("32", "PanelThree", "head foot", 2, "flat anti_snore tv zero_g", False),
        ("33", "PanelThree", "neck head foot", 2, "flat anti_snore tv zero_g", False),
        ("34", "PanelThree", "neck head lumbar foot", 2, "flat anti_snore tv zero_g", False),
        ("39", "PanelThree", "head foot", 2, "flat anti_snore tv zero_g", False),
        ("65", "PanelThree", "head lumbar foot", 2, "flat anti_snore tv zero_g", False),
        ("75", "PanelThree", "neck head lumbar foot", 2, "flat anti_snore tv zero_g", False),
        ("41", "PanelFour", "head", 2, "flat anti_snore tv zero_g", True),
        ("42", "PanelFour", "head foot", 2, "flat anti_snore tv zero_g", True),
        ("43", "PanelFour", "neck head foot", 2, "flat anti_snore tv zero_g", True),
        ("44", "PanelFour", "neck head lumbar foot", 2, "flat anti_snore tv zero_g", True),
        ("51", "PanelFive", "head", 0, "flat", False),
        ("61", "PanelSix", "head foot", 0, "flat", False),
        ("71", "PanelSeven", "head foot", 2, "flat", True),
        ("81", "PanelEight", "head foot", 2, "flat anti_snore tv zero_g", False),
        ("91", "PanelNine", "head foot", 0, "flat", False),
        ("A1", "PanelA", "head foot lumbar", 2, "flat anti_snore tv zero_g", False),
        ("B1", "PanelFour", "head foot", 2, "flat anti_snore tv zero_g", True),
        ("C1", "PanelD", "head foot neck", 2, "flat", True),
        ("D1", "PanelSixZG", "head foot", 0, "zero_g", False),
        ("E1", "PanelE", "head", 0, "flat anti_snore", False),
    ],
)
def test_layout_permissions(pair, layout, axes, slots, presets, massage):
    p = L2MotionProfile(name(pair))
    assert panel(p.name) == layout
    assert [axis for axis, _, _ in p.axes] == axes.split()
    assert p.memory_slots == slots
    assert [key for key, _ in p.presets] == presets.split()
    assert any(c.key.startswith("massage_") for c in p.controls) is massage
    assert p.light is (slots > 0 or layout == "PanelE")
    assert not p.execution.concurrent


@pytest.mark.parametrize(
    "light,mode,flag,rgb,timer,music,alarm,sync",
    [
        ("D", "0", "X", True, True, False, False, True),
        ("C", "D", "H", False, True, False, False, False),
        ("B", "M", "X", False, False, True, False, True),
        ("C", "E", "H", True, True, False, True, False),
    ],
)
def test_independent_auxiliary_gates(light, mode, flag, rgb, timer, music, alarm, sync):
    p = L2MotionProfile(name(light=light, mode=mode, flag=flag))
    assert (p.rgb, p.timer, p.music, p.alarm, p.sync) == (rgb, timer, music, alarm, sync)


def test_name_and_letter_case():
    assert eligible("xxHHC00001D00X")
    assert not eligible("hhc0000001D00X")
    assert not eligible("HHC0000001D00X ")
    assert L2MotionProfile(name("15", flag="H")).axes[-1] == ("lumbar", "p", "q")
    assert L2MotionProfile(name("15")).axes[-1] == ("lumbar", "P", "Q")
    assert L2MotionProfile(name("25")).axes[1] == ("lumbar", "P", "Q")
    assert L2MotionProfile(name("65")).axes[1] == ("lumbar", "P", "Q")
    assert not BedgearProfile(name(light="C")).rgb  # Prior-app default stays independent.


async def test_first_tick_and_five_stop_offsets(runtime, clock):
    _hass, co = runtime
    trace = []
    start = clock.time()
    co.client.write_gatt_char.side_effect = lambda _char, data, **_kw: trace.append(
        (round((clock.time() - start) * 1000), bytes(data))
    )
    task = asyncio.create_task(
        co.async_execute_controller_command(lambda c: c.hold_control("l2motion_head_up", 250))
    )
    await asyncio.sleep(0.05)
    assert trace == []
    await task
    assert trace == [
        (100, b"$K"),
        (200, b"$K"),
        (250, b"$b"),
        (280, b"$b"),
        (310, b"$b"),
        (340, b"$b"),
        (370, b"$b"),
    ]


@pytest.mark.parametrize(
    "pair,key,expected",
    [
        ("01", "tilt_down", [b"$Q"] * 3),
        ("01", "preset_flat", [b"$O"] * 3),
        ("91", "preset_flat", []),
        ("E1", "preset_anti_snore", []),
        ("E1", "preset_flat", [b"$O"] * 3),
        ("01", "massage_head_up", [b"$G"] * 3),
    ],
)
async def test_short_up_filler_and_callback_policy(runtime, clock, pair, key, expected):
    _hass, co = runtime
    await install(co, name(pair))
    await co.async_execute_controller_command(lambda c: c.hold_control("l2motion_" + key, 20))
    assert writes(co) == expected


@pytest.mark.parametrize(
    "key,stop", [("head_up", True), ("tilt_down", False), ("preset_flat", False)]
)
async def test_cancel_never_fills_or_adds_up_motion(runtime, clock, key, stop):
    _hass, co = runtime
    events = []

    async def held(controller):
        events.append(co.cancel_command)
        await controller.hold_control("l2motion_" + key, 1000)

    task = asyncio.create_task(co.async_execute_controller_command(held))
    await asyncio.sleep(0.05)
    events[0].set()
    await task
    assert writes(co) == ([b"$b"] * 5 if stop else [])


async def test_public_memory_save_does_not_assume_phone_widget_up(runtime, clock):
    hass, co = runtime
    await hass.services.async_call(
        "adjustable_bed", "save_preset", {"device_id": ["bed"], "preset": 1}, blocking=True
    )
    assert writes(co) == [b"$Z"]


async def test_music_uses_current_volume_and_mutable_mode_maps(runtime, clock):
    _hass, co = runtime
    bed = await install(co, name(mode="M"))
    assert co.controller_state.get(VOLUME) is None and co.controller_state.get(MODE) is None
    await co.async_execute_controller_command(lambda c: c.set_music(0, 7.9))
    await co.async_execute_controller_command(lambda c: c.set_music_mode("vocal"))
    assert writes(co) == [b"$#M07\rR\r", b"$#M07\r$#T10\r$#B05\r$#V05\rR\r"]
    with pytest.raises(ValueError, match="Custom"):
        await co.async_execute_controller_command(lambda c: c.set_music(1, 15))
    await co.async_execute_controller_command(lambda c: c.set_music(3, 9))
    await co.async_execute_controller_command(lambda c: c.set_music_mode("cinema"))
    await co.async_execute_controller_command(lambda c: c.set_music_mode("vocal"))
    assert writes(co)[-1] == b"$#M07\r$#T10\r$#B05\r$#V09\rR\r"
    assert co.controller_state.get(VOLUME) == 7 and co.controller_state.get(VIBRATION) == 9
    await bed.stop_notify()
    assert co.controller_state.get(VOLUME) is None


async def test_parsed_alarm_offsets_timer_and_sync(runtime, clock):
    _hass, co = runtime
    bed = await install(co, name(mode="E"))
    tokens = ["00000"] * 75
    tokens[8], tokens[9], tokens[11], tokens[54] = "06", "30", "1", "999999"
    notification(bed, tokens)
    assert co.controller_state.get(ALARM) == "06:30"
    assert co.controller_state.get(TIMER) == 65535
    assert not any(spec.state_key == TIMER for spec in bed.controller_state_sensor_specs)
    timer_spec = next(spec for spec in bed.controller_number_specs if spec.state_key == TIMER)
    assert timer_spec.card.attributes["card_role"] == "timer_minutes"
    tokens = ["00000"] * 39
    tokens[24], tokens[27] = "1", "00066"
    notification(bed, tokens)
    assert co.controller_state.get(L2SYNC) is False
    await co.async_execute_controller_command(lambda c: c.set_sync(True))
    assert writes(co) == [b"$#000120000000003R\r"]


@pytest.mark.parametrize(
    "strength,enabled,expected",
    [
        (1, True, b"$#063000011800013R\r"),
        (2, True, b"$#063000021900015R\r"),
        (1, False, b"$#063000001700003R\r"),
    ],
)
async def test_unified_alarm_service(runtime, clock, strength, enabled, expected):
    hass, co = runtime
    await install(co, name(mode="E"))
    await hass.services.async_call(
        "adjustable_bed",
        "set_alarm",
        {
            "device_id": ["bed"],
            "time": "06:30:00",
            "enabled": enabled,
            "massage_intensity": strength,
        },
        blocking=True,
    )
    assert writes(co) == [b"$z", expected]
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "adjustable_bed",
            "set_alarm",
            {"device_id": ["bed"], "enabled": True, "weekdays": ["monday"]},
            blocking=True,
        )


async def test_rgb_sequence_and_latest_busy_debounce(runtime, clock):
    hass, co = runtime

    async def color(rgb):
        await hass.services.async_call(
            "adjustable_bed",
            "l2motion",
            {"device_id": ["bed"], "operation": "rgb", "rgb": rgb},
            blocking=True,
        )

    first = asyncio.create_task(color([255, 0, 0]))
    await asyncio.sleep(0.05)
    second = asyncio.create_task(color([0, 255, 255]))
    await asyncio.gather(first, second)
    assert (
        writes(co)
        == [
            b"$z",
            b"$#003150000000007R\r",
            b"$z",
            b"$#003160012000007R\r",
            b"$z",
            b"$#003170012000006R\r",
        ]
        * 2
    )


@pytest.mark.parametrize("duration,count", [(100, 1), (500, 5)])
async def test_timed_move_final_tick_survives_scheduler_lateness(runtime, clock, duration, count):
    hass, co = runtime
    original = co.controller._wait

    async def late(seconds, cancel):
        result = await original(seconds, cancel)
        if seconds > 0 and result:
            await asyncio.sleep(0.001)
        return result

    with patch.object(co.controller, "_wait", side_effect=late):
        await hass.services.async_call(
            "adjustable_bed",
            "timed_move",
            {"device_id": ["bed"], "motor": "head", "direction": "up", "duration_ms": duration},
            blocking=True,
        )
    assert writes(co) == [b"$K"] * count + [b"$b"] * 5


async def test_five_late_periodic_ticks_do_not_trigger_short_up_filler(runtime, clock):
    _hass, co = runtime
    original = co.controller._wait

    async def late(seconds, cancel):
        result = await original(seconds, cancel)
        if seconds > 0 and result:
            await asyncio.sleep(0.001)
        return result

    with patch.object(co.controller, "_wait", side_effect=late):
        await co.async_execute_controller_command(
            lambda c: c.hold_control("l2motion_preset_flat", 500)
        )
    assert writes(co) == [b"$O"] * 5


@pytest.mark.parametrize(
    "key,letter,cleanup", [("preset_flat", b"$O", []), ("head_up", b"$K", [b"$b"] * 5)]
)
async def test_failed_hold_never_fills_but_still_sends_defined_stop(
    runtime, clock, key, letter, cleanup
):
    _hass, co = runtime

    async def fail_motion(_char, data, **_kwargs):
        if bytes(data) == letter:
            raise RuntimeError("failed motor write")

    co.client.write_gatt_char.side_effect = fail_motion
    with pytest.raises(RuntimeError, match="failed motor write"):
        await co.async_execute_controller_command(lambda c: c.hold_control("l2motion_" + key, 500))
    assert writes(co) == [letter] + cleanup


async def test_sync_switch_requires_current_support_report(runtime, clock):
    from custom_components.adjustable_bed.switch import AdjustableBedControllerSwitch

    _hass, co = runtime
    bed = co.controller
    entity = AdjustableBedControllerSwitch(
        co, next(s for s in bed.controller_switch_specs if s.state_key == L2SYNC)
    )
    assert not entity.available and entity.is_on is None
    assert not bed.supports_single_address_pairing
    assert BedgearController(co, name=name()).supports_single_address_pairing
    tokens = ["00000"] * 39
    tokens[27] = "00066"
    notification(bed, tokens)
    assert entity.available and entity.is_on is False
    tokens[27] = "00000"
    notification(bed, tokens)
    assert not entity.available and entity.is_on is None
    with pytest.raises(ValueError):
        await bed.set_sync(True)
    assert writes(co) == []


async def test_sync_switch_refreshes_after_unexpected_disconnect(runtime, clock):
    from custom_components.adjustable_bed.switch import AdjustableBedControllerSwitch

    hass, co = runtime
    bed = co.controller
    entity = AdjustableBedControllerSwitch(
        co, next(spec for spec in bed.controller_switch_specs if spec.state_key == L2SYNC)
    )
    entity.hass = hass
    with patch.object(entity, "async_write_ha_state") as publish:
        await entity.async_added_to_hass()
        try:
            tokens = ["00000"] * 39
            tokens[27] = "00066"
            notification(bed, tokens)
            assert entity.available
            co.cache_capability_controller()
            dropped = co.client
            dropped.is_connected = False
            publish.reset_mock()
            with patch.object(co, "_auto_reconnect_enabled", return_value=False):
                co._on_disconnect(dropped)
            assert co.controller is None and co.capability_controller is bed
            assert bed._bind == (True, False)  # Cached capability evidence remains.
            assert not entity.available
            publish.assert_called_once()
            with pytest.raises(ValueError):
                await bed.set_sync(True)
            dropped.write_gatt_char.assert_not_awaited()
        finally:
            await entity.async_will_remove_from_hass()


async def test_public_rgb_reconnects_after_idle_disconnect(runtime, clock):
    from tests.test_bedgear import client

    hass, co = runtime
    cached = co.controller
    co.cache_capability_controller()
    old_client = co.client
    old_client.disconnect.side_effect = lambda: setattr(old_client, "is_connected", False)
    assert await co.async_disconnect("idle_timeout")
    assert co.controller is None and co.capability_controller is cached
    connections = []

    async def reconnect(**_kwargs):
        if co.controller is None:
            connections.append(True)
            co._client = client()
            co._controller = BedgearController(co, name=name(), profile=L2MotionProfile(name()))
            await co.controller.start_notify()
        return True

    with patch.object(co, "async_ensure_connected", side_effect=reconnect):
        await hass.services.async_call(
            "adjustable_bed",
            "l2motion",
            {"device_id": ["bed"], "operation": "rgb", "rgb": [255, 0, 0]},
            blocking=True,
        )
    assert connections == [True]
    assert writes(co) == [
        b"$z",
        b"$#003150012000004R\r",
        b"$z",
        b"$#003160000000004R\r",
        b"$z",
        b"$#003170000000005R\r",
    ]


async def test_bluetooth_hhc_overlap_offers_l2motion(
    hass, enable_custom_integrations, mock_bluetooth_service_info
):
    from custom_components.adjustable_bed.const import DOMAIN

    mock_bluetooth_service_info.name = name()
    mock_bluetooth_service_info.service_uuids = []
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "bluetooth"},
        data=mock_bluetooth_service_info,
    )
    assert result["step_id"] == "bluetooth_disambiguate"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"bed_type_choice": "l2motion"}
    )
    assert result["step_id"] == "bluetooth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"bed_type": "l2motion"}
    )
    assert result["step_id"] == "profile_questions"


async def test_stale_rgb_and_notification_cannot_reach_new_session(runtime, clock):
    hass, co = runtime
    old = co.controller
    link = old._link

    async def color(rgb):
        await hass.services.async_call(
            "adjustable_bed",
            "l2motion",
            {"device_id": ["bed"], "operation": "rgb", "rgb": rgb},
            blocking=True,
        )

    task = asyncio.create_task(color([255, 255, 255]))
    await asyncio.sleep(0.02)
    replacement_input = asyncio.create_task(color([0, 255, 255]))
    await asyncio.sleep(0.05)
    replacement = await install(co, name())
    with pytest.raises(ConnectionError):
        await task
    await replacement_input
    old._notification(link, link.write, bytearray(b"$1 2 3"))
    assert replacement._rgb is None
    assert writes(co) == []


async def test_configuration_service_checks_all_targets_before_writing(runtime, clock):
    hass, co = runtime
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "adjustable_bed",
            "l2motion",
            {"device_id": ["bed"], "operation": "sync_mode", "wired": True},
            blocking=True,
        )
    assert writes(co) == []
    await hass.services.async_call(
        "adjustable_bed",
        "l2motion",
        {"device_id": ["bed"], "operation": "sync_mode", "wired": True, "confirm": True},
        blocking=True,
    )
    assert writes(co) == [b"$#330490000100012R\r"]
    await install(co, name(light="B"))
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "adjustable_bed",
            "l2motion",
            {"device_id": ["bed"], "operation": "rgb", "rgb": [255, 255, 255]},
            blocking=True,
        )
    assert writes(co) == []


def test_source_stream_shapes_and_parser_quirks():
    for length in (39, 44, 71, 75):
        tokens = [f"{i:02d}" for i in range(length)]
        if length == 39:
            tokens[27] = "00065"
        receiver = Receiver()
        assert receiver.feed(b"$" + " ".join(tokens).encode()) == ()
        texts = receiver.feed(b"R\r")
        fields = token_fields(texts[0], alarm_indices=(8, 9, 11))
        assert fields["rgb_timer"] == (
            ["28", "29", "30", "54"] if length == 75 else ["18", "19", "20", "30"]
        )
        if length == 75:
            assert fields["alarm"] == ["08", "09", "11"]
        if length == 39:
            assert (
                fields["bind"] == {"available": True, "active": True} and fields["sync_type"] == 24
            )
    receiver = Receiver()
    assert receiver.feed(b"$1R\r") == ()  # Initial packet CR is ignored.
    assert receiver.feed(b"$2") == ()
    assert receiver.feed(b"X\r") == ("12",)  # Drops X regardless of its value.


async def test_setup_and_reconfigure_keep_original_per_side_name(hass, enable_custom_integrations):
    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.profile_migration import reconfigure_context
    from tests.form_helpers import answer_app

    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info", return_value=[]
    ):
        result = await hass.config_entries.flow.async_init(const.DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "manual"}
        )
        result = await answer_app(hass, result, "l2motion")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "AA:BB:CC:DD:EE:12"}
        )
    assert result["step_id"] == "profile_questions"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_BLE_DEVICE_NAME: name("15")}
    )
    assert result["step_id"] == "finish_settings"
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False),
        patch("custom_components.adjustable_bed.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: "My bed", const.CONF_PREFERRED_ADAPTER: "auto"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = AdjustableBedCoordinator(hass, entry)
    assert entry.data[const.CONF_BLE_DEVICE_NAME] == name("15")
    side_profile = per_side_profile("l2motion", "auto")
    assert side_profile is not None and const.CONF_BLE_DEVICE_NAME in side_profile.keys
    manager = hass.config_entries.flow
    result = await manager.async_init(const.DOMAIN, context=reconfigure_context(entry))
    result = await manager.async_configure(result["flow_id"], {const.CONF_BED_TYPE: "l2motion"})
    assert result["step_id"] == "profile_questions"
    result = await manager.async_configure(
        result["flow_id"], {const.CONF_BLE_DEVICE_NAME: name("E1", mode="E")}
    )
    assert result["step_id"] == "migration_confirm"
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BLE_DEVICE_NAME] == name("E1", mode="E")


@pytest.mark.parametrize("active", [False, True])
async def test_second_ineligible_target_blocks_first_write_or_ingress(runtime, clock, active):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from tests.test_bedgear import client

    hass, co = runtime
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:13",
            const.CONF_BED_TYPE: "l2motion",
            const.CONF_BLE_DEVICE_NAME: name(light="B"),
        },
    )
    entry.add_to_hass(hass)
    other = AdjustableBedCoordinator(hass, entry)
    other._client = client()
    other._controller = BedgearController(
        other, name=name(light="B"), profile=L2MotionProfile(name(light="B"))
    )
    await other.controller.start_notify()
    running = None
    if active:
        running = asyncio.create_task(
            hass.services.async_call(
                const.DOMAIN,
                "l2motion",
                {"device_id": ["bed"], "operation": "rgb", "rgb": [255, 0, 0]},
                blocking=True,
            )
        )
        await asyncio.sleep(0.02)
    try:
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(co, "both"), (other, "both")], []),
            ),
            pytest.raises(ServiceValidationError),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "l2motion",
                {"device_id": ["bed"], "operation": "rgb", "rgb": [255, 255, 255]},
                blocking=True,
            )
        if running is not None:
            await running
        assert writes(other) == []
        assert writes(co) == (
            [
                b"$z",
                b"$#003150012000004R\r",
                b"$z",
                b"$#003160000000004R\r",
                b"$z",
                b"$#003170000000005R\r",
            ]
            if active
            else []
        )
    finally:
        await other.async_shutdown()


async def test_expired_queued_write_is_suppressed_but_stop_drains(runtime, clock):
    _hass, co = runtime
    await co.controller.ble_lock.acquire()
    task = asyncio.create_task(co.controller.hold_control("l2motion_head_up", 200))
    await asyncio.sleep(0.3)
    co.controller.ble_lock.release()
    await task
    assert writes(co) == [b"$b"] * 5


@pytest.mark.parametrize("latency,expected_ms", [(0.4, [100]), (0.26, [100, 400, 500])])
async def test_slow_write_does_not_replay_missed_ticks(runtime, clock, latency, expected_ms):
    _hass, co = runtime
    at = []
    began = clock.time()

    async def slow(_char, data, **_kwargs):
        if bytes(data) == b"$K":
            at.append(round((clock.time() - began) * 1000))
            if len(at) == 1:
                await asyncio.sleep(latency)

    co.client.write_gatt_char.side_effect = slow
    await co.async_execute_controller_command(lambda c: c.hold_control("l2motion_head_up", 500))
    assert at == expected_ms
    assert writes(co) == [b"$K"] * len(expected_ms) + [b"$b"] * 5


@pytest.mark.parametrize(
    "pair,key",
    [
        ("51", "foot_up"),
        ("D1", "preset_flat"),
        ("34", "massage_head"),
        ("E1", "memory_1"),
        ("81", "massage_head"),
    ],
)
async def test_denied_layout_controls_never_write(runtime, clock, pair, key):
    _hass, co = runtime
    await install(co, name(pair))
    with pytest.raises(NotImplementedError):
        await co.async_execute_controller_command(lambda controller: controller.press(key))
    assert writes(co) == []


async def test_brightness_scales_color_and_m_route_suppresses_queries(runtime, clock):
    _hass, co = runtime
    await install(co, name(mode="M"))
    await co.async_execute_controller_command(
        lambda controller: controller.configure(
            Request(operation="rgb", rgb=(255, 64, 255), brightness=0.5)
        )
    )
    assert writes(co) == [b"$#003150005900011R\r", b"$#003160000000004R\r", b"$#003170005900009R\r"]


async def test_light_timer_queries_then_waits_without_fabricating_readback(runtime, clock):
    _hass, co = runtime
    trace = []
    started = clock.time()
    co.client.write_gatt_char.side_effect = lambda _char, data, **_kw: trace.append(
        (round((clock.time() - started) * 1000), bytes(data))
    )
    await co.async_execute_controller_command(
        lambda controller: controller.configure(Request(operation="light_timer", minutes=10))
    )
    assert trace == [(0, b"$z"), (50, b"$#003190001000010R\r")]
    assert co.controller_state.get(TIMER) is None


def test_setup_rejects_non_text_bluetooth_name():
    from custom_components.adjustable_bed.setup_questions import _l2motion_errors

    assert _l2motion_errors({"ble_device_name": 14}) == {"ble_device_name": "l2motion_profile"}


async def test_stop_cancels_delayed_rgb_before_channel_writes(runtime, clock):
    _hass, co = runtime
    task = asyncio.create_task(
        co.async_execute_controller_command(
            lambda controller: controller.configure(Request(operation="rgb", rgb=(255, 255, 255)))
        )
    )
    await asyncio.sleep(0.05)
    await co.async_stop_command()
    await task
    assert writes(co) == [b"$z"] + [b"$b"] * 5
    assert co.controller._color_busy is None


async def test_stop_cancels_merged_public_rgb_without_replaying_it(runtime, clock):
    hass, co = runtime

    async def color(rgb):
        await hass.services.async_call(
            "adjustable_bed",
            "l2motion",
            {"device_id": ["bed"], "operation": "rgb", "rgb": rgb},
            blocking=True,
        )

    first = asyncio.create_task(color([255, 0, 0]))
    await asyncio.sleep(0.02)
    second = asyncio.create_task(color([0, 255, 255]))
    await asyncio.sleep(0.03)
    await co.async_stop_command()
    await asyncio.gather(first, second)
    assert writes(co) == [b"$z"] + [b"$b"] * 5
    assert co.controller._color_busy is None


async def test_replaced_rgb_debounce_waits_from_latest_input(runtime, clock):
    hass, co = runtime
    trace = []
    started = clock.time()
    co.client.write_gatt_char.side_effect = lambda _char, data, **_kw: trace.append(
        (round((clock.time() - started) * 1000), bytes(data))
    )

    async def color(rgb):
        await hass.services.async_call(
            "adjustable_bed",
            "l2motion",
            {"device_id": ["bed"], "operation": "rgb", "rgb": rgb},
            blocking=True,
        )

    first = asyncio.create_task(color([255, 0, 0]))
    await asyncio.sleep(0.3)
    second = asyncio.create_task(color([0, 255, 0]))
    await asyncio.sleep(0.35)
    third = asyncio.create_task(color([0, 0, 255]))
    await asyncio.gather(first, second, third)
    assert trace[6][0] == 1150
    assert [data for _, data in trace[6:]] == [
        b"$z",
        b"$#003150000000007R\r",
        b"$z",
        b"$#003160000000004R\r",
        b"$z",
        b"$#003170012000006R\r",
    ]
