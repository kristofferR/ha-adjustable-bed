"""Runtime narrowing for Standard OCTO controllers and paired-side views."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .beds.octo import OctoController


def octo_controller(controller: object | None) -> OctoController | None:
    """Return the underlying Standard OCTO controller when present.

    Single-address paired children expose a ``SideBoundController`` proxy. Its
    dynamic forwarding intentionally supports every bed controller, so unwrap
    it before narrowing to the Octo-specific runtime contract.
    """
    from .beds.base import SideBoundController

    if isinstance(controller, SideBoundController):
        controller = controller._controller
    if not getattr(controller, "is_octo_smart_control", False):
        return None

    # Keep the protocol module lazy for integrations that do not use Standard
    # OCTO. The marker only selects the candidate; isinstance establishes its
    # actual runtime type before exposing OCTO-specific attributes.
    from .beds.octo import OctoController

    return controller if isinstance(controller, OctoController) else None
