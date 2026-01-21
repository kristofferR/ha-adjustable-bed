"""Factory function for creating bed controllers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .adapter import discover_services
from .const import (
    # Legacy/brand-specific bed types
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JIECANG,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LINAK,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_NECTAR,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_FFE,
    # Protocol-based bed types (new)
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REVERIE,
    BED_TYPE_RICHMAT,
    BED_TYPE_SOLACE,
    # Variants and UUIDs
    KEESON_VARIANT_ERGOMOTION,
    KEESON_VARIANT_KSBT,
    KEESON_VARIANT_OKIN,
    KEESON_VARIANT_SERTA,
    LEGGETT_VARIANT_MLRM,
    LEGGETT_VARIANT_OKIN,
    OCTO_STAR2_SERVICE_UUID,
    OCTO_VARIANT_STAR2,
    RICHMAT_PROTOCOL_PREFIX55,
    RICHMAT_PROTOCOL_PREFIXAA,
    RICHMAT_VARIANT_NORDIC,
    RICHMAT_VARIANT_PREFIX55,
    RICHMAT_VARIANT_PREFIXAA,
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
    # Protocol-based bed types (new naming convention)
    if bed_type == BED_TYPE_OKIN_HANDLE:
        from .beds.okin_handle import OkinHandleController

        return OkinHandleController(coordinator)

    if bed_type in (BED_TYPE_OKIN_UUID, BED_TYPE_OKIMAT):
        from .beds.okin_uuid import OkinUuidController

        # Pass the configured variant (remote code) to the controller
        variant = protocol_variant or "auto"
        _LOGGER.debug("Using Okin UUID variant: %s", variant)
        return OkinUuidController(coordinator, variant=variant)

    if bed_type == BED_TYPE_OKIN_7BYTE:
        from .beds.okin_7byte import Okin7ByteController

        return Okin7ByteController(coordinator)

    if bed_type == BED_TYPE_OKIN_NORDIC:
        from .beds.okin_nordic import OkinNordicController

        return OkinNordicController(coordinator)

    if bed_type == BED_TYPE_MALOUF_NEW_OKIN:
        from .beds.malouf import MaloufNewOkinController

        return MaloufNewOkinController(coordinator)

    if bed_type == BED_TYPE_MALOUF_LEGACY_OKIN:
        from .beds.malouf import MaloufLegacyOkinController

        return MaloufLegacyOkinController(coordinator)

    if bed_type == BED_TYPE_LEGGETT_GEN2:
        from .beds.leggett_gen2 import LeggettGen2Controller

        return LeggettGen2Controller(coordinator)

    if bed_type == BED_TYPE_LEGGETT_OKIN:
        from .beds.leggett_okin import LeggettOkinController

        return LeggettOkinController(coordinator)

    if bed_type == BED_TYPE_LEGGETT_WILINKE:
        from .beds.leggett_wilinke import LeggettWilinkeController

        return LeggettWilinkeController(coordinator)

    # Brand-specific bed types
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
        elif protocol_variant == RICHMAT_VARIANT_PREFIX55:
            _LOGGER.debug("Using Prefix55 Richmat variant (configured)")
            return RichmatController(
                coordinator,
                remote_code=richmat_remote,
                command_protocol=RICHMAT_PROTOCOL_PREFIX55,
            )
        elif protocol_variant == RICHMAT_VARIANT_PREFIXAA:
            _LOGGER.debug("Using PrefixAA Richmat variant (configured)")
            return RichmatController(
                coordinator,
                remote_code=richmat_remote,
                command_protocol=RICHMAT_PROTOCOL_PREFIXAA,
            )
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
        elif protocol_variant == KEESON_VARIANT_OKIN:
            _LOGGER.debug("Using OKIN FFE Keeson variant (0xE6 prefix)")
            return KeesonController(coordinator, variant="okin")
        elif protocol_variant == KEESON_VARIANT_SERTA:
            _LOGGER.debug("Using Serta Keeson variant (big-endian)")
            return KeesonController(coordinator, variant="serta")
        else:
            # Auto or base variant
            _LOGGER.debug("Using Base Keeson variant")
            return KeesonController(coordinator, variant="base")

    if bed_type == BED_TYPE_OKIN_FFE:
        from .beds.keeson import KeesonController

        # OKIN FFE uses Keeson protocol with 0xE6 prefix
        _LOGGER.debug("Using OKIN FFE controller (Keeson protocol with 0xE6 prefix)")
        return KeesonController(coordinator, variant="okin")

    if bed_type == BED_TYPE_SOLACE:
        from .beds.solace import SolaceController

        return SolaceController(coordinator)

    if bed_type == BED_TYPE_MOTOSLEEP:
        from .beds.motosleep import MotoSleepController

        return MotoSleepController(coordinator)

    if bed_type == BED_TYPE_LEGGETT_PLATT:
        # Use configured variant or auto-detect
        if protocol_variant == LEGGETT_VARIANT_MLRM:
            from .beds.leggett_wilinke import LeggettWilinkeController

            _LOGGER.debug("Using MlRM Leggett & Platt variant (configured)")
            return LeggettWilinkeController(coordinator)
        elif protocol_variant == LEGGETT_VARIANT_OKIN:
            from .beds.leggett_okin import LeggettOkinController

            _LOGGER.debug("Using Okin Leggett & Platt variant (configured)")
            return LeggettOkinController(coordinator)
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
                    from .beds.leggett_wilinke import LeggettWilinkeController

                    _LOGGER.debug("Using MlRM Leggett & Platt variant (auto-detected)")
                    return LeggettWilinkeController(coordinator)

            # Default to gen2 variant (most common L&P variant)
            from .beds.leggett_gen2 import LeggettGen2Controller

            _LOGGER.debug("Using Gen2 Leggett & Platt variant (no WiLinke UUID found)")
            return LeggettGen2Controller(coordinator)
        else:
            # Explicit gen2 variant
            from .beds.leggett_gen2 import LeggettGen2Controller

            _LOGGER.debug("Using Gen2 Leggett & Platt variant (configured)")
            return LeggettGen2Controller(coordinator)

    if bed_type == BED_TYPE_REVERIE:
        from .beds.reverie import ReverieController

        return ReverieController(coordinator)

    if bed_type == BED_TYPE_ERGOMOTION:
        # Ergomotion uses the same protocol as Keeson with position feedback
        from .beds.keeson import KeesonController

        return KeesonController(coordinator, variant="ergomotion")

    if bed_type == BED_TYPE_JIECANG:
        from .beds.jiecang import JiecangController

        return JiecangController(coordinator)

    if bed_type == BED_TYPE_DEWERTOKIN:
        from .beds.okin_handle import OkinHandleController

        return OkinHandleController(coordinator)

    if bed_type == BED_TYPE_OCTO:
        from .beds.octo import OctoController, OctoStar2Controller

        # Use configured variant or auto-detect
        if protocol_variant == OCTO_VARIANT_STAR2:
            _LOGGER.debug("Using Star2 Octo variant (configured)")
            return OctoStar2Controller(coordinator)
        elif protocol_variant in (None, "", "auto"):
            # Auto-detect: check if Star2 service UUID is available
            star2_detected = False

            # Ensure services are discovered
            if client and not client.services:
                _LOGGER.debug("Services not populated for Octo bed, attempting discovery...")
                address = getattr(client, "address", "unknown")
                await discover_services(client, address)

            if client and client.services:
                service_uuids = [s.uuid.lower() for s in client.services]
                _LOGGER.debug(
                    "Auto-detecting Octo variant, found services: %s",
                    service_uuids,
                )
                if OCTO_STAR2_SERVICE_UUID.lower() in service_uuids:
                    star2_detected = True
            else:
                _LOGGER.debug(
                    "No services available for auto-detection, "
                    "defaulting to standard Octo variant"
                )

            if star2_detected:
                _LOGGER.debug("Using Star2 Octo variant (auto-detected)")
                return OctoStar2Controller(coordinator)
            else:
                _LOGGER.debug("Using standard Octo variant (auto-detected)")
                return OctoController(coordinator, pin=octo_pin)
        else:
            # Explicit standard variant
            _LOGGER.debug("Using standard Octo variant (configured)")
            return OctoController(coordinator, pin=octo_pin)

    if bed_type == BED_TYPE_MATTRESSFIRM:
        from .beds.okin_nordic import OkinNordicController

        return OkinNordicController(coordinator)

    if bed_type == BED_TYPE_NECTAR:
        from .beds.okin_7byte import Okin7ByteController

        return Okin7ByteController(coordinator)

    if bed_type == BED_TYPE_DIAGNOSTIC:
        from .beds.diagnostic import DiagnosticBedController

        return DiagnosticBedController(coordinator)

    raise ValueError(f"Unknown bed type: {bed_type}")
