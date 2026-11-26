"""Likimio's product scope over the shared Richmat session and wire codec."""

from __future__ import annotations

from dataclasses import replace

from ...codec import richmat as codec
from ...const import BED_TYPE_LIKIMIO, CONF_BED_TYPE, CONF_PROTOCOL_VARIANT
from ...errors import invalid
from ...profiles.likimio import NO_PRODUCT, PROFILES, product_for_variant
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..catalog_buttons import Kind, catalog_button
from ..entity_specs import ControllerButtonSpec, ControllerStateSensorSpec
from .controller import ACK, DreamSenseController
from .receive import Receive
from .transport import LIKIMIO_ROUTES

CANCEL_ALARM = "likimio_cancel_alarm"


class LikimioReceive(Receive):
    """Only type 20 uses a length byte in this delivery."""

    _extended_types = (0x20,)

    def _record(self, frame: bytes) -> None:
        domain, subtype, parameter = frame[3:6]
        if domain == 0x0B and subtype == 2 and parameter in (2, 3) and len(frame) >= 9:
            # The shared model receives this value even though ABM10 has no mode selector.
            self.split = frame[7] != 2


class LikimioController(DreamSenseController):
    _receive_type = LikimioReceive
    _requires_notify = False
    _routes = LIKIMIO_ROUTES

    def _matches_product(self, product: str) -> bool:
        data = self._coordinator.entry.data
        return (
            data.get(CONF_BED_TYPE) == BED_TYPE_LIKIMIO
            and product_for_variant(data.get(CONF_PROTOCOL_VARIANT)) == product
        )

    @property
    def supports_motor_control(self) -> bool:
        return self.profile.product != NO_PRODUCT

    @property
    def supports_stop_all(self) -> bool:
        return self.supports_motor_control

    async def stop_all(self) -> None:
        if self.supports_stop_all:
            await super().stop_all()

    @property
    def has_dynamic_buttons(self) -> bool:
        return True

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if self.profile.product != NO_PRODUCT:
            return super().controller_button_specs
        if "clock" not in self._known:
            return ()
        button = catalog_button(
            CANCEL_ALARM,
            "Cancel alarm",
            lambda ctrl: require_controller(ctrl, LikimioController).cancel_alarm(),
            kind=Kind.EXTRA,
            cancel_movement=False,
            scheduler_resource="configuration",
        )
        assert button is not None
        return (replace(button, entity_registry_enabled_default=True),)

    def controller_button_available(self, key: str) -> bool:
        if self.profile.product == NO_PRODUCT:
            return (
                key == CANCEL_ALARM
                and self.command_side is None
                and "clock" in self._known
                and (self._session is None or "clock" in self._receive.capabilities)
            )
        if key == "dreamsense_light_close" and self._session is None:
            return self._has_light and self.command_side is None
        return super().controller_button_available(key)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        if self.profile.product != NO_PRODUCT or "clock" not in self._known:
            return ()
        return (
            ControllerStateSensorSpec(
                "likimio_alarm_ack", "dreamsense_alarm_ack", ACK, "mdi:alarm"
            ),
        )

    async def cancel_alarm(self) -> None:
        self._physical()
        if self.profile.product != NO_PRODUCT or "clock" not in self._receive.capabilities:
            raise invalid("dreamsense_capability")
        with self._transaction():
            cancel = self._coordinator.cancel_command
            for frame in codec.countdown(0, 0):
                if not await self._send(frame, cancel):
                    break


async def build_controller(ctx: BuildContext) -> BedController:
    product = product_for_variant(ctx.variant)
    if product not in PROFILES:
        raise invalid("dreamsense_product")
    return LikimioController(
        ctx.coordinator,
        product=PROFILES[product],
        capability_snapshot=ctx.stored_capabilities(BED_TYPE_LIKIMIO),
    )
