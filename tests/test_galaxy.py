"""Galaxy product, setup, public action and connection-state contracts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.adjustable_bed.beds.galaxy.catalog import (
    CATALOG,
    PICKERS,
    PRODUCTS,
    PROFILE_CHOICES,
    RUNTIMES,
    resolve_product,
)
from custom_components.adjustable_bed.beds.goodvibe import controller as bed
from custom_components.adjustable_bed.beds.goodvibe.services import Request
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.richmat_catalog import Action
from tests.test_galaxy_vectors import fixture
from tests.test_goodvibe import controller as goodvibe_controller
from tests.test_goodvibe import coordinator as coordinator
from tests.test_goodvibe import writes


def controller(c, profile="6BRM", single=False):
    obj = bed.GoodVibeController(c, profile=profile, catalog=CATALOG)
    obj._link = goodvibe_controller(c)._link
    obj._link = replace(obj._link, legacy=single)
    obj._pace = AsyncMock(return_value=True)
    c.client.write_gatt_char = AsyncMock()
    return obj


async def test_every_profile_builds_and_owns_only_its_side_configuration(hass, coordinator):
    from custom_components.adjustable_bed.app_profiles import (
        hidden_generic_fields,
        per_side_profile,
    )
    from custom_components.adjustable_bed.const import CONF_MOTOR_COUNT
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.detection import bed_type_choice, get_bed_type_options
    from custom_components.adjustable_bed.setup_questions import setup_profile
    from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type

    rows = {row["value"]: row["label"] for row in get_bed_type_options()}
    assert "Galaxy Bed Control" in rows["galaxy"]
    spec = setup_profile("galaxy")
    assert spec is not None
    assert set(spec.questions[0].options({})) == PROFILE_CHOICES.keys()
    assert spec.questions[0].searchable
    for key in PROFILE_CHOICES:
        assert bed_type_choice("galaxy", key) not in rows
        assert is_valid_variant_for_bed_type("galaxy", key)
        assert CONF_MOTOR_COUNT in hidden_generic_fields("galaxy", key)
        assert per_side_profile("galaxy", key).variant_owned
        coordinator.entry.data = {}
        obj = await create_controller(coordinator, "galaxy", key, coordinator.client)
        assert obj.product == PRODUCTS[resolve_product(key)]
        assert obj.catalog.key == "galaxy"
        assert obj.choices.release == RUNTIMES[obj.product_key].initial_release
        assert all(
            s.hold is not None
            for s in obj.controller_button_specs
            if s.key.removeprefix("goodvibe_") in CATALOG.actions
            and not CATALOG.actions[s.key.removeprefix("goodvibe_")].local
        )
        assert set(obj.execution.hold_controls or ()) <= set(obj.held_control_options)
    for key, targets in PICKERS.items():
        assert {resolve_product(f"{key}>{target}") for target in targets} == set(targets)
        with pytest.raises(ValueError):
            resolve_product(key)
        with pytest.raises(ValueError):
            resolve_product(key + ">BAD")
    for key in ("FWRM", "WFRM", "GKRN", "BAD", "", "sleep_rm", "sleep_hj"):
        with pytest.raises(ValueError):
            resolve_product(key)


async def test_runtime_press_and_memory_vectors(coordinator):
    for vector in fixture("runtime"):
        if vector["kind"] != "press":
            continue
        i, e = vector["inputs"], vector["expected"]
        obj = controller(coordinator)
        obj.product = replace(PRODUCTS["6BRM"], label=i["code"], actions=("vector",))
        for k, v in i["state"].items():
            setattr(obj.choices, k, v)
        name = "deviceFunctionItem" + i["action"]
        action = Action(
            name,
            "shortPress",
            i["action"] in ("PhoneLight", "Clock", "Voice"),
            i.get("flag43", False),
            i.get("flag47", False),
            True,
            i["short"],
            i.get("long", 0),
            i.get("alternate", i["short"]),
        )
        obj.actions = {"vector": action}
        obj._delay = AsyncMock(return_value=True)
        coordinator.client.write_gatt_char.reset_mock()
        if action.local:
            with pytest.raises(ValueError):
                await obj.press("vector", 0)
            assert not writes(coordinator)
        else:
            await obj.press("vector", 0)
            assert [x.hex() for x in writes(coordinator)][0:1] == e["calls"], vector["id"]
        assert {k: getattr(obj.choices, k) for k in i["state"]} == e["state"], vector["id"]


async def test_runtime_initial_selection_and_settings_vectors(coordinator):
    for vector in fixture("runtime"):
        i, e = vector["inputs"], vector["expected"]
        if vector["kind"] == "selection":
            if i["route"] != "success":
                with pytest.raises(ValueError):
                    resolve_product(i["code"])
                continue  # Invalid HA configuration is refused instead of installing Android's sentinel.
            obj = controller(coordinator, i["code"])
            assert {k: getattr(obj.choices, k) for k in e} == e, vector["id"]
        elif vector["kind"] == "settings":
            obj = controller(coordinator)
            obj.product = replace(
                PRODUCTS["6BRM"],
                label=i["code"],
                alarms=("alarm",) if i["alarms"] else (),
                light=i["light"],
                sleep="deviceSleepMonitoringBle" if i["ble_sleep"] else "deviceSleepMonitoringNone",
            )
            runtime = replace(
                RUNTIMES["6BRM"],
                code=i["code"],
                snore=i["code"] in ("HNRN", "HQRN", "HSRN", "HURN", "M7RN", "MJRN"),
            )
            obj.catalog = replace(CATALOG, runtimes={obj.product_key: runtime})
            obj._menus = {"alarm"} if i["code"] == "PNRN" else set()
            obj.choices.events.pop("sleep_advertisement_name", None)
            for event in i["events"]:
                if not event.get("mounted", True):
                    continue
                name = {
                    "clock": "deviceCharacteristicsSubscriptionClockEvent",
                    "light": "deviceCharacteristicsSubscriptionLightEvent",
                    "sleep": "deviceSleepAdvNameEvent",
                }[event["event"]]
                obj._event(name, list(bytes.fromhex(event["hex"])) if "hex" in event else None)
            assert obj._menus == set(e["menus"]) - {"icon", "name", "config"}, vector["id"]
            assert obj.choices.events.get("sleep_advertisement_name", "") == e["sleep_name"], (
                vector["id"]
            )
        elif vector["kind"] == "notification_press":
            obj = controller(coordinator)
            for k, v in i["state"].items():
                setattr(obj.choices, k, v)
            obj._normal.feed(codec.record_20_len(11, i["sub"], 2, (0, i["byte"])))
            assert {k: getattr(obj.choices, k) for k in i["state"]} == e["state"]


async def test_countdown_owned_vectors_send_once_without_release(coordinator):
    for vector in fixture("countdown"):
        i, e = vector["inputs"], vector["expected"]
        obj = controller(coordinator, i["code"], i["nordic"])
        coordinator.client.write_gatt_char.reset_mock()
        if i["commit"] and i["value"] not in (0, 1, 2, 3):
            with pytest.raises(ValueError):
                await obj.async_execute_goodvibe_request(
                    Request("massage_timer", value=i["value"] * 10)
                )
            assert not writes(coordinator) and not e["calls"]
        elif i["commit"]:
            await obj.async_execute_goodvibe_request(
                Request("massage_timer", value=i["value"] * 10)
            )
            assert [x.hex() for x in writes(coordinator)] == [
                bytes.fromhex(x["expected_bytes"]).hex() for x in e["calls"]
            ], vector["id"]
        else:
            assert not writes(coordinator)  # Drag changes are not service commits.


async def test_bed_setting_builders_and_reported_capability_preflight(coordinator):
    obj = controller(coordinator, "HNRN")
    when = datetime(2026, 11, 10, 7, 30, tzinfo=ZoneInfo("Europe/Oslo"))
    request = Request(
        "repeat", action=obj.product.alarms[0], when=when, alarm_id=1, weekdays=(0, 6), enabled=True
    )
    coordinator.client.is_connected = False
    request.plan(obj)  # A cold preflight checks product gates, then live dispatch checks the reply.
    coordinator.client.is_connected = True
    with pytest.raises(ValueError, match="advertised"):
        request.validate(obj)
    obj._event("deviceCharacteristicsSubscriptionClockEvent", None)
    request.validate(obj)
    assert request.frames(obj)[0][:6] == bytes.fromhex("6e0d20050101")
    obj._event("deviceSleepAdvNameEvent", list(b"RM-A"))
    Request("snore_count", value=3).validate(obj)
    assert Request("snore_count", value=3).frames(obj) == (bytes.fromhex("6e0a20060501010003a8"),)
    obj.on_disconnect()
    with pytest.raises(ValueError, match="advertised"):
        request.validate(obj)
    with pytest.raises(ValueError):
        Request("report").plan(controller(coordinator, "HNRN"))


async def test_startup_uses_product_queries_and_stale_replies_are_ignored(coordinator):
    obj = controller(coordinator, "HNRN")
    link = obj._link
    with (
        patch.object(bed, "select_link", return_value=link),
        patch.object(bed.asyncio, "sleep", new=AsyncMock()),
    ):
        await obj.start_notify()
    frames = writes(coordinator)
    assert frames[0][:6] == bytes.fromhex("6e0c20080201")
    assert frames[1][:6] == bytes.fromhex("6e0d20080301")
    assert frames[2] == bytes.fromhex("6e0820060300009f")
    assert frames[3:] == [bytes.fromhex("6e08010178"), bytes.fromhex("6e0a000179")]
    obj.on_disconnect()
    obj._notification(link, link.rx, bytearray.fromhex("6e09010078"))
    assert not obj._menus


async def test_cancelled_hold_releases_captured_side_and_link(coordinator):
    obj = controller(coordinator, "6BRM")
    detail = next(k for k in obj.product.actions if obj.actions[k].gesture == "sustainPress")
    started = asyncio.Event()

    async def delay(_ms):
        if started.is_set():
            obj.choices.side = 1  # UI changes cannot redirect this gesture's cleanup.
            coordinator.cancel_command.set()
            return False
        started.set()
        return True

    obj._delay = delay
    await obj.press(detail, 1000)
    assert writes(coordinator)[-1] == bytes.fromhex("6e01006edd")


def test_gatt_records_and_conflicting_service_framing_stay_bound_to_tx():
    from types import SimpleNamespace

    from tests.test_galaxy_vectors import fixture

    for row, key in zip(fixture("gatt"), CATALOG.wire.transports, strict=True):
        transport = codec.TRANSPORTS[key]
        assert (transport.service_uuid, transport.write_uuid, transport.notify_uuid) == (
            row["service"],
            row["write_uuid"],
            row["declared_notify_uuid"],
        )

    def service(key):
        transport = codec.TRANSPORTS[key]
        tx = SimpleNamespace(uuid=transport.write_uuid, properties=["write"], handle=1)
        rx = SimpleNamespace(uuid=transport.notify_uuid, properties=["notify"], handle=2)
        return SimpleNamespace(uuid=transport.service_uuid, characteristics=[tx, rx])

    first, last = service("w1"), service("n1")
    link = bed.select_link(SimpleNamespace(services=[first, last]), 1, bind_framing=True)
    assert link.tx is first.characteristics[0] and not link.legacy
    # A write-without-response-only characteristic is not admitted by Galaxy.
    first.characteristics[0].properties = ["write-without-response"]
    link = bed.select_link(SimpleNamespace(services=[first, last]), 1, bind_framing=True)
    assert link.tx is last.characteristics[0] and link.legacy


async def test_pacing_cancellation_and_replaced_links_cannot_submit(coordinator):
    obj = controller(coordinator)
    obj._pace = bed.GoodVibeController._pace.__get__(obj)
    obj._last_write = asyncio.get_running_loop().time()

    async def cancelled(_milliseconds):
        coordinator.cancel_command.set()
        return False

    obj._delay = cancelled
    assert not await obj._send(b"\x24")
    assert not writes(coordinator)
    coordinator.cancel_command.clear()

    async def replaced(_cleanup):
        obj._link = replace(obj._link, legacy=True)
        return True

    obj._pace = replaced
    with pytest.raises(ConnectionError, match="replaced"):
        await obj._send(b"\x24")
    assert not writes(coordinator)


async def test_public_service_has_only_bed_operations_and_checks_app_before_execution(
    hass, coordinator
):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.beds.goodvibe import services
    from custom_components.adjustable_bed.const import DOMAIN

    services.async_register_goodvibe_services(hass)
    obj = controller(coordinator, "D1RM")

    async def execute(_targets, _cls, _description, call, *, validate):
        validate(obj)
        await call(obj)

    with (
        patch.object(services, "_preflight_and_execute", side_effect=execute),
        patch.object(services, "_call_targets", return_value=[]),
    ):
        await hass.services.async_call(
            DOMAIN,
            "galaxy",
            {"device_id": ["bed"], "operation": "massage_timer", "value": 10},
            blocking=True,
        )
        assert writes(coordinator) == [bytes.fromhex("6e01005fce")]
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "goodvibe",
                {"device_id": ["bed"], "operation": "massage_timer", "value": 10},
                blocking=True,
            )
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        services.GALAXY_SCHEMA({"device_id": ["bed"], "operation": "report"})


async def test_alarm_enable_preserves_observed_fields_and_freezes_the_plan(coordinator):
    obj = controller(coordinator, "HNRN")
    obj._menus.add("alarm")
    with pytest.raises(ValueError, match="Query"):
        Request("enable_alarm", alarm_id=3, enabled=False).plan(obj)
    obj.choices.events["repeat_alarms"] = {"3": [3, 17, 7, 30, 2, 131]}
    request = Request("enable_alarm", alarm_id=3, enabled=False).plan(obj)
    obj.choices.events["repeat_alarms"]["3"][2] = 9
    await obj.async_execute_goodvibe_request(request)
    assert writes(coordinator) == [bytes.fromhex("6e0d200501010311071e02825f")]


async def test_frozen_generic_gesture_sequences_and_safe_side_capture(coordinator):
    for vector in fixture("runtime"):
        if vector["kind"] != "gesture":
            continue
        i, e = vector["inputs"], vector["expected"]
        if i["operate"] == "short_long_sustain":
            assert not any(
                a.gesture == "shortAndLongSustainPress" for a in CATALOG.actions.values()
            )
            continue  # Unused declaration, explicitly dispositioned in the local ledger.
        obj = controller(coordinator, single=i["service"] == "one_byte")
        obj.product = replace(PRODUCTS["6BRM"], actions=("vector",), sides=(0, 1, 2))
        obj.choices.side = i["side"]
        mode = {
            "short": "shortPress",
            "sustain": "sustainPress",
            "short_long": "shortAndLongPress",
        }[i["operate"]]
        obj.actions = {
            "vector": Action(
                "deviceFunctionItemHeadUp",
                mode,
                False,
                False,
                False,
                False,
                i["short"],
                i["long"],
                i["short"],
            )
        }
        obj._delay = AsyncMock(return_value=True)
        duration = (
            3100
            if "threshold" in i["events"]
            else 100 * i["events"].count("tick")
            if mode == "sustainPress"
            else 50
        )
        await obj.press("vector", duration)
        expected = e["calls"] if vector["id"] != "R-025" else ["6e01002493", "6e01006edd"]
        assert [frame.hex() for frame in writes(coordinator)] == expected, vector["id"]


async def test_public_bulk_preflight_rejects_missing_live_capability_before_writes(hass):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.beds.goodvibe import services
    from custom_components.adjustable_bed.const import DOMAIN
    from tests.test_goodvibe_ha import runtime

    targets = [
        runtime(hass, "selector-0001", address=f"AA:BB:CC:DD:EE:{suffix}")
        for suffix in ("81", "82")
    ]
    for target in targets:
        link = target._controller._link
        target._controller = bed.GoodVibeController(target, profile="HNRN", catalog=CATALOG)
        target._controller._link = link
        target._client.write_gatt_char = AsyncMock()
    targets[0]._controller._menus.add("light")
    services.async_register_goodvibe_services(hass)
    try:
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(target, "both") for target in targets], []),
            ),
            pytest.raises(ServiceValidationError, match="advertised"),
        ):
            await hass.services.async_call(
                DOMAIN, "galaxy", {"device_id": ["a", "b"], "operation": "light_off"}, blocking=True
            )
        for target in targets:
            target._client.write_gatt_char.assert_not_awaited()
    finally:
        for target in targets:
            target._client.is_connected = False
            await target.async_shutdown()


async def test_forced_long_buttons_distinguish_their_names_and_operands(coordinator):
    obj = controller(coordinator, "BRRM")
    obj.choices.release = False
    obj._delay = AsyncMock(return_value=True)
    specs = [
        spec
        for spec in obj.controller_button_specs
        if spec.key.removeprefix("goodvibe_") in obj.actions
        and obj.actions[spec.key.removeprefix("goodvibe_")].label == "deviceFunctionItemZeroGravity"
    ]
    assert {spec.name for spec in specs} == {"Zero Gravity", "Zero Gravity (long action)"}
    operands = {}
    for spec in specs:
        assert spec.translation_placeholders["action"] == spec.name
        coordinator.client.write_gatt_char.reset_mock()
        await obj.press(spec.key.removeprefix("goodvibe_"), 0)
        operands[spec.name] = writes(coordinator)[0].hex()
    assert operands == {"Zero Gravity": "6e010045b4", "Zero Gravity (long action)": "6e010066d5"}


def test_galaxy_hints_preserve_exclusions_and_confident_receiver_detection():
    from custom_components.adjustable_bed.config_flow import _confident_auto_detect
    from custom_components.adjustable_bed.const import BED_TYPE_LINAK, LINAK_CONTROL_SERVICE_UUID
    from custom_components.adjustable_bed.detection import detect_bed_type, detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    excluded = _make_service_info(
        "COOL Headphones", service_uuids=["0000ffe0-0000-1000-8000-00805f9b34fb"]
    )
    result = detect_bed_type_detailed(excluded)
    assert result.bed_type is None and "excluded:headphone" in result.signals
    assert detect_bed_type(excluded) is None
    dedicated = _make_service_info("BED-Linak", service_uuids=[LINAK_CONTROL_SERVICE_UUID])
    result = detect_bed_type_detailed(dedicated)
    assert result.bed_type == BED_TYPE_LINAK and result.confidence == 1.0
    assert "galaxy" in result.ambiguous_types
    assert _confident_auto_detect(result) == BED_TYPE_LINAK
    from custom_components.adjustable_bed.detection import DetectionResult

    candidate = _make_service_info("prefixCOOL", service_uuids=[])
    # Isolate Galaxy enrichment from the other apps sharing the same scan keywords.
    with patch(
        "custom_components.adjustable_bed.detection._detect_bed_type_with_app_candidates",
        return_value=DetectionResult(None, 0.0, []),
    ):
        result = detect_bed_type_detailed(candidate)
        assert result.bed_type == "galaxy" and result.confidence < 0.7
        assert detect_bed_type(candidate) is None
        assert _confident_auto_detect(result) is None
