"""Remacro (SynData) controller for the Slumberland, The Brick and Jerome's apps.

Accepted evidence: cluster-002 / row 050 (``com.cheers.slumber`` 1.0 (2),
``com.cheers.brick`` 1.0 (3), ``com.cheers.jewmes`` 1.202112141512 (20)).
The advertised company ID selects one of the apps' control screens; this
controller exposes exactly that screen's controls. Hardware is unverified.

Movement sends one press frame and, after the hold, the axis STOP 120 ms
later. OneActivity instead repeats three STOPs, and its combined arrows stream
every 100 ms in Slumberland and Jerome's. STOP cleanup always runs, including
on cancellation, which the apps themselves do not guarantee.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, Literal

from bleak.exc import BleakError

from ..const import DOMAIN, REMACRO_READ_CHAR_UUID, REMACRO_WRITE_CHAR_UUID
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    MotorCommandCallable,
    MotorControlSpec,
    SideBoundController,
)
from .remacro_protocol import (
    APP_JEROMES,
    APP_LED_SETTINGS_MODEL_IDS,
    APP_SLUMBERLAND,
    APP_THE_BRICK,
    FLAT,
    LED_DEFAULT_BRIGHTNESS,
    LED_PREVIEW_DELAY_S,
    LED_SAVE_DELAY_S,
    LED_WHITE,
    LIGHT_OFF,
    LIGHT_RGBV,
    LIGHT_RGBV_SAVE,
    MOTOR_STOP,
    RELEASE_DELAY_S,
    STREAM_INTERVAL_S,
    Axis,
    MassageCodes,
    Model,
    RemacroApp,
    RemacroSession,
    SideCodes,
    SynDataSerial,
    session_for,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

Side = Literal["left", "right"]
SIDE_STATE_KEY = "remacro_control_side"
LED_STATE_KEY = "remacro_led_brightness"
# OneActivity release schedules, measured from the release moment.
_ONE_INDIVIDUAL_RELEASE = (0.0, 0.120, 0.240)
_ONE_COMBINED_RELEASE = (0.0, 0.020, 0.040)


def _remacro(
    action: Callable[[RemacroController], Coroutine[Any, Any, None]],
) -> MotorCommandCallable:
    async def invoke(controller: BedController) -> None:
        target: object = controller
        if isinstance(target, SideBoundController):
            target = target._controller
        if not isinstance(target, RemacroController):
            raise TypeError("This control requires the Remacro controller")
        await action(target)

    return invoke


async def _select_side(controller: BedController, option: str) -> None:
    await _remacro(lambda ctrl: ctrl.set_control_side(option))(controller)


async def _set_led_brightness(controller: BedController, value: float) -> None:
    await _remacro(lambda ctrl: ctrl.set_led_brightness(int(value)))(controller)


class RemacroController(BedController):
    """One Remacro bed as shown by one app's model-specific control screen."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app: RemacroApp,
        model: Model,
        session: RemacroSession | None = None,
        led_level: object = None,
    ) -> None:
        super().__init__(coordinator)
        self._app: RemacroApp = app
        self._model = model
        # All app state lives in the session so controller rebuilds after a
        # command handoff or idle disconnect do not reset it (see RemacroSession).
        self._session = session or RemacroSession(
            SynDataSerial(cache_hold_serial=app == APP_JEROMES)
        )
        self._serial = self._session.serial
        if self._session.led_brightness is None:
            self._session.led_brightness = (
                led_level
                if isinstance(led_level, int)
                and not isinstance(led_level, bool)
                and 0 <= led_level <= 255
                else LED_DEFAULT_BRIGHTNESS
            )
        updates: dict[str, Any] = {}
        if self._model.screen.split:
            updates[SIDE_STATE_KEY] = self._session.side
        if self.supports_led_brightness:
            updates[LED_STATE_KEY] = self._led_level
        self.forward_controller_state_updates(updates)

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    @property
    def _led_level(self) -> int:
        level = self._session.led_brightness
        return LED_DEFAULT_BRIGHTNESS if level is None else level

    @property
    def app(self) -> RemacroApp:
        return self._app

    @property
    def model(self) -> Model:
        return self._model

    @property
    def control_side(self) -> Side:
        return "right" if self._session.side == "right" else "left"

    @property
    def _codes(self) -> SideCodes:
        screen = self._model.screen
        if self._session.side == "right" and screen.right is not None:
            return screen.right
        return screen.left

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        return {
            "remacro_app": self._app,
            "remacro_model_id": self._model.model_id,
            "remacro_model": self._model.name,
            "remacro_screen": self._model.screen.name,
            "remacro_control_side": self.control_side if self._model.screen.split else None,
        }

    @property
    def control_characteristic_uuid(self) -> str:
        return REMACRO_WRITE_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        # Every app subscribes on connect, independently of any feature.
        return True

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    @property
    def supports_preset_flat(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "anti_snore" in self._model.screen.left.presets

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in self._model.screen.left.presets

    @property
    def supports_preset_zero_g(self) -> bool:
        return "zero_g" in self._model.screen.left.presets

    @property
    def memory_slot_count(self) -> int:
        return len(self._model.screen.left.memory_recall)

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def supports_memory_programming(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def has_lumbar_support(self) -> bool:
        return self._model.screen.left.lumbar is not None

    @property
    def supports_massage(self) -> bool:
        return self._model.screen.left.massage is not None

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_lights(self) -> bool:
        return self._model.screen.light_toggle

    @property
    def supports_discrete_light_control(self) -> bool:
        return self._model.screen.light_toggle

    @property
    def supports_stop_all(self) -> bool:
        # NineActivity has no global STOP frame; Stop only ends the active move.
        return self._model.screen.has_global_stop

    @property
    def supports_led_brightness(self) -> bool:
        return self._model.model_id in APP_LED_SETTINGS_MODEL_IDS[self._app]

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # Keys keep the legacy unique IDs; translations use the app labels.
        codes = self._model.screen.left
        specs: list[MotorControlSpec] = []
        if codes.head is not None:
            specs.append(
                MotorControlSpec(
                    key="back",
                    translation_key="head",
                    open_fn=lambda ctrl: ctrl.move_back_up(),
                    close_fn=lambda ctrl: ctrl.move_back_down(),
                    stop_fn=lambda ctrl: ctrl.move_back_stop(),
                )
            )
        if codes.lumbar is not None:
            specs.append(
                MotorControlSpec(
                    key="lumbar",
                    translation_key="lumbar",
                    open_fn=lambda ctrl: ctrl.move_lumbar_up(),
                    close_fn=lambda ctrl: ctrl.move_lumbar_down(),
                    stop_fn=lambda ctrl: ctrl.move_lumbar_stop(),
                    max_angle=30,
                )
            )
        if codes.foot is not None:
            specs.append(
                MotorControlSpec(
                    key="legs",
                    translation_key="feet",
                    open_fn=lambda ctrl: ctrl.move_legs_up(),
                    close_fn=lambda ctrl: ctrl.move_legs_down(),
                    stop_fn=lambda ctrl: ctrl.move_legs_stop(),
                    max_angle=45,
                )
            )
        if codes.combined is not None:
            specs.append(
                MotorControlSpec(
                    key="all_motors",
                    translation_key="all_motors",
                    open_fn=_remacro(lambda ctrl: ctrl.move_all_up()),
                    close_fn=_remacro(lambda ctrl: ctrl.move_all_down()),
                    stop_fn=_remacro(lambda ctrl: ctrl.move_all_stop()),
                )
            )
        return tuple(specs)

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset({"back", "legs", "head", "feet", "lumbar", "tilt", "all_motors"})

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if not self._model.screen.split:
            return ()
        return (
            ControllerSelectSpec(
                key=SIDE_STATE_KEY,
                translation_key=SIDE_STATE_KEY,
                state_key=SIDE_STATE_KEY,
                options=("left", "right"),
                select_fn=_select_side,
                local_select_fn=self.select_control_side,
            ),
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if not self.supports_led_brightness:
            return ()
        return (
            ControllerNumberSpec(
                key=LED_STATE_KEY,
                translation_key="light_level",
                state_key=LED_STATE_KEY,
                native_min_value=0,
                native_max_value=255,
                native_step=1,
                set_fn=_set_led_brightness,
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if not self.supports_led_brightness:
            return ()
        return (
            ControllerButtonSpec(
                key="remacro_led_brightness_save",
                name="Save light level",
                press_fn=_remacro(lambda ctrl: ctrl.save_led_brightness()),
                icon="mdi:content-save",
                translation_key="remacro_led_brightness_save",
            ),
        )

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _main(self, code: int, parameter: int = 0) -> bytes:
        """Frame for a main-screen tap (flat, memory, preset, massage, light)."""
        if self._app == APP_JEROMES:
            return self._serial.tap(code, parameter)
        return self._serial.hold(code, parameter)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        # Every app writes WRITE_TYPE_NO_RESPONSE.
        await self._write_gatt_with_retry(
            REMACRO_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=False,
        )

    async def _sleep(self, seconds: float) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds)

    async def _pause(self, seconds: float, cancel_event: asyncio.Event) -> bool:
        """Wait for ``seconds``; return True early when cancelled."""
        if cancel_event.is_set():
            return True
        if seconds <= 0:
            return False
        try:
            async with asyncio.timeout(seconds):
                await cancel_event.wait()
        except TimeoutError:
            return False
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Enable notifications like the apps; payloads carry no bed state."""
        self._notify_callback = callback
        client = self.client
        if client is None or not client.is_connected:
            return
        try:
            async with self._ble_lock:
                await client.start_notify(REMACRO_READ_CHAR_UUID, self._handle_notification)
        except BleakError:
            _LOGGER.warning("Remacro notification subscription failed", exc_info=True)

    async def stop_notify(self) -> None:
        self._notify_callback = None
        client = self.client
        if client is None or not client.is_connected:
            return
        try:
            async with self._ble_lock:
                await client.stop_notify(REMACRO_READ_CHAR_UUID)
        except BleakError:
            _LOGGER.debug("Remacro notification unsubscribe failed", exc_info=True)

    def _handle_notification(self, _sender: object, data: bytearray) -> None:
        # Sleep-module telemetry and MAC replies only feed app screens that
        # have no in-app route, so they are recorded for diagnostics only.
        self.forward_raw_notification(REMACRO_READ_CHAR_UUID, bytes(data))

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    async def _release(self, code: int, offsets: tuple[float, ...]) -> None:
        """Send the release STOP at each offset, surviving cancellation."""

        async def send() -> None:
            event = asyncio.Event()  # Fresh: a STOP request must not suppress it.
            failure: Exception | None = None
            elapsed = 0.0
            for offset in offsets:
                await self._sleep(offset - elapsed)
                elapsed = offset
                try:
                    await self.write_command(self._serial.hold(code), cancel_event=event)
                except Exception as error:  # noqa: BLE001 - the apps schedule each STOP independently
                    failure = failure or error
            if failure is not None:
                raise failure

        task = asyncio.create_task(send())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _move(self, axis: Axis | None, up: bool, *, combined: bool = False) -> None:
        if axis is None:
            raise NotImplementedError(f"{self._model.name} has no such control")
        code = axis.up if up else axis.down
        pulse_count, pulse_delay_ms = self.motor_pulse_settings()
        hold_s = max(pulse_count, 1) * pulse_delay_ms / 1000
        cancel_event = self._coordinator.cancel_command
        one_activity = self._model.screen.one_activity_timing
        stream = one_activity and combined and self._app != APP_THE_BRICK
        if stream:
            release = _ONE_COMBINED_RELEASE
        elif one_activity and not combined:
            release = _ONE_INDIVIDUAL_RELEASE
        else:
            release = (RELEASE_DELAY_S,)
        try:
            if not stream:
                await self.write_command(self._serial.hold(code))
                await self._pause(hold_s, cancel_event)
                return
            elapsed = 0.0
            while elapsed < hold_s:
                if cancel_event.is_set():
                    return
                await self.write_command(self._serial.hold(code))
                step = min(STREAM_INTERVAL_S, hold_s - elapsed)
                if await self._pause(step, cancel_event):
                    return
                elapsed += step
        finally:
            await self._release(axis.stop, release)

    async def _stop_axis(self, axis: Axis | None) -> None:
        if axis is None:
            raise NotImplementedError(f"{self._model.name} has no such control")
        await self.write_command(self._serial.hold(axis.stop), cancel_event=asyncio.Event())

    async def move_back_up(self) -> None:
        await self._move(self._codes.head, True)

    async def move_back_down(self) -> None:
        await self._move(self._codes.head, False)

    async def move_back_stop(self) -> None:
        await self._stop_axis(self._codes.head)

    async def move_head_up(self) -> None:
        await self.move_back_up()

    async def move_head_down(self) -> None:
        await self.move_back_down()

    async def move_head_stop(self) -> None:
        await self.move_back_stop()

    async def move_legs_up(self) -> None:
        await self._move(self._codes.foot, True)

    async def move_legs_down(self) -> None:
        await self._move(self._codes.foot, False)

    async def move_legs_stop(self) -> None:
        await self._stop_axis(self._codes.foot)

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.move_legs_stop()

    async def move_lumbar_up(self) -> None:
        await self._move(self._codes.lumbar, True)

    async def move_lumbar_down(self) -> None:
        await self._move(self._codes.lumbar, False)

    async def move_lumbar_stop(self) -> None:
        await self._stop_axis(self._codes.lumbar)

    async def move_all_up(self) -> None:
        await self._move(self._codes.combined, True, combined=True)

    async def move_all_down(self) -> None:
        await self._move(self._codes.combined, False, combined=True)

    async def move_all_stop(self) -> None:
        await self._stop_axis(self._codes.combined)

    async def stop_all(self) -> None:
        """Send the screens' global motor STOP; NineActivity defines none."""
        if not self._model.screen.has_global_stop:
            return
        self._session.active_preset = None
        frame = self._main(MOTOR_STOP) if self._codes.presets else self._serial.hold(MOTOR_STOP)
        await self.write_command(frame, cancel_event=asyncio.Event())

    def select_control_side(self, option: str) -> None:
        """Mirror the split screens' local left/right toggle (no write).

        Only the shared session and the coordinator's state change, so this is
        safe on an offline or since-rebuilt controller.
        """
        if not self._model.screen.split or option not in ("left", "right"):
            raise ValueError(f"Unsupported control side: {option}")
        # The entity may hold an older controller; always write the bed's live
        # session, the one every new controller for this address reads.
        sessions = self._coordinator.hass.data.get(DOMAIN, {}).get("remacro_sessions")
        if isinstance(sessions, dict):
            self._session = session_for(
                sessions, self._coordinator.address, self._app, self._model.model_id
            )
            self._serial = self._session.serial
        self._session.side = option
        self.forward_controller_state_update(SIDE_STATE_KEY, option)

    async def set_control_side(self, option: str) -> None:
        self.select_control_side(option)

    # ------------------------------------------------------------------
    # Presets and memory
    # ------------------------------------------------------------------

    async def preset_flat(self) -> None:
        await self.write_command(self._main(FLAT))

    async def _preset(self, name: str) -> None:
        code = self._codes.presets.get(name)
        if code is None:
            raise NotImplementedError(f"{self._model.name} has no {name} preset")
        # Tapping the highlighted preset again stops the motors instead.
        if self._session.active_preset == name:
            self._session.active_preset = None
            await self.write_command(self._main(MOTOR_STOP))
            return
        self._session.active_preset = name
        await self.write_command(self._main(code))

    async def preset_anti_snore(self) -> None:
        await self._preset("anti_snore")

    async def preset_tv(self) -> None:
        await self._preset("tv")

    async def preset_zero_g(self) -> None:
        await self._preset("zero_g")

    def _memory_code(self, codes: tuple[int, ...], memory_num: int) -> int:
        if isinstance(memory_num, bool) or not 1 <= memory_num <= len(codes):
            raise ValueError(f"{self._model.name} has memory slots 1-{len(codes)}")
        return codes[memory_num - 1]

    async def preset_memory(self, memory_num: int) -> None:
        await self.write_command(
            self._main(self._memory_code(self._codes.memory_recall, memory_num))
        )

    async def program_memory(self, memory_num: int) -> None:
        await self.write_command(self._main(self._memory_code(self._codes.memory_save, memory_num)))

    # ------------------------------------------------------------------
    # Massage: the apps' head, foot and wave buttons with local counters
    # ------------------------------------------------------------------

    def _massage(self) -> MassageCodes:
        massage = self._codes.massage
        if massage is None:
            raise NotImplementedError(f"{self._model.name} has no massage")
        return massage

    def _next_level(self, level: int) -> int:
        level += 1
        if level > 3:
            # Slumberland and The Brick skip "off" while a wave is running.
            level = 1 if self._session.wave and self._app != APP_JEROMES else 0
        return level

    def _zone_code(
        self, levels: tuple[int, int, int], wave_levels: tuple[int, int, int], off: int, level: int
    ) -> int:
        if level == 0:
            return off
        return (wave_levels if self._session.wave else levels)[level - 1]

    async def massage_head_toggle(self) -> None:
        massage = self._massage()
        self._session.head_level = self._next_level(self._session.head_level)
        await self.write_command(
            self._main(
                self._zone_code(massage.head, massage.head_wave, massage.head_off, self._session.head_level)
            )
        )

    async def massage_foot_toggle(self) -> None:
        massage = self._massage()
        self._session.foot_level = self._next_level(self._session.foot_level)
        await self.write_command(
            self._main(
                self._zone_code(massage.foot, massage.foot_wave, massage.foot_off, self._session.foot_level)
            )
        )

    async def massage_mode_step(self) -> None:
        """Advance the wave button: wave 1, wave 2, then off."""
        massage = self._massage()
        self._session.wave = (self._session.wave + 1) % 3
        if self._session.wave == 0:
            self._session.head_level = self._session.foot_level = 0
            code = massage.wave_off
        elif self._session.wave == 1:
            self._session.head_level = self._session.foot_level = 1
            code = massage.wave[0]
        else:
            code = massage.wave[1]
        await self.write_command(self._main(code))

    # ------------------------------------------------------------------
    # Lighting
    # ------------------------------------------------------------------

    async def lights_on(self) -> None:
        if not self.supports_lights:
            raise NotImplementedError(f"{self._model.name} has no light control")
        await self.write_command(self._main(LIGHT_RGBV, 0))

    async def lights_off(self) -> None:
        if not self.supports_lights:
            raise NotImplementedError(f"{self._model.name} has no light control")
        await self.write_command(self._main(LIGHT_OFF, 0))

    async def set_led_brightness(self, brightness: int) -> None:
        """Settings > LED light slider: white at ``brightness`` after 150 ms."""
        if not self.supports_led_brightness:
            raise NotImplementedError("This app hides the LED light setting for this model")
        if isinstance(brightness, bool) or not 0 <= brightness <= 255:
            raise ValueError("Light level must be 0-255")
        self._session.led_brightness = brightness
        self.forward_controller_state_update(LED_STATE_KEY, brightness)
        await self._sleep(LED_PREVIEW_DELAY_S)
        await self.write_command(self._serial.tap(LIGHT_RGBV, LED_WHITE | brightness))

    async def save_led_brightness(self) -> None:
        """Settings > LED light commit: store the current level after 500 ms."""
        if not self.supports_led_brightness:
            raise NotImplementedError("This app hides the LED light setting for this model")
        # The app persists the slider value before scheduling the write; it seeds
        # the slider and the next commit when the screen reopens.
        level = self._led_level
        self._coordinator.remember_remacro_led_level(self._model.model_id, level)
        await self._sleep(LED_SAVE_DELAY_S)
        await self.write_command(
            self._serial.tap(LIGHT_RGBV_SAVE, LED_WHITE | level)
        )


__all__ = ["APP_JEROMES", "APP_SLUMBERLAND", "APP_THE_BRICK", "RemacroController"]
