"""Freshness gate for setup-time BLE probes and pairing attempts.

Home Assistant keeps a bed in its Bluetooth history for a while after the bed
stops advertising, and it hands out a ``BLEDevice`` built from that history. A
bed that has gone to sleep, been unplugged or moved out of range therefore still
*looks* present, and the probe or pairing attempt that follows spends its full
connection timeout failing. Worse, that failure is easy to misread as "pairing
is broken" or "the bond is stale", which is exactly the misdiagnosis issue #459
forbids.

So before any setup-time connection, ask a narrower question than "does Home
Assistant know about this address": *has this bed advertised recently, on a
connectable scanner, with a usable signal reading?* Only then resolve a fresh
``BLEDevice`` and connect.

Two signals matter:

* **Age.** ``BluetoothServiceInfoBleak.time`` is a coarse monotonic timestamp of
  the last advertisement. ``habluetooth`` will keep a connectable record for up
  to ``CONNECTABLE_FALLBACK_MAXIMUM_STALE_ADVERTISEMENT_SECONDS`` (195 s) when it
  has not learned the device's advertising interval, so "present in history" can
  mean "last heard over three minutes ago".
* **RSSI invalidation.** BlueZ reports ``-127`` when it has no valid reading for
  a device — the value ``habluetooth`` also uses as its "no RSSI" sentinel. A
  record carrying it proves the adapter is not currently hearing the bed.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback

from .bluetooth_transport import ConnectionPath, async_path_for_source, async_resolve_ble_device

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)

try:  # pragma: no cover - the fallback only matters if the dep changes
    from bluetooth_data_tools import monotonic_time_coarse as _monotonic
except ImportError:  # pragma: no cover
    _monotonic = time.monotonic

# BlueZ publishes -127 dBm when it has no valid RSSI for a device, and
# habluetooth uses the same value as its "no reading" sentinel. Anything at or
# below it is an absence of evidence, not a weak signal.
RSSI_INVALIDATED: int = -127

# How recently the bed must have advertised for a setup-time connection to be
# worth attempting.
#
# Chosen well below habluetooth's 195 s connectable-history ceiling: within that
# ceiling a record can be almost three minutes old, which is long enough for a
# bed to have been unplugged or gone to sleep. It is also comfortably above the
# advertising intervals seen from bed controllers (typically a few hundred ms
# while awake, and a couple of seconds when idle), so a bed that is genuinely
# present and reachable always passes. The gate only ever refuses a bed that has
# been silent for a minute and a half.
MAX_ADVERTISEMENT_AGE_SECONDS: float = 90.0


# How long to keep listening for a new advertisement before giving up. A bed
# that is merely between advertising intervals should not be reported as absent,
# and unlike everything else here this wait has a known duration, so it is the
# one phase that can honestly drive a determinate progress bar.
ADVERTISEMENT_WAIT_SECONDS: float = 30.0

# How often that wait reports progress while no advertisement arrives.
_PROGRESS_INTERVAL_SECONDS: float = 1.0


class FreshnessStatus(StrEnum):
    """Why a bed is, or is not, worth attempting a connection to right now.

    The failures are kept apart rather than collapsed into one "not seen":
    diagnostics need to distinguish "Home Assistant has never heard of this
    address" from "the record it has carries a timestamp we cannot trust".

    ``DEVICE_UNRESOLVED`` is the odd one out: the advertising evidence was good,
    but no ``BLEDevice`` could be built from it. That is a transient gap rather
    than a silent bed, so it must not be reported as "not advertising".
    """

    FRESH = "fresh"
    STALE = "stale"
    MISSING = "missing"
    RSSI_INVALID = "rssi_invalid"
    INVALID_TIMESTAMP = "invalid_timestamp"
    SOURCE_UNAVAILABLE = "source_unavailable"
    BEFORE_REQUIRED_TIME = "before_required_time"
    DEVICE_UNRESOLVED = "device_unresolved"


@dataclass(frozen=True, slots=True)
class _Sighting:
    """The raw facts a single scanner reports about one address."""

    source: str | None
    rssi: int | None
    seen_at: Any


@dataclass(frozen=True, slots=True)
class AdvertisementEvidence:
    """What Home Assistant currently knows about a bed's advertising."""

    status: FreshnessStatus
    age_seconds: float | None = None
    rssi: int | None = None
    source: str | None = None
    path: ConnectionPath | None = None

    @property
    def is_fresh(self) -> bool:
        """Return True when a connection attempt is justified."""
        return self.status is FreshnessStatus.FRESH

    @property
    def error_key(self) -> str:
        """Return the translation key describing why the bed is unreachable.

        A bed that advertised but could not be resolved into a ``BLEDevice`` is
        reported separately: telling that user the bed is not advertising would
        send them off to wake a bed that is already awake.
        """
        if self.status is FreshnessStatus.DEVICE_UNRESOLVED:
            return "device_unresolved"
        return "not_advertising"


def _coerce_age(raw_time: Any) -> float | None:
    """Return the age in seconds of a monotonic advertisement timestamp.

    Returns None when the timestamp is missing, non-numeric, not finite, or in
    the future — all cases where freshness cannot be proven and therefore must
    not be claimed. ``NaN`` matters specifically because every comparison
    against it is False, so an unchecked ``NaN`` would sail past the age limit.
    """
    try:
        seen_at = float(raw_time)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seen_at):
        return None
    age = _monotonic() - seen_at
    if age < 0:
        # A future timestamp means the record was written against a different
        # clock than ours; treat it as unproven rather than as brand new.
        return None
    return age


def advertisement_time_marker() -> float:
    """Return a marker comparable with advertisement timestamps."""
    return _monotonic()


@callback
def _async_sighting_from_scanner(
    hass: HomeAssistant,
    address: str,
    source: str,
    *,
    connectable: bool = True,
) -> _Sighting | None:
    """Return what one specific scanner last heard from ``address``.

    When a particular adapter or proxy has been chosen, its own view is what
    matters: another scanner still hearing the bed says nothing about whether
    the selected transport can reach it.
    """
    try:
        scanner_devices = bluetooth.async_scanner_devices_by_address(
            hass, address, connectable=connectable
        )
    except Exception:  # noqa: BLE001 - fall back to the merged history
        _LOGGER.debug("Per-scanner freshness lookup failed for %s", address, exc_info=True)
        return None

    for scanner_device in scanner_devices:
        scanner = getattr(scanner_device, "scanner", None)
        if getattr(scanner, "source", None) != source:
            continue
        timestamps = getattr(scanner, "discovered_device_timestamps", None)
        seen_at = timestamps.get(address) if isinstance(timestamps, dict) else None
        return _Sighting(
            source=source,
            rssi=_coerce_rssi(
                getattr(getattr(scanner_device, "advertisement", None), "rssi", None)
            ),
            seen_at=seen_at,
        )
    return None


@callback
def _async_sighting(
    hass: HomeAssistant,
    address: str,
    *,
    connectable: bool = True,
) -> _Sighting | None:
    """Return the newest sighting from the merged history."""
    try:
        service_info = bluetooth.async_last_service_info(
            hass, address, connectable=connectable
        )
    except Exception:  # noqa: BLE001 - absence of a manager is "no evidence"
        _LOGGER.debug("Could not read advertisement history for %s", address, exc_info=True)
        return None
    if service_info is None:
        return None
    return _Sighting(
        source=getattr(service_info, "source", None),
        rssi=_coerce_rssi(getattr(service_info, "rssi", None)),
        seen_at=getattr(service_info, "time", None),
    )


def _coerce_rssi(value: Any) -> int | None:
    """Coerce an advertised RSSI to an int, or None when unusable."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sighting_is_usable(sighting: _Sighting) -> bool:
    """Return True when this sighting could prove the bed is reachable.

    BlueZ publishes -127 to say "I no longer have a reading", which is the one
    RSSI value that disproves rather than supports reachability.
    """
    return sighting.rssi is None or sighting.rssi > RSSI_INVALIDATED


def _newest_sighting(*sightings: _Sighting | None) -> _Sighting | None:
    """Return the freshest sighting, preferring ones that could prove anything.

    Freshest-wins alone is wrong across scanners: one adapter publishing a
    slightly newer -127 invalidation would discard another adapter's valid
    reading a second earlier, and the bed would be reported as not advertising
    while it is sitting there answering. Usable evidence is compared first, and
    an invalidated reading is only returned when it is all there is - it is
    still the honest answer when no scanner can hear the bed.
    """
    available = [sighting for sighting in sightings if sighting is not None]
    if not available:
        return None

    def _freshest(candidates: list[_Sighting]) -> _Sighting | None:
        aged = [
            (age, sighting)
            for sighting in candidates
            if (age := _coerce_age(sighting.seen_at)) is not None
        ]
        if aged:
            return min(aged, key=lambda item: item[0])[1]
        return candidates[0] if candidates else None

    usable = [sighting for sighting in available if _sighting_is_usable(sighting)]
    # Preserve the existing invalid-timestamp result when neither view carries
    # a timestamp that can prove freshness.
    return _freshest(usable) or _freshest(available)


@callback
def async_check_advertisement(
    hass: HomeAssistant,
    address: str,
    *,
    source: str | None = None,
    max_age: float = MAX_ADVERTISEMENT_AGE_SECONDS,
    seen_after: float | None = None,
) -> AdvertisementEvidence:
    """Return whether ``address`` has recent, valid connectable advertising.

    ``source`` restricts the check to one scanner, so a preferred adapter that
    can no longer hear the bed is reported as not advertising even while another
    proxy still sees it.

    ``seen_after`` additionally requires a newer scanner timestamp. This is
    useful after BlueZ removes a device object, when otherwise-fresh history
    still points at the object that was just invalidated.
    """
    normalized = address.upper()
    if source:
        # A proxy can keep a stale connectable snapshot while publishing current
        # advertisements only in its non-connectable view. Compare both so the
        # stale record cannot hide the live one.
        sighting = _newest_sighting(
            _async_sighting_from_scanner(hass, normalized, source),
            _async_sighting_from_scanner(
                hass, normalized, source, connectable=False
            ),
        )
        if sighting is None:
            # The chosen transport cannot see the bed. Report that specifically
            # rather than falling back to a scanner the user did not select: a
            # proxy across the house still hearing the bed says nothing about
            # whether the selected adapter can reach it.
            _LOGGER.debug("Adapter %s can no longer see %s", source, address)
            return AdvertisementEvidence(
                status=FreshnessStatus.SOURCE_UNAVAILABLE, source=source
            )
    else:
        # Some ESPHome proxies have been observed classifying a perfectly
        # connectable bed as non-connectable. Compare both histories because an
        # old connectable snapshot can coexist with a current non-connectable
        # one; falling back only when the first view is empty would reject a bed
        # that is actively advertising.
        sighting = _newest_sighting(
            _async_sighting(hass, normalized),
            _async_sighting(hass, normalized, connectable=False),
        )
        if sighting is None:
            _LOGGER.debug("No advertisement history for %s", address)
            return AdvertisementEvidence(status=FreshnessStatus.MISSING, source=source)

    info_source = sighting.source
    rssi = sighting.rssi
    path = async_path_for_source(hass, info_source, rssi=rssi)
    age = _coerce_age(sighting.seen_at)

    if age is None:
        _LOGGER.debug(
            "Advertisement for %s has no usable timestamp; treating it as unproven", address
        )
        return AdvertisementEvidence(
            status=FreshnessStatus.INVALID_TIMESTAMP,
            rssi=rssi,
            source=info_source or source,
            path=path,
        )

    if seen_after is not None and float(sighting.seen_at) <= seen_after:
        return AdvertisementEvidence(
            status=FreshnessStatus.BEFORE_REQUIRED_TIME,
            age_seconds=age,
            rssi=rssi,
            source=info_source or source,
            path=path,
        )

    if rssi is not None and rssi <= RSSI_INVALIDATED:
        _LOGGER.debug(
            "Advertisement for %s carries an invalidated RSSI (%s dBm)", address, rssi
        )
        return AdvertisementEvidence(
            status=FreshnessStatus.RSSI_INVALID,
            age_seconds=age,
            rssi=rssi,
            source=info_source or source,
            path=path,
        )

    if age > max_age:
        _LOGGER.debug(
            "Last advertisement from %s is %.1fs old (limit %.0fs)", address, age, max_age
        )
        return AdvertisementEvidence(
            status=FreshnessStatus.STALE,
            age_seconds=age,
            rssi=rssi,
            source=info_source or source,
            path=path,
        )

    return AdvertisementEvidence(
        status=FreshnessStatus.FRESH,
        age_seconds=age,
        rssi=rssi,
        source=info_source or source,
        path=path,
    )


@callback
def async_gate_connection(
    hass: HomeAssistant,
    address: str,
    *,
    source: str | None = None,
    max_age: float = MAX_ADVERTISEMENT_AGE_SECONDS,
    seen_after: float | None = None,
) -> tuple[AdvertisementEvidence, BLEDevice | None]:
    """Check freshness and, only if it passes, resolve a current BLEDevice.

    The device is resolved *after* the check and never reused from discovery, so
    a connection attempt always targets the scanner that just heard the bed.

    Guarantees that ``evidence.is_fresh`` implies a device: Home Assistant's
    scanner view can change between the history check and the resolution, and a
    caller told "fresh" while holding ``None`` would have to invent its own
    reason for the failure. That is exactly how a momentary resolution gap ends
    up presented as "this bed is not advertising".
    """
    evidence = async_check_advertisement(
        hass,
        address,
        source=source,
        max_age=max_age,
        seen_after=seen_after,
    )
    if not evidence.is_fresh:
        return evidence, None
    device = async_resolve_ble_device(hass, address, evidence.source or source)
    if device is None:
        return replace(evidence, status=FreshnessStatus.DEVICE_UNRESOLVED), None
    return evidence, device


async def async_wait_for_advertisement(
    hass: HomeAssistant,
    address: str,
    *,
    source: str | None = None,
    max_age: float = MAX_ADVERTISEMENT_AGE_SECONDS,
    seen_after: float | None = None,
    wait_timeout: float = ADVERTISEMENT_WAIT_SECONDS,
    on_progress: Callable[[float], None] | None = None,
) -> tuple[AdvertisementEvidence, BLEDevice | None]:
    """Gate a connection, listening a while longer before giving up.

    A bed that is simply between advertising intervals, or that the user is
    walking over to put into pairing mode, should not be reported as absent on
    the strength of one glance at the history. This waits for a genuinely fresh
    advertisement and only then resolves the device. Every packet Home Assistant
    receives from the address wakes the wait, so it ends on the first fresh one.

    ``on_progress`` receives the fraction of the wait elapsed. It is the only
    honest determinate progress in the whole setup path: the duration really is
    known in advance, unlike a BLE connect.

    When ``seen_after`` is provided, cached history at or before that marker is
    ignored until a later advertisement arrives.
    """

    def gate() -> tuple[AdvertisementEvidence, BLEDevice | None]:
        return async_gate_connection(
            hass, address, source=source, max_age=max_age, seen_after=seen_after
        )

    def report(fraction: float) -> None:
        if on_progress is not None:
            with contextlib.suppress(Exception):
                on_progress(fraction)

    evidence, device = gate()
    if evidence.is_fresh and device is not None:
        return evidence, device
    if wait_timeout <= 0:
        report(1.0)
        return evidence, None

    advertised = asyncio.Event()
    # The callback runs before Home Assistant records the packet, so it only
    # wakes the wait; the gate then reads the updated history.
    unsubscribe = bluetooth.async_register_advertisement_callback(
        hass, lambda _service_info: advertised.set(), address.upper()
    )
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        async with asyncio.timeout(wait_timeout):
            while True:
                report(min(1.0, (loop.time() - started) / wait_timeout))
                with contextlib.suppress(TimeoutError):
                    async with asyncio.timeout(_PROGRESS_INTERVAL_SECONDS):
                        await advertised.wait()
                if not advertised.is_set():
                    continue
                advertised.clear()
                evidence, device = gate()
                if evidence.is_fresh and device is not None:
                    report(1.0)
                    return evidence, device
    except TimeoutError:
        report(1.0)
        return evidence, None
    finally:
        unsubscribe()
