"""Independence controls, neutral release, and status for one Okin receiver."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTime

from ...card import CARD_LIGHTING, CARD_PRESETS
from ...codec import okin_nframe as codec
from ...command_scheduler import current_command_context, note_frame_skipped
from ...const import DEVICE_INFO_SERVICE_UUID
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...profiles import customatic_demo as app
from ...profiles.okin_nframe import OkinNFrameProfile
from ..base import BedController, ProfileExecution, require_controller
from ..cancellation import settled
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession

LIGHT_TIMER: Final = StateKey[int | None]("customatic_demo_light_timer")
DEMO_MODE: Final = StateKey[bool | None]("customatic_demo_mode")
BED_PROBLEM: Final = StateKey[bool | None]("customatic_demo_problem")
_WRITE_TIMEOUT_S: Final = 5.0  # HA transport bound for each GATT attempt.


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    started: float
    generation: int


def _role(client: BleakClient, service_uuid: str, uuid: str) -> BleakGATTCharacteristic | None:
    matches = [
        char
        for service in client.services
        if service.uuid.lower() == service_uuid
        for char in service.characteristics
        if char.uuid.lower() == uuid
    ]
    return matches[0] if len(matches) == 1 else None


class CustomaticDemoController(ProfileExecution[OkinNFrameProfile], BedController):
    """The Independence app's fixed controls over the 96-bit CST frame."""

    profile = app.PROFILE

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._link: _Link | None = None
        self._released_intent_id: str | None = None
        self._demo_cancel: asyncio.Event | None = None
        self._reported_demo = False
        self._reported_problem = False

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.WRITE_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def sequential_stop_on_current_link(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    def _link_is_current(self, link: _Link) -> bool:
        return (
            self._link is link
            and self.client is link.client
            and link.client.is_connected
            and self._coordinator.connection_generation == link.generation
        )

    def _require_link(self, link: _Link | None = None) -> _Link:
        link = self._link if link is None else link
        if link is None or not self._link_is_current(link):
            raise BedNotConnectedError
        return link

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError
        async with self._ble_lock:
            if self.client is not client or not client.is_connected:
                raise BedNotConnectedError
            if self._link is not None and self._link_is_current(self._link):
                return
            if self._link is not None:
                self.on_disconnect()
            write = _role(client, codec.SERVICE_UUID, codec.WRITE_UUID)
            notify = _role(client, codec.SERVICE_UUID, codec.STATUS_UUID)
            if (
                write is None
                or not {"write", "write-without-response"}.intersection(write.properties)
                or notify is None
                or "notify" not in notify.properties
            ):
                raise BedNotConnectedError("customatic_demo_gatt_missing")
            link = _Link(
                client,
                write,
                notify,
                asyncio.get_running_loop().time(),
                self._coordinator.connection_generation,
            )
            self._link = link

            def receive(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
                if self._link_is_current(link):
                    self._receive(data)

            try:
                await client.start_notify(notify, receive)
            except BaseException:
                if self._link is link:
                    self.on_disconnect()
                raise

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        link = self._require_link()
        await asyncio.sleep(app.QUERY_DELAY_S)
        await self._write(link, app.STATUS_QUERY, cancel_event=asyncio.Event(), track=False)

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        link = self._require_link()
        char = _role(link.client, DEVICE_INFO_SERVICE_UUID, app.MANUFACTURER_UUID)
        if char is not None and "read" in char.properties:
            loop = asyncio.get_running_loop()
            await asyncio.sleep(max(0, link.started + app.MANUFACTURER_DELAY_S - loop.time()))
            try:
                async with asyncio.timeout(2), self._ble_lock:
                    self._require_link(link)
                    manufacturer = await link.client.read_gatt_char(char)
            except BleakError, OSError, TimeoutError:
                pass  # The manufacturer string is optional BLE device information.
            else:
                if self._link_is_current(link):
                    session.store_device_info(manufacturer.decode("utf-8", errors="replace"), None)
        return True

    def on_disconnect(self) -> None:
        had_link = self._link is not None
        self._link = None
        self._released_intent_id = None
        self._reported_demo = False
        self._reported_problem = False
        if self._demo_cancel is not None:
            self._demo_cancel.set()
        if had_link:
            self.forward_controller_state_updates(
                LIGHT_TIMER(None), BED_PROBLEM(None), DEMO_MODE(None)
            )

    async def stop_notify(self) -> None:
        async with self._ble_lock:
            link = self._link
            current = link is not None and self._link_is_current(link)
            self.on_disconnect()
            if current and link is not None:
                await link.client.stop_notify(link.notify)

    def _receive(self, data: bytearray) -> None:
        self.forward_raw_notification(codec.STATUS_UUID, bytes(data))
        if len(data) < 14:
            return
        timer = {1: 2, 2: 3, 3: 5}.get(data[10])
        problem = any(data[11:13]) or (len(data) >= 16 and any(data[14:16]))
        demo = data[13] in (1, 3)
        if self._demo_cancel is not None and (problem or (self._reported_demo and not demo)):
            self._demo_cancel.set()
        self._reported_demo = demo
        self._reported_problem = problem
        self.forward_controller_state_updates(
            LIGHT_TIMER(timer), BED_PROBLEM(problem), DEMO_MODE(demo)
        )

    async def _write(
        self,
        link: _Link,
        command: bytes,
        cancel_event: asyncio.Event | None = None,
        *,
        track: bool = True,
        deadline: float | None = None,
        still_admitted: Callable[[], bool] | None = None,
    ) -> None:
        def require_session() -> None:
            self._require_link(link)
            # This callback runs under the BLE lock at the actual write boundary.
            if still_admitted is not None and not still_admitted():
                note_frame_skipped()
                raise asyncio.CancelledError

        self._require_link(link)
        timeout_at = asyncio.get_running_loop().time() + _WRITE_TIMEOUT_S
        if deadline is not None:
            timeout_at = min(timeout_at, deadline)
        async with asyncio.timeout_at(timeout_at):
            await self._write_gatt_with_retry(
                codec.WRITE_UUID,
                command,
                cancel_event=cancel_event,
                response="write" in link.write.properties,
                characteristic=link.write,
                expected_client=link.client,
                before_write=require_session,
                track_command_write=track,
            )

    async def _release(self, link: _Link) -> None:
        cancel = asyncio.Event()
        loop = asyncio.get_running_loop()
        hold = self.profile.hold
        stop = codec.frame(self.profile.keys["stop"], self.profile.width)
        first_at = loop.time() + hold.release_after_ms / 1000
        await asyncio.sleep(max(0, first_at - loop.time()))
        try:
            await self._write(link, stop, cancel, track=False)
        finally:
            await asyncio.sleep(max(0, first_at + hold.release_ms / 1000 - loop.time()))
            await self._write(link, stop, cancel, track=False)
        context = current_command_context()
        if context is not None:
            context.cleanup_stop_sent = True
            self._released_intent_id = context.intent_id

    async def _press(
        self,
        control: str,
        duration_ms: int | None = None,
        *,
        still_admitted: Callable[[], bool] | None = None,
    ) -> None:
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return
        link = self._require_link()
        context = current_command_context()
        if context is not None:
            context.cleanup_stop_sent = False
        self._released_intent_id = None
        command = codec.frame(self.profile.keys[control], self.profile.width)
        async with self.releasing(lambda: self._release(link)):
            if duration_ms is None:
                await self._write(link, command, cancel, still_admitted=still_admitted)
                return

            loop = asyncio.get_running_loop()
            deadline = loop.time() + duration_ms / 1000
            count = (duration_ms + app.REFRESH_MS - 1) // app.REFRESH_MS
            for _ in range(count):
                started = loop.time()
                if cancel.is_set() or started >= deadline:
                    break
                await self._write(
                    link, command, cancel, deadline=deadline, still_admitted=still_admitted
                )
                try:
                    async with asyncio.timeout_at(min(deadline, started + app.REFRESH_MS / 1000)):
                        await cancel.wait()
                except TimeoutError:
                    pass

    async def stop_all(self) -> None:
        context = current_command_context()
        released = self._released_intent_id
        if (
            context is not None
            and released is not None
            and any(
                c.intent_id == released and c.cleanup_stop_sent
                for c in (context, *context.preempted_contexts)
            )
        ):
            return
        await self._release(self._require_link())

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (*app.MOTOR_CONTROLS, *app.BUTTON_CONTROLS)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise invalid(
                "held_control_not_supported",
                device_name=self._coordinator.name,
                control=control,
                valid_controls=", ".join(self.held_control_options),
            )
        if type(duration_ms) is not int or not 1 <= duration_ms <= 60000:
            raise invalid("hold_lease_duration", min=1, max=60000)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._press(control, self.leased_hold_ms(duration_ms))

    async def _move(self, control: str) -> None:
        duration = max(1, self._coordinator.motor_pulse_count) * app.REFRESH_MS
        await self.hold_control(control, min(duration, 60000))

    async def move_back_up(self) -> None:
        await self._move("back_up")

    async def move_back_down(self) -> None:
        await self._move("back_down")

    async def move_legs_up(self) -> None:
        await self._move("legs_up")

    async def move_legs_down(self) -> None:
        await self._move("legs_down")

    move_head_up = move_back_up
    move_head_down = move_back_down
    move_feet_up = move_legs_up
    move_feet_down = move_legs_down
    move_back_stop = move_head_stop = move_legs_stop = move_feet_stop = stop_all

    async def preset_flat(self) -> None:
        await self._press("auto_flat")

    async def lights_toggle(self) -> None:
        await self._press("light_toggle")

    async def preset_memory(self, memory_num: int) -> None:
        raise self.not_supported("memory")

    async def program_memory(self, memory_num: int) -> None:
        raise self.not_supported("memory programming")

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        if key == "preset_flat":
            return ControllerHoldSpec("auto_flat")
        if key == "toggle_light":
            return ControllerHoldSpec("light_toggle")
        return None

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                axis if axis in ("back", "legs") else f"customatic_demo_{axis}",
                lambda ctrl, axis=axis: require_controller(ctrl, CustomaticDemoController)._move(
                    f"{axis}_up"
                ),
                lambda ctrl, axis=axis: require_controller(ctrl, CustomaticDemoController)._move(
                    f"{axis}_down"
                ),
                lambda ctrl: ctrl.stop_all(),
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up",
                    f"{axis}_down",
                    press_hold_ms=None,
                    stop_scope="side",
                ),
            )
            for axis in app.MOTOR_AXES
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec(
                "customatic_demo_auto_sit",
                "Automatic sitting up",
                lambda ctrl: require_controller(ctrl, CustomaticDemoController)._press("auto_sit"),
                translation_key="customatic_demo_auto_sit",
                icon="mdi:seat",
                card=CARD_PRESETS,
                hold=ControllerHoldSpec("auto_sit"),
            ),
            ControllerButtonSpec(
                "customatic_demo_light_auto",
                "Automatic under-bed light",
                lambda ctrl: require_controller(ctrl, CustomaticDemoController)._press(
                    "light_auto"
                ),
                translation_key="customatic_demo_light_auto",
                icon="mdi:lightbulb-auto",
                card=CARD_LIGHTING,
                hold=ControllerHoldSpec("light_auto"),
            ),
            ControllerButtonSpec(
                "customatic_demo_light_timer_cycle",
                "Cycle under-bed light timer",
                lambda ctrl: require_controller(ctrl, CustomaticDemoController)._press(
                    "light_timer"
                ),
                translation_key="customatic_demo_light_timer_cycle",
                icon="mdi:timer-sync-outline",
                card=CARD_LIGHTING,
                hold=ControllerHoldSpec("light_timer"),
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                LIGHT_TIMER,
                LIGHT_TIMER,
                LIGHT_TIMER,
                "mdi:timer-outline",
                native_unit_of_measurement=UnitOfTime.MINUTES,
                entity_registry_enabled_default=True,
                entity_category=None,
                device_class=SensorDeviceClass.DURATION,
            ),
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            ControllerStateBinarySensorSpec(
                DEMO_MODE,
                DEMO_MODE,
                DEMO_MODE,
                "mdi:play-circle-outline",
                entity_registry_enabled_default=True,
                entity_category=None,
            ),
            ControllerStateBinarySensorSpec(
                BED_PROBLEM,
                BED_PROBLEM,
                BED_PROBLEM,
                None,
                device_class=BinarySensorDeviceClass.PROBLEM,
            ),
        )

    async def run_demo(self, *, still_admitted: Callable[[], bool] | None = None) -> None:
        """Run one confirmed sit/flat cycle in the scheduler's command lane."""
        if self._reported_problem:
            raise invalid("customatic_demo_bed_problem")
        link = self._require_link()
        stop = self._coordinator.cancel_command
        abort = asyncio.Event()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + app.DEMO_PHASE_S
        self._demo_cancel = abort

        def stopped() -> bool:
            return stop.is_set() or (still_admitted is not None and not still_admitted())

        try:
            await self._press("auto_sit", app.DEMO_PRESS_MS, still_admitted=still_admitted)
            if stopped() or abort.is_set():
                return
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError

            # The sit phase's release predates any STOP admitted during the pause.
            self._released_intent_id = None
            context = current_command_context()
            if context is not None:
                context.cleanup_stop_sent = False
            tasks = {asyncio.create_task(event.wait()) for event in (stop, abort)}
            interrupted = True
            try:
                try:
                    await asyncio.wait(
                        tasks, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
                    )
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                interrupted = False
            finally:
                # Settle fresh neutral before the pair can give up this link.
                if (stopped() or interrupted) and self._link_is_current(link):
                    await settled(self._release(link))
            if not stopped() and not abort.is_set() and self._link_is_current(link):
                await self._press("auto_flat", app.DEMO_PRESS_MS, still_admitted=still_admitted)
        finally:
            self._demo_cancel = None
