"""Exact inspection and removal of bonds stored by the Home Assistant host.

A BLE bond belongs to whichever transport created it. The host's BlueZ stores
bonds for adapters plugged into the host; an ESPHome proxy keeps its own, and
neither can see the other's. Two rules follow, and everything here exists to
enforce them:

1. Host BlueZ state is never evidence about a proxy bond, or the reverse
   (issue #459).
2. A host-side unpair never runs for a bond that does not live on the host
   (issue #455).

Three properties matter more than convenience:

**A failed read is not an empty result.** ``bluetooth_adapters``'
``get_dbus_managed_objects()`` swallows D-Bus authentication, socket, timeout
and reply failures and returns ``{}``. That is fine for discovery and fatal for
a destructive action: "I could not ask" would look identical to "there is no
bond", and an unpair would report success having done nothing. This module talks
to BlueZ directly so a read failure stays a read failure.

**One address can exist under several adapters.** A host with two Bluetooth
adapters can hold two independent bonds for the same bed. Removal therefore
names an exact adapter and device object, and refuses when the caller has not
said which one it means.

**Removal is verified, not assumed.** A successful ``RemoveDevice`` reply is not
proof. The object tree is re-read afterwards, that read must itself succeed, and
the record must be gone or report both ``Paired`` and ``Bonded`` false.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .bluetooth_freshness import advertisement_time_marker

_LOGGER = logging.getLogger(__name__)

_BLUEZ_SERVICE = "org.bluez"
_DEVICE_INTERFACE = "org.bluez.Device1"
_ADAPTER_INTERFACE = "org.bluez.Adapter1"
_OBJECT_MANAGER_INTERFACE = "org.freedesktop.DBus.ObjectManager"

# BlueZ answers GetManagedObjects in milliseconds; a hang means something is
# wrong with the bus. One unpair makes three calls (inventory, removal,
# verification), so the per-call budget is kept small enough that the whole
# transaction stays inside a sensible wait even in the worst case.
_DBUS_TIMEOUT_SECONDS = 4.0


class BluezReadStatus(StrEnum):
    """Whether the host's BlueZ could be asked at all."""

    OK = "ok"
    UNAVAILABLE = "unavailable"


class BondRemovalStatus(StrEnum):
    """Outcome of a host-side unpair attempt.

    ``ALREADY_ABSENT`` is deliberately separate from ``REMOVED``: both leave the
    user with no bond, but only one of them did anything, and a UI that conflates
    them teaches people that unpair "worked" when it never ran.
    """

    REMOVED = "removed"
    ALREADY_ABSENT = "already_absent"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    AMBIGUOUS_OWNER = "ambiguous_owner"
    RPC_FAILED = "rpc_failed"
    VERIFICATION_FAILED = "verification_failed"


@dataclass(frozen=True, slots=True)
class LocalBondRecord:
    """One device object the host's BlueZ holds for an address."""

    address: str
    device_path: str
    adapter_path: str
    adapter_address: str | None = None
    paired: bool = False
    bonded: bool = False
    trusted: bool = False
    connected: bool = False

    @property
    def has_bond(self) -> bool:
        """Return True only when BlueZ positively reports a bond."""
        return self.paired or self.bonded

    def is_same_bond_as(self, other: LocalBondRecord) -> bool:
        """Return True when two reads describe the same BlueZ bond.

        Identity is the device object, the adapter holding it, and that
        adapter's own MAC. Both reads must name the MAC, because every other
        field here is reusable: swapping a host dongle can hand ``hci0``, and
        with it this bed's deterministic device path, to different hardware than
        the one named in the confirmation the user approved. A record whose
        adapter address BlueZ did not publish cannot rule that out, so it never
        answers True - this method exists to authorize destroying a bond, and
        "probably the same one" is not a basis for that.

        Whole-dataclass equality would instead also compare ``connected`` and
        ``trusted``, which change while a confirmation dialog is open and would
        refuse a removal the user already approved for exactly this bond.
        """
        if self.adapter_address is None or other.adapter_address is None:
            return False
        return (
            self.adapter_address.upper() == other.adapter_address.upper()
            and self.device_path == other.device_path
            and self.adapter_path == other.adapter_path
            and self.address.upper() == other.address.upper()
            and self.has_bond == other.has_bond
        )


@dataclass(frozen=True, slots=True)
class LocalBondInventory:
    """Every host bond record for one address, plus whether the read worked."""

    status: BluezReadStatus
    records: tuple[LocalBondRecord, ...] = ()

    @property
    def readable(self) -> bool:
        """Return True when the host's BlueZ answered."""
        return self.status is BluezReadStatus.OK

    @property
    def bonded_records(self) -> tuple[LocalBondRecord, ...]:
        """Return only the records that actually carry a bond."""
        return tuple(record for record in self.records if record.has_bond)

    @property
    def sole_bond(self) -> LocalBondRecord | None:
        """Return the single bonded record, or None if there is not exactly one.

        None covers both "no bond" and "more than one adapter holds one". The
        caller must tell those apart before offering to remove anything.
        """
        bonded = self.bonded_records
        return bonded[0] if len(bonded) == 1 else None


class BondSelectionStatus(StrEnum):
    """Whether a specific host bond record could be identified for removal."""

    EXACT = "exact"
    UNKNOWN_OWNER = "unknown_owner"
    AMBIGUOUS = "ambiguous"
    NO_BOND = "no_bond"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class BondSelection:
    """The one record a removal may target, or why there is not one."""

    status: BondSelectionStatus
    record: LocalBondRecord | None = None

    @property
    def is_exact(self) -> bool:
        """Return True when exactly one record was positively identified."""
        return self.status is BondSelectionStatus.EXACT and self.record is not None


def select_local_bond(
    inventory: LocalBondInventory,
    *,
    owner_source: str | None = None,
    owner_adapter: str | None = None,
) -> BondSelection:
    """Pick the single host bond record a removal may target.

    Ownership is matched on the adapter's MAC address, because that is what
    both sides actually hold: a local scanner's ``source`` IS its adapter MAC,
    while ``adapter`` is the interface name (``hci0``). Comparing the interface
    name against ``Device1.Adapter``'s MAC never matches, and a near-miss here
    is not harmless - it would silently fall through to "whichever record came
    first", which on a two-adapter host is the wrong bond.

    Returning a typed status rather than an optional record is deliberate: a
    caller cannot accidentally treat "could not identify one" as "use any".
    """
    if not inventory.readable:
        return BondSelection(status=BondSelectionStatus.UNREADABLE)

    bonded = inventory.bonded_records
    if not bonded:
        return BondSelection(status=BondSelectionStatus.NO_BOND)

    wanted_mac = (owner_source or "").upper()
    if wanted_mac:
        matches = [
            record
            for record in bonded
            if (record.adapter_address or "").upper() == wanted_mac
        ]
        if len(matches) == 1:
            return BondSelection(status=BondSelectionStatus.EXACT, record=matches[0])
        if len(matches) > 1:
            return BondSelection(status=BondSelectionStatus.AMBIGUOUS)
        if any(record.adapter_address for record in bonded):
            # The adapter this bond was made on is named and known, and it is
            # not among the adapters currently holding one. Falling through to
            # the interface-name match would let a different adapter's bond be
            # selected on the strength of a looser identifier.
            return BondSelection(status=BondSelectionStatus.UNKNOWN_OWNER)

    if owner_adapter:
        # Secondary: BlueZ adapter object paths end in the interface name.
        suffix = f"/{owner_adapter}"
        matches = [
            record for record in bonded if record.adapter_path.endswith(suffix)
        ]
        if len(matches) == 1:
            return BondSelection(status=BondSelectionStatus.EXACT, record=matches[0])
        if len(matches) > 1:
            return BondSelection(status=BondSelectionStatus.AMBIGUOUS)

    if len(bonded) == 1:
        # No provenance, but the host holds exactly one bond for this exact
        # address, so there is nothing to choose between. The caller still has
        # to decide whether it is willing to act without provenance.
        return BondSelection(
            status=(
                BondSelectionStatus.EXACT
                if not (owner_source or owner_adapter)
                else BondSelectionStatus.UNKNOWN_OWNER
            ),
            record=bonded[0],
        )

    # Several bonds and nothing that names one of them. Never guess.
    return BondSelection(status=BondSelectionStatus.AMBIGUOUS)


@dataclass(frozen=True, slots=True)
class BondRemovalResult:
    """What a host-side unpair actually achieved."""

    status: BondRemovalStatus
    record: LocalBondRecord | None = None
    error: str | None = None
    removed_at: float | None = None

    @property
    def succeeded(self) -> bool:
        """Return True only for a removal that was carried out and confirmed."""
        return self.status is BondRemovalStatus.REMOVED

    @property
    def is_unconfirmed(self) -> bool:
        """Return True when the bond may or may not have survived.

        A refused RPC and a verification that could not be read say nothing
        about whether the bond is still there, which is a different thing to
        tell the user than BlueZ still reporting one: "nothing changed" would
        send them back to remove a bond that may already be gone, when what
        they actually need is to pair a replacement.
        """
        return self.status is BondRemovalStatus.RPC_FAILED or (
            self.status is BondRemovalStatus.VERIFICATION_FAILED
            and self.error != "bond_still_present"
        )


async def _async_managed_objects() -> dict[str, Any] | None:
    """Return BlueZ's object tree, or None when it could not be read.

    Deliberately not ``bluetooth_adapters.get_dbus_managed_objects()``: that
    helper maps every backend failure to an empty dict, which is exactly the
    ambiguity a destructive action must not inherit.
    """
    try:
        from dbus_fast import BusType, Message, MessageType, unpack_variants
        from dbus_fast.aio import MessageBus
    except ImportError:  # pragma: no cover - ships with HA's bluetooth stack
        _LOGGER.debug("dbus-fast is unavailable; cannot inspect host bonds")
        return None

    bus: Any = None
    try:
        bus = MessageBus(bus_type=BusType.SYSTEM)
        async with asyncio.timeout(_DBUS_TIMEOUT_SECONDS):
            await bus.connect()
            reply = await bus.call(
                Message(
                    destination=_BLUEZ_SERVICE,
                    path="/",
                    interface=_OBJECT_MANAGER_INTERFACE,
                    member="GetManagedObjects",
                )
            )
    except Exception as err:
        _LOGGER.debug("Could not read BlueZ objects: %s", err)
        return None
    finally:
        if bus is not None:
            try:
                bus.disconnect()
            except Exception:
                _LOGGER.debug("Failed to close the D-Bus connection", exc_info=True)

    if reply is None or getattr(reply, "message_type", None) != MessageType.METHOD_RETURN:
        _LOGGER.debug(
            "BlueZ refused GetManagedObjects: %s", getattr(reply, "error_name", "no reply")
        )
        return None

    body = getattr(reply, "body", None)
    if not body or not isinstance(body[0], dict):
        return None
    return unpack_variants(body[0])


def _records_from_objects(
    managed_objects: dict[str, Any], address: str
) -> tuple[LocalBondRecord, ...]:
    """Build a record for every BlueZ device object matching ``address``.

    Matching is on the ``Device1.Address`` property BlueZ itself reports, never
    on a path assembled from the address, so an address-format mismatch cannot
    make us name the wrong object.
    """
    wanted = address.upper()
    adapters: dict[str, str] = {}
    for path, interfaces in managed_objects.items():
        if isinstance(interfaces, dict):
            adapter_props = interfaces.get(_ADAPTER_INTERFACE)
            if isinstance(adapter_props, dict):
                adapter_address = adapter_props.get("Address")
                if isinstance(adapter_address, str):
                    adapters[path] = adapter_address

    records: list[LocalBondRecord] = []
    for path, interfaces in managed_objects.items():
        if not isinstance(interfaces, dict):
            continue
        props = interfaces.get(_DEVICE_INTERFACE)
        if not isinstance(props, dict):
            continue
        device_address = props.get("Address")
        if not isinstance(device_address, str) or device_address.upper() != wanted:
            continue
        adapter_path = props.get("Adapter")
        if not isinstance(adapter_path, str):
            continue
        records.append(
            LocalBondRecord(
                address=device_address.upper(),
                device_path=path,
                adapter_path=adapter_path,
                adapter_address=adapters.get(adapter_path),
                paired=bool(props.get("Paired")),
                bonded=bool(props.get("Bonded")),
                trusted=bool(props.get("Trusted")),
                connected=bool(props.get("Connected")),
            )
        )
    return tuple(records)


async def async_read_local_bonds(address: str) -> LocalBondInventory:
    """Return every host BlueZ record for ``address``.

    Works while the bed is asleep and never costs a BLE connection: a bond is
    stored state, not something that has to be observed on the air.
    """
    managed_objects = await _async_managed_objects()
    if managed_objects is None:
        return LocalBondInventory(status=BluezReadStatus.UNAVAILABLE)
    return LocalBondInventory(
        status=BluezReadStatus.OK,
        records=_records_from_objects(managed_objects, address),
    )


async def async_remove_local_bond(record: LocalBondRecord) -> BondRemovalResult:
    """Remove one exact host bond and confirm afterwards that it is gone.

    ``record`` must come from :func:`async_read_local_bonds`, so the adapter and
    device objects are ones BlueZ reported rather than paths built from a string.
    Only call this once the bond has been shown to live on the host: removing a
    host device object for a bed that pairs through a proxy destroys nothing
    useful while looking like a fix.
    """
    try:
        from dbus_fast import BusType, Message, MessageType
        from dbus_fast.aio import MessageBus
    except ImportError:  # pragma: no cover - ships with HA's bluetooth stack
        return BondRemovalResult(
            status=BondRemovalStatus.BACKEND_UNAVAILABLE,
            record=record,
            error="dbus_unavailable",
        )

    bus: Any = None
    try:
        bus = MessageBus(bus_type=BusType.SYSTEM)
        async with asyncio.timeout(_DBUS_TIMEOUT_SECONDS):
            await bus.connect()
            reply = await bus.call(
                Message(
                    destination=_BLUEZ_SERVICE,
                    path=record.adapter_path,
                    interface=_ADAPTER_INTERFACE,
                    member="RemoveDevice",
                    signature="o",
                    body=[record.device_path],
                )
            )
            # Capture the cutoff as soon as RemoveDevice completes. The object
            # tree verification below can overlap a new advertisement whose
            # recreated Device1 object is already safe to reconnect through.
            removed_at = advertisement_time_marker()
    except Exception as err:
        _LOGGER.warning("Could not remove the host bond for %s: %s", record.address, err)
        return BondRemovalResult(
            status=BondRemovalStatus.RPC_FAILED,
            record=record,
            error=str(err) or err.__class__.__name__,
        )
    finally:
        if bus is not None:
            try:
                bus.disconnect()
            except Exception:
                _LOGGER.debug("Failed to close the D-Bus connection", exc_info=True)

    if reply is None or getattr(reply, "message_type", None) != MessageType.METHOD_RETURN:
        error_name = getattr(reply, "error_name", None) or "no_reply"
        _LOGGER.warning("BlueZ refused to remove the bond for %s: %s", record.address, error_name)
        return BondRemovalResult(
            status=BondRemovalStatus.RPC_FAILED, record=record, error=str(error_name)
        )

    # BlueZ accepting the call is not proof. Re-read, and require that read to
    # succeed: an unreadable tree cannot confirm anything.
    after = await async_read_local_bonds(record.address)
    if not after.readable:
        return BondRemovalResult(
            status=BondRemovalStatus.VERIFICATION_FAILED,
            record=record,
            error="bluez_unreadable_after_removal",
        )
    for remaining in after.records:
        if remaining.device_path == record.device_path and remaining.has_bond:
            _LOGGER.warning(
                "BlueZ accepted RemoveDevice for %s but still reports it as paired",
                record.address,
            )
            return BondRemovalResult(
                status=BondRemovalStatus.VERIFICATION_FAILED,
                record=record,
                error="bond_still_present",
            )

    _LOGGER.info("Removed the host Bluetooth bond for %s", record.address)
    return BondRemovalResult(
        status=BondRemovalStatus.REMOVED,
        record=record,
        removed_at=removed_at,
    )
