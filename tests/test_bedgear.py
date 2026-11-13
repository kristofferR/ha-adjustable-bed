"""Bedgear's source routes through setup, entities, services and HA admission."""

from __future__ import annotations

import asyncio
import json
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.bedgear import controller as module
from custom_components.adjustable_bed.beds.bedgear.controller import (
    ALARM,
    BIND,
    RGB,
    SYNC,
    TIMER,
    BedgearController,
    select_transport,
)
from custom_components.adjustable_bed.command_scheduler import CommandKind, CommandOutcome
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.bedgear import BedgearProfile
from custom_components.adjustable_bed.services import async_register_services
from tests.form_helpers import answer_app, form_answers
from tests.hold_lease_wire import virtual_clock

COMMANDS = json.loads((Path(__file__).parent / "fixtures/bedgear/commands.json").read_text())
NAMES = ("15", "35", "E1", "81", "51", "44", "91", "13", "71", "61", "D1", "34", "23", "01", "97")


def name(pair="01", *, light="D", mode="0", flag="X"):
    return "HHC00000" + pair + light + mode + "0" + flag


def client():
    result = MagicMock()
    result.is_connected = True
    # Intentionally noncanonical UUIDs and no characteristic properties.
    char = SimpleNamespace(uuid="1234FfE10000", handle=7, properties=[])
    result.services = [SimpleNamespace(uuid="abcFFE0123", characteristics=[char])]
    result.disconnect = AsyncMock()
    result.start_notify = AsyncMock()
    result.stop_notify = AsyncMock()
    result.write_gatt_char = AsyncMock()
    return result


@pytest.fixture
async def runtime(hass):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Bedgear",
        unique_id="AA:BB:CC:DD:EE:12",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:12",
            CONF_NAME: "Bedgear",
            const.CONF_BED_TYPE: "bedgear",
            const.CONF_BLE_DEVICE_NAME: name(),
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, entry)
    co._client = client()
    co._controller = await create_controller(co, "bedgear", "auto", co.client)
    await co.controller.start_notify()
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = co
    await async_register_services(hass)
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(co, "async_ensure_connected", AsyncMock(return_value=True))
        )
        stack.enter_context(patch.object(co, "_async_refresh_controller_auth", AsyncMock()))
        stack.enter_context(
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(co, "both")], []),
            )
        )
        yield hass, co
    await co.async_shutdown()


@pytest.fixture
async def clock(runtime):
    with virtual_clock() as fake, patch.object(module, "monotonic", fake.time):
        yield fake


async def install(co, selected):
    await co.controller.stop_notify()
    co._controller = BedgearController(co, name=selected)
    await co.controller.start_notify()
    co.client.write_gatt_char.reset_mock()
    return co.controller


def writes(co):
    return [bytes(call.args[1]) for call in co.client.write_gatt_char.await_args_list]


async def call(hass, operation, **fields):
    await hass.services.async_call(
        const.DOMAIN,
        "bedgear",
        {"device_id": ["bed"], "operation": operation, **fields},
        blocking=True,
    )


@pytest.mark.parametrize("pair", NAMES)
async def test_real_setup_saved_profile_factory_and_configure(
    hass, enable_custom_integrations, pair
):
    selected = name(pair, mode="E")
    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info", return_value=[]
    ):
        result = await hass.config_entries.flow.async_init(const.DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "manual"}
        )
        result = await answer_app(hass, result, "bedgear")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "AA:BB:CC:DD:EE:12"}
        )
    assert result["step_id"] == "profile_questions"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_BLE_DEVICE_NAME: selected}
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
    data = result["data"]
    assert data[const.CONF_BLE_DEVICE_NAME] == selected
    assert data[const.CONF_DISABLE_ANGLE_SENSING] is True
    entry = result["result"]
    co = AdjustableBedCoordinator(hass, entry)
    co._client = client()
    co._controller = await create_controller(co, "bedgear", "auto", co.client)
    bed = co.controller
    assert isinstance(bed, BedgearController)
    assert bed.profile == BedgearProfile(selected)
    assert bed.motor_control_specs and all(
        spec.hold is not None for spec in bed.motor_control_specs
    )
    assert not bed.supports_position_feedback
    assert bed.memory_slot_count == bed.profile.memory_slots
    # Configure exposes the exact same owned name rather than generic layout guesses.
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = co
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    assert result["step_id"] == "settings"
    answers = form_answers(result)
    answers[const.CONF_BLE_DEVICE_NAME] = name(pair, mode="M")
    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_configure(result["flow_id"], answers)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_BLE_DEVICE_NAME] == name(pair, mode="M")
    await co.async_shutdown()


@pytest.mark.parametrize("row", COMMANDS[:183], ids=lambda row: row["id"])
async def test_every_source_short_command_and_branch_through_admitted_controls(runtime, clock, row):
    hass, co = runtime
    if row["id"] == "A12-C183":
        await co.async_stop_command()
        assert writes(co) == [b"$b"] * 5
        return
    pairs = list(NAMES) + [
        "25",
        "55",
        "65",
        "75",
        "95",
        "96",
        "98",
        "41",
        "42",
        "43",
        "31",
        "32",
        "11",
        "12",
        "21",
        "22",
    ]
    for source_command, literal in row["frames"].items():
        expected = source_command[1:]
        key = ""
        # Source action labels distinguish axes which share the same literal.
        action = row["action"]
        if "program" in action:
            pair = next(
                pair for pair in pairs if BedgearProfile(name(pair)).panel == row["variant"]
            )
            bed = await install(co, name(pair))
            if "snore" in action:
                await call(hass, "save_snore")
            else:
                await call(hass, "save_memory", slot=1 if action.endswith("1") else 2)
        else:
            if action.startswith("LUMBAR-labelled"):
                key = "lumbar_" + action.rsplit(" ", 1)[1]
            elif action.startswith("third axis"):
                key = "neck_" + action.rsplit(" ", 1)[1]
            elif action.startswith("single actuator"):
                key = "actuator_" + action.rsplit(" ", 1)[1]
            elif action.startswith("whole-bed tilt"):
                key = "tilt_" + action.rsplit(" ", 1)[1]
            elif action.startswith("combined"):
                key = "combined_" + action.rsplit(" ", 1)[1]
            elif action.startswith("recall memory"):
                key = "memory_" + action[-1]
            elif "preset" in action:
                key = (
                    "preset_" + {"O": "flat", "R": "anti_snore", "S": "tv", "T": "zero_g"}[expected]
                )
            elif action == "light toggle":
                key = "light_toggle"
            elif "massage" in action:
                key = (
                    "massage_"
                    + {
                        "C": "head",
                        "B": "foot",
                        "D": "stop",
                        "G": "head_up",
                        "H": "head_down",
                        "J": "head_stop",
                        "E": "foot_up",
                        "F": "foot_down",
                        "I": "foot_stop",
                    }[expected]
                )
            else:
                key = action.replace(" ", "_")
            choices = [name(pair, flag=flag) for pair in pairs for flag in ("H", "X")]
            selected = next(
                n
                for n in choices
                if BedgearProfile(n).panel == row["variant"]
                and any(c.key == key and c.letter == expected for c in BedgearProfile(n).controls)
            )
            bed = await install(co, selected)
            binding = next(c for c in bed.profile.controls if c.key == key)
            if binding.held:
                await hass.services.async_call(
                    const.DOMAIN,
                    "hold_control",
                    {"device_id": ["bed"], "control": "bedgear_" + key, "duration": 0.2},
                    blocking=True,
                )
            else:
                spec = next(s for s in bed.controller_button_specs if s.key == "bedgear_" + key)
                await co.async_execute_controller_command(spec.press_fn)
        actual = writes(co)
        assert actual and actual[0].hex() == literal["plain_hex"]
        if "program" not in action:
            held = next(c for c in bed.profile.controls if c.key == key)
            assert (actual.count(b"$b") == 5) == (held.release == "stop")
        assert all(c.kwargs["response"] is False for c in co.client.write_gatt_char.await_args_list)


@pytest.mark.parametrize(
    "operation,fields,expected",
    [
        (
            "rgb",
            {"rgb": [255, 64, 255]},
            [
                b"$z",
                b"$#003150012000004R\r",
                b"$z",
                b"$#003160003000007R\r",
                b"$z",
                b"$#003170012000006R\r",
            ],
        ),
        ("light_timer", {"minutes": 10}, [b"$z", b"$#003190001000010R\r"]),
        ("light_timer", {"minutes": 0}, [b"$z", b"$#003190000000011R\r"]),
        ("alarm", {"time": "07:30", "strength": 0}, [b"$z", b"$#073000001700002R\r"]),
        ("alarm", {"time": "08:30", "strength": 1}, [b"$z", b"$#083000011800003R\r"]),
        ("alarm", {"time": "08:30", "strength": 2}, [b"$z", b"$#083000021900001R\r"]),
        ("sync_mode", {"wired": False, "confirm": True}, [b"$#330490000000013R\r"]),
        ("sync_mode", {"wired": True, "confirm": True}, [b"$#330490000100012R\r"]),
    ],
)
async def test_auxiliary_registered_service_and_serialized_wire(
    runtime, clock, operation, fields, expected
):
    hass, co = runtime
    await install(co, name(mode="E"))
    await call(hass, operation, **fields)
    assert writes(co) == expected
    assert co._command_scheduler.recent_records[-1].outcome is CommandOutcome.COMPLETED


async def test_m_wrapping_and_suppressed_query_through_real_service(runtime, clock):
    hass, co = runtime
    await install(co, name(mode="M"))
    await call(hass, "rgb", rgb=[128, 192, 255])
    assert len(writes(co)) == 3 and b"$z" not in writes(co)
    await hass.services.async_call(
        const.DOMAIN,
        "timed_move",
        {"device_id": ["bed"], "motor": "head", "direction": "up", "duration_ms": 200},
        blocking=True,
    )
    assert writes(co)[3:] == [b"$#$KR\r"] * 2 + [b"$#$bR\r"] * 5


async def test_short_up_fallback_and_zero_q_asymmetry(runtime, clock):
    hass, co = runtime
    from custom_components.adjustable_bed.button import ControllerActionButton

    task = asyncio.create_task(
        hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": ["bed"], "control": "bedgear_tilt_down", "duration": 1},
            blocking=True,
        )
    )
    await asyncio.sleep(0.02)
    release = next(
        spec for spec in co.controller.controller_button_specs if spec.key == "bedgear_release"
    )
    await ControllerActionButton(co, release).async_press()
    await task
    assert writes(co) == [b"$Q"] * 4  # Immediate finite pulse, then the three short-up writes.
    co.client.write_gatt_char.reset_mock()
    await hass.services.async_call(
        const.DOMAIN,
        "timed_move",
        {"device_id": ["bed"], "motor": "tilt", "direction": "up", "duration_ms": 100},
        blocking=True,
    )
    assert writes(co) == [b"$P"] + [b"$b"] * 5


async def test_leases_renew_then_expire_and_stale_renewal_after_stop_fails(runtime, clock):
    hass, co = runtime
    first_tick = []
    began = clock.time()
    co.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: first_tick.append(
        round((clock.time() - began) * 1000)
    )

    async def held(generation):
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {
                "device_id": ["bed"],
                "motor": "head",
                "direction": "up",
                "duration_ms": 200,
                "hold_owner": "card",
                "hold_generation": generation,
            },
            blocking=True,
        )

    task = asyncio.create_task(held(1))
    for _ in range(5):
        await asyncio.sleep(0.1)
        await held(1)
    await task
    assert first_tick[0] == 100  # Renewable gestures retain the native first-tick delay.
    assert writes(co).count(b"$K") >= 6 and writes(co).count(b"$b") == 5
    assert co._command_scheduler.recent_records[-1].outcome is CommandOutcome.EXPIRED
    task = asyncio.create_task(held(2))
    await asyncio.sleep(0.15)
    await co.async_stop_command()
    await task
    before = writes(co)
    with pytest.raises(ServiceValidationError, match="ended"):
        await held(2)
    assert writes(co) == before
    assert co._command_scheduler.recent_records[-1].kind is CommandKind.STOP


async def test_old_session_notifications_and_delayed_writes_cannot_reach_replacement(
    runtime, clock
):
    hass, co = runtime
    old = co.controller
    old_link = old._link
    task = asyncio.create_task(call(hass, "rgb", rgb=[255, 255, 255]))
    await asyncio.sleep(0.05)
    replacement = await install(co, name())
    with pytest.raises(ConnectionError, match="session"):
        await task
    old._notification(old_link, old_link.write, bytearray(b"$" + b"0 " * 38 + b"0R\r"))
    assert replacement._rgb is None and old._rgb is None
    assert writes(co) == []


def notification(bed, tokens):
    link = bed._link
    bed._notification(link, link.write, bytearray(b"$" + " ".join(tokens).encode()))
    bed._notification(link, link.write, bytearray(b"R\r"))


async def test_observed_only_projection_and_bind_controls(runtime, clock):
    hass, co = runtime
    bed = co.controller
    assert all(co.controller_state.get(key) is None for key in (RGB, TIMER, ALARM, SYNC, BIND))
    with pytest.raises(ServiceValidationError):
        await call(hass, "toggle_sync")
    for token, expected in [("00065", b"$#000150000000004R\r"), ("00066", b"$#000120000000003R\r")]:
        tokens = ["00000"] * 39
        tokens[18:21], tokens[24], tokens[27], tokens[30] = (
            ["00120", "00030", "00001"],
            "1",
            token,
            "9999999999",
        )
        notification(bed, tokens)
        await call(hass, "toggle_sync")
        assert writes(co)[-1] == expected
        assert bed._rgb == (255, 63, 2) and bed._timer == 65535
    await bed.stop_notify()
    assert bed._rgb is None and bed._bind is None


async def test_alarm_preserves_received_digit_widths_and_save_release_is_explicit(runtime, clock):
    hass, co = runtime
    bed = await install(co, name("E1", mode="E"))
    tokens = ["00000"] * 75
    tokens[11:13], tokens[14] = ["00007", "00030"], "1"
    notification(bed, tokens)
    await call(hass, "alarm", strength=2)
    from custom_components.adjustable_bed.codec.motomotion import decimal_fields

    assert writes(co)[-1] == decimal_fields("000070003000", "0219")
    await call(hass, "save_snore")
    assert writes(co)[-1] == b"$W"


def test_gatt_last_match_all_subscriptions_and_no_invented_property_gate():
    c = client()
    first = c.services[0].characteristics[0]
    second = SimpleNamespace(uuid="FFFFffe10001", handle=9, properties=[])
    c.services.append(SimpleNamespace(uuid="123ffe012", characteristics=[second]))
    link = select_transport(c)
    assert link.write is second and link.notify == (first, second)


@pytest.mark.parametrize("pair", NAMES)
async def test_covers_publish_real_card_hold_metadata_and_use_the_scheduler(runtime, clock, pair):
    from custom_components.adjustable_bed.cover import _cover_entities_for

    hass, co = runtime
    bed = await install(co, name(pair))
    covers = _cover_entities_for(hass, co)
    assert len(covers) == len(bed.profile.axes)
    for cover in covers:
        attrs = cover.extra_state_attributes
        assert cover.capability_attributes["card_section"] == "motors"
        assert attrs["hold_lease_mode"] == "stream"
        assert attrs["hold_release_button_key"] == "bedgear_release"
    first = covers[0]
    first.hass = hass
    first.async_write_ha_state = MagicMock()
    await first.async_open_cover()
    expected = next(
        c.letter for c in bed.profile.controls if c.key == bed.profile.axes[0][0] + "_up"
    )
    assert writes(co) == [("$" + expected).encode()] * 10 + [b"$b"] * 5
    assert co._command_scheduler.recent_records[-1].outcome is CommandOutcome.COMPLETED


async def test_precise_first_tick_and_five_stop_timing_through_cover(runtime, clock):
    from custom_components.adjustable_bed.cover import _cover_entities_for

    hass, co = runtime
    cover = _cover_entities_for(hass, co)[0]
    cover.hass = hass
    cover.async_write_ha_state = MagicMock()
    recorded = []
    began = clock.time()
    co.client.write_gatt_char.side_effect = lambda _char, data, **_kw: recorded.append(
        (round((clock.time() - began) * 1000), bytes(data))
    )
    task = asyncio.create_task(cover.async_open_cover())
    await asyncio.sleep(0.05)
    assert recorded == [(0, b"$K")]
    await task
    assert recorded[0] == (0, b"$K")
    stops = [at for at, data in recorded if data == b"$b"]
    assert stops == [1000, 1030, 1060, 1090, 1120]


async def test_all_target_validation_prevents_partial_setting_writes(runtime, clock):
    hass, co = runtime
    # A second physical target has no RGB gate. Neither target may write.
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Other Bedgear",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:13",
            const.CONF_BED_TYPE: "bedgear",
            const.CONF_BLE_DEVICE_NAME: name(light="B"),
        },
    )
    entry.add_to_hass(hass)
    other = AdjustableBedCoordinator(hass, entry)
    other._client = client()
    other._controller = BedgearController(other, name=name(light="B"))
    await other.controller.start_notify()
    other.async_ensure_connected = AsyncMock(return_value=True)
    try:
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(co, "both"), (other, "both")], []),
            ),
            pytest.raises(ServiceValidationError),
        ):
            await call(hass, "rgb", rgb=[255, 255, 255])
        assert writes(co) == [] and writes(other) == []
    finally:
        await other.async_shutdown()


async def test_two_address_pair_routes_only_the_chosen_physical_side(runtime, clock):
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    hass, co = runtime
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Other Bedgear",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:13",
            const.CONF_BED_TYPE: "bedgear",
            const.CONF_BLE_DEVICE_NAME: name(mode="M"),
        },
    )
    entry.add_to_hass(hass)
    right = AdjustableBedCoordinator(hass, entry)
    right._client = client()
    right._controller = BedgearController(right, name=name(mode="M"))
    await right.controller.start_notify()
    right.async_ensure_connected = AsyncMock(return_value=True)
    right._async_refresh_controller_auth = AsyncMock()
    parent_entry = MockConfigEntry(
        domain=const.DOMAIN, title="Pair", data={"pair_id": "bedgear-pair"}
    )
    parent_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, parent_entry, {"left": co, "right": right})
    try:
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "right")], []),
        ):
            await call(hass, "light_timer", minutes=10)
        assert writes(co) == []
        assert writes(right) == [b"$#003190001000010R\r"]
        assert co.controller._timer is None and right.controller._timer is None
    finally:
        await right.async_shutdown()


async def test_release_offsets_absorb_ble_write_latency(runtime, clock):
    hass, co = runtime
    recorded = []
    began = clock.time()

    async def delayed(_char, data, **_kw):
        recorded.append((round((clock.time() - began) * 1000), bytes(data)))
        await asyncio.sleep(0.007)

    co.client.write_gatt_char.side_effect = delayed
    await co.async_stop_command()
    assert recorded == [(0, b"$b"), (30, b"$b"), (60, b"$b"), (90, b"$b"), (120, b"$b")]
    recorded.clear()
    began = clock.time()
    await co.async_execute_controller_command(lambda bed: bed.hold_control("bedgear_tilt_down", 20))
    assert recorded == [(0, b"$Q"), (20, b"$Q"), (120, b"$Q"), (220, b"$Q")]


async def test_alarm_partial_changes_preserve_the_other_observed_field(runtime, clock):
    hass, co = runtime
    bed = await install(co, name(mode="E"))
    with pytest.raises(ServiceValidationError, match="strength"):
        await call(hass, "alarm", time="08:30")
    tokens = ["00000"] * 75
    tokens[11], tokens[12], tokens[14] = "07", "45", "00001"
    notification(bed, tokens)
    await call(hass, "alarm", time="08:30")
    assert writes(co)[-1] == b"$#083000011800003R\r"
    assert bed._alarm == ("07", "45", "00001")


async def test_reported_rgb_reaches_the_real_sensor_platform(runtime, clock):
    from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor

    hass, co = runtime
    bed = co.controller
    tokens = ["00000"] * 39
    tokens[18:21] = ["00120", "00030", "00001"]
    notification(bed, tokens)
    spec = next(spec for spec in bed.controller_state_sensor_specs if spec.state_key == RGB)
    sensor = AdjustableBedControllerStateSensor(co, spec)
    assert sensor.native_value == "255,63,2"


async def test_settings_stop_fences_later_targets_in_the_registered_batch(runtime, clock):
    hass, co = runtime
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Second Bedgear",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:13",
            const.CONF_BED_TYPE: "bedgear",
            const.CONF_BLE_DEVICE_NAME: name(),
        },
    )
    entry.add_to_hass(hass)
    second = AdjustableBedCoordinator(hass, entry)
    second._client = client()
    second._controller = BedgearController(second, name=name())
    await second.controller.start_notify()
    second.async_ensure_connected = AsyncMock(return_value=True)
    second._async_refresh_controller_auth = AsyncMock()
    reached, resume = asyncio.Event(), asyncio.Event()

    async def pause_first(_char, data, **_kwargs):
        if bytes(data) == b"$Z":
            reached.set()
            await resume.wait()

    co.client.write_gatt_char.side_effect = pause_first
    try:
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(co, "both"), (second, "both")], []),
        ):
            batch = asyncio.create_task(call(hass, "save_memory", recall_on_release=True))
            await reached.wait()
            await second.async_stop_command()
            resume.set()
            await batch
        assert writes(co) == [b"$Z", b"$U"]
        assert writes(second) == [b"$b"] * 5
    finally:
        resume.set()
        await second.async_shutdown()


async def test_finite_move_does_not_backfill_after_a_slow_write(runtime, clock):
    hass, co = runtime
    recorded = []
    began = clock.time()

    async def slow(_char, data, **_kwargs):
        recorded.append((round((clock.time() - began) * 1000), bytes(data)))
        await asyncio.sleep(0.3)

    co.client.write_gatt_char.side_effect = slow
    await hass.services.async_call(
        const.DOMAIN,
        "timed_move",
        {
            "device_id": ["bed"],
            "motor": "head",
            "direction": "up",
            "duration_ms": 200,
        },
        blocking=True,
    )
    assert [row for row in recorded if row[1] == b"$K"] == [(0, b"$K")]
    assert recorded[1] == (300, b"$b")
    assert [data for _at, data in recorded[1:]] == [b"$b"] * 5
    assert co._command_scheduler.recent_records[-1].outcome is CommandOutcome.COMPLETED


@pytest.mark.parametrize("duration_ms", [100, 200])
@pytest.mark.parametrize("memory", [False, True])
async def test_short_finite_holds_survive_event_loop_wake_latency(
    runtime, clock, duration_ms, memory
):
    hass, co = runtime
    bed = co.controller
    original_wait = bed._wait

    async def late_wake(seconds, cancel):
        result = await original_wait(seconds, cancel)
        if seconds > 0:
            await asyncio.sleep(0.001)
        return result

    bed._wait = late_wake
    recorded = []
    began = clock.time()

    async def write(_char, data, **_kwargs):
        recorded.append((round((clock.time() - began) * 1000), bytes(data)))

    co.client.write_gatt_char.side_effect = write
    if memory:
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": ["bed"], "control": "bedgear_memory_1", "duration": duration_ms / 1000},
            blocking=True,
        )
    else:
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {"device_id": ["bed"], "motor": "head", "direction": "up", "duration_ms": duration_ms},
            blocking=True,
        )
    movement = [(at, data) for at, data in recorded if data != b"$b"]
    assert [data for _at, data in movement] == [b"$U" if memory else b"$K"] * (duration_ms // 100)
    assert movement[0][0] == 0
    assert all(at < duration_ms for at, _data in movement)


async def test_expired_finite_hold_in_ble_lane_sends_only_captured_stop(runtime, clock):
    _hass, co = runtime
    bed = co.controller
    await bed.ble_lock.acquire()
    task = asyncio.create_task(bed.hold_control("bedgear_head_up", 100))
    await asyncio.sleep(0.2)
    bed.ble_lock.release()
    await task
    assert writes(co) == [b"$b"] * 5


async def test_panel_e_save_has_no_release_recall_and_snore_remains_held(runtime, clock):
    hass, co = runtime
    await install(co, name("E1"))
    with pytest.raises(ServiceValidationError, match="release recall"):
        await call(hass, "save_snore", recall_on_release=True)
    assert writes(co) == []
    await call(hass, "save_snore")
    assert writes(co) == [b"$W"]
    await hass.services.async_call(
        const.DOMAIN,
        "hold_control",
        {
            "device_id": ["bed"],
            "control": "bedgear_preset_anti_snore",
            "duration": 0.1,
        },
        blocking=True,
    )
    assert writes(co) == [b"$W", b"$R"]


def test_bedgear_utf16_discovery_without_an_existing_match():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from custom_components.adjustable_bed.profiles.bedgear import eligible
    from tests.test_detection import _make_service_info

    selected = "🙂HHC00001D00X"
    assert eligible(selected)
    detected = detect_bed_type_detailed(_make_service_info(name=selected))
    assert detected.bed_type == "bedgear" and detected.confidence == 0.3
    assert "name:bedgear_app_candidate" in detected.signals
    existing = detect_bed_type_detailed(_make_service_info(name=name()))
    assert existing.bed_type == "motosleep" and "bedgear" in existing.ambiguous_types
    excluded = detect_bed_type_detailed(_make_service_info(name="HHCmouse01D00X"))
    assert excluded.bed_type is None and any(s.startswith("excluded:") for s in excluded.signals)
    assert "name:bedgear_app_candidate" not in excluded.signals
