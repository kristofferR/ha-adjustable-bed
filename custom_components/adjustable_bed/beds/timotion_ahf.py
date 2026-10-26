"""TiMOTION AHF bed controller implementation.

The AHF app exposes thirteen held controls over one fixed BLE route. The
control labels below preserve the app's names without assigning physical
actuator or posture meanings.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError

from ..const import (
    TIMOTION_AHF_NOTIFY_CHAR_UUID,
    TIMOTION_AHF_SERVICE_UUID,
    TIMOTION_AHF_WRITE_CHAR_UUID,
)
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from bleak import BleakClient

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

STATUS_READINESS_TIMEOUT_SECONDS: Final = 8.0
_INITIAL_CONTROL_DELAY_SECONDS: Final = 0.1
_CONTROL_REPEAT_DELAY_SECONDS: Final = 0.1


class TiMOTIONAhfCommands:
    """AHF app-action bitmasks, grouped by packet byte."""

    CONTROL_1_UP = 0x01
    CONTROL_1_DOWN = 0x02
    CONTROL_2_UP = 0x04
    CONTROL_2_DOWN = 0x08
    CONTROL_3_UP = 0x10
    CONTROL_3_DOWN = 0x20

    CONTROL_4_UP = 0x01
    CONTROL_4_DOWN = 0x02
    CONTROL_5_UP = 0x04
    CONTROL_5_DOWN = 0x08
    NIGHT = 0x10
    LIGHT = 0x20
    CHAIR = 0x40


@dataclass(frozen=True, slots=True)
class _ControlAction:
    """One action label and its app-observed packet bit."""

    key: str
    label: str
    group1: int = 0
    group2: int = 0
    lock_bit: int | None = None
    icon: str = "mdi:gesture-tap"


_CONTROL_ACTIONS: Final = (
    _ControlAction("control_1_up", "Control 1 Up", group1=0x01, lock_bit=0, icon="mdi:arrow-up"),
    _ControlAction(
        "control_1_down", "Control 1 Down", group1=0x02, lock_bit=0, icon="mdi:arrow-down"
    ),
    _ControlAction("control_2_up", "Control 2 Up", group1=0x04, lock_bit=1, icon="mdi:arrow-up"),
    _ControlAction(
        "control_2_down", "Control 2 Down", group1=0x08, lock_bit=1, icon="mdi:arrow-down"
    ),
    _ControlAction("control_3_up", "Control 3 Up", group1=0x10, lock_bit=2, icon="mdi:arrow-up"),
    _ControlAction(
        "control_3_down", "Control 3 Down", group1=0x20, lock_bit=2, icon="mdi:arrow-down"
    ),
    _ControlAction("control_4_up", "Control 4 Up", group2=0x01, lock_bit=3, icon="mdi:arrow-up"),
    _ControlAction(
        "control_4_down", "Control 4 Down", group2=0x02, lock_bit=3, icon="mdi:arrow-down"
    ),
    _ControlAction("control_5_up", "Control 5 Up", group2=0x04, lock_bit=4, icon="mdi:arrow-up"),
    _ControlAction(
        "control_5_down", "Control 5 Down", group2=0x08, lock_bit=4, icon="mdi:arrow-down"
    ),
    _ControlAction("night", "Night", group2=0x10, lock_bit=5, icon="mdi:weather-night"),
    _ControlAction("light", "Light", group2=0x20, icon="mdi:lightbulb-outline"),
    _ControlAction("chair", "Chair", group2=0x40, lock_bit=6, icon="mdi:chair-rolling"),
)
_CONTROL_ACTION_BY_KEY: Final = {action.key: action for action in _CONTROL_ACTIONS}
_BUTTON_PREFIX: Final = "timotion_ahf_"
_STATUS_NOT_READY_MESSAGE: Final = (
    "TiMOTION AHF controls need a valid status frame. Wait up to 8 seconds after "
    "connecting, then check the status characteristic's read/notify path and reconnect. "
    "The neutral STOP control remains available."
)


def build_timotion_ahf_command(group1: int = 0, group2: int = 0) -> bytes:
    """Build an 11-byte neutral-based AHF packet."""
    return bytes([0xDD, 0xDD, 0xFF, group1, group1, group2, group2, 0, 0, 0, 0])


class TiMOTIONAhfController(BedController):
    """Controller for the fixed TiMOTION AHF app route."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize app-control and session-local status state."""
        super().__init__(coordinator)
        self._ahf_write_with_response: bool | None = None
        self._write_mode_initialized = False
        self._write_mode_error: str | None = None
        self._status_session_client: BleakClient | None = None
        self._status_generation = 0
        self._status_event = asyncio.Event()
        self._notify_started = False
        self._notify_error: str | None = None
        self._read_error: str | None = None
        self._status_ready = False
        self._status_state = "waiting"
        self._status_error: str | None = None
        self._feature_mask: int | None = None
        self._lamp_display_code: int | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the fixed NUS write characteristic UUID."""
        return TIMOTION_AHF_WRITE_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        """Keep status notifications active even when angle sensing is disabled."""
        return True

    @property
    def status_ready(self) -> bool:
        """Whether this BLE session supplied a valid AHF status frame."""
        return self._status_ready

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_memory_presets(self) -> bool:
        return False

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_motor_control(self) -> bool:
        """The app labels commands but does not identify physical motor axes."""
        return False

    @property
    def position_number_specs(self) -> tuple[()]:
        """AHF status contains no position values."""
        return ()

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Do not infer physical axes from app action indices."""
        return ()

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Remove the physical labels exposed by older AHF versions."""
        return frozenset({"back", "legs", "head", "feet", "pillow"})

    @property
    def held_control_options(self) -> tuple[str, ...]:
        """Return all app controls with a defined held-command lifecycle."""
        return tuple(action.key for action in _CONTROL_ACTIONS)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        """Expose the app's thirteen literal controls as stable named actions."""
        return tuple(
            ControllerButtonSpec(
                key=f"{_BUTTON_PREFIX}{action.key}",
                name=action.label,
                press_fn=_press_action(action.key),
                icon=action.icon,
            )
            for action in _CONTROL_ACTIONS
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        """Expose status readiness and the two raw app-reported status bytes."""
        return (
            ControllerStateSensorSpec(
                key="timotion_ahf_status",
                translation_key="timotion_ahf_status",
                state_key="timotion_ahf_status",
                icon="mdi:bluetooth",
                attribute_keys=("timotion_ahf_status_error",),
            ),
            ControllerStateSensorSpec(
                key="timotion_ahf_lock_mask",
                translation_key="timotion_ahf_lock_mask",
                state_key="timotion_ahf_lock_mask",
                icon="mdi:lock-outline",
            ),
            ControllerStateSensorSpec(
                key="timotion_ahf_lamp_display_code",
                translation_key="timotion_ahf_lamp_display_code",
                state_key="timotion_ahf_lamp_display_code",
                icon="mdi:lightbulb-outline",
            ),
        )

    def controller_button_available(self, key: str) -> bool:
        """Require current status and an unlocked app action for its button."""
        if not key.startswith(_BUTTON_PREFIX):
            return True
        action = _CONTROL_ACTION_BY_KEY.get(key.removeprefix(_BUTTON_PREFIX))
        if action is None:
            return False
        # The coordinator reconnects on press, so a cached offline controller
        # must not make its app actions permanently unavailable.
        if not self._session_connected:
            return True
        return self._action_enabled(action)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        """Preflight AHF status and lock state before a bounded held action."""
        if duration_ms <= 0:
            raise ValueError("TiMOTION AHF hold duration must be greater than zero")
        action = _CONTROL_ACTION_BY_KEY.get(control)
        if action is None:
            raise ValueError(f"Unsupported TiMOTION AHF held control: {control}")
        # Service preflight precedes on-demand connection. Session-owned status
        # and locks are checked again by hold_control once the live link is ready.
        if self._session_connected:
            self._validate_action(action)

    @property
    def _session_connected(self) -> bool:
        """Whether this controller currently owns a connected BLE session."""
        client = self.client
        return client is not None and client.is_connected

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write using only a mode advertised by the discovered characteristic."""
        response = self._refresh_write_mode()
        await self._write_gatt_with_retry(
            TIMOTION_AHF_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=response,
        )

    def _refresh_write_mode(self) -> bool:
        """Select write-with-response when supported, otherwise WWR."""
        if self._write_mode_initialized:
            if self._ahf_write_with_response is None:
                raise BleakError(self._write_mode_error or "AHF write mode is unavailable")
            return self._ahf_write_with_response

        client = self.client
        if client is None or client.services is None:
            raise ConnectionError("TiMOTION AHF GATT services are not available")

        service = client.services.get_service(TIMOTION_AHF_SERVICE_UUID)
        if service is None:
            raise BleakError(f"TiMOTION AHF service {TIMOTION_AHF_SERVICE_UUID} was not discovered")

        characteristic = next(
            (
                char
                for char in service.characteristics
                if str(char.uuid).lower() == TIMOTION_AHF_WRITE_CHAR_UUID.lower()
            ),
            None,
        )
        if characteristic is None:
            raise BleakError(
                f"TiMOTION AHF write characteristic {TIMOTION_AHF_WRITE_CHAR_UUID} "
                "was not discovered"
            )

        properties = {str(prop).lower() for prop in characteristic.properties}
        can_write_with_response = "write" in properties
        can_write_without_response = "write-without-response" in properties
        if not can_write_with_response and not can_write_without_response:
            self._write_mode_initialized = True
            self._write_mode_error = (
                "TiMOTION AHF write characteristic supports neither write nor "
                "write-without-response"
            )
            raise BleakError(self._write_mode_error)

        self._ahf_write_with_response = can_write_with_response
        self._write_mode_initialized = True
        _LOGGER.debug(
            "TiMOTION AHF write mode: response=%s (properties=%s)",
            self._ahf_write_with_response,
            characteristic.properties,
        )
        return self._ahf_write_with_response

    async def _send_stop(self) -> None:
        """Send three neutral frames with a fresh cancellation context."""
        cleanup_cancel = asyncio.Event()
        neutral = build_timotion_ahf_command()
        for index in range(3):
            await self.write_command(neutral, cancel_event=cleanup_cancel)
            if index < 2:
                await self._sleep(_CONTROL_REPEAT_DELAY_SECONDS)

    async def _send_action(self, action: _ControlAction) -> None:
        """Run one configured finite button pulse and always release it."""
        self._validate_action(action)
        command = build_timotion_ahf_command(action.group1, action.group2)
        try:
            pulse_count, pulse_delay_ms = self.motor_pulse_settings()
            await self.write_command(
                command,
                repeat_count=pulse_count,
                repeat_delay_ms=pulse_delay_ms,
            )
        finally:
            await self._send_stop()

    async def hold_control(self, control: str, duration_ms: int) -> None:
        """Hold an app action inside HA's requested bound, then send STOP."""
        self.validate_hold_control(control, duration_ms)
        action = _CONTROL_ACTION_BY_KEY[control]
        command = build_timotion_ahf_command(action.group1, action.group2)
        deadline = self._monotonic() + duration_ms / 1000
        cancel_event = self._coordinator.cancel_command
        timeout = asyncio.timeout(duration_ms / 1000)
        try:
            try:
                async with timeout:
                    initial_delay = min(_INITIAL_CONTROL_DELAY_SECONDS, duration_ms / 1000)
                    await self._sleep(initial_delay)
                    while self._monotonic() < deadline:
                        self._validate_action(action)
                        if cancel_event.is_set():
                            break
                        await self.write_command(command, cancel_event=cancel_event)
                        remaining = deadline - self._monotonic()
                        if remaining <= 0:
                            break
                        await self._sleep(min(_CONTROL_REPEAT_DELAY_SECONDS, remaining))
            except TimeoutError:
                if not timeout.expired():
                    raise
        finally:
            await self._send_stop()

    def _monotonic(self) -> float:
        """Return the event-loop clock used to bound a held action."""
        return asyncio.get_running_loop().time()

    async def _sleep(self, seconds: float) -> None:
        """Sleep between held writes; tests replace this with a controlled clock."""
        await asyncio.sleep(seconds)

    def _validate_action(self, action: _ControlAction) -> None:
        """Reject stale status or an app-reported lock before writing a control."""
        if not self._status_ready:
            raise ValueError(self._status_error or _STATUS_NOT_READY_MESSAGE)
        if action.lock_bit is not None and self._feature_mask is not None:
            if self._feature_mask & (1 << action.lock_bit):
                raise ValueError(
                    f"TiMOTION AHF {action.label} is disabled by status lock bit "
                    f"{action.lock_bit} (mask 0x{self._feature_mask:02X})"
                )

    def _action_enabled(self, action: _ControlAction) -> bool:
        """Return whether status is ready and the app has not disabled the action."""
        if not self._status_ready:
            return False
        return (
            action.lock_bit is None
            or self._feature_mask is None
            or not bool(self._feature_mask & (1 << action.lock_bit))
        )

    def _is_valid_notification(self, data: bytes) -> bool:
        """Validate the complete 15-byte AHF status frame."""
        if len(data) != 15 or data[0] != 0x9D:
            return False
        return (sum(data[2:14]) & 0x7F) == data[14]

    def _handle_notification(
        self,
        sender: BleakGATTCharacteristic,
        data: bytearray,
        *,
        generation: int | None = None,
    ) -> None:
        """Accept a notification only from the active status session."""
        if generation is not None and generation != self._status_generation:
            return
        raw = bytes(data)
        self.forward_raw_notification(TIMOTION_AHF_NOTIFY_CHAR_UUID, raw)
        self._process_status_frame(raw)

    def _process_status_frame(self, data: bytes) -> None:
        """Publish valid app status and queue STOP if the lamp display changes."""
        if not self._is_valid_notification(data):
            return

        old_lamp_code = self._lamp_display_code
        self._feature_mask = data[2]
        self._lamp_display_code = data[3]
        self._status_ready = True
        self._status_state = "ready"
        self._status_error = None
        self._read_error = None
        self._notify_error = None
        self._status_event.set()
        self.forward_controller_state_updates(
            {
                "timotion_ahf_status": self._status_state,
                "timotion_ahf_status_error": None,
                "timotion_ahf_lock_mask": self._feature_mask,
                "timotion_ahf_lamp_display_code": self._lamp_display_code,
            }
        )
        _LOGGER.debug(
            "TiMOTION AHF status: lock_mask=0x%02X lamp_display_code=%d",
            self._feature_mask,
            self._lamp_display_code,
        )
        if old_lamp_code is not None and old_lamp_code != self._lamp_display_code:
            self._queue_preempting_stop()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe and read status, then wait at most eight seconds for a valid frame."""
        client = self.client
        if client is None or not client.is_connected:
            self._set_status_timeout("No connected BLE session is available for AHF status")
            return

        if self._status_session_client is not client:
            self._begin_status_session(client)
        generation = self._status_generation
        if self._status_ready:
            return

        deadline = self._monotonic() + STATUS_READINESS_TIMEOUT_SECONDS
        read_task: asyncio.Task[None] | None = None
        status_task: asyncio.Task[bool] | None = None
        try:
            if not self._notify_started:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise TimeoutError
                try:
                    await asyncio.wait_for(
                        client.start_notify(
                            TIMOTION_AHF_NOTIFY_CHAR_UUID,
                            lambda sender, data: self._handle_notification(
                                sender, data, generation=generation
                            ),
                        ),
                        timeout=remaining,
                    )
                    self._notify_started = True
                except TimeoutError:
                    self._notify_error = "Status notification subscription timed out"
                    raise
                except Exception as err:  # noqa: BLE001 - read can still establish status
                    self._notify_error = f"Status notification subscription failed: {err}"
                    _LOGGER.warning("Failed to start TiMOTION AHF status notifications: %s", err)

            if (
                self._status_ready
                or generation != self._status_generation
                or not client.is_connected
            ):
                return

            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise TimeoutError

            async def read_initial_status() -> None:
                try:
                    initial_status = await client.read_gatt_char(TIMOTION_AHF_NOTIFY_CHAR_UUID)
                except Exception as err:  # noqa: BLE001 - a later valid notification may succeed
                    self._read_error = f"Initial status read failed: {err}"
                    _LOGGER.debug("Failed to read initial TiMOTION AHF status: %s", err)
                else:
                    if generation == self._status_generation and self.client is client:
                        self._process_status_frame(bytes(initial_status))

            read_task = asyncio.create_task(read_initial_status())
            status_task = asyncio.create_task(self._status_event.wait())
            done, _ = await asyncio.wait(
                (read_task, status_task),
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # A valid notification wins over a read that is still pending. Cancel
            # only the initial read, leaving the established subscription active.
            if status_task in done:
                if self._status_ready or generation != self._status_generation:
                    return
            if read_task in done:
                await read_task
                if (
                    self._status_ready
                    or generation != self._status_generation
                    or not client.is_connected
                ):
                    return
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise TimeoutError
                await asyncio.wait_for(status_task, timeout=remaining)
            else:
                raise TimeoutError
        except TimeoutError:
            if generation == self._status_generation and not self._status_ready:
                detail = "; ".join(
                    reason for reason in (self._notify_error, self._read_error) if reason
                )
                message = (
                    "No valid 15-byte TiMOTION AHF status frame arrived within 8 seconds. "
                    "Check that the bed is nearby and the status characteristic supports "
                    "the required read/notify path, then reconnect."
                )
                if detail:
                    message = f"{message} {detail}"
                self._set_status_timeout(message)
        finally:
            if read_task is not None and not read_task.done():
                read_task.cancel()
            if status_task is not None and not status_task.done():
                status_task.cancel()
            if read_task is not None:
                await asyncio.gather(read_task, return_exceptions=True)
            if status_task is not None:
                await asyncio.gather(status_task, return_exceptions=True)

    async def stop_notify(self) -> None:
        """Stop the AHF status subscription when the owning session closes."""
        client = self.client
        if client is not None and client.is_connected and self._notify_started:
            with contextlib.suppress(BleakError):
                await client.stop_notify(TIMOTION_AHF_NOTIFY_CHAR_UUID)
        self._notify_started = False

    def _begin_status_session(self, client: BleakClient) -> None:
        """Clear session-owned readiness and raw status before connecting anew."""
        self._status_session_client = client
        self._status_generation += 1
        self._status_event = asyncio.Event()
        self._notify_started = False
        self._notify_error = None
        self._read_error = None
        self._status_ready = False
        self._status_state = "waiting"
        self._status_error = None
        self._feature_mask = None
        self._lamp_display_code = None
        self.forward_controller_state_updates(
            {
                "timotion_ahf_status": self._status_state,
                "timotion_ahf_status_error": None,
                "timotion_ahf_lock_mask": None,
                "timotion_ahf_lamp_display_code": None,
            }
        )

    def _set_status_timeout(self, message: str) -> None:
        """Publish an actionable unready state without treating BLE as disconnected."""
        self._status_ready = False
        self._status_state = "timed_out"
        self._status_error = message
        self.forward_controller_state_updates(
            {
                "timotion_ahf_status": self._status_state,
                "timotion_ahf_status_error": message,
            }
        )
        _LOGGER.warning("%s", message)

    def _queue_preempting_stop(self) -> None:
        """Cancel this controller's active action before scheduling serialized STOP."""
        self._coordinator.request_command_cancel()
        self._coordinator.hass.async_create_task(
            self._coordinator.async_stop_command(),
            name=f"adjustable_bed_timotion_ahf_status_stop_{self._coordinator.address}",
        )

    def on_disconnect(self) -> None:
        """Invalidate status readiness and any callback from the old BLE session."""
        self._status_generation += 1
        self._status_session_client = None
        self._status_event.set()
        self._notify_started = False
        self._notify_error = None
        self._read_error = None
        self._status_ready = False
        self._status_state = "waiting"
        self._status_error = None
        self._feature_mask = None
        self._lamp_display_code = None
        self._ahf_write_with_response = None
        self._write_mode_initialized = False
        self._write_mode_error = None
        self.forward_controller_state_updates(
            {
                "timotion_ahf_status": self._status_state,
                "timotion_ahf_status_error": None,
                "timotion_ahf_lock_mask": None,
                "timotion_ahf_lamp_display_code": None,
            }
        )

    # The shared abstract controller contract requires legacy axis methods, but
    # their physical meanings are not known for this app. Only neutral STOP is
    # safe to expose through those compatibility methods.
    async def move_head_up(self) -> None:
        raise NotImplementedError("Use the app-labelled TiMOTION AHF controls")

    async def move_head_down(self) -> None:
        raise NotImplementedError("Use the app-labelled TiMOTION AHF controls")

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        raise NotImplementedError("Use the app-labelled TiMOTION AHF controls")

    async def move_back_down(self) -> None:
        raise NotImplementedError("Use the app-labelled TiMOTION AHF controls")

    async def move_back_stop(self) -> None:
        await self._send_stop()

    async def move_legs_up(self) -> None:
        raise NotImplementedError("Use the app-labelled TiMOTION AHF controls")

    async def move_legs_down(self) -> None:
        raise NotImplementedError("Use the app-labelled TiMOTION AHF controls")

    async def move_legs_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        raise NotImplementedError("Use the app-labelled TiMOTION AHF controls")

    async def move_feet_down(self) -> None:
        raise NotImplementedError("Use the app-labelled TiMOTION AHF controls")

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def stop_all(self) -> None:
        """Send the protocol's neutral frame for cancellation and cleanup."""
        await self._send_stop()

    async def preset_flat(self) -> None:
        raise NotImplementedError("TiMOTION AHF does not expose a flat preset")

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError(f"TiMOTION AHF does not expose memory slot {memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError(f"TiMOTION AHF does not expose memory slot {memory_num}")


def _press_action(key: str) -> Callable[[BedController], Coroutine[Any, Any, None]]:
    """Return the typed entity dispatcher for one AHF app action."""

    async def press(controller: BedController) -> None:
        if not isinstance(controller, TiMOTIONAhfController):
            raise HomeAssistantError("The active controller is not TiMOTION AHF")
        action = _CONTROL_ACTION_BY_KEY[key]
        try:
            await controller._send_action(action)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    return press
