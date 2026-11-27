"""MUUEGM frozen builders, receiver, HA setup, native controls and session lifetime."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, number, select, services
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.dreamsense.muuegm import (
    ACTIVE,
    COLOR,
    DIAGNOSTICS,
    ROUTES,
    MuuegmController,
)
from custom_components.adjustable_bed.beds.dreamsense.muuegm_receive import (
    Alarm,
    MuuegmReceive,
    decode,
)
from custom_components.adjustable_bed.beds.dreamsense.transport import select as choose
from custom_components.adjustable_bed.codec import richmat as c
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.muuegm import PROFILES
from tests.error_helpers import raises_key
from tests.test_dreamsense import make_client, written

FIXTURES = Path(__file__).parent / "fixtures/muuegm"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())
FEATURES = json.loads((FIXTURES / "feature-vectors.json").read_text())
SPECIAL = {x["object"]: x for x in json.loads((FIXTURES / "special-prefixes.json").read_text())}


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: v["id"])
def test_frozen_builders(v):
    i = v["inputs"]
    if v["kind"] in ("ordinary", "special"):
        result = c.function(
            i["code"],
            i.get("side", 0),
            single=not i["framed"],
            action=SPECIAL[i["enum_object"]]["name"] if v["kind"] == "special" else "",
        )
    else:
        result = c.frame(*i["prefix"])
    assert result == bytes.fromhex(v["expected_bytes"])


@pytest.mark.parametrize("v", FEATURES, ids=lambda v: v["id"])
def test_feature_builders(v):
    i, k = v["inputs"], v["kind"]
    if k == "light_duration":
        result = (
            c.light_timer(255, 255)
            if i["seconds"] == 0
            else c.light_timer(i["seconds"] >> 8, i["seconds"])
        )
    elif k == "light_rgb":
        result = c.rgb(*i["rgb"])
    elif k == "simple_alarm":
        result = list(c.countdown(i["minutes"], i["mode"]))
    elif k == "repeat_add":
        result = Alarm(
            *(i[n] for n in ("number", "reserved", "hour", "minute", "mode", "mask"))
        ).frame()
    elif k == "repeat_delete":
        result = c.record_20_len(5, 2, 1, (i["number"],))
    else:
        result = [
            c.record_20_len(
                8, 2, 1, (*i["epoch_seconds"].to_bytes(4, "big"), int(i["timezone_minutes"] / 60))
            ),
            c.record_20_len(8, 3, 1, (i["local"][0] - 1970, *i["local"][1:])),
        ]
    actual = [x.hex(" ") for x in result] if isinstance(result, list) else result.hex(" ")
    assert actual == v["expected"]


@pytest.mark.parametrize(
    "v", json.loads((FIXTURES / "parser-vectors.json").read_text()), ids=lambda v: v["id"]
)
def test_frozen_parser(v):
    if v["kind"] == "buffer":
        recv = MuuegmReceive()
        frames = []
        for chunk in v["chunks"]:
            recv.feed(bytes.fromhex(chunk))
            frames.extend(recv.frames)
        assert {"frames": frames, "remaining": recv.pending.hex(" ")} == v["expected"]
    else:
        assert decode(bytes.fromhex(v["frame"])) == v["expected"]


async def runtime(hass, product="ABF03", layout=0):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="MUUEGM",
        data={
            CONF_ADDRESS: "11:22:33:44:55:68",
            CONF_NAME: "MUUEGM",
            const.CONF_BED_TYPE: "muuegm",
            const.CONF_PROTOCOL_VARIANT: product,
            const.CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    coord._client = make_client(layout)
    ctrl = await create_controller(coord, "muuegm", product, coord._client)
    assert isinstance(ctrl, MuuegmController)
    coord._controller = ctrl
    ctrl._wait = AsyncMock()
    return coord, ctrl


def notify(coord, value):
    char, callback = coord.client.start_notify.await_args.args
    callback(char, bytearray.fromhex(value))


@pytest.mark.parametrize("layout", range(6))
@pytest.mark.parametrize("product", PROFILES)
async def test_product_startup_and_controls(hass, product, layout):
    coord, ctrl = await runtime(hass, product, layout)
    await ctrl.start_notify()
    packets = written(coord)
    single = layout != 0
    assert packets[0] == ("00" if single else "6e02010071")
    assert packets[-2:] == (["01", "01"] if single else ["6e08010178", "6e0a000179"])
    assert len(packets) == (3 if product == "NUPG400" else 5)
    assert not ctrl.supports_single_address_pairing and not ctrl.controller_select_specs
    assert ctrl.execution.hold_for("HeadUp") == "stream"
    assert not ctrl.position_number_specs
    coord.client.write_gatt_char.reset_mock()
    for action in ctrl.profile.controls:
        if action.held:
            continue
        await ctrl.press(action.action)
        expected = [c.function(action.code, single=single).hex()]
        if action.release:
            expected.append(c.function(c.STOP, single=single).hex())
        assert written(coord) == expected
        coord.client.write_gatt_char.reset_mock()
        if action.save is not None:
            await ctrl.press(action.action, save=True)
            assert written(coord) == [c.function(action.save, single=single).hex()]
            coord.client.write_gatt_char.reset_mock()
    if product == "ABF07":
        with raises_key("dreamsense_action"):
            await ctrl.press("MassageModeAllOff")


@pytest.mark.parametrize("order", [(1, 0), (0, 1)])
def test_service_order_keeps_handles_independent(order):
    client = make_client(order[0])
    client.services += make_client(order[1]).services
    session = choose(client, 1, "ABF03", routes=ROUTES, requires_notify=False)
    assert session.write is client.services[0].characteristics[0]
    assert session.notify is client.services[0].characteristics[1]
    assert session.single is (order[-1] != 0)
    assert c.function(0x24, single=session.single).hex() == ("24" if order[-1] else "6e01002493")
    client.services[0].characteristics[0].properties = ["write-without-response"]
    assert choose(client, 1, "ABF03", routes=ROUTES).write is client.services[1].characteristics[0]
    client.services[0].uuid = "00000000-0000-0000-0000-000000000000"
    assert choose(client, 1, "ABF03", routes=ROUTES).notify is client.services[1].characteristics[1]


async def test_native_lighting_gates_and_unknown_disconnect(hass):
    coord, ctrl = await runtime(hass)
    hass.data.setdefault(const.DOMAIN, {})[coord.entry.entry_id] = coord
    await ctrl.start_notify()
    numbers, selects = [], []
    await number.async_setup_entry(hass, coord.entry, numbers.extend)
    await select.async_setup_entry(hass, coord.entry, selects.extend)
    with raises_key("dreamsense_capability"):
        await ctrl.light_settings(seconds=60)
    notify(coord, "6e0e00037e")
    assert not ctrl.controller_select_specs
    notify(coord, "6e0e00037f")
    await hass.async_block_till_done()
    timer = next(e for e in numbers if e.unique_id.endswith("dreamsense_light_seconds"))
    color = next(e for e in selects if e.unique_id.endswith("muuegm_color"))
    assert timer.native_step == 60
    coord.client.write_gatt_char.reset_mock()
    await timer.async_set_native_value(300)
    await color.async_select_option("red")
    assert written(coord) == ["6e0b012ca6", "6e0cffff786e0d00007b"]
    assert coord.controller_state.get(COLOR) == "red"
    old_callback = coord.client.start_notify.await_args.args[1]
    ctrl.on_disconnect()
    assert coord.controller_state.get(COLOR) is None
    assert coord.controller_state.get(ACTIVE) is None
    assert coord.controller_state.get(DIAGNOSTICS) is None
    await ctrl.start_notify()
    old_callback(None, bytearray.fromhex("6e0e00037f"))
    with raises_key("dreamsense_capability"):
        await color.async_select_option("blue")


async def test_simple_alarm_uses_execution_time_and_no_release(hass):
    coord, ctrl = await runtime(hass)
    await ctrl.start_notify()
    notify(coord, "6e09010078")
    coord.client.write_gatt_char.reset_mock()
    alarm = AlarmRequest(
        enabled=True,
        hour=12,
        minute=35,
        wake_action="zero_g",
        reference_time=datetime(2026, 11, 27, 11, 0, tzinfo=UTC),
    )
    with patch(
        "custom_components.adjustable_bed.beds.dreamsense.muuegm.dt_util.now",
        return_value=datetime(2026, 11, 27, 12, 34, 59, tzinfo=UTC),
    ):
        await coord.async_execute_controller_command(
            lambda live: live.configure_alarm(alarm), cancel_running=False
        )
    assert written(coord) == ["6e05010074", "6e060045b9"]
    notify(coord, "6e07010177")
    assert coord.controller_state.get(ACTIVE) is True
    await coord.async_execute_controller_command(
        lambda live: live.configure_alarm(replace(alarm, enabled=False)), cancel_running=False
    )
    assert written(coord)[-2:] == ["6e05000073", "6e06000074"]
    notify(coord, "6e07010278")
    assert coord.controller_state.get(ACTIVE) is False


async def test_repeat_records_and_real_services_preserve_fields(hass):
    coord, ctrl = await runtime(hass, "ABF07")
    await ctrl.start_notify()
    notify(coord, "6e09010078")
    original = Alarm(2, 9, 7, 30, 69, 0xF9)

    def feed(record, kind=2):
        notify(
            coord,
            c.record_20_len(
                5,
                1,
                kind,
                (
                    record.id,
                    record.reserved,
                    record.hour,
                    record.minute,
                    record.mode,
                    record.repeat_mask,
                ),
            ).hex(),
        )

    feed(original)
    feed(original)
    feed(replace(original, hour=8))
    assert len(ctrl.receive.records) == 2
    feed(replace(original, id=7), 3)
    assert len(ctrl.receive.records) == 2
    feed(replace(original, minute=31), 3)
    assert ctrl.receive.records[0].minute == 31
    await services.async_register_services(hass)
    coord.client.write_gatt_char.reset_mock()
    with patch.object(
        services, "_resolve_sided_targets", return_value=([(coord, const.SIDE_BOTH)], [])
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "muuegm_enable_alarm",
            {"device_id": "bed", "alarm_number": 2, "enabled": False},
            blocking=True,
        )
    assert written(coord) == [
        replace(original, minute=31, repeat_mask=0xF8).frame().hex(),
        "6e2008050100009c",
    ]
    assert not ctrl.receive.records
    feed(original)
    identity = ctrl.validate_record(2)
    feed(replace(original, minute=32), 3)
    with raises_key("dreamsense_alarm_record"):
        await ctrl.delete_alarm(2, identity)
    coord.client.write_gatt_char.reset_mock()
    identity = ctrl.validate_record(2)
    await coord.async_execute_controller_command(
        lambda live: live.delete_alarm(2, identity), cancel_running=False
    )
    assert written(coord) == ["6e200805020102a0", "6e2008050100009c"]


@pytest.mark.parametrize("product", PROFILES)
async def test_real_setup_saves_explicit_app_product(hass, product):
    from custom_components.adjustable_bed import _async_sync_profile_ids
    from tests.form_helpers import finish_new_bed
    from tests.test_richmat_family_flow import setup_flow

    flow = setup_flow(hass, **{const.CONF_BED_TYPE: "muuegm"})
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        form = await flow.async_step_profile_questions()
        assert form["type"] == "form"
        result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: product})
        result = await finish_new_bed(flow, result)
    saved = MockConfigEntry(domain=const.DOMAIN, data=result["data"])
    saved.add_to_hass(hass)
    _async_sync_profile_ids(hass, saved)
    assert saved.data[const.CONF_PROFILE_ID] == f"muuegm:{product}"
    coord = AdjustableBedCoordinator(hass, saved)
    await coord.async_prime_offline_controller()
    assert coord.capability_controller.profile == PROFILES[product]


async def test_nupg400_suppresses_ack_gated_features_and_side_controls(hass):
    coord, ctrl = await runtime(hass, "NUPG400")
    await ctrl.start_notify()
    notify(coord, "6e09010078 6e0e00037f")
    assert not ctrl.alarm_capability and not ctrl.supports_clock_sync
    assert not ctrl.controller_number_specs and not ctrl.controller_select_specs
    with ctrl.side_scope(const.SIDE_RIGHT), raises_key("dreamsense_side"):
        await ctrl.press("MotorReset")
    with raises_key("dreamsense_action"):
        await ctrl.light_settings(seconds=60)


async def test_pending_light_cannot_cross_reconnect_or_product_change(hass):
    coord, ctrl = await runtime(hass)
    await ctrl.start_notify()
    notify(coord, "6e0e00037f")
    coord.client.write_gatt_char.reset_mock()
    started, resume = asyncio.Event(), asyncio.Event()

    async def wait(_ms, _event=None):
        started.set()
        await resume.wait()

    ctrl._wait = wait
    command = asyncio.create_task(ctrl.light_settings(seconds=60))
    await started.wait()
    coord._position_connection_generation += 1
    resume.set()
    with raises_key("dreamsense_session"):
        await command
    assert written(coord) == []


async def test_cancelled_motor_releases_original_writer_and_never_reconnects_stop(hass):
    coord, ctrl = await runtime(hass)
    await ctrl.start_notify()
    coord.client.write_gatt_char.reset_mock()
    started, resume = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **_kwargs):
        if data == bytes.fromhex("6e01002493"):
            started.set()
            await resume.wait()

    coord.client.write_gatt_char.side_effect = write
    command = asyncio.create_task(
        coord.async_execute_controller_command(lambda live: live.hold_control("HeadUp", 1000))
    )
    await started.wait()
    stop = asyncio.create_task(coord.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    resume.set()
    await asyncio.gather(command, stop, return_exceptions=True)
    assert written(coord)[0] == "6e01002493"
    assert set(written(coord)[1:]) == {"6e01006edd"}
    coord.client.write_gatt_char.reset_mock()
    ctrl.on_disconnect()
    with raises_key("dreamsense_session"):
        await ctrl.stop_all()
    assert written(coord) == []


@pytest.mark.parametrize("product", PROFILES)
def test_saved_app_choice_survives_shared_scan_names(product):
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile
    from tests.test_profile_recommendations import info

    advert = info("QRRM123")
    advert.advertisement.local_name = advert.name
    advert.advertisement.platform_data = ("native",)
    assert (
        recommend_profile(
            {const.CONF_BED_TYPE: "muuegm", const.CONF_PROTOCOL_VARIANT: product}, advert, {}
        )
        is None
    )


def test_shared_app_hint_does_not_replace_confident_receiver():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_profile_recommendations import info

    advert = info("KSBT-QRRM123")
    advert.advertisement.local_name = advert.name
    advert.advertisement.platform_data = ("native",)
    advert.manufacturer_data = {89: bytes.fromhex("4142010204")}
    detected = detect_bed_type_detailed(advert)
    assert detected.bed_type != "muuegm"
    assert "muuegm" in (detected.ambiguous_types or [])


def test_confident_receiver_with_only_muuegm_hint_stays_automatic():
    from custom_components.adjustable_bed.config_flow import _confident_auto_detect
    from custom_components.adjustable_bed.detection import DetectionResult

    assert (
        _confident_auto_detect(
            DetectionResult("keeson", 0.95, ["manufacturer:receiver"], ambiguous_types=["muuegm"])
        )
        == "keeson"
    )


async def test_real_set_alarm_service_adds_abf07_record(hass):
    coord, ctrl = await runtime(hass, "ABF07")
    await ctrl.start_notify()
    notify(coord, "6e09010078")
    await services.async_register_services(hass)
    coord.client.write_gatt_char.reset_mock()
    with patch.object(
        services, "_resolve_sided_targets", return_value=([(coord, const.SIDE_BOTH)], [])
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {
                "device_id": "bed",
                "enabled": True,
                "time": "07:30:00",
                "slot": 3,
                "wake_action": "zero_g",
                "weekdays": ["monday", "friday"],
            },
            blocking=True,
        )
    assert written(coord) == [Alarm(3, 0, 7, 30, 69, 0x89).frame().hex(), "6e2008050100009c"]


async def test_repeat_stamp_cannot_be_reused_after_reconnect(hass):
    coord, ctrl = await runtime(hass, "ABF07")
    await ctrl.start_notify()
    reply = c.record_20_len(5, 1, 2, (1, 0, 7, 30, 69, 1)).hex()
    notify(coord, "6e09010078 " + reply)
    identity = ctrl.validate_record(1)
    ctrl.on_disconnect()
    await ctrl.start_notify()
    notify(coord, "6e09010078 " + reply)
    with raises_key("dreamsense_alarm_record"):
        await ctrl.enable_alarm(1, False, identity)


def _record_notify(coord, record, kind=2):
    fields = (record.id, record.reserved, record.hour, record.minute, record.mode, record.repeat_mask)
    notify(coord, c.record_20_len(5, 1, kind, fields).hex())


def _simple_request(hour=7):
    return AlarmRequest(
        enabled=True,
        hour=hour,
        minute=30,
        wake_action="zero_g",
        reference_time=datetime(2026, 11, 27, 6, tzinfo=UTC),
    )


async def test_shared_disable_rejects_record_changed_after_preflight(hass):
    coord, ctrl = await runtime(hass, "ABF07")
    await ctrl.start_notify()
    notify(coord, "6e09010078")
    original = Alarm(2, 9, 7, 30, 69, 0xF9)
    _record_notify(coord, original)
    await services.async_register_services(hass)
    coord.client.write_gatt_char.reset_mock()
    execute = services._execute_alarm_step
    steps = 0

    async def changed_record(*args, **kwargs):
        nonlocal steps
        steps += 1
        if steps == 2:
            _record_notify(coord, replace(original, hour=8), 3)
        return await execute(*args, **kwargs)

    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(coord, const.SIDE_BOTH)], [])),
        patch.object(services, "_execute_alarm_step", side_effect=changed_record),
        raises_key("dreamsense_alarm_record"),
    ):
        await hass.services.async_call(
            const.DOMAIN, "set_alarm", {"device_id": "bed", "enabled": False, "slot": 2}, blocking=True
        )
    assert written(coord) == []


@pytest.mark.parametrize("operation", ("delete", "enable", "configure"))
@pytest.mark.parametrize("interruption", ("before_write", "after_write", "write_failure"))
async def test_repeat_mutation_retires_only_attempted_record(hass, operation, interruption):
    coord, ctrl = await runtime(hass, "ABF07")
    await ctrl.start_notify()
    notify(coord, "6e09010078")
    _record_notify(coord, Alarm(2, 9, 7, 30, 69, 0xF9))
    identity = ctrl.validate_record(2)
    coord.client.write_gatt_char.reset_mock()
    started = asyncio.Event()

    async def wait(milliseconds, _event=None):
        if milliseconds == 200:
            started.set()
            await asyncio.Future()

    ctrl._wait = wait
    if interruption == "before_write":
        await ctrl.ble_lock.acquire()
    elif interruption == "write_failure":
        coord.client.write_gatt_char.side_effect = BleakError("write failed")
    if operation == "delete":
        pending = ctrl.delete_alarm(2, identity)
    elif operation == "enable":
        pending = ctrl.enable_alarm(2, False, identity)
    else:
        pending = ctrl.configure_alarm(
            replace(_simple_request(), enabled=False, slot=2, record_identity=identity)
        )
    task = asyncio.create_task(pending)
    if interruption == "write_failure":
        with pytest.raises(BleakError, match="write failed"):
            await task
    else:
        if interruption == "after_write":
            await started.wait()
        else:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    if interruption == "before_write":
        ctrl.ble_lock.release()
        assert written(coord) == []
        assert ctrl.validate_record(2, identity) == identity
    else:
        assert len(written(coord)) == 1
        with raises_key("dreamsense_alarm_record"):
            ctrl.validate_record(2, identity)


async def test_simple_alarm_consumes_only_fresh_matching_ack(hass):
    from custom_components.adjustable_bed.beds.dreamsense.controller import ALARMS

    coord, ctrl = await runtime(hass)
    await ctrl.start_notify()
    notify(coord, "6e09010078 6e07010278")
    await ctrl.configure_alarm(_simple_request())
    notify(coord, "6e0e00037f")
    notify(coord, "6e07010177")
    assert coord.controller_state.get(ALARMS) == {"hour": 7, "minute": 30, "wake_action": "zero_g"}
    await ctrl.configure_alarm(_simple_request(8))
    notify(coord, "6e0e00037f")
    assert coord.controller_state.get(ALARMS) is None
    # Consecutive identical ACK values still represent separate received replies.
    notify(coord, "6e07010177")
    assert coord.controller_state.get(ALARMS) == {"hour": 8, "minute": 30, "wake_action": "zero_g"}


async def test_simple_alarm_unsent_cancellation_preserves_confirmed_settings(hass):
    from custom_components.adjustable_bed.beds.dreamsense.controller import ALARMS

    coord, ctrl = await runtime(hass)
    await ctrl.start_notify()
    notify(coord, "6e09010078")
    await ctrl.configure_alarm(_simple_request())
    notify(coord, "6e07010177")
    original = coord.controller_state.get(ALARMS)
    started = asyncio.Event()

    async def wait(_milliseconds, event=None):
        started.set()
        await event.wait()
        raise asyncio.CancelledError

    ctrl._wait = wait
    coord.client.write_gatt_char.reset_mock()
    task = asyncio.create_task(ctrl.configure_alarm(_simple_request(8)))
    await started.wait()
    coord.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    notify(coord, "6e0e00037f")
    assert written(coord) == []
    assert coord.controller_state.get(ALARMS) == original


@pytest.mark.parametrize("product", ("ABF03", "ABF07"))
async def test_alarm_cancellation_drains_write_and_retires_pending_state(hass, product):
    from custom_components.adjustable_bed.beds.dreamsense.controller import ALARMS

    coord, ctrl = await runtime(hass, product)
    await ctrl.start_notify()
    notify(coord, "6e09010078")
    identity = None
    if product == "ABF07":
        _record_notify(coord, Alarm(2, 9, 7, 30, 69, 0xF9))
        identity = ctrl.validate_record(2)
        operation = ctrl.delete_alarm(2, identity)
    else:
        await ctrl.configure_alarm(_simple_request())
        notify(coord, "6e07010177")
        operation = ctrl.configure_alarm(_simple_request(8))
    coord.client.write_gatt_char.reset_mock()
    started, finish = asyncio.Event(), asyncio.Event()

    async def write(*_args, **_kwargs):
        started.set()
        await finish.wait()

    coord.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(operation)
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(written(coord)) == 1
    assert coord.controller_state.get(ALARMS) is None
    if product == "ABF07":
        assert identity is not None
        with raises_key("dreamsense_alarm_record"):
            ctrl.validate_record(2, identity)
    else:
        notify(coord, "6e0e00037f 6e07010177")
        assert coord.controller_state.get(ALARMS) is None


async def test_partial_simple_alarm_ack_cannot_confirm_unwritten_settings(hass):
    from custom_components.adjustable_bed.beds.dreamsense.controller import ALARMS

    coord, ctrl = await runtime(hass)
    await ctrl.start_notify()
    notify(coord, "6e09010078")
    coord.client.write_gatt_char.reset_mock()

    async def write(*_args, **_kwargs):
        if coord.client.write_gatt_char.await_count == 1:
            notify(coord, "6e07010177")
        else:
            raise BleakError("second setting failed")

    coord.client.write_gatt_char.side_effect = write
    with pytest.raises(BleakError, match="second setting failed"):
        await ctrl.configure_alarm(_simple_request())
    assert coord.controller_state.get(ALARMS) is None
