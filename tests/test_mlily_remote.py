"""MLILY Remote unit162 literals, product gates and physical session ownership."""

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.adjustable_bed.beds.casper_base.protocol import Request, alarm_countdown
from custom_components.adjustable_bed.beds.mlily_remote.controller import MlilyRemoteController
from custom_components.adjustable_bed.beds.mlily_remote.receive import Receiver
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.mlily_remote import ACTIONS, PROFILES
from tests.mlily_remote_vectors import ROOT, VECTORS, encode
from tests.test_casper_base import char, frames
from tests.test_casper_base import make as casper_make


@pytest.fixture(autouse=True)
async def protocol_clock():
    from tests.hold_lease_wire import virtual_clock

    with virtual_clock():
        yield


def make(product="ms600", transport=1, layout="single"):
    _, coordinator = casper_make(transport=transport)
    controller = MlilyRemoteController(coordinator, product=product, layout=layout)
    return controller, coordinator


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_frozen_tx(row):
    assert encode(row).hex() == bytes.fromhex(row["expected_bytes"]).hex()


@pytest.mark.parametrize(
    "row",
    json.loads((ROOT / "variant_inventory.json").read_text()),
    ids=lambda row: row["selector"],
)
def test_complete_product_gates(row):
    if row["label"] == "none":
        with pytest.raises(ValueError):
            make("none")
        return
    profile = next(p for p in PROFILES.values() if p.code == row["catalog_code"])
    for field, indices in zip(
        ("manual", "massage_or_fan", "presets", "alarm_modes"), profile.row[1:5], strict=True
    ):
        assert ["deviceFunctionItem" + ACTIONS[i][0] for i in indices] == row[field]
    assert profile.cooling == row["flag_30"]
    assert profile.phone_snore == row["flag_2c"]


def test_buttons_add_only_what_shared_presets_lack():
    controller, _ = make("ms600")
    # Flat and memory recall/save are the shared preset_flat/preset_memory/program_memory.
    assert controller.supports_preset_flat and controller.memory_slot_count == 3
    assert controller.standard_button_requires_confirmation("program_memory_3")
    assert [s.name for s in controller.controller_button_specs] == [
        "Toggle Light",
        "Massage: Head Up",
        "Massage: Lumbar Up",
        "Massage: Foot Up",
        "Massage: Mode",
        "Massage: Off",
        "Massage: Timer 10 Minutes",
        "Massage: Timer 20 Minutes",
        "Massage: Timer 30 Minutes",
        "Zero Gravity",
        "Save Zero Gravity",
        "Anti-Snore",
        "Save Anti-Snore",
        "TV",
        "Save TV",
    ]


def expected_events(row):
    """Compare source result values with the shared parser's event schema."""
    x, name = row["expected_state"], row["id"]
    if x is None or name in ("RX-check-5", "RX-check-6"):
        return []
    if "zones" in x:
        return [
            ("deviceMassageHeadStrengthStatusEvent", 4),
            ("deviceMassageFootStrengthStatusEvent", 6),
        ]
    if "height" in x:
        return [("deviceMotorCurrentHeightStatusEvent", x)]
    if "record" in x:
        return [
            (
                "deviceRepeatAlarmListStatusEvent"
                if x["event"] == "list"
                else "deviceRepeatAlarmListEscalationStatusEvent",
                {"alarm_fields": list(x["record"].values())},
            )
        ]
    if "check_selector" in x:
        return [("deviceCheckEvent", [x["check_selector"], x["raw"]])]
    if "event_payload" in x:
        return [
            (
                "deviceDetectionMessageEvent",
                {"type": "RMDeviceDetectionDataDetails", "fields": x["event_payload"]},
            )
        ]
    if "rgb" in x:
        return [("deviceRGBStripColorStatusEvent", {"rgba_bytes": [*x["rgb"], 255]})]
    if "no" in x:
        return [("deviceVersionOneMotorAngleEvent", x)]
    if "massage1" in x:
        return [("deviceVersionOneMassageModeEvent", x)]
    mapping = {
        "version": "deviceControlBoxProtocolVersionEvent",
        "bed_mode": "deviceVersionOneBedModeEvent",
        "check_status": "deviceDetectionStatusEvent",
        "minutes": "deviceRGBStripTimerStatusEvent",
        "sensor_enabled": "deviceRGBStripMotionStatusEvent",
        "strip_on": "deviceRGBStripStatusEvent",
        "snore_detection": "deviceAntiSnoreEvent",
        "out_of_bed_detection": "deviceGetOffBedStatusEvent",
        "sleep_band_name_bytes": "deviceSleepAdvNameEvent",
        "mode": "deviceMassageModeStatusEvent",
        "frequency": "deviceMassageFrequencStatusEvent",
        "follow_intensity": "deviceMusicShakeStatusEvent",
    }
    key = next(iter(x))
    if key == "on":
        return [
            (
                "deviceWhiteLedStatusEvent" if "white" in name else "deviceMassagePowerStatusEvent",
                x[key],
            )
        ]
    return [(mapping[key], x[key])]


@pytest.mark.parametrize(
    "row", json.loads((ROOT / "notification_vectors.json").read_text()), ids=lambda row: row["id"]
)
def test_frozen_rx(row):
    events = []
    receiver = Receiver(lambda name, value: events.append((name, value)))
    receiver.feed(bytes.fromhex(row["expected_bytes"]))
    assert events == expected_events(row)


@pytest.mark.parametrize("transport", range(6))
async def test_gatt_startup_and_response_type(transport):
    controller, c = make(transport=transport)
    with patch(
        "custom_components.adjustable_bed.beds.mlily_remote.controller.dt_util.now",
        return_value=datetime(2026, 11, 16, 12, 34, 56, tzinfo=UTC),
    ):
        await controller.start_notify()
    assert frames(c) == (["00", "01"] if transport == 0 else ["6e02010071", "6e08010178"]) + [
        "6e200d080301380b100c223860"
    ]
    assert all(call.kwargs["response"] is False for call in c.client.write_gatt_char.call_args_list)
    assert controller.supports_single_address_pairing is False
    await controller.stop_notify()


async def test_gatt_binds_to_first_complete_service_and_ignores_indicate():
    controller, c = make(layout="double")
    nordic, framed = codec.TRANSPORTS["n1"], codec.TRANSPORTS["w1"]
    c.client.services = [
        SimpleNamespace(uuid=nordic.service_uuid, characteristics=[char("unrelated", "notify")]),
        SimpleNamespace(
            uuid=framed.service_uuid,
            characteristics=[
                char(framed.write_uuid, "write"),
                char("wrong", "indicate"),
                char("actual", "notify"),
            ],
        ),
    ]
    await controller.start_notify()
    assert controller._link.rx.uuid == "actual"
    assert not controller._link.legacy
    assert controller.supports_single_address_pairing
    assert all(call.kwargs["response"] is True for call in c.client.write_gatt_char.call_args_list)
    await controller.stop_notify()


async def test_powercool_labels_and_no_massage_release():
    controller, c = make("powercool")
    await controller.start_notify()
    specs = controller.controller_button_specs
    assert {s.name for s in specs if "Timer" in s.name} == {
        "Fan: Timer 2 Hours",
        "Fan: Timer 3 Hours",
        "Fan: Timer 5 Hours",
    }
    assert all("Massage" not in s.name for s in specs)
    spec = next(s for s in specs if s.name == "Fan: Head Up")
    c.client.write_gatt_char.reset_mock()
    await spec.press_fn(controller)
    assert frames(c) == ["6e01004cbb"]
    await controller.stop_notify()


async def test_capture_side_on_cancel_and_do_not_send_on_replacement_link():
    controller, c = make(layout="double")
    await controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    submitted = asyncio.Event()

    async def write(_char, _packet, **_kwargs):
        submitted.set()

    c.client.write_gatt_char.side_effect = write
    with controller.side_scope("right"):
        task = asyncio.create_task(controller.hold_control("mlily_remote_HeadUp", 1000))
    await submitted.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert frames(c) == ["6e01012494", "6e01016ede"]
    c.cancel_command.clear()
    c.client.write_gatt_char.reset_mock()
    submitted.clear()
    task = asyncio.create_task(controller.hold_control("mlily_remote_HeadUp", 1000))
    await submitted.wait()
    controller.on_disconnect()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert frames(c) == ["6e01002493"]


async def test_elapsed_deadline_has_no_stale_backfill_and_short_hold_is_supported():
    controller, c = make()
    await controller.start_notify()
    c.client.write_gatt_char.reset_mock()

    async def slow_write(_char, packet, **_kwargs):
        if packet[3] != codec.STOP:
            await asyncio.sleep(0.18)

    c.client.write_gatt_char.side_effect = slow_write
    await controller.hold_control("mlily_remote_HeadUp", 200)
    assert frames(c) == ["6e01002493", "6e01006edd"]
    c.client.write_gatt_char.reset_mock()
    c.client.write_gatt_char.side_effect = None
    await controller.hold_control("mlily_remote_HeadUp", 100)
    assert frames(c) == ["6e01002493", "6e01006edd"]
    await controller.stop_notify()


async def test_programming_threshold_is_distinct_and_no_discrete_stop():
    controller, c = make()
    await controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    with patch.object(controller, "_wait", AsyncMock(return_value=True)) as wait:
        await controller.program_memory(3)
    wait.assert_awaited_once_with(3)
    await controller.preset_memory(3)
    assert frames(c) == ["6e01002d9c", "6e0100309f"]
    await controller.stop_notify()


async def test_alarm_halves_ack_cache_cancel_and_clock_gate():
    controller, c = make()
    await controller.start_notify()
    controller._event("deviceCharacteristicsSubscriptionClockEvent", None)
    c.client.write_gatt_char.reset_mock()
    with patch(
        "custom_components.adjustable_bed.beds.mlily_remote.controller.dt_util.now",
        return_value=datetime(2026, 11, 16, 6, tzinfo=UTC),
    ):
        await controller.async_execute_casper_base_request(
            Request("alarm", hour=11, mode="MemoryPosition1")
        )
    assert frames(c) == ["6e052c009f", "6e06012ea3"]
    assert not controller.persisted_app_state
    controller._event("deviceAddAlarmSuccessEvent", None)
    assert controller.persisted_app_state == {"hour": 11, "minute": 0, "mode": "MemoryPosition1"}
    await controller.async_execute_casper_base_request(Request("alarm_cancel"))
    assert frames(c)[-2:] == ["6e05000073", "6e06000074"]
    controller._event("deviceCancelAlarmSuccessEvent", None)
    assert not controller.persisted_app_state
    assert alarm_countdown(6, 0, datetime(2026, 11, 16, 6, tzinfo=UTC)) == 1440
    await controller.stop_notify()


def test_receive_safe_fragmentation_malformed_progress_and_no_capability_promotion():
    events = []
    receiver = Receiver(lambda name, value: events.append((name, value)))
    receiver.feed(bytes.fromhex("6e0901"))
    assert not events
    receiver.feed(bytes.fromhex("0078"))
    assert events == [("deviceCharacteristicsSubscriptionClockEvent", None)]
    receiver.feed(bytes.fromhex("6e20006e2007050102dd"))
    assert not receiver.buffer
    assert receiver.rejection
    controller, _ = make("ms200")
    assert not controller.alarm_modes
    assert controller.memory_slot_count == 2
    assert {s.key for s in controller.motor_control_specs} == {"back", "legs"}
    assert not controller.supports_casper_base_controls
    with pytest.raises(ValueError):
        controller.validate_casper_base_request(Request("alarm"))


async def test_short_hold_tolerates_bounded_first_tick_scheduling_latency():
    controller, c = make()
    await controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    wait = controller._wait

    async def late(delay):
        result = await wait(delay)
        await asyncio.sleep(.02)
        return result

    with patch.object(controller, "_wait", late):
        await controller.hold_control("mlily_remote_HeadUp", 100)
    assert frames(c) == ["6e01002493", "6e01006edd"]
    await controller.stop_notify()


def test_default_left_detector_consequence_preserves_ms300sh_gate():
    controller, _ = make("ms200")
    with pytest.raises(ValueError, match="MS300-SH"):
        controller.validate_casper_base_request(Request("anti_snore"))
    controller, _ = make("ms300_sh")
    controller.validate_casper_base_request(Request("anti_snore"))


@pytest.mark.parametrize("keyword", ["QRRM", "COOL", "MPE_", "209A", "BED-"])
def test_case_sensitive_scan_substrings_do_not_choose_a_model(keyword):
    from custom_components.adjustable_bed.discovery_hints.mlily_remote import HINTS

    assert HINTS[0].matches_name("prefix-" + keyword + "-suffix")
    assert not HINTS[0].matches_name("prefix-" + keyword.lower() + "-suffix")
    assert HINTS[0].bed_types == frozenset({"mlily_remote"})


@pytest.mark.parametrize("row", json.loads((ROOT / "gatt_routes.json").read_text()), ids=lambda row: row["name"])
def test_frozen_gatt_routes(row):
    from custom_components.adjustable_bed.profiles.mlily_remote import TRANSPORTS

    route = codec.TRANSPORTS[TRANSPORTS[row["ordinal"]]]
    assert route.service_uuid.lower() == row["service"].lower()
    assert route.write_uuid.lower() == row["write"].lower()
    assert route.notify_uuid.lower() == row["declared_notify"].lower()


def test_truncated_alarm_never_uses_checksum_as_sixth_field():
    events = []
    receiver = Receiver(lambda name, value: events.append((name, value)))
    # Five record fields followed by checksum, rather than all six fields.
    receiver.feed(codec.record_20_len(5, 1, 2, (1, 2, 3, 4, 5)))
    assert not events
    assert receiver.rejection == "Truncated alarm record"


async def test_cancelled_startup_does_not_mark_partial_initialization_ready():
    controller, c = make()

    async def cancel_after_exit(_char, _packet, **_kwargs):
        c.cancel_command.set()

    c.client.write_gatt_char.side_effect = cancel_after_exit
    with pytest.raises(asyncio.CancelledError):
        await controller.start_notify()
    assert frames(c) == ["6e02010071"]
    assert controller._link is None
    c.client.stop_notify.assert_awaited_once()


@pytest.mark.parametrize("side", ["right", "both"])
def test_direct_intervention_rejects_non_left_controller_scope(side):
    controller, _ = make("ms300_sh", layout="double")
    with controller.side_scope(side), pytest.raises(ValueError, match="left owner"):
        controller.validate_casper_base_request(Request("anti_snore"))
