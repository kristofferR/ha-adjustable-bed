"""Complete direct BLE profile for com.okin.adjustamattress 1.6.0 (row067)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ..app_session import app_session
from ..const import CONF_BLE_DEVICE_NAME
from ..detection import is_mac_like_name
from .adjustamattress_protocol import (
    BASE_ACTIONS,
    CYCLIC,
    DEDICATED,
    LAYOUT_ACTIONS,
    LAYOUTS,
    LIFTS,
    MODELS,
    MOVEMENT,
    TIMERS,
    Model,
    State,
    dedicated_massage,
    frame,
    has_snore,
    model_from_name,
    parse,
)
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_WRITE = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_NOTIFY = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
FFE_WRITE_SERVICE = "0000ffe5-0000-1000-8000-00805f9b34fb"
FFE_NOTIFY_SERVICE = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE_WRITE = "0000ffe9-0000-1000-8000-00805f9b34fb"
FFE_NOTIFY = "0000ffe4-0000-1000-8000-00805f9b34fb"
FFF0 = "0000fff0-0000-1000-8000-00805f9b34fb"
INTERVAL_S = 0.2
NS = "adjustamattress_"
MAX_HOLD_MS = 60000  # Integration bound, also used by the card's hold service.


@dataclass
class Preferences:
    """Local app choices survive BLE controller replacement, not HA restarts."""

    alarm_hour: int = 0
    alarm_minute: int = 0
    alarm_type: int = 0
    alarm_edited: bool = False
    strength_index: int = 0
    strength_edited: bool = False
    privacy: bool = False


def _action(name: str) -> MotorCommandCallable:
    async def invoke(controller: BedController) -> None:
        await cast(AdjustaMattressController, controller).execute_action(name)

    return invoke


class AdjustaMattressController(BedController):
    """One physical receiver with explicit model/layout and serialized lifecycles."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        protocol_variant: str | None = None,
        device_name: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.model: Model
        self._automatic = protocol_variant in (None, "auto")
        if self._automatic:
            self.layout = 1  # Artifact GlobalState default, independent of model.
            stored = coordinator.entry.data.get(CONF_BLE_DEVICE_NAME)
            raw_name = device_name if not is_mac_like_name(device_name) else None
            self.model = model_from_name(raw_name or (stored if isinstance(stored, str) else None))
        else:
            parts = (protocol_variant or "").split("_L")
            if (
                len(parts) != 2
                or parts[0] not in MODELS
                or parts[1] not in tuple(map(str, range(7)))
            ):
                raise ValueError("Choose an AdjustaMattress model and layout")
            self.model = cast(Model, parts[0])
            self.layout = int(parts[1])
        self.state = State()
        self._write_char: BleakGATTCharacteristic | None = None
        self._notify_char: BleakGATTCharacteristic | None = None
        self._busy_timer: asyncio.TimerHandle | None = None
        self._subscribed = False
        self._preferences = app_session(
            coordinator.hass,
            str(coordinator.address),
            ("adjustamattress", protocol_variant or "auto"),
            Preferences,
        )

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def control_characteristic_uuid(self) -> str:
        return NUS_WRITE if self.model in ("P3", "P4") else FFE_WRITE

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": "com.okin.adjustamattress",
            "model": self.model,
            "layout": LAYOUTS[self.layout],
            "hardware_verified": False,
        }

    @property
    def position_actions(self) -> tuple[str, ...]:
        return (*BASE_ACTIONS, *LAYOUT_ACTIONS[self.layout])

    @property
    def _dedicated(self) -> bool:
        return dedicated_massage(self.model, self.layout)

    @property
    def _snore(self) -> bool:
        return has_snore(self.model, self.layout)

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("AdjustaMattress is not connected")
        self._write_char = self._notify_char = None
        # In automatic mode only, GATT fff0 refines the constructor's P1 model.
        if self._automatic and self.model not in ("P3", "P4"):
            self.model = "P2" if any(s.uuid.lower() == FFF0 for s in client.services) else "P1"
        nus = self.model in ("P3", "P4")
        for service in client.services:
            for char in service.characteristics:
                if service.uuid.lower() == (
                    NUS_SERVICE if nus else FFE_WRITE_SERVICE
                ) and char.uuid.lower() == (NUS_WRITE if nus else FFE_WRITE):
                    if "write" in char.properties:
                        self._write_char = char
                if service.uuid.lower() == (
                    NUS_SERVICE if nus else FFE_NOTIFY_SERVICE
                ) and char.uuid.lower() == (NUS_NOTIFY if nus else FFE_NOTIFY):
                    if "notify" in char.properties or "indicate" in char.properties:
                        self._notify_char = char
        if self._write_char is None or self._notify_char is None:
            raise ConnectionError(
                "AdjustaMattress requires its exact writable and notifying GATT roles"
            )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 200,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if self._write_char is None:
            raise ConnectionError("AdjustaMattress write role is unresolved")
        await self._write_gatt_with_retry(
            self._write_char.uuid,
            command,
            repeat_count,
            repeat_delay_ms,
            cancel_event=cancel_event,
            response=True,
            characteristic=self._write_char,
            wall_clock_pacing=True,
        )

    async def _send(self, action: str, *, cleanup: bool = False) -> None:
        packet = frame(self.model, action, now=dt_util.now(), sleeping=self.state.sleeping)
        if packet is not None:
            await self.write_command(packet, cancel_event=asyncio.Event() if cleanup else None)

    async def _send_delayed(self, action: str) -> None:
        packet = frame(self.model, action, now=dt_util.now())
        await self._delay(INTERVAL_S)
        if packet is not None:
            await self.write_command(packet)

    async def _delay(self, seconds: float, *, cleanup: bool = False) -> None:
        if cleanup:
            await asyncio.sleep(seconds)
            return
        try:
            async with asyncio.timeout(seconds):
                await self._coordinator.cancel_command.wait()
        except TimeoutError:
            pass

    async def _at(self, started: float, offset: float, *, cleanup: bool = False) -> None:
        await self._delay(
            max(0, started + offset - asyncio.get_running_loop().time()), cleanup=cleanup
        )

    async def _release(self, *, massage: bool = False) -> None:
        async def finish() -> None:
            started = asyncio.get_running_loop().time()
            await self._at(started, 0.2, cleanup=True)
            await self._send("stop", cleanup=True)
            if massage and self.model in ("P3", "P4"):
                await self._at(started, 0.4, cleanup=True)
                await self._send("queryMassage", cleanup=True)
                await self._at(started, 0.6, cleanup=True)
                await self._send("queryMassage", cleanup=True)

        # Cancellation cannot hand the command lock to another operation before STOP.
        task = asyncio.create_task(finish())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    @property
    def held_control_options(self) -> tuple[str, ...]:
        position = tuple(
            a for a in self.position_actions if not (self.model == "P2" and a == "underbedLighting")
        )
        return (*position, *(TIMERS if self._dedicated else CYCLIC))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError(f"This model/layout does not expose {control}")
        if not 1 <= duration_ms <= MAX_HOLD_MS:
            raise ValueError("Hold duration must be 1 through 60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        packet = frame(self.model, control)
        if packet is None:
            raise ValueError(f"No safe command for {control}")
        delayed = control in MOVEMENT or control in LIFTS
        loop = asyncio.get_running_loop()
        started = loop.time()
        deadline = started + duration_ms / 1000
        next_write = started + (INTERVAL_S if delayed else 0)
        try:
            while not self._coordinator.cancel_command.is_set():
                await self._delay(max(0, min(next_write, deadline) - loop.time()))
                if self._coordinator.cancel_command.is_set() or loop.time() >= deadline:
                    break
                await self.write_command(packet)
                # Awaited GATT latency must not extend the 200 ms refresh cadence.
                next_write = max(next_write + INTERVAL_S, loop.time())
        finally:
            await self._release(massage=control in CYCLIC)

    async def execute_action(self, action: str) -> None:
        if action in self.held_control_options:
            await self.hold_control(
                action,
                max(
                    200,
                    min(
                        30000,
                        self._coordinator.motor_pulse_count * 200
                        + (200 if action in MOVEMENT or action in LIFTS else 0),
                    ),
                ),
            )
        elif action in DEDICATED and self._dedicated:
            await self._send(action)
        elif action == "sync_clock" and self.model != "P2":
            await self._send_delayed("setCurrentTime")
        elif action == "query_alarm":
            await self._send_delayed("queryAlarm")
        elif action == "query_massage" and self.model != "P2":
            started = asyncio.get_running_loop().time()
            await self._send("queryMassage")
            await self._at(started, INTERVAL_S)
            await self._send("queryMassage")
        elif action == "query_massage_once" and self.model in ("P3", "P4"):
            await self._send("queryMassageOnce")
        elif action == "query_status" and self._snore:
            await self._send("queryControlBoxStatus")
        elif action == "demonstration" and self._snore:
            if self.state.snore_enabled:
                raise ValueError("Turn off intelligent anti-snore before demonstrating it")
            self.state.demonstration = True
            await self._send_snore()
        elif action == "sleep" and self._snore:
            await self._toggle_sleep()
        else:
            raise ValueError(f"This model/layout does not expose {action}")

    async def _send_snore(self) -> None:
        strength = self._preferences.strength_index
        packet = frame(
            self.model,
            "_sendAntiSnoreCommand",
            enabled=self.state.snore_enabled,
            demonstration=self.state.demonstration,
            strength_index=strength,
        )
        if packet is not None:
            await self.write_command(packet)
            if (
                not self._coordinator.cancel_command.is_set()
                and self._preferences.strength_index == strength
            ):
                self._preferences.strength_edited = False

    async def _toggle_sleep(self) -> None:
        started = asyncio.get_running_loop().time()
        start = not self.state.sleeping
        prelude = start and not self.state.snore_enabled
        if prelude:
            self.state.snore_enabled = True
            self.state.strength_index = self._preferences.strength_index = 1
            self._preferences.strength_edited = False
            await self._send_snore()  # Auto-enable preserves demonstration.
            await self._at(started, INTERVAL_S)
        await self._send("toggleSleeping")
        await self._at(started, 0.5)
        await self._send("queryControlBoxStatus")

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        client, char = self.client, self._notify_char
        if self._subscribed:
            return
        if client is None or char is None:
            raise ConnectionError("AdjustaMattress notify role is unresolved")
        try:
            async with self._ble_lock:
                await client.start_notify(char, self._notification)
        except BleakError:
            if self.model in ("P3", "P4"):
                raise
            await self._delay(1.0)
            async with self._ble_lock:
                await client.start_notify(char, self._notification)
        self._subscribed = True
        # No movement or hidden control action at setup, only the app's time/alarm hydration.
        if self.model != "P2":
            await self._send_delayed("setCurrentTime")
        await self._send_delayed("queryAlarm")
        self._publish_drafts()

    async def stop_notify(self) -> None:
        subscribed, self._subscribed = self._subscribed, False
        self._notify_callback = None
        if self._busy_timer is not None:
            self._busy_timer.cancel()
            self._busy_timer = None
        if (
            subscribed
            and self.client is not None
            and self.client.is_connected
            and self._notify_char is not None
        ):
            async with self._ble_lock:
                await self.client.stop_notify(self._notify_char)

    def on_disconnect(self) -> None:
        self._subscribed = False
        if self._busy_timer is not None:
            self._busy_timer.cancel()
            self._busy_timer = None
        self._write_char = self._notify_char = None
        self.state = State()
        keys = [
            s.state_key
            for s in (
                *self.controller_state_sensor_specs,
                *self.controller_state_binary_sensor_specs,
            )
        ]
        self.forward_controller_state_updates(dict.fromkeys(keys))

    def _notification(self, _sender: object, data: bytearray) -> None:
        self.forward_raw_notification(
            NUS_NOTIFY if self.model in ("P3", "P4") else FFE_NOTIFY, bytes(data)
        )
        fields = parse(self.model, bytes(data), self.state)
        if "alarm_hour" in fields and not self._preferences.alarm_edited:
            if self.state.alarm_hour < 24 and self.state.alarm_minute < 60:
                self._preferences.alarm_hour = self.state.alarm_hour
                self._preferences.alarm_minute = self.state.alarm_minute
            if self.state.alarm_type in (0, 9, 17, 19):
                self._preferences.alarm_type = self.state.alarm_type
            self._publish_drafts()
        if "alarm_on" in fields:
            self.forward_controller_state_update(
                NS + "alarm_commit", "on" if self.state.alarm_on else "off"
            )
        if "snore_enabled" in fields:
            self.forward_controller_state_update(
                NS + "snore_control", "on" if self.state.snore_enabled else "off"
            )
        if "strength_index" in fields and not self._preferences.strength_edited:
            self._preferences.strength_index = self.state.strength_index
            self.forward_controller_state_update(
                NS + "strength_setting", str(self._preferences.strength_index)
            )
        self.forward_controller_state_updates(
            {NS + key: getattr(self.state, key) for key in fields}
        )
        if "busy" in fields:
            if self._busy_timer is not None:
                self._busy_timer.cancel()
            self._busy_timer = asyncio.get_running_loop().call_later(0.3, self._clear_busy)

    def _clear_busy(self) -> None:
        self._busy_timer = None
        self.state.busy = False
        self.forward_controller_state_update(NS + "busy", False)

    # Settings are local drafts until the explicit alarm commit control is used.
    def _publish_drafts(self) -> None:
        self.forward_controller_state_updates(
            {
                NS + "alarm_draft_hour": self._preferences.alarm_hour,
                NS + "alarm_draft_minute": self._preferences.alarm_minute,
                NS + "alarm_draft_type": str(self._preferences.alarm_type),
                NS + "privacy": "accepted" if self._preferences.privacy else "not_accepted",
                NS + "strength_setting": str(self._preferences.strength_index),
            }
        )

    def _live_local_setting(self, key: str, option: str) -> None:
        # Local select entities outlive the BLE controller that created their specs.
        target = self._coordinator.controller or self._coordinator.capability_controller or self
        if (
            not isinstance(target, AdjustaMattressController)
            or target._preferences is not self._preferences
        ):
            raise ValueError("The selected AdjustaMattress profile has changed")
        target.local_setting(key, option)

    def local_setting(self, key: str, option: str) -> None:
        if key == "privacy" and option in ("accepted", "not_accepted") and self._snore:
            self._preferences.privacy = option == "accepted"
            self._coordinator.save_app_state(self)
        elif key == "strength_setting" and option in ("0", "1", "2") and self._snore:
            self._preferences.strength_index = int(option)
            self._preferences.strength_edited = True
        elif key == "alarm_draft_type" and option in ("0", "9", "17", "19"):
            if self.state.alarm_on:
                raise ValueError("Turn off the alarm before editing it")
            self._preferences.alarm_type = int(option)
            self._preferences.alarm_edited = True
        else:
            raise ValueError(f"Unsupported local setting {key}={option}")
        self._publish_drafts()

    async def set_number(self, key: str, value: float) -> None:
        high = 23 if key == "alarm_draft_hour" else 59 if key == "alarm_draft_minute" else -1
        if not float(value).is_integer() or not 0 <= value <= high or self.state.alarm_on:
            raise ValueError("Turn off the alarm and choose a valid integer time")
        self._preferences.alarm_edited = True
        if key == "alarm_draft_hour":
            self._preferences.alarm_hour = int(value)
        else:
            self._preferences.alarm_minute = int(value)
        self._publish_drafts()

    async def set_setting(self, key: str, option: str) -> None:
        if key == "alarm_commit" and option in ("on", "off"):
            on = option == "on"
            draft = hour, minute, kind = (
                self._preferences.alarm_hour,
                self._preferences.alarm_minute,
                self._preferences.alarm_type,
            )
            repeat = 255 if on else 0
            if not on and self.model == "P2":
                hour = minute = kind = repeat = 255
            packet = frame(
                self.model,
                "setAlarm",
                now=dt_util.now(),
                hour=hour,
                minute=minute,
                alarm_type=kind,
                repeat=repeat,
            )
            if packet is None:
                raise ValueError("No alarm command")
            started = asyncio.get_running_loop().time()
            await self._at(started, INTERVAL_S)
            await self.write_command(packet)
            if not self._coordinator.cancel_command.is_set() and draft == (
                self._preferences.alarm_hour,
                self._preferences.alarm_minute,
                self._preferences.alarm_type,
            ):
                self._preferences.alarm_edited = False
            await self._at(started, 0.4)  # Query builder at +400 ms, submission +600 ms.
            await self._send_delayed("queryAlarm")
        elif key == "snore_control" and self._snore and option in ("on", "off"):
            if option == "on" and not self._preferences.privacy:
                raise ValueError("Accept the anti-snore privacy notice before enabling it")
            self.state.snore_enabled = option == "on"
            if self.state.snore_enabled:
                self.state.demonstration = False
            await self._send_snore()
        else:
            self.local_setting(key, option)

    @property
    def persisted_app_state_key(self) -> str:
        return "com.okin.adjustamattress"

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {"privacy": self._preferences.privacy}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        privacy = state.get("privacy", False)
        if not isinstance(privacy, bool):
            raise ValueError("Invalid AdjustaMattress privacy preference")
        self._preferences.privacy = privacy

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        axes = {
            "back": ("headUp", "headDown"),
            "legs": ("footUp", "footDown"),
            "back_legs": ("unionUp", "unionDown"),
            "neck": ("neckTiltUp", "neckTiltDown"),
            "lumbar": ("lumbarUp", "lumbarDown"),
            "adjustamattress_lift": ("liftUp", "liftDown"),
        }
        return tuple(
            MotorControlSpec(
                key,
                key,
                _action(up),
                _action(down),
                lambda ctrl: ctrl.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(up, down, 0, 0),
            )
            for key, (up, down) in axes.items()
            if up in self.position_actions
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        actions = {"sync_clock": "Synchronize clock", "query_alarm": "Refresh alarm"}
        if self.model == "P2":
            actions.pop("sync_clock")
        else:
            actions["query_massage"] = "Refresh massage"
        if self.model in ("P3", "P4"):
            actions["query_massage_once"] = "Query massage once"
        if self._dedicated:
            actions.update(
                {a: f"Massage timer {10 * (i + 1)} minutes" for i, a in enumerate(TIMERS)}
            )
        else:
            actions.update(
                zip(
                    CYCLIC,
                    ("Head massage step", "Foot massage step", "Wave step", "Massage timer step"),
                    strict=True,
                )
            )
        if "m1" in self.position_actions:
            actions["m1"] = "M1"
        if "underbedLighting" in self.held_control_options:
            actions["underbedLighting"] = "Underbed lighting"
        if self.layout == 6:
            actions.update(liftHead="Lift head", liftFoot="Lift foot")
        if self._snore:
            actions.update(
                sleep="Sleep",
                demonstration="Demonstrate anti-snore",
                query_status="Refresh anti-snore status",
            )
        return tuple(
            ControllerButtonSpec(
                NS + key,
                label,
                _action(key),
                translation_key=NS + key,
                scheduler_resource="*",
                hold=ControllerHoldSpec(key, 0, 0) if key in self.held_control_options else None,
            )
            for key, label in actions.items()
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        definitions = [
            ("alarm_draft_type", ("0", "9", "17", "19"), True),
            ("alarm_commit", ("off", "on"), False),
        ]
        if self._snore:
            definitions += [
                ("privacy", ("not_accepted", "accepted"), True),
                ("strength_setting", ("0", "1", "2"), True),
                ("snore_control", ("off", "on"), False),
            ]
        if self._dedicated:
            definitions += [
                (zone + "_selector", ("0", "1", "2", "3"), False)
                for zone in ("head", "foot", "wave")
            ]
        specs = []
        for key, options, local in definitions:

            async def select(ctrl: BedController, option: str, key: str = key) -> None:
                target = cast(AdjustaMattressController, ctrl)
                if key.endswith("_selector"):
                    if not target._dedicated or option not in ("0", "1", "2", "3"):
                        raise ValueError("Dedicated massage selector is unavailable")
                    actions = tuple(
                        a
                        for a in DEDICATED
                        if a.startswith(key.split("_")[0])
                        or (key == "wave_selector" and a == "WaveOne")
                    )
                    await target.execute_action(actions[int(option)])
                    target.forward_controller_state_update(NS + key, option)
                else:
                    await target.set_setting(key, option)

            specs.append(
                ControllerSelectSpec(
                    NS + key,
                    NS + key,
                    NS + key,
                    options,
                    select,
                    local_select_fn=(lambda option, key=key: self._live_local_setting(key, option))
                    if local
                    else None,
                )
            )
        return tuple(specs)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs = []
        for key, high in (("alarm_draft_hour", 23), ("alarm_draft_minute", 59)):

            async def set_value(ctrl: BedController, value: float, key: str = key) -> None:
                await cast(AdjustaMattressController, ctrl).set_number(key, value)

            specs.append(ControllerNumberSpec(NS + key, NS + key, NS + key, 0, high, 1, set_value))
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        fields = ["alarm_hour", "alarm_minute", "alarm_type", "alarm_repeat"]
        if self.model != "P2":
            fields += ["massage_time", "head_intensity", "foot_intensity", "wave"]
        if self.model == "P4":
            fields += ["sensitivity", "strength_index"]
        return tuple(
            ControllerStateSensorSpec(
                NS + key,
                NS + key,
                NS + key,
                "mdi:information-outline",
                native_unit_of_measurement="min" if key == "massage_time" else None,
            )
            for key in fields
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        fields = ["alarm_on"]
        if self.model == "P4":
            fields += [
                "sleeping",
                "snore_enabled",
                "demonstration",
                "auxiliary_status_bit_1",
                "busy",
            ]
        return tuple(
            ControllerStateBinarySensorSpec(NS + key, NS + key, NS + key, "mdi:information-outline")
            for key in fields
        )

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 200

    async def move_head_up(self) -> None:
        await self.execute_action("headUp")

    async def move_head_down(self) -> None:
        await self.execute_action("headDown")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.execute_action("footUp")

    async def move_feet_down(self) -> None:
        await self.execute_action("footDown")

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        await self._release()

    async def preset_flat(self) -> None:
        await self.execute_action("flatPosition")

    async def preset_zero_g(self) -> None:
        await self.execute_action("zeroGravity")

    async def preset_tv(self) -> None:
        await self.execute_action("tv")

    async def preset_lounge(self) -> None:
        await self.execute_action("lounge")

    async def preset_anti_snore(self) -> None:
        await self.execute_action("anti")

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in self.position_actions

    @property
    def supports_preset_lounge(self) -> bool:
        return "lounge" in self.position_actions

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "anti" in self.position_actions

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num != 1 or self.layout != 0:
            raise ValueError("Only the app's L0 M1 recall exists")
        await self.execute_action("m1")

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("The app defines no memory programming action")
