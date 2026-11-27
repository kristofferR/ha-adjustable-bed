"""Frozen Hestia vectors and actual entity/service/session boundaries."""

from __future__ import annotations

import asyncio
import itertools
import json
from datetime import datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.hestia.controller import HestiaController
from custom_components.adjustable_bed.beds.hestia.state import ALARM, MASSAGE
from custom_components.adjustable_bed.codec import keeson
from custom_components.adjustable_bed.const import KEESON_BASE_NOTIFY_CHAR_UUID as NOTIFY
from custom_components.adjustable_bed.const import KEESON_BASE_WRITE_CHAR_UUID as WRITE
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.profiles import hestia as app
from custom_components.adjustable_bed.profiles.keeson import encode
from scripts.wire_snapshot import FakeClock, virtual_time
from tests.test_controller_contract import _FactoryCoordinator

VECTORS = json.loads((Path(__file__).parent / "fixtures/hestia_vectors.json").read_text())


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["id"])
def test_existing_codec_matches_frozen_literal(vector):
    fields = vector["inputs"]
    if "keycode_hex" in fields:
        actual = keeson.frame(int(fields["keycode_hex"], 16), order="big")
    else:
        now = datetime(2026, 1, 1, fields["hc"], fields["mc"], fields["sc"])
        target = None if fields["hs"] == 255 else time(fields["hs"], fields["ms"])
        actual = keeson.ea_clock(
            now, target, tuple(fields[k] for k in ("intensity", "wave", "timer", "memory"))
        )
    assert actual.hex() == vector["expected_bytes"]


def test_all_profile_keys_are_exactly_the_frozen_keys():
    frozen = {bytes.fromhex(v["expected_bytes"]) for v in VECTORS if v["id"].startswith("K")}
    assert {encode(app.PROFILE, word) for word in app.words()} == frozen


def test_alarm_formula_all_288_settings_and_disable():
    # Independent field mapping from the accepted report, not the encoder.
    now = datetime(2026, 1, 1, 12, 34, 56)
    for enhancement, intensity, wave, timer, memory in itertools.product(
        (False, True), range(4), range(4), (10, 20, 30), ("none", "memory_1", "memory_2")
    ):
        payload = [
            234,
            254,
            22,
            56,
            34,
            12,
            45,
            7,
            16 + intensity if enhancement and intensity else 255,
            32 + wave if enhancement else 255,
            {10: 48, 20: 49, 30: 50}[timer] if enhancement else 255,
            {"none": 255, "memory_1": 4, "memory_2": 6}[memory],
        ]
        expected = bytes([*payload, ~sum(payload) & 255])
        assert (
            app.alarm(
                now,
                time(7, 45),
                enhancement=enhancement,
                intensity=intensity,
                wave=wave,
                timer=timer,
                memory=memory,
            )
            == expected
        )
        assert app.alarm(
            now,
            None,
            enhancement=enhancement,
            intensity=intensity,
            wave=wave,
            timer=timer,
            memory=memory,
        ) == bytes.fromhex("eafe1638220cffffffffffffa1")


def make_bed(*, properties=("write",)):
    coordinator = _FactoryCoordinator()
    coordinator.record_command_trace = MagicMock()
    write = SimpleNamespace(uuid=WRITE, properties=properties, handle=1)
    notify = SimpleNamespace(uuid=NOTIFY, properties=("notify",), handle=2)
    client = SimpleNamespace(
        is_connected=True,
        services=[SimpleNamespace(uuid="unrelated-service", characteristics=[write, notify])],
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )
    coordinator.client = client
    bed = HestiaController(coordinator)
    coordinator.controller = bed
    return coordinator, client, bed


def packets(client):
    return [bytes(call.args[1]) for call in client.write_gatt_char.call_args_list]


async def connected():
    coordinator, client, bed = make_bed()
    await bed.async_discover_capabilities()
    return coordinator, client, bed


async def test_manual_factory_and_no_automatic_name_guess():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from custom_components.adjustable_bed.setup_questions import SETUP_PROFILES
    from tests.test_detection import _make_service_info

    coordinator, client, _ = make_bed()
    bed = await create_controller(coordinator, "hestia_motion", "auto", client)
    assert isinstance(bed, HestiaController)
    assert SETUP_PROFILES["hestia_motion"].owns["motor_count"] == 2
    result = detect_bed_type_detailed(_make_service_info(name="Hestia Motion", service_uuids=[]))
    assert result.bed_type != "hestia_motion"
    assert "hestia_motion" not in (result.ambiguous_types or ())
    assert bed.execution.declared == {"hold"}
    assert bed.execution.hold_for("both_up") == "stream"


@pytest.mark.parametrize(
    "properties,response",
    [
        (("write",), True),
        (("write-without-response",), False),
        (("write", "write-without-response"), False),
    ],
)
async def test_roles_cross_services_last_match_and_live_write_mode(properties, response):
    coordinator, client, bed = make_bed(properties=properties)
    old = SimpleNamespace(uuid=WRITE, properties=("write",), handle=9)
    client.services.insert(0, SimpleNamespace(uuid="other", characteristics=[old]))
    await bed.async_discover_capabilities()
    with virtual_time(FakeClock()):
        await bed.lights_on()
    assert client.write_gatt_char.call_args.args[0].handle == 1
    assert client.write_gatt_char.call_args.kwargs["response"] is response


async def test_missing_roles_or_properties_never_write():
    _, client, bed = make_bed(properties=())
    with pytest.raises(BleakError):
        await bed.async_discover_capabilities()
    with pytest.raises(BedNotConnectedError):
        await bed.lights_on()
    assert not packets(client)


async def test_raw_notifications_ignore_old_session_and_empty_packets():
    coordinator, client, bed = await connected()
    # Use a callable recorder without parsing any bytes.
    received = []
    bed.forward_raw_notification = lambda uuid, value: received.append((uuid, value))
    await bed.start_notify()
    callback = client.start_notify.call_args.args[1]
    callback(None, bytearray())
    callback(None, bytearray.fromhex("f4fe16deadbeef"))
    assert received == [(NOTIFY, bytes.fromhex("f4fe16deadbeef"))]
    bed.on_disconnect()
    callback(None, bytearray(b"late"))
    await bed.async_discover_capabilities()
    await bed.start_notify()
    callback(None, bytearray(b"old-token"))
    assert len(received) == 1


@pytest.mark.parametrize(
    "control,word",
    [
        (f"{axis}_{direction}", pair[index])
        for axis, pair in app.AXES.items()
        for index, direction in enumerate(("up", "down"))
    ],
)
async def test_native_motor_cadence_and_release(control, word):
    _, client, bed = await connected()
    clock = FakeClock()
    with virtual_time(clock):
        await bed.hold_control(control, 250)
    assert packets(client) == [encode(app.PROFILE, word)] * 3 + [encode(app.PROFILE, 0)]
    assert clock.now == pytest.approx(0.35)


async def test_cancel_mid_write_finishes_before_release_and_fresh_event():
    coordinator, client, bed = await connected()
    started, finish = asyncio.Event(), asyncio.Event()
    sent = []

    async def write(char, frame, **kwargs):
        sent.append(bytes(frame))
        if len(sent) == 1:
            started.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(bed.hold_control("back_up", 2000))
    await started.wait()
    task.cancel()
    coordinator.cancel_command.set()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sent == [encode(app.PROFILE, 1), encode(app.PROFILE, 0)]


async def test_failed_movement_still_releases_but_replaced_link_never_receives_cleanup():
    coordinator, client, bed = await connected()
    client.write_gatt_char.side_effect = [BleakError("failed"), None]
    with virtual_time(FakeClock()), pytest.raises(BleakError):
        await bed.hold_control("legs_down", 100)
    assert packets(client) == [encode(app.PROFILE, 8), encode(app.PROFILE, 0)]
    client.write_gatt_char.reset_mock(side_effect=True)

    async def replace(*args, **kwargs):
        coordinator.client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock())

    client.write_gatt_char.side_effect = replace
    with virtual_time(FakeClock()), pytest.raises(BedNotConnectedError):
        await bed.hold_control("legs_up", 100)
    assert len(packets(client)) == 1
    coordinator.client.write_gatt_char.assert_not_called()


async def test_presets_memory_save_and_repeat_cancel_survive_unrelated_actions():
    _, client, bed = await connected()
    with virtual_time(FakeClock()):
        await bed.preset_memory(1)
        await bed.lights_on()
        await bed.hold_control("both_up", 100)
        await bed.preset_memory(1)
        await bed.program_memory(2)
        await bed.preset_memory(2)
        await bed.stop_all()
    assert packets(client) == [
        encode(app.PROFILE, word)
        for word in (0x21000004, 0x31000001, 5, 0, 0x21000000, 0x21000016, 0x21000006, 0x21000000)
    ]


async def test_native_massage_choices_on_off_and_immediate_timer():
    coordinator, client, bed = await connected()
    choices = {spec.key: spec for spec in bed.controller_select_specs}
    choices["hestia_wave"].local_select_fn("2")
    choices["hestia_intensity"].local_select_fn("3")
    assert not packets(client)
    switch = next(spec for spec in bed.controller_switch_specs if spec.key == "hestia_massage")
    with virtual_time(FakeClock()):
        await switch.set_fn(bed, True)
        await bed.set_massage_timer(20)
        await switch.set_fn(bed, False)
    assert packets(client) == [
        encode(app.PROFILE, word) for word in (0x10000022, 0x10000013, 0x10000031, 0x10000010)
    ]
    saved = bed.persisted_app_state
    assert saved["timer"] == "20"
    bed.on_disconnect()
    assert bed.persisted_app_state == saved
    assert bed._lamp is None


async def test_partial_massage_cancel_never_claims_success():
    coordinator, client, bed = await connected()
    updates = []
    bed.forward_controller_state_updates = lambda *values: updates.extend(values)

    async def cancel(*args, **kwargs):
        coordinator.cancel_command.set()

    client.write_gatt_char.side_effect = cancel
    with virtual_time(FakeClock()), pytest.raises(asyncio.CancelledError):
        await bed.massage_start()
    assert len(packets(client)) == 1
    assert updates == [MASSAGE(None)]


async def test_invalid_native_and_alarm_requests_fail_before_first_write():
    _, client, bed = await connected()
    with pytest.raises(ValueError):
        await bed.set_massage_timer(0)
    with pytest.raises(ValueError):
        bed.choose("wave", "4")
    with pytest.raises(ValueError):
        await bed.program_memory(3)
    with pytest.raises(ValueError):
        await bed.configure_alarm(
            AlarmRequest(enabled=True, hour=24, reference_time=datetime.now())
        )
    assert not packets(client)


async def test_native_alarm_switch_uses_exact_rtc_and_clears_on_failure(freezer):
    freezer.move_to("2026-01-01 12:34:56+00:00")
    _, client, bed = await connected()
    for key, value in {
        "hour": "7",
        "minute": "45",
        "wave": "2",
        "intensity": "1",
        "memory": "memory_1",
    }.items():
        bed.choose(key, value)
    bed._enhancement(True)
    switch = next(spec for spec in bed.controller_switch_specs if spec.key == "hestia_alarm")
    await switch.set_fn(bed, True)
    assert packets(client)[-1] == app.alarm(
        datetime(2026, 1, 1, 12, 34, 56),
        time(7, 45),
        enhancement=True,
        intensity=1,
        wave=2,
        memory="memory_1",
    )
    await switch.set_fn(bed, False)
    assert packets(client)[-1][6:12] == b"\xff" * 6
    updates = []
    bed.forward_controller_state_updates = lambda *values: updates.extend(values)
    client.write_gatt_char.side_effect = BleakError("failed")
    with pytest.raises(BleakError):
        await switch.set_fn(bed, True)
    assert updates == [ALARM(None)]


async def test_stale_controller_cannot_write_or_invalidate_new_native_state():
    coordinator, client, bed = await connected()
    coordinator.controller = HestiaController(coordinator)
    updates = []
    bed.forward_controller_state_updates = lambda *values: updates.extend(values)
    for operation in (bed.lights_on, bed.massage_start, bed.massage_off):
        with pytest.raises(BedNotConnectedError):
            await operation()
    assert not updates and not packets(client)
    spec = bed.controller_select_specs[0]
    bed.on_app_state_replaced()
    with pytest.raises(BedNotConnectedError):
        spec.local_select_fn("1")
    assert not updates


async def test_subscribe_failure_invalidates_callback_and_allows_retry():
    _, client, bed = await connected()
    received = []
    bed.forward_raw_notification = lambda uuid, frame: received.append(frame)
    client.start_notify.side_effect = BleakError("subscription refused")
    with pytest.raises(BleakError):
        await bed.start_notify()
    failed_callback = client.start_notify.call_args.args[1]
    failed_callback(None, bytearray(b"late"))
    client.start_notify.side_effect = None
    await bed.start_notify()
    callback = client.start_notify.call_args.args[1]
    callback(None, bytearray(b"fresh"))
    failed_callback(None, bytearray(b"old"))
    assert received == [b"fresh"]


async def test_new_session_during_tap_wait_gets_no_old_frame():
    coordinator, client, bed = await connected()
    old_link = bed._link

    async def replace():
        await asyncio.sleep(0.05)
        bed.on_disconnect()
        await bed.async_discover_capabilities()

    with virtual_time(FakeClock()):
        await asyncio.gather(replace(), bed.lights_on(), return_exceptions=True)
    assert bed._link is not old_link
    assert not packets(client)


def test_translations_and_card_placements_cover_native_specs():
    _, _, bed = make_bed()
    root = Path(__file__).parents[1]
    fixture = json.loads((root / "tests/fixtures/card_placements.json").read_text())
    for filename in ("strings.json", "translations/en.json"):
        entities = json.loads((root / "custom_components/adjustable_bed" / filename).read_text())[
            "entity"
        ]
        for domain, specs in (
            ("button", bed.controller_button_specs),
            ("select", bed.controller_select_specs),
            ("switch", bed.controller_switch_specs),
        ):
            for spec in specs:
                assert entities[domain][spec.translation_key]["name"]
                assert fixture[f"{domain}:{spec.translation_key}"] == spec.card.attributes
