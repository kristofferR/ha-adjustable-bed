"""Row083's frozen bytes, complete remote gates and HA execution boundaries."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.bed_traits import bed_traits
from custom_components.adjustable_bed.beds.comfort_enhancement3 import controller as apex
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles.comfort_enhancement3 import (
    CHOICES,
    CODE_INDEX,
    PROFILES,
    REMOTE_CODE,
    REMOTES,
    resolve,
)
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.hold_lease_wire import virtual_clock
from tests.test_controller_contract import _FactoryCoordinator

FIXTURES = Path(__file__).parent / "fixtures/comfort_enhancement3"
CONTROLS = json.loads((FIXTURES / "controls.json").read_text())
SCHEDULE = json.loads((FIXTURES / "schedule.json").read_text())
VARIANTS = json.loads((FIXTURES / "profiles.json").read_text())
ACTIONS = {
    "m1": 0x1000,
    "m2": 0x2000,
    "stopCommand": 0,
    "TV": 0x3000,
    "massageStop": 0x400,
    "QS": 0x8000,
    "m3Down": 0x20,
    "m3Up": 0x10,
    "storeMemoryPosition": 0x10000,
    "zeroGravity": 0x4000,
    "ubl": 0x20000,
    "massageFootPlus": 0x400000,
    "massageHeadPlus": 0x800,
    "massageWave3": 0x80000000,
    "massageStopCommand": 0,
    "tilt": 0x90,
    "flat": 0x10000000,
    "m4Down": 0x80,
    "m3m4Down": 0xA0,
    "m4Up": 0x40,
    "m3m4Up": 0x50,
    "m1m2Down": 10,
    "m1m2Up": 5,
    "footDown": 8,
    "footUp": 4,
    "headDown": 2,
    "headUp": 1,
    "duration-cycle": 0x02000000,
}


@pytest.mark.parametrize("row", CONTROLS + SCHEDULE, ids=lambda r: r["id"])
def test_all_29_literal_and_8_dynamic_vectors(row):
    if row["protocol"] == "P1":
        word = ACTIONS["duration-cycle" if row["id"] == "duration-cycle" else row["action"]]
        assert word == row["inputs"]["command_mask"]
        actual = codec.frame(word)
    else:
        inputs = row["inputs"]
        actual = codec.schedule_step(
            inputs["slot"],
            inputs["step"],
            inputs["delay_ticks"],
            inputs.get("command", inputs.get("command_mask")),
            inputs["duration"],
        )
    assert actual == bytes.fromhex(row["expected_bytes"])


@pytest.mark.parametrize("index", range(15))
async def test_complete_profiles_codes_gates_factory_and_restore(index):
    expected, remote, profile = VARIANTS[index], REMOTES[index], PROFILES[f"apex_{index}"]
    assert expected["selector"] == index
    assert remote.codes == tuple(expected["codes"])
    for code in remote.codes:
        assert CODE_INDEX[code] == resolve("15", code) == index
        coordinator = _FactoryCoordinator()
        coordinator.entry.data[REMOTE_CODE] = code
        controller = await create_controller(
            coordinator, const.BED_TYPE_COMFORT_ENHANCEMENT3, "15", None
        )
        assert controller.profile is profile
    coordinator = _FactoryCoordinator()
    controller = await create_controller(
        coordinator, const.BED_TYPE_COMFORT_ENHANCEMENT3, profile.key, None
    )
    assert controller.profile is profile
    for property, field in (
        ("supports_preset_flat", "flat_preset"),
        ("supports_preset_zero_g", "ZG"),
        ("supports_preset_tv", "TV"),
        ("supports_lights", "under_bed_light"),
        ("supports_massage", "massage"),
    ):
        assert getattr(controller, property) is expected[field]
    assert not controller.supports_preset_anti_snore
    assert ("qs" in profile.keys) is (expected["QS"] or expected["Zzz_alias_QS"])
    assert controller.memory_slot_count == (2 if expected["M2"] else 1)
    assert remote.wake_presets == tuple(expected["wake_up_memory_options"])
    assert remote.wake_massage is expected["wake_up_massage"]
    assert bool("tilt" in profile.keys) is expected["tilt_preset"]
    assert not controller.supports_single_address_pairing
    assert not controller.supports_position_feedback
    assert not controller.supports_discrete_light_control
    assert not controller.execution.concurrent
    assert controller.execution.hold == "stream"
    assert {s.scheduler_resource for s in controller.motor_control_specs} == {"*"}
    assert {s.key for s in controller.motor_control_specs} == {"back", "legs"}
    assert len(controller.remote.groups) == len(expected["top_control_groups"]) - 2
    for preset in ("None", "M1", "M2", "Zero Gravity", "TV", "QS"):
        if preset in remote.wake_presets:
            assert apex.wake_frames(index, 1, 0, preset=preset)
        else:
            with pytest.raises(ValueError):
                apex.wake_frames(index, 1, 0, preset=preset)
    for effect, enabled in (("massage", remote.wake_massage), ("light", remote.light)):
        if enabled:
            assert apex.wake_frames(index, 1, 0, **{effect: True})
        else:
            with pytest.raises(ValueError):
                apex.wake_frames(index, 1, 0, **{effect: True})
    setup = setup_profile_for({const.CONF_BED_TYPE: const.BED_TYPE_COMFORT_ENHANCEMENT3})
    data = {const.CONF_PROTOCOL_VARIANT: profile.key}
    assert setup.validate is not None
    assert setup.validate(data) == {}
    assert setup.settled(data)[const.CONF_HAS_MASSAGE] is remote.massage


def test_unknown_manual_sentinels_and_exact_case():
    assert len(REMOTES) == 15 and len(CODE_INDEX) == 24 and len(CHOICES) == 15
    for variant in ("-1", "-100", "apex_15", "unknown"):
        with pytest.raises(ValueError):
            resolve(variant)
    for code in ("unknown", "pmt-5024", " PMT-5024", "PMT-5024 ", ""):
        with pytest.raises(ValueError):
            resolve("15", code)
    setup = setup_profile_for({const.CONF_BED_TYPE: const.BED_TYPE_COMFORT_ENHANCEMENT3})
    assert setup.validate is not None
    assert setup.validate({}) == {const.CONF_PROTOCOL_VARIANT: "apex_remote_required"}
    assert setup.validate({const.CONF_PROTOCOL_VARIANT: "15", REMOTE_CODE: "unknown"}) == {
        REMOTE_CODE: "apex_remote_code"
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("slot", -1),
        ("slot", 100),
        ("step", 100),
        ("step", True),
        ("delay_ticks", -1),
        ("delay_ticks", 2**32),
        ("command", 2**32),
        ("duration", 256),
        ("duration", -1),
    ],
)
def test_formatter_rejects_unsafe_domain_not_firmware_capacity(field, value):
    inputs = {"slot": 0, "step": 0, "delay_ticks": 0, "command": 0, "duration": 0}
    inputs[field] = value
    with pytest.raises(ValueError):
        codec.schedule_step(**inputs)


def test_delay_truncation_date_normalization_and_full_schedule():
    now = datetime(2026, 12, 31, 23, 59, 59, 750000, tzinfo=UTC)
    assert apex.delay_ticks(now - timedelta(microseconds=999999), now) == 0
    assert apex.delay_ticks(now - timedelta(seconds=1), now) == -10
    assert apex.delay_ticks(now + timedelta(seconds=60, microseconds=999999), now) == 600
    assert apex.selected_time(now, 0, 0, True) == datetime(2027, 1, 1, tzinfo=UTC)
    assert apex.selected_time(now, 0, 0, False) == datetime(2026, 12, 31, tzinfo=UTC)
    frames = apex.wake_frames(3, 1, 600, massage=True, light=True, preset="M1")
    assert [f.hex() for f in frames] == [
        "0b0d0100000002580000000005",
        "0b0d0101000000000000000005",
        "0b0d0102000000000200000000",
        "0b0d0103000000000000000005",
        "0b0d0104000000000000080000",
        "0b0d0105000000000000000005",
        "0b0d0106000000000002000000",
        "0b0d0107000000000000000005",
        "0b0d0108000000000000100005",
    ]
    maximal = apex.wake_frames(
        3, 9, 10, massage=True, duration=30, intensity=3, kind="both", light=True, preset="M2"
    )
    assert len(maximal) == 23 and maximal[10][3] == 0x10
    assert maximal[-1].hex() == "0b0d0922000000000000200005"
    assert len(apex.wake_frames(3, 2, 10, massage=True, duration=30, kind="wave")) == 9
    with pytest.raises(ValueError):
        apex.wake_frames(3, 1, 0, preset="ZeroGravity")


def char(uuid, properties):
    return SimpleNamespace(uuid=uuid, properties=properties, handle=1, descriptors=[])


@pytest.fixture
def bed():
    client = MagicMock(is_connected=True)
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.read_gatt_char = AsyncMock(return_value=b"HE150")
    client.services = [
        SimpleNamespace(
            uuid=codec.SERVICE_UUID,
            characteristics=[char(codec.WRITE_UUID, ["write"]), char(apex.NOTIFY_UUID, ["notify"])],
        ),
        SimpleNamespace(
            uuid="00001801-0000-1000-8000-00805f9b34fb",
            characteristics=[char(apex.SERVICE_CHANGED, ["indicate"])],
        ),
        SimpleNamespace(
            uuid="0000180a-0000-1000-8000-00805f9b34fb",
            characteristics=[char(apex.MODEL_UUID, ["read"]), char(apex.FIRMWARE_UUID, ["read"])],
        ),
    ]
    coordinator = MagicMock(
        client=client, motor_pulse_count=3, motor_pulse_delay_ms=17, motor_count=4
    )
    coordinator.cancel_command = asyncio.Event()
    controller = apex.ComfortEnhancement3Controller(coordinator, 3)
    controller.static_traits = bed_traits(const.BED_TYPE_COMFORT_ENHANCEMENT3)
    return controller, coordinator, client


def frames(client):
    return [call.args[1].hex() for call in client.write_gatt_char.await_args_list]


async def test_normal_pulses_safe_recall_and_relative_massage(bed):
    c, coordinator, client = bed
    await c.async_discover_capabilities()
    with virtual_clock():
        await c.move_back_up()
        assert frames(client) == ["040200000001"] * 3 + ["040200000000"] * 2
        client.write_gatt_char.reset_mock()
        await c.preset_zero_g()
        assert frames(client) == ["040200004000", "040200000000", "040200000000"]
        client.write_gatt_char.reset_mock()
        await c.massage_step("massage_duration")
        await c.massage_head_toggle()
        await c.massage_foot_toggle()
        await c.massage_toggle()
        assert frames(client) == [
            "040200000000",
            "040202000000",
            "040200000000",
            "040200000800",
            "040200000000",
            "040200400000",
            "040200000000",
            "040280000000",
        ]
        client.write_gatt_char.reset_mock()
        coordinator.cancel_command.set()
        await c.massage_off()
        assert frames(client) == ["040200000400", "0b0d0000000000000000040005"] * 2


@pytest.mark.parametrize("slot", [1, 2])
async def test_save_has_40_setters_then_3_recalls(bed, slot):
    c, _, client = bed
    await c.async_discover_capabilities()
    with virtual_clock() as clock:
        await c.program_memory(slot)
        assert clock.elapsed == pytest.approx(4.3)
    assert frames(client) == ["040200010000"] * 40 + [f"04020000{slot}000"] * 3


async def test_cancellation_and_failed_first_stop_complete_cleanup(bed):
    c, coordinator, client = bed
    await c.async_discover_capabilities()
    with virtual_clock():
        coordinator.cancel_command.set()
        client.write_gatt_char.side_effect = [BleakError("first STOP"), None]
        with pytest.raises(BleakError):
            await c.move_back_up()
    assert frames(client) == ["040200000000"] * 2


async def test_lifecycle_optional_info_notify_retry_no_telemetry_or_startup(bed):
    c, coordinator, client = bed
    await c.async_discover_capabilities()
    session = SimpleNamespace(async_start_notify=c.start_notify, store_device_info=MagicMock())
    client.start_notify.side_effect = [None, BleakError("busy"), None]
    with virtual_clock():
        await c.async_on_connect(session)
    assert [a.args[0].uuid for a in client.start_notify.await_args_list] == [
        apex.SERVICE_CHANGED,
        apex.NOTIFY_UUID,
        apex.NOTIFY_UUID,
    ]
    assert not frames(client)
    assert client.read_gatt_char.await_count == 2
    assert any(
        update.key == apex.FIRMWARE and update.value == "V.HE150"
        for call in coordinator.handle_controller_state_updates.call_args_list
        for update in call.args
    )
    receive = client.start_notify.call_args.args[1]
    raw = MagicMock()
    c.set_raw_notify_callback(raw)
    for data in (b"", b"\xa5\x0b", b"\xa5\x0b\x0e", b"\0\0\0", b"\xa5\x0b\x0e\xff"):
        receive(client.services[0].characteristics[1], bytearray(data))
    assert raw.call_count == 5
    assert c.position_number_specs == ()
    await c.stop_notify()
    raw.reset_mock()
    receive(client.services[0].characteristics[1], bytearray.fromhex("a50b0e"))
    raw.assert_not_called()
    assert client.stop_notify.await_count == 2
    client.start_notify.side_effect = None
    client.services = client.services[:1]  # DeviceInfo and ServiceChanged optional.
    await c.async_discover_capabilities()
    await c.start_notify()


async def test_captured_release_never_writes_new_session(bed, monkeypatch):
    c, coordinator, client = bed
    await c.async_discover_capabilities()
    old = c._link
    c.on_disconnect()
    replacement = MagicMock(is_connected=True, services=client.services)
    replacement.write_gatt_char = AsyncMock()
    coordinator.client = replacement
    await c.async_discover_capabilities()
    with virtual_clock(), pytest.raises(ConnectionError):
        await c._release(old)
    replacement.write_gatt_char.assert_not_awaited()


async def test_wakeup_set_edit_delete_restore_and_due_fence(bed, monkeypatch):
    c, coordinator, client = bed
    await c.async_discover_capabilities()
    now = datetime(2026, 11, 12, 12, tzinfo=UTC)
    monkeypatch.setattr(dt_util, "now", lambda: now)
    target = now + timedelta(seconds=60)
    with virtual_clock():
        await c.set_wakeup(10, target, massage=True, preset="M1")
        assert frames(client)[0] == "0b0d1000000000000000000000"
        assert frames(client)[1] == "0b0d1000000002580000000005"
        original = c._timers["wake:10"]
        state = c.persisted_app_state
        restored = apex.ComfortEnhancement3Controller(coordinator, 3)
        restored.restore_persisted_app_state(state)
        assert restored.persisted_app_state == state
        await c.delete_wakeup(10)
        await asyncio.sleep(0)
        assert original.cancelled()
        assert c.persisted_app_state["wakes"] == {}
        assert frames(client)[-1] == "0b0d1000000000000000000000"
        c.on_disconnect()
        assert not c._timers


@pytest.mark.usefixtures(
    "mock_bluetooth_api", "mock_establish_connection", "mock_async_ble_device_from_address"
)
async def test_real_coordinator_cover_timed_move_and_card_lease(hass, mock_bleak_client, bed):
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
    from custom_components.adjustable_bed.services import async_register_services

    c, _, client = bed
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        version=5,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            const.CONF_BED_TYPE: const.BED_TYPE_COMFORT_ENHANCEMENT3,
            const.CONF_PROTOCOL_VARIANT: "apex_3",
            const.CONF_MOTOR_PULSE_COUNT: 3,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
            const.CONF_IDLE_DISCONNECT_SECONDS: 0,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._max_retries = 1
    mock_bleak_client.services.__iter__ = lambda _: iter(client.services[:1])
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    mock_bleak_client.write_gatt_char = AsyncMock()
    assert await coordinator.async_connect()
    controller = coordinator.controller
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, const.SIDE_BOTH)], []),
    ):
        # Use the actual cover call with its configured pulse count.
        cover = AdjustableBedCover(
            coordinator, _build_cover_description(controller.motor_control_specs[0])
        )
        cover.hass = hass
        cover.async_write_ha_state = MagicMock()
        with virtual_clock():
            await cover.async_open_cover()
        assert frames(mock_bleak_client) == ["040200000001"] * 3 + ["040200000000"] * 2
        mock_bleak_client.write_gatt_char.reset_mock()
        with virtual_clock():
            await hass.services.async_call(
                const.DOMAIN,
                "timed_move",
                {"device_id": "bed", "motor": "back", "direction": "up", "duration_ms": 350},
                blocking=True,
            )
        assert frames(mock_bleak_client) == ["040200000001"] * 4 + ["040200000000"] * 2
        mock_bleak_client.write_gatt_char.reset_mock()
        with virtual_clock():
            await hass.services.async_call(
                const.DOMAIN,
                "timed_move",
                {
                    "device_id": "bed",
                    "motor": "back",
                    "direction": "up",
                    "duration_ms": 750,
                    "hold_owner": "card",
                    "hold_generation": 1,
                },
                blocking=True,
            )
        held = frames(mock_bleak_client)
        assert len([f for f in held if f == "040200000001"]) >= 7
        assert held[-2:] == ["040200000000"] * 2
        mock_bleak_client.write_gatt_char.reset_mock()
        with virtual_clock():
            gesture = asyncio.create_task(
                hass.services.async_call(
                    const.DOMAIN,
                    "timed_move",
                    {
                        "device_id": "bed",
                        "motor": "back",
                        "direction": "up",
                        "duration_ms": 5000,
                        "hold_owner": "card",
                        "hold_generation": 2,
                    },
                    blocking=True,
                )
            )
            await asyncio.sleep(0.25)
            await hass.services.async_call(
                const.DOMAIN, "stop_all", {"device_id": "bed"}, blocking=True
            )
            await gesture
            assert "040200000001" in frames(mock_bleak_client)
            assert frames(mock_bleak_client)[-2:] == ["040200000000"] * 2
            mock_bleak_client.write_gatt_char.reset_mock()
            await hass.services.async_call(
                const.DOMAIN,
                "timed_move",
                {
                    "device_id": "bed",
                    "motor": "legs",
                    "direction": "down",
                    "duration_ms": 350,
                },
                blocking=True,
            )
            await asyncio.sleep(0.5)
            assert frames(mock_bleak_client) == ["040200000008"] * 4 + ["040200000000"] * 2
    await coordinator.async_disconnect()


async def test_service_all_target_preflight_and_profile12_wakeup(hass, bed):
    from custom_components.adjustable_bed.services import async_register_services
    from tests.test_generic_services import select, target

    c, _, _ = bed
    await async_register_services(hass)
    first = target(const.BED_TYPE_COMFORT_ENHANCEMENT3, family=apex.ComfortEnhancement3Controller)
    second = target(const.BED_TYPE_COMFORT_ENHANCEMENT3, family=apex.ComfortEnhancement3Controller)
    first[1].validate_wakeup = MagicMock()
    second[1].validate_wakeup = MagicMock(side_effect=ValueError("unsupported effect"))
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets") as resolved:
        select(resolved, first, second)
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                const.DOMAIN,
                "comfort_enhancement3_set_wakeup",
                {"device_id": ["a", "b"], "slot": 10, "time": "23:59", "massage": True},
                blocking=True,
            )
    first[0].async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize("index", range(15))
async def test_actual_config_flow_requires_remote_and_canonicalizes_manual_code(hass, index):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import form_fields

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._verification_possible = lambda: False
    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        const.CONF_BED_TYPE: const.BED_TYPE_COMFORT_ENHANCEMENT3,
    }
    flow._final_settings_pending = True
    result = await flow._async_app_setup_step(data, pairing_step="manual_pairing")
    assert result["step_id"] == "profile_questions"
    assert const.CONF_PROTOCOL_VARIANT in {m.schema for m in form_fields(result["data_schema"])}
    result = await flow.async_step_profile_questions(
        {const.CONF_PROTOCOL_VARIANT: "15", REMOTE_CODE: "unknown"}
    )
    assert result["errors"] == {REMOTE_CODE: "apex_remote_code"}
    result = await flow.async_step_profile_questions(
        {const.CONF_PROTOCOL_VARIANT: "15", REMOTE_CODE: REMOTES[index].codes[0]}
    )
    assert result["step_id"] == "finish_settings"
    settled = flow._manual_data
    assert settled[const.CONF_PROTOCOL_VARIANT] == f"apex_{index}"
    assert settled[const.CONF_HAS_MASSAGE] is REMOTES[index].massage


@pytest.mark.parametrize("invalidate", ["none", "edit", "disconnect"])
async def test_due_callback_has_real_bed_effect_and_stale_fences(
    hass, bed, monkeypatch, invalidate
):
    c, coordinator, client = bed
    coordinator.hass = hass
    await c.async_discover_capabilities()

    async def execute(operation, *, run_if, **_kwargs):
        if invalidate == "disconnect":
            c.on_disconnect()
        elif invalidate == "edit":
            c._cancel_timer("wake:1")
        if run_if():
            await operation(c)

    coordinator.async_execute_controller_query = AsyncMock(side_effect=execute)
    now = datetime(2026, 11, 12, 12, tzinfo=UTC)
    monkeypatch.setattr(dt_util, "now", lambda: now)
    with virtual_clock():
        c._arm("wake:1", now, c._link, {"massage": True, "duration": 10})
        # The actual call_later callback enqueues the real HA operation.
        await asyncio.sleep(0.2)
        await hass.async_block_till_done()
        assert frames(client) == (
            ["040200000400", "0b0d0000000000000000040005"] * 2 if invalidate == "none" else []
        )
        if invalidate == "none":
            assert c._massage_end == (now + timedelta(minutes=10)).isoformat()
        c.on_disconnect()


def test_repaired_callback_fixtures_are_frozen_counterexamples():
    repair = json.loads((FIXTURES / "repairs.json").read_text())
    assert len(repair["system_literal_map"]) == 19 and "isTilt" not in repair["system_literal_map"]
    assert repair["favorites_literal_map"]["isZg"] == "13"
    cases = repair["cases"]
    assert len(cases) == 3
    assert cases[0]["expected_admission"] == [True, False, False, True]
    assert cases[1]["expected_press_admission"] == [True, False]


async def test_cancelled_wakeup_edit_deletes_partial_program_and_host_state(bed, monkeypatch):
    c, coordinator, client = bed
    await c.async_discover_capabilities()
    now = datetime(2026, 11, 12, 12, tzinfo=UTC)
    monkeypatch.setattr(dt_util, "now", lambda: now)

    async def cancel_last(_char, data, **_kwargs):
        if data == codec.schedule_step(1, 2, 0, 0x1000, 5):
            coordinator.cancel_command.set()

    client.write_gatt_char.side_effect = cancel_last
    await c.set_wakeup(1, now + timedelta(minutes=1), preset="M1")
    assert frames(client)[-1] == "0b0d0100000000000000000000"
    assert not c._wakes and not c._timers


def test_elapsed_delay_uses_instants_across_clock_change():
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Europe/Oslo")
    now = datetime(2027, 3, 28, 1, 30, tzinfo=zone)
    selected = apex.selected_time(now, 2, 30, False)
    assert selected.hour == 3
    assert apex.delay_ticks(selected, now) == 36000


async def test_two_address_card_release_stays_on_original_side(hass):
    from contextlib import ExitStack

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.services import async_register_services

    children, clients = {}, {}
    with ExitStack() as patches:
        for side, suffix, index in (("left", "01", 3), ("right", "02", 6)):
            entry = MockConfigEntry(
                domain=const.DOMAIN,
                data={
                    CONF_ADDRESS: f"AA:BB:CC:DD:EE:{suffix}",
                    const.CONF_BED_TYPE: const.BED_TYPE_COMFORT_ENHANCEMENT3,
                    const.CONF_PROTOCOL_VARIANT: f"apex_{index}",
                    const.CONF_MOTOR_PULSE_COUNT: 3,
                    const.CONF_DISABLE_ANGLE_SENSING: True,
                    const.CONF_DISCONNECT_AFTER_COMMAND: False,
                    const.CONF_IDLE_DISCONNECT_SECONDS: 0,
                },
            )
            entry.add_to_hass(hass)
            child = AdjustableBedCoordinator(hass, entry)
            client = MagicMock(is_connected=True)
            client.services = [
                SimpleNamespace(
                    uuid=codec.SERVICE_UUID,
                    characteristics=[
                        char(codec.WRITE_UUID, ["write"]),
                        char(apex.NOTIFY_UUID, ["notify"]),
                    ],
                )
            ]
            client.write_gatt_char, client.stop_notify = AsyncMock(), AsyncMock()
            child._client = client
            child._controller = apex.ComfortEnhancement3Controller(child, index)
            await child._controller.async_discover_capabilities()
            patches.enter_context(
                patch.object(child, "async_ensure_connected", AsyncMock(return_value=True))
            )
            patches.enter_context(
                patch.object(child, "_async_refresh_controller_auth", AsyncMock())
            )
            children[side], clients[side] = child, client
        pair_entry = MockConfigEntry(domain=const.DOMAIN, data={const.CONF_PAIR_ID: "unit083"})
        paired = PairedBedCoordinator(hass, pair_entry, children)
        patches.enter_context(
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                side_effect=lambda _hass, _ids, side=None: ([(paired, side or "both")], []),
            )
        )
        await async_register_services(hass)
        with virtual_clock():
            held = asyncio.create_task(
                hass.services.async_call(
                    const.DOMAIN,
                    "timed_move",
                    {
                        "device_id": "pair",
                        "side": "left",
                        "motor": "back",
                        "direction": "up",
                        "duration_ms": 5000,
                        "hold_owner": "card",
                        "hold_generation": 1,
                    },
                    blocking=True,
                )
            )
            await asyncio.sleep(0.25)
            await hass.services.async_call(
                const.DOMAIN,
                "timed_move",
                {
                    "device_id": "pair",
                    "side": "right",
                    "motor": "legs",
                    "direction": "down",
                    "duration_ms": 350,
                },
                blocking=True,
            )
            await hass.services.async_call(
                const.DOMAIN, "stop_all", {"device_id": "pair", "side": "left"}, blocking=True
            )
            await held
            assert frames(clients["left"])[-2:] == ["040200000000"] * 2
            assert "040200000008" not in frames(clients["left"])
            assert frames(clients["right"]) == ["040200000008"] * 4 + ["040200000000"] * 2
        for child in children.values():
            child._controller.on_disconnect()


async def test_configure_manual_code_preserves_profile_identity_and_owned_gates(hass):
    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.profile_id import resolve_profile_id, with_profile_ids
    entry = MockConfigEntry(domain=const.DOMAIN, version=5, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", const.CONF_BED_TYPE: const.BED_TYPE_COMFORT_ENHANCEMENT3,
        const.CONF_PROTOCOL_VARIANT: "apex_3", const.CONF_HAS_MASSAGE: True,
        const.CONF_MOTOR_COUNT: 2, const.CONF_DISABLE_ANGLE_SENSING: True})
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    result = await flow._async_options_form({const.CONF_PROTOCOL_VARIANT: "15", REMOTE_CODE: "PMT-5020"}, step_id="settings")
    assert not result.get("errors")
    assert entry.data[const.CONF_PROTOCOL_VARIANT] == "apex_12"
    assert not entry.data[const.CONF_HAS_MASSAGE]
    saved = with_profile_ids(entry.data)  # Entry setup refreshes ids on the options reload.
    assert saved[const.CONF_PROFILE_ID] == resolve_profile_id(saved) == "comfort_enhancement3:apex_12"


async def test_batch_massage_honors_stop_on_later_target(hass):
    from contextlib import ExitStack

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.services import async_register_services

    children, clients = [], []
    entered, release = asyncio.Event(), asyncio.Event()
    with ExitStack() as patches:
        for suffix in ("31", "32"):
            entry = MockConfigEntry(domain=const.DOMAIN, data={
                CONF_ADDRESS: f"AA:BB:CC:DD:EE:{suffix}",
                const.CONF_BED_TYPE: const.BED_TYPE_COMFORT_ENHANCEMENT3,
                const.CONF_PROTOCOL_VARIANT: "apex_3", const.CONF_HAS_MASSAGE: True,
                const.CONF_DISABLE_ANGLE_SENSING: True,
                const.CONF_DISCONNECT_AFTER_COMMAND: False, const.CONF_IDLE_DISCONNECT_SECONDS: 0,
            })
            entry.add_to_hass(hass)
            child = AdjustableBedCoordinator(hass, entry)
            client = MagicMock(is_connected=True)
            client.services = [SimpleNamespace(uuid=codec.SERVICE_UUID, characteristics=[
                char(codec.WRITE_UUID, ["write"]), char(apex.NOTIFY_UUID, ["notify"]),
            ])]
            client.write_gatt_char, client.stop_notify = AsyncMock(), AsyncMock()
            child._client = client
            child._controller = apex.ComfortEnhancement3Controller(child, 3)
            await child._controller.async_discover_capabilities()
            patches.enter_context(patch.object(child, "async_ensure_connected", AsyncMock(return_value=True)))
            patches.enter_context(patch.object(child, "_async_refresh_controller_auth", AsyncMock()))
            children.append(child)
            clients.append(client)
        async def first_write(*_args, **_kwargs):
            entered.set()
            await release.wait()
        clients[0].write_gatt_char.side_effect = first_write
        patches.enter_context(patch("custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(child, const.SIDE_BOTH) for child in children], [])))
        await async_register_services(hass)
        with virtual_clock():
            batch = asyncio.create_task(hass.services.async_call(const.DOMAIN,
                "comfort_enhancement3_start_massage", {"device_id": ["first", "later"]}, blocking=True))
            await entered.wait()
            await children[1].async_stop_command()
            assert children[1].stop_epoch == 1
            release.set()
            await batch
            assert frames(clients[0]) == ["040200000000", "040202000000", "040200000000", "040200000800"]
            assert frames(clients[1]) == ["040200000000"] * 2
            for child in children:
                child._controller.on_disconnect()


async def test_wakeup_retires_previous_massage_countdown(hass, bed, monkeypatch):
    c, coordinator, client = bed
    coordinator.hass = hass
    await c.async_discover_capabilities()
    now = datetime(2026, 11, 12, 12, tzinfo=UTC)
    monkeypatch.setattr(dt_util, "now", lambda: now)
    async def execute(operation, *, run_if, **_kwargs):
        if run_if():
            await operation(c)
    coordinator.async_execute_controller_query = AsyncMock(side_effect=execute)
    with virtual_clock():
        previous_end = now + timedelta(seconds=60)
        c._massage_end = previous_end.isoformat()
        c._arm("massage", previous_end, c._link)
        previous_timer = c._timers["massage"]
        c._arm("wake:1", now, c._link, {"massage": False})
        await asyncio.sleep(0.2)
        await hass.async_block_till_done()
        assert c._massage_end is None
        assert "massage" not in c._timers
        assert previous_timer.cancelled()
        await c.massage_head_toggle()
        await asyncio.sleep(120)
        await hass.async_block_till_done()
        assert frames(client) == ["040200000400", "0b0d0000000000000000040005"] * 2 + ["040200000000", "040200000800"]
        c.on_disconnect()
