"""Canonical-v2 routes and user surfaces for the explicit Sleepy's app profile."""

from __future__ import annotations

import asyncio
import csv
import re
from collections import Counter
from collections.abc import Awaitable
from pathlib import Path
from types import SimpleNamespace
from typing import TypeVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.sleepys_app import SleepysEliteAppController
from custom_components.adjustable_bed.beds.sleepys_app_routes import (
    CANONICAL_ROUTE_SHA256,
    ROUTES,
)
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.const import (
    BED_TYPE_SLEEPYS_ELITE_APP,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_PULSE_USER_SET,
    CONF_SLEEPYS_ELITE_SELECTOR,
    SLEEPYS_ELITE_SELECTORS,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES

FIXTURES = Path(__file__).parent / "fixtures"
_ROUTE_FIXTURE = FIXTURES / "sleepys_elite_routes_v2.tsv"
_DYNAMIC_FIXTURE = FIXTURES / "sleepys_elite_dynamic_v2.tsv"
_TIMING_FIXTURE = FIXTURES / "sleepys_elite_timing_v2.tsv"
_PARSER_FIXTURE = FIXTURES / "sleepys_elite_parser_v2.tsv"
_EXPECTED_SHA256 = "d5cc166ef68ca07d81b9112f16f4143d0851409ed2fe5086ff2fe10b0a7db138"
_POSITION_SLIDER_SELECTORS = ("none", "BOX15", "BOX24", "BOX1220", "BOX1221", "BOX2422", "BOX2442")
_VOICE_SELECTORS = ("BOX25", "BOX25_STAR")
_POSITION_KEY_TO_AXIS = {
    "0x2b": "axis_0",
    "0x33": "axis_1",
    "0x3b": "axis_2",
}
_T = TypeVar("_T")


class _VirtualClock:
    """Advance controller protocol timers without waiting on wall time."""

    def __init__(self) -> None:
        self.now = 0.0
        self._sleepers: list[tuple[float, asyncio.Future[None]]] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        future = asyncio.get_running_loop().create_future()
        sleeper = (self.now + seconds, future)
        self._sleepers.append(sleeper)
        try:
            await future
        finally:
            self._sleepers.remove(sleeper)

    async def run(self, awaitable: Awaitable[_T]) -> _T:
        task = asyncio.ensure_future(awaitable)
        for _ in range(1_000):
            for _ in range(12):
                await asyncio.sleep(0)
            if task.done():
                return task.result()
            pending = [deadline for deadline, future in self._sleepers if not future.done()]
            if not pending:
                continue
            self.now = min(pending)
            for deadline, future in tuple(self._sleepers):
                if deadline <= self.now and not future.done():
                    future.set_result(None)
        raise AssertionError("virtualized operation did not settle")


def _tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file, delimiter="\t"))


def _controller(selector: str, *, connected: bool = False) -> SleepysEliteAppController:
    client = SimpleNamespace(is_connected=True, services=[]) if connected else None
    coordinator = SimpleNamespace(
        address="AA:BB:CC:DD:EE:FF",
        cancel_command=asyncio.Event(),
        client=client,
        record_command_trace=MagicMock(),
        handle_controller_state_updates=MagicMock(),
    )
    return SleepysEliteAppController(coordinator, selector)


def _gatt_client(
    controller: SleepysEliteAppController,
) -> tuple[SimpleNamespace, dict[str, object]]:
    setup = ROUTES[("keepConnect", controller.selector)]
    notify_service_uuid, notify_char_uuid = setup.notify_target.split("/", 1)
    destinations = {
        (setup.write_service, setup.write_characteristic),
        (notify_service_uuid, notify_char_uuid),
    }
    services: dict[str, SimpleNamespace] = {}
    characteristics: dict[str, object] = {}
    for service_uuid, characteristic_uuid in destinations:
        service_key = service_uuid.casefold()
        service = services.get(service_key)
        if service is None:
            service = SimpleNamespace(uuid=service_uuid, characteristics=[])
            services[service_key] = service
        char = SimpleNamespace(uuid=characteristic_uuid, handle=len(characteristics) + 1)
        service.characteristics.append(char)
        characteristics[characteristic_uuid.casefold()] = char
        service.get_characteristic = lambda uuid, chars=service.characteristics: next(
            (item for item in chars if item.uuid.casefold() == uuid.casefold()), None
        )
    client = SimpleNamespace(
        is_connected=True,
        services=list(services.values()),
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )
    return client, characteristics


def _field_values(state: str) -> dict[str, object]:
    values: dict[str, object] = {}
    for field_id, raw_value in re.findall(r"(0x[0-9a-fA-F]+)=([^,;]+)", state):
        if raw_value == "True":
            value: object = True
        elif raw_value == "False":
            value = False
        else:
            value = int(raw_value)
        values[field_id.lower()] = value
    return values


def _changed_field_ids(value: str) -> set[str]:
    # Duplicate vectors record the first changed write then an unchanged replay.
    first = value.split(";", maxsplit=1)[0]
    return {item.lower() for item in re.findall(r"0x[0-9a-fA-F]+", first)}


def _selector_for_parser_branch(branch: str) -> str:
    if branch.startswith("box15"):
        return "BOX15"
    if branch.startswith("box25"):
        return "BOX25"
    return "BOX24"


def test_canonical_v2_routes_match_all_550_selector_rows() -> None:
    rows = _tsv(_ROUTE_FIXTURE)
    assert CANONICAL_ROUTE_SHA256 == _EXPECTED_SHA256
    assert len(rows) == 550
    assert Counter(row["disposition"] for row in rows) == {
        "IMPLEMENTED": 496,
        "ALREADY_IMPLEMENTED": 1,
        "EXCLUDED": 53,
    }
    assert len(ROUTES) == 497

    for row in rows:
        key = (row["builder"], row["selector"])
        route = ROUTES.get(key)
        if row["disposition"] == "EXCLUDED":
            assert route is None, key
            continue

        assert route is not None, key
        logical_values = (
            ()
            if row["final_logical_values"] == "[]"
            else tuple(map(int, row["final_logical_values"].split()))
        )
        assert route.logical_values == logical_values, key
        assert route.payload == bytes.fromhex(row["wire_hex"]), key
        assert route.write_service == row["write_service"], key
        assert route.write_characteristic == row["write_characteristic"], key
        assert route.notify_target == row["notify_target"], key
        assert route.write_with_response is (row["write_mode"] == "with_response"), key
        assert route.response_parser == row["response_parser"], key
        assert row["packet_model_version"] == "2"

    assert not any(builder in {"setAlarm", "queryAlarm"} for builder, _ in ROUTES)


async def test_empty_box15_actions_preserve_the_writer_attempts_without_filling_bytes() -> None:
    controller = _controller("BOX15")
    client, characteristics = _gatt_client(controller)
    controller._coordinator.client = client

    await controller.send("meanwhileStrengthReduce")
    await controller.send("massageMode")
    calls = client.write_gatt_char.await_args_list
    assert [call.args[1] for call in calls] == [bytes.fromhex("5A 0B 00 A5"), b"", b""]
    assert [call.kwargs["response"] for call in calls] == [True, False, False]
    assert all(call.args[0] is characteristics["ffe9"] for call in calls)


@pytest.mark.parametrize("selector", SLEEPYS_ELITE_SELECTORS)
async def test_setup_write_and_notify_use_each_selector_gatt_route(selector: str) -> None:
    controller = _controller(selector)
    client, characteristics = _gatt_client(controller)
    controller._coordinator.client = client

    await controller.start_notify()

    setup = ROUTES[("keepConnect", selector)]
    notify_service_uuid, notify_char_uuid = setup.notify_target.split("/", 1)
    assert client.write_gatt_char.await_count == 1
    write_call = client.write_gatt_char.await_args
    assert write_call.args[0] is characteristics[setup.write_characteristic.casefold()]
    assert write_call.args[1] == bytes.fromhex("5A 0B 00 A5")
    assert write_call.kwargs["response"] is True
    assert client.start_notify.await_count == 1
    assert client.start_notify.await_args.args[0] is characteristics[notify_char_uuid.casefold()]
    assert client.start_notify.await_args.args[0].uuid.casefold() == notify_char_uuid.casefold()
    assert any(
        service.uuid.casefold() == notify_service_uuid.casefold() for service in client.services
    )


async def test_app_selector_belongs_to_each_physical_side_and_factory_does_not_infer_it() -> None:
    profile = per_side_profile(BED_TYPE_SLEEPYS_ELITE_APP, None)
    assert profile is not None
    assert CONF_SLEEPYS_ELITE_SELECTOR in profile.keys

    class FakeHass:
        async def async_add_import_executor_job(self, fn, *args):
            return fn(*args)

    async def make(selector: str | None) -> SleepysEliteAppController:
        data = {} if selector is None else {CONF_SLEEPYS_ELITE_SELECTOR: selector}
        coordinator = SimpleNamespace(
            hass=FakeHass(),
            entry=SimpleNamespace(data=data, options={}),
            address="AA:BB:CC:DD:EE:FF",
            client=None,
            cancel_command=asyncio.Event(),
        )
        controller = await create_controller(
            coordinator,
            BED_TYPE_SLEEPYS_ELITE_APP,
            None,
            None,
        )
        assert isinstance(controller, SleepysEliteAppController)
        return controller

    left, right = await asyncio.gather(make("BOX15"), make("BOX25"))
    assert left.selector == "BOX15"
    assert right.selector == "BOX25"
    with pytest.raises(ValueError, match="explicit selector"):
        await make(None)


async def test_manual_app_profile_is_findable_and_persists_selector_capabilities(
    hass: HomeAssistant,
) -> None:
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._manual_data = {CONF_NAME: "Sleepy's test bed"}
    finish = AsyncMock(return_value={"step_id": "verify_connection"})

    with patch.object(flow, "_finish_with_verify", finish):
        form = await flow.async_step_sleepys_elite_app()
        marker = next(
            marker
            for marker in form["data_schema"].schema
            if marker.schema == CONF_SLEEPYS_ELITE_SELECTOR
        )
        selector = form["data_schema"].schema[marker]
        assert marker.default() == "none"
        assert {option["value"] for option in selector.config["options"]} == set(
            SLEEPYS_ELITE_SELECTORS
        )
        assert BED_TYPE_DISPLAY_NAMES[BED_TYPE_SLEEPYS_ELITE_APP] == (
            "Sleepy's Elite app (explicit selector)"
        )

        result = await flow.async_step_sleepys_elite_app({CONF_SLEEPYS_ELITE_SELECTOR: "BOX25"})

    assert result == {"step_id": "verify_connection"}
    assert flow._manual_data == {
        CONF_NAME: "Sleepy's test bed",
        CONF_SLEEPYS_ELITE_SELECTOR: "BOX25",
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: False,
        CONF_MOTOR_PULSE_USER_SET: False,
    }
    finish.assert_awaited_once_with(flow._manual_data, "Sleepy's test bed")


def test_ha_surfaces_follow_proven_selector_and_feature_domains() -> None:
    for selector in SLEEPYS_ELITE_SELECTORS:
        controller = _controller(selector)
        button_keys = {spec.key for spec in controller.controller_button_specs}
        number_keys = {spec.key for spec in controller.controller_number_specs}
        select_keys = {spec.key for spec in controller.controller_select_specs}
        state_keys = {spec.key for spec in controller.controller_state_sensor_specs}

        assert not any("alarm" in key.casefold() for key in button_keys | number_keys | select_keys)
        assert "sleepys_app_query_position" in button_keys
        assert ("sleepys_app_massage_query" in button_keys) is (selector in _VOICE_SELECTORS)
        assert ("sleepys_app_color_code" in number_keys) is (selector in _VOICE_SELECTORS)
        assert ("sleepys_app_massage_timer_code" in select_keys) is (selector in _VOICE_SELECTORS)

        if selector in (*_POSITION_SLIDER_SELECTORS, *_VOICE_SELECTORS):
            assert {f"sleepys_app_target_axis_{axis}" for axis in range(3)} <= number_keys
        else:
            assert not any(key.startswith("sleepys_app_target_axis_") for key in number_keys)

        if selector in _VOICE_SELECTORS:
            assert {
                f"sleepys_app_voice_axis_{axis}_{target}"
                for axis in range(3)
                for target in (0, 100)
            } <= button_keys
            assert {
                "sleepys_app_voice_brightness_down",
                "sleepys_app_voice_brightness_up",
            } <= button_keys
            assert {"sleepys_app_field_0x43", "sleepys_app_field_0x5f"} <= state_keys
        else:
            assert not any(key.startswith("sleepys_app_voice_axis_") for key in button_keys)

        assert any(key.startswith("sleepys_app_field_") for key in state_keys)


async def test_dynamic_vectors_retain_frozen_provenance_and_current_route_counts() -> None:
    rows = _tsv(_DYNAMIC_FIXTURE)
    assert len(rows) == 60
    historical_counts = Counter(row["caller_domain_status"] for row in rows)
    assert historical_counts == {
        "APP_UI_SELECTOR_PROVEN": 15,
        "APP_VOICE_SELECTOR_PROVEN": 2,
        "BUILDER_ROUTE_ONLY": 42,
        "APP_UI_RESELECTION_CONDITIONAL": 1,
    }

    current_statuses = {
        (row["family"], row["selector"]): (
            "APP_UI_SELECTOR_PROVEN"
            if row["family"] == "changePosition" and row["selector"] in _VOICE_SELECTORS
            else row["caller_domain_status"]
        )
        for row in rows
    }
    current_counts = Counter(current_statuses.values())
    assert {
        key: current_counts[key]
        for key in (
            "APP_UI_SELECTOR_PROVEN",
            "APP_VOICE_SELECTOR_PROVEN",
            "BUILDER_ROUTE_ONLY",
            "APP_UI_RESELECTION_CONDITIONAL",
        )
    } == {
        "APP_UI_SELECTOR_PROVEN": 17,
        "APP_VOICE_SELECTOR_PROVEN": 0,
        "BUILDER_ROUTE_ONLY": 42,
        "APP_UI_RESELECTION_CONDITIONAL": 1,
    }

    selectors = {
        selector: _controller(selector, connected=True) for selector in SLEEPYS_ELITE_SELECTORS
    }
    for row in rows:
        key = (row["family"], row["selector"])
        controller = selectors[row["selector"]]
        if current_statuses[key] in {"BUILDER_ROUTE_ONLY", "APP_UI_RESELECTION_CONDITIONAL"}:
            assert key not in ROUTES
            continue

        route = ROUTES[key]
        builder = row["family"]
        values = dict(
            part.split("=", maxsplit=1) for part in row["sample_builder_input"].split(",")
        )
        if builder == "changePosition":
            control, value = f"position_axis_{values['axis']}", values["position"]
        else:
            control, value = (
                {
                    "changeLightBrightness": "light_level",
                    "changeLightColorLevel": "light_color_code",
                    "changeMassageTime": "massage_timer_code",
                    "changeMassageIntensity": "massage_intensity_all",
                }[builder],
                values["value"],
            )
        encoded_route = controller._value_route(control, float(value))
        assert encoded_route.builder == builder
        assert encoded_route.selector == row["selector"]
        assert encoded_route.logical_values == tuple(map(int, row["final_logical_values"].split()))
        assert encoded_route.payload == bytes.fromhex(row["wire_hex"])
        assert encoded_route.write_service == row["write_service"]
        assert encoded_route.write_characteristic == row["write_characteristic"]
        assert encoded_route.notify_target == row["notify_target"]
        assert encoded_route.write_with_response is (row["write_mode"] == "with_response")
        assert encoded_route.response_parser == route.response_parser
        assert row["packet_model_version"] == "2"


@pytest.mark.parametrize(
    ("selector", "axis", "target", "payload"),
    [
        ("none", 0, 0, "03 F0 00 00 00"),
        ("BOX2442", 2, 100, "03 F0 02 64 00"),
        ("BOX25", 1, 50, "03 F0 01 32 00"),
        ("BOX25", 1, 100, "03 F0 01 64 00"),
        ("BOX25_STAR", 1, 0, "5A F0 03 01 00 00 A5"),
    ],
)
async def test_dynamic_position_edges_and_voice_targets(
    selector: str, axis: int, target: int, payload: str
) -> None:
    controller = _controller(selector, connected=True)
    controller._write_route = AsyncMock()
    await controller.set_position_target(axis, target)
    assert controller._write_route.await_args_list[0].args[0].payload == bytes.fromhex(payload)


@pytest.mark.parametrize(
    ("operation", "args"),
    [
        ("set_position_target", (0, -1)),
        ("set_position_target", (0, 101)),
        ("set_position_target", (0, 200)),
    ],
)
async def test_dynamic_position_slider_rejects_out_of_domain_targets(operation, args) -> None:
    controller = _controller("BOX15", connected=True)
    controller._write_route = AsyncMock()
    with pytest.raises(ValueError):
        await getattr(controller, operation)(*args)
    controller._write_route.assert_not_awaited()


async def test_dynamic_domains_reject_noncaller_and_feature_values() -> None:
    unsupported = _controller("BOX3633", connected=True)
    unsupported._write_route = AsyncMock()
    with pytest.raises(ValueError):
        await unsupported.set_position_target(0, 100)
    with pytest.raises(ValueError):
        await unsupported.set_light_level(0)
    with pytest.raises(ValueError):
        await unsupported.set_massage_timer_code(1)
    unsupported._write_route.assert_not_awaited()

    star = _controller("BOX25_STAR", connected=True)
    star._write_route = AsyncMock()
    for operation in (
        lambda: star.set_light_level(7),
        lambda: star.set_light_color_code(0),
        lambda: star.set_massage_timer_code(4),
        lambda: star.set_massage_intensity("head", 3),
        lambda: star.set_massage_intensity("all", 8),
        lambda: star.set_position_target(0, 101),
    ):
        with pytest.raises(ValueError):
            await operation()
    star._write_route.assert_not_awaited()


async def test_position36_commit_writes_target_stop_then_real_midpoint_value() -> None:
    controller = _controller("BOX2442", connected=True)
    controller._write_route = AsyncMock()

    await controller.set_position_target(2, 100)

    routes = [call.args[0] for call in controller._write_route.await_args_list]
    assert [route.builder for route in routes] == ["changePosition", "stop", "changePosition"]
    assert [route.payload for route in routes] == [
        bytes.fromhex("03 F0 02 64 00"),
        controller._route("stop").payload,
        bytes.fromhex("03 F0 02 32 00"),
    ]
    assert controller._targets[2] == 50


async def test_brightness_ui_zero_is_off_but_controller_zero_is_brightness() -> None:
    controller = _controller("BOX25", connected=True)
    controller._write_route = AsyncMock()

    with pytest.raises(ValueError, match="enabled under-bed lighting"):
        await controller.set_light_slider_value(0)
    controller._app_fields["field_0x53"] = 1
    await controller.set_light_slider_value(0)
    off = controller._write_route.await_args.args[0]
    assert off.builder == "turnoffUnderbedLighting"

    controller._write_route.reset_mock()
    await controller.set_light_level(0)
    brightness = controller._write_route.await_args.args[0]
    assert brightness.builder == "changeLightBrightness"
    assert brightness.logical_values == (4, 224, 0, 0, 0, 0)
    controller._write_route.assert_awaited_once()


async def test_voice_brightness_step_retains_endpoint_and_needs_known_level() -> None:
    controller = _controller("BOX25", connected=True)
    controller._write_route = AsyncMock()

    await controller.adjust_light_level(-1)
    controller._write_route.assert_not_awaited()

    controller._light_level = 0
    controller._light_level_known = True
    await controller.adjust_light_level(-1)
    route = controller._write_route.await_args.args[0]
    assert route.builder == "changeLightBrightness"
    assert route.logical_values == (4, 224, 0, 0, 0, 0)
    controller._write_route.assert_awaited_once()


async def test_palette_number_requires_enabled_lights_and_is_one_shot() -> None:
    controller = _controller("BOX25_STAR", connected=True)
    controller._write_route = AsyncMock()
    characteristic = SimpleNamespace(uuid="6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
    controller._notify_characteristic = characteristic
    status = bytearray(16)
    status[:2] = b"\xa5\x0b"

    with pytest.raises(ValueError, match="enabled under-bed lighting"):
        await controller.set_light_color_code(7)
    controller._handle_notification(characteristic, status)
    assert controller._app_fields["field_0x53"] == 0
    with pytest.raises(ValueError, match="enabled under-bed lighting"):
        await controller.set_light_color_code(7)
    controller._write_route.assert_not_awaited()

    status[14] = 0x10
    controller._handle_notification(characteristic, status)
    assert controller._app_fields["field_0x53"] == 1
    await controller.set_light_color_code(7)
    route = controller._write_route.await_args.args[0]
    assert route.payload == bytes.fromhex("5A E0 04 01 07 00 00 A5")
    controller._write_route.assert_awaited_once()


@pytest.mark.parametrize(("level", "wire_level"), [(0, 0), (1, 2), (7, 8)])
async def test_massage_intensity_commit_maps_once_without_stop(level: int, wire_level: int) -> None:
    controller = _controller("BOX25", connected=True)
    controller._app_fields["field_0x4b"] = 1
    controller._write_route = AsyncMock()

    await controller.set_massage_intensity("all", level)

    route = controller._write_route.await_args.args[0]
    assert route.logical_values == (4, 224, 6, wire_level, wire_level, 0)
    controller._write_route.assert_awaited_once()


async def test_massage_values_require_active_state_and_time_commit_skips_same_code() -> None:
    controller = _controller("BOX25", connected=True)
    controller._write_route = AsyncMock()
    with pytest.raises(ValueError, match="active massage"):
        await controller.set_massage_intensity("all", 2)
    with pytest.raises(ValueError, match="active massage"):
        await controller.set_massage_timer_code(2)
    controller._write_route.assert_not_awaited()

    characteristic = SimpleNamespace(uuid="6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
    controller._notify_characteristic = characteristic
    status = bytearray(16)
    status[:2] = b"\xa5\x0b"
    controller._handle_notification(characteristic, status)
    assert controller._app_fields["field_0x4b"] == 0
    with pytest.raises(ValueError, match="active massage"):
        await controller.set_massage_intensity("all", 2)

    status[4:6] = (1200).to_bytes(2, "big")
    status[14] = 1
    controller._handle_notification(characteristic, status)
    assert controller._app_fields["field_0x4b"] == 1
    assert controller._app_fields["field_0x0b"] == 2
    await controller.set_massage_timer_code(2)
    controller._write_route.assert_not_awaited()
    await controller.set_massage_intensity("all", 2)
    await controller.set_massage_timer_code(3)
    routes = [call.args[0] for call in controller._write_route.await_args_list]
    assert [route.logical_values for route in routes] == [
        (4, 224, 6, 3, 3, 0),
        (4, 224, 7, 3, 0, 0),
    ]


@pytest.mark.parametrize(
    ("operation_name", "value", "expected_payload"),
    [
        ("set_light_level", 6, "04 E0 00 06 00 00"),
        ("set_light_color_code", 7, "04 E0 01 07 00 00"),
        ("set_massage_timer_code", 3, "04 E0 07 03 00 00"),
    ],
)
async def test_box25_dynamic_end_values_match_canonical_frames(
    operation_name: str, value: int, expected_payload: str
) -> None:
    controller = _controller("BOX25", connected=True)
    controller._write_route = AsyncMock()
    controller._app_fields["field_0x4b"] = 1
    controller._app_fields["field_0x53"] = 1
    operation = getattr(controller, operation_name)
    clock = _VirtualClock()
    with (
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
    ):
        await clock.run(operation(value))
    assert controller._write_route.await_args_list[0].args[0].payload == bytes.fromhex(
        expected_payload
    )
    assert controller._write_route.await_count == 1


async def test_starcode_positive_intensity_keeps_duplicate_wire_slots() -> None:
    controller = _controller("BOX25_STAR", connected=True)
    controller._write_route = AsyncMock()
    controller._app_fields["field_0x4b"] = 1
    clock = _VirtualClock()
    with (
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
    ):
        await clock.run(controller.set_massage_intensity("all", 7))
    route = controller._write_route.await_args_list[0].args[0]
    assert route.logical_values == (90, 224, 4, 6, 8, 8, 0, 165)
    assert route.payload == bytes.fromhex("5A E0 04 06 08 08 00 A5")
    assert controller._write_route.await_count == 1


@pytest.mark.parametrize("row", _tsv(_PARSER_FIXTURE), ids=lambda row: row["case_id"])
def test_all_39_accepted_parser_cases(row: dict[str, str]) -> None:
    selector = _selector_for_parser_branch(row["branch"])
    controller = _controller(selector)
    parsed = controller._parse_notification(bytes.fromhex(row["input_bytes"]))

    if row["scenario"] == "malformed" or row["model_result"] == "MODEL_BOUNDS_FAULT":
        assert parsed is None
        return
    assert parsed is not None

    # A selected-device-null app crash is deliberately rejected at notification
    # dispatch time; the standalone parser still decodes a structurally complete frame.
    if row["model_result"] == "MODEL_NULL_SELECTED_DEVICE_FAULT":
        return
    changed_ids = _changed_field_ids(row["changed_fields_in_store_order"])
    expected_values = _field_values(row["state_after"])
    for field_id in changed_ids:
        if field_id in _POSITION_KEY_TO_AXIS:
            axis_key = _POSITION_KEY_TO_AXIS[field_id]
            positions = parsed.get("_positions")
            assert isinstance(positions, dict)
            position = positions.get(axis_key)
            assert isinstance(position, (int, float))
            assert float(position) == float(expected_values[field_id])
            continue
        key = f"field_0x{int(field_id, 16):02x}"
        assert key in parsed, row["case_id"]
        actual = parsed[key]
        expected = expected_values[field_id]
        if isinstance(expected, bool):
            assert actual is expected, row["case_id"]
        else:
            assert actual == expected, row["case_id"]


def test_parser_faults_and_stale_notifications_leave_state_unchanged() -> None:
    controller = _controller("BOX25", connected=True)
    char = SimpleNamespace(uuid="6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
    controller._notify_characteristic = char

    controller._handle_notification(char, bytearray.fromhex("A5 0C 00 00 01 0A 07"))
    controller._coordinator.handle_controller_state_updates.assert_not_called()
    assert controller._app_fields == {}

    controller.client.is_connected = False
    controller._handle_notification(char, bytearray.fromhex("A5 0C 00 00 01 0C 07 03"))
    controller._coordinator.handle_controller_state_updates.assert_not_called()
    assert controller._app_fields == {}


@pytest.mark.parametrize(
    ("selector", "frame"),
    [
        ("BOX15", bytes((0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0))),
        ("BOX1220", bytes.fromhex("A5 0B 0E 00 02 58 03 04 05")),
    ],
)
def test_non_timer_layouts_keep_field_0b_out_of_the_timer_select(
    selector: str, frame: bytes
) -> None:
    controller = _controller(selector, connected=True)
    characteristic = SimpleNamespace(uuid="accepted-notify")
    controller._notify_characteristic = characteristic

    controller._handle_notification(characteristic, bytearray(frame))

    updates = controller._coordinator.handle_controller_state_updates.call_args.args[0]
    assert "sleepys_app_field_0x0b" in updates
    assert "sleepys_app_massage_timer_code" not in updates


def test_unknown_timer_code_does_not_enter_the_declared_select_domain() -> None:
    controller = _controller("BOX25", connected=True)
    characteristic = SimpleNamespace(uuid="accepted-notify")
    controller._notify_characteristic = characteristic
    raw = bytearray(16)
    raw[:2] = b"\xa5\x0b"
    raw[14] = 1

    controller._handle_notification(characteristic, raw)

    updates = controller._coordinator.handle_controller_state_updates.call_args.args[0]
    assert updates["sleepys_app_field_0x0b"] == 0
    assert "sleepys_app_massage_timer_code" not in updates


@pytest.mark.parametrize(
    "row",
    [
        row
        for row in _tsv(_PARSER_FIXTURE)
        if row["model_result"] in {"MODEL_BOUNDS_FAULT", "NO_MATCH"}
    ],
    ids=lambda row: row["case_id"],
)
def test_malformed_and_bounds_fault_notifications_are_atomic(row: dict[str, str]) -> None:
    controller = _controller(_selector_for_parser_branch(row["branch"]), connected=True)
    notify_uuid = ROUTES[("keepConnect", controller.selector)].notify_target.split("/", 1)[1]
    characteristic = SimpleNamespace(uuid=notify_uuid)
    controller._notify_characteristic = characteristic

    controller._handle_notification(characteristic, bytearray.fromhex(row["input_bytes"]))

    controller._coordinator.handle_controller_state_updates.assert_not_called()
    assert controller._app_fields == {}
    assert controller._position_data == {}


@pytest.mark.parametrize(
    "row",
    [
        row
        for row in _tsv(_PARSER_FIXTURE)
        if row["model_result"] == "MODEL_NULL_SELECTED_DEVICE_FAULT"
    ],
    ids=lambda row: row["case_id"],
)
def test_selected_device_null_callbacks_are_ignored_without_a_current_session(
    row: dict[str, str],
) -> None:
    """No current client/notify session is the HA equivalent of a null selection."""
    controller = _controller(_selector_for_parser_branch(row["branch"]))
    notify_uuid = ROUTES[("keepConnect", controller.selector)].notify_target.split("/", 1)[1]
    characteristic = SimpleNamespace(uuid=notify_uuid)
    controller._notify_characteristic = characteristic

    controller._handle_notification(characteristic, bytearray.fromhex(row["input_bytes"]))

    controller._coordinator.handle_controller_state_updates.assert_not_called()
    assert controller._app_fields == {}
    assert controller._position_data == {}


def test_timing_crosswalk_has_53_production_rows_and_no_alarm_action() -> None:
    rows = _tsv(_TIMING_FIXTURE)
    assert len(rows) == 55
    assert Counter(row["disposition"] for row in rows) == {
        "IMPLEMENTED": 53,
        "EXCLUDED": 2,
    }
    assert {row["builder"] for row in rows if row["disposition"] == "EXCLUDED"} == {
        "setAlarm",
        "queryAlarm",
    }
    for row in rows:
        if row["disposition"] == "IMPLEMENTED":
            assert any(builder == row["builder"] for builder, _ in ROUTES)
        else:
            assert not any(builder == row["builder"] for builder, _ in ROUTES)

    for selector in SLEEPYS_ELITE_SELECTORS:
        controller = _controller(selector)
        assert not any(
            "alarm" in spec.key.casefold() for spec in controller.controller_button_specs
        )
        assert not any(
            "alarm" in spec.key.casefold() for spec in controller.controller_number_specs
        )
        assert not any(
            "alarm" in spec.key.casefold() for spec in controller.controller_select_specs
        )


async def test_hold_repeats_at_100ms_then_stops_with_a_fresh_event() -> None:
    controller = _controller("BOX15", connected=True)
    controller._write_route = AsyncMock()
    clock = _VirtualClock()

    with (
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
    ):
        await clock.run(controller.hold_control("headUp", 250))

    assert controller._write_route.await_count == 4
    assert [call.args[0].builder for call in controller._write_route.await_args_list] == [
        "headUp",
        "headUp",
        "headUp",
        "stop",
    ]
    movement_kwargs = controller._write_route.await_args_list[0].kwargs
    assert movement_kwargs == {"cancel_event": controller._coordinator.cancel_command}
    release, release_kwargs = (
        controller._write_route.await_args_list[3].args[0],
        (controller._write_route.await_args_list[3].kwargs),
    )
    assert release.builder == "stop"
    assert isinstance(release_kwargs["cancel_event"], asyncio.Event)
    assert release_kwargs["cancel_event"] is not controller._coordinator.cancel_command
