"""Askona's selected bed route, without inheriting generic motor refresh/STOP."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Final, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.const import UnitOfTime

from ...card import CARD_MASSAGE, CARD_MASSAGE_TIMER
from ...codec.keeson import AskonaStatus
from ...command_scheduler import note_frame_skipped
from ...controller_state import StateKey
from ...errors import failed, invalid
from ...profiles import askona as app
from ...state_keys import UNDER_BED_LIGHTS_ON, massage_intensity
from ..base import BedController
from ..builder import BuildContext
from ..cancellation import cancellable
from ..entity_specs import (
    POSITION_UNIT_DEGREES,
    ControllerNumberSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
    build_position_number_spec,
)
from .controller import KeesonController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession

TIMER_SECONDS: Final = StateKey[float | None]("askona_timer_seconds")


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    address: str
    response: bool


class AskonaController(KeesonController):
    """Use shared family actions only where the frozen app proves equivalence."""

    def __init__(self, coordinator: AdjustableBedCoordinator, model: str) -> None:
        if model not in app.PROFILES:
            raise invalid("askona_model_required")
        super().__init__(coordinator, char_uuid=app.WRITE_UUID)
        self.model = model
        self.profile: app.AskonaProfile = app.PROFILES[model]
        self._link: _Link | None = None
        self._subscribed: _Link | None = None
        self._subscription_token: object | None = None
        self._status: AskonaStatus | None = None
        self._software_version: str | None = None

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "model": self.model,
            "audit_status": "PARTIAL",
            "hardware": "UNVERIFIED",
            "status": asdict(self._status) if self._status is not None else None,
            "stop_frame": "not defined in accepted mapper",
            "software_version": self._software_version,
            "custom_targets": self.supports_direct_position_control,
        }

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_direct_position_control(self) -> bool:
        return self.model != "180x200"

    @property
    def supports_combined_position_control(self) -> bool:
        return self.supports_direct_position_control

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # No proven held-command timing or physical stopping contract.
        return ()

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        if not self.supports_direct_position_control:
            return ()
        return (
            build_position_number_spec(
                "head",
                max_value=self.profile.max_head,
                unit=POSITION_UNIT_DEGREES,
                position_key="back",
            ),
            build_position_number_spec(
                "feet",
                max_value=self.profile.max_foot,
                unit=POSITION_UNIT_DEGREES,
                position_key="legs",
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "askona_massage_timer",
                "massage_timer",
                TIMER_SECONDS,
                "mdi:timer-outline",
                native_unit_of_measurement=UnitOfTime.SECONDS,
                entity_registry_enabled_default=True,
                card=CARD_MASSAGE_TIMER,
                entity_category=None,
            ),
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        # Only the head slider's complete wrap/delta caller is accepted (E22).
        return (
            ControllerNumberSpec(
                "askona_head_massage",
                "massage_head_intensity",
                massage_intensity("head"),
                0,
                len(self.profile.massage_values) - 1,
                1,
                lambda c, value: cast(AskonaController, c).set_head_massage(value),
                card=CARD_MASSAGE,
            ),
        )

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage_toggle_control(self) -> bool:
        return True

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return True

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return True

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return True

    @property
    def supports_light_state_feedback(self) -> bool:
        return True

    def _live(self, link: _Link | None = None) -> _Link:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self.client is not current.client
            or not current.client.is_connected
            or self._coordinator.address.upper() != current.address
        ):
            raise failed("askona_session_changed")
        return current

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise failed("askona_session_changed")
        service = client.services.get_service(app.WRITE_SERVICE)
        notify_service = client.services.get_service(app.NOTIFY_SERVICE)
        write = service.get_characteristic(app.WRITE_UUID) if service else None
        notify = notify_service.get_characteristic(app.NOTIFY_UUID) if notify_service else None
        if (
            write is None
            or notify is None
            or not {"write", "write-without-response"}.intersection(write.properties)
        ):
            raise failed("askona_gatt_missing")
        # The app leaves Android writeType untouched. This is HA's runtime
        # transport choice, not a claim that Android used an acknowledged write.
        self._link = _Link(
            client, write, notify, self._coordinator.address.upper(), "write" in write.properties
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 0,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        event = self._coordinator.cancel_command if cancel_event is None else cancel_event
        if event.is_set():
            note_frame_skipped()
            return
        if self._subscribed is not link:
            await self.start_notify()

        def check() -> None:
            self._live(link)

        await self._write_gatt_with_retry(
            link.write.uuid,
            command,
            cancel_event=event,
            response=link.response,
            characteristic=link.write,
            expected_client=link.client,
            before_write=check,
        )

    async def lights_on(self) -> None:
        await self._set_light(True)

    async def lights_off(self) -> None:
        await self._set_light(False)

    async def _set_light(self, on: bool) -> None:
        link = self._live()
        status, token = self._status, self._subscription_token
        if status is None or token is None or self._subscribed is not link:
            raise invalid("askona_feedback_required")
        reported = self._coordinator.controller_state.get(UNDER_BED_LIGHTS_ON)
        if reported is None:
            raise invalid("askona_feedback_required")
        if reported is on:
            return

        def current() -> bool:
            return (
                self._link is link
                and self.client is link.client
                and self._coordinator.address.upper() == link.address
                and self._subscribed is link
                and self._subscription_token is token
                and self._status is status
                and link.client.is_connected
            )

        with self.sent_state(UNDER_BED_LIGHTS_ON(on), is_current=current):
            await self.lights_toggle()

    async def _write_single_shot(self, command: bytes) -> None:
        # No release frame in P1. Never inherit another app's zero key.
        await self.write_command(command)

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        raise invalid("askona_movement_unavailable")

    async def stop_all(self) -> None:
        raise invalid("askona_movement_unavailable")

    async def preset_flat(self) -> None:
        await self.write_command(app.target(0, 0))

    async def set_motor_position(self, motor: str, position: int) -> None:
        await self.set_motor_positions({motor: position})

    async def set_motor_positions(self, positions: Mapping[str, int]) -> None:
        if not self.supports_direct_position_control:
            raise invalid("askona_movement_unavailable")
        link = self._live()
        status = self._status
        if status is None or self._subscribed is not link:
            raise invalid("askona_feedback_required")
        head, foot = status.head, status.foot
        for motor, position in positions.items():
            if motor not in ("head", "back", "feet", "legs"):
                raise invalid("askona_target_invalid")
            head_axis = motor in ("head", "back")
            maximum = self.profile.max_head if head_axis else self.profile.max_foot
            if (
                isinstance(position, bool)
                or not isinstance(position, int)
                or not 0 <= position <= maximum
            ):
                raise invalid("askona_target_invalid")
            if head_axis:
                head = position
            else:
                foot = position
        await self.write_command(app.target(head, foot))

    async def set_head_massage(self, value: float) -> None:
        link = self._live()
        status = self._status
        if status is None:
            raise invalid("askona_feedback_required")
        maximum = len(self.profile.massage_values) - 1
        if (
            isinstance(value, bool)
            or not math.isfinite(value)
            or value != int(value)
            or not 0 <= value <= maximum
        ):
            raise invalid("askona_target_invalid")
        old, target = status.head_massage, int(value)
        # Reject unrecognized raw levels instead of driving from unknown state.
        if status.real_head_massage not in self.profile.massage_values:
            raise invalid("askona_feedback_required")
        wrapped_up, wrapped_down = old == maximum and target == 0, old == 0 and target == maximum
        up = wrapped_up or not wrapped_down and target > old
        count = 1 if wrapped_up or wrapped_down else abs(target - old)
        event = self._coordinator.cancel_command
        for _ in range(count):
            self._live(link)
            if event.is_set():
                return
            await (self.massage_head_up() if up else self.massage_head_down())
            try:
                await cancellable(asyncio.sleep(1), event)
            except asyncio.CancelledError:
                if not event.is_set():
                    raise
                return

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if callback is not None:
            self._notify_callback = callback
        if self._subscribed is link:
            return
        token = self._subscription_token = object()

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._subscription_token is not token
                or self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
                or self._coordinator.address.upper() != link.address
                or sender.handle != link.notify.handle
                or sender.uuid.lower() != app.NOTIFY_UUID
            ):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            status = app.parse_status(bytes(data), self.model)
            if status is None:
                return
            self._status = status
            self.forward_controller_state_updates(
                UNDER_BED_LIGHTS_ON(status.light),
                TIMER_SECONDS(status.timer_ms / 1000),
                massage_intensity("head")(status.head_massage),
                massage_intensity("foot")(status.foot_massage),
            )
            if self._notify_callback is not None:
                self._notify_callback("back", status.head)
                self._notify_callback("legs", status.foot)

        try:
            await link.client.start_notify(link.notify, receive)
            self._live(link)
            if self._subscription_token is token:
                self._subscribed = link
        except BaseException:
            if self._subscription_token is token:
                self._retire_subscription()
            raise

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        link = self._live()
        version = link.client.services.get_characteristic(app.VERSION_UUID)
        if version is not None and "read" in version.properties:
            value = await link.client.read_gatt_char(version)
            self._live(link)
            if session.is_current():
                self._software_version = bytes(value).decode("utf-8", errors="replace")
        return True

    async def read_positions(self, motor_count: int = 2) -> None:
        await self.start_notify()

    async def stop_notify(self) -> None:
        link = self._subscribed
        self._retire_subscription()
        if link is not None and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._retire_subscription()

    def _retire_subscription(self) -> None:
        self._subscribed = None
        self._subscription_token = None
        self._status = None
        self._software_version = None
        self._notify_callback = None
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None),
            TIMER_SECONDS(None),
            massage_intensity("head")(None),
            massage_intensity("foot")(None),
        )


async def build_controller(ctx: BuildContext) -> BedController:
    return AskonaController(ctx.coordinator, ctx.variant or "")
