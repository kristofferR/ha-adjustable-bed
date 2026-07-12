"""Utilities for handling unsupported BLE devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote

from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.issue_registry import (
    async_get as async_get_issue_registry,
)

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

_LOGGER = logging.getLogger(__name__)

GITHUB_REPO = "kristofferR/ha-adjustable-bed"
GITHUB_NEW_ISSUE_URL = f"https://github.com/{GITHUB_REPO}/issues/new"

# Prefix for the legacy "unsupported BLE device" Repairs issues. These were
# created automatically on discovery, but proved to be noise (the integration's
# Bluetooth matchers are broad, so most matches are unrelated BLE devices). We no
# longer create them and clear any stragglers on setup; see
# ``async_clear_unsupported_device_issues``.
_UNSUPPORTED_ISSUE_PREFIX = "unsupported_device_"


@dataclass
class UnsupportedDeviceInfo:
    """Information about an unsupported BLE device."""

    address: str
    name: str | None
    service_uuids: list[str]
    manufacturer_data: dict[int, bytes]
    rssi: int | None = None

    def to_misidentified_details(
        self,
        detected_bed_type: str | None,
        confidence: float,
        signals: list[str],
        integration_version: str | None = None,
        ha_version: str | None = None,
    ) -> str:
        """Format GitHub issue details for a device wrongly auto-detected as a bed."""
        if self.manufacturer_data:
            mfr_str = "\n".join(
                f"  - `{hex(k)}`: `{v.hex()}`" for k, v in self.manufacturer_data.items()
            )
        else:
            mfr_str = "  None"

        if self.service_uuids:
            uuid_str = "\n".join(f"  - `{uuid}`" for uuid in self.service_uuids)
        else:
            uuid_str = "  None"

        signal_str = "\n".join(f"  - `{signal}`" for signal in signals) if signals else "  None"
        confidence_pct = round(confidence * 100)

        return f"""## Misidentified device

The integration auto-detected this device as **`{detected_bed_type or "a bed"}`** \
(confidence {confidence_pct}%), but the detection is wrong: it may not be a bed at \
all, or it is a different brand/model.

| Property | Value |
|----------|-------|
| Detected as | `{detected_bed_type or "unknown"}` |
| Confidence | {confidence_pct}% |
| Address | `{self.address}` |
| Name | `{self.name or "Unknown"}` |
| RSSI | {self.rssi or "N/A"} |
| Integration version | `{integration_version or "unknown"}` |
| Home Assistant | `{ha_version or "unknown"}` |

### Detection signals
{signal_str}

### Advertised service UUIDs
{uuid_str}

### Manufacturer data
{mfr_str}

## What is this device actually?

<!-- Tell us what this device really is, e.g.:
- "It's a Bluetooth scale / speaker / fitness tracker, not a bed"
- "It IS a bed, but the wrong type was detected - it's actually a <brand/model>"
-->

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


def build_misidentified_issue_url(
    device_info: UnsupportedDeviceInfo,
    detected_bed_type: str | None,
    confidence: float,
    signals: list[str],
    integration_version: str | None = None,
    ha_version: str | None = None,
) -> str:
    """Generate a pre-filled GitHub issue URL for a misidentified (false-positive) device.

    Targets the ``misidentified-bed.yml`` issue form, prefilling its ``details``
    textarea (field id) with the captured detection data.
    """
    title = f"[Misidentified] {device_info.name or device_info.address}"
    details = device_info.to_misidentified_details(
        detected_bed_type,
        confidence,
        signals,
        integration_version=integration_version,
        ha_version=ha_version,
    )
    params = (
        f"?template=misidentified-bed.yml&title={quote(title)}&details={quote(details)}"
    )
    return f"{GITHUB_NEW_ISSUE_URL}{params}"


def async_clear_unsupported_device_issues(hass: HomeAssistant) -> None:
    """Delete any leftover "unsupported BLE device" Repairs issues.

    Earlier versions raised a persistent Repairs issue for every discovered BLE
    device that wasn't recognised as a bed. Because the integration's Bluetooth
    matchers are intentionally broad, this nagged users about unrelated devices,
    so the feature was removed. Issues created by those versions linger in the
    registry, so we clear them on setup to make the upgrade self-cleaning.
    """
    registry = async_get_issue_registry(hass)
    stale_ids = [
        issue_id
        for (domain, issue_id) in list(registry.issues)
        if domain == DOMAIN and issue_id.startswith(_UNSUPPORTED_ISSUE_PREFIX)
    ]
    for issue_id in stale_ids:
        async_delete_issue(hass, DOMAIN, issue_id)
    if stale_ids:
        _LOGGER.debug(
            "Cleared %d obsolete unsupported-device Repairs issue(s)",
            len(stale_ids),
        )


def _pairing_required_issue_id(address: str) -> str:
    """Return the stable Repairs issue id for a pairing-required bed."""
    return f"pairing_required_{address.replace(':', '_').lower()}"


async def create_pairing_required_issue(
    hass: HomeAssistant,
    address: str,
    name: str,
    entry_id: str | None = None,
) -> None:
    """Create a fixable issue for beds that require Bluetooth pairing.

    This is shown when a bed requiring pairing fails to bond at runtime, to
    guide users through the pairing process. The issue is fixable: the repair
    flow (see ``repairs.py``) walks the user through power-cycling the base and
    re-pairs it. ``entry_id`` (when known) lets the repair flow clear a stale
    bond marker and reload the entry on success.
    """
    issue_id = _pairing_required_issue_id(address)

    async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=True,
        is_persistent=True,
        severity=IssueSeverity.ERROR,
        translation_key="pairing_required",
        translation_placeholders={
            "name": name,
            "address": address,
        },
        data={
            "address": address,
            "name": name,
            "entry_id": entry_id,
        },
    )

    _LOGGER.debug(
        "Created Repairs issue for bed requiring pairing: %s (%s)",
        name,
        address,
    )


async def delete_pairing_required_issue(hass: HomeAssistant, address: str) -> None:
    """Remove the pairing-required Repairs issue once the bed is bonded."""
    async_delete_issue(hass, DOMAIN, _pairing_required_issue_id(address))
