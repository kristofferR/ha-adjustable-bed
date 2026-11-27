"""My Side cancellation at the writer, translated admission and packet-name discovery."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.adjustable_bed.beds.myside import controller as bed
from custom_components.adjustable_bed.beds.myside.protocol import Alarm
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.config_flow import _EXPLICIT_APP_HINTS, _confident_auto_detect
from custom_components.adjustable_bed.const import (
    BED_TYPE_MYSIDE,
    DOMAIN,
    LINAK_CONTROL_SERVICE_UUID,
)
from custom_components.adjustable_bed.detection import DetectionResult, detect_bed_type_detailed
from custom_components.adjustable_bed.discovery_hints import first_pass
from custom_components.adjustable_bed.profile_recommendations import recommend_profile
from custom_components.adjustable_bed.profiles import myside as app
from custom_components.adjustable_bed.services import async_register_services
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock
from tests.test_detection import _make_service_info
from tests.test_myside_ha import cleanup as cleanup
from tests.test_myside_ha import frames, invoke, receive_alarm, target


@pytest.mark.parametrize(
    "control", ["flat", "massage_timer10", "massage_timer20", "massage_timer30"]
)
@pytest.mark.parametrize("blocked", ["lock", "spacing"])
@pytest.mark.parametrize("stop", [False, True])
async def test_cancel_before_short_text_write_through_registered_hold(hass, control, blocked, stop):
    coord, ctrl, client, device = await target(hass)
    await async_register_services(hass)
    entered = asyncio.Event()
    captured = []
    original_send = ctrl._send

    async def send(data, link, event, **kwargs):
        captured.append(event)
        entered.set()
        return await original_send(data, link, event, **kwargs)

    with (
        virtual_clock() as clock,
        patch.object(bed, "monotonic", lambda: clock.now),
        patch.object(ctrl, "_wait", AsyncMock(return_value=True)),
        patch.object(ctrl, "_send", send),
    ):
        if blocked == "lock":
            await ctrl._ble_lock.acquire()
        else:
            ctrl._last_write = clock.now
        moving = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": [device.id], "control": control, "duration": 0.1},
                blocking=True,
            )
        )
        await entered.wait()
        if blocked == "spacing":
            await asyncio.sleep(0.05)
        stopping = coord.admit_stop_command() if stop else None
        if not stop:
            captured[0].set()
        assert captured[0].is_set()
        if blocked == "lock":
            ctrl._ble_lock.release()
        await moving
        if stopping is not None:
            await stopping
    assert frames(client) == ([codec.command(codec.STOP).hex()] if stop else [])


@pytest.mark.parametrize(
    "product,operation,key",
    [
        ("76", "query", "myside_alarms_unsupported"),
        ("78", "name", "myside_sleep_unsupported"),
        ("79", "edit", "myside_alarm_query_required"),
        ("79", "add", "myside_alarm_delete_required"),
    ],
)
async def test_registered_alarm_preflight_retains_specific_translated_reason(
    hass, product, operation, key
):
    _, _, client, device = await target(hass, product)
    await async_register_services(hass)
    with raises_key(key):
        await invoke(hass, [device.id], operation)
    assert frames(client) == []


async def test_hold_validation_and_lost_session_use_translated_errors(hass):
    _, ctrl, client, _ = await target(hass)
    with raises_key("myside_hold_invalid"):
        ctrl.validate_hold_control("flat", 60001)
    with raises_key("myside_massage_timer_invalid"):
        await ctrl.set_massage_timer(15)
    ctrl.on_disconnect()
    with raises_key("myside_session_ended"):
        await ctrl.preset_flat()
    assert frames(client) == []


@pytest.mark.parametrize(
    "missing,key",
    [
        ("connection", "myside_disconnected"),
        ("writer", "myside_write_route_missing"),
        ("notify", "myside_notify_required"),
    ],
)
async def test_connect_rejections_use_specific_translated_errors(hass, missing, key):
    _, ctrl, client, _ = await target(hass)
    if missing == "connection":
        client.is_connected = False
    elif missing == "writer":
        client.services = []
    else:
        client.services[0].characteristics = client.services[0].characteristics[:1]
    with raises_key(key):
        await ctrl.start_notify()
    assert frames(client) == []


async def test_shared_clock_action_owns_calendar_sync(hass):
    _, ctrl, client, device = await target(hass)
    await async_register_services(hass)
    when = datetime(2026, 11, 27, 10, 20, 30, tzinfo=UTC)
    with patch.object(bed.dt_util, "now", return_value=when):
        await hass.services.async_call(
            DOMAIN, "sync_clock", {"device_id": [device.id]}, blocking=True
        )
    assert frames(client) == [codec.calendar(when).hex()]
    schema = hass.services.async_services()[DOMAIN]["myside"].schema
    assert schema is not None
    with pytest.raises(vol.Invalid):
        schema({"device_id": [device.id], "operation": "sync"})
    with raises_key("myside_operation_unknown"):
        ctrl.validate_operation("sync")


async def test_protocol_state_stays_available_without_raw_sensor(hass):
    _, ctrl, _, _ = await target(hass, "79")
    await ctrl.operation("query")
    alarm = Alarm(1, 55, 6, 30, 69, 169)
    receive_alarm(ctrl, alarm)
    link = ctrl._link
    for data in (bytes.fromhex("6e09010078"), codec.record_20_len(6, 1, 3, (0, *b"RM-001"))):
        ctrl._notification(link, link.rx, bytearray(data))
    assert ctrl.protocol_diagnostics == {
        str(bed.CAPABILITIES): ["alarm"],
        str(bed.ALARMS): [alarm.attributes()],
        str(bed.SLEEP_NAME): "RM-001",
    }
    assert not ctrl.controller_state_sensor_specs


@pytest.mark.parametrize("word", app.SCAN_WORDS)
def test_scan_candidates_use_only_packet_names(word):
    def advertisement(name, *, alias=None, raw=None, cached=False):
        info = MagicMock(
            advertisement=SimpleNamespace(
                local_name=name, platform_data=() if cached else (object(),)
            ),
            raw=raw,
            service_uuids=[],
            manufacturer_data={},
            service_data={},
        )
        info.name = alias or name
        return info

    live = advertisement(f"prefix{word}suffix")
    assert first_pass(live).name(BED_TYPE_MYSIDE)
    result = detect_bed_type_detailed(live)
    assert BED_TYPE_MYSIDE in {result.bed_type, *(result.ambiguous_types or ())}
    for info in (
        advertisement(None, alias=word),
        advertisement(word, cached=True),
        advertisement(word, raw=b"\x02\x01\x06"),
        advertisement(word.lower()),
    ):
        assert not first_pass(info).name(BED_TYPE_MYSIDE)
        result = detect_bed_type_detailed(info)
        assert BED_TYPE_MYSIDE not in {result.bed_type, *(result.ambiguous_types or ())}
    name = f"prefix{word}suffix".encode()
    raw = bytes((len(name) + 1, 0x09)) + name
    assert first_pass(advertisement("Unrelated", raw=raw, cached=True)).name(BED_TYPE_MYSIDE)


@pytest.mark.parametrize("candidate", sorted(_EXPLICIT_APP_HINTS))
def test_explicit_app_candidates_preserve_confident_receiver(candidate):
    assert BED_TYPE_MYSIDE in _EXPLICIT_APP_HINTS
    result = DetectionResult("bedtech", 0.9, [], ambiguous_types=[candidate])
    assert _confident_auto_detect(result) == "bedtech"


@pytest.mark.parametrize(
    "name,uuids,manufacturer,expected",
    [
        (
            "QRRM157738",
            ["0000fee9-0000-1000-8000-00805f9b34fb"],
            {19543: bytes.fromhex("54307651")},
            "bedtech",
        ),
        ("BED-123", [LINAK_CONTROL_SERVICE_UUID], {}, "linak"),
    ],
)
def test_live_myside_hint_does_not_poison_receiver_recommendation(
    name, uuids, manufacturer, expected
):
    info = _make_service_info(name, service_uuids=uuids, manufacturer_data=manufacturer)
    info.advertisement = SimpleNamespace(local_name=name, platform_data=(object(),))
    info.raw = None
    result = detect_bed_type_detailed(info)
    assert BED_TYPE_MYSIDE in (result.ambiguous_types or ())
    assert _confident_auto_detect(result) == expected
    for selected in ("richmat", expected):
        data = {"bed_type": selected, "protocol_variant": "auto"}
        recommendation = recommend_profile(data, info, {})
        # Preserve other packet-name candidates, including Atlas Lift on QRRM.
        baseline = replace(
            result,
            ambiguous_types=[
                candidate
                for candidate in result.ambiguous_types or ()
                if candidate != BED_TYPE_MYSIDE
            ],
        )
        with patch(
            "custom_components.adjustable_bed.profile_recommendations.detect_bed_type_detailed",
            return_value=baseline,
        ):
            assert recommendation == recommend_profile(data, info, {})
        if recommendation is not None:
            assert BED_TYPE_MYSIDE not in recommendation.choices
    assert (
        recommend_profile({"bed_type": BED_TYPE_MYSIDE, "protocol_variant": "79"}, info, {}) is None
    )
