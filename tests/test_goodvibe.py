"""Production controller, entity and lifecycle contracts for accepted row116."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from custom_components.adjustable_bed.beds.goodvibe import controller as bed
from custom_components.adjustable_bed.beds.goodvibe.catalog import (
    ACTIONS,
    PRODUCTS,
    PROFILE_CHOICES,
)
from custom_components.adjustable_bed.beds.goodvibe.protocol import action_frame, clock
from custom_components.adjustable_bed.beds.goodvibe.services import Request
from custom_components.adjustable_bed.beds.goodvibe.sleep import sleep_packet
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.richmat import GOODVIBE
from tests.state_helpers import state_writer


@pytest.fixture
def coordinator(hass):
    c = MagicMock()
    c.hass = hass
    c.address = "AA:BB:CC:DD:EE:16"
    c.cancel_command = asyncio.Event()
    c.client.is_connected = True
    c.client.mtu_size = 23
    c.client.write_gatt_char = AsyncMock()
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.controller_state = {}
    c.handle_controller_state_updates.side_effect = state_writer(c.controller_state)
    return c


def controller(c, profile="selector-0001", legacy=False):
    obj = bed.GoodVibeController(c, profile=profile)
    tx = SimpleNamespace(uuid="tx", properties=["write", "write-without-response"], handle=1)
    rx = SimpleNamespace(uuid="rx", properties=["notify"], handle=2)
    obj._link = bed.Link(c.client, tx, rx, legacy)
    return obj


def writes(c):
    return [x.args[1] for x in c.client.write_gatt_char.await_args_list]


async def test_all_profile_factory_and_setup_contracts(hass, coordinator):
    from custom_components.adjustable_bed.app_profiles import (
        hidden_generic_fields,
        per_side_profile,
    )
    from custom_components.adjustable_bed.bed_traits import disconnect_after_command_default_enabled
    from custom_components.adjustable_bed.const import (
        BED_TYPE_GOODVIBE,
        CONF_MOTOR_COUNT,
    )
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.detection import (
        APP_VARIANT_CHOICES,
        bed_type_choice,
        get_bed_type_options,
    )
    from custom_components.adjustable_bed.setup_questions import setup_profile
    from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type

    # One row asks the product, searchable by label; each product keeps its app entry.
    choices = {x["value"]: x["label"] for x in get_bed_type_options()}
    assert BED_TYPE_GOODVIBE in choices
    assert not any(
        bed_type_choice(BED_TYPE_GOODVIBE, profile) in choices for profile in PROFILE_CHOICES
    )
    profile_spec = setup_profile(BED_TYPE_GOODVIBE)
    assert profile_spec is not None
    (product,) = profile_spec.questions
    assert product.searchable and set(product.options({})) == set(PROFILE_CHOICES)
    for profile in PROFILE_CHOICES:
        assert "Good Vibe Sleep" in APP_VARIANT_CHOICES[BED_TYPE_GOODVIBE, profile]
        assert is_valid_variant_for_bed_type(BED_TYPE_GOODVIBE, profile)
        assert CONF_MOTOR_COUNT in hidden_generic_fields(BED_TYPE_GOODVIBE, profile)
        assert per_side_profile(BED_TYPE_GOODVIBE, profile).variant_owned
        obj = await create_controller(coordinator, BED_TYPE_GOODVIBE, profile, None)
        assert isinstance(obj, bed.GoodVibeController)
        assert obj.profile is GOODVIBE and obj.product_key == profile
        assert disconnect_after_command_default_enabled(BED_TYPE_GOODVIBE, profile) == (
            profile not in ("sleep_rm", "sleep_hj")
        )
    assert not is_valid_variant_for_bed_type(BED_TYPE_GOODVIBE, "auto")


def test_past_single_alarm_countdown_truncates_its_high_byte():
    # Over a day in the past the countdown is negative; -5.6 truncates to -5, not -6.
    assert clock(-1440, 5) == (bytes.fromhex("6e056000d3"), bytes.fromhex("6e06fb0574"))
    assert clock(-1440, 5)[1] != codec.countdown(-1440, 5)[1]


@pytest.mark.parametrize("kind", (1, 2, 3))
def test_gatt_selection_uses_exact_properties_and_service_order(coordinator, kind):
    services = []
    for service, (uuid, _) in bed.GATT.items():
        services.append(
            SimpleNamespace(
                uuid=service,
                characteristics=[
                    SimpleNamespace(uuid=uuid, properties=["write", "write-without-response"]),
                    SimpleNamespace(uuid="other-notify", properties=["notify"]),
                    SimpleNamespace(
                        uuid="00000003-3c17-d293-8e48-14fe2e4da212", properties=["notify"]
                    ),
                ],
            )
        )
    services.append(
        SimpleNamespace(
            uuid="2320567c-05cf-6eb4-c341-772851827e1b",
            characteristics=[
                SimpleNamespace(uuid="property-only", properties=["write-without-response"]),
                SimpleNamespace(uuid="00000003-3c17-d293-8e48-14fe2e4da212", properties=["notify"]),
            ],
        )
    )
    coordinator.client.services = services
    link = bed.select_link(coordinator.client, kind)
    assert link.tx.uuid == (
        "d44bc439-abfd-45a2-b575-925416129600"
        if kind == 1
        else "00000002-3c17-d293-8e48-14fe2e4da212"
    )
    assert link.rx.uuid == ("00000003-3c17-d293-8e48-14fe2e4da212" if kind == 3 else "other-notify")
    coordinator.client.services = [services[-1]]
    if kind == 2:
        assert bed.select_link(coordinator.client, kind).tx.uuid == "property-only"
    else:
        with pytest.raises(ValueError):
            bed.select_link(coordinator.client, kind)


async def test_process_choices_survive_controller_replacement_and_handoff(coordinator):
    first = controller(coordinator)
    first.choices.memory = True
    first.choices.hold = True
    first.on_disconnect()
    fresh = controller(coordinator)
    assert fresh.choices.memory and fresh.choices.hold
    assert fresh.choices is first.choices
    foreign = controller(coordinator, "selector-0002")
    assert not foreign.choices.memory
    assert not controller(coordinator).choices.memory
    coordinator.address = "AA:BB:CC:DD:EE:17"
    assert not controller(coordinator).choices.hold


async def test_old_callbacks_cannot_publish_into_new_link(coordinator):
    obj = controller(coordinator)
    initial = obj.choices.events.copy()
    old = obj._link
    obj.on_disconnect()
    obj._notification(old, old.rx, bytearray.fromhex("6e09010078"))
    assert obj.choices.events == initial
    fresh = controller(coordinator)
    obj._notification(old, old.rx, bytearray.fromhex("6e09010078"))
    assert fresh.choices.events == initial


async def test_sleep_chunk_write_modes_sequence_and_clear(coordinator):
    obj = controller(coordinator, "sleep_rm")
    await obj.sleep_request("realtime")
    data = b"".join(writes(coordinator))
    assert data == sleep_packet(1, "q_realtime", {"type": 0, "time": 1})
    assert all(len(x) <= 20 for x in writes(coordinator))
    assert all(
        x.kwargs["response"] is False for x in coordinator.client.write_gatt_char.await_args_list
    )
    obj.on_disconnect()
    obj = controller(coordinator, "sleep_rm")
    assert obj.choices.sequence == 1
    coordinator.client.write_gatt_char.reset_mock()
    obj = controller(coordinator, "sleep_hj")
    await obj.sleep_request("realtime")
    assert all(x.kwargs["response"] for x in coordinator.client.write_gatt_char.await_args_list)
    obj.choices.monitoring = True
    await obj.stop_all()
    assert not obj.choices.monitoring and obj._sleep.last is None


async def test_sleep_async_error_never_replays_queued_chunks(coordinator):
    obj = controller(coordinator, "sleep_hj")
    coordinator.client.write_gatt_char.side_effect = [None, ConnectionError("write failed")]
    with pytest.raises(ConnectionError):
        await obj.sleep_request("realtime")
    assert len(writes(coordinator)) == 2
    assert obj.choices.sequence == 1


async def test_notification_partial_invalid_and_cross_side_state(coordinator):
    obj = controller(coordinator, "sleep_hj")
    await obj.sleep_request("realtime")
    packet = sleep_packet(1, "q_realtime", {"L": [0, 1, 60, 15, 1], "R": [0, 0, 99, 99, 0]})
    obj._notification(obj._link, obj._link.rx, bytearray(packet[:20]))
    assert obj.choices.realtime["L"].heart == "--"
    obj._notification(obj._link, obj._link.rx, bytearray(packet[20:]))
    assert obj.choices.realtime["L"].heart == "60"
    assert obj.choices.realtime["R"].heart == "--"
    bad = sleep_packet(2, "q_realtime", {"L": [0, 1, 80, 16, 0], "R": [0]})
    obj._notification(obj._link, obj._link.rx, bytearray(bad))
    assert obj.choices.realtime["L"].heart == "60"
    assert obj._rejection
    assert not obj._sleep.buffer


async def test_single_alarm_updates_only_from_ack(coordinator):
    profile, product = next((key, p) for key, p in PRODUCTS.items() if p.alarms)
    obj = controller(coordinator, profile)
    await obj.async_execute_goodvibe_request(
        Request(
            "single",
            action=product.alarms[0],
            when=datetime(2026, 11, 4, 7, tzinfo=ZoneInfo("Europe/Oslo")),
        )
    )
    assert "saved_single" not in obj.choices.events
    obj._notification(obj._link, obj._link.rx, bytearray.fromhex("6e07010177"))
    saved = obj.choices.events["saved_single"]
    assert isinstance(saved, dict)
    assert saved["action"] == product.alarms[0]


async def test_buttons_expose_only_exact_product_actions(coordinator):
    obj = controller(coordinator)
    assert {spec.key for spec in obj.controller_button_specs} >= {
        "goodvibe_" + d for d in obj.product.actions if not ACTIONS[d].local
    }
    assert not obj.supports_motor_control
    assert obj.memory_slot_count == 0
    with pytest.raises(ValueError):
        await obj.press("not-this-product", 1000)


@pytest.mark.parametrize(
    "gesture", ("shortPress", "sustainPress", "longPress", "shortAndLongPress")
)
@pytest.mark.parametrize("legacy", (False, True))
async def test_action_gesture_write_and_release_contract(coordinator, monkeypatch, gesture, legacy):
    profile, detail = next(
        (k, d)
        for k, p in PRODUCTS.items()
        for d in p.actions
        if ACTIONS[d].gesture == gesture
        and not ACTIONS[d].local
        and not ACTIONS[d].force_long
        and not ACTIONS[d].memory_toggle
    )
    obj = controller(coordinator, profile, legacy)
    delays = []

    async def delay(ms):
        delays.append(ms)
        return True

    monkeypatch.setattr(obj, "_delay", delay)
    duration = 3100 if gesture in ("longPress", "shortAndLongPress") else 300
    await obj.press(detail, duration)
    side = obj._side()
    primary = action_frame(
        ACTIONS[detail], side, legacy, gesture in ("longPress", "shortAndLongPress")
    )
    if gesture == "sustainPress":
        assert writes(coordinator) == [primary] * 3 + [
            codec.function(codec.STOP, side, single=legacy)
        ]
        assert delays == [100, 100, 100]
    elif gesture == "shortPress":
        assert writes(coordinator) == [primary, codec.function(codec.STOP, side, single=legacy)]
    else:
        assert writes(coordinator) == [primary]
        assert delays == [3000]


async def test_cancellation_and_async_failure_run_fresh_release(coordinator, monkeypatch):
    profile, detail = next(
        (k, d)
        for k, p in PRODUCTS.items()
        for d in p.actions
        if ACTIONS[d].gesture == "sustainPress" and not ACTIONS[d].local
    )
    obj = controller(coordinator, profile)
    ticks = 0

    async def delay(_ms):
        nonlocal ticks
        ticks += 1
        if ticks > 1:
            raise asyncio.CancelledError
        return True

    monkeypatch.setattr(obj, "_delay", delay)
    with pytest.raises(asyncio.CancelledError):
        await obj.press(detail, 300)
    assert writes(coordinator)[-1] == codec.function(codec.STOP, obj._side(), single=False)
    coordinator.client.write_gatt_char.reset_mock()
    coordinator.client.write_gatt_char.side_effect = [ConnectionError("in flight failure"), None]
    monkeypatch.setattr(obj, "_delay", AsyncMock(return_value=True))
    with pytest.raises(ConnectionError):
        await obj.press(detail, 300)
    assert writes(coordinator)[-1] == codec.function(codec.STOP, obj._side(), single=False)


async def test_sleep_stop_between_chunks_prevents_later_send(coordinator):
    obj = controller(coordinator, "sleep_rm")

    async def write(_char, _data, **_kwargs):
        coordinator.cancel_command.set()

    coordinator.client.write_gatt_char.side_effect = write
    await obj.sleep_request("realtime")
    assert len(writes(coordinator)) == 1
    assert obj._sleep.last is None


async def test_report_request_replaces_live_polling_and_keeps_size_for_continuation(coordinator):
    from datetime import date

    obj = controller(coordinator, "sleep_rm")
    obj.choices.monitoring = True
    obj._poll = MagicMock()
    await obj.sleep_request("report", Request("report", part=1, date=date(2026, 11, 3)))
    assert not obj.choices.monitoring
    assert obj._poll is None
    obj._notification(
        obj._link, obj._link.rx, bytearray(sleep_packet(1, "q_report", {"fsize": 32}))
    )
    assert obj._sleep.report_size == 32
    await obj.sleep_request("report_allow", Request("report_allow", part=1, date=date(2026, 11, 3)))
    assert obj._sleep.last == "q_report_allow"
    assert obj._sleep.report_size == 32


async def test_all_reachable_sleep_builder_operands_use_actual_controller(coordinator, monkeypatch):
    from datetime import date, timedelta, timezone
    from pathlib import Path

    fixtures = json.loads(
        (Path(__file__).parent / "fixtures/goodvibe/sleep_builders.json").read_text()
    )
    routes = {
        "0x6b48f0": ("sleep_hj", "anti_snore"),
        "0x6b4de8": ("sleep_hj", "sensitivity"),
        "0x6b5e64": ("sleep_hj", "report_allow"),
        "0x6b61e0": ("sleep_hj", "report"),
        "0x6b66e0": ("sleep_hj", "realtime"),
        "0x6b6a7c": ("sleep_hj", "part"),
        "0x6b6d1c": ("sleep_hj", "part"),
        "0x6b6f58": ("sleep_hj", "time"),
        "0x6b730c": ("sleep_hj", "sync"),
        "0x6b4b8c": ("sleep_hj", "anti_snore"),
        "0x6bbaa4": ("sleep_rm", "report_allow"),
        "0x6bbff8": ("sleep_rm", "report"),
        "0x6bc32c": ("sleep_rm", "realtime"),
        "0x6bc62c": ("sleep_rm", "part"),
        "0x6bc8cc": ("sleep_rm", "part"),
        "0x6bcb6c": ("sleep_rm", "sync"),
    }
    seen = set()
    coordinator.hass.config.time_zone = "Europe/Oslo"
    for address, args, expected in fixtures:
        if address not in routes:
            continue  # Exact firmware/removed-code exclusions have no public route.
        profile, operation = routes[address]
        obj = controller(coordinator, profile)
        obj.choices.sequence = expected["id"] - 1
        coordinator.client.write_gatt_char.reset_mock()
        if "clock_microseconds" in args:
            now = datetime.fromtimestamp(
                args["clock_microseconds"] / 1e6, timezone(timedelta(hours=args["timezone_hours"]))
            )
            monkeypatch.setattr(bed.dt_util, "now", lambda now=now: now)
        request = Request(
            operation,
            part=args.get("x2") if address not in ("0x6bc8cc", "0x6b6d1c", "0x6b5e64") else None,
            date=date(args.get("x5", 2026), args.get("x6", 11), args.get("x7", 3)),
            report_type=args.get("x3", 0),
            enabled=args.get("enabled"),
        )
        await obj.sleep_request(operation, request)
        wire = b"".join(writes(coordinator))
        assert wire == sleep_packet(expected["id"], expected["cmd"], expected["val"]), (
            address,
            args,
        )
        seen.add(address)
    assert seen == set(routes)


@pytest.mark.parametrize("model", ("PARN", "RNRN", "V9RM"))
async def test_light_menu_ranges_are_exact_profile_choices(coordinator, model):
    profile = next(
        k
        for k, p in PRODUCTS.items()
        if p.label.startswith(model) and p.light_display.endswith("EightColorValue")
    )
    obj = controller(coordinator, profile)
    expected = (0, 1800, 3600, 14400, 28800) if model == "RNRN" else (0, 300, 600, 900)
    assert next(
        s for s in obj.controller_select_specs if s.key == "goodvibe_light_duration"
    ).options == tuple(map(str, expected))
    for seconds in expected:
        obj.validate_goodvibe_request(Request("light_duration", seconds=seconds))
    with pytest.raises(ValueError):
        obj.validate_goodvibe_request(Request("light_duration", seconds=1))
    for rgb in bed.p.EIGHT_COLORS:
        obj.validate_goodvibe_request(Request("light_color", rgb=rgb))
    with pytest.raises(ValueError):
        obj.validate_goodvibe_request(Request("light_color", rgb=(1, 2, 3)))


async def test_alias_choices_resolve_exact_accepted_endpoints(coordinator):
    from custom_components.adjustable_bed.beds.goodvibe.catalog import ALIAS_TARGETS

    assert len(ALIAS_TARGETS) == 27
    for alias, target in ALIAS_TARGETS.items():
        obj = controller(coordinator, alias)
        assert obj.product is PRODUCTS[target]
        assert obj.product.actions == PRODUCTS[target].actions
        assert alias in PROFILE_CHOICES


async def test_startup_queries_use_only_this_units_inline_vectors(coordinator, monkeypatch):
    from pathlib import Path

    vectors = json.loads((Path(__file__).parent / "fixtures/goodvibe/inline.json").read_text())

    async def pause(_seconds):
        return None

    monkeypatch.setattr(bed.asyncio, "sleep", pause)
    for service, (uuid, legacy) in bed.GATT.items():
        tx = SimpleNamespace(uuid=uuid, properties=["write", "write-without-response"], handle=1)
        rx = SimpleNamespace(uuid="notify", properties=["notify"], handle=2)
        coordinator.client.services = [SimpleNamespace(uuid=service, characteristics=[tx, rx])]
        coordinator.client.write_gatt_char.reset_mock()
        obj = bed.GoodVibeController(coordinator, profile="selector-0001")
        await obj.start_notify()
        expected = [
            bytes.fromhex(v[4])
            for v in vectors
            if v[0] in ("a660e1", "a66261", "a661e1") and v[1] == 0 and v[2] == legacy and not v[3]
        ]
        assert writes(coordinator) == expected
        await obj.stop_notify()


@pytest.mark.parametrize("kind,profile", ((2, "sleep_rm"), (3, "sleep_hj")))
@pytest.mark.parametrize("report_type", (1, 2))
async def test_report_service_completes_metadata_continuation_and_typed_payload(
    coordinator, kind, profile, report_type
):
    import gzip
    from datetime import date
    from pathlib import Path

    valid = dict(json.loads((Path(__file__).parent / "fixtures/goodvibe/schemas.json").read_text()))
    address = (
        ("0x6e0bf0" if kind == 2 else "0x6dc034")
        if report_type == 1
        else ("0x6e3860" if kind == 2 else "0x6ddeb0")
    )
    body = valid[address] if report_type == 1 else [valid[address]]
    packed = gzip.compress(json.dumps(body, separators=(",", ":")).encode())
    obj = controller(coordinator, profile)
    pending = bytearray()
    commands = []

    async def write(_char, data, **_kwargs):
        pending.extend(data)
        if len(pending) < 14 or len(pending) < 14 + int.from_bytes(pending[12:14], "little"):
            return
        request = json.loads(pending[14:])
        commands.append(request)
        pending.clear()
        if "allow" not in request["val"]:
            obj._notification(
                obj._link,
                obj._link.rx,
                bytearray(sleep_packet(request["id"], "q_report", {"fsize": len(packed)})),
            )
        else:
            for offset in range(0, len(packed), 20):
                chunk = packed[offset : offset + 20]
                obj._notification(
                    obj._link, obj._link.rx, bytearray((b"\x00" * 14 if kind == 3 else b"") + chunk)
                )

    coordinator.client.write_gatt_char.side_effect = write
    await obj.async_execute_goodvibe_request(
        Request("report", part=1, date=date(2026, 11, 3), report_type=report_type)
    )
    assert len(commands) == 2
    assert commands[0]["val"]["type"] == report_type
    assert commands[1]["val"]["allow"] == 1
    cache = obj.choices.events["report_cache"]
    assert isinstance(cache, dict)
    assert cache[f"1:{report_type}:2026:11:3"]
    assert obj._sleep.last is None
    assert obj._report_context is None


@pytest.mark.parametrize("profile,parts", (("sleep_rm", (1, 2)), ("sleep_hj", (11, 12, 13))))
async def test_part_setting_uses_admitted_caller_operands(coordinator, profile, parts):
    obj = controller(coordinator, profile)
    for part in parts:
        await obj.async_execute_goodvibe_request(Request("part", part=part))
        assert json.loads(b"".join(writes(coordinator))[14:])["val"] == part
        coordinator.client.write_gatt_char.reset_mock()
    for part in (0, 3, 10):
        with pytest.raises(ValueError, match="part"):
            obj.validate_goodvibe_request(Request("part", part=part))


async def test_type_two_time_response_chain_is_link_owned(coordinator):
    obj = controller(coordinator, "sleep_hj")

    async def execute(fn, **_kwargs):
        await fn(obj)

    coordinator.async_execute_controller_command.side_effect = execute
    obj._sleep.begin("s_time")
    link = obj._link
    obj._notification(
        link, link.rx, bytearray(sleep_packet(1, "s_time", {"error": 0, "ver": "1", "type": "HJ"}))
    )
    await asyncio.sleep(0)
    assert json.loads(b"".join(writes(coordinator))[14:])["cmd"] == "q_time"
    coordinator.client.write_gatt_char.reset_mock()
    gate = asyncio.get_running_loop().create_future()

    async def waiting(fn, **_kwargs):
        await gate
        await fn(obj)

    coordinator.async_execute_controller_command.side_effect = waiting
    obj._notification(link, link.rx, bytearray(sleep_packet(2, "q_time", {"ts": 1, "utc": "1"})))
    obj.on_disconnect()
    await asyncio.sleep(0)
    coordinator.client.write_gatt_char.assert_not_awaited()
    assert not obj.requires_persistent_connection


@pytest.mark.parametrize("legacy", (False, True))
async def test_inline_countdown_and_light_close_have_public_controller_paths(coordinator, legacy):
    key = next(k for k, v in PRODUCTS.items() if v.massage_timer and v.light)
    obj = controller(coordinator, key, legacy)
    spec = next(s for s in obj.controller_select_specs if s.key == "goodvibe_massage_timer")
    assert spec.options == ("0", "10", "20", "30")
    for value, code in ((0, 94), (10, 95), (20, 99), (30, 97)):
        await spec.select_fn(obj, str(value))
        assert writes(coordinator)[-1] == (
            bytes([code]) if legacy else bytes([110, 1, 0, code, (111 + code) & 255])
        )
    button = next(s for s in obj.controller_button_specs if s.key == "goodvibe_light_off")
    await button.press_fn(obj)
    assert writes(coordinator)[-1] == (b"\x75" if legacy else bytes.fromhex("6e010075e4"))


@pytest.mark.parametrize("model,seconds", (("FMRM", 900), ("RNRN", 14400), ("6BRM", 300)))
async def test_light_preference_defaults_survive_controller_replacement(
    coordinator, model, seconds
):
    key = next(k for k, v in PRODUCTS.items() if v.label == model)
    first = controller(coordinator, key)
    assert first.choices.events["light_duration"] == seconds
    first.choices.events["light_duration"] = 0
    first.on_disconnect()
    fresh = controller(coordinator, key)
    assert fresh.choices.events["light_duration"] == 0


async def test_bound_side_is_scoped_and_release_keeps_original_side(coordinator, monkeypatch):
    key = next(
        k
        for k, v in PRODUCTS.items()
        if 0 in v.sides
        and 1 in v.sides
        and any(not ACTIONS[d].local and ACTIONS[d].gesture == "shortPress" for d in v.actions)
    )
    obj = controller(coordinator, key)
    detail = next(
        d
        for d in obj.product.actions
        if not ACTIONS[d].local and ACTIONS[d].gesture == "shortPress"
    )
    monkeypatch.setattr(obj, "_delay", AsyncMock(return_value=True))
    spec = next(s for s in obj.controller_button_specs if s.key == "goodvibe_" + detail)
    with obj.side_scope("right"):
        await spec.press_fn(obj)
    assert writes(coordinator) == [
        action_frame(ACTIONS[detail], 1, False),
        bytes.fromhex("6e01016ede"),
    ]
    assert obj.command_side is None and obj.choices.side == 0


async def test_alarm_refresh_callback_requeries_and_rebuilds_observed_slots(coordinator):
    key = next(k for k, v in PRODUCTS.items() if v.repeat_alarm)
    obj = controller(coordinator, key)
    obj.choices.events["repeat_alarms"] = {"7": [7, 0, 0, 0, 0, 0]}

    async def execute(fn, **_kwargs):
        await fn(obj)

    coordinator.async_execute_controller_command.side_effect = execute
    obj._event("deviceRefreshRepeatAlarmListStatusEvent", None)
    await asyncio.sleep(0)
    assert writes(coordinator) == [bed.p.QUERIES["alarms"]]
    assert obj.choices.events["repeat_alarms"] == {}
    obj._event("deviceRepeatAlarmListStatusEvent", {"alarm_fields": [2, 0, 8, 30, 4, 1]})
    assert list(obj.choices.events["repeat_alarms"]) == ["2"]
    obj.on_disconnect()


async def test_unavailable_report_ends_transaction_without_using_stale_size(coordinator):
    from datetime import date

    obj = controller(coordinator, "sleep_hj")
    obj._sleep.report_size = 512
    incoming = bytearray()

    async def write(_char, data, **_kwargs):
        incoming.extend(data)
        if len(incoming) < 14 or len(incoming) < 14 + int.from_bytes(incoming[12:14], "little"):
            return
        obj._notification(
            obj._link, obj._link.rx, bytearray(sleep_packet(1, "q_report", {"fsize": 0}))
        )

    coordinator.client.write_gatt_char.side_effect = write
    with pytest.raises(ConnectionError, match="No sleep report"):
        await obj.async_execute_goodvibe_request(Request("report", part=1, date=date(2026, 11, 3)))
    assert obj._sleep.report_size == 0 and obj._report_context is None


@pytest.mark.parametrize("constant", ("NaN", "Infinity", "-Infinity"))
async def test_non_json_numeric_constants_cannot_replace_sleep_state(coordinator, constant):
    obj = controller(coordinator, "sleep_hj")
    obj._sleep.begin("q_realtime")
    obj.choices.realtime["L"].heart = "60"
    raw = (
        "{" + '"id":1,"cmd":"q_realtime","val":{"L":[0,1,' + constant + ',12,0],"R":null}}'
    ).encode()
    header = bytearray(14)
    header[12] = len(raw)
    obj._notification(obj._link, obj._link.rx, header + raw)
    assert obj.choices.realtime["L"].heart == "60"
    assert obj._rejection is not None
