"""Utilities for handling unsupported BLE devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
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
PROXY_PAIRING_RECOVERY_URL = (
    f"https://github.com/{GITHUB_REPO}/blob/master/docs/TROUBLESHOOTING.md"
    "#repeated-authentication-failures-through-an-esphome-proxy"
)

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


def _evidence_field(evidence: dict[str, Any] | None, key: str) -> str | None:
    """Return a top-level evidence field as a string, or None."""
    if not isinstance(evidence, dict):
        return None
    value = evidence.get(key)
    return str(value) if value is not None else None


def _evidence_owner_field(evidence: dict[str, Any] | None, key: str) -> str | None:
    """Return a field of the evidence's bond owner as a string, or None."""
    if not isinstance(evidence, dict):
        return None
    owner = evidence.get("owner")
    if not isinstance(owner, dict):
        return None
    value = owner.get(key)
    return str(value) if value is not None else None


async def create_pairing_required_issue(
    hass: HomeAssistant,
    address: str,
    name: str,
    entry_id: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> None:
    """Create a fixable issue for beds that require Bluetooth pairing.

    This is shown when a bed requiring pairing fails to bond at runtime, to
    guide users through the pairing process. The issue is fixable: the repair
    flow (see ``repairs.py``) walks the user through power-cycling the base and
    re-pairs it. ``entry_id`` (when known) lets the repair flow clear a stale
    bond marker and reload the entry on success.

    ``evidence`` carries what was actually observed: which transport saw the
    failure and what kind of failure it was. Without it a repair cannot tell a
    local authentication failure from one carried by a proxy, and those need
    opposite treatment - one may justify removing a host bond, the other must
    never touch it (issue #459).
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
        # Home Assistant stores issue data as flat scalars, so the evidence is
        # spread across named keys rather than nested. A repair reads these to
        # decide whether recovery may touch a host bond at all.
        data={
            "address": address,
            "name": name,
            "entry_id": entry_id,
            "evidence_status": _evidence_field(evidence, "status"),
            "evidence_transport": _evidence_owner_field(evidence, "transport"),
            "evidence_source": _evidence_owner_field(evidence, "source"),
            "evidence_adapter": _evidence_owner_field(evidence, "adapter"),
            "evidence_observed_at": _evidence_field(evidence, "observed_at"),
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


# OCTO's own lost-PIN recovery page. Passed to the Repairs issue as a
# placeholder because hassfest rejects literal URLs inside translation strings.
OCTO_PIN_RECOVERY_URL = "https://octo-customer.com/pinlost/"


def _octo_pin_required_issue_id(address: str) -> str:
    """Return the stable Repairs issue id for a PIN-locked Octo receiver."""
    return f"octo_pin_required_{address.replace(':', '_').lower()}"


def update_octo_pin_required_issue(
    hass: HomeAssistant,
    address: str,
    name: str,
    pin_locked_without_pin: bool | None,
) -> None:
    """Raise or clear the "Octo receiver is PIN locked" Repairs issue.

    A locked receiver still connects and still reports its capabilities, but
    will not act on commands until it is authenticated. That is
    indistinguishable from a broken protocol implementation unless we say so,
    and the fix (enter the PIN in the options flow) is not discoverable.

    ``None`` means capability discovery did not resolve the lock state, and the
    last known state is left untouched. Retracting the warning on a transient
    discovery timeout would be a claim we have not earned.
    """
    if pin_locked_without_pin is None:
        return

    issue_id = _octo_pin_required_issue_id(address)

    if not pin_locked_without_pin:
        async_delete_issue(hass, DOMAIN, issue_id)
        return

    # A locked receiver drops the link roughly every 30 seconds and every
    # reconnect rediscovers the same lock, so log only on the transition.
    # The issue registry survives the controller being recreated; an instance
    # flag would not.
    if async_get_issue_registry(hass).async_get_issue(DOMAIN, issue_id) is None:
        _LOGGER.warning(
            "Octo bed %s (%s) reports its PIN lock engaged but no PIN is configured. "
            "The bed stays connected and reports its capabilities, but will not act on "
            "commands until it is authenticated. Enter the receiver's 4-digit OCTO app "
            "PIN in the integration options",
            name,
            address,
        )

    async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=True,
        severity=IssueSeverity.WARNING,
        translation_key="octo_pin_required",
        translation_placeholders={
            "name": name,
            "address": address,
            "recovery_url": OCTO_PIN_RECOVERY_URL,
        },
        learn_more_url=(
            "https://github.com/kristofferR/ha-adjustable-bed/blob/master/docs/beds/octo.md"
            "#lost-pin-factory-reset"
        ),
    )

    _LOGGER.debug(
        "Created Repairs issue for PIN-locked Octo receiver: %s (%s)",
        name,
        address,
    )


def clear_octo_pin_required_issue(hass: HomeAssistant, address: str) -> None:
    """Drop the PIN-locked repair without needing a successful connection.

    The issue is otherwise only cleared from the connect path, so a user who
    follows the repair and saves a PIN while the bed is unreachable would keep
    seeing an issue claiming no PIN is configured. Callers use this when the
    configuration itself makes the issue moot (a PIN was saved, the bed type
    changed) or when the entry goes away.
    """
    async_delete_issue(hass, DOMAIN, _octo_pin_required_issue_id(address))
