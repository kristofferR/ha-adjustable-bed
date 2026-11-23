"""Snore Monitor's BED profile over the shared GATT writer and scheduler.

Its session owns every notification and release. Separate sensing/history,
network, audio and app presentation do not enter the BED state machine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypedDict

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

from ...alarm import AlarmError
from ...card import CARD_MASSAGE, CARD_MASSAGE_TIMER
from ...codec import onlysnore as codec
from ...command_scheduler import current_command_context
from ...const import CONF_PRODUCT_TYPE
from ...profiles import onlysnore as app
from ..base import BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..catalog_buttons import EXTRA_KEY, save_button, save_name
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
    PositionNumberSpec,
)
from ..lifecycle import CapabilitySnapshotPolicy, ControllerSession
from . import state_keys as keys

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


class AlarmArguments(TypedDict):
    slot: int
    enabled: bool
    hour: int
    minute: int
    week: int
    type_index: int
    soft: bool


class OnlySnoreController(ProfileExecution[app.OnlySnoreProfile], BedController):
    """One physical BED receiver, without packet-level side addressing."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, model: str = "unKnow", alarm_count: int = 1
    ) -> None:
        super().__init__(coordinator)
        if model not in app.MODELS:
            raise ValueError("Choose a supported Snore Monitor BED model")
        self.profile = app.PROFILE
        self.model = model
        self._alarm_count = alarm_count if alarm_count in (1, 3) else 1
        self._generation = 0
        self._notify: BleakGATTCharacteristic | None = None
        self._status: codec.Status | None = None
        self._alarms: dict[int, codec.Alarm] = {}

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.WRITE

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    def _role(self, uuid: str) -> BleakGATTCharacteristic:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Snore Monitor is disconnected")
        for service in client.services:
            if service.uuid.lower() == codec.SERVICE:
                char = service.get_characteristic(uuid)
                if char is not None:
                    return char
        raise ConnectionError(f"Snore Monitor requires {uuid} in its BED service")

    def _check_session(self, generation: int, client: object) -> None:
        if (
            generation != self._generation
            or client is not self.client
            or self.client is None
            or not self.client.is_connected
            or self._coordinator.controller is not self
        ):
            raise ConnectionError("Snore Monitor BED session ended")

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 150,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        generation, client = self._generation, self.client
        char = self._role(codec.WRITE)
        if "write-without-response" not in char.properties:
            raise ConnectionError("Snore Monitor requires writes without response")
        await self._write_gatt_with_retry(
            codec.WRITE,
            command,
            repeat_count,
            repeat_delay_ms,
            cancel_event,
            response=False,
            characteristic=char,
            expected_client=client,
            before_write=lambda: self._check_session(generation, client),
        )
        self._check_session(generation, client)

    async def _wait(self, ms: int) -> bool:
        try:
            async with asyncio.timeout(ms / 1000):
                await self._coordinator.cancel_command.wait()
        except TimeoutError:
            return False
        return True

    async def _release(
        self, frame: bytes, generation: int, client: object, *, delay_ms: int | None = None
    ) -> None:
        async def cleanup() -> None:
            await asyncio.sleep((self.profile.release_ms if delay_ms is None else delay_ms) / 1000)
            if generation == self._generation and self.client is client and client is not None:
                if self.client is not None and self.client.is_connected:
                    await self.write_command(frame, cancel_event=asyncio.Event())
                    context = current_command_context()
                    if context is not None and frame[:2] == b"\x05\x02":
                        context.cleanup_stop_sent = True

        task = asyncio.create_task(cleanup())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _hold(
        self,
        action: str,
        duration_ms: int | None = None,
        *,
        save: bool = False,
        allow_program: bool = False,
    ) -> None:
        if action not in app.KEYS or action == "stop":
            raise ValueError("Unknown BED control")
        generation, client = self._generation, self.client
        interval = self.profile.refresh_ms
        leased = self.leased_hold_refreshes(interval)
        duration = (
            duration_ms
            if duration_ms is not None
            else self._coordinator.motor_pulse_count * interval
        ) / 1000
        loop = asyncio.get_running_loop()
        start = loop.time()
        deadline = None if leased is not None else start + duration
        remaining = leased
        saved = save

        async def stream() -> None:
            nonlocal saved, remaining
            while not self._coordinator.cancel_command.is_set():
                self._check_session(generation, client)
                now = loop.time()
                if deadline is not None and now >= deadline:
                    break
                if remaining is not None:
                    if remaining <= 0:
                        break
                    remaining -= 1
                saved = save or (
                    allow_program
                    and action in app.PRESETS
                    and now - start >= self.profile.save_ms / 1000
                )
                await self.write_command(codec.control(app.KEYS[action], save=saved))
                # No latency catch-up: every refresh starts a new interval.
                delay = interval / 1000
                if deadline is not None:
                    delay = min(delay, max(0, deadline - loop.time()))
                if await self._wait(round(delay * 1000)):
                    break

        timeout = asyncio.timeout_at(deadline)
        try:
            try:
                async with timeout:
                    await stream()
            except TimeoutError:
                if not timeout.expired():
                    raise
        finally:
            await self._release(codec.control(0, save=saved), generation, client)

    async def move_axis(self, axis: str, up: bool) -> None:
        if axis not in app.AXES:
            raise ValueError("Unknown BED actuator")
        await self._hold(f"{app.AXES[axis]}_{'up' if up else 'down'}")

    async def move_head_up(self) -> None:
        await self.move_axis("head", True)

    async def move_head_down(self) -> None:
        await self.move_axis("head", False)

    async def move_back_up(self) -> None:
        await self.move_axis("back", True)

    async def move_back_down(self) -> None:
        await self.move_axis("back", False)

    async def move_legs_up(self) -> None:
        await self.move_axis("legs", True)

    async def move_legs_down(self) -> None:
        await self.move_axis("legs", False)

    async def move_lumbar_up(self) -> None:
        await self.move_axis("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self.move_axis("lumbar", False)

    async def stop_all(self) -> None:
        context = current_command_context()
        if context is not None and context.cleanup_stop_sent:
            return
        await self._release(codec.control(0), self._generation, self.client)

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all
    move_lumbar_stop = stop_all
    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                f"smart_sleep_{label}",
                lambda ctrl, axis=axis: require_controller(ctrl, OnlySnoreController).move_axis(
                    axis, True
                ),
                lambda ctrl, axis=axis: require_controller(ctrl, OnlySnoreController).move_axis(
                    axis, False
                ),
                lambda ctrl: ctrl.stop_all(),
                hold=ControllerMotorHoldSpec(f"{axis}_up", f"{axis}_down", press_hold_ms=None),
            )
            for axis, label in app.AXES.items()
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            *tuple(f"{axis}_{direction}" for axis in app.AXES for direction in ("up", "down")),
            *tuple(f"preset_{name}" for name in ("flat", *app.PRESETS)),
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 30000
        ):
            raise ValueError("Choose a control this bed offers and a duration of up to 30 seconds")

    def validate_timed_movement(self, motor: str, direction: str, duration_ms: int) -> None:
        self.validate_hold_control(f"{motor}_{direction}", duration_ms)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if control.startswith("preset_"):
            action = control.removeprefix("preset_")
        else:
            axis, direction = control.rsplit("_", 1)
            action = f"{app.AXES[axis]}_{direction}"
        await self._hold(action, duration_ms, allow_program=control.startswith("preset_"))

    async def preset_flat(self) -> None:
        await self._hold("flat")

    async def preset_zero_g(self) -> None:
        await self._hold("zero_gravity")

    async def preset_anti_snore(self) -> None:
        await self._hold("anti_snore_preset")

    async def preset_tv(self) -> None:
        await self._hold("tv")

    async def preset_reading(self) -> None:
        await self._hold("reading")

    preset_lounge = preset_reading

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._hold(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.save(f"memory_{memory_num}")

    async def save(self, action: str) -> None:
        if action not in app.PRESETS:
            raise ValueError("Only six non-flat BED presets can be saved")
        await self._hold(action, self.profile.refresh_ms, save=True)

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_reading(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        # Holding a programmable preset past the save threshold saves it.
        control = {
            "preset_flat": "preset_flat",
            "preset_zero_g": "preset_zero_gravity",
            "preset_tv": "preset_tv",
            "preset_reading": "preset_reading",
            "preset_anti_snore": "preset_anti_snore_preset",
        }.get(key, key if key.startswith("preset_memory_") else None)
        return None if control is None else ControllerHoldSpec(control)

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    async def lights_toggle(self) -> None:
        await self.utility("light")

    async def lights_on(self) -> None:
        raise NotImplementedError("Only a light action is proven")

    async def lights_off(self) -> None:
        raise NotImplementedError("Only a light action is proven")

    async def massage_toggle(self) -> None:
        if self._status is None:
            raise ValueError("Refresh BED state before toggling massage")
        await self.utility(
            "massage_stop_all" if self._status.massage_timer_index else "massage_all"
        )

    async def massage_mode_step(self) -> None:
        await self.utility("massage_wave_next")

    async def utility(self, action: str) -> None:
        if action not in ("light", *tuple(key for key in app.KEYS if key.startswith("massage_"))):
            raise ValueError("Unknown BED utility")
        generation, client = self._generation, self.client
        try:
            await self.write_command(
                codec.control(app.KEYS[action]),
                2 if action in ("massage_all", "massage_stop_all") else 1,
                0,
            )
        finally:
            await self._release(codec.control(0), generation, client)
        if action.startswith("massage_") and not await self._wait(200):
            self._check_session(generation, client)
            await self.write_command(codec.query(176))
            if action in ("massage_all", "massage_stop_all") and not await self._wait(50):
                self._check_session(generation, client)
                await self.write_command(codec.query(176))

    async def select_setting(self, name: str, option: str) -> None:
        generation, client = self._generation, self.client
        if name in ("privacy", "detection") and option in ("off", "on"):
            await self.write_command(
                codec.setting(178 if name == "privacy" else 181, int(option == "on")),
                1 if name == "privacy" else 2,
                100,
            )
        elif name == "intervention" and option in ("off", "1", "3", "6"):
            await self.write_command(
                codec.intervention(int(option != "off"), 0 if option == "off" else int(option))
            )
        else:
            raise ValueError("Choose a proven BED setting")
        if not await self._wait(300):
            self._check_session(generation, client)
            await self.write_command(codec.query(176))

    async def demo(self, duration_ms: int = 1000, level: int = 1) -> None:
        if not 1 <= duration_ms <= 30000 or level not in app.INTERVENTION_LEVELS:
            raise ValueError("Choose a proven demo level and a duration up to 30 seconds")
        generation, client = self._generation, self.client
        deadline = asyncio.get_running_loop().time() + duration_ms / 1000
        timeout = asyncio.timeout_at(deadline)
        try:
            try:
                async with timeout:
                    await self.write_command(codec.intervention(2, level))
                    remaining_ms = max(
                        0, round((deadline - asyncio.get_running_loop().time()) * 1000)
                    )
                    if remaining_ms:
                        await self._wait(remaining_ms)
            except TimeoutError:
                if not timeout.expired():
                    raise
        finally:
            await self._release(codec.INTERVENTION_STOP, generation, client, delay_ms=0)

    @property
    def supports_massage_toggle_control(self) -> bool:
        return False  # the Massage switch starts and stops it

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        # Recall buttons are the standard presets; wave cycling is the standard
        # massage mode step; start/stop is the Massage switch.
        saves = tuple(
            save_button(
                f"onlysnore_save_{name}",
                save_name(name),
                lambda ctrl, name=name: require_controller(ctrl, OnlySnoreController).save(name),
            )
            for name in app.PRESETS
            if not name.startswith("memory_")
        )
        utilities = tuple(
            ControllerButtonSpec(
                f"onlysnore_{name}",
                name.replace("_", " ").title(),
                lambda ctrl, name=name: require_controller(ctrl, OnlySnoreController).utility(name),
                translation_key=f"onlysnore_{name}",
                card=CARD_MASSAGE_TIMER if name == "massage_timer_next" else CARD_MASSAGE,
            )
            for name in (
                "massage_timer_next",
                "massage_foot_strength_next",
                "massage_head_strength_next",
            )
        )
        return (
            *saves,
            *utilities,
            ControllerButtonSpec(
                "onlysnore_refresh",
                "Refresh status",
                lambda ctrl: require_controller(ctrl, OnlySnoreController).refresh_all(),
                translation_key="onlysnore_refresh",
                cancel_movement=False,
                diagnostic=True,
            ),
            # Trying an intervention level is there to enable, not for the dashboard.
            *(
                ControllerButtonSpec(
                    f"onlysnore_demo_{level}",
                    f"Test anti-snore level {level}",
                    lambda ctrl, level=level: require_controller(ctrl, OnlySnoreController).demo(
                        level=level
                    ),
                    translation_key=EXTRA_KEY,
                    translation_placeholders={"action": f"Test anti-snore level {level}"},
                    entity_registry_enabled_default=False,
                )
                for level in app.INTERVENTION_LEVELS
            ),
            ControllerButtonSpec(
                "onlysnore_stop_intervention",
                "Stop anti-snore intervention",
                lambda ctrl: ctrl.write_command(codec.INTERVENTION_STOP),
                translation_key=EXTRA_KEY,
                translation_placeholders={"action": "Stop anti-snore intervention"},
                entity_registry_enabled_default=False,
            ),
        )

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        def setting(name: str):
            async def set_value(ctrl: BedController, on: bool) -> None:
                await require_controller(ctrl, OnlySnoreController).select_setting(
                    name, "on" if on else "off"
                )

            return set_value

        async def massage(ctrl: BedController, on: bool) -> None:
            await require_controller(ctrl, OnlySnoreController).utility(
                "massage_all" if on else "massage_stop_all"
            )

        return (
            ControllerSwitchSpec(
                "onlysnore_massage",
                "onlysnore_massage",
                massage,
                keys.MASSAGE,
                icon="mdi:vibrate",
                # Status is only known when queried, so on and off stay separate.
                assumed_state=True,
                card=CARD_MASSAGE,
            ),
            ControllerSwitchSpec(
                "onlysnore_privacy",
                "onlysnore_privacy",
                setting("privacy"),
                keys.PRIVACY,
                "on",
                "mdi:shield-lock-outline",
                entity_category=EntityCategory.CONFIG,
            ),
            ControllerSwitchSpec(
                "onlysnore_detection",
                "onlysnore_detection",
                setting("detection"),
                keys.DETECTION,
                "on",
            ),
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return (
            ControllerSelectSpec(
                "onlysnore_intervention",
                "onlysnore_intervention",
                keys.INTERVENTION,
                ("off", "1", "3", "6"),
                lambda ctrl, option: require_controller(ctrl, OnlySnoreController).select_setting(
                    "intervention", option
                ),
            ),
        )

    def alarm_frame(
        self,
        slot: int,
        enabled: bool,
        hour: int,
        minute: int,
        week: int,
        type_index: int,
        soft: bool,
        *,
        now: datetime | None = None,
        weekday_now: datetime | None = None,
    ) -> bytes:
        name = self._coordinator.name
        if slot not in range(1, self._alarm_count + 1):
            raise AlarmError(
                "alarm_value_out_of_range",
                f"{name} accepts slot 1 to {self._alarm_count}",
                device_name=name,
                option="slot",
                min=1,
                max=self._alarm_count,
            )
        if (
            not 0 <= hour <= 23
            or not 0 <= minute <= 59
            or not 0 <= week <= 255
            or type_index not in range(5)
        ):
            raise ValueError("Invalid BED alarm fields")
        if soft and self._alarm_count != 3:
            raise AlarmError(
                "alarm_option_not_supported",
                f"{name} has no soft wake with a single alarm",
                device_name=name,
                option="soft_wake",
            )
        model = codec.AlarmModel(week, hour, minute, type_index, slot - 1, int(enabled), int(soft))
        now = now or dt_util.now()
        if self._alarm_count == 3:
            return codec.set_triple(model, now, weekday_now or dt_util.now())[0]
        return codec.open_single(model, now)[0] if enabled else codec.CLOSE_SINGLE

    async def set_alarm(
        self,
        slot: int,
        enabled: bool,
        hour: int,
        minute: int,
        week: int,
        type_index: int,
        soft: bool,
    ) -> None:
        frame = self.alarm_frame(slot, enabled, hour, minute, week, type_index, soft)
        generation, client = self._generation, self.client
        await self.write_command(frame)
        if not await self._wait(300):
            self._check_session(generation, client)
            await self.write_command(codec.query(192 + (slot - 1) * 16))

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def sync_clock(self) -> None:
        await self.write_command(codec.clock(dt_util.now()))

    async def refresh_all(self) -> None:
        generation, client = self._generation, self.client
        await self.write_command(codec.query(160))
        if await self._wait(300):
            return
        self._check_session(generation, client)
        await self.write_command(codec.query(176))
        for slot in range(self._alarm_count):
            if await self._wait(200):
                return
            self._check_session(generation, client)
            await self.write_command(codec.query(192 + slot * 16))

    async def async_on_connect(self, session: ControllerSession) -> None:
        client = self.client
        if client is None:
            raise ConnectionError("Snore Monitor is disconnected")
        await self.start_notify()
        generation = self._generation
        for uuid, key in ((codec.FIRMWARE, keys.FIRMWARE), (codec.HARDWARE, keys.HARDWARE)):
            char = next(
                (
                    char
                    for service in client.services
                    if service.uuid.lower() == "0000180a-0000-1000-8000-00805f9b34fb"
                    if (char := service.get_characteristic(uuid)) is not None
                ),
                None,
            )
            if char is not None and "read" in char.properties:
                value = (
                    bytes(await client.read_gatt_char(char))
                    .decode("utf-8", errors="replace")
                    .rstrip("\0")
                )
                self._check_session(generation, client)
                self.forward_controller_state_updates(key(value))
        for delay, opcode in ((100, None), (300, 176), (100, 160)):
            if await self._wait(delay):
                return
            self._check_session(generation, client)
            if not session.is_current():
                return
            await self.write_command(
                codec.clock(dt_util.now()) if opcode is None else codec.query(opcode)
            )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._notify is not None:
            return
        client = self.client
        if client is None:
            raise ConnectionError("Snore Monitor is disconnected")
        char = self._role(codec.NOTIFY)
        if not {"notify", "indicate"}.intersection(char.properties):
            raise ConnectionError("Snore Monitor requires notifications")
        self._generation += 1
        generation = self._generation
        self._notify = char
        try:
            await client.start_notify(
                char, lambda sender, data: self._notification(sender, data, generation, client)
            )
            self._check_session(generation, client)
        except BaseException:
            self.on_disconnect()
            raise

    def _notification(
        self, sender: BleakGATTCharacteristic, data: bytearray, generation: int, client: object
    ) -> None:
        if (
            generation != self._generation
            or self.client is not client
            or self.client is None
            or not self.client.is_connected
            or self._coordinator.controller is not self
            or self._notify is None
            or sender.handle != self._notify.handle
        ):
            return
        raw = bytes(data)
        self.forward_raw_notification(codec.NOTIFY, raw)
        parsed = codec.parse(raw)
        if isinstance(parsed, codec.Status):
            self._status = parsed
            self.forward_controller_state_updates(
                keys.PRIVACY("on" if parsed.privacy else "off"),
                keys.DETECTION("on" if parsed.snore_detection else "off"),
                keys.INTERVENTION(
                    str(parsed.anti_snore_level) if parsed.anti_snore_enabled else "off"
                ),
                keys.MASSAGE(parsed.massage_timer_index != 0),
            )
        elif isinstance(parsed, codec.Alarm):
            if parsed.index >= self._alarm_count:
                return
            self._alarms[parsed.index] = parsed
            i = parsed.index
            self.forward_controller_state_updates(
                keys.ALARM_TIME[i](f"{parsed.hour:02}:{parsed.minute:02}"),
                keys.ALARM_WEEK[i](parsed.week),
                keys.ALARM_ACTION[i](parsed.action_code),
                keys.ALARM_OPEN[i](parsed.opened == 1),
            )
            if parsed.soft is not None and (self._alarm_count == 3 or raw[2] >= 16):
                self.forward_controller_state_updates(keys.ALARM_SOFT[i](parsed.soft == 1))
        elif type(parsed) is int:
            self._alarm_count = parsed
            for index in range(parsed, 3):
                self._alarms.pop(index, None)
            self.forward_controller_state_updates(
                *(key(None) for key in keys.ALARM_TIME[parsed:]),
                *(key(None) for key in keys.ALARM_WEEK[parsed:]),
                *(key(None) for key in keys.ALARM_ACTION[parsed:]),
                *(key(None) for key in keys.ALARM_OPEN[parsed:]),
                *(key(None) for key in keys.ALARM_SOFT[parsed:]),
            )
            self.forward_controller_state_updates(keys.ALARM_COUNT(parsed))

    @property
    def capability_snapshot_policy(self) -> CapabilitySnapshotPolicy:
        return CapabilitySnapshotPolicy(deferred_reload=True, after_operations=True)

    def capability_snapshot(self) -> dict[str, Any]:
        return {"alarm_count": self._alarm_count}

    def on_disconnect(self) -> None:
        self._generation += 1
        self._notify = None
        self._status = None
        self._alarms.clear()
        self.forward_controller_state_updates(
            keys.PRIVACY(None),
            keys.DETECTION(None),
            keys.INTERVENTION(None),
            keys.MASSAGE(None),
            keys.ALARM_COUNT(None),
            keys.FIRMWARE(None),
            keys.HARDWARE(None),
            *(key(None) for key in keys.ALARM_TIME),
            *(key(None) for key in keys.ALARM_WEEK),
            *(key(None) for key in keys.ALARM_ACTION),
            *(key(None) for key in keys.ALARM_OPEN),
            *(key(None) for key in keys.ALARM_SOFT),
        )

    async def stop_notify(self) -> None:
        char, client = self._notify, self.client
        self.on_disconnect()
        if char is not None and client is not None and client.is_connected:
            await client.stop_notify(char)

    async def read_positions(self, motor_count: int = 2) -> None:
        """No BED position parser; sensing bytes never become motor angles."""

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        # Whether it is on, repeat days, action and soft wake are attributes of
        # each alarm's time.
        alarms = tuple(
            ControllerStateSensorSpec(
                str(keys.ALARM_TIME[i]),
                str(keys.ALARM_TIME[i]),
                keys.ALARM_TIME[i],
                "mdi:alarm",
                attribute_keys=(
                    keys.ALARM_OPEN[i],
                    keys.ALARM_WEEK[i],
                    keys.ALARM_ACTION[i],
                    keys.ALARM_SOFT[i],
                ),
                entity_registry_enabled_default=True,
                entity_category=None,
            )
            for i in range(self._alarm_count)
        )
        return (
            *alarms,
            *(
                ControllerStateSensorSpec(
                    str(key),
                    str(key),
                    key,
                    "mdi:information-outline",
                    entity_registry_enabled_default=False,
                )
                for key in (keys.FIRMWARE, keys.HARDWARE)
            ),
        )



async def build_controller(ctx: BuildContext) -> OnlySnoreController:
    snapshot = ctx.stored_capabilities("onlysnore") or {}
    found = app.advertisement(
        ctx.advertisement_name or ctx.live_device_name or "",
        ctx.manufacturer_data or {},
        ctx.coordinator.address,
    )
    model = ctx.data.get(CONF_PRODUCT_TYPE, found or "unKnow")
    if not isinstance(model, str):
        raise ValueError("Choose a Snore Monitor BED model")
    count = snapshot.get("alarm_count", 1)
    return OnlySnoreController(ctx.coordinator, model, count if type(count) is int else 1)
