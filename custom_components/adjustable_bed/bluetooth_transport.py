"""Transport-aware view of the Bluetooth paths that can reach a bed.

Home Assistant can reach a bed either through an adapter plugged into the host
(BlueZ) or through a remote scanner such as an ESPHome Bluetooth proxy. The two
are not interchangeable for anything security related: a BLE bond is stored by
whichever transport created it, so a bond made through a proxy is invisible to
the host's BlueZ and vice versa (issue #459).

Everything in this module therefore classifies a path from Home Assistant's own
scanner objects rather than from the shape of the ``source`` string. Substring
tests like ``"esphome" in source`` are wrong in both directions: a proxy from
another integration is not named "esphome", and a local adapter's source is its
MAC address, which merely *looks* remote.

Path ranking mirrors ``habluetooth``'s connection routing (see
``habluetooth.wrappers._async_get_best_available_backend_and_device``): sort the
candidate scanners by advertised RSSI, derive the RSSI gap between the best two,
then re-sort by ``BluetoothScannerDevice.score_connection_path(rssi_diff)``,
which folds in connection slots, in-flight connects and recent failures. Using
the same inputs is what makes the prediction shown during setup match the path
Home Assistant actually takes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.core import HomeAssistant, callback

from .const import ADAPTER_AUTO

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)

# Config-entry domain/keys used to name a remote scanner's owning integration.
_BLUETOOTH_DOMAIN = "bluetooth"
_ESPHOME_DOMAIN = "esphome"
_CONF_SOURCE = "source"
_CONF_SOURCE_DOMAIN = "source_domain"
_CONF_SOURCE_MODEL = "source_model"


class TransportClass(StrEnum):
    """Which kind of Bluetooth transport a connection path uses.

    ``LOCAL`` means an adapter owned by the Home Assistant host, so bonds live in
    the host's BlueZ and are inspectable and removable from here. ``PROXY`` means
    a remote scanner (ESPHome and friends), which owns its own bond store that
    the host cannot read or clear. ``UNKNOWN`` is used when Home Assistant does
    not expose enough information; callers must treat it as "not proven local"
    and never run a host-side destructive action on it.
    """

    LOCAL = "local"
    PROXY = "proxy"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ConnectionPath:
    """One way Home Assistant can currently reach a bed."""

    source: str
    transport: TransportClass = TransportClass.UNKNOWN
    scanner_name: str | None = None
    adapter: str | None = None
    rssi: int | None = None
    connectable: bool = True
    can_connect: bool = True
    score: float | None = None
    source_domain: str | None = None
    source_model: str | None = None

    @property
    def owns_host_bond(self) -> bool:
        """Return True only when a bond over this path is stored by the host.

        Deliberately False for ``UNKNOWN``: a host-side unpair must never run on
        a path we could not prove is local.
        """
        return self.transport is TransportClass.LOCAL

    @property
    def display_name(self) -> str:
        """Return the friendliest identifier we have for this path."""
        return self.scanner_name or self.adapter or self.source


@dataclass(frozen=True, slots=True)
class PathPrediction:
    """What Home Assistant is expected to do, plus the paths it could take.

    ``preferred_adapter`` is what the user *requested*, and requesting is not
    the same as pinning: ``HaBleakClientWrapper`` keeps only the address and
    re-ranks every scanner inside ``connect()``, so a ``BLEDevice`` taken from a
    chosen source does not force Home Assistant to use it. The UI must therefore
    present this as the likely path, never as a guarantee, and the actual path is
    only known once a connection exists.
    """

    chosen: ConnectionPath | None
    paths: tuple[ConnectionPath, ...]
    preferred_adapter: str | None = None
    preferred_available: bool = True

    @property
    def local_alternative(self) -> ConnectionPath | None:
        """Return the best local path when the chosen path is a proxy.

        Surfaced during setup so a user who is about to pair through a proxy can
        see that a host adapter is also in range (issue #456).
        """
        if self.chosen is None or self.chosen.transport is not TransportClass.PROXY:
            return None
        for path in self.paths:
            if path.transport is TransportClass.LOCAL:
                return path
        return None

    @property
    def proxy_pairing_risk(self) -> bool:
        """Return True when a pairing-required bed would pair over a proxy."""
        return self.chosen is not None and self.chosen.transport is TransportClass.PROXY


def classify_scanner(scanner: Any) -> TransportClass:
    """Classify a Home Assistant scanner object as local or remote.

    Two signals are combined because neither alone is reliable.
    ``HaScannerDetails.scanner_type`` is authoritative for ``REMOTE`` (habluetooth
    sets it from the class hierarchy) but degrades to ``UNKNOWN`` for a local
    adapter that is missing from the cached adapter table — and demoting a real
    host adapter to ``UNKNOWN`` would block a legitimate host-side unpair. The
    class check covers exactly that gap.

    The order matters: prove ``PROXY`` first, so a scanner that is somehow both
    is never mistaken for a host adapter.
    """
    try:
        from habluetooth import BaseHaRemoteScanner, HaScanner
    except ImportError:  # pragma: no cover - habluetooth ships with HA
        BaseHaRemoteScanner = HaScanner = None  # type: ignore[assignment]

    if BaseHaRemoteScanner is not None and isinstance(scanner, BaseHaRemoteScanner):
        return TransportClass.PROXY

    scanner_type = getattr(getattr(scanner, "details", None), "scanner_type", None)
    value = getattr(scanner_type, "value", scanner_type)
    if value == "remote":
        return TransportClass.PROXY

    if HaScanner is not None and isinstance(scanner, HaScanner):
        return TransportClass.LOCAL
    if value in ("usb", "uart"):
        return TransportClass.LOCAL

    return TransportClass.UNKNOWN


def _can_connect(scanner: Any, transport: TransportClass) -> bool:
    """Return whether this scanner could take a connection right now.

    Home Assistant skips a remote scanner whose connector reports no free slot,
    and a local adapter that cannot allocate one. Reflecting that here keeps a
    prediction from naming a path Home Assistant would immediately reject.
    Unknowable means "assume yes": refusing to show a usable path is worse than
    showing one that turns out to be busy.
    """
    if transport is TransportClass.PROXY:
        connector = getattr(scanner, "connector", None)
        checker = getattr(connector, "can_connect", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:  # noqa: BLE001 - advisory only
                return True
        return True

    allocations = getattr(scanner, "get_allocations", None)
    if callable(allocations):
        try:
            allocation = allocations()
        except Exception:  # noqa: BLE001 - advisory only
            return True
        slots = getattr(allocation, "slots", 0) or 0
        if slots > 0:
            return bool(getattr(allocation, "free", 0))
    return True


@callback
def async_scanner_registrations(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    """Return the bluetooth config-entry data for each registered scanner source.

    Remote scanners are registered by their owning integration (ESPHome, Shelly,
    …), and that registration is the only place the owning domain and model are
    recorded. Used for labelling and to recognise ESPHome proxies.
    """
    registrations: dict[str, dict[str, Any]] = {}
    try:
        entries = hass.config_entries.async_entries(_BLUETOOTH_DOMAIN)
    except Exception:  # noqa: BLE001 - labelling must never break setup
        return registrations
    for entry in entries:
        source = entry.data.get(_CONF_SOURCE)
        if isinstance(source, str):
            registrations[source] = dict(entry.data)
    return registrations


def _rssi(value: Any) -> int | None:
    """Coerce an advertised RSSI to an int, or None when unusable."""
    try:
        rssi = int(value)
    except (TypeError, ValueError):
        return None
    return rssi


def _sort_rssi(scanner_device: Any) -> int:
    """Return a sortable RSSI for a scanner device (missing sorts last)."""
    rssi = _rssi(getattr(getattr(scanner_device, "advertisement", None), "rssi", None))
    # habluetooth uses -127 as its "no RSSI" sentinel; match it so a device with
    # no reading never outranks one with a real, weak reading.
    return rssi if rssi is not None else -127


def _score(scanner_device: Any, rssi_diff: int) -> float | None:
    """Return HA's own connection-path score, or None when unavailable."""
    scorer = getattr(scanner_device, "score_connection_path", None)
    if not callable(scorer):
        return None
    try:
        score: Any = scorer(rssi_diff)
        return float(score)
    except Exception:  # noqa: BLE001 - scoring is advisory
        _LOGGER.debug("Could not score connection path", exc_info=True)
        return None


def _path_from_scanner_device(
    scanner_device: Any,
    registrations: dict[str, dict[str, Any]],
    score: float | None,
) -> ConnectionPath | None:
    """Build a ConnectionPath from one habluetooth BluetoothScannerDevice."""
    scanner = getattr(scanner_device, "scanner", None)
    if scanner is None:
        return None
    source = getattr(scanner, "source", None)
    if not isinstance(source, str) or not source:
        return None
    registration = registrations.get(source, {})
    transport = classify_scanner(scanner)
    return ConnectionPath(
        source=source,
        transport=transport,
        scanner_name=getattr(scanner, "name", None) or None,
        adapter=getattr(scanner, "adapter", None) or None,
        rssi=_rssi(getattr(getattr(scanner_device, "advertisement", None), "rssi", None)),
        connectable=bool(getattr(scanner, "connectable", True)),
        can_connect=_can_connect(scanner, transport),
        score=score,
        source_domain=registration.get(_CONF_SOURCE_DOMAIN),
        source_model=registration.get(_CONF_SOURCE_MODEL),
    )


@callback
def async_connection_paths(hass: HomeAssistant, address: str) -> tuple[ConnectionPath, ...]:
    """Return every connection path Home Assistant may use, best first.

    The ordering reproduces ``habluetooth``'s routing: RSSI first, then a
    re-sort by ``score_connection_path`` using the gap between the two strongest
    signals, so slot exhaustion and recent failures move a path down exactly as
    they would during a real connect. When the connectable view is empty, use
    the same non-connectable fallback as device resolution for proxies that
    misclassify an otherwise connectable bed.
    """
    try:
        scanner_devices = list(
            bluetooth.async_scanner_devices_by_address(hass, address.upper(), connectable=True)
        )
    except Exception:  # noqa: BLE001 - a missing manager must not block setup
        _LOGGER.debug("Could not enumerate scanners for %s", address, exc_info=True)
        return ()

    if not scanner_devices:
        try:
            scanner_devices = list(
                bluetooth.async_scanner_devices_by_address(
                    hass, address.upper(), connectable=False
                )
            )
        except Exception:  # noqa: BLE001 - a missing manager must not block setup
            _LOGGER.debug(
                "Could not enumerate fallback scanners for %s", address, exc_info=True
            )
            return ()
        if not scanner_devices:
            return ()

    scanner_devices.sort(key=_sort_rssi, reverse=True)
    rssi_diff = 0
    scores: dict[int, float | None] = {}
    if len(scanner_devices) > 1:
        rssi_diff = _sort_rssi(scanner_devices[0]) - _sort_rssi(scanner_devices[1])
        scored = [(_score(device, rssi_diff), device) for device in scanner_devices]
        scores = {id(device): score for score, device in scored}
        # Keep the RSSI order for any device HA could not score, rather than
        # letting a None score reshuffle the list.
        if all(score is not None for score, _ in scored):
            ranked: list[tuple[float, Any]] = [
                (score, device) for score, device in scored if score is not None
            ]
            ranked.sort(key=lambda item: item[0], reverse=True)
            scanner_devices = [device for _, device in ranked]

    registrations = async_scanner_registrations(hass)
    paths: list[ConnectionPath] = []
    for device in scanner_devices:
        device_id = id(device)
        score = scores[device_id] if device_id in scores else _score(device, rssi_diff)
        path = _path_from_scanner_device(device, registrations, score)
        if path is not None:
            paths.append(path)
    return tuple(paths)


@callback
def async_predict_path(
    hass: HomeAssistant,
    address: str,
    preferred_adapter: str | None = None,
) -> PathPrediction:
    """Predict which path Home Assistant will use for the next connection.

    Home Assistant re-ranks every connectable scanner inside ``connect()``, so
    selecting an adapter does not pin the connection to it. Preserve that
    selection as requested metadata and report whether it is available, while
    always deriving ``chosen`` from the same automatic ranking as the wrapper.
    """
    paths = async_connection_paths(hass, address)
    if not paths:
        return PathPrediction(
            chosen=None,
            paths=(),
            preferred_adapter=preferred_adapter,
            preferred_available=False,
        )

    preferred_available = True
    if preferred_adapter and preferred_adapter != ADAPTER_AUTO:
        preferred_available = any(
            path.source == preferred_adapter and path.can_connect for path in paths
        )

    return PathPrediction(
        chosen=_first_usable(paths),
        paths=paths,
        preferred_adapter=preferred_adapter,
        preferred_available=preferred_available,
    )


def _first_usable(paths: tuple[ConnectionPath, ...]) -> ConnectionPath | None:
    """Return the best path that could take a connection now.

    Mirrors Home Assistant, which walks its ranked list and skips any scanner
    with no free connection slot. If every path is busy the best-ranked one is
    still returned: "all adapters are full" is a truer prediction than "no path".
    """
    for path in paths:
        if path.can_connect:
            return path
    return paths[0] if paths else None


@callback
def async_path_for_source(
    hass: HomeAssistant,
    source: str | None,
    *,
    rssi: int | None = None,
) -> ConnectionPath | None:
    """Resolve the path actually used, given the source a connection reported.

    Called after a connect so the UI and diagnostics can show the real transport
    rather than only the prediction.
    """
    if not source or source == "unknown":
        return None
    try:
        scanner = bluetooth.async_scanner_by_source(hass, source)
    except Exception:  # noqa: BLE001 - diagnostics must not raise
        scanner = None
    if scanner is None:
        return ConnectionPath(source=source, rssi=rssi)
    registration = async_scanner_registrations(hass).get(source, {})
    return ConnectionPath(
        source=source,
        transport=classify_scanner(scanner),
        scanner_name=getattr(scanner, "name", None) or None,
        adapter=getattr(scanner, "adapter", None) or None,
        rssi=rssi,
        connectable=bool(getattr(scanner, "connectable", True)),
        source_domain=registration.get(_CONF_SOURCE_DOMAIN),
        source_model=registration.get(_CONF_SOURCE_MODEL),
    )


@callback
def async_resolve_ble_device(
    hass: HomeAssistant,
    address: str,
    source: str | None = None,
) -> BLEDevice | None:
    """Return a freshly resolved BLEDevice, preferring a specific scanner.

    Never reuse the ``BLEDevice`` captured during discovery: Home Assistant
    replaces it as advertisements arrive, and a frozen one can point at a
    scanner that has since stopped seeing the bed (issue #458).
    """
    normalized = address.upper()
    if source and source != ADAPTER_AUTO:
        for connectable in (True, False):
            try:
                for scanner_device in bluetooth.async_scanner_devices_by_address(
                    hass, normalized, connectable=connectable
                ):
                    scanner_source = getattr(
                        getattr(scanner_device, "scanner", None), "source", None
                    )
                    if scanner_source == source:
                        return getattr(scanner_device, "ble_device", None)
            except Exception:  # noqa: BLE001 - fall through to the generic lookup
                _LOGGER.debug(
                    "Scanner-specific lookup failed for %s", address, exc_info=True
                )
    for connectable in (True, False):
        try:
            device = bluetooth.async_ble_device_from_address(
                hass, normalized, connectable=connectable
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Could not resolve a BLE device for %s", address, exc_info=True)
            continue
        if device is not None:
            return device
    return None


def client_source(client: Any) -> str | None:
    """Return the scanner source a connected client is actually routed through.

    This is the only reliable moment to learn the real transport: Home Assistant
    chooses it inside ``connect()``, after every prediction has been made. Ask
    the wrapper for the scanner it settled on, and fall back to the backend
    device's details for a plain bleak client.
    """
    scanner_source = getattr(getattr(client, "_connected_scanner", None), "source", None)
    if isinstance(scanner_source, str) and scanner_source:
        return scanner_source

    details = getattr(getattr(getattr(client, "_backend", None), "_device", None), "details", None)
    if isinstance(details, dict):
        source = details.get("source")
        if isinstance(source, str) and source:
            return source
    return None


async def async_clear_proxy_gatt_cache(client: Any, path: ConnectionPath | None) -> bool:
    """Drop the cached GATT table of a bed reached through an ESPHome proxy.

    The proxy keeps a bonded device's table in flash, Home Assistant keeps
    another copy in memory, and neither honours ``use_services_cache=False``.
    A bed that lays out its characteristics differently after a reboot then
    gets reads and writes on the wrong handles, which looks exactly like a lost
    bond (issue #660). Clearing needs the live link; the next connection
    rediscovers. Limited to ESPHome because Home Assistant's wrapper falls back
    to BlueZ ``RemoveDevice`` for other backends, which deletes a host bond.
    """
    if (
        path is None
        or path.transport is not TransportClass.PROXY
        or path.source_domain != _ESPHOME_DOMAIN
        or not getattr(client, "is_connected", False)
    ):
        return False
    try:
        cleared = bool(await client.clear_cache())
    except Exception:  # noqa: BLE001 - best effort; the caller already has its failure
        _LOGGER.debug("Could not clear the proxy GATT cache via %s", path.source, exc_info=True)
        return False
    if cleared:
        _LOGGER.warning(
            "Cleared the cached GATT services for this bed on %s; "
            "the next connection rediscovers them",
            path.display_name,
        )
    return cleared


def path_from_service_info(
    hass: HomeAssistant,
    service_info: BluetoothServiceInfoBleak | None,
) -> ConnectionPath | None:
    """Build a path from an advertisement snapshot (used by the freshness gate)."""
    if service_info is None:
        return None
    return async_path_for_source(
        hass,
        getattr(service_info, "source", None),
        rssi=_rssi(getattr(service_info, "rssi", None)),
    )


# --- User-facing description -------------------------------------------------
#
# The sentences live in ``strings.json`` under the discovery step's
# ``data_description`` (the same place this integration already keeps its
# pairing instructions), because hassfest only allows ``flow_title``, ``step``,
# ``error``, ``abort``, ``progress`` and ``create_entry`` under ``config``.
# Only the dynamic parts — scanner name, signal, adapter id — are interpolated
# here; the prose itself is translated.

_TRANSPORT_STRINGS_PREFIX = "step.bluetooth_confirm.data_description"

_DEFAULT_STRINGS: dict[str, str] = {
    "transport_direct": "Direct Bluetooth",
    "transport_proxy": "Bluetooth proxy",
    "transport_unknown": "Bluetooth",
    "transport_likely": "Likely connection: {kind} · {scanner}{signal}",
    "transport_signal": "· {rssi} dBm",
    "transport_none": (
        "⚠️ No Bluetooth adapter or proxy can currently see this device. "
        "You can still finish setup; Home Assistant will connect when it "
        "appears."
    ),
    "transport_local_alternative": (
        # Deliberately does not claim the local signal is weaker. Home Assistant
        # ranks paths on connection slots and recent failures as well as signal,
        # so a proxy can win while the host adapter is in fact stronger. The
        # translations carry this same wording.
        "A Bluetooth adapter on this Home Assistant host ({scanner}) can also "
        "see it."
    ),
    "transport_preferred_unavailable": (
        "⚠️ The selected adapter ({adapter}) is not currently available for this "
        "connection. Select Automatic to let Home Assistant choose another path, "
        "or restore the selected adapter before continuing."
    ),
    "transport_not_guaranteed": (
        "Home Assistant picks the path when it connects, so this is a "
        "prediction rather than a guarantee."
    ),
    "transport_proxy_pairing_warning": (
        "⚠️ This bed needs Bluetooth pairing, and pairing over a proxy stores "
        "the bond on the proxy rather than on Home Assistant. If you later move "
        "the bed to a different proxy or to a Home Assistant adapter, you will "
        "have to pair again. Home Assistant also cannot remove a bond that "
        "lives on a proxy."
    ),
    "transport_all_busy": (
        "⚠️ Every adapter that can see this device is currently out of free "
        "Bluetooth connections."
    ),
    "transport_actual": "Connected over: {kind} · {scanner}{signal}",
    "transport_actual_differs": (
        "Home Assistant used a different path than predicted ({predicted})."
    ),
}


async def _async_string(hass: HomeAssistant, key: str) -> str:
    """Return a translated fragment, falling back to English."""
    default = _DEFAULT_STRINGS[key]
    try:
        from homeassistant.helpers.translation import async_get_translations

        from .const import DOMAIN

        translations = await async_get_translations(
            hass, hass.config.language, "config", {DOMAIN}
        )
    except Exception:  # noqa: BLE001 - a missing translation must not block setup
        return default
    return translations.get(
        f"component.{DOMAIN}.config.{_TRANSPORT_STRINGS_PREFIX}.{key}", default
    )


async def _async_kind(hass: HomeAssistant, path: ConnectionPath) -> str:
    """Return the localized name of a path's transport class."""
    key = {
        TransportClass.LOCAL: "transport_direct",
        TransportClass.PROXY: "transport_proxy",
    }.get(path.transport, "transport_unknown")
    return await _async_string(hass, key)


async def _async_describe_path(hass: HomeAssistant, path: ConnectionPath, key: str) -> str:
    """Render one path as "<kind> · <scanner> · <rssi> dBm"."""
    signal = ""
    if path.rssi is not None:
        # The separator lives here rather than in the string, because hassfest
        # rejects translation values with leading or trailing spaces.
        signal = " " + (await _async_string(hass, "transport_signal")).format(
            rssi=path.rssi
        )
    return (await _async_string(hass, key)).format(
        kind=await _async_kind(hass, path),
        scanner=path.display_name,
        signal=signal,
    )


async def async_describe_prediction(
    hass: HomeAssistant,
    prediction: PathPrediction,
    *,
    pairing_required: bool = False,
) -> str:
    """Describe the path setup is expected to take, and its consequences.

    Recomputed on every render rather than cached: scanner visibility changes
    from one moment to the next, and a stale prediction is worse than none.
    """
    chosen = prediction.chosen
    if chosen is None:
        return await _async_string(hass, "transport_none")

    lines = [await _async_describe_path(hass, chosen, "transport_likely")]

    if not prediction.preferred_available and prediction.preferred_adapter:
        lines.append(
            (await _async_string(hass, "transport_preferred_unavailable")).format(
                adapter=prediction.preferred_adapter
            )
        )

    if not any(path.can_connect for path in prediction.paths):
        lines.append(await _async_string(hass, "transport_all_busy"))

    local_alternative = prediction.local_alternative
    if local_alternative is not None:
        lines.append(
            (await _async_string(hass, "transport_local_alternative")).format(
                scanner=local_alternative.display_name
            )
        )

    if pairing_required and prediction.proxy_pairing_risk:
        lines.append(await _async_string(hass, "transport_proxy_pairing_warning"))

    lines.append(await _async_string(hass, "transport_not_guaranteed"))
    return "\n".join(lines)


async def async_describe_actual(
    hass: HomeAssistant,
    actual: ConnectionPath,
    predicted: ConnectionPath | None = None,
) -> str:
    """Describe the path a connection really used, noting any surprise."""
    lines = [await _async_describe_path(hass, actual, "transport_actual")]
    if predicted is not None and predicted.source != actual.source:
        lines.append(
            (await _async_string(hass, "transport_actual_differs")).format(
                predicted=predicted.display_name
            )
        )
    return "\n".join(lines)
