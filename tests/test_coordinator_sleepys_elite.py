"""Startup ordering for the explicit Sleepy's Elite app profile."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import ExitStack
from dataclasses import replace
from types import SimpleNamespace
from typing import TypeVar
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

# The hold action imports this on demand in the executor; loading it up front
# keeps virtual time from racing a real import thread.
import custom_components.adjustable_bed.beds.vmatbasic.services  # noqa: F401
from custom_components.adjustable_bed.adapter import AdapterSelectionResult
from custom_components.adjustable_bed.beds.sleepys.app import SleepysEliteAppController
from custom_components.adjustable_bed.beds.sleepys.app_routes import ROUTES
from custom_components.adjustable_bed.bluetooth_transport import ConnectionPath, TransportClass
from custom_components.adjustable_bed.bond_verification import (
    BondEvidence,
    BondEvidenceKind,
    BondOwner,
    BondVerificationStatus,
)
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.const import (
    BED_TYPE_SLEEPYS_ELITE_APP,
    CONF_BED_TYPE,
    CONF_CONNECTION_MODE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_SLEEPYS_ELITE_SELECTOR,
    DEVICE_INFO_CHARS,
    DEVICE_INFO_SERVICE_UUID,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.number import (
    LIGHT_LEVEL_DESCRIPTION,
    MASSAGE_NUMBER_DESCRIPTIONS,
    AdjustableBedControllerNumber,
    AdjustableBedLevelNumber,
    AdjustableBedMassageNumber,
    AdjustableBedPositionNumber,
    _build_position_description,
    _number_entities_for,
)
from custom_components.adjustable_bed.select import (
    MASSAGE_TIMER_DESCRIPTION,
    AdjustableBedMassageTimerSelect,
)
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from custom_components.adjustable_bed.services import _position_config, async_register_services
from custom_components.adjustable_bed.switch import AdjustableBedControllerSwitch
from tests.error_helpers import raises_key
from tests.pair_mode import CONF_PAIR_CONNECTION_MODE

from .conftest import TEST_ADDRESS, TEST_NAME

_MODULE = "custom_components.adjustable_bed.coordinator"
_APP = "custom_components.adjustable_bed.beds.sleepys.app"
_BASE = "custom_components.adjustable_bed.beds.base"
# The position report of #372: head 22 at byte 4, with lumbar 40 added at byte 8.
_POSITION_REPORT = bytes.fromhex("A5 0D 11 01 16 00 00 00 28 00 00 00 00 00 00 00 00 00 00 00")

_CONNECTION = "custom_components.adjustable_bed.coordinator_connection"
_BONDS = "custom_components.adjustable_bed.coordinator_bonds"
_LOCAL = ConnectionPath(source="local", transport=TransportClass.LOCAL, adapter="hci0")
_T = TypeVar("_T")


class _FakeGattCharacteristic:
    def __init__(self, uuid: str) -> None:
        self.uuid = uuid
        self.handle = 1
        self.properties = ["write", "notify", "read"]
        self.descriptors: list[object] = []


class _FakeGattService:
    def __init__(self, uuid: str, characteristic_uuids: tuple[str, ...]) -> None:
        self.uuid = uuid
        self.characteristics = [_FakeGattCharacteristic(value) for value in characteristic_uuids]

    def get_characteristic(self, uuid: str) -> _FakeGattCharacteristic | None:
        return next(
            (
                characteristic
                for characteristic in self.characteristics
                if characteristic.uuid.casefold() == uuid.casefold()
            ),
            None,
        )


class _FakeGattClient:
    def __init__(self) -> None:
        self.is_connected = True
        self.services = [_FakeGattService("1000", ("1001", "1002"))]
        self.write_gatt_char = AsyncMock()
        self.disconnect = AsyncMock(side_effect=self._disconnect)
        self.stop_notify = AsyncMock()

    async def _disconnect(self) -> None:
        self.is_connected = False


SleepysRuntime = tuple[
    HomeAssistant,
    AdjustableBedCoordinator,
    SleepysEliteAppController,
    _FakeGattClient,
]


class _VirtualClock:
    def __init__(self) -> None:
        self.now = 0.0
        self._sleepers: list[tuple[float, asyncio.Future[None]]] = []
        self.sleep_calls: list[tuple[float, float]] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleep_calls.append((self.now, seconds))
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

    async def run_until(self, task: asyncio.Task[_T]) -> _T:
        loop = asyncio.get_running_loop()
        for _ in range(1_000):
            # Virtual time may only pass once nothing else can run: a fixed
            # number of yields raced on-demand imports finishing in the
            # executor, which let a write's deadline fire before the write.
            for _ in range(10_000):
                await asyncio.sleep(0)
                if not loop._ready:  # type: ignore[attr-defined]
                    break
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


def _ready_command_lane(coordinator: AdjustableBedCoordinator) -> ExitStack:
    """Keep connection setup external while exercising the real scheduler lane."""
    stack = ExitStack()
    stack.enter_context(
        patch.object(
            coordinator,
            "async_ensure_connected",
            new=AsyncMock(return_value=True),
        )
    )
    stack.enter_context(
        patch.object(coordinator, "_async_refresh_controller_auth", new=AsyncMock())
    )
    return stack


def _service(uuid: str, *characteristic_uuids: str) -> SimpleNamespace:
    characteristics = [
        SimpleNamespace(
            uuid=value,
            properties=["write", "notify", "read"],
            descriptors=[],
            handle=index,
        )
        for index, value in enumerate(characteristic_uuids, start=1)
    ]

    def get_characteristic(characteristic_uuid: str) -> SimpleNamespace | None:
        return next(
            (item for item in characteristics if item.uuid.lower() == characteristic_uuid.lower()),
            None,
        )

    return SimpleNamespace(
        uuid=uuid,
        handle=1,
        characteristics=characteristics,
        get_characteristic=get_characteristic,
    )


def _native_bond() -> BondEvidence:
    return BondEvidence(
        BondVerificationStatus.NATIVE_OS_STATE,
        BondOwner.from_path(_LOCAL),
        "sleepys_startup_test",
        "now",
        kind=BondEvidenceKind.NATIVE_OS_STATE,
    )


@pytest.fixture
def sleepys_coordinator(hass: HomeAssistant) -> AdjustableBedCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        unique_id=TEST_ADDRESS,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_SLEEPYS_ELITE_APP,
            CONF_SLEEPYS_ELITE_SELECTOR: "BOX1220",
            CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    coordinator._connection_path = _LOCAL
    coordinator._max_retries = 1
    coordinator._post_connect_delay = 0
    return coordinator


@pytest.fixture
async def sleepys_runtime(
    hass: HomeAssistant,
) -> AsyncIterator[SleepysRuntime]:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sleepy's runtime bed",
        unique_id="AA:BB:CC:DD:EE:01",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
            CONF_NAME: "Sleepy's runtime bed",
            CONF_BED_TYPE: BED_TYPE_SLEEPYS_ELITE_APP,
            CONF_SLEEPYS_ELITE_SELECTOR: "BOX25",
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_CONNECTION_MODE: "idle",
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._connection_path = _LOCAL
    coordinator._max_retries = 1
    coordinator._post_connect_delay = 0
    client = _FakeGattClient()
    controller = SleepysEliteAppController(coordinator, "BOX25")
    controller._initialized = True
    keep_route = ROUTES[("keepConnect", "BOX25")]
    _, notify_characteristic = keep_route.notify_target.split("/", 1)
    service = _FakeGattService(
        keep_route.write_service,
        (keep_route.write_characteristic, notify_characteristic),
    )
    client.services = [service]
    controller._write_characteristic = service.characteristics[0]
    coordinator._client = client
    coordinator._controller = controller
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await async_register_services(hass)

    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, "both")], []),
    ):
        yield hass, coordinator, controller, client
    await coordinator.async_shutdown()


async def _connect_with_real_startup(
    coordinator: AdjustableBedCoordinator,
) -> tuple[bool, AsyncMock]:
    device = BLEDevice(TEST_ADDRESS, TEST_NAME, {"source": _LOCAL.source})
    adapter = AdapterSelectionResult(device, _LOCAL.source, -50, True, [_LOCAL.source])
    generic_dis = AsyncMock()
    with (
        patch(f"{_CONNECTION}.select_adapter", return_value=adapter),
        patch(f"{_CONNECTION}.client_source", return_value=_LOCAL.source),
        patch(f"{_CONNECTION}.async_path_for_source", return_value=_LOCAL),
        patch(f"{_BONDS}.async_verify_native_bond", return_value=_native_bond()),
        patch(f"{_CONNECTION}.close_stale_connections_by_address", new_callable=AsyncMock),
        patch(f"{_CONNECTION}.read_ble_device_info", generic_dis),
    ):
        connected = await coordinator.async_connect()
    return connected, generic_dis


@pytest.mark.usefixtures("mock_coordinator_connected")
async def test_startup_orders_setup_notify_then_optional_device_information(
    sleepys_coordinator: AdjustableBedCoordinator,
    mock_bleak_client,
) -> None:
    """A same-frame setup error retry precedes notify and exact 2A29/2A28 reads."""
    setup_service = _service("1000", "1001", "1002")
    info_service = _service(
        DEVICE_INFO_SERVICE_UUID,
        DEVICE_INFO_CHARS["manufacturer_name"],
        DEVICE_INFO_CHARS["software_revision"],
        DEVICE_INFO_CHARS["model_number"],
    )
    mock_bleak_client.services = [setup_service, info_service]
    mock_bleak_client.start_notify = AsyncMock()
    trace: list[tuple[object, ...]] = []
    setup_attempts = 0

    async def write(characteristic, payload: bytes, *, response: bool = True) -> None:
        nonlocal setup_attempts
        uuid = getattr(characteristic, "uuid", str(characteristic))
        trace.append(("write", uuid, bytes(payload), response))
        if uuid == "1001":
            setup_attempts += 1
            if setup_attempts == 1:
                raise BleakError("first setup write failed")

    async def start_notify(characteristic, _callback) -> None:
        trace.append(("notify", characteristic.uuid))

    async def read(characteristic_uuid: str) -> bytes:
        trace.append(("read", characteristic_uuid))
        if characteristic_uuid == DEVICE_INFO_CHARS["manufacturer_name"]:
            raise BleakError("manufacturer unavailable")
        return {
            DEVICE_INFO_CHARS["software_revision"]: b"1.1.5",
        }[characteristic_uuid]

    mock_bleak_client.write_gatt_char = AsyncMock(side_effect=write)
    mock_bleak_client.start_notify.side_effect = start_notify
    mock_bleak_client.read_gatt_char = AsyncMock(side_effect=read)

    connected, generic_dis = await _connect_with_real_startup(sleepys_coordinator)

    assert connected
    assert trace == [
        ("write", "1001", bytes.fromhex("5A 0B 00 A5"), True),
        ("write", "1001", bytes.fromhex("5A 0B 00 A5"), True),
        ("notify", "1002"),
        ("read", DEVICE_INFO_CHARS["manufacturer_name"]),
        ("read", DEVICE_INFO_CHARS["software_revision"]),
    ]
    assert sleepys_coordinator._ble_manufacturer is None
    assert sleepys_coordinator._ble_model == "1.1.5"
    generic_dis.assert_not_awaited()
    await sleepys_coordinator.async_shutdown()


async def test_registered_hold_service_uses_elapsed_window_and_one_release(
    sleepys_runtime: SleepysRuntime,
) -> None:
    hass, coordinator, controller, client = sleepys_runtime
    clock = _VirtualClock()
    trace: list[tuple[float, bytes, bool]] = []

    async def write(_characteristic: object, payload: bytes, *, response: bool = True) -> None:
        trace.append((clock.now, bytes(payload), response))

    client.write_gatt_char.side_effect = write
    up = controller._route("headUp")
    stop = controller._route("stop")
    with (
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ),
        _ready_command_lane(coordinator),
    ):
        operation = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["sleepys"], "control": "headUp", "duration": 0.3},
                blocking=True,
            )
        )
        await clock.run_until(operation)

    assert [payload for _, payload, _ in trace] == [
        up.payload,
        up.payload,
        up.payload,
        stop.payload,
    ]
    assert [round(when, 3) for when, _, _ in trace] == [0, 0.1, 0.2, 0.3]
    assert all(response is up.write_with_response for _, _, response in trace[:3])
    assert trace[-1][2] is stop.write_with_response
    await coordinator.async_shutdown()


async def test_slow_pending_write_is_cancelled_at_active_deadline(
    sleepys_runtime: SleepysRuntime,
) -> None:
    hass, coordinator, controller, client = sleepys_runtime
    clock = _VirtualClock()
    attempts: list[tuple[float, bytes]] = []
    completions: list[tuple[float, bytes]] = []
    cancelled_at: list[float] = []
    up = controller._route("headUp")
    stop = controller._route("stop")
    up_attempts = 0

    async def write(_characteristic: object, payload: bytes, *, response: bool = True) -> None:
        nonlocal up_attempts
        frame = bytes(payload)
        attempts.append((clock.now, frame))
        if frame == up.payload:
            up_attempts += 1
            if up_attempts == 2:
                try:
                    await clock.sleep(1)
                except asyncio.CancelledError:
                    cancelled_at.append(clock.now)
                    raise
        completions.append((clock.now, frame))

    client.write_gatt_char.side_effect = write
    with (
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ),
        _ready_command_lane(coordinator),
    ):
        operation = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["sleepys"], "control": "headUp", "duration": 0.3},
                blocking=True,
            )
        )
        await clock.run_until(operation)

    assert [frame for _, frame in attempts] == [up.payload, up.payload, stop.payload]
    assert [when for when, _ in attempts] == [0, 0.1, 0.3]
    assert cancelled_at == [0.3]
    assert completions == [(0, up.payload), (0.3, stop.payload)]
    await coordinator.async_shutdown()


async def test_registered_timed_move_honors_duration_and_sends_one_stop(
    sleepys_runtime: SleepysRuntime,
) -> None:
    hass, coordinator, controller, client = sleepys_runtime
    clock = _VirtualClock()
    trace: list[tuple[float, bytes]] = []
    up = controller._route("headUp")
    stop = controller._route("stop")

    async def write(_characteristic: object, payload: bytes, *, response: bool = True) -> None:
        trace.append((clock.now, bytes(payload)))

    client.write_gatt_char.side_effect = write
    with (
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ),
        _ready_command_lane(coordinator),
    ):
        operation = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "timed_move",
                {
                    "device_id": ["sleepys"],
                    "motor": "head",
                    "direction": "up",
                    "duration_ms": 300,
                },
                blocking=True,
            )
        )
        await clock.run_until(operation)

    assert [payload for _, payload in trace] == [
        up.payload,
        up.payload,
        up.payload,
        stop.payload,
    ]
    assert trace[-1][0] >= 0.3
    assert sum(payload == stop.payload for _, payload in trace) == 1
    await coordinator.async_shutdown()


@pytest.mark.parametrize(("fail_first_stop", "expected_stops"), [(False, 1), (True, 2)])
async def test_stop_race_acknowledges_only_successful_controller_cleanup(
    sleepys_runtime: SleepysRuntime,
    fail_first_stop: bool,
    expected_stops: int,
) -> None:
    hass, coordinator, controller, client = sleepys_runtime
    clock = _VirtualClock()
    writes: list[bytes] = []
    first_stop_failed = False
    up = controller._route("headUp")
    stop = controller._route("stop")

    async def write(_characteristic: object, payload: bytes, *, response: bool = True) -> None:
        nonlocal first_stop_failed
        frame = bytes(payload)
        writes.append(frame)
        if frame == stop.payload and fail_first_stop and not first_stop_failed:
            first_stop_failed = True
            raise BleakError("first cleanup release failed")

    client.write_gatt_char.side_effect = write
    with (
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ),
        _ready_command_lane(coordinator),
    ):
        held = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["sleepys"], "control": "headUp", "duration": 60},
                blocking=True,
            )
        )
        for _ in range(100):
            await asyncio.sleep(0)
            if up.payload in writes:
                break
        assert up.payload in writes

        stop_task = asyncio.create_task(coordinator.async_stop_command())
        await asyncio.gather(held, stop_task)

        # A subsequent operation still runs, then each idle STOP sends a frame.
        next_move = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["sleepys"], "control": "headDown", "duration": 0.1},
                blocking=True,
            )
        )
        await clock.run_until(next_move)
        await coordinator.async_stop_command()
        await coordinator.async_stop_command()

    assert writes.count(up.payload) == 1
    assert writes.count(stop.payload) == expected_stops + 3
    assert writes.count(controller._route("headDown").payload) == 1
    await coordinator.async_shutdown()


async def test_native_button_cover_number_and_select_use_bounded_paths(
    sleepys_runtime: SleepysRuntime,
) -> None:
    hass, coordinator, controller, client = sleepys_runtime
    clock = _VirtualClock()
    trace: list[tuple[float, bytes]] = []

    async def write(_characteristic: object, payload: bytes, *, response: bool = True) -> None:
        trace.append((clock.now, bytes(payload)))

    client.write_gatt_char.side_effect = write
    with (
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
        _ready_command_lane(coordinator),
    ):
        button_spec = next(
            spec
            for spec in controller.controller_button_specs
            if spec.key == "sleepys_app_memory_1"
        )
        button = ControllerActionButton(coordinator, button_spec)
        await clock.run_until(asyncio.create_task(button.async_press()))

        head_spec = next(spec for spec in controller.motor_control_specs if spec.key == "head")
        cover = AdjustableBedCover(coordinator, _build_cover_description(head_spec))
        with patch.object(cover, "async_write_ha_state"):
            await clock.run_until(asyncio.create_task(cover.async_open_cover()))

        number_spec = next(
            spec
            for spec in controller.controller_number_specs
            if spec.key == "sleepys_app_color_code"
        )
        number = AdjustableBedControllerNumber(coordinator, number_spec)
        controller._app_fields["field_0x53"] = 1
        await clock.run_until(asyncio.create_task(number.async_set_native_value(5)))

        select = AdjustableBedMassageTimerSelect(
            coordinator, MASSAGE_TIMER_DESCRIPTION, [10, 20, 30], has_off=False
        )
        controller._app_fields["field_0x4b"] = 1
        await clock.run_until(asyncio.create_task(select.async_select_option("20 min")))

        level = AdjustableBedLevelNumber(
            coordinator,
            replace(LIGHT_LEVEL_DESCRIPTION, native_min_value=0, native_max_value=6),
        )
        await clock.run_until(asyncio.create_task(level.async_set_native_value(0)))
        await clock.run_until(asyncio.create_task(level.async_set_native_value(6)))

        massage = AdjustableBedMassageNumber(
            coordinator,
            replace(MASSAGE_NUMBER_DESCRIPTIONS[0], native_max_value=7),
        )
        await clock.run_until(asyncio.create_task(massage.async_set_native_value(7)))

        position_spec = next(
            spec for spec in controller.position_number_specs if spec.position_key == "feet"
        )
        position = AdjustableBedPositionNumber(
            coordinator, _build_position_description(position_spec)
        )
        await clock.run_until(asyncio.create_task(position.async_set_native_value(100)))
        await clock.run_until(asyncio.create_task(position.async_set_native_value(0)))

    stop = controller._route("stop").payload
    memory = ROUTES[("m1", "BOX25")].payload
    palette = controller._value_route("light_color_code", 5).payload
    timer = controller._value_route("massage_timer_code", 2).payload
    light_off = controller._route("turnoffUnderbedLighting").payload
    light_level = controller._value_route("light_level", 6).payload
    intensity = controller._value_route("massage_intensity_all", 7).payload
    position_target = controller._value_route("position_axis_1", 100).payload
    voice_position = controller._value_route("position_axis_1", 0).payload
    query = controller._route("queryPosition").payload
    assert [payload for _, payload in trace[:4]] == [memory, memory, memory, stop]
    assert sum(payload == stop for _, payload in trace) == 2
    assert trace[8][1] == palette
    assert trace[9][1] == timer
    assert trace[10][1] == light_off
    assert trace[11][1] == light_level
    assert trace[12][1] == intensity
    # The slider asks where the bed is, then sends its one target frame.
    assert [payload for _, payload in trace[13:]] == [
        query,
        position_target,
        query,
        voice_position,
    ]
    assert sum(payload == palette for _, payload in trace) == 1
    assert sum(payload == timer for _, payload in trace) == 1
    assert sum(payload == light_level for _, payload in trace) == 1
    assert sum(payload == intensity for _, payload in trace) == 1
    assert sum(payload == position_target for _, payload in trace) == 1
    assert sum(payload == voice_position for _, payload in trace) == 1
    await coordinator.async_shutdown()


async def test_motion_sensor_refresh_is_bounded_and_has_no_stop(
    sleepys_runtime: SleepysRuntime,
) -> None:
    _hass, coordinator, controller, client = sleepys_runtime
    clock = _VirtualClock()
    trace: list[tuple[float, bytes]] = []

    async def write(_characteristic: object, payload: bytes, *, response: bool = True) -> None:
        trace.append((clock.now, bytes(payload)))

    client.write_gatt_char.side_effect = write
    with (
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
        _ready_command_lane(coordinator),
    ):
        spec = next(
            spec
            for spec in controller.controller_switch_specs
            if spec.key == "sleepys_app_motion_sensor"
        )
        switch = AdjustableBedControllerSwitch(coordinator, spec)
        with patch.object(switch, "async_write_ha_state"):
            await clock.run_until(asyncio.create_task(switch.async_turn_on()))

    route = controller._route("motionSensorOn")
    assert len(trace) == 50, trace[-3:]
    assert all(payload == route.payload for _, payload in trace)
    assert trace[0][0] == 0
    assert trace[-1][0] < 5
    assert all(payload != controller._route("stop").payload for _, payload in trace)
    await coordinator.async_shutdown()


async def test_sequential_both_button_is_finite_and_drops_stale_hold_metadata(
    hass: HomeAssistant,
    sleepys_runtime: SleepysRuntime,
) -> None:
    from custom_components.adjustable_bed.button import PairedBedCombinedMotorButton
    from custom_components.adjustable_bed.const import (
        CONF_PAIR_ID,
        PAIR_CONNECTION_MODE_CONCURRENT,
        PAIR_CONNECTION_MODE_SEQUENTIAL,
        SIDE_LEFT,
        SIDE_RIGHT,
    )
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    _hass, left, left_controller, left_client = sleepys_runtime
    right_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sleepy's right side",
        unique_id="AA:BB:CC:DD:EE:02",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:02",
            CONF_NAME: "Sleepy's right side",
            CONF_BED_TYPE: BED_TYPE_SLEEPYS_ELITE_APP,
            CONF_SLEEPYS_ELITE_SELECTOR: "BOX25",
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_CONNECTION_MODE: "idle",
        },
    )
    right_entry.add_to_hass(hass)
    right = AdjustableBedCoordinator(hass, right_entry)
    right._connection_path = _LOCAL
    right._max_retries = 1
    right._post_connect_delay = 0
    right_client = _FakeGattClient()
    keep_route = ROUTES[("keepConnect", "BOX25")]
    _, notify_characteristic = keep_route.notify_target.split("/", 1)
    right_service = _FakeGattService(
        keep_route.write_service,
        (keep_route.write_characteristic, notify_characteristic),
    )
    right_client.services = [right_service]
    right_controller = SleepysEliteAppController(right, "BOX25")
    right_controller._initialized = True
    right_controller._write_characteristic = right_service.characteristics[0]
    right._client = right_client
    right._controller = right_controller
    hass.data.setdefault(DOMAIN, {})[right_entry.entry_id] = right

    pair_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sleepy's paired bed",
        unique_id="sleepys-pair",
        data={
            CONF_PAIR_ID: "sleepys-pair",
            CONF_PAIR_CONNECTION_MODE: PAIR_CONNECTION_MODE_SEQUENTIAL,
            "name": "Sleepy's paired bed",
        },
    )
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass,
        pair_entry,
        {SIDE_LEFT: left, SIDE_RIGHT: right},
        connection_mode=PAIR_CONNECTION_MODE_SEQUENTIAL,
    )
    spec = next(spec for spec in left_controller.motor_control_specs if spec.key == "head")
    from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description

    cover = AdjustableBedCover(left, _build_cover_description(spec))
    assert cover.extra_state_attributes["held_stop_scope"] == "side"
    button = PairedBedCombinedMotorButton(pair, spec, "up")

    pair._connection_mode = PAIR_CONNECTION_MODE_CONCURRENT
    assert button.extra_state_attributes["held_control"] == "headUp"
    pair._connection_mode = PAIR_CONNECTION_MODE_SEQUENTIAL
    assert "held_control" not in button.extra_state_attributes

    clock = _VirtualClock()
    trace: list[tuple[str, float, bytes]] = []
    right_cancel_at_write: list[bool] = []
    left_up = left_controller._route("headUp").payload
    right_up = right_controller._route("headUp").payload
    stop = left_controller._route("stop").payload

    async def write_left(_characteristic: object, payload: bytes, *, response: bool = True) -> None:
        trace.append(("left", clock.now, bytes(payload)))

    async def write_right(
        _characteristic: object, payload: bytes, *, response: bool = True
    ) -> None:
        trace.append(("right", clock.now, bytes(payload)))
        right_cancel_at_write.append(right.cancel_command.is_set())

    left_client.write_gatt_char.side_effect = write_left
    right_client.write_gatt_char.side_effect = write_right

    async def connect_left() -> bool:
        left_client.is_connected = True
        return True

    async def connect_right() -> bool:
        right_client.is_connected = True
        return True

    async def disconnect_left(_reason: str = "intentional") -> bool:
        left_client.is_connected = False
        return True

    async def disconnect_right(_reason: str = "intentional") -> bool:
        right_client.is_connected = False
        return True

    stack = _ready_command_lane(left)
    stack.enter_context(_ready_command_lane(right))
    stack.enter_context(patch.object(left_controller, "_monotonic", clock.monotonic))
    stack.enter_context(patch.object(left_controller, "_sleep", clock.sleep))
    stack.enter_context(patch.object(right_controller, "_monotonic", clock.monotonic))
    stack.enter_context(patch.object(right_controller, "_sleep", clock.sleep))
    stack.enter_context(
        patch.object(left, "async_connect", new=AsyncMock(side_effect=connect_left))
    )
    stack.enter_context(
        patch.object(right, "async_connect", new=AsyncMock(side_effect=connect_right))
    )
    stack.enter_context(
        patch.object(left, "async_disconnect", new=AsyncMock(side_effect=disconnect_left))
    )
    stack.enter_context(
        patch.object(right, "async_disconnect", new=AsyncMock(side_effect=disconnect_right))
    )
    with stack:
        await clock.run_until(asyncio.create_task(button.async_press()))

    assert len(trace) == 8, (
        trace,
        clock.sleep_calls[-10:],
        right_cancel_at_write,
        right.cancel_command.is_set(),
    )
    assert [side for side, _, _ in trace] == [
        "left",
        "left",
        "left",
        "left",
        "right",
        "right",
        "right",
        "right",
    ]
    assert [payload for _, _, payload in trace] == [
        left_up,
        left_up,
        left_up,
        stop,
        right_up,
        right_up,
        right_up,
        stop,
    ]
    assert [when for _, when, _ in trace] == [0, 0.1, 0.2, 0.3, 0.3, 0.4, 0.5, 0.6]
    await right.async_shutdown()


async def test_stale_both_hold_preflight_preserves_new_left_hold(
    hass: HomeAssistant,
    sleepys_runtime: SleepysRuntime,
) -> None:
    """A STOP during Both-side preflight cannot replace a newer Left hold."""
    from custom_components.adjustable_bed.const import (
        CONF_PAIR_ID,
        PAIR_CONNECTION_MODE_CONCURRENT,
        SIDE_BOTH,
        SIDE_LEFT,
        SIDE_RIGHT,
    )
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    _hass, left, left_controller, left_client = sleepys_runtime
    right_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sleepy's right side",
        unique_id="AA:BB:CC:DD:EE:03",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:03",
            CONF_NAME: "Sleepy's right side",
            CONF_BED_TYPE: BED_TYPE_SLEEPYS_ELITE_APP,
            CONF_SLEEPYS_ELITE_SELECTOR: "BOX25",
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_CONNECTION_MODE: "idle",
        },
    )
    right_entry.add_to_hass(hass)
    right = AdjustableBedCoordinator(hass, right_entry)
    right._connection_path = _LOCAL
    right._max_retries = 1
    right._post_connect_delay = 0
    right_client = _FakeGattClient()
    keep_route = ROUTES[("keepConnect", "BOX25")]
    _, notify_characteristic = keep_route.notify_target.split("/", 1)
    right_service = _FakeGattService(
        keep_route.write_service,
        (keep_route.write_characteristic, notify_characteristic),
    )
    right_client.services = [right_service]
    right_controller = SleepysEliteAppController(right, "BOX25")
    right_controller._initialized = True
    right_controller._write_characteristic = right_service.characteristics[0]
    right._client = right_client
    right._controller = right_controller
    hass.data.setdefault(DOMAIN, {})[right_entry.entry_id] = right

    pair_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sleepy's paired admission test",
        unique_id="sleepys-admission-pair",
        data={
            CONF_PAIR_ID: "sleepys-admission-pair",
            CONF_PAIR_CONNECTION_MODE: PAIR_CONNECTION_MODE_CONCURRENT,
            CONF_NAME: "Sleepy's paired admission test",
        },
    )
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass,
        pair_entry,
        {SIDE_LEFT: left, SIDE_RIGHT: right},
        connection_mode=PAIR_CONNECTION_MODE_CONCURRENT,
    )

    preflight_started = asyncio.Event()
    resume_preflight = asyncio.Event()
    newer_left_started = asyncio.Event()
    right_connect_calls = 0
    writes: list[tuple[str, bytes]] = []

    async def connect_right(*, reset_timer: bool = True) -> bool:
        nonlocal right_connect_calls
        del reset_timer
        right_connect_calls += 1
        if right_connect_calls == 1:
            preflight_started.set()
            await resume_preflight.wait()
        right_client.is_connected = True
        right._controller = right_controller
        return True

    async def block_refresh(_seconds: float) -> None:
        await asyncio.Future()

    async def write_left(
        _characteristic: object, payload: bytes, *, response: bool = True
    ) -> None:
        del response
        frame = bytes(payload)
        writes.append((SIDE_LEFT, frame))
        if frame == left_controller._route("headUp").payload:
            newer_left_started.set()

    async def write_right(
        _characteristic: object, payload: bytes, *, response: bool = True
    ) -> None:
        del response
        writes.append((SIDE_RIGHT, bytes(payload)))

    left_client.write_gatt_char.side_effect = write_left
    right_client.write_gatt_char.side_effect = write_right
    right_client.is_connected = False
    right._controller = None
    right._offline_controller = None

    def resolve_targets(
        _hass: HomeAssistant,
        _device_ids: list[str],
        explicit_side: str | None = None,
        *,
        problems: list[BaseException] | None = None,
    ) -> tuple[list[tuple[PairedBedCoordinator, str]], list[str]]:
        # The pair resolves, so a STOP has no problem to record.
        return [(pair, explicit_side or SIDE_BOTH)], []

    old_both_hold: asyncio.Task[object] | None = None
    new_left_hold: asyncio.Task[object] | None = None
    try:
        with (
            _ready_command_lane(left),
            patch.object(
                right,
                "async_ensure_connected",
                new=AsyncMock(side_effect=connect_right),
            ),
            patch.object(right, "_async_refresh_controller_auth", new=AsyncMock()),
            patch.object(left_controller, "_sleep", block_refresh),
            patch.object(right_controller, "_sleep", block_refresh),
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                side_effect=resolve_targets,
            ),
        ):
            old_both_hold = asyncio.create_task(
                hass.services.async_call(
                    DOMAIN,
                    "hold_control",
                    {
                        "device_id": ["sleepys-admission-pair"],
                        "control": "headUp",
                        "duration": 60,
                        "side": SIDE_BOTH,
                    },
                    blocking=True,
                )
            )
            await preflight_started.wait()

            await hass.services.async_call(
                DOMAIN,
                "stop_all",
                {"device_id": ["sleepys-admission-pair"], "side": SIDE_LEFT},
                blocking=True,
            )
            new_left_hold = asyncio.create_task(
                hass.services.async_call(
                    DOMAIN,
                    "hold_control",
                    {
                        "device_id": ["sleepys-admission-pair"],
                        "control": "headUp",
                        "duration": 60,
                        "side": SIDE_LEFT,
                    },
                    blocking=True,
                )
            )
            await newer_left_started.wait()
            assert not new_left_hold.done()

            resume_preflight.set()
            for _ in range(100):
                if old_both_hold.done():
                    break
                await asyncio.sleep(0)
            assert old_both_hold.done(), "stale Both hold entered a held controller operation"
            assert old_both_hold is not None
            await old_both_hold

            assert not new_left_hold.done()
            assert writes == [
                (SIDE_LEFT, left_controller._route("stop").payload),
                (SIDE_LEFT, left_controller._route("headUp").payload),
            ]
            assert right_connect_calls >= 2

            await hass.services.async_call(
                DOMAIN,
                "stop_all",
                {"device_id": ["sleepys-admission-pair"], "side": SIDE_LEFT},
                blocking=True,
            )
            assert new_left_hold is not None
            await new_left_hold
            assert writes == [
                (SIDE_LEFT, left_controller._route("stop").payload),
                (SIDE_LEFT, left_controller._route("headUp").payload),
                (SIDE_LEFT, left_controller._route("stop").payload),
            ]
    finally:
        resume_preflight.set()
        pending = [
            task
            for task in (old_both_hold, new_left_hold)
            if task is not None and not task.done()
        ]
        if pending:
            from contextlib import suppress

            with (
                _ready_command_lane(left),
                patch.object(
                    right,
                    "async_ensure_connected",
                    new=AsyncMock(side_effect=connect_right),
                ),
                patch.object(right, "_async_refresh_controller_auth", new=AsyncMock()),
                patch.object(left_controller, "_sleep", block_refresh),
                patch.object(right_controller, "_sleep", block_refresh),
                patch(
                    "custom_components.adjustable_bed.services._resolve_sided_targets",
                    side_effect=resolve_targets,
                ),
            ):
                with suppress(Exception, asyncio.CancelledError):
                    await hass.services.async_call(
                        DOMAIN,
                        "stop_all",
                        {"device_id": ["sleepys-admission-pair"], "side": SIDE_BOTH},
                        blocking=True,
                    )
                await asyncio.gather(*pending, return_exceptions=True)
        await right.async_shutdown()


@pytest.mark.usefixtures("mock_coordinator_connected")
async def test_disconnect_during_first_dis_read_stops_stale_session_reads(
    sleepys_coordinator: AdjustableBedCoordinator,
    mock_bleak_client,
) -> None:
    """A completed read from a dropped client cannot trigger the second read or store."""
    mock_bleak_client.services = [
        _service("1000", "1001", "1002"),
        _service(
            DEVICE_INFO_SERVICE_UUID,
            DEVICE_INFO_CHARS["manufacturer_name"],
            DEVICE_INFO_CHARS["software_revision"],
        ),
    ]
    mock_bleak_client.start_notify = AsyncMock()
    reads: list[str] = []

    async def read(characteristic_uuid: str) -> bytes:
        reads.append(characteristic_uuid)
        mock_bleak_client.is_connected = False
        sleepys_coordinator._on_disconnect(mock_bleak_client)
        return b"stale"

    mock_bleak_client.read_gatt_char = AsyncMock(side_effect=read)
    mock_bleak_client.write_gatt_char = AsyncMock()

    connected, generic_dis = await _connect_with_real_startup(sleepys_coordinator)
    assert not connected
    assert reads == [DEVICE_INFO_CHARS["manufacturer_name"]]
    assert sleepys_coordinator._ble_manufacturer is None
    assert sleepys_coordinator._ble_model is None
    generic_dis.assert_not_awaited()
    await sleepys_coordinator.async_shutdown()


async def test_remote_timer_notifications_update_the_declared_select(
    sleepys_runtime: SleepysRuntime,
) -> None:
    _hass, coordinator, controller, client = sleepys_runtime
    characteristic = _FakeGattCharacteristic("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
    controller._notify_characteristic = characteristic
    select = AdjustableBedMassageTimerSelect(
        coordinator, MASSAGE_TIMER_DESCRIPTION, [10, 20, 30], has_off=False
    )

    def status(seconds: int) -> bytearray:
        packet = bytearray(16)
        packet[:2] = b"\xa5\x0b"
        packet[4:6] = seconds.to_bytes(2, "big")
        packet[14] = 1
        return packet

    controller._handle_notification(characteristic, status(600))
    assert coordinator.controller_state["sleepys_app_field_0x0b"] == 1
    assert select.current_option == "10 min"

    controller._handle_notification(characteristic, status(1200))
    assert coordinator.controller_state["sleepys_app_field_0x0b"] == 2
    assert select.current_option == "20 min"

    stale_characteristic = _FakeGattCharacteristic(
        "6E400003-B5A3-F393-E0A9-E50E24DCCA9F"
    )
    before_stale = dict(coordinator.controller_state)
    controller._handle_notification(stale_characteristic, status(1800))
    controller._handle_notification(characteristic, bytearray.fromhex("A5 0B 00"))
    assert coordinator.controller_state == before_stale
    assert select.current_option == "20 min"

    with _ready_command_lane(coordinator):
        await select.async_select_option("20 min")
    client.write_gatt_char.assert_not_awaited()
    await coordinator.async_shutdown()


def _target_unique_ids(coordinator: AdjustableBedCoordinator) -> set[str]:
    """The unique IDs the head, foot and lumbar target numbers have always had."""
    return {
        f"{coordinator.address}_controller_number_sleepys_app_target_axis_{axis}"
        for axis in range(3)
    }


async def test_box25_reports_reach_the_position_system_and_its_sliders(
    sleepys_runtime: SleepysRuntime,
) -> None:
    hass, coordinator, controller, client = sleepys_runtime
    coordinator._disable_angle_sensing = False
    client.start_notify = AsyncMock()
    await coordinator.async_start_notify()
    characteristic = controller._notify_characteristic
    assert characteristic is not None

    controller._handle_notification(characteristic, bytearray(_POSITION_REPORT))

    assert coordinator.position_data == {"head": 22.0, "feet": 0.0, "lumbar": 40.0}
    numbers = _number_entities_for(hass, coordinator)
    sliders = [entity for entity in numbers if isinstance(entity, AdjustableBedPositionNumber)]
    # Each slider is the target number's own registry row, now showing the report.
    assert {slider.unique_id for slider in sliders} == _target_unique_ids(coordinator)
    assert [slider.native_value for slider in sliders] == [22.0, 0.0, 40.0]
    assert [slider.translation_key for slider in sliders] == [
        "head_position",
        "feet_position",
        "lumbar_position",
    ]
    assert len({entity.unique_id for entity in numbers}) == len(numbers)
    # The same value is not shown a second time as a sensor.
    assert not any(
        "position" in str(entity.unique_id) for entity in _sensor_entities_for(hass, coordinator)
    )
    head = next(spec for spec in controller.motor_control_specs if spec.key == "head")
    cover = AdjustableBedCover(coordinator, _build_cover_description(head))
    assert cover.current_cover_position == 22
    await coordinator.async_shutdown()


async def test_a_control_box_without_reports_keeps_its_target_numbers(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_ADDRESS,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: BED_TYPE_SLEEPYS_ELITE_APP,
            CONF_SLEEPYS_ELITE_SELECTOR: "BOX2442",
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = SleepysEliteAppController(coordinator, "BOX2442")
    coordinator._controller = controller
    controller.follow_autonomous_move = AsyncMock()  # type: ignore[method-assign]
    controller._write_route = AsyncMock()  # type: ignore[method-assign]

    numbers = _number_entities_for(hass, coordinator)
    assert {
        entity.unique_id for entity in numbers if isinstance(entity, AdjustableBedControllerNumber)
    } == _target_unique_ids(coordinator)
    assert not any(isinstance(entity, AdjustableBedPositionNumber) for entity in numbers)
    with raises_key("position_feedback_not_supported", ServiceValidationError):
        _position_config(coordinator, controller, "back", 30)

    # Nothing asks this control box for a position or waits on one after a target.
    await controller.read_positions()
    controller._write_route.assert_not_awaited()
    await controller.set_position_target(2, 100)
    controller.follow_autonomous_move.assert_not_awaited()
    assert not controller.supports_position_feedback


async def test_box25_target_and_recall_follow_and_other_actions_do_not(
    sleepys_runtime: SleepysRuntime,
) -> None:
    _hass, coordinator, controller, client = sleepys_runtime
    clock = _VirtualClock()
    follow = AsyncMock()
    controller.follow_autonomous_move = follow  # type: ignore[method-assign]
    with (
        patch.object(controller, "_monotonic", clock.monotonic),
        patch.object(controller, "_sleep", clock.sleep),
    ):
        await controller.set_motor_position("feet", 100)
        assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
            bytes.fromhex("03 F0 01 64 00")
        ]
        assert follow.await_count == 1
        for key, builder in (
            ("sleepys_app_memory_1", "m1"),
            ("sleepys_app_preset_flat", "flatPosition"),
        ):
            await clock.run_until(asyncio.create_task(controller._press_app_action(key, builder)))
        assert follow.await_count == 3
        for key, builder in (
            ("sleepys_app_save_tv", "saveTv"),
            ("sleepys_app_light_mode", "underbedLighting"),
        ):
            await clock.run_until(asyncio.create_task(controller._press_app_action(key, builder)))
        await clock.run_until(asyncio.create_task(controller.hold_control("headUp", 300)))
        await controller.lights_on()

    assert follow.await_count == 3
    await coordinator.async_shutdown()


@pytest.mark.parametrize("stop_during", ["follow", "release"])
async def test_stop_after_a_recall_started_still_reaches_the_bed(
    sleepys_runtime: SleepysRuntime, monkeypatch: pytest.MonkeyPatch, stop_during: str
) -> None:
    """The recall's own release frame starts the move, so it stops nothing."""
    _hass, coordinator, controller, client = sleepys_runtime
    coordinator._disable_angle_sensing = False
    monkeypatch.setattr(f"{_BASE}._FOLLOW_BOUND_SECONDS", 30.0)
    monkeypatch.setattr(f"{_BASE}._FOLLOW_STEP_SECONDS", 0.01)
    monkeypatch.setattr(f"{_APP}.SLEEPYS_ELITE_NATIVE_ACTION_MS", 1)
    stop = controller._route("stop").payload
    writes: list[bytes] = []
    release_started = asyncio.Event()
    release_may_finish = asyncio.Event()

    async def write(_characteristic: object, payload: bytes, *, response: bool = True) -> None:
        if bytes(payload) == stop and not release_started.is_set():
            release_started.set()
            if stop_during == "release":
                await release_may_finish.wait()
        writes.append(bytes(payload))

    client.write_gatt_char.side_effect = write
    button = ControllerActionButton(
        coordinator,
        next(
            spec
            for spec in controller.controller_button_specs
            if spec.key == "sleepys_app_memory_1"
        ),
    )
    with _ready_command_lane(coordinator):
        press = asyncio.create_task(button.async_press())
        async with asyncio.timeout(2):
            await release_started.wait()
        if stop_during == "follow":
            await asyncio.sleep(0.05)
            assert stop in writes and not press.done()

        stopping = asyncio.create_task(coordinator.async_stop_command())
        await asyncio.sleep(0.05)
        release_may_finish.set()
        await asyncio.gather(press, stopping, return_exceptions=True)

    assert writes.count(stop) == 2
    await coordinator.async_shutdown()
