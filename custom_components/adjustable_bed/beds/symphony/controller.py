"""Symphony's model gates and session over the shared Keeson word controller."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...app_session import app_session
from ...card import CARD_LIGHTING, CARD_MASSAGE, CARD_MASSAGE_TIMER, CARD_PRESETS, CARD_UTILITY
from ...codec import keeson, okin_nframe, okin_soundwave
from ...const import (
    CONF_BLE_DEVICE_NAME,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    CONF_SYMPHONY_SIDE,
)
from ...controller_state import StateKey, sided, sided_updates
from ...profiles import symphony as app
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..keeson.controller import KeesonController, _wait_unless_cancelled
from ..lifecycle import ControllerSession
from . import state
from . import state_keys as k

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...coordinator import AdjustableBedCoordinator
    from .services import AlarmFields

NUS = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_WRITE = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_NOTIFY = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
INFORMATION = "0000180a-0000-1000-8000-00805f9b34fb"
FIRMWARE = "00002a26-0000-1000-8000-00805f9b34fb"
PROTOCOL = "00002a27-0000-1000-8000-00805f9b34fb"


@dataclass
class LocalSession:
    child: bool = False


class SymphonyController(KeesonController):
    """Independent product/selector, captured releases and current-link state."""

    # No motor-position reader or telemetry is inherited from the word family.
    read_positions = BedController.read_positions

    def __init__(self, coordinator: AdjustableBedCoordinator, profile: app.SymphonyProfile) -> None:
        super().__init__(coordinator, char_uuid=NUS_WRITE)
        self.profile = app.word_profile(profile)
        self.app = profile
        self.local = app_session(
            coordinator.hass, coordinator.address, ("symphony", profile.key), LocalSession
        )
        self._link: BleakClient | None = None
        self._writer: BleakGATTCharacteristic | None = None
        self._reader: BleakGATTCharacteristic | None = None
        self._generation = 0
        self._ready = False
        self._assembler = state.Assembler()
        self._old_massage: dict[int, bytes] = {}
        self._alarm_cache: bytes | None = None
        self._alarm_received = asyncio.Event()
        self._alarm_at: float | None = None
        self._sonic_state: state.Massage | None = None
        self._light: state.Light | None = None
        self._light_received = asyncio.Event()
        self._massage_received = asyncio.Event()
        self._firmware: str | None = None
        self._protocol: str | None = None
        self.forward_controller_state_updates(k.CHILD("on" if self.local.child else "off"))

    @property
    def control_characteristic_uuid(self) -> str:
        return str(self._writer.uuid) if self._writer is not None else NUS_WRITE

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.app.product.page in ("split_p1", "split_p3")

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return "memory_1" in self.app.presets

    @property
    def memory_slot_count(self) -> int:
        return 2 if "memory_2" in self.app.presets else int(self.supports_memory_presets)

    @property
    def supports_memory_programming(self) -> bool:
        return "memory_1" in self.app.saves

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "anti_snore" in self.app.presets

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in self.app.presets

    @property
    def supports_preset_lounge(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return self.app.product.light

    @property
    def supports_light_toggle_control(self) -> bool:
        return False  # This app's explicit spec owns its toggle or fixed P2 actions.

    @property
    def supports_massage(self) -> bool:
        return self.app.sonic or self.app.product.massage is not None

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def persisted_app_state_key(self) -> str:
        return self.app.key

    @property
    def persisted_app_state(self) -> dict[str, bool]:
        return {"child": self.local.child}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        child = state.get("child", False)
        if set(state) - {"child"} or type(child) is not bool:
            raise ValueError("Invalid Symphony local child-mode preference")
        self.local.child = child
        self.forward_controller_state_updates(k.CHILD("on" if child else "off"))

    def _side(self) -> int:
        return (
            1
            if self.command_side == "left"
            else 2
            if self.command_side == "right"
            else self.app.side
        )

    def _admit(self) -> None:
        if self.local.child:
            raise ValueError("Symphony local child mode is on")
        if not self._ready or self.client is not self._link:
            raise ConnectionError("Symphony session is no longer current")

    def validate_command(self) -> None:
        self._admit()

    def validate_light(self, color: int, brightness: int) -> None:
        self._admit()
        if (
            self.app.product.page != "soundwave"
            or not 1 <= color <= 7
            or not 20 <= brightness <= 80
        ):
            raise ValueError("Choose a SoundWave light product, color 1..7 and brightness 20..80")

    def _roles(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Symphony is disconnected")
        self._writer = self._reader = None
        # Preserve the app's iteration overwrite, including independently
        # selected write and notify roles when both transports are present.
        for service in client.services:
            uuid = str(service.uuid).lower()
            if uuid in (NUS, keeson.JALON_WRITE_SERVICE):
                found = service.get_characteristic(NUS_WRITE if uuid == NUS else keeson.JALON_WRITE)
                if found is not None:
                    self._writer = found
            if uuid in (NUS, keeson.JALON_NOTIFY_SERVICE):
                found = service.get_characteristic(
                    NUS_NOTIFY if uuid == NUS else keeson.JALON_NOTIFY
                )
                if found is not None:
                    self._reader = found
        if self._writer is None or self._reader is None:
            raise ConnectionError("Symphony requires a recognized write and notification role")
        if "write" not in self._writer.properties:
            raise ConnectionError("Symphony requires acknowledged GATT writes")

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if not self._ready or self._writer is None or self._link is None:
            raise ConnectionError("Symphony session is unavailable")
        generation = self._generation

        def current() -> None:
            if not self._ready or generation != self._generation:
                raise ConnectionError("Queued write belongs to an earlier Symphony session")

        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=True,
            characteristic=self._writer,
            expected_client=self._link,
            before_write=current,
        )

    async def _cleanup(
        self, release: tuple[int, tuple[bytes, ...]], generation: int, client: BleakClient | None
    ) -> None:
        async def send() -> None:
            delay, frames = release
            if delay:
                await asyncio.sleep(delay / 1000)
            failure: Exception | None = None
            for frame in frames:
                if generation != self._generation or not self._ready or self.client is not client:
                    return
                try:
                    await self.write_command(frame, cancel_event=asyncio.Event())
                except Exception as error:
                    failure = failure or error
            if failure is not None:
                raise failure

        # The scheduler lane remains owned until this captured release ends.
        task = asyncio.create_task(send())
        interrupted = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                interrupted = True
        task.result()
        if interrupted:
            raise asyncio.CancelledError

    async def _hold_frame(
        self, frame: bytes, duration_ms: int, release: tuple[int, tuple[bytes, ...]]
    ) -> None:
        self._admit()
        event, generation, client = self._coordinator.cancel_command, self._generation, self._link
        deadline = asyncio.get_running_loop().time() + duration_ms / 1000
        budget = asyncio.timeout_at(deadline)
        try:
            async with budget:
                await self.write_command(frame)
                await _wait_unless_cancelled(event, deadline - asyncio.get_running_loop().time())
        except TimeoutError:
            if not budget.expired():
                raise
        finally:
            await self._cleanup(release, generation, client)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        axes = (*self.app.product.axes, *(("head_foot",) if self.app.product.combined else ()))
        return tuple(f"{axis}_{direction}" for axis in axes for direction in ("up", "down"))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or isinstance(duration_ms, bool)
            or not 100 <= duration_ms <= 30000
        ):
            raise ValueError("Choose a product motor and a duration of 100..30000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        axis, direction = control.rsplit("_", 1)
        side = self._side()
        wire = (
            "P2"
            if self.app.product.value == 13 and axis == "elevation"
            else "P2"
            if axis == "head_foot_lift" and self.app.sonic
            else "P3"
            if axis == "head_foot_lift"
            else self.app.position_wire
        )
        await self._hold_frame(
            app.movement(self.app, axis, direction == "up", side),
            self.leased_hold_ms(duration_ms),
            app.stops(self.app, side, wire=wire),
        )

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if direction is None:
            await self.stop_all()
        else:
            count, delay = self.motor_pulse_settings()
            await self.hold_control(
                f"{motor}_{'up' if direction else 'down'}", max(100, min(30000, count * delay))
            )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        axes = (*self.app.product.axes, *(("head_foot",) if self.app.product.combined else ()))
        return tuple(
            MotorControlSpec(
                axis,
                "symphony_" + axis,
                lambda ctrl, axis=axis: selected(ctrl)._move_motor(axis, True),
                lambda ctrl, axis=axis: selected(ctrl)._move_motor(axis, False),
                lambda ctrl: ctrl.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up", f"{axis}_down", stop_scope="side", press_hold_ms=None
                ),
            )
            for axis in axes
        )

    async def stop_all(self) -> None:
        await self._cleanup(app.stops(self.app, self._side()), self._generation, self._link)
        if self.app.product.value == 13 and self.app.position_wire != "P2":
            await self._cleanup(
                app.stops(self.app, self._side(), wire="P2"), self._generation, self._link
            )

    async def recall(self, name: str, *, save: bool = False) -> None:
        self._admit()
        side = self._side()
        frame = app.preset(self.app, name, side, save=save)
        if self.app.product.page == "soundwave":
            await self.write_command(frame)
        else:
            # Explicit HA taps have no artificial Android gesture duration.
            # Preserve the page's release after both recall and HILO Save.
            generation, client = self._generation, self._link
            try:
                await self.write_command(frame)
            finally:
                await self._cleanup(app.stops(self.app, side), generation, client)

    async def _preset(self, preset: str) -> None:
        await self.recall(preset)

    async def preset_memory(self, memory_num: int) -> None:
        await self.recall(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        await self.recall(f"memory_{memory_num}", save=True)

    async def sync_clock(self) -> None:
        generation = self._generation
        frame = app.clock(self.app.selector, dt_util.now())
        await self.write_command(frame)
        if self.app.selector == 4 and generation == self._generation:
            await self.write_command(frame)  # Source fall-through sends the same snapshot twice.

    @property
    def supports_clock_sync(self) -> bool:
        return True

    def _state_query(self) -> bytes:
        return (
            okin_soundwave.query(7)
            if self.app.sonic
            else app.encode_word("P1", 0)
            if self.app.selector == 4
            else okin_nframe.request(0xB0)
        )

    async def query_state(self) -> None:
        generation = self._generation
        await self.write_command(self._state_query())
        if self.app.sonic and generation == self._generation:
            await self.write_command(okin_soundwave.query(6))

    def _alarm_query(self) -> bytes:
        return (
            okin_soundwave.query(3, (1,))
            if self.app.product.page == "soundwave"
            else keeson.checked(b"\xe1\x80\x03")
            if self.app.selector == 4
            else okin_nframe.request(0xC0)
        )

    async def query_alarm(self) -> None:
        await self.write_command(self._alarm_query())

    def alarm_frame(
        self,
        *,
        enabled: bool,
        hour: int,
        minute: int,
        week: int,
        mode: str,
        side: int | None = None,
    ) -> bytes:
        self._admit()
        side = self._side() if side is None else side
        if self.app.product.page in ("split_p1", "split_p3"):
            if self._alarm_at is None or asyncio.get_running_loop().time() - self._alarm_at > 30:
                raise ValueError(
                    "Refresh current-session split alarm state before changing either side"
                )
            if (
                enabled
                and self.app.product.page == "split_p3"
                and state.opposite_alarm_conflict(self._alarm_cache, side, hour, minute)
            ):
                raise ValueError("The opposite side already has an enabled alarm at that time")
        return app.alarm(
            self.app,
            enabled=enabled,
            hour=hour,
            minute=minute,
            week=week,
            mode=mode,
            side=side,
            cache=self._alarm_cache,
        )

    def alarm_frames(
        self, *, sides: tuple[int, ...], enabled: bool, hour: int, minute: int, week: int, mode: str
    ) -> tuple[bytes, ...]:
        fields: AlarmFields = {
            "enabled": enabled,
            "hour": hour,
            "minute": minute,
            "week": week,
            "mode": mode,
        }
        frames = tuple(self.alarm_frame(side=side, **fields) for side in sides)
        if self.app.product.page == "split_p1":
            # Both changes share one complete table, so the second side cannot
            # restore peer fields from the pre-request notification cache.
            frame = self._alarm_cache
            for side in sides:
                frame = app.alarm(self.app, side=side, cache=frame, **fields)
            assert frame is not None
            return (frame,)
        if self.app.product.page == "split_p3" and len(sides) > 1 and enabled:
            raise ValueError(
                "Split P3 sides cannot share the same enabled alarm time; select one side"
            )
        return frames

    async def prepare_alarm(self) -> None:
        generation = self._generation
        self._alarm_received.clear()
        self._alarm_cache, self._alarm_at = None, None
        if self.app.product.page == "soundwave":
            await self.write_command(app.clock(9, dt_util.now()))
        else:
            await self.sync_clock()
        await _wait_unless_cancelled(self._coordinator.cancel_command, 0.1)
        if generation != self._generation:
            raise ConnectionError("The alarm request belongs to an earlier session")
        await self.query_alarm()
        await _wait_unless_cancelled(self._coordinator.cancel_command, 0.1)
        if generation != self._generation:
            raise ConnectionError("The alarm request belongs to an earlier session")
        await self.query_alarm()
        if self.app.product.page in ("split_p1", "split_p3"):
            try:
                await asyncio.wait_for(self._alarm_received.wait(), 2)
            except TimeoutError as error:
                raise ValueError(
                    "No complete split alarm response; peer state remains unknown"
                ) from error

    async def set_alarm(
        self,
        *,
        enabled: bool,
        hour: int,
        minute: int,
        week: int,
        mode: str,
        sides: tuple[int, ...] | None = None,
    ) -> None:
        frames = self.alarm_frames(
            sides=sides or (self._side(),),
            enabled=enabled,
            hour=hour,
            minute=minute,
            week=week,
            mode=mode,
        )
        generation, client = self._generation, self._link
        for frame in frames:
            if generation != self._generation:
                return
            await self.write_command(frame)
            if self.app.product.page != "soundwave":
                await _wait_unless_cancelled(self._coordinator.cancel_command, 0.3)
                if generation != self._generation or client is not self._link:
                    return
                await self.write_command(frame)
        if generation == self._generation:
            await self.query_alarm()

    async def set_privacy(self, enabled: bool) -> None:
        if self.app.selector not in (2, 9):
            raise ValueError(
                "The app's Privacy Settings are available only for Sleep Smart selectors 2 and 9"
            )
        frame = (
            okin_soundwave.record(7, 2, (int(enabled),))
            if self.app.selector == 9
            else okin_nframe.parameter_record(0xB2, (int(enabled),))
        )
        generation = self._generation
        await self.write_command(frame)
        if generation == self._generation:
            await self.query_state()

    async def configure_snore(
        self, *, enabled: bool, axis: str, strength: int, demo: bool = False
    ) -> None:
        self._admit()
        generation = self._generation
        frame = app.anti_snore(self.app, enabled=enabled, axis=axis, strength=strength, demo=demo)
        await self.write_command(frame)
        if not self.app.sonic:
            await _wait_unless_cancelled(self._coordinator.cancel_command, 0.3)
            if generation != self._generation:
                return
            await self.write_command(frame)
        if generation == self._generation:
            await self.write_command(self._state_query())

    async def set_light(self, *, color: int | None = None, brightness: int | None = None) -> None:
        self._admit()
        generation = self._generation
        if self.app.product.page != "soundwave":
            raise ValueError("This product's light has no color/brightness controls")
        if color is None or brightness is None:
            self._light_received.clear()
            self._light = None
            generation = self._generation
            await self.write_command(okin_soundwave.query(4))
            try:
                await asyncio.wait_for(self._light_received.wait(), 2)
            except TimeoutError as error:
                raise ValueError(
                    "No fresh light state; explicitly provide both color and brightness"
                ) from error
            self._admit()
            if generation != self._generation:
                raise ValueError("The light request belongs to an earlier session")
            if self._light is None:
                raise ValueError(
                    "Refresh light state first, or explicitly provide both color and brightness"
                )
            color = self._light.color if color is None else color
            brightness = self._light.brightness if brightness is None else brightness
        await self.write_command(app.light(color, brightness))
        if generation == self._generation:
            await self.write_command(okin_soundwave.query(4))

    async def light_action(self, on: bool | None) -> None:
        self._admit()
        generation = self._generation
        if not self.app.product.light:
            raise ValueError("The selected product has no light control")
        if self.app.product.page == "soundwave":
            if on is None:
                raise ValueError("Choose the explicit light On or Off action")
            await self.write_command(okin_soundwave.record(4, 1, (0, int(on)), size=5))
            if generation == self._generation:
                await self.write_command(okin_soundwave.query(4))
        else:
            await self.write_command(
                app.encode_word("P1" if self.app.selector == 4 else "P3", app.WORDS["light"])
            )

    async def massage_action(self, action: str) -> None:
        self._admit()
        generation = self._generation
        if self.app.sonic:
            fixed = {"on": (12, 1), "off": (12, 0), "sonic_on": (5, 1), "sonic_off": (5, 0)}
            if action in fixed:
                operation, value = fixed[action]
                frame = okin_soundwave.record(6, operation, (0, value))
            else:
                self._massage_received.clear()
                self._sonic_state = None
                generation = self._generation
                await self.write_command(okin_soundwave.query(6))
                try:
                    await asyncio.wait_for(self._massage_received.wait(), 2)
                except TimeoutError as error:
                    raise ValueError("No fresh sonic massage response") from error
                self._admit()
                current = self._sonic_state
                if generation != self._generation or current is None:
                    raise ValueError("The massage request belongs to an earlier session")
                if action == "timer":
                    frame = app.sonic_timer(current.timer_index)
                elif action == "wave_next":
                    frame = okin_soundwave.record(
                        6, 3, (0, (current.wave + 1) % 9 if current.wave is not None else 0)
                    )
                elif action in ("head_strength", "foot_strength"):
                    value = current.head if action == "head_strength" else current.foot
                    assert value is not None
                    frame = app.sonic_strength(value, 1 if action == "head_strength" else 2)
                else:
                    raise ValueError("Unknown sonic massage action")
        else:
            if action not in self.massage_actions:
                raise ValueError("This massage page has no requested control")
            key = {"on": "massage_on", "off": "massage_off"}.get(action, action)
            wire = self.app.position_wire if self.supports_single_address_pairing else self.app.wire
            side = self._side() if self.supports_single_address_pairing else 0
            if self.app.product.page == "split_p1" and key == "foot_strength":
                side = 0  # Actual fixed helper, unlike its sibling head-strength helper.
            if self.app.product.page == "split_p3" and key == "head_strength":
                word = 0x800 if side == 1 else 0x400
            else:
                word = app.WORDS[key]
            if wire == "P3" and key == "wave_previous":
                word = 0x80000
            frame = app.encode_word(wire, word, side)
        await self.write_command(frame)
        if generation == self._generation:
            await self.query_state()

    @property
    def massage_actions(self) -> tuple[str, ...]:
        if self.app.sonic:
            return (
                "on",
                "off",
                "sonic_on",
                "sonic_off",
                "head_strength",
                "foot_strength",
                "wave_next",
                "timer",
            )
        page = self.app.product.massage
        if page is None:
            return ()
        if page == "premier":
            return (
                "on",
                "off",
                "intensity_up",
                "intensity_down",
                "timer",
                "wave_next",
                "wave_previous",
            )
        if page in ("kgd", "split_p1"):
            return ("on", "off", "head_strength", "foot_strength", "timer", "wave_next")
        return (
            "on",
            "off",
            "head_strength" if page == "split_p3" else "intensity_up",
            "timer",
            "wave_next",
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        def button(
            key: str,
            label: str,
            fn: Callable[[SymphonyController], Awaitable[None]],
            card=CARD_UTILITY,
        ) -> ControllerButtonSpec:
            async def press(ctrl: BedController) -> None:
                await fn(selected(ctrl))

            return ControllerButtonSpec(
                "symphony_" + key,
                label,
                press,
                translation_key=f"symphony_{card.section.value}_action",
                translation_placeholders={"action": label},
                card=card,
            )

        buttons = [
            button("refresh", "Refresh bed state", lambda c: c.query_state()),
            button("alarm_refresh", "Refresh alarm", lambda c: c.query_alarm()),
            button(
                "diagnostic",
                "Request bed diagnostic status (opaque)",
                lambda c: c.write_command(okin_nframe.parameter_record(0xB4, (1,))),
            ),
        ]
        for name in self.app.saves:
            buttons.append(
                button(
                    "save_" + name,
                    "Save " + name.replace("_", " "),
                    lambda c, name=name: c.recall(name, save=True),
                    CARD_PRESETS,
                )
            )
        if "reading" in self.app.presets:
            buttons.append(
                button("reading", "Reading", lambda c: c.recall("reading"), CARD_PRESETS)
            )
        if self.app.product.light:
            if self.app.product.page == "soundwave":
                buttons.extend(
                    (
                        button(
                            "light_on", "Light on", lambda c: c.light_action(True), CARD_LIGHTING
                        ),
                        button(
                            "light_off", "Light off", lambda c: c.light_action(False), CARD_LIGHTING
                        ),
                        button(
                            "light_refresh",
                            "Refresh light",
                            lambda c: c.write_command(okin_soundwave.query(4)),
                        ),
                    )
                )
            else:
                buttons.append(
                    button(
                        "light_toggle",
                        "Toggle underbed light",
                        lambda c: c.light_action(None),
                        CARD_LIGHTING,
                    )
                )
        for action in self.massage_actions:
            buttons.append(
                button(
                    "massage_" + action,
                    "Massage " + action.replace("_", " "),
                    lambda c, action=action: c.massage_action(action),
                    CARD_MASSAGE,
                )
            )
        if self.app.selector in (2, 9):
            buttons.extend(
                (
                    button("privacy_on", "Privacy on", lambda c: c.set_privacy(True)),
                    button("privacy_off", "Privacy off", lambda c: c.set_privacy(False)),
                )
            )
        return tuple(buttons)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if self.app.product.page != "soundwave":
            return ()
        return (
            ControllerNumberSpec(
                "symphony_light_color",
                "symphony_light_color",
                k.COLOR,
                1,
                7,
                1,
                lambda c, value: selected(c).set_light(color=int(value)),
                card=CARD_LIGHTING,
            ),
            ControllerNumberSpec(
                "symphony_light_brightness",
                "symphony_light_brightness",
                k.BRIGHTNESS,
                20,
                80,
                1,
                lambda c, value: selected(c).set_light(brightness=int(value)),
                card=CARD_LIGHTING,
            ),
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        def local(option: str) -> None:
            current = self._coordinator.capability_controller
            if not isinstance(current, SymphonyController) or current.local is not self.local:
                raise ValueError("The Symphony Sleep Sense profile changed")
            self.local.child = option == "on"
            self.forward_controller_state_updates(k.CHILD(option))

        async def choose(ctrl: BedController, option: str) -> None:
            selected(ctrl).local.child = option == "on"
            ctrl.forward_controller_state_updates(k.CHILD(option))

        return (
            ControllerSelectSpec(
                "symphony_child_mode",
                "symphony_child_mode",
                k.CHILD,
                ("off", "on"),
                choose,
                local_select_fn=local,
            ),
        )

    def _key[T](self, key: StateKey[T]) -> StateKey[T]:
        return sided(key, self.command_side) if self.supports_single_address_pairing else key

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = [
            ControllerStateSensorSpec(
                "symphony_firmware", "symphony_firmware", k.FIRMWARE, "mdi:chip"
            ),
            ControllerStateSensorSpec(
                "symphony_protocol", "symphony_protocol", k.PROTOCOL, "mdi:bluetooth"
            ),
            ControllerStateSensorSpec(
                "symphony_alarm",
                "symphony_alarm",
                self._key(k.HOUR),
                "mdi:alarm",
                attribute_keys=(
                    self._key(k.MINUTE),
                    self._key(k.SECOND),
                    self._key(k.WEEK),
                    self._key(k.MODE),
                    self._key(k.ALARM),
                ),
            ),
        ]
        if self.supports_massage:
            specs.append(
                ControllerStateSensorSpec(
                    "symphony_massage",
                    "symphony_massage",
                    self._key(k.TIMER),
                    "mdi:vibrate",
                    attribute_keys=(
                        self._key(k.MASSAGE),
                        self._key(k.WAVE),
                        self._key(k.HEAD),
                        self._key(k.FOOT),
                        self._key(k.SONIC),
                        self._key(k.PREMIER),
                    ),
                    card=CARD_MASSAGE_TIMER,
                )
            )
        return tuple(specs)

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        specs = (
            ControllerStateBinarySensorSpec(
                "symphony_privacy", "symphony_privacy", k.PRIVACY, "mdi:shield-lock"
            ),
            ControllerStateBinarySensorSpec(
                "symphony_anti_snore",
                "symphony_anti_snore",
                k.SNORE,
                "mdi:sleep",
                attribute_keys=(k.STRENGTH,),
            ),
        )
        if self.app.product.page == "soundwave":
            specs += (
                ControllerStateBinarySensorSpec(
                    "symphony_light_on",
                    "symphony_light_on",
                    k.LIGHT_ON,
                    "mdi:lightbulb",
                    attribute_keys=(k.COLOR, k.BRIGHTNESS),
                    card=CARD_LIGHTING,
                ),
            )
        return specs

    def _publish[T](self, key: StateKey[T], value: T, side: int) -> None:
        if self.supports_single_address_pairing:
            self.forward_controller_state_updates(
                *sided_updates(
                    key, "left" if side == 1 else "right", value, unsided=side == self.app.side
                )
            )
        else:
            self.forward_controller_state_updates(key(value))

    def _notify(self, generation: int, client: BleakClient, data: bytes) -> None:
        if (
            not self._ready
            or generation != self._generation
            or client is not self._link
            or self.client is not client
        ):
            return
        assert self._reader is not None
        self.forward_raw_notification(str(self._reader.uuid), data)
        packet = self._assembler.feed(data)
        if packet is None:
            return
        value = (
            state.soundwave(packet)
            if self.app.sonic or self.app.product.page == "soundwave"
            else None
        )
        if isinstance(value, state.Light):
            self._light = value
            self._light_received.set()
            self.forward_controller_state_updates(
                k.COLOR(value.color), k.BRIGHTNESS(value.brightness), k.LIGHT_ON(value.on)
            )
        elif isinstance(value, state.Snore):
            self.forward_controller_state_updates(
                k.SNORE(value.enabled), k.STRENGTH(value.strength), k.PRIVACY(value.privacy)
            )
        if self.app.selector == 2 and packet[:2] == b"\xa5\x0b":
            index = 19 if state.offline_voice(self._protocol, self._firmware) else 18
            if len(packet) > index:
                self.forward_controller_state_updates(
                    k.PRIVACY(bool(packet[19] & 2) if index == 19 else packet[18] == 1)
                )
        sides = (1, 2) if self.supports_single_address_pairing else (self.app.side,)
        for side in sides:
            massage = (
                value
                if isinstance(value, state.Massage)
                else state.legacy_massage(self.app, packet, side, self._old_massage.get(side, b""))
            )
            if massage is not None:
                if isinstance(value, state.Massage):
                    self._sonic_state = massage
                    self._massage_received.set()
                self._old_massage[side] = packet
                self._publish(k.MASSAGE, massage.running, side)
                self._publish(k.TIMER, massage.timer_index, side)
                self._publish(k.WAVE, massage.wave, side)
                self._publish(k.HEAD, massage.head, side)
                self._publish(k.FOOT, massage.foot, side)
                self._publish(k.SONIC, massage.sonic, side)
                self._publish(
                    k.PREMIER,
                    "0" if not massage.timer_index else str(massage.timer_index) + "0",
                    side,
                )
            alarm = state.alarm(self.app, packet, side)
            if alarm is not None:
                self._alarm_cache = packet
                self._alarm_at = asyncio.get_running_loop().time()
                self._alarm_received.set()
                self._publish(k.ALARM, alarm.enabled, side)
                if not alarm.enabled and self.app.product.page != "soundwave":
                    now = dt_util.now()
                    self._publish(k.HOUR, now.hour, side)
                    self._publish(k.MINUTE, now.minute, side)
                for key, field in (
                    (k.WEEK, alarm.week),
                    (k.MODE, alarm.mode),
                    (k.HOUR, alarm.hour),
                    (k.MINUTE, alarm.minute),
                    (k.SECOND, alarm.second),
                ):
                    if field is not None:
                        self._publish(key, field, side)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._roles()
        client = self.client
        assert client is not None and self._reader is not None
        self._generation += 1
        generation = self._generation
        self._link, self._ready, self._notify_callback = client, True, callback
        try:
            await client.start_notify(
                self._reader, lambda _sender, data: self._notify(generation, client, bytes(data))
            )
        except BaseException:
            self.on_disconnect()
            raise

    async def stop_notify(self) -> None:
        client, reader = self._link, self._reader
        self.on_disconnect()
        if client is not None and client.is_connected and reader is not None:
            await client.stop_notify(reader)

    def on_disconnect(self) -> None:
        self._generation += 1
        self._ready = False
        self._assembler = state.Assembler()
        self._old_massage.clear()
        self._alarm_cache, self._alarm_at = None, None
        self._alarm_received.clear()
        self._sonic_state = self._light = None
        self._firmware = self._protocol = None
        self._light_received.set()
        self._massage_received.set()
        for key in (
            k.FIRMWARE,
            k.PROTOCOL,
            k.PRIVACY,
            k.SNORE,
            k.STRENGTH,
            k.COLOR,
            k.BRIGHTNESS,
            k.LIGHT_ON,
        ):
            self.forward_controller_state_updates(key(None))
        for side in (1, 2) if self.supports_single_address_pairing else (self.app.side,):
            self._publish(k.MASSAGE, None, side)
            self._publish(k.TIMER, None, side)
            self._publish(k.WAVE, None, side)
            self._publish(k.HEAD, None, side)
            self._publish(k.FOOT, None, side)
            self._publish(k.SONIC, None, side)
            self._publish(k.PREMIER, None, side)
            self._publish(k.ALARM, None, side)
            self._publish(k.WEEK, None, side)
            self._publish(k.MODE, None, side)
            self._publish(k.HOUR, None, side)
            self._publish(k.MINUTE, None, side)
            self._publish(k.SECOND, None, side)

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        if self.app.sonic:
            await self.write_command(okin_soundwave.query(5, (1, 255, 255, 0, 0, 34, 37, 18, 75)))
        client = self._link
        assert client is not None
        generation = self._generation
        service = client.services.get_service(INFORMATION)
        if service is not None:
            for uuid, key in ((FIRMWARE, k.FIRMWARE), (PROTOCOL, k.PROTOCOL)):
                char = service.get_characteristic(uuid)
                if char is not None:
                    value = (
                        bytes(await client.read_gatt_char(char))
                        .decode("utf-8", errors="replace")
                        .rstrip("\0")
                    )
                    if not session.is_current() or generation != self._generation:
                        return
                    if key == k.FIRMWARE:
                        self._firmware = value
                    else:
                        self._protocol = value
                    self.forward_controller_state_updates(key(value))

    async def async_after_connect(self, session: ControllerSession) -> None:
        generation = self._generation
        await asyncio.sleep(0.1)
        if not session.is_current() or generation != self._generation:
            return
        await self.sync_clock()
        if not session.is_current() or generation != self._generation:
            return
        await self.query_state()
        if not session.is_current() or generation != self._generation:
            return
        if self.app.product.page == "soundwave":
            await self.write_command(okin_soundwave.query(4))
        await asyncio.sleep(0.1)
        if session.is_current() and generation == self._generation:
            await self.query_alarm()


def selected(controller: BedController) -> SymphonyController:
    return require_controller(controller, SymphonyController)


async def build_controller(ctx: BuildContext) -> SymphonyController:
    product = str(ctx.data.get(CONF_PRODUCT_TYPE, "0"))
    if product not in app.PRODUCTS:
        # The app parses the product before its unknown-ID fallback. Null and
        # nonnumeric catalog results do not become a known model.
        int(product)
        product = "0"
    selector = ctx.variant or str(ctx.data.get(CONF_PROTOCOL_VARIANT, "0"))
    if selector not in app.SELECTORS:
        if selector != "auto":
            raise ValueError("Choose a source-proven Symphony selector")
        # Old Auto entries can use this app's own scan rule, never a model guess.
        name = ctx.live_device_name or ctx.data.get(CONF_BLE_DEVICE_NAME, "")
        selector = str(app.selector_from_scan(name, ctx.manufacturer_data or {}))
    side = 2 if ctx.data.get(CONF_SYMPHONY_SIDE) == "right" else 1
    return SymphonyController(
        ctx.coordinator, app.SymphonyProfile(app.PRODUCTS[product], int(selector), side)
    )
