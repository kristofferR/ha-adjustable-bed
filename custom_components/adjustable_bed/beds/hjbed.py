"""HJBed 2.1.2: exact product controls and ordered BLE receive state."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, cast

from homeassistant.util import dt as dt_util

from ..codec import richmat as codec
from ..hjbed_catalog import ACTIONS, MUSIC_ACTIONS, PRODUCTS, Action
from ..hjbed_protocol import (
    Alarm,
    add_alarm,
    clock,
    color,
    control_mode,
    delete_alarm,
    function,
    light_time,
    query_alarms,
    sync_time,
)
from ..hjbed_receive import Value
from ..hjbed_requests import Request
from ..hjbed_state import GESTURE_RELEASE, NonProgressFrame, State, Stream
from ..profiles.richmat import HJBED
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    require_controller,
)
from .builder import BuildContext

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

# The app's refresh tick and minimum write spacing, menu-probe spacing and BJRN save wait.
TICK_MS = 100
TICK_S = 0.1
MENU_PROBE_S = 0.3
BJRN_SAVE_WAIT_S = 3

# Order is the artifact's enum table. Selection iterates the returned services.
GATT = {
    codec.TRANSPORTS[key].service_uuid: (
        codec.TRANSPORTS[key].write_uuid,
        codec.TRANSPORTS[key].single,
    )
    for key in HJBED.transports
}


def select_transport(
    client: BleakClient,
) -> tuple[BleakGATTCharacteristic, BleakGATTCharacteristic, bool]:
    """First write/notify persist; last matched service sets generic packet mode."""
    write = notify = None
    single = False
    for service in client.services:
        pair = GATT.get(service.uuid.lower())
        if pair is None:
            continue
        uuid, single = pair
        for characteristic in service.characteristics:
            if (
                write is None
                and characteristic.uuid.lower() == uuid
                and "write" in characteristic.properties
            ):
                write = characteristic
            if notify is None and "notify" in characteristic.properties:
                notify = characteristic
    if write is None or notify is None:
        raise ValueError("HJBed requires its writable and notification characteristics")
    return write, notify, single


def action_key(action: Action) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", action.key).lower()


def action_label(action: Action) -> str:
    return (
        re.sub(r"(?<!^)(?=[A-Z])", " ", action.key)
        .replace("Lumber", "Lumbar")
        .replace("Tile", "Tilt")
    )


async def _action(controller: BedController, *, detail: str, save: bool = False) -> None:
    await require_controller(controller, HJBedController).async_execute_hjbed_action(
        detail, save=save
    )


@dataclass(frozen=True, slots=True)
class Session:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    single: bool
    address: str


class HJBedController(BedController):
    """Opt-in product profile; shared UUIDs never select an HJBed layout."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, profile: str) -> None:
        super().__init__(coordinator)
        if profile not in PRODUCTS:
            raise ValueError("Choose the exact product shown in HJBed")
        self.profile = HJBED
        self.product_key = profile
        self._target_address = coordinator.address
        self.product = PRODUCTS[profile]
        self._session: Session | None = None
        self._timer: asyncio.TimerHandle | None = None
        self._last_write: float | None = None
        self._state = State()
        self._rejection: str | None = None
        self._motion = False
        # No wire event proves a complete/empty alarm table. Only a slot freed
        # by this session is safe to allocate without an explicit user choice.
        self._free_alarm_slots: set[int] = set()
        self._stream = Stream(self._event, self._arm_timer, self._cancel_timer)
        previous = coordinator.capability_controller
        if (
            isinstance(previous, HJBedController)
            and previous.product_key == profile
            and previous._target_address == coordinator.address
        ):
            self._state = deepcopy(previous._state)
            self._state.pending_alarm = None
            self._motion = previous._motion

    @property
    def control_characteristic_uuid(self) -> str:
        return self._session.write.uuid if self._session else next(iter(GATT.values()))[0]

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def supports_motor_control(self) -> bool:
        return bool(self.motor_control_specs)

    @property
    def supports_preset_flat(self) -> bool:
        return False  # Reset has a product-specific gesture, exposed by its own button.

    @property
    def supports_preset_zero_g(self) -> bool:
        return False

    @property
    def supports_preset_anti_snore(self) -> bool:
        return False

    @property
    def supports_preset_tv(self) -> bool:
        return False

    @property
    def memory_slot_count(self) -> int:
        return 0  # Named detail buttons preserve short/sustained recall and save gestures.

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.product.coupled

    @property
    def persisted_app_state_key(self) -> str:
        return f"hjbed:{self.product_key}"

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {"saved_alarm": deepcopy(self._state.saved_alarm), "motion_layout": self._motion}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        motion = state.get("motion_layout", False)
        if type(motion) is not bool:
            raise ValueError("Invalid HJBed layout")
        self._motion = motion
        value = state.get("saved_alarm")
        if value is not None and (
            not isinstance(value, dict)
            or set(value)
            != {
                "hour",
                "minute",
                "action",
                "clock_datetime_ms",
                "function_enum",
                "action_name",
                "repeat_type",
            }
            or type(value["hour"]) is not int
            or not 0 <= value["hour"] <= 23
            or type(value["minute"]) is not int
            or not 0 <= value["minute"] <= 59
            or not isinstance(value["action"], str)
            or type(value["clock_datetime_ms"]) is not int
            or not isinstance(value["function_enum"], str)
            or not isinstance(value["action_name"], str)
            or value["repeat_type"] is not None
        ):
            raise ValueError("Invalid HJBed saved alarm")
        self._state.saved_alarm = deepcopy(value)

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "profile": self.product_key,
            "product": self.product.label,
            "hardware_verified": False,
            "coupled_default": self.product.coupled,
            "sofa_layout": self.product.sofa,
            "alarm_actions": [action_key(ACTIONS[d]) for d in self.product.alarm],
            "single_code": self._session.single if self._session else None,
            "events": deepcopy(self._state.values),
            "alarm_records": deepcopy(self._state.alarms),
            "saved_alarm": deepcopy(self._state.saved_alarm),
            "available_alarm_slots": self._available_alarm_slots(),
            "last_rejection": self._rejection,
            "remainder": bytes(self._stream.buffer).hex(),
            "features": sorted(self._state.features),
        }

    def _publish(self) -> None:
        self.forward_controller_state_updates(
            {
                "hjbed_status": self._state.last_event,
                "hjbed_layout": "Motion" if self._motion else "Normal",
                "hjbed_events": deepcopy(self._state.values),
                "hjbed_alarms": deepcopy(self._state.alarms),
                "hjbed_saved_alarm": deepcopy(self._state.saved_alarm),
                "hjbed_available_alarm_slots": self._available_alarm_slots(),
                "hjbed_rejection": self._rejection,
            }
        )

    def _event(self, event: str, value: Value) -> None:
        if event in (
            "deviceRepeatAlarmListStatusEvent",
            "deviceRepeatAlarmListEscalationStatusEvent",
        ) and isinstance(value, dict):
            number = value.get("number")
            if type(number) is int:
                self._free_alarm_slots.discard(number)
        self._state.accept(event, value)
        self._publish()

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "hjbed_status",
                "hjbed_status",
                "hjbed_status",
                "mdi:bed",
                attribute_keys=(
                    "hjbed_events",
                    "hjbed_alarms",
                    "hjbed_saved_alarm",
                    "hjbed_available_alarm_slots",
                    "hjbed_rejection",
                ),
            ),
        )

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = None

    def _arm_timer(self) -> None:
        # The fired reference remains until the next handler cancels/nulls it.
        self._timer = asyncio.get_running_loop().call_later(0.5, self._stream.buffer.clear)

    def _notification(
        self, session: Session, _sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if (
            self._session is not session
            or self.client is not session.client
            or not session.client.is_connected
            or session.address != self._coordinator.address
        ):
            return
        self.forward_raw_notification(session.notify.uuid, bytes(data))
        try:
            self._stream.feed(data)
            self._rejection = None
        except (IndexError, NonProgressFrame) as err:
            self._rejection = str(err)
        self._publish()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("HJBed is disconnected")
        self._stream.clear()
        self._free_alarm_slots.clear()
        write, notify, single = select_transport(client)
        session = Session(client, write, notify, single, self._coordinator.address)
        self._session = session
        self._last_write = None
        try:
            await client.start_notify(notify, partial(self._notification, session))
            await self._send(function("deviceFunctionItemExitLimit", 0, 0, single), session)
            # requestProductMenu: clock uses one timestamp/calendar plus a second offset snapshot.
            menu_start = asyncio.get_running_loop().time()
            for frame in sync_time(dt_util.now(), dt_util.now()):
                await self._send(frame, session)
            if self.product.object in (
                ("98fd91", "98fd31") if self._motion else ("98fd91", "98fd31", "98fcd1")
            ):
                await self._send(control_mode(), session)
            for tick, enum in enumerate(
                (
                    "deviceFunctionItemCheckClock",
                    "deviceFunctionItemCheckLight",
                    "deviceFunctionItemCheckMusic",
                ),
                start=1,
            ):
                await asyncio.sleep(
                    max(0, menu_start + tick * MENU_PROBE_S - asyncio.get_running_loop().time())
                )
                await self._send(function(enum, 1, 0, single), session)

        except BaseException:
            self._session = None
            self._stream.clear()
            raise
        self._publish()

    async def stop_notify(self) -> None:
        session, self._session = self._session, None
        self._stream.clear()
        self._state.pending_alarm = None
        self._free_alarm_slots.clear()
        self._publish()
        if session is not None and session.client.is_connected:
            await session.client.stop_notify(session.notify)

    def _current_session(self) -> Session:
        session = self._session
        if (
            session is None
            or self.client is not session.client
            or not session.client.is_connected
            or self._coordinator.address != session.address
        ):
            raise ConnectionError("The HJBed BLE session changed")
        return session

    async def _send(
        self,
        frame: bytes,
        session: Session,
        cancel: asyncio.Event | None = None,
        on_attempt: Callable[[], None] | None = None,
        deadline: float | None = None,
    ) -> bool:
        if cancel is not None and cancel.is_set():
            return False
        if deadline is not None and monotonic() - deadline > 1e-9:
            return False
        if self._last_write is not None:
            await asyncio.sleep(max(0, self._last_write + TICK_S - monotonic()))
        async with self._ble_lock:
            if cancel is not None and cancel.is_set():
                return False
            if deadline is not None and monotonic() - deadline > 1e-9:
                return False
            if self._current_session() is not session:
                raise ConnectionError("The HJBed BLE session changed")
            response = "write-without-response" not in session.write.properties
            self._coordinator.record_command_trace(
                payload={"hex": frame.hex()},
                characteristic_uuid=session.write.uuid,
                characteristic_handle=session.write.handle,
                response=response,
                repeat_count=1,
                repeat_delay_ms=TICK_MS,
                command_origin="hjbed",
                controller_class=type(self).__name__,
            )
            self._last_write = monotonic()
            if on_attempt is not None:
                on_attempt()
            await session.client.write_gatt_char(session.write, frame, response=response)
        return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        session = self._current_session()
        for _ in range(repeat_count):
            if not await self._send(
                command, session, cancel_event or self._coordinator.cancel_command
            ):
                break

    def _detail(self, enum: str, group: tuple[str, ...] | None = None) -> Action:
        for detail in (
            group
            if group is not None
            else (*self.product.motor, *self.product.preset, *self.product.massage)
        ):
            if ACTIONS[detail].enum == enum:
                return ACTIONS[detail]
        raise ValueError(f"{enum} is not available for {self.product.label}")

    async def execute_action(
        self,
        detail: str,
        *,
        save: bool = False,
        motion: bool | None = None,
        hold_ms: int | None = None,
    ) -> None:
        motion = self._motion if motion is None else motion
        action = ACTIONS.get(detail)
        if action is None or (
            detail not in (*self.product.motor, *self.product.massage, *self.product.preset)
            and action not in MUSIC_ACTIONS
            and detail != "975a61"
        ):
            raise ValueError("This HJBed product does not offer that action")
        if save and (detail not in self.product.preset or action.save_code is None):
            raise ValueError("This HJBed preset cannot be saved")
        session = self._current_session()
        sides = (
            (0,)
            if action.kind == "music" or session.single
            else (0, 1)
            if self.command_side == "both"
            else (self._side(),)
        )
        code = action.save_code if save else action.code
        assert code is not None
        cancel = self._coordinator.cancel_command
        sustain = not save and action.sustain and not (motion and action.kind == "reset")
        fired: set[int] = set()

        try:
            if save and self.product.label == "BJRN":
                if not await self._delay(BJRN_SAVE_WAIT_S, cancel):
                    return
            if sustain:
                duration = (
                    hold_ms
                    if hold_ms is not None
                    else self._coordinator.motor_pulse_count * TICK_MS
                )
                start = monotonic()
                deadline = start + duration / 1000
                # A finite pulse needs one serialized pacing slot per side
                # after its last nominal tick. Explicit holds end at duration.
                write_deadline = deadline + (len(sides) * TICK_S if hold_ms is None else 0)
                tick = 1
                while tick * TICK_MS <= duration:
                    if not await self._delay(max(0, start + tick * TICK_S - monotonic()), cancel):
                        break
                    for side in sides:
                        if not await self._send(
                            function(action.enum, code, side, session.single),
                            session,
                            cancel,
                            on_attempt=partial(fired.add, side),
                            deadline=write_deadline,
                        ):
                            break
                    # Periodic ticks do not inherit write latency or drain stale refreshes.
                    tick = max(tick + 1, int((monotonic() - start + 1e-9) / TICK_S) + 1)
                else:
                    remaining = deadline - monotonic()
                    if remaining > 0:
                        await self._delay(remaining, cancel)
            else:
                deadline = monotonic() + hold_ms / 1000 if hold_ms is not None else None
                for side in sides:
                    if not await self._send(
                        function(action.enum, code, side, session.single),
                        session,
                        cancel,
                        on_attempt=partial(fired.add, side),
                        deadline=deadline,
                    ):
                        break
                if deadline is not None and fired and (remaining := deadline - monotonic()) > 0:
                    await self._delay(remaining, cancel)
        finally:
            if fired and action.release and not save:
                # Cleanup belongs to the captured physical session and selected side.
                failure: BaseException | None = None
                for side in sides:
                    if side in fired:
                        try:
                            await self._send(
                                function("deviceFunctionItemStop", 110, side, session.single),
                                session,
                                asyncio.Event(),
                            )
                        except BaseException as err:
                            failure = failure or err
                if failure is not None:
                    raise failure

    async def _delay(self, seconds: float, cancel: asyncio.Event) -> bool:
        try:
            await asyncio.wait_for(cancel.wait(), timeout=seconds)
            return False
        except TimeoutError:
            return True

    def _side(self) -> int:
        if self.command_side not in (None, "left", "right"):
            raise ValueError("HJBed frames select left or right; choose one side")
        return 1 if self.command_side == "right" else 0

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons: list[ControllerButtonSpec] = []
        for detail in dict.fromkeys(
            (
                *self.product.motor,
                *self.product.massage,
                *self.product.preset,
                *(a.object for a in MUSIC_ACTIONS),
            )
        ):
            action = ACTIONS[detail]
            if action.kind == "motor":
                partner = (
                    action.enum.removesuffix("Up") + "Down"
                    if action.enum.endswith("Up")
                    else action.enum.removesuffix("Down") + "Up"
                )
                if action.enum.endswith(("Forword", "Backward")) or any(
                    ACTIONS[d].enum == partner for d in self.product.motor
                ):
                    continue
            key = action_key(action)
            buttons.append(
                ControllerButtonSpec(
                    "hjbed_" + key,
                    action_label(action),
                    partial(_action, detail=detail),
                    translation_key="hjbed_action",
                    translation_placeholders={"action": action_label(action)},
                    hold=ControllerHoldSpec("hjbed_" + key, 0, 0, "hjbed_release")
                    if action.sustain or action.release
                    else None,
                )
            )
            if action.save_code is not None and detail in self.product.preset:
                buttons.append(
                    ControllerButtonSpec(
                        "hjbed_save_" + key,
                        "Save " + action_label(action),
                        partial(_action, detail=detail, save=True),
                        translation_key="hjbed_action",
                        translation_placeholders={"action": "Save " + action_label(action)},
                    )
                )

        async def released(_controller: BedController) -> None:
            # The button platform uses STOP admission to invalidate pending holds.
            # Their own finally owns protocol release; add no unconditional STOP.
            return

        buttons.append(
            ControllerButtonSpec(
                "hjbed_release", "Release held action", released, translation_key="hjbed_release"
            )
        )
        return tuple(buttons)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        specs = []
        for detail in self.product.motor:
            up = ACTIONS[detail]
            if up.kind != "motor" or not (up.enum.endswith("Up") or up.enum.endswith("Forword")):
                continue
            down_enum = (
                up.enum.removesuffix("Up") + "Down"
                if up.enum.endswith("Up")
                else up.enum.removesuffix("Forword") + "Backward"
            )
            if not any(ACTIONS[d].enum == down_enum for d in self.product.motor):
                continue
            down = self._detail(down_enum, self.product.motor)
            axis = (
                "sofa_travel" if up.enum.endswith("Forword") else action_key(up).removesuffix("_up")
            )
            translation = {
                "foot": "feet",
                "head_and_foot": "head_feet",
                "lumber": "lumbar",
                "tile": "tilt",
                "foot_box": "hjbed_foot_box",
                "sofa_travel": "hjbed_sofa_travel",
            }.get(axis, axis)
            specs.append(
                MotorControlSpec(
                    "hjbed_" + axis,
                    translation,
                    partial(_action, detail=up.object),
                    partial(_action, detail=down.object),
                    lambda c: c.stop_all(),
                    hold=ControllerMotorHoldSpec(
                        "hjbed_" + axis + "_up",
                        "hjbed_" + axis + "_down",
                        0,
                        0,
                        "hjbed_release",
                        stop_scope="side",
                    ),
                )
            )
        return tuple(specs)

    async def _move(self, enum: str) -> None:
        await self.execute_action(
            self._detail("deviceFunctionItem" + enum, self.product.motor).object
        )

    async def move_head_up(self) -> None:
        await self._move("HeadUp")

    async def move_head_down(self) -> None:
        await self._move("HeadDown")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._move("FootUp")

    async def move_legs_down(self) -> None:
        await self._move("FootDown")

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        if GESTURE_RELEASE.get():
            return
        session = self._current_session()
        if self.command_side == "both":
            for side in (0,) if session.single else (0, 1):
                await self._send(
                    function("deviceFunctionItemStop", 110, side, session.single),
                    session,
                    asyncio.Event(),
                )
            return
        await self._send(
            function("deviceFunctionItemStop", 110, self._side(), session.single),
            session,
            asyncio.Event(),
        )

    async def preset_flat(self) -> None:
        await self._move("MotorReset")

    async def preset_memory(self, memory_num: int) -> None:
        action = self._detail(f"deviceFunctionItemMemoryPosition{memory_num}", self.product.preset)
        await self.execute_action(action.object)

    async def program_memory(self, memory_num: int) -> None:
        action = self._detail(f"deviceFunctionItemMemoryPosition{memory_num}", self.product.preset)
        await self.execute_action(action.object, save=True)

    async def async_execute_hjbed_action(self, detail: str, *, save: bool = False) -> None:
        await self.execute_action(detail, save=save)

    def _hold_actions(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for detail in (*self.product.motor, *self.product.massage, *self.product.preset):
            action = ACTIONS[detail]
            if not (action.sustain or action.release):
                continue
            key = action_key(action)
            if action.enum.endswith(("Forword", "Backward")):
                key = "sofa_travel_" + ("up" if action.enum.endswith("Forword") else "down")
            result["hjbed_" + key] = detail
        return result

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(self._hold_actions())

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self._hold_actions()
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise ValueError(
                "Choose an available HJBed hold control and duration from 1 to 60000 ms"
            )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.execute_action(self._hold_actions()[control], hold_ms=duration_ms)

    def _layout(self, option: str) -> None:
        if option not in ("Normal", "Motion"):
            raise ValueError("Choose Normal or Motion")
        self._motion = option == "Motion"
        self._publish()

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        async def select(controller: BedController, option: str) -> None:
            # Local selections resolve the current spec in the entity platform.
            if not isinstance(controller, HJBedController):
                raise TypeError("HJBed layout requires HJBed")
            controller._layout(option)

        return (
            ControllerSelectSpec(
                "hjbed_layout",
                "hjbed_layout",
                "hjbed_layout",
                ("Normal", "Motion"),
                select,
                local_select_fn=self._layout,
            ),
        )

    def _eligible(self, feature: str) -> bool:
        flag = self.product.alarms if feature == "alarm" else self.product.light
        return flag and feature in self._state.features

    def _alarm_action(self, key: str | None) -> Action:
        for detail in self.product.alarm:
            action = ACTIONS[detail]
            if action_key(action) == key:
                return action
        raise ValueError("Choose an alarm action listed for this HJBed product")

    def _alarm_record(self, number: int | None) -> Alarm:
        row = next((a for a in self._state.alarms if a.get("number") == number), None)
        if row is None:
            raise ValueError("Refresh alarms and choose an observed alarm number")
        fields = ("number", "kind", "hour", "minute", "code", "repeat")
        values = [row.get(key) for key in fields]
        data = row.get("data")
        if (
            any(type(v) is not int for v in values)
            or not isinstance(data, list)
            or any(type(v) is not int for v in data)
        ):
            raise ValueError("Invalid received alarm bean")
        return Alarm(*(cast(int, v) for v in values), data=tuple(cast(int, v) for v in data))

    def _available_alarm_slots(self) -> list[int]:
        return sorted(
            number
            for number in self._free_alarm_slots
            if not any(row.get("number") == number for row in self._state.alarms)
        )

    def validate_hjbed_request(self, request: Request) -> None:
        op = request.operation
        if op in ("single", "cancel_single", "repeat", "delete", "query", "toggle"):
            if not self._eligible("alarm"):
                raise ValueError(
                    "This product requires its alarm eligibility and clock acknowledgement"
                )
            if (op in ("single", "cancel_single")) == self.product.repeat:
                raise ValueError("Choose the single or repeating alarm operation for this product")
        if op in ("single", "repeat"):
            self._alarm_action(request.action)
            if request.when is None or request.when.second or request.when.microsecond:
                raise ValueError("Setting an HJBed alarm requires a time with minute precision")
        if op in ("delete", "toggle"):
            if type(request.alarm_id) is not int or not 1 <= request.alarm_id <= 7:
                raise ValueError("Choose an alarm number from 1 to 7")
        if op == "toggle":
            self._alarm_record(request.alarm_id)
        if op == "repeat":
            if request.alarm_id is not None and (
                type(request.alarm_id) is not int or not 1 <= request.alarm_id <= 7
            ):
                raise ValueError("Choose an alarm number from 1 to 7")
            if any(type(day) is not int or not 0 <= day <= 6 for day in request.weekdays):
                raise ValueError("Choose weekdays Monday through Sunday")
            if request.alarm_id is None and all(
                any(row.get("number") == i for row in self._state.alarms) for i in range(1, 8)
            ):
                raise ValueError("All seven HJBed alarm slots are occupied")
            if request.alarm_id is None and not self._available_alarm_slots():
                raise ValueError(
                    "Choose an explicit alarm_id; unobserved slots are not known to be free. "
                    "Automatic allocation can reuse a slot deleted in this connection."
                )
        if op in ("light_timeout", "light_color") and not self._eligible("light"):
            raise ValueError(
                "This product requires its light-page eligibility and light acknowledgement"
            )
        if op == "light_timeout":
            minimum, maximum = (1800, 28800) if self.product.object == "98fcd1" else (0, 900)
            if type(request.seconds) is not int or not minimum <= request.seconds <= maximum:
                raise ValueError(
                    f"Choose an HJBed light timeout from {minimum} to {maximum} seconds"
                )
        if op == "light_color":
            if (
                request.rgb is None
                or len(request.rgb) != 3
                or any(type(v) is not int or not 0 <= v <= 255 for v in request.rgb)
            ):
                raise ValueError("Choose three RGB channel values from 0 to 255")
        if op == "mode":
            if self.product.object not in ("98fd91", "98fd31", "98fcd1") or self._motion:
                raise ValueError(
                    "Control mode belongs to the Normal layout for blue, green or orange"
                )
            if request.mode not in ("split_head", "standard"):
                raise ValueError("Choose split_head or standard")
        if type(request.enabled) is not bool:
            raise ValueError("enabled must be a boolean")

    async def async_execute_hjbed_request(self, request: Request) -> None:
        self.validate_hjbed_request(request)
        session = self._current_session()
        op = request.operation
        frames: tuple[bytes, ...]
        reserved_slot: int | None = None
        if op == "sync":
            frames = sync_time(dt_util.now(), dt_util.now())
        elif op == "light_timeout":
            assert request.seconds is not None
            if not await self._delay(0.2, self._coordinator.cancel_command):
                return
            frames = (light_time(request.seconds),)
        elif op == "light_color":
            assert request.rgb is not None
            frames = (color(request.rgb),)
        elif op == "mode":
            frames = (control_mode(0 if request.mode == "split_head" else 2),)
        elif op == "query":
            self._state.alarms.clear()
            self._free_alarm_slots.clear()
            self._publish()
            frames = (query_alarms(),)
        elif op == "delete":
            assert request.alarm_id is not None
            frames = (delete_alarm(request.alarm_id),)
        elif op == "toggle":
            record = self._alarm_record(request.alarm_id)
            reserved_slot = record.number
            # Preserve imported/custom payloads. The app's toggle constructor drops
            # kind1 data, a narrow safety deviation documented in the ledger.
            from dataclasses import replace

            frames = (add_alarm(replace(record, repeat=(record.repeat & 254) | request.enabled)),)
        elif op == "repeat":
            assert request.when is not None
            number = request.alarm_id or self._available_alarm_slots()[0]
            reserved_slot = number
            repeat = sum(1 << (7 - day) for day in set(request.weekdays)) | request.enabled
            record = Alarm(
                number,
                0,
                request.when.hour,
                request.when.minute,
                self._alarm_action(request.action).code,
                repeat,
            )
            frames = (add_alarm(record),)
        elif op == "cancel_single":
            frames = clock(0, 0)
        else:
            assert request.when is not None
            now = dt_util.now().replace(second=0, microsecond=0)
            then = now.replace(hour=request.when.hour, minute=request.when.minute)
            seconds = int(then.timestamp()) - int(now.timestamp())
            if seconds <= 0:
                seconds += 86400
            selected_action = self._alarm_action(request.action)
            self._state.pending_alarm = {
                "clock_datetime_ms": int(then.timestamp() * 1000),
                "function_enum": selected_action.enum,
                "action_name": action_label(selected_action),
                "repeat_type": None,
                "hour": request.when.hour,
                "minute": request.when.minute,
                "action": request.action,
            }
            frames = clock(int(seconds / 60), self._alarm_action(request.action).code)
        deleted_alarm = (
            next((row for row in self._state.alarms if row.get("number") == request.alarm_id), None)
            if op == "delete"
            else None
        )

        def reserve_alarm_slot() -> None:
            if reserved_slot is not None:
                if (
                    op == "repeat"
                    and request.alarm_id is None
                    and reserved_slot not in self._available_alarm_slots()
                ):
                    raise ValueError(
                        "The automatically selected alarm slot is no longer free; "
                        "choose an explicit alarm_id."
                    )
                self._free_alarm_slots.discard(reserved_slot)
                self._publish()

        for frame in frames:
            if not await self._send(
                frame, session, self._coordinator.cancel_command, on_attempt=reserve_alarm_slot
            ):
                return
        if deleted_alarm is not None and deleted_alarm in self._state.alarms:
            self._state.alarms.remove(deleted_alarm)
        if op == "delete":
            assert request.alarm_id is not None
            self._free_alarm_slots.add(request.alarm_id)
        self._publish()


async def build_controller(ctx: BuildContext) -> HJBedController:
    """Build the controller for the selected profile."""
    return HJBedController(ctx.coordinator, profile=ctx.variant or "")
