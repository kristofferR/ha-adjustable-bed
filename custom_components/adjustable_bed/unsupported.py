"""Utilities for handling unsupported BLE devices."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote

from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_get as async_get_issue_registry,
)

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

_LOGGER = logging.getLogger(__name__)

GITHUB_REPO = "kristofferR/ha-adjustable-bed"
GITHUB_NEW_ISSUE_URL = f"https://github.com/{GITHUB_REPO}/issues/new"

# In-memory set of issue_ids already processed this session.
# Prevents repeated registry lookups and log spam from BLE advertisements.
_notified_devices: set[str] = set()


@dataclass
class UnsupportedDeviceInfo:
    """Information about an unsupported BLE device."""

    address: str
    name: str | None
    service_uuids: list[str]
    manufacturer_data: dict[int, bytes]
    rssi: int | None = None

    def to_log_string(self) -> str:
        """Format device info for logging."""
        lines = [
            f"Address: {self.address}",
            f"Name: {self.name or 'Unknown'}",
            f"RSSI: {self.rssi or 'N/A'}",
            f"Service UUIDs: {self.service_uuids or 'None'}",
        ]
        if self.manufacturer_data:
            mfr_lines = [f"  {hex(k)}: {v.hex()}" for k, v in self.manufacturer_data.items()]
            lines.append("Manufacturer data:")
            lines.extend(mfr_lines)
        else:
            lines.append("Manufacturer data: None")
        return "\n".join(lines)

    def to_issue_body(self, reason: str) -> str:
        """Format device info for GitHub issue body."""
        mfr_str = ""
        if self.manufacturer_data:
            mfr_items = [f"  - `{hex(k)}`: `{v.hex()}`" for k, v in self.manufacturer_data.items()]
            mfr_str = "\n".join(mfr_items)
        else:
            mfr_str = "  None"

        uuid_str = ""
        if self.service_uuids:
            uuid_items = [f"  - `{uuid}`" for uuid in self.service_uuids]
            uuid_str = "\n".join(uuid_items)
        else:
            uuid_str = "  None"

        return f"""## Device Information

**Reason for non-detection:** {reason}

| Property | Value |
|----------|-------|
| Address | `{self.address}` |
| Name | `{self.name or "Unknown"}` |
| RSSI | {self.rssi or "N/A"} |

### Service UUIDs
{uuid_str}

### Manufacturer Data
{mfr_str}

## Bed Information

Please provide the following information about your bed:

- **Bed manufacturer/brand:**
- **Bed model name:**
- **Remote control model (if visible):**
- **App used to control the bed (if any):**

## Additional Context

<!-- Add any other context about your bed here -->

"""


def capture_device_info(
    discovery_info: BluetoothServiceInfoBleak,
) -> UnsupportedDeviceInfo:
    """Extract device information from BluetoothServiceInfoBleak."""
    # Handle None service_uuids gracefully
    service_uuids = discovery_info.service_uuids
    return UnsupportedDeviceInfo(
        address=discovery_info.address,
        name=discovery_info.name,
        service_uuids=[str(uuid) for uuid in service_uuids] if service_uuids else [],
        manufacturer_data={k: bytes(v) for k, v in discovery_info.manufacturer_data.items()}
        if discovery_info.manufacturer_data
        else {},
        rssi=getattr(discovery_info, "rssi", None),
    )


def log_unsupported_device(device_info: UnsupportedDeviceInfo, reason: str) -> None:
    """Log detailed information about an unsupported device."""
    _LOGGER.warning(
        "Unsupported BLE device detected during discovery:\n"
        "Reason: %s\n"
        "%s\n"
        "If this is an adjustable bed, please report it at:\n"
        "%s",
        reason,
        device_info.to_log_string(),
        _generate_github_url(device_info, reason),
    )


def _generate_github_url(device_info: UnsupportedDeviceInfo, reason: str) -> str:
    """Generate a pre-filled GitHub issue URL."""
    title = f"Support request: {device_info.name or 'Unknown device'}"
    body = device_info.to_issue_body(reason)

    # URL encode the parameters
    params = f"?template=new-bed-support.yml&title={quote(title)}&body={quote(body)}"
    return f"{GITHUB_NEW_ISSUE_URL}{params}"


def _make_unsupported_issue_id(device_info: UnsupportedDeviceInfo) -> str:
    """Generate a stable issue ID, preferring device name over MAC address.

    BLE devices may use randomized MAC addresses, so keying by name prevents
    duplicate Repairs entries for the same device across address changes.
    """
    if device_info.name:
        sanitized = re.sub(r"[^a-z0-9]", "_", device_info.name.lower()).strip("_")
        if sanitized:
            return f"unsupported_device_{sanitized}"
    # Fallback to MAC for unnamed devices
    return f"unsupported_device_{device_info.address.replace(':', '_').lower()}"


async def create_unsupported_device_issue(
    hass: HomeAssistant,
    device_info: UnsupportedDeviceInfo,
    reason: str,
) -> bool:
    """Create a persistent issue in the Repairs dashboard for an unsupported device.

    Returns True if the issue was newly created, False if it already existed.
    Deduplicates by device name (or MAC for unnamed devices) to handle BLE
    address randomization and prevent repeated repairs after dismissal.
    """
    issue_id = _make_unsupported_issue_id(device_info)

    # Fast path: already processed this session
    if issue_id in _notified_devices:
        return False

    # Check if issue already exists in registry (respects dismissed state across restarts)
    registry = async_get_issue_registry(hass)
    if registry.async_get_issue(DOMAIN, issue_id) is not None:
        _notified_devices.add(issue_id)
        return False

    github_url = _generate_github_url(device_info, reason)

    async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=True,
        severity=IssueSeverity.WARNING,
        translation_key="unsupported_device",
        translation_placeholders={
            "name": device_info.name or "Unknown device",
            "address": device_info.address,
            "reason": reason,
            "github_url": github_url,
        },
    )

    _notified_devices.add(issue_id)

    _LOGGER.debug(
        "Created Repairs issue for unsupported device %s (%s)",
        device_info.name or "Unknown",
        device_info.address,
    )

    return True


async def create_pairing_required_issue(
    hass: HomeAssistant,
    address: str,
    name: str,
) -> None:
    """Create a persistent issue for beds that require Bluetooth pairing.

    This is shown when a bed requiring pairing fails to connect at runtime,
    to guide users through the pairing process.
    """
    # Use address as unique identifier (normalized to avoid duplicates)
    issue_id = f"pairing_required_{address.replace(':', '_').lower()}"

    async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=True,
        severity=IssueSeverity.ERROR,
        translation_key="pairing_required",
        translation_placeholders={
            "name": name,
            "address": address,
        },
    )

    _LOGGER.debug(
        "Created Repairs issue for bed requiring pairing: %s (%s)",
        name,
        address,
    )
