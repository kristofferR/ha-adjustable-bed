"""Create bed controllers.

Each bed type maps to a lazily imported bed module. A ``_ControllerSpec``
names a controller class with fixed constructor arguments; a ``_BuilderSpec``
names the module's builder, which turns a ``BuildContext`` (the entry, the
route and what the live link observed) into a controller. Importing every
controller module at integration load would cost startup time for protocols
the user does not have, and the import must run in the import executor
rather than the event loop (issue #368).

tests/test_controller_contract.py resolves every entry, so a bad module, class
or builder name fails the suite rather than a user's bed setup.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from types import MappingProxyType, ModuleType
from typing import TYPE_CHECKING, Any, Final

from .adapter import discover_services
from .bed_traits import bed_traits
from .beds.builder import BuildContext, ControllerBuilder
from .const import (
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_ADJUSTAMATTRESS,
    BED_TYPE_BEDJET_POWERLAYER,
    BED_TYPE_BEDSENSE,
    BED_TYPE_BEDTECH,
    BED_TYPE_BF,
    BED_TYPE_CASPER_BASE,
    BED_TYPE_CHERISH,
    BED_TYPE_COMFORT_ENHANCEMENTS,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_COOLBASE,
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_DOUBLESLEEP,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_ERGOMOTION_4,
    BED_TYPE_ESHINE,
    BED_TYPE_ESHINE_OKIN,
    BED_TYPE_FSM_RELAX,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_GLIDEAWAY_MOTION,
    BED_TYPE_GMMOTOR,
    BED_TYPE_GMMOTOR_SLEEP_MM,
    BED_TYPE_GMMOTOR_SLEEP_SXB,
    BED_TYPE_GOODVIBE,
    BED_TYPE_HJBED,
    BED_TYPE_ISLEEP,
    BED_TYPE_JENSEN,
    BED_TYPE_JIECANG,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_LP_LEGACY,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LIMOSS,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LINAK,
    BED_TYPE_LOGICDATA,
    BED_TYPE_LOGICDATA_AIR_PUMP,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_MOTION_BED,
    BED_TYPE_MOTOMOTION,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_NECTAR,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_64BIT,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_OKIN_CB35,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_DOT,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_ORE,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REMACRO,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_REVERIE_PAIRLINK,
    BED_TYPE_RICHMAT,
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    BED_TYPE_RONDURE,
    BED_TYPE_SBI,
    BED_TYPE_SCOTT_LIVING,
    BED_TYPE_SERENITY,
    BED_TYPE_SERTA,
    BED_TYPE_SIMMONS,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SLEEPSTAR,
    BED_TYPE_SLEEPTRACKER,
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_SOLACE,
    BED_TYPE_STAR_ELEVATE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_SUTA,
    BED_TYPE_SVANE,
    BED_TYPE_TIMOTION_AHF,
    BED_TYPE_TRANQUIL,
    BED_TYPE_VIBRADORM,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    BED_TYPE_ZSERIES,
    CONF_BED_TYPE,
    CONF_SLEEPYS_ELITE_SELECTOR,
    KEESON_BASE_WRITE_CHAR_UUID,
    KEESON_VARIANT_ERGOMOTION,
    KEESON_VARIANT_OKIN,
    KEESON_VARIANT_SERTA,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_MLRM,
    LOGICDATA_CHAR_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
    OKIMAT_WRITE_CHAR_UUID,
    RICHMAT_MH_APPS,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    SLEEPYS_BOX24_WRITE_CHAR_UUID,
    VARIANT_AUTO,
)

if TYPE_CHECKING:
    from bleak import BleakClient

    from .beds.base import BedController
    from .coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# The command endpoints each Okin route's controller writes. An Okin UUID entry
# also drives a DOT box, and FurniMove selects whichever of the two it finds.
_OKIN_ROUTE_ENDPOINTS: Final[dict[str, frozenset[str]]] = {
    **dict.fromkeys(
        (BED_TYPE_OKIN_UUID, BED_TYPE_OKIMAT, BED_TYPE_FURNIMOVE),
        frozenset({OKIMAT_WRITE_CHAR_UUID.lower(), NORDIC_UART_WRITE_CHAR_UUID.lower()}),
    ),
    BED_TYPE_OKIN_RF_ECO_BT: frozenset({OKIMAT_WRITE_CHAR_UUID.lower()}),
    BED_TYPE_OKIN_DOT: frozenset({NORDIC_UART_WRITE_CHAR_UUID.lower()}),
}


def _require_write_endpoint(client: BleakClient, endpoints: frozenset[str], bed_type: str) -> None:
    """Raise ConnectionError unless the link has one of these writable endpoints."""
    for service in client.services or ():
        for characteristic in service.characteristics:
            if str(characteristic.uuid).lower() in endpoints and {
                "write",
                "write-without-response",
            } & set(characteristic.properties):
                return
    raise ConnectionError(f"The bed exposes no command endpoint for {bed_type}")


def require_okin_route_endpoint(client: BleakClient, bed_type: str) -> None:
    """Raise ConnectionError unless the link has a writable endpoint the route writes."""
    _require_write_endpoint(client, _OKIN_ROUTE_ENDPOINTS[bed_type], bed_type)


# The one command endpoint each Sleepy's receiver route's controller writes.
_SLEEPYS_ROUTE_ENDPOINTS: Final[dict[str, frozenset[str]]] = {
    BED_TYPE_SLEEPYS_BOX15: frozenset({KEESON_BASE_WRITE_CHAR_UUID.lower()}),
    BED_TYPE_SLEEPYS_BOX24: frozenset({SLEEPYS_BOX24_WRITE_CHAR_UUID.lower()}),
    BED_TYPE_SLEEPYS_BOX25: frozenset({NORDIC_UART_WRITE_CHAR_UUID.lower()}),
}


def require_sleepys_route(client: BleakClient, data: Mapping[str, Any]) -> None:
    """Raise ConnectionError unless the link exposes what the staged Sleepy's route needs.

    The app's control box selector needs its exact setup and response targets;
    a receiver route needs the one endpoint its controller writes.
    """
    bed_type = data[CONF_BED_TYPE]
    if bed_type == BED_TYPE_SLEEPYS_ELITE_APP:
        from .beds.sleepys_app import require_selector_route

        require_selector_route(client, data[CONF_SLEEPYS_ELITE_SELECTOR])
        return
    _require_write_endpoint(client, _SLEEPYS_ROUTE_ENDPOINTS[bed_type], bed_type)


def require_logicdata_route(client: BleakClient, data: Mapping[str, Any]) -> None:
    """Raise ConnectionError unless the link exposes what the staged LOGICDATA route needs.

    SimplicityFrame writes its one characteristic; an app needs its own transport.
    """
    if data[CONF_BED_TYPE] == BED_TYPE_LOGICDATA_APP:
        from .beds.logicdata_app import require_app_transport

        require_app_transport(client, data)
        return
    _require_write_endpoint(client, frozenset({LOGICDATA_CHAR_UUID.lower()}), BED_TYPE_LOGICDATA)




@dataclass(frozen=True, slots=True)
class _ControllerSpec:
    """A controller class built from the coordinator and fixed constructor kwargs.

    ``module`` is resolved relative to ``.beds``.
    """

    module: str
    class_name: str
    kwargs: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class _BuilderSpec:
    """A ``ControllerBuilder`` function in a ``.beds`` module."""

    module: str
    function: str = "build_controller"


# Bed types whose construction is "import this class and pass the coordinator
# plus fixed kwargs".
_SIMPLE_CONTROLLERS: Final[dict[str, _ControllerSpec]] = {
    BED_TYPE_BF: _ControllerSpec("bf_cherish", "BfCherishController"),
    BED_TYPE_CHERISH: _ControllerSpec("bf_cherish", "BfCherishController", MappingProxyType({"cherish": True})),
    BED_TYPE_ESHINE: _ControllerSpec("eshine", "EshineController"),
    BED_TYPE_GMMOTOR_SLEEP_MM: _ControllerSpec(
        "gmmotor_sleep", "GmmotorSleepController", MappingProxyType({"sxb": False})
    ),
    BED_TYPE_GMMOTOR_SLEEP_SXB: _ControllerSpec(
        "gmmotor_sleep", "GmmotorSleepController", MappingProxyType({"sxb": True})
    ),
    "hush_remote": _ControllerSpec("hush_sleep", "HushRemoteController"),
    "hush_sleep_mm": _ControllerSpec(
        "hush_sleep", "HushSleepController", MappingProxyType({"kind": "mm"})
    ),
    "hush_sleep_sxb": _ControllerSpec(
        "hush_sleep", "HushSleepController", MappingProxyType({"kind": "sxb"})
    ),
    BED_TYPE_ISLEEP: _ControllerSpec("isleep", "IsleepController"),
    "casper_remote": _ControllerSpec("casper_sleep", "CasperRemoteController"),
    "casper_sleep_mm": _ControllerSpec(
        "casper_sleep", "CasperSleepController", MappingProxyType({"kind": "mm"})
    ),
    "casper_sleep_sxb": _ControllerSpec(
        "casper_sleep", "CasperSleepController", MappingProxyType({"kind": "sxb"})
    ),
    BED_TYPE_SERENITY: _ControllerSpec("serenity", "SerenityController"),
    BED_TYPE_TRANQUIL: _ControllerSpec("serenity", "TranquilController"),
    BED_TYPE_CUSTOMATIC_CLARITY: _ControllerSpec(
        "customatic", "CustomaticController", MappingProxyType({"profile": "clarity"})
    ),
    BED_TYPE_CUSTOMATIC_JEROMES: _ControllerSpec(
        "customatic", "CustomaticController", MappingProxyType({"profile": "jeromes"})
    ),
    BED_TYPE_CUSTOMATIC_REMEDY: _ControllerSpec(
        "customatic", "CustomaticController", MappingProxyType({"profile": "remedy"})
    ),
    BED_TYPE_OKIN_RF_ECO_BT: _ControllerSpec("okin_rf_eco_bt", "OkinRfEcoBtController"),
    BED_TYPE_OKIN_7BYTE: _ControllerSpec("okin_7byte", "Okin7ByteController"),
    BED_TYPE_OKIN_NORDIC: _ControllerSpec("okin_nordic", "OkinNordicController"),
    BED_TYPE_OKIN_CB35: _ControllerSpec("okin_cb35", "OkinCB35Controller"),
    BED_TYPE_OKIN_ORE: _ControllerSpec("okin_ore", "OkinOreController"),
    BED_TYPE_MALOUF_NEW_OKIN: _ControllerSpec("malouf", "MaloufNewOkinController"),
    BED_TYPE_MALOUF_LEGACY_OKIN: _ControllerSpec("malouf", "MaloufLegacyOkinController"),
    BED_TYPE_LEGGETT_WILINKE: _ControllerSpec("leggett_wilinke", "LeggettWilinkeController"),
    # OKIN FFE uses the Keeson protocol with an 0xE6 prefix.
    BED_TYPE_OKIN_FFE: _ControllerSpec(
        "keeson", "KeesonController", MappingProxyType({"variant": KEESON_VARIANT_OKIN})
    ),
    BED_TYPE_SUTA: _ControllerSpec("suta", "SutaController"),
    BED_TYPE_TIMOTION_AHF: _ControllerSpec("timotion_ahf", "TiMOTIONAhfController"),
    BED_TYPE_BEDJET_POWERLAYER: _ControllerSpec(
        "bedjet_powerlayer", "BedJetPowerLayerController"
    ),
    BED_TYPE_COMFORT_MOTION: _ControllerSpec("jiecang", "JiecangController"),
    # Ergomotion is the Keeson protocol with position feedback; Serta Motion
    # Perfect is the same protocol with its own variant.
    BED_TYPE_ERGOMOTION: _ControllerSpec(
        "keeson", "KeesonController", MappingProxyType({"variant": KEESON_VARIANT_ERGOMOTION})
    ),
    BED_TYPE_ERGOMOTION_4: _ControllerSpec("ergomotion4", "Ergomotion4Controller"),
    BED_TYPE_SERTA: _ControllerSpec(
        "keeson", "KeesonController", MappingProxyType({"variant": KEESON_VARIANT_SERTA})
    ),
    BED_TYPE_JIECANG: _ControllerSpec("jiecang", "JiecangController"),
    BED_TYPE_LIMOSS: _ControllerSpec("limoss", "LimossController"),
    BED_TYPE_LOGICDATA: _ControllerSpec("logicdata", "LogicdataController"),
    BED_TYPE_LOGICDATA_AIR_PUMP: _ControllerSpec(
        "logicdata_air_pump", "LogicdataAirPumpController"
    ),
    BED_TYPE_MATTRESSFIRM: _ControllerSpec("okin_nordic", "OkinNordicController"),
    BED_TYPE_NECTAR: _ControllerSpec("okin_7byte", "Okin7ByteController"),
    BED_TYPE_DIAGNOSTIC: _ControllerSpec("diagnostic", "DiagnosticBedController"),
    BED_TYPE_BEDTECH: _ControllerSpec("bedtech", "BedTechController"),
    BED_TYPE_SLEEPYS_BOX15: _ControllerSpec("sleepys", "SleepysBox15Controller"),
    BED_TYPE_SLEEPYS_BOX24: _ControllerSpec("sleepys", "SleepysBox24Controller"),
    BED_TYPE_VIBRADORM: _ControllerSpec("vibradorm", "VibradormController"),
    BED_TYPE_SCOTT_LIVING: _ControllerSpec("scott_living", "ScottLivingController"),
}


# Bed types whose controller needs the variant, entry data, the advertisement
# or the live GATT table. Each builder lives in its bed module.
_BUILDERS: Final[dict[str, _BuilderSpec]] = {
    **dict.fromkeys(RICHMAT_MH_APPS, _BuilderSpec("richmat_mh")),
    BED_TYPE_ADJUSTABLE_LUMBAR: _BuilderSpec("adjustable_lumbar"),
    BED_TYPE_ADJUSTAMATTRESS: _BuilderSpec("adjustamattress"),
    BED_TYPE_BEDSENSE: _BuilderSpec("bedsense"),
    BED_TYPE_CASPER_BASE: _BuilderSpec("casper_base"),
    BED_TYPE_RICHMAT_CLASSIC_APPS: _BuilderSpec("richmat_classic"),
    BED_TYPE_COMFORT_ENHANCEMENTS: _BuilderSpec("comfort_enhancements"),
    BED_TYPE_COOLBASE: _BuilderSpec("coolbase"),
    BED_TYPE_DEWERTOKIN: _BuilderSpec("okin_handle"),
    BED_TYPE_DOUBLESLEEP: _BuilderSpec("doublesleep"),
    BED_TYPE_ESHINE_OKIN: _BuilderSpec("eshine_okin"),
    BED_TYPE_FSM_RELAX: _BuilderSpec("fsm_relax"),
    BED_TYPE_FURNIMOVE: _BuilderSpec("furnimove"),
    BED_TYPE_GLIDEAWAY_MOTION: _BuilderSpec("glideaway_motion"),
    BED_TYPE_GMMOTOR: _BuilderSpec("gmmotor"),
    BED_TYPE_GOODVIBE: _BuilderSpec("goodvibe"),
    BED_TYPE_HJBED: _BuilderSpec("hjbed"),
    "hush_base": _BuilderSpec("hush_base"),
    BED_TYPE_JENSEN: _BuilderSpec("jensen"),
    BED_TYPE_JIECANG_APP: _BuilderSpec("jiecang_app"),
    BED_TYPE_KAIDI: _BuilderSpec("kaidi"),
    BED_TYPE_KEESON: _BuilderSpec("keeson"),
    BED_TYPE_LEGGETT_GEN2: _BuilderSpec("leggett_gen2"),
    BED_TYPE_LEGGETT_LP_LEGACY: _BuilderSpec("leggett_lp_legacy"),
    BED_TYPE_LEGGETT_OKIN: _BuilderSpec("leggett_okin"),
    BED_TYPE_LEGGETT_PLATT: _BuilderSpec("leggett_gen2", "build_leggett_platt"),
    BED_TYPE_LIMOSS_REMOTE: _BuilderSpec("limoss_remote"),
    BED_TYPE_LINAK: _BuilderSpec("linak"),
    BED_TYPE_LOGICDATA_APP: _BuilderSpec("logicdata_app"),
    BED_TYPE_MALOUF_APP: _BuilderSpec("malouf_app"),
    BED_TYPE_MOTION_BED: _BuilderSpec("motion_bed"),
    BED_TYPE_MOTOMOTION: _BuilderSpec("motomotion"),
    BED_TYPE_MOTOSLEEP: _BuilderSpec("motosleep"),
    BED_TYPE_OCTO: _BuilderSpec("octo"),
    BED_TYPE_OKIMAT: _BuilderSpec("okin_uuid"),
    BED_TYPE_OKIN_64BIT: _BuilderSpec("okin_64bit"),
    BED_TYPE_OKIN_CB24: _BuilderSpec("okin_cb24"),
    BED_TYPE_OKIN_CST: _BuilderSpec("okin_cst"),
    BED_TYPE_OKIN_DOT: _BuilderSpec("okin_dot"),
    BED_TYPE_OKIN_HANDLE: _BuilderSpec("okin_handle"),
    BED_TYPE_OKIN_UUID: _BuilderSpec("okin_uuid"),
    BED_TYPE_REMACRO: _BuilderSpec("remacro"),
    BED_TYPE_REVERIE: _BuilderSpec("reverie"),
    BED_TYPE_REVERIE_NIGHTSTAND: _BuilderSpec("reverie_nightstand"),
    BED_TYPE_REVERIE_PAIRLINK: _BuilderSpec("reverie_pairlink"),
    BED_TYPE_RICHMAT: _BuilderSpec("richmat"),
    "richmat_sleep_receiver": _BuilderSpec("ruf_richmat_sleep"),
    BED_TYPE_RONDURE: _BuilderSpec("rondure"),
    BED_TYPE_SBI: _BuilderSpec("sbi"),
    BED_TYPE_SIMMONS: _BuilderSpec("simmons"),
    BED_TYPE_SLEEP_NUMBER: _BuilderSpec("sleep_number"),
    BED_TYPE_SLEEP_NUMBER_MCR: _BuilderSpec("sleep_number_mcr"),
    BED_TYPE_SLEEPSTAR: _BuilderSpec("sleepstar"),
    BED_TYPE_SLEEPTRACKER: _BuilderSpec("sleeptracker"),
    BED_TYPE_SLEEPYS_BOX25: _BuilderSpec("sleepys_box25"),
    BED_TYPE_SLEEPYS_ELITE_APP: _BuilderSpec("sleepys_app"),
    BED_TYPE_SOLACE: _BuilderSpec("solace"),
    BED_TYPE_STAR_ELEVATE: _BuilderSpec("star_elevate"),
    BED_TYPE_STARCODE_ABM5_4: _BuilderSpec("starcode_abm5_4"),
    BED_TYPE_STARCODE_M1X12: _BuilderSpec("starcode_m1x12"),
    BED_TYPE_STARCODE_M5X5: _BuilderSpec("starcode_m5x5"),
    BED_TYPE_SVANE: _BuilderSpec("svane"),
    BED_TYPE_VIBRADORM_APP: _BuilderSpec("vibradorm_app"),
    BED_TYPE_VMATBASIC: _BuilderSpec("vmatbasic"),
    BED_TYPE_ZSERIES: _BuilderSpec("serenity", "build_zseries"),
    # Keeson layout app profiles.
    "ergo_slim": _BuilderSpec("ergo_slim"),
    "ergomotion_app": _BuilderSpec("ergomotion_app"),
    "omazz_adjusto_iii": _BuilderSpec("omazz_adjusto_iii"),
    "qplus_app": _BuilderSpec("sbi", "build_qplus"),
    "row_control": _BuilderSpec("row_control"),
    "serta_mp_remote": _BuilderSpec("serta_mp_remote"),
    "tempur_au": _BuilderSpec("tempur_au"),
    "tempur_curve": _BuilderSpec("tempur_curve"),
}


async def _import_bed_module(coordinator: AdjustableBedCoordinator, module: str) -> ModuleType:
    """Import a ``.beds`` module in the import executor (issue #368).

    The executor import fills ``sys.modules``, so the second lookup never blocks.
    """
    name = f".beds.{module}"
    await coordinator.hass.async_add_import_executor_job(import_module, name, __package__)
    return import_module(name, __package__)


async def _create_from_registry(
    coordinator: AdjustableBedCoordinator, bed_type: str
) -> BedController | None:
    """Instantiate ``bed_type`` from its class spec, or None if it has none."""
    spec = _SIMPLE_CONTROLLERS.get(bed_type)
    if spec is None:
        return None
    module = await _import_bed_module(coordinator, spec.module)
    controller_cls: type[BedController] = getattr(module, spec.class_name)
    _LOGGER.debug(
        "Using %s for bed type %s%s",
        spec.class_name,
        bed_type,
        f" ({spec.kwargs})" if spec.kwargs else "",
    )
    return controller_cls(coordinator, **spec.kwargs)


async def create_controller(
    coordinator: AdjustableBedCoordinator,
    bed_type: str,
    protocol_variant: str | None,
    client: BleakClient | None,
    device_name: str | None = None,
    *,
    ble_manufacturer: str | None = None,
    ble_model: str | None = None,
    manufacturer_data: dict[int, bytes] | None = None,
    advertisement_name: str | None = None,
) -> BedController:
    """Create the controller for a bed type, carrying its static traits.

    Everything else a controller needs (PINs, app profiles, stored capability
    snapshots) its builder reads from the config entry.

    Args:
        client: The live link, or None for a client-free controller minted from
            stored configuration.
        device_name: BLE name of the live link, else the display name.
        ble_manufacturer, ble_model: Device Information Service 0x2A29 and 0x2A24.
        manufacturer_data: Last advertisement manufacturer payloads by Company ID.
        advertisement_name: Name in the last advertisement.

    Raises:
        ValueError: If the bed type is unknown or its configuration is invalid.
        ConnectionError: If the route needs a live link that is missing.
    """
    if bed_type == BED_TYPE_LEGGETT_PLATT and protocol_variant in (None, "", VARIANT_AUTO):
        # Resolve the automatic route first, so the controller carries the traits
        # of the protocol it actually speaks.
        protocol_variant = await _detect_leggett_platt_variant(client)
    spec = _BUILDERS.get(bed_type)
    if spec is not None:
        module = await _import_bed_module(coordinator, spec.module)
        builder: ControllerBuilder = getattr(module, spec.function)
        controller = await builder(
            BuildContext(
                coordinator=coordinator,
                bed_type=bed_type,
                variant=protocol_variant,
                client=client,
                device_name=device_name,
                advertisement_name=advertisement_name,
                manufacturer_data=manufacturer_data,
                ble_manufacturer=ble_manufacturer,
                ble_model=ble_model,
            )
        )
    elif (registered := await _create_from_registry(coordinator, bed_type)) is not None:
        controller = registered
    else:
        raise ValueError(f"Unknown bed type: {bed_type}")
    controller.static_traits = bed_traits(bed_type, protocol_variant)
    return controller


async def _detect_leggett_platt_variant(client: BleakClient | None) -> str:
    """Pick MlRM when the WiLinke service is present, otherwise Gen2."""
    if client is None:
        raise ConnectionError("Cannot auto-detect Leggett & Platt variant: no BLE client provided")

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

    wilinke_uuids_lower = [uuid.lower() for uuid in RICHMAT_WILINKE_SERVICE_UUIDS]
    if any(service.uuid.lower() in wilinke_uuids_lower for service in client.services):
        _LOGGER.debug("Auto-detected MlRM Leggett & Platt variant (WiLinke UUID found)")
        return LEGGETT_VARIANT_MLRM
    _LOGGER.debug("Auto-detected Gen2 Leggett & Platt variant (no WiLinke UUID found)")
    return LEGGETT_VARIANT_GEN2

