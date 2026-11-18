"""Dawn House's session and native HA surfaces over the shared Keeson runtime."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ...app_session import app_session
from ...card import CARD_LIGHTING, CARD_MASSAGE_TIMER, CARD_PRESETS, CARD_UTILITY
from ...codec import keeson as codec
from ...command_scheduler import CommandContext, current_command_context
from ...const import (
    CONF_AGINGPLACE_BED_MODE,
    CONF_AGINGPLACE_BED_SIDE,
    CONF_AGINGPLACE_SELECTED_SIDE,
    CONF_BLE_DEVICE_NAME,
)
from ...profiles import agingplace as app
from ..base import BedController
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from .agingplace_state import CONNECTED, NUMBERS, PRESENT, TEXT, Observations, integer
from .controller import KeesonController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _AutomaticIntent:
    """An admitted start's Flat obligation, never a live device capability."""

    generation: int = 0
    action: str | None = None

    def start(self, action: str) -> int:
        self.generation += 1
        self.action = action
        return self.generation

    def clear(self, generation: int) -> bool:
        if generation != self.generation:
            return False
        self.action = None
        return True


async def _drain(operation: Awaitable[None]) -> None:
    """Let an admitted write finish before cancellation can start its release."""
    task = asyncio.ensure_future(operation)
    interrupted: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.wait((task,))
        except asyncio.CancelledError as err:
            interrupted = err
    task.result()
    if interrupted is not None:
        raise interrupted


def _action(name: str) -> MotorCommandCallable:
    async def run(controller: BedController) -> None:
        await cast(AgingPlaceController, controller).run_action(name)

    return run


def _stop(controller: BedController):
    return controller.stop_all()


class AgingPlaceController(KeesonController):
    """One selected local identity, one serialized key stream, one session owner."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        device_id: str | None = None,
        mode: int | None = None,
        bed_side: int = 0,
        selected_side: int = 0,
    ) -> None:
        super().__init__(coordinator, variant="json")
        self.profile = app.PROFILE
        self.device_id = device_id
        self._mode = mode
        self._bed_side = bed_side
        self._selected_side = selected_side
        self.observations = Observations(mode=mode, bed_side=bed_side, selected_side=selected_side)
        self._epoch = 0
        self._ready_client: BleakClient | None = None
        self._indicate: BleakGATTCharacteristic | None = None
        self._automatic = app_session(
            coordinator.hass, coordinator.address, ("agingplace", app.PROFILE.key), _AutomaticIntent
        )
        self._diagnostic_generation: int | None = None
        self._diagnostic_timeout: asyncio.TimerHandle | None = None
        self._diagnostic_quiet: asyncio.TimerHandle | None = None
        self._cleanup: tuple[BleakClient, int, CommandContext] | None = None

    @property
    def _flat_cancel_active(self) -> bool:
        return self._automatic.action is not None

    @property
    def supports_single_address_pairing(self) -> bool:
        return False  # incoming si is not a command-side selector

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_massage_toggle_control(self) -> bool:
        return True

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        return False

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return False

    @property
    def supports_massage_timer(self) -> bool:
        return False

    @property
    def supports_massage_off_control(self) -> bool:
        return False

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(name for name, action in app.ACTIONS.items() if action.held)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return app.PROFILE.hold or (5, app.REFRESH_MS)

    def _role(self, uuid: str) -> BleakGATTCharacteristic:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Dawn House is disconnected")
        transport = codec.TRANSPORTS["json"]
        for service in client.services:
            if service.uuid.lower() == transport.service_uuid:
                characteristic = service.get_characteristic(uuid)
                if characteristic is not None:
                    return characteristic
        raise ConnectionError(f"Dawn House requires {uuid} on {transport.service_uuid}")

    def _current(self, client: BleakClient, epoch: int) -> None:
        if (
            self.client is not client
            or self._ready_client is not client
            or self._epoch != epoch
            or not client.is_connected
        ):
            raise ConnectionError("Dawn House command belongs to a retired session")

    async def async_on_connect(self, session: ControllerSession) -> None:
        await asyncio.sleep(app.CONNECT_WAIT)
        if not session.is_current():
            raise ConnectionError("Dawn House connection changed during startup")
        await session.async_start_notify()

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        # Device-info is an explicit JSON query, not generic DIS reads or a binary startup write.
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None:
            raise ConnectionError("Dawn House is disconnected")
        if self._ready_client is client:
            return
        write = self._role(codec.TRANSPORTS["json"].write_uuid)
        if not {"write", "write-without-response"}.intersection(write.properties):
            raise ConnectionError("Dawn House requires a writable B002 characteristic")
        char = self._role(codec.TRANSPORTS["json"].notify_uuid)
        if "indicate" not in char.properties:
            raise ConnectionError("Dawn House requires B004 indications")
        self._epoch += 1
        epoch = self._epoch
        self._ready_client = None
        self._diagnostic_generation = (
            self._automatic.generation if self._automatic.action == "diagnostic" else None
        )
        # Bleak has no portable requestMtu(260). BlueZ exposes acquisition;
        # proxy/platform backends negotiate themselves. Never invent ATT bytes.
        backend = getattr(client, "_backend", None)
        acquire = getattr(backend, "_acquire_mtu", None)
        # BlueZ's AcquireWrite/AcquireNotify cannot use write-only or indicate-only roles.
        if callable(acquire) and any(
            {"write-without-response", "notify"}.intersection(characteristic.properties)
            for service in client.services
            for characteristic in service.characteristics
        ):
            await cast(Callable[[], Awaitable[object]], acquire)()
        _LOGGER.debug(
            "Dawn House app requests MTU %d; negotiated %s, literal chunk size %d",
            app.REQUESTED_MTU,
            client.mtu_size,
            app.CHUNK_BYTES,
        )
        self._indicate = char

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if self._epoch == epoch and self.client is client and self._indicate is char:
                self._receive(sender, data)

        try:
            await client.start_notify(char, receive, force_indicate=True)
            await asyncio.sleep(app.INDICATION_WAIT)
            if self.client is not client or self._epoch != epoch or not client.is_connected:
                raise ConnectionError("Dawn House connection changed while subscribing")
            self._ready_client = client
        except BaseException:
            self._indicate = None
            self._epoch += 1
            raise

    async def stop_notify(self) -> None:
        char, self._indicate = self._indicate, None
        client, self._ready_client = self._ready_client, None
        self._epoch += 1
        self._diagnostic_generation = None
        self._clear_timers()
        if char is not None and client is not None and client.is_connected:
            await client.stop_notify(char)

    def _clear_timers(self) -> None:
        for timer in (self._diagnostic_timeout, self._diagnostic_quiet):
            if timer is not None:
                timer.cancel()
        self._diagnostic_timeout = self._diagnostic_quiet = None

    def on_disconnect(self) -> None:
        self._ready_client = None
        self._indicate = None
        self._epoch += 1
        self._diagnostic_generation = None
        self._cleanup = None
        self._clear_timers()
        self.observations = Observations(
            mode=self._mode, bed_side=self._bed_side, selected_side=self._selected_side
        )
        self.forward_controller_state_updates(
            *(key(None) for key in NUMBERS.values()),
            *(key(None) for key in TEXT.values()),
            *(key(None) for key in PRESENT.values()),
            *(key(None) for key in CONNECTED.values()),
        )

    async def _send(
        self, command: bytes, client: BleakClient, epoch: int, cancel: asyncio.Event
    ) -> None:
        self._current(client, epoch)
        char = self._role(codec.TRANSPORTS["json"].write_uuid)
        failure: BleakError | None = None
        for start in range(0, len(command), app.CHUNK_BYTES):
            try:
                await self._write_gatt_with_retry(
                    char.uuid,
                    command[start : start + app.CHUNK_BYTES],
                    cancel_event=cancel,
                    response="write" in char.properties,
                    characteristic=char,
                    expected_client=client,
                    before_write=lambda: self._current(client, epoch),
                )
            except BleakError as err:
                # FastBle advances the split queue on either callback, without retry.
                failure = failure or err
        if failure is not None:
            raise failure

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 200,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        client = self._ready_client
        if client is None:
            raise ConnectionError("Dawn House indication session is not ready")
        epoch = self._epoch
        cancel = cancel_event or self._coordinator.cancel_command
        for index in range(repeat_count):
            if cancel.is_set():
                return
            await _drain(self._send(command, client, epoch, cancel))
            if index + 1 < repeat_count:
                await self._wait(cancel, repeat_delay_ms / 1000)

    @staticmethod
    async def _wait(cancel: asyncio.Event, delay: float) -> None:
        if delay <= 0 or cancel.is_set():
            return
        try:
            async with asyncio.timeout(delay):
                await cancel.wait()
        except TimeoutError:
            pass

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or duration_ms <= 0
        ):
            raise ValueError("Choose a supported Dawn House held control and positive duration")
        client, epoch = self._ready_client, self._epoch
        if client is None:
            raise ConnectionError("Dawn House indication session is not ready")
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return
        self._cleanup = None
        context = current_command_context()
        if context is not None:
            context.cleanup_stop_sent = False
        duration = self.leased_hold_ms(duration_ms) / 1000
        deadline = asyncio.get_running_loop().time() + duration
        frame = app.ACTIONS[control].frame(self.device_id)
        try:
            while not cancel.is_set() and asyncio.get_running_loop().time() < deadline:
                await self.write_command(frame)
                await self._wait(
                    cancel, min(app.REFRESH_MS / 1000, deadline - asyncio.get_running_loop().time())
                )
        finally:
            # Drain an in-flight refresh before the independent zero release.
            # A retired link never borrows a replacement client for cleanup.
            if (
                self._ready_client is client
                and self.client is client
                and self._epoch == epoch
                and client.is_connected
            ):

                async def release() -> None:
                    await self._send(
                        app.ACTIONS["release"].frame(self.device_id), client, epoch, asyncio.Event()
                    )
                    if context is not None:
                        context.cleanup_stop_sent = True
                        self._cleanup = (client, epoch, context)

                await _drain(release())

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if direction is None:
            await self.stop_all()
            return
        prefix = {"head": "head", "feet": "foot", "bed": "bed"}.get(motor)
        if prefix is None:
            raise NotImplementedError("Dawn House has no independent command for that axis")
        await self.hold_control(f"{prefix}_{'up' if direction else 'down'}", 1000)

    def _build_command(self, command_value: int) -> bytes:
        action = next(
            (action for action in app.ACTIONS.values() if action.word == command_value), None
        )
        if action is None:
            raise NotImplementedError("No source-proven Dawn House command")
        return action.frame(self.device_id)

    async def run_action(self, name: str) -> None:
        if name not in app.ACTIONS:
            raise ValueError("Unknown Dawn House action")
        action = app.ACTIONS[name]
        if action.held:
            await self.hold_control(name, 1000)
            return
        client, epoch = self._ready_client, self._epoch
        if client is None:
            raise ConnectionError("Dawn House indication session is not ready")
        self._current(client, epoch)
        self._cleanup = None
        generation = self._automatic.generation
        if name in ("circulation", "sleep", "relax_cycle", "diagnostic"):
            # An admitted start may transmit before cancellation is delivered.
            # Its STOP must still use Flat after the in-flight write drains.
            generation = self._automatic.start(name)
        if name == "diagnostic":
            self._clear_timers()
            self.observations.maxima = dict.fromkeys(self.observations.maxima, 0)
            self._diagnostic_generation = generation
            self.forward_controller_state_updates(TEXT["diagnostic_status"]("waiting"))

            def timeout() -> None:
                if (
                    self._epoch == epoch
                    and self._ready_client is client
                    and self._automatic.generation == generation
                    and self._automatic.action == "diagnostic"
                ):
                    self._diagnostic_timeout = None
                    self.forward_controller_state_updates(TEXT["diagnostic_status"]("timeout"))

            self._diagnostic_timeout = asyncio.get_running_loop().call_later(
                app.SELF_CHECK_TIMEOUT, timeout
            )
        await self.write_command(action.frame(self.device_id))
        self._current(client, epoch)
        if name == "flat" and self._automatic.clear(generation):
            self._diagnostic_generation = None
            self._clear_timers()

    async def stop_all(self) -> None:
        context = current_command_context()
        if self._cleanup is not None and context is not None:
            client, epoch, owner = self._cleanup
            if (
                client is self._ready_client
                and epoch == self._epoch
                and not self._flat_cancel_active
                and owner.cleanup_stop_sent
                and (owner is context or any(owner is old for old in context.preempted_contexts))
            ):
                owner.cleanup_stop_sent = False
                self._cleanup = None
                return
        name = "flat" if self._flat_cancel_active else "release"
        client, epoch = self._ready_client, self._epoch
        if client is None:
            raise ConnectionError("Dawn House indication session is not ready")
        self._current(client, epoch)
        generation = self._automatic.generation
        await self.write_command(
            app.ACTIONS[name].frame(self.device_id), cancel_event=asyncio.Event()
        )
        self._current(client, epoch)
        if self._automatic.clear(generation):
            self._diagnostic_generation = None
            self._clear_timers()

    async def _preset(self, preset: str) -> None:
        if preset not in self.profile.presets:
            raise NotImplementedError("Dawn House has no such preset")
        await self.run_action(preset)

    async def lights_toggle(self) -> None:
        await self.run_action("light")

    async def massage_toggle(self) -> None:
        await self.run_action("massage")

    async def set_setting(self, name: str, value: int) -> None:
        client, epoch = self._ready_client, self._epoch
        if client is None:
            raise ConnectionError("Dawn House indication session is not ready")
        await self.write_command(app.setting(name, value, self.device_id))
        self._current(client, epoch)
        self.forward_controller_state_updates(NUMBERS[name](value))

    async def query_device_info(self) -> None:
        await self.write_command(app.device_info(self.device_id))

    def _receive(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        raw = bytes(data)
        payload = codec.parse_json_indication(raw)
        if payload is None:
            self.forward_raw_notification(codec.TRANSPORTS["json"].notify_uuid, raw)
            return
        if "ssid" in payload and "pswd" in payload:
            # Provisioning remains excluded. Its observed shared link invalidation
            # still retires BED admission; HA owns reconnect and resubscription.
            client = self._ready_client or self.client
            self.on_disconnect()
            if client is not None and client.is_connected:
                self._coordinator.hass.async_create_task(
                    client.disconnect(), "Dawn House shared link invalidation"
                )
            return
        self.forward_raw_notification(codec.TRANSPORTS["json"].notify_uuid, raw)
        updates = self.observations.consume(payload)
        if "chkStatu" in payload:
            updates.append(TEXT["diagnostic_raw"](json.dumps(payload, separators=(",", ":"))))
            if self._diagnostic_quiet is not None:
                self._diagnostic_quiet.cancel()
            flag = integer(payload, "chkStatu")
            if flag >= 49152:
                self._clear_timers()
                if self._diagnostic_generation is not None:
                    self._automatic.clear(self._diagnostic_generation)
                    self._diagnostic_generation = None
            elif flag >= 1:
                epoch = self._epoch
                generation = self._automatic.generation

                def aggregate() -> None:
                    if self._epoch == epoch and self._automatic.generation == generation:
                        self.forward_controller_state_updates(TEXT["diagnostic_status"]("observed"))

                self._diagnostic_quiet = asyncio.get_running_loop().call_later(
                    app.DIAGNOSTIC_QUIET, aggregate
                )
        self.forward_controller_state_updates(*updates)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key,
                translation,
                _action(f"{prefix}_up"),
                _action(f"{prefix}_down"),
                _stop,
                hold=ControllerMotorHoldSpec(
                    f"{prefix}_up", f"{prefix}_down", stop_scope="side", press_is_native=True
                ),
            )
            for key, translation, prefix in (
                ("back", "keeson_back", "head"),
                ("legs", "keeson_legs", "foot"),
                ("bed_height", "bed_height", "bed"),
            )
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        names = ("in", "out", "read", "circulation", "sleep", "relax_cycle", "diagnostic")
        specs = tuple(
            ControllerButtonSpec(
                f"agingplace_{name}",
                app.ACTIONS[name].label,
                _action(name),
                translation_key=f"agingplace_{name}",
                hold=ControllerHoldSpec(name) if app.ACTIONS[name].held else None,
                card=CARD_PRESETS if name == "read" else CARD_UTILITY,
            )
            for name in names
        )

        async def query(controller: BedController) -> None:
            await cast(AgingPlaceController, controller).query_device_info()

        return (
            *specs,
            ControllerButtonSpec(
                "agingplace_cancel",
                "Cancel cycle or self check",
                _action("flat"),
                translation_key="agingplace_cancel",
            ),
            ControllerButtonSpec(
                "agingplace_device_info",
                "Read device information",
                query,
                translation_key="agingplace_device_info",
                cancel_movement=False,
                scheduler_resource="configuration",
            ),
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        def setter(name: str):
            async def set_value(controller: BedController, value: float) -> None:
                if not float(value).is_integer():
                    raise ValueError("Dawn House settings use whole values")
                await cast(AgingPlaceController, controller).set_setting(name, int(value))

            return set_value

        return tuple(
            ControllerNumberSpec(
                f"agingplace_{name}",
                f"agingplace_{name}",
                NUMBERS[name],
                low,
                high,
                1,
                setter(name),
                native_unit_of_measurement=unit,
                card=card,
            )
            for name, low, high, unit, card in (
                ("brightness", 0, 100, "%", CARD_LIGHTING),
                ("massage_minutes", 1, 60, "min", CARD_MASSAGE_TIMER),
                ("motion_minutes", 1, 30, "min", CARD_LIGHTING),
            )
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        settings = {"brightness", "massage_minutes", "motion_minutes"}
        return tuple(
            ControllerStateSensorSpec(
                f"agingplace_{name}",
                f"agingplace_{name.lower()}",
                key,
                "mdi:bed",
                attribute_keys=tuple(TEXT.values()) if name == "version" else (),
            )
            for name, key in NUMBERS.items()
            if name not in settings
        ) + tuple(
            ControllerStateSensorSpec(
                f"agingplace_{name}",
                f"agingplace_{name.lower()}",
                key,
                "mdi:information-outline",
                attribute_keys=(TEXT["diagnostic_raw"],) if name == "diagnostic_status" else (),
            )
            for name, key in TEXT.items()
            if name != "diagnostic_raw"
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return tuple(
            ControllerStateBinarySensorSpec(
                f"agingplace_{name}_occupancy", f"agingplace_{name}_occupancy", key, "mdi:bed"
            )
            for name, key in PRESENT.items()
        ) + tuple(
            ControllerStateBinarySensorSpec(
                f"agingplace_{name}_connected",
                f"agingplace_{name}_connected",
                key,
                "mdi:connection",
            )
            for name, key in CONNECTED.items()
        )


async def build_controller(ctx: BuildContext) -> BedController:
    mode = ctx.data.get(CONF_AGINGPLACE_BED_MODE, "auto")
    bed_side = ctx.data.get(CONF_AGINGPLACE_BED_SIDE, 0)
    selected_side = ctx.data.get(CONF_AGINGPLACE_SELECTED_SIDE, 0)
    if (
        str(mode) not in ("auto", "0", "1", "2")
        or type(bed_side) is not int
        or bed_side not in (0, 1, 2)
        or type(selected_side) is not int
        or selected_side not in (0, 1)
    ):
        raise ValueError("Choose a valid Dawn House sensor display and telemetry side")
    return AgingPlaceController(
        ctx.coordinator,
        device_id=app.selected_device_id(
            ctx.data.get(CONF_BLE_DEVICE_NAME), ctx.live_device_name or ctx.advertisement_name
        ),
        mode=None if mode == "auto" else int(mode),
        bed_side=bed_side,
        selected_side=selected_side,
    )
