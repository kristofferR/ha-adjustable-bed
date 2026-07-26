"""Support report generation for the Adjustable Bed integration."""

from __future__ import annotations

import logging
import os
import re
import stat
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .adapter import find_service_info_by_address
from .const import (
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_KAIDI_ADV_TYPE,
    CONF_KAIDI_PRODUCT_ID,
    CONF_KAIDI_RESOLVED_VARIANT,
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_KAIDI_TARGET_VADDR,
    CONF_KAIDI_VARIANT_SOURCE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SUPPORTED_BED_TYPES,
    connection_gated_by_bond,
    requires_pairing,
)
from .diagnostics_utils import get_gatt_summary
from .kaidi_protocol import extract_kaidi_advertisement, kaidi_advertisement_to_dict
from .redaction import redact_data, redact_pins_only

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# Maximum number of log entries to include
MAX_LOG_ENTRIES = 100

# How much of the tail of home-assistant.log to scan (bytes). Debug runs are
# verbose, so keep enough history to cover a reproduction without reading the
# whole (potentially multi-MB) file.
_LOG_TAIL_BYTES = 512 * 1024

# Standard Home Assistant log line:
#   2026-06-24 13:26:56.557 DEBUG (MainThread) [logger.name] message
_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[.,]\d+) "
    r"(?P<level>[A-Z]+) "
    r"\([^)]*\) "
    r"\[(?P<name>[^\]]+)\] "
    r"(?P<msg>.*)$"
)

# Logger-name fragments worth keeping for bed debugging.
_RELEVANT_LOG_NAMES = (DOMAIN, "bluetooth", "bleak", "habluetooth")


async def generate_support_report(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator,
    *,
    include_logs: bool = True,
) -> dict[str, Any]:
    """Generate a comprehensive support report."""
    timestamp = datetime.now(UTC)

    # Get integration version from manifest
    integration = await async_get_integration(hass, DOMAIN)
    integration_version = str(integration.version) if integration.version is not None else "unknown"

    report: dict[str, Any] = {
        "report_version": "1.2",
        "generated_at": timestamp.isoformat(),
        "system": _get_system_info(hass, integration_version),
        "integration": _get_integration_info(entry),
        "connection": _get_connection_info(coordinator),
        "connection_history": coordinator.connection_history,
        "pairing": _get_pairing_info(entry, coordinator),
        "adapter": coordinator.adapter_details,
        "command_timing": coordinator.command_timing,
        "bluetooth": await _get_bluetooth_info(hass, coordinator),
        "gatt_summary": get_gatt_summary(coordinator),
        "controller": _get_controller_info(coordinator),
        "position_data": dict(coordinator.position_data),
        "supported_bed_types": list(SUPPORTED_BED_TYPES),
    }

    if include_logs:
        report["recent_logs"] = await _get_recent_logs(hass)

    # Redact sensitive data (partial MAC redaction - keeps OUI for debugging)
    return redact_data(report)  # type: ignore[no-any-return]


def _get_system_info(hass: HomeAssistant, integration_version: str) -> dict[str, Any]:
    """Get system information."""
    return {
        "integration_version": integration_version,
        "home_assistant_version": HA_VERSION,
        "python_version": sys.version,
        "os": sys.platform,
        "timezone": str(hass.config.time_zone),
    }


def _get_integration_info(entry: ConfigEntry) -> dict[str, Any]:
    """Get integration configuration info."""
    return {
        "entry_id": entry.entry_id,
        "version": entry.version,
        "title": entry.title,
        "bed_type": entry.data.get(CONF_BED_TYPE),
        "protocol_variant": entry.data.get(CONF_PROTOCOL_VARIANT, "auto"),
        "motor_count": entry.data.get(CONF_MOTOR_COUNT),
        "has_massage": entry.data.get(CONF_HAS_MASSAGE),
        "disable_angle_sensing": entry.data.get(CONF_DISABLE_ANGLE_SENSING),
        "preferred_adapter": entry.data.get(CONF_PREFERRED_ADAPTER),
        "ble_bond_established": entry.data.get(CONF_BLE_BOND_ESTABLISHED),
        "address": entry.data.get(CONF_ADDRESS),
        "kaidi_room_id": entry.data.get(CONF_KAIDI_ROOM_ID),
        "kaidi_target_vaddr": entry.data.get(CONF_KAIDI_TARGET_VADDR),
        "kaidi_product_id": entry.data.get(CONF_KAIDI_PRODUCT_ID),
        "kaidi_sofa_acu_no": entry.data.get(CONF_KAIDI_SOFA_ACU_NO),
        "kaidi_adv_type": entry.data.get(CONF_KAIDI_ADV_TYPE),
        "kaidi_resolved_variant": entry.data.get(CONF_KAIDI_RESOLVED_VARIANT),
        "kaidi_variant_source": entry.data.get(CONF_KAIDI_VARIANT_SOURCE),
    }


def _get_connection_info(coordinator: AdjustableBedCoordinator) -> dict[str, Any]:
    """Get connection state information."""
    is_connected = coordinator.is_connected
    client = coordinator.client

    info: dict[str, Any] = {
        "is_connected": is_connected,
        "is_connecting": coordinator.is_connecting,
    }

    if client and is_connected:
        info.update(
            {
                "mtu_size": getattr(client, "mtu_size", None),
                "services_discovered": len(list(client.services)) if client.services else 0,
            }
        )

        # Get service UUIDs
        if client.services:
            info["service_uuids"] = [str(service.uuid) for service in client.services]

    return info


def _get_pairing_info(
    entry: ConfigEntry | None,
    coordinator: AdjustableBedCoordinator | None = None,
    *,
    diagnostic_backend: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Consolidate integration and Bluetooth-backend pairing diagnostics."""
    if coordinator is not None:
        info = coordinator.pairing_diagnostics
    else:
        bed_type = entry.data.get(CONF_BED_TYPE) if entry is not None else None
        protocol_variant = (
            entry.data.get(CONF_PROTOCOL_VARIANT) if entry is not None else None
        )
        info = {
            "required": requires_pairing(bed_type, protocol_variant) if bed_type else None,
            "connection_gated_by_bond": (
                connection_gated_by_bond(bed_type, protocol_variant) if bed_type else None
            ),
            "persisted_bond_marker": (
                bool(entry.data.get(CONF_BLE_BOND_ESTABLISHED, False))
                if entry is not None
                else None
            ),
            "runtime_bond_established": None,
            "adapter_pairing_supported": None,
            "transient_skip_next_attempt": None,
            "bond_probe_timed_out": None,
            "last_bond_verification": None,
            "backend_reports": [],
            "connection_attempts": [],
        }

    if diagnostic_backend is not None:
        info["diagnostic_backend"] = dict(diagnostic_backend)
    return info


def _get_controller_info(coordinator: AdjustableBedCoordinator) -> dict[str, Any]:
    """Get controller information."""
    info: dict[str, Any] = {"initialized": coordinator.controller is not None}

    if coordinator.controller:
        controller = coordinator.controller
        info.update(
            {
                "class": type(controller).__name__,
                "characteristic_uuid": controller.control_characteristic_uuid,
            }
        )

        # Add variant info for controllers that have it
        is_wilinke = getattr(controller, "_is_wilinke", None)
        if is_wilinke is not None:
            info["richmat_is_wilinke"] = is_wilinke
        variant = getattr(controller, "_variant", None)
        if variant is not None:
            info["variant"] = variant
        variant_source = getattr(controller, "_variant_source", None)
        if variant_source is not None:
            info["variant_source"] = variant_source
        char_uuid = getattr(controller, "_char_uuid", None)
        if char_uuid is not None:
            info["char_uuid"] = char_uuid

        # Whatever the connect-time protocol handshake resolved to (capabilities,
        # authentication state, ...). Empty for controllers with no handshake.
        protocol_state = controller.protocol_diagnostics
        if protocol_state:
            info["protocol_state"] = protocol_state

    return info


async def _get_bluetooth_info(
    hass: HomeAssistant, coordinator: AdjustableBedCoordinator
) -> dict[str, Any]:
    """Get Bluetooth adapter and advertisement information."""
    info: dict[str, Any] = {}

    # Get last known advertisement data
    service_info, service_info_connectable = find_service_info_by_address(
        hass,
        coordinator.address,
        allow_non_connectable=True,
    )
    if service_info:
        # Guard against None values for optional BLE advertisement fields
        service_uuids = service_info.service_uuids or []
        manufacturer_data = service_info.manufacturer_data or {}
        service_data = service_info.service_data or {}

        info["last_advertisement"] = {
            "captured_at": datetime.now(UTC).isoformat(),
            "device_name": service_info.name,
            "rssi": getattr(service_info, "rssi", None),
            "service_uuids": [str(uuid) for uuid in service_uuids],
            "manufacturer_data": {str(k): bytes(v).hex() for k, v in manufacturer_data.items()},
            "service_data": {str(k): bytes(v).hex() for k, v in service_data.items()},
            "connectable": service_info_connectable,
        }
        kaidi_advertisement = extract_kaidi_advertisement(manufacturer_data)
        if kaidi_advertisement is not None:
            info["last_advertisement"]["kaidi"] = kaidi_advertisement_to_dict(
                kaidi_advertisement
            )
        # Include source info (adapter/proxy)
        if hasattr(service_info, "source"):
            info["last_advertisement"]["source"] = service_info.source
    else:
        info["last_advertisement"] = None

    # Get scanner/adapter info if available
    try:
        # Use async_current_scanners which is available in modern HA versions
        scanners = bluetooth.async_current_scanners(hass)
        info["scanners"] = [
            {
                "source": getattr(scanner, "source", "unknown"),
                "name": getattr(scanner, "name", "unknown"),
                "scanning": getattr(scanner, "scanning", None),
                "connector": type(getattr(scanner, "connector", None)).__name__
                if hasattr(scanner, "connector")
                else None,
            }
            for scanner in scanners
        ]
    except Exception as err:
        info["scanners_error"] = str(err)

    return info


async def _get_recent_logs(hass: HomeAssistant) -> list[dict[str, str]]:
    """Return recent integration-related entries from the HA log file.

    Home Assistant does not keep an in-memory debug-log buffer we can read, so
    this tails the on-disk ``home-assistant.log`` (off-loop, in an executor) and
    keeps only lines emitted by the integration, the Bluetooth stack, or bleak.
    """
    log_path = hass.config.path("home-assistant.log")
    return await hass.async_add_executor_job(_read_log_file, log_path)


def _is_relevant_log_name(name: str) -> bool:
    """Return True if a logger name belongs to the bed/Bluetooth stack."""
    lowered = name.lower()
    return any(fragment in lowered for fragment in _RELEVANT_LOG_NAMES)


class _NotARegularFile(OSError):
    """The log path exists but is a FIFO, device, or similar."""


def _open_regular_file(log_path: str) -> int:
    """Open ``log_path`` read-only and return a validated file descriptor.

    Raises ``_NotARegularFile`` for a FIFO or device and ``OSError`` for
    anything else; the caller owns the descriptor on success.

    This is the one copy of the hang-prevention rule, because two copies of
    safety-critical logic drift. ``O_NONBLOCK`` stops a FIFO open from waiting
    for a writer, and ``fstat`` describes the object actually opened, so the
    type check cannot be raced by a path swapped after a bare ``stat``.
    """
    # Check before opening as well as after. O_NONBLOCK keeps *us* from waiting
    # on a FIFO, but opening its read end can release a writer that was blocked
    # waiting for a reader, and closing again immediately can then hand that
    # writer EPIPE - disrupting the very log stream this is inspecting. Refuse
    # special files without touching them.
    # stat, not lstat: a symlink pointing at a real log file is a legitimate
    # setup and must be followed, while a symlink to a FIFO resolves to the FIFO
    # and is refused on its own merits.
    if not stat.S_ISREG(os.stat(log_path).st_mode):  # noqa: PTH116 - HA config path
        raise _NotARegularFile(f"{log_path} is not a regular file")

    fd = os.open(log_path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        # Re-check on the descriptor: the pre-check above races with anything
        # that could swap the path between the two calls.
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise _NotARegularFile(f"{log_path} is not a regular file")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _tail_text(log_path: str, max_bytes: int) -> str:
    """Read up to the last ``max_bytes`` of a UTF-8 log file as text.

    Refuses anything that is not a regular file: opening a FIFO blocks until a
    writer appears, which would hang the capture in its executor thread.
    """
    fd = _open_regular_file(log_path)
    try:
        handle = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise
    with handle:
        handle.seek(0, 2)
        size = handle.tell()
        start = max(0, size - max_bytes)
        handle.seek(start)
        data = handle.read()
    # If we seeked into the middle of the file, drop the partial first line.
    if start > 0:
        newline = data.find(b"\n")
        if newline != -1:
            data = data[newline + 1 :]
    return data.decode("utf-8", errors="replace")


def _read_log_file(log_path: str) -> list[dict[str, str]]:
    """Parse relevant entries out of the tail of the HA log file.

    Runs in an executor (blocking file I/O). Continuation lines (e.g. traceback
    bodies) are appended to the entry they belong to so multi-line records stay
    readable.
    """
    try:
        raw = _tail_text(log_path, _LOG_TAIL_BYTES)
    except OSError as err:
        _LOGGER.debug("Could not read %s: %s", log_path, err)
        # A missing file and an unreadable one need different remedies, so keep
        # the distinction (and the original error) instead of always blaming
        # disabled logging.
        # A FIFO (a container logging to stdout) needs the same remedy as a
        # missing file: a real log to download, not a permissions fix.
        missing = isinstance(err, FileNotFoundError | _NotARegularFile)
        hint = (
            "File logging may be disabled; enable it and reproduce the issue to "
            "capture logs."
            if missing
            else "The log file exists but could not be read; check its permissions "
            "and the configured log path."
        )
        return [
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": "INFO",
                "name": DOMAIN,
                "message": f"Could not read {log_path}: {err}. {hint}",
                "log_read_error": str(err),
                "log_read_reason": "missing" if missing else "unreadable",
            }
        ]

    logs: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in raw.splitlines():
        match = _LOG_LINE_RE.match(line)
        if match:
            if not _is_relevant_log_name(match.group("name")):
                current = None
                continue
            # Only redact PINs — MACs/names are needed for debugging and the
            # caller applies its own MAC redaction over the whole report.
            current = {
                "timestamp": match.group("ts"),
                "level": match.group("level"),
                "name": match.group("name"),
                "message": redact_pins_only({"msg": match.group("msg")})["msg"],
            }
            logs.append(current)
        elif current is not None:
            # Continuation of the current (relevant) entry, e.g. a traceback.
            current["message"] += "\n" + redact_pins_only({"msg": line})["msg"]

    return logs[-MAX_LOG_ENTRIES:]


def _probe_log_file(log_path: str) -> tuple[bool, str | None, str | None]:
    """Return ``(available, reason, error)`` for the Home Assistant log file.

    Runs in an executor (blocking file I/O). ``reason`` is ``"missing"``,
    ``"not_a_file"`` or ``"unreadable"`` when the file cannot be used.

    ``os.stat`` comes first and the file is never read. If the path is a FIFO or
    a device - which is exactly what a container redirecting its logs to stdout
    can leave behind - then ``open()`` alone blocks until a writer appears, and
    a read would also consume a byte of somebody else's stream. Statting cannot
    block, so the hazard is settled before anything is opened.
    """
    try:
        fd = _open_regular_file(log_path)
    except FileNotFoundError as err:
        return False, "missing", str(err)
    except _NotARegularFile as err:
        return False, "not_a_file", str(err)
    except OSError as err:
        # Covers fstat as well as open: every failure has to degrade into a
        # reason, because the caller probes outside its own error handling.
        return False, "unreadable", str(err)

    try:
        size = os.fstat(fd).st_size
    except OSError as err:
        return False, "unreadable", str(err)
    finally:
        os.close(fd)

    if size == 0:
        # A left-over empty file while the running instance logs to stdout is
        # readable but will never yield evidence, so readability alone is not
        # proof that logs will be captured. Home Assistant writes its startup
        # banner immediately, so an empty file means nothing is writing here.
        # Deliberately no mtime "liveness" check: a quiet instance can go a long
        # time without a record, and a threshold would misreport it.
        return False, "empty_file", f"{log_path} is empty"
    return True, None, None


async def async_check_log_file(hass: HomeAssistant) -> dict[str, Any]:
    """Check up front whether a support bundle will be able to include logs.

    The capture itself takes minutes, and a bundle without logs is missing the
    single most useful evidence for connection problems (issue #385: every
    bundle in that report had ``log_capture_status: "unavailable"``). Probing
    first lets the caller tell the user *before* they wait for a useless
    capture.
    """
    log_path = hass.config.path("home-assistant.log")
    # Uses Home Assistant's shared executor, deliberately.
    #
    # os.open on a wedged network or FUSE mount cannot be cancelled, so no
    # arrangement here can free the worker; the only question is which pool it
    # is stranded in. _get_recent_logs() already performs this same open on this
    # same executor a few seconds later during the capture, so the probe adds no
    # hazard that the capture did not already carry. A private executor would
    # instead leave a thread that concurrent.futures joins at interpreter
    # shutdown, which can block a clean Home Assistant restart: strictly worse.
    # The caller's timeout is what keeps the *service* responsive.
    available, reason, error = await hass.async_add_executor_job(
        _probe_log_file, log_path
    )
    return {
        "available": available,
        "reason": reason,
        "path": log_path,
        "error": error,
    }


def build_missing_log_notice(
    reason: str | None, error: str | None, *, future: bool = False
) -> str:
    """Explain a bundle that has (or will have) no logs, and how to fix it.

    Shared by the pre-capture warning and the finished-bundle notification so
    both give the same remedy. Note what is deliberately absent: telling the
    user to configure `logger:`. That only sets levels; it does not create a
    file handler, so it cannot help an install that logs to stdout.
    """
    headline = (
        "⚠️ **This bundle will contain no logs.**"
        if future
        else "⚠️ **This bundle contains no logs.**"
    )
    if reason == "unreadable":
        return (
            f"{headline} The Home Assistant log file could not be read "
            f"(`{error}`), so the reason a command failed is usually not "
            "recoverable from it. Check the file's permissions and the "
            "configured log path, then run this service again."
        )
    return (
        f"{headline} Home Assistant is not writing a `home-assistant.log` file "
        "(common on container installs that log to stdout), so the reason a "
        "command failed is usually not recoverable from it.\n\n"
        "Use **Settings → Devices & services → Adjustable Bed → ⋮ → "
        "Enable debug logging** instead, reproduce the problem, then "
        "**Disable debug logging** to download the captured log and attach it "
        "alongside this bundle. The full log is also available under "
        "**Settings → System → Logs → Load full logs**."
    )
