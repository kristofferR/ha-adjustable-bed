"""AW MOTION product scope on the shared Richmat writer and session lifecycle."""

from __future__ import annotations

from typing import Final

from bleak.backends.characteristic import BleakGATTCharacteristic

from ...const import CONF_BED_TYPE, CONF_PROTOCOL_VARIANT
from ...controller_state import StateKey
from ...errors import invalid
from ...profiles.awmotion import PROFILES
from ..base import BedController
from ..builder import BuildContext
from .awmotion_receive import AwMotionReceive
from .controller import DreamSenseController
from .transport import LIKIMIO_ROUTES, Session

STATUS: Final = StateKey[str | None]("awmotion_status")
REPORTS: Final = StateKey[dict[str, object] | None]("awmotion_reports")


class AwMotionController(DreamSenseController):
    _receive_type = AwMotionReceive
    _routes = LIKIMIO_ROUTES
    # Audio and its capability query are outside the direct-bed product boundary.
    _menu_queries = ("CheckClock", "CheckLight")

    def validate_light(
        self, color: tuple[int, int, int] | None = None, seconds: int | None = None
    ) -> None:
        super().validate_light(color, seconds)
        # Offline admission uses only a saved capability. Execution still checks
        # the freshly connected session in light_settings before any write.
        if not (self._has_light if self._session is None else self._gate("light")):
            raise invalid("dreamsense_capability")

    def _matches_product(self, product: str) -> bool:
        data = self._coordinator.entry.data
        return data.get(CONF_BED_TYPE) == "awmotion" and data.get(CONF_PROTOCOL_VARIANT) == product

    @property
    def requires_notification_channel(self) -> bool:
        return True

    def controller_button_available(self, key: str) -> bool:
        if key == "dreamsense_light_close" and self._session is None:
            return self._has_light and self.command_side is None
        return super().controller_button_available(key)

    @property
    def supports_clock_sync(self) -> bool:
        # All current products use a single countdown, without timezone setup.
        return False

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        received = self._receive
        if not isinstance(received, AwMotionReceive):
            return super().protocol_diagnostics
        return {
            **super().protocol_diagnostics,
            "last_event": received.last_event,
            "reports": dict(received.values),
        }

    def _notification(
        self, session: Session, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if not self._current(session):
            return
        super()._notification(session, sender, data)
        received = self._receive
        if isinstance(received, AwMotionReceive):
            self.forward_controller_state_updates(
                STATUS(received.last_event), REPORTS(dict(received.values))
            )

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self.forward_controller_state_updates(STATUS(None), REPORTS(None))


async def build_controller(ctx: BuildContext) -> BedController:
    if ctx.variant not in PROFILES:
        raise invalid("dreamsense_product")
    return AwMotionController(
        ctx.coordinator,
        product=PROFILES[ctx.variant],
        capability_snapshot=ctx.stored_capabilities("awmotion"),
    )
