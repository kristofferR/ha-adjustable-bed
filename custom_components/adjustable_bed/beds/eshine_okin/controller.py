"""Explicit eShine E2000/E3000/E3100/E5000 app controls (row122)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ...card import CARD_MASSAGE, CARD_UTILITY
from ...controller_state import StateKey
from ...execution import ExecutionCapabilities
from ...profiles.okin_nframe import ESHINE_PROFILES, ESHINE_REFRESH_MS
from ...state_keys import UNDER_BED_LIGHTS_ON
from ..base import (
    BedController,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from ..builder import BuildContext
from .protocol import (
    ALARM_TYPES,
    COMMANDS,
    HELD,
    NOTIFY_UUID,
    SERVICE_UUID,
    WRITE_UUID,
    StateValue,
    alarm_frame,
    clock_frame,
    parse_notification,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator


@dataclass(frozen=True, slots=True)
class Session:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    address: str


def _action(action: str) -> MotorCommandCallable:
    async def invoke(controller: BedController) -> None:
        target = controller
        if not isinstance(target, EshineOkinController):
            raise TypeError("This action requires the eShine E2000/E3000/E3100/E5000 app")
        await target.execute_action(action)

    return invoke


def _group_key(group: str) -> StateKey[str | None]:
    return StateKey[str | None](f"eshine_okin_{group}")


def _group_data_key(group: str) -> StateKey[dict[str, StateValue] | None]:
    return StateKey[dict[str, StateValue] | None](f"eshine_okin_{group}_data")


class EshineOkinController(BedController):
    """App-selected capabilities with connection-bound writes and receive state."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, profile: str) -> None:
        super().__init__(coordinator)
        if profile not in ESHINE_PROFILES:
            raise ValueError("Choose E2000, E3000/E3100 or E5000 from the eShine app")
        self.profile = ESHINE_PROFILES[profile]
        self._session: Session | None = None
        self._notifying = False
        self._observed: dict[str, dict[str, StateValue]] = {}

    @property
    def execution(self) -> ExecutionCapabilities:
        """Held keys refresh until release, then STOP after the profile's delay (#483)."""
        return self.profile.execution

    @property
    def control_characteristic_uuid(self) -> str:
        return WRITE_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"app": "com.okin.eshine", "profile": self.profile.key, "hardware_verified": False}

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                _action(f"{axis}_up"),
                _action(f"{axis}_down"),
                _action("stop"),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(f"{axis}_up", f"{axis}_down"),
            )
            for axis in self.profile.axes
        )

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, ESHINE_REFRESH_MS

    @property
    def has_pillow_support(self) -> bool:
        return "pillow" in self.profile.axes

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_reading(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return False

    @property
    def memory_slot_count(self) -> int:
        return 0

    @property
    def supports_massage(self) -> bool:
        return "massage_on" in self.profile.keys

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_lights(self) -> bool:
        return self.supports_massage

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.supports_lights

    def get_light_state(self) -> dict[str, object]:
        return {"is_on": self._observed.get("massage", {}).get("light")}

    async def lights_on(self) -> None:
        await self._set_light(True)

    async def lights_off(self) -> None:
        await self._set_light(False)

    async def _set_light(self, desired: bool) -> None:
        if not self.supports_lights:
            raise ValueError("E2000 has no Night Light control")
        observed = self.get_light_state()["is_on"]
        if observed is None:
            raise ValueError(
                "Refresh light state before using turn_on or turn_off; toggle is available"
            )
        if observed != desired:
            await self.lights_toggle()

    @property
    def supports_clock_alarm(self) -> bool:
        return True

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def clock_alarm_preset_options(self) -> tuple[str, ...]:
        return tuple(k for k in ALARM_TYPES if k != "massage" or self.supports_massage)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            k
            for k in COMMANDS
            if k in HELD
            and (not k.startswith("pillow_") or self.has_pillow_support)
            and (k != "light" or self.supports_lights)
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = key.removeprefix("preset_")
        return ControllerHoldSpec(control) if control in self.held_control_options else None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        labels = {
            "flat_zero_g": "Flat + Zero Gravity",
            "query_state": "Refresh bed state",
            "query_alarm": "Refresh alarm",
            "sync_clock": "Synchronize bed clock",
        }
        if self.supports_massage:
            labels.update(
                {
                    "massage_on": "Massage on",
                    "massage_head_strength": "Head massage strength",
                    "massage_foot_strength": "Foot massage strength",
                    "massage_timer": "Massage timer",
                }
            )
        return tuple(
            ControllerButtonSpec(
                f"eshine_okin_{key}",
                name,
                _action(key),
                translation_key=f"eshine_okin_{key}",
                hold=ControllerHoldSpec(key) if key in HELD else None,
                card=CARD_MASSAGE if key.startswith("massage_") else CARD_UTILITY,
            )
            for key, name in labels.items()
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                f"eshine_okin_{group}",
                f"eshine_okin_{group}",
                _group_key(group),
                "mdi:alarm" if group == "alarm" else "mdi:vibrate",
                attribute_keys=(_group_data_key(group),),
                card=CARD_MASSAGE if group == "massage" else CARD_UTILITY,
            )
            for group in (("massage", "alarm") if self.supports_massage else ("alarm",))
        )

    def invalidate_diagnostics(self) -> None:
        self._observed.clear()
        self.forward_controller_state_updates(
            _group_key("massage")(None),
            _group_data_key("massage")(None),
            _group_key("alarm")(None),
            _group_data_key("alarm")(None),
            UNDER_BED_LIGHTS_ON(None),
        )

    def on_disconnect(self) -> None:
        self._session = None
        self._notifying = False
        self._notify_callback = None
        self.invalidate_diagnostics()

    def _live(self, expected: Session | None = None) -> Session:
        session = self._session
        if (
            session is None
            or (expected is not None and session is not expected)
            or self.client is not session.client
            or not session.client.is_connected
            or self._coordinator.address != session.address
        ):
            raise ConnectionError("The eShine BLE session changed or disconnected")
        return session

    async def async_discover_capabilities(self) -> None:
        self._session = None
        self._notifying = False
        self.invalidate_diagnostics()
        client = self.client
        if client is None:
            raise ConnectionError("eShine is not connected")
        for service in client.services:
            if service.uuid.lower() != SERVICE_UUID:
                continue
            write = next((c for c in service.characteristics if c.uuid.lower() == WRITE_UUID), None)
            notify = next(
                (c for c in service.characteristics if c.uuid.lower() == NOTIFY_UUID), None
            )
            if (
                write is not None
                and "write-without-response" in write.properties
                and notify is not None
                and {"notify", "indicate"}.intersection(notify.properties)
            ):
                self._session = Session(client, write, notify, self._coordinator.address)
                return
        raise ValueError(
            "eShine requires its exact UART write-without-response and notify/indicate roles"
        )

    @staticmethod
    async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
        if cancel.is_set():
            return True
        try:
            await asyncio.wait_for(cancel.wait(), seconds)
        except TimeoutError:
            return False
        return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = ESHINE_REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        session = self._live()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if cancel.is_set():
                return
            if index and await self._pause(repeat_delay_ms / 1000, cancel):
                return
            async with self._ble_lock:
                self._live(session)
                if cancel.is_set():
                    return
                await session.client.write_gatt_char(session.write, command, response=False)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        session = self._live()
        if self._notifying:
            return

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._session is not session
                or self.client is not session.client
                or not session.client.is_connected
                or self._coordinator.address != session.address
            ):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            result = parse_notification(bytes(data), dt_util.now())
            if result is None:
                return
            group, state = result
            self._observed[group] = state
            updates = [
                _group_key(group)("on" if state["enabled"] else "off"),
                _group_data_key(group)(dict(state)),
            ]
            if group == "massage" and self.supports_lights:
                updates.append(UNDER_BED_LIGHTS_ON(state["light"] is True))
            self.forward_controller_state_updates(*updates)

        try:
            async with self._ble_lock:
                await session.client.start_notify(session.notify, receive)
            self._notifying = True
            await self.write_command(COMMANDS["query_state"])
            if not await self._pause(0.2, self._coordinator.cancel_command):
                self._live(session)
                await self.write_command(COMMANDS["query_alarm"])
        except BaseException:
            await self.stop_notify()
            raise

    async def stop_notify(self) -> None:
        session, self._session = self._session, None
        try:
            if self._notifying and session is not None and session.client.is_connected:
                async with self._ble_lock:
                    await session.client.stop_notify(session.notify)
        finally:
            self._notifying = False
            self._notify_callback = None
            self.invalidate_diagnostics()

    async def _send_stop(self) -> None:
        await self._release(self._live())

    async def _release(self, session: Session) -> None:
        # The coordinator cancels the operation task as well as its event. Retain
        # the command lane until the original session's delayed release drains.
        release = asyncio.create_task(self._release_frame(session))
        interrupted = False
        while not release.done():
            try:
                await asyncio.shield(release)
            except asyncio.CancelledError:
                interrupted = True
        release.result()
        if interrupted:
            raise asyncio.CancelledError

    async def _release_frame(self, session: Session) -> None:
        # Preserve the app's release delay, capturing STOP and the current session.
        await self._pause(self.profile.hold.release_after_ms / 1000, asyncio.Event())
        self._live(session)
        await self.write_command(COMMANDS["stop"], cancel_event=asyncio.Event())

    async def _move_with_stop(self, command: bytes) -> None:
        session = self._live()
        try:
            count, delay = self.motor_pulse_settings()
            await self.write_command(command, repeat_count=count, repeat_delay_ms=delay)
        finally:
            await self._release(session)

    async def execute_action(self, action: str) -> None:
        if action == "sync_clock":
            await self.sync_clock()
            return
        if action not in COMMANDS:
            raise ValueError("Unknown eShine action")
        if action.startswith("massage_") and not self.supports_massage:
            raise ValueError("E2000 has no massage controls")
        if action.startswith("pillow_") and not self.has_pillow_support:
            raise ValueError("Head Tilt is only exposed by E5000")
        if action == "light" and not self.supports_lights:
            raise ValueError("E2000 has no Night Light control")
        if action == "massage_wave" and not self._observed.get("massage", {}).get("enabled"):
            raise ValueError("Refresh massage state and enable massage before changing the wave")
        session = self._live()
        if action == "stop":
            await self._send_stop()
        elif action in HELD:
            await self._move_with_stop(COMMANDS[action])
            if action == "light" and not await self._pause(0.1, self._coordinator.cancel_command):
                self._live(session)
                await self.write_command(COMMANDS["query_state"])
        else:
            session = self._live()
            await self.write_command(COMMANDS[action])
            if action.startswith("massage_"):
                if not await self._pause(0.05, self._coordinator.cancel_command):
                    self._live(session)
                    await self.write_command(COMMANDS["query_state"])

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Unsupported eShine held control")
        if type(duration_ms) is not int or not 0 < duration_ms <= 60000:
            raise ValueError("Duration must be an integer from 1 to 60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        session = self._live()
        deadline = asyncio.timeout(duration_ms / 1000)
        write_timeout = False
        try:
            try:
                async with deadline:
                    try:
                        await self.write_command(
                            COMMANDS[control],
                            repeat_count=self.timed_move_repeat_count(
                                duration_ms, ESHINE_REFRESH_MS
                            ),
                            repeat_delay_ms=ESHINE_REFRESH_MS,
                        )
                    except TimeoutError:
                        write_timeout = True
                        raise
            except TimeoutError:
                if write_timeout or not deadline.expired():
                    raise
        finally:
            await self._release(session)
        if control == "light" and not await self._pause(0.1, self._coordinator.cancel_command):
            self._live(session)
            await self.write_command(COMMANDS["query_state"])

    async def configure_clock_alarm(
        self,
        *,
        enabled: bool,
        weekdays: Sequence[int],
        hour: int,
        minute: int,
        preset: str,
        head_level: int = 0,
        foot_level: int = 0,
    ) -> None:
        if weekdays or head_level or foot_level:
            raise ValueError("eShine selects a single next-occurrence day and no massage levels")
        if enabled and (
            preset not in self.clock_alarm_preset_options
            or type(hour) is not int
            or not 0 <= hour <= 23
            or type(minute) is not int
            or not 0 <= minute <= 59
        ):
            raise ValueError("Choose an available eShine action and minute-precision alarm time")
        session = self._live()
        now = dt_util.now()
        packet = alarm_frame(now, hour, minute, preset) if enabled else COMMANDS["disable_alarm"]
        # The app alarm UI writes twice, querying before the second write.
        for _index in range(2 if enabled else 1):
            self._live(session)
            await self.write_command(packet)
            if await self._pause(0.2, self._coordinator.cancel_command):
                return
            self._live(session)
            await self.write_command(COMMANDS["query_alarm"])

    async def sync_clock(self) -> None:
        session = self._live()
        if await self._pause(0.1, self._coordinator.cancel_command):
            return
        self._live(session)
        await self.write_command(clock_frame(dt_util.now()))
        if not await self._pause(0.2, self._coordinator.cancel_command):
            self._live(session)
            await self.write_command(COMMANDS["query_alarm"])

    async def move_head_up(self) -> None:
        await self.execute_action("head_up")

    async def move_head_down(self) -> None:
        await self.execute_action("head_down")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.execute_action("feet_up")

    async def move_feet_down(self) -> None:
        await self.execute_action("feet_down")

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_pillow_up(self) -> None:
        await self.execute_action("pillow_up")

    async def move_pillow_down(self) -> None:
        await self.execute_action("pillow_down")

    async def move_pillow_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        await self.move_feet_stop()

    async def preset_flat(self) -> None:
        await self.execute_action("flat")

    async def preset_zero_g(self) -> None:
        await self.execute_action("zero_g")

    async def preset_anti_snore(self) -> None:
        await self.execute_action("anti_snore")

    async def preset_tv(self) -> None:
        await self.execute_action("tv")

    async def preset_reading(self) -> None:
        await self.execute_action("reading")

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError("eShine has named presets, not numbered memory slots")

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Use a sustained named preset; no separate save packet is proven")

    async def stop_all(self) -> None:
        await self._send_stop()

    async def lights_toggle(self) -> None:
        await self.execute_action("light")

    async def massage_off(self) -> None:
        await self.execute_action("massage_off")

    async def massage_on(self) -> None:
        await self.execute_action("massage_on")

    async def massage_toggle(self) -> None:
        state = self._observed.get("massage")
        if state is None:
            raise ValueError("Refresh massage state before toggling massage")
        await self.execute_action("massage_off" if state["enabled"] else "massage_on")

    async def massage_mode_step(self) -> None:
        await self.execute_action("massage_wave")


async def build_controller(ctx: BuildContext) -> EshineOkinController:
    """Build the controller for the selected profile."""
    return EshineOkinController(ctx.coordinator, profile=ctx.variant or "")
