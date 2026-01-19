"""Factory function for creating bed controllers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .adapter import discover_services
from .const import (
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JIECANG,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LINAK,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_NECTAR,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_REVERIE,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERTA,
    BED_TYPE_SOLACE,
    KEESON_VARIANT_ERGOMOTION,
    KEESON_VARIANT_KSBT,
    LEGGETT_VARIANT_MLRM,
    LEGGETT_VARIANT_OKIN,
    OCTO_STAR2_SERVICE_UUID,
    OCTO_VARIANT_STAR2,
    RICHMAT_VARIANT_NORDIC,
    RICHMAT_VARIANT_WILINKE,
    RICHMAT_WILINKE_SERVICE_UUIDS,
)

if TYPE_CHECKING:
    from bleak import BleakClient

    from .beds.base import BedController
    from .coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


async def create_controller(
    coordinator: AdjustableBedCoordinator,
    bed_type: str,
    protocol_variant: str | None,
    client: BleakClient | None,
    octo_pin: str = "",
    richmat_remote: str = "auto",
) -> BedController:
    """Create the appropriate bed controller.

    This factory function handles controller instantiation with lazy imports
    to avoid loading all controller modules until needed.

    Args:
        coordinator: The AdjustableBedCoordinator instance
        bed_type: The type of bed (from const.py BED_TYPE_* constants)
        protocol_variant: Protocol variant for beds with multiple protocols
        client: The BleakClient connection (needed for auto-detection)
        octo_pin: PIN for Octo beds (default: empty string)
        richmat_remote: Remote code for Richmat beds (default: "auto")

    Returns:
        The appropriate BedController subclass instance

    Raises:
        ValueError: If bed_type is unknown
        ConnectionError: If auto-detection is needed but client is not connected
    """
    if bed_type == BED_TYPE_LINAK:
        from .beds.linak import LinakController

        return LinakController(coordinator)

    if bed_type == BED_TYPE_RICHMAT:
        from .beds.richmat import RichmatController, detect_richmat_variant

        # Use configured variant or auto-detect
        if protocol_variant == RICHMAT_VARIANT_NORDIC:
            _LOGGER.debug("Using Nordic Richmat variant (configured)")
            return RichmatController(coordinator, is_wilinke=False, remote_code=richmat_remote)
        elif protocol_variant == RICHMAT_VARIANT_WILINKE:
            _LOGGER.debug("Using WiLinke Richmat variant (configured)")
            return RichmatController(coordinator, is_wilinke=True, remote_code=richmat_remote)
        else:
            # Auto-detect variant based on available services
            _LOGGER.debug("Auto-detecting Richmat variant...")
            if client is None or not client.is_connected:
                raise ConnectionError("Cannot detect variant: client not connected")
            is_wilinke, char_uuid = await detect_richmat_variant(client)
            return RichmatController(
                coordinator,
                is_wilinke=is_wilinke,
                char_uuid=char_uuid,
                remote_code=richmat_remote,
            )

    if bed_type == BED_TYPE_KEESON:
        from .beds.keeson import KeesonController

        # Use configured variant or default to base
        if protocol_variant == KEESON_VARIANT_KSBT:
            _LOGGER.debug("Using KSBT Keeson variant (configured)")
            return KeesonController(coordinator, variant="ksbt")
        elif protocol_variant == KEESON_VARIANT_ERGOMOTION:
            _LOGGER.debug("Using Ergomotion Keeson variant (with position feedback)")
            return KeesonController(coordinator, variant="ergomotion")
        else:
            # Auto or base variant
            _LOGGER.debug("Using Base Keeson variant")
            return KeesonController(coordinator, variant="base")

    if bed_type == BED_TYPE_SOLACE:
        from .beds.solace import SolaceController

        return SolaceController(coordinator)

    if bed_type == BED_TYPE_MOTOSLEEP:
        from .beds.motosleep import MotoSleepController

        return MotoSleepController(coordinator)

    if bed_type == BED_TYPE_LEGGETT_PLATT:
        # Use configured variant or auto-detect
        if protocol_variant == LEGGETT_VARIANT_MLRM:
            from .beds.leggett_platt_mlrm import LeggettPlattMlrmController

            _LOGGER.debug("Using MlRM Leggett & Platt variant (configured)")
            return LeggettPlattMlrmController(coordinator)
        elif protocol_variant == LEGGETT_VARIANT_OKIN:
            from .beds.leggett_platt import LeggettPlattController

            _LOGGER.debug("Using Okin Leggett & Platt variant (configured)")
            return LeggettPlattController(coordinator, variant="okin")
        elif protocol_variant in (None, "", "auto"):
            # Auto-detect: check if WiLinke service UUID is available (indicates MlRM)
            if client is None:
                raise ConnectionError(
                    "Cannot auto-detect Leggett & Platt variant: no BLE client provided"
                )

            # Ensure services are discovered
            if not client.services:
                _LOGGER.debug("Services not populated, attempting discovery...")
                address = getattr(client, "address", "unknown")
                discovered = await discover_services(client, address)
                if not discovered or not client.services:
                    raise ConnectionError(
                        "Cannot auto-detect Leggett & Platt variant: "
                        "failed to discover BLE services. "
                        "Please manually select a protocol variant in settings."
                    )

            # Check for WiLinke service UUID (indicates MlRM variant)
            wilinke_uuids_lower = [uuid.lower() for uuid in RICHMAT_WILINKE_SERVICE_UUIDS]
            for service in client.services:
                if service.uuid.lower() in wilinke_uuids_lower:
                    from .beds.leggett_platt_mlrm import LeggettPlattMlrmController

                    _LOGGER.debug("Using MlRM Leggett & Platt variant (auto-detected)")
                    return LeggettPlattMlrmController(coordinator)

            # Default to gen2 variant (most common L&P variant)
            from .beds.leggett_platt import LeggettPlattController

            _LOGGER.debug("Using Gen2 Leggett & Platt variant (no WiLinke UUID found)")
            return LeggettPlattController(coordinator, variant="gen2")
        else:
            # Explicit gen2 variant
            from .beds.leggett_platt import LeggettPlattController

            _LOGGER.debug("Using Gen2 Leggett & Platt variant (configured)")
            return LeggettPlattController(coordinator, variant="gen2")

    if bed_type == BED_TYPE_REVERIE:
        from .beds.reverie import ReverieController

        return ReverieController(coordinator)

    if bed_type == BED_TYPE_OKIMAT:
        from .beds.okimat import OkimatController

        # Pass the configured variant (remote code) to the controller
        variant = protocol_variant or "auto"
        _LOGGER.debug("Using Okimat variant: %s", variant)
        return OkimatController(coordinator, variant=variant)

    if bed_type == BED_TYPE_ERGOMOTION:
        # Ergomotion uses the same protocol as Keeson with position feedback
        from .beds.keeson import KeesonController

        return KeesonController(coordinator, variant="ergomotion")

    if bed_type == BED_TYPE_JIECANG:
        from .beds.jiecang import JiecangController

        return JiecangController(coordinator)

    if bed_type == BED_TYPE_DEWERTOKIN:
        from .beds.dewertokin import DewertOkinController

        return DewertOkinController(coordinator)

    if bed_type == BED_TYPE_SERTA:
        from .beds.serta import SertaController

        return SertaController(coordinator)

    if bed_type == BED_TYPE_OCTO:
        from .beds.octo import OctoController, OctoStar2Controller

        # Use configured variant or auto-detect
        if protocol_variant == OCTO_VARIANT_STAR2:
            _LOGGER.debug("Using Star2 Octo variant (configured)")
            return OctoStar2Controller(coordinator)
        elif protocol_variant in (None, "", "auto"):
            # Auto-detect: check if Star2 service UUID is available
            if client and client.services:
                for service in client.services:
                    if service.uuid.lower() == OCTO_STAR2_SERVICE_UUID.lower():
                        _LOGGER.debug("Using Star2 Octo variant (auto-detected)")
                        return OctoStar2Controller(coordinator)
            # Default to standard Octo
            _LOGGER.debug("Using standard Octo variant")
            return OctoController(coordinator, pin=octo_pin)
        else:
            # Explicit standard variant
            _LOGGER.debug("Using standard Octo variant (configured)")
            return OctoController(coordinator, pin=octo_pin)

    if bed_type == BED_TYPE_MATTRESSFIRM:
        from .beds.mattressfirm import MattressFirmController

        return MattressFirmController(coordinator)

    if bed_type == BED_TYPE_NECTAR:
        from .beds.nectar import NectarController

        return NectarController(coordinator)

    if bed_type == BED_TYPE_DIAGNOSTIC:
        from .beds.diagnostic import DiagnosticBedController

        return DiagnosticBedController(coordinator)

    raise ValueError(f"Unknown bed type: {bed_type}")
