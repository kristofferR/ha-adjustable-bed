"""Bounded Intellibed controls; no inferred movement or release contract."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...errors import BedNotConnectedError, invalid
from ...profiles.intellibed import PROFILES, Profile
from ...state_keys import UNDER_BED_LIGHTS_ON
from ..base import BedController, ProfileExecution
from ..builder import BuildContext
from ..cancellation import cancellable
from ..catalog_buttons import Kind, catalog_button, unique_buttons
from ..diagnostic import DiagnosticBedController
from ..entity_specs import ControllerButtonSpec, MotorControlSpec, PositionNumberSpec

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic


async def press(controller: BedController, variant: str, action: str) -> None:
    # A stale entity's callable must never operate a replacement profile.
    if not isinstance(controller, IntellibedController) or controller.profile.key != variant:
        raise invalid("option_unavailable")
    await controller.press(action)


class IntellibedController(ProfileExecution[Profile], DiagnosticBedController):
    """Explicit single-receiver profile with single-shot non-motion buttons."""

    def __init__(self, coordinator: AdjustableBedCoordinator, variant: str) -> None:
        super().__init__(coordinator)
        if variant not in PROFILES:
            raise ValueError("Choose the Intellibed OLD or HHC remote explicitly")
        self.profile = PROFILES[variant]
        self._link: Link | None = None
        self._subscription: object | None = None
        self._report: bytes | None = None
        self._report_revision = 0

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return self.profile.key == "hhc"

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.supports_lights

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    async def lights_on(self) -> None:
        await self.press("light_on")

    async def lights_off(self) -> None:
        await self.press("light_off")

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return ()

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def control_characteristic_uuid(self) -> str:
        return self.profile.write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return True

    def _role(self, client: BleakClient, service: str, uuid: str) -> BleakGATTCharacteristic:
        matches = [
            c
            for s in client.services
            if s.uuid.lower() == service
            for c in s.characteristics
            if c.uuid.lower() == uuid
        ]
        if len(matches) != 1:
            raise ValueError(f"Intellibed requires one {uuid} under {service}")
        return matches[0]

    def _live(self, expected: Link | None = None) -> Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.controller is not self
        ):
            raise BedNotConnectedError
        p = self.profile
        if (
            self._role(link.client, p.write_service, p.write_uuid) is not link.write
            or self._role(link.client, p.notify_service, p.notify_uuid) is not link.notify
        ):
            raise BedNotConnectedError
        if "write" not in link.write.properties or "notify" not in link.notify.properties:
            raise BedNotConnectedError
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError
        p = self.profile
        write = self._role(client, p.write_service, p.write_uuid)
        notify = self._role(client, p.notify_service, p.notify_uuid)
        if "write" not in write.properties or "notify" not in notify.properties:
            raise ValueError("Intellibed requires write-with-response and notify properties")
        self._link = Link(client, write, notify)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        token = object()
        self._subscription = token
        self._report = None
        self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(None))

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if self._subscription is not token or sender is not link.notify:
                return
            try:
                self._live(link)
            except BedNotConnectedError, ValueError:
                return
            raw = bytes(data)
            self.forward_raw_notification(sender.uuid, raw)
            # No header/checksum or position unit is established. Keep the raw
            # fields diagnostic, including HHC's notification/UI UUID mismatch.
            self._report = raw
            self._report_revision += 1

        try:
            await link.client.start_notify(link.notify, receive)
            self._live(link)
            if self._subscription is not token:
                raise BedNotConnectedError
        except BaseException:
            if self._subscription is token:
                self.on_disconnect()
            raise

    async def stop_notify(self) -> None:
        link, self._subscription = self._link, None
        self._report = None
        self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(None))
        if (
            link is not None
            and self.client is link.client
            and link.client.is_connected
            and self._coordinator.controller is self
        ):
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._subscription = None
        self._report = None
        self._report_revision = 0
        self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(None))

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        raw = self._report if self._subscription is not None else None
        try:
            self._live()
        except BedNotConnectedError, ValueError:
            raw = None
        return {
            "variant": self.profile.key,
            "notify_uuid": self.profile.notify_uuid,
            "ui_notify_uuid": self.profile.ui_notify_uuid,
            "report_revision": self._report_revision,
            "raw_status": raw.hex() if raw is not None else None,
            "raw_fields": (
                {"head": raw[7], "feet": raw[8], "light": raw[13], "timer": raw[14]}
                if raw is not None and len(raw) >= 15
                else None
            ),
        }

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return unique_buttons(
            catalog_button(
                f"intellibed_{self.profile.key}_{key}",
                action.label,
                partial(press, variant=self.profile.key, action=key),
                kind=Kind.LIGHT if action.light else Kind.MASSAGE,
                combine_sides=False,
            )
            for key, action in self.profile.actions.items()
            if not (self.profile.key == "hhc" and key in ("light_on", "light_off"))
        )

    async def press(self, action: str) -> None:
        if action not in self.profile.actions:
            raise invalid("option_unavailable")
        link = self._live()
        if self._subscription is None:
            raise BedNotConnectedError
        token = self._subscription
        value = self.profile.actions[action]
        event = self._coordinator.cancel_command
        if value.delay_ms:
            await cancellable(asyncio.sleep(value.delay_ms / 1000), event)
        self._live(link)
        if self._subscription is not token:
            raise BedNotConnectedError
        await self.write_command(self.profile.encode(value), cancel_event=event)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if repeat_count != 1 or command not in {
            self.profile.encode(action) for action in self.profile.actions.values()
        }:
            raise invalid("option_unavailable")
        link = self._live()
        token = self._subscription
        if token is None:
            raise BedNotConnectedError

        def validate() -> None:
            self._live(link)
            if self._subscription is not token:
                raise BedNotConnectedError

        # PROPERTY_WRITE is required by the app. HA uses the acknowledged path;
        # the app's retained Android write type is not hardware-verified.
        await self._write_gatt_with_retry(
            link.write.uuid,
            command,
            cancel_event=cancel_event,
            response=True,
            characteristic=link.write,
            expected_client=link.client,
            before_write=validate,
            settle_write=True,
        )

    async def stop_all(self) -> None:
        raise invalid("option_unavailable")


async def build_controller(ctx: BuildContext) -> BedController:
    return IntellibedController(ctx.coordinator, ctx.variant or "")
