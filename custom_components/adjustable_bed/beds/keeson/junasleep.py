"""JunaSleep session/state over the shared Keeson movement and preset glue."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ...card import CARD_MASSAGE, CARD_MASSAGE_TIMER, CARD_UTILITY
from ...codec import keeson as codec
from ...const import KEESON_BASE_NOTIFY_SERVICE_UUID
from ...controller_state import StateKey
from ...profiles import junasleep as app
from ...state_keys import UNDER_BED_LIGHTS_ON
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    massage_timer_sensor_spec,
)
from .controller import KeesonController, _wait_unless_cancelled

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

SECONDS: Final = StateKey[int | None]("junasleep_timer_seconds")
INDICATOR: Final = StateKey[int | None]("junasleep_timer_indicator")


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    address: str
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic | None
    response: bool


class JunaSleepController(KeesonController):
    """Two explicitly selected remotes, without inferred STOP or combined keys."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, remote: str) -> None:
        if remote not in app.PROFILES:
            raise ValueError("Choose JunaSleep remote A or B")
        profile = app.PROFILES[remote]
        super().__init__(
            coordinator, variant="base", char_uuid=codec.TRANSPORTS[profile.transport].write_uuid
        )
        self.remote, self.profile = remote, profile
        self._notify_char_uuid = codec.TRANSPORTS[profile.notify].notify_uuid
        self._link: _Link | None = None
        self._subscribed = False
        self._next_query = 0.0

    @property
    def auto_stops_on_idle(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def supports_light_state_feedback(self) -> bool:
        return True

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ("Position I", "Position II")

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"remote": self.remote, "hardware": "UNVERIFIED", "release": "end refresh, no frame"}

    def _live(self, expected: _Link | None = None) -> _Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.controller is not self
            or self._coordinator.address.upper() != link.address
        ):
            raise ConnectionError("JunaSleep BLE session changed")
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("JunaSleep is disconnected")
        transport = codec.TRANSPORTS[self.profile.transport]
        # The app selects notification transport by the saved name, independently
        # of the chosen remote's write transport.
        name = self._coordinator.ble_device_name or ""
        notify_transport = codec.TRANSPORTS["base" if name.startswith("base") else "ksbt"]
        notify_service = (
            KEESON_BASE_NOTIFY_SERVICE_UUID
            if name.startswith("base")
            else notify_transport.service_uuid
        )

        def role(service: str, uuid: str) -> BleakGATTCharacteristic | None:
            for item in client.services:
                if item.uuid.lower() == service:
                    char = item.get_characteristic(uuid)
                    if char is not None:
                        return char
            return None

        write = role(transport.service_uuid, transport.write_uuid)
        notify = role(notify_service, notify_transport.notify_uuid)
        self._notify_char_uuid = notify_transport.notify_uuid
        if write is None or not {"write", "write-without-response"}.intersection(write.properties):
            raise ValueError("JunaSleep control characteristic is not writable")
        self._link = _Link(
            client, self._coordinator.address.upper(), write, notify, "write" in write.properties
        )
        self._next_query = asyncio.get_running_loop().time() + app.QUERY_PERIOD_S

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()

        def validate() -> None:
            self._live(link)

        await self._write_gatt_with_retry(
            link.write.uuid,
            command,
            repeat_count,
            repeat_delay_ms,
            cancel_event=cancel_event
            if cancel_event is not None
            else self._coordinator.cancel_command,
            characteristic=link.write,
            expected_client=link.client,
            response=link.response,
            wall_clock_pacing=True,
            before_write=validate,
        )
        self._live(link)

    def _build_command(self, command_value: int) -> bytes:
        allowed = {
            *app.actions(self.remote).values(),
            0x20000,
            *self.profile.presets.values(),
            *self.profile.memory.values(),
            *(word for _, up, down in app.AXES[self.remote] for word in (up, down)),
        }
        if command_value not in allowed:
            raise NotImplementedError("Unproven JunaSleep command")
        return super()._build_command(command_value)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, cast(int, self.profile.refresh_ms)

    def _get_move_command(self) -> int:
        for axis, up, down in app.AXES[self.remote]:
            direction = self._motor_state.get(axis)
            if direction is not None:
                return up if direction else down
        return 0

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if motor not in {axis for axis, _, _ in app.AXES[self.remote]}:
            raise ValueError("This remote has no such axis")
        await super()._move_motor(motor, direction)

    async def _release_motion(self, *, delay: bool = True) -> None:
        # UP/CANCEL ends refresh only. Polling resumes after three seconds.
        self._next_query = asyncio.get_running_loop().time() + app.QUERY_PERIOD_S

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if self.leased_hold_refreshes(cast(int, self.profile.refresh_ms)) is not None:
            axis, direction = control.rsplit("_", 1)
            await self._move_motor(axis, direction == "up")
        else:
            await super().hold_control(control, duration_ms)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        names = {
            "head": "keeson_back",
            "feet": "keeson_legs",
            "tilt": "junasleep_tilt",
            "lumbar": "junasleep_lumbar",
        }
        return tuple(
            MotorControlSpec(
                axis,
                names[axis],
                lambda c, axis=axis: cast(JunaSleepController, c)._move_motor(axis, True),
                lambda c, axis=axis: cast(JunaSleepController, c)._move_motor(axis, False),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up", f"{axis}_down", stop_scope="side", press_hold_ms=None
                ),
            )
            for axis, _, _ in app.AXES[self.remote]
        )

    async def _write_single_shot(self, command: bytes) -> None:
        link = self._live()
        await super()._write_single_shot(command)
        if self.remote == "a":
            for _ in range(3):
                await _wait_unless_cancelled(self._coordinator.cancel_command, app.POST_TAP_QUERY_S)
                self._live(link)
                if self._coordinator.cancel_command.is_set():
                    return
                await self.write_command(app.QUERY[self.remote])

    async def action(self, key: str) -> None:
        await self._write_single_shot(self._build_command(app.actions(self.remote)[key]))

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec(
                "junasleep_query",
                "Refresh bed status",
                lambda c: cast(JunaSleepController, c).query_status(),
                translation_key="junasleep_query",
                card=CARD_UTILITY,
                scheduler_resource="*",
                diagnostic=True,
            ),
            *tuple(
                ControllerButtonSpec(
                    f"junasleep_{key}",
                    key,
                    lambda c, key=key: cast(JunaSleepController, c).action(key),
                    translation_key=f"junasleep_{key}",
                    card=CARD_MASSAGE,
                    scheduler_resource="*",
                )
                for key in app.actions(self.remote)
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            massage_timer_sensor_spec(
                "junasleep_timer",
                "junasleep_timer",
                INDICATOR,
                attribute_keys=(SECONDS,),
                card=CARD_MASSAGE_TIMER,
            ),
        )

    @property
    def diagnostic_poll_interval(self) -> float | None:
        return app.QUERY_PERIOD_S

    async def async_refresh_diagnostics(self) -> None:
        if asyncio.get_running_loop().time() >= self._next_query:
            await self.query_status()

    async def _toggle_light_to(self, on: bool) -> None:
        if self._coordinator.controller_state.get(UNDER_BED_LIGHTS_ON) is None:
            await self.query_status()
        await super()._toggle_light_to(on)

    async def query_status(self) -> None:
        await self.write_command(app.QUERY[self.remote])

    @property
    def requires_notification_channel(self) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscribed or link.notify is None:
            return
        try:
            await link.client.start_notify(
                link.notify, lambda sender, data: self._receive(link, sender, data)
            )
        except BleakError:
            # Notification/MTU success does not gate app command admission.
            return
        self._live(link)
        self._subscribed = True

    def _receive(self, link: _Link, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        try:
            self._live(link)
        except ConnectionError:
            return
        if link.notify is None or sender.handle != link.notify.handle:
            return
        self.forward_raw_notification(link.notify.uuid, bytes(data))
        status = app.parse_status(self.remote, bytes(data))
        if status is not None:
            if status.light is not None:
                self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(status.light))
            if status.seconds is not None:
                self.forward_controller_state_updates(SECONDS(status.seconds))
            if status.indicator is not None:
                self.forward_controller_state_updates(INDICATOR(status.indicator))

    async def stop_notify(self) -> None:
        link, subscribed = self._link, self._subscribed
        self.on_disconnect()
        if (
            link is not None
            and link.notify is not None
            and subscribed
            and self.client is link.client
            and link.client.is_connected
        ):
            await link.client.stop_notify(link.notify)

    def invalidate_diagnostics(self) -> None:
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None), SECONDS(None), INDICATOR(None)
        )

    def on_disconnect(self) -> None:
        self._link, self._subscribed = None, False
        self._motor_state.clear()
        if self._coordinator.controller is self:
            self.invalidate_diagnostics()


async def build_controller(ctx: BuildContext) -> JunaSleepController:
    return JunaSleepController(ctx.coordinator, remote=ctx.variant or "")
