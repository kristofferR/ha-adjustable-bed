"""Entry-scoped Pairlink SDK metadata effects, independent of transport scheduling.

The dispatcher owns frame parsing, source/session guards, and canonical devices.
Persistence and callbacks are awaited in source order; failures retain preceding
in-memory mutations. This private module does not register any HA API or timer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol


class SdkMetadataUnit(Protocol):
    """The canonical SDK unit's function list."""

    @property
    def functions(self) -> Sequence[int]: ...


class SdkMetadataDevice(Protocol):
    """Read-only projection of a canonical device, never a fingerprint copy."""

    @property
    def app_id(self) -> int: ...

    @property
    def company_id(self) -> int: ...

    @property
    def product_id(self) -> int: ...

    @property
    def appearance(self) -> int: ...

    @property
    def bt_address(self) -> str: ...

    @property
    def units(self) -> Sequence[SdkMetadataUnit]: ...


@dataclass
class SdkAttributeUnit:
    functions: list[int] = field(default_factory=list)


@dataclass
class SdkAttributeRecord:
    app_id: int
    company_id: int
    product_ids: list[int]
    appearance: int
    units: list[SdkAttributeUnit] = field(default_factory=list)


@dataclass
class SdkFingerprintRecord[DeviceT: SdkMetadataDevice]:
    home_id: str = ""
    fingerprint: str = ""
    devices: list[DeviceT] = field(default_factory=list)
    valid: bool = False


@dataclass(frozen=True)
class SdkMetadataStatus:
    status: Literal[7, 8]
    # The actual app callback performs initial reads before its delegate.
    detail: str = ""


@dataclass(frozen=True)
class SdkFingerprintStatus:
    fingerprint: str
    # MeshCallback.onFingerPrintStatus is a shipped callback no-op.


@dataclass(frozen=True)
class SdkMetadataTimer:
    timer: Literal["fingerprint", "attributes"]
    delay_ms: int | None  # None removes the existing callback.


@dataclass(frozen=True)
class SdkFingerprintQuery:
    """Call the existing MeshService.apiGetFingerPrint path."""


@dataclass(frozen=True)
class SdkCompositionQuery:
    bt_address: str
    mode: Literal[0] = 0


type SdkMetadataEffect = (
    SdkMetadataStatus
    | SdkFingerprintStatus
    | SdkMetadataTimer
    | SdkFingerprintQuery
    | SdkCompositionQuery
)


class SdkMetadataIo[DeviceT: SdkMetadataDevice](Protocol):
    """Entry-scoped storage/ordered effect adapter supplied by the dispatcher.

    Read returns decoded source records (None means absent/Gson null). Decode and
    storage exceptions propagate. Writes serialize at the call boundary, including
    the complete canonical devices, and return the source commit boolean, ignored
    by this reducer. Do not retain a mutable record as the persisted snapshot.
    """

    async def read_attributes(
        self, defaults: list[SdkAttributeRecord]
    ) -> list[SdkAttributeRecord] | None: ...

    async def write_attributes(self, records: list[SdkAttributeRecord]) -> bool: ...

    async def read_fingerprint(self, home_id: str) -> SdkFingerprintRecord[DeviceT] | None: ...

    async def write_fingerprint(
        self, home_id: str, record: SdkFingerprintRecord[DeviceT] | None
    ) -> bool:
        """None is the source clear operation (stored empty string)."""
        ...

    async def emit(self, effect: SdkMetadataEffect) -> None: ...


def default_attribute_records() -> list[SdkAttributeRecord]:
    """Exact AttributesManagement default catalog, newly allocated per entry."""
    rows = (
        (4369, 1465, (65535,), 1984, ((2, 3),)),
        (4370, 1465, (4370,), 1984, ((2, 3, 4, 5),)),
        (61697, 1465, (61697,), 1984, ((2, 3, 4),)),
        (61698, 1465, (61698,), 1984, ((2, 3, 4, 5),)),
        (61699, 1465, (61699,), 1218, ((2,), (2,))),
        (61700, 1465, (61700,), 1860, ((2, 3),)),
        (61702, 32769, (0, 1), 1984, ((2, 3),)),
        (61702, 32769, (2, 3), 1984, ((2, 3, 4),)),
        (61703, 32769, (4,), 1218, ((9,),)),
        (61705, 32770, (65535,), 1984, ((2, 3, 4),)),
        (61706, 32770, (256,), 1984, ((2, 3, 4),)),
        (61711, 32770, (257,), 1218, ((9,),)),
        (61714, 32771, (0,), 1218, ((2,), (2,))),
        (61716, 32771, (1,), 1218, ((2,), (2,))),
        (61717, 1465, (256,), 1984, ((2, 3, 4),)),
    )
    return [
        SdkAttributeRecord(
            app,
            company,
            list(pids),
            appearance,
            [SdkAttributeUnit(list(functions)) for functions in units],
        )
        for app, company, pids, appearance, units in rows
    ]


class PairlinkSdkMetadata[DeviceT: SdkMetadataDevice]:
    """One instance per entry/mesh identity; no SDK singletons or implicit IO."""

    def __init__(
        self,
        devices: list[DeviceT],
        io: SdkMetadataIo[DeviceT],
        *,
        callback_present: bool = True,
    ) -> None:
        self.devices = devices
        self.io = io
        self.callback_present = callback_present
        self.attributes: list[SdkAttributeRecord] = []
        self.unknown_identities: list[str] = []
        self.fingerprint = SdkFingerprintRecord[DeviceT]()
        self.fingerprint_enabled = False
        self.fingerprint_state = 0
        self.pending_fingerprint = ""
        self.last_checked_fingerprint = ""

    async def initialize(self, home_id: str) -> None:
        """Service metadata init, then API_set_mesh_info fingerprint init."""
        records = await self.io.read_attributes(default_attribute_records())
        self.attributes = [] if records is None else records
        await self.initialize_fingerprint(home_id)

    async def initialize_fingerprint(self, home_id: str) -> None:
        record = await self.io.read_fingerprint(home_id)
        if record is not None:
            self.fingerprint = record
        else:
            self.fingerprint.home_id = home_id
            self.fingerprint.fingerprint = ""
            self.fingerprint.devices.clear()
            self.fingerprint.valid = False

    def reset_join_state(self) -> None:
        """Only after a successful central/peripheral join-entry reset."""
        self.fingerprint_state = 0

    def is_known(self, app_id: int, company_id: int, product_id: int) -> bool:
        app_id, company_id, product_id = (v & 0xFFFF for v in (app_id, company_id, product_id))
        return any(
            r.app_id == app_id
            and r.company_id == company_id
            and (0xFFFF in r.product_ids or product_id in r.product_ids)
            for r in self.attributes
        )

    @staticmethod
    def _matches(record: SdkAttributeRecord, app: int, company: int, product: int) -> bool:
        app, company, product = (v & 0xFFFF for v in (app, company, product))
        return (
            (record.app_id == app or app == 0xFFFF)
            and record.company_id == company
            and ((app != 0xFFFF and 0xFFFF in record.product_ids) or product in record.product_ids)
        )

    def appearance(self, company_id: int, product_id: int, *, app_id: int = 0xFFFF) -> int:
        """Exact two/three-argument getApperance, retaining first-match order."""
        for record in self.attributes:
            if self._matches(record, app_id, company_id, product_id):
                return record.appearance
        return 0

    def supports(
        self,
        app_id: int,
        company_id: int,
        product_id: int,
        unit: int,
        function: int,
    ) -> bool:
        for record in self.attributes:
            if self._matches(record, app_id, company_id, product_id):
                if len(record.units) <= unit:
                    return False
                if unit < 0:
                    # Java List.get has no Python-style negative indexing.
                    raise IndexError("negative SDK attribute unit")
                return function in record.units[unit].functions
        return False

    async def clear_attributes(self) -> None:
        # Source clear saves defaults without replacing the live catalog.
        await self.io.write_attributes(default_attribute_records())

    @staticmethod
    def identity_key(device: SdkMetadataDevice) -> str:
        return "_".join(
            str(v & 0xFFFF) for v in (device.app_id, device.company_id, device.product_id)
        )

    async def add(self, device: DeviceT) -> bool:
        """After FuncMsg 0x0001 has mutated the canonical composition fields."""
        if self.is_known(device.app_id, device.company_id, device.product_id):
            return False
        record = SdkAttributeRecord(
            device.app_id & 0xFFFF,
            device.company_id & 0xFFFF,
            [device.product_id & 0xFFFF],
            device.appearance,
        )
        for unit in device.units:
            functions: list[int] = []
            for function in unit.functions:
                functions.append(function)
                if function in (4, 5) and 3 not in functions:
                    functions.append(3)
            record.units.append(SdkAttributeUnit(functions))
        self.attributes.append(record)
        await self.io.write_attributes(self.attributes)
        if self.unknown_identities:
            self.unknown_identities.pop(0)
            await self._process_attributes()
        else:
            await self._status(8)
            await self._finish_attributes()
        return True

    async def _finish_attributes(self) -> None:
        await self.io.emit(SdkMetadataTimer("attributes", None))

    async def _process_attributes(self) -> None:
        if not self.unknown_identities:
            await self._finish_attributes()
            return
        for device in self.devices:
            if self.identity_key(device) == self.unknown_identities[0]:
                await self.io.emit(SdkMetadataTimer("attributes", None))
                await self.io.emit(SdkMetadataTimer("attributes", 3000))
                await self.io.emit(SdkCompositionQuery(device.bt_address))
                return

    async def attributes_timeout(self) -> None:
        """Existing SDK worker callback only; does not create a scheduler."""
        if self.unknown_identities:
            self.unknown_identities.pop(0)
            await self._process_attributes()
        else:
            await self._status(8)
            await self._finish_attributes()

    # AttributesManagement.start is default-disabled with no app true writer.
    # No acquisition worker is created; receive-reachable add remains ungated.

    def check_fingerprint(self, fingerprint: str) -> bool:
        self.last_checked_fingerprint = fingerprint
        return (
            fingerprint != "0000000000000000"
            and self.fingerprint.valid
            and fingerprint.lower() == self.fingerprint.fingerprint.lower()
        )

    async def begin_fingerprint(self) -> bool:
        """At CMD02's enabled/state0 branch, after the caller's role/join gate."""
        if not self.fingerprint_enabled or self.fingerprint_state != 0:
            return False
        self.fingerprint_state = 1
        await self.io.emit(SdkFingerprintQuery())
        await self.io.emit(SdkMetadataTimer("fingerprint", None))
        await self.io.emit(SdkMetadataTimer("fingerprint", 500))
        return True

    async def fingerprint_timeout(self) -> None:
        """Existing timer callback only; caller rejects stale entry generations."""
        self.fingerprint_state = 3
        await self._status(7)

    async def receive_fingerprint(self, packet: bytes) -> bool:
        """Full process_mesh_response 0x42 packet (includes its two-byte header)."""
        if len(packet) < 10 or packet[:2] != b"\x02\x42":
            return False
        value = packet[2:10].hex().upper()
        await self.io.emit(SdkMetadataTimer("fingerprint", None))
        if self.fingerprint_state == 1:
            if self.check_fingerprint(value):
                self.fingerprint_state = 3
                await self.load_fingerprint()
                await self._status(8)
            else:
                self.pending_fingerprint = value
                self.fingerprint_state = 2
                await self._status(7)
        elif self.callback_present:
            await self.io.emit(SdkFingerprintStatus(value))
        return True

    async def load_fingerprint(self) -> None:
        self.devices.clear()
        self.devices.extend(self.fingerprint.devices)
        self.fingerprint.valid = False
        await self.io.write_fingerprint(self.fingerprint.home_id, self.fingerprint)

    async def save_fingerprint(self, fingerprint: str) -> bool:
        if not self.fingerprint.home_id:
            return False
        self.fingerprint.fingerprint = fingerprint
        self.fingerprint.devices.clear()
        self.fingerprint.devices.extend(self.devices)
        self.fingerprint.valid = False
        await self.io.write_fingerprint(self.fingerprint.home_id, self.fingerprint)
        return True

    async def ping_list_complete(self, expected_device_count: int) -> bool:
        """At process_mesh_cmd ping's post-callback list-count/state2 branch."""
        if len(self.devices) != expected_device_count or self.fingerprint_state != 2:
            return False
        await self.save_fingerprint(self.pending_fingerprint)
        self.fingerprint_state = 3
        return True

    async def save_status(self) -> bool:
        """API_exit_mesh must await this before libExitMesh clears its runtime."""
        if (
            not self.fingerprint_enabled
            or not self.fingerprint.home_id
            or not self.fingerprint.fingerprint
            or not self.devices
            or self.fingerprint.valid
        ):
            return False
        self.fingerprint.devices.clear()
        self.fingerprint.devices.extend(self.devices)
        self.fingerprint.valid = True
        await self.io.write_fingerprint(self.fingerprint.home_id, self.fingerprint)
        return True

    async def clear_fingerprint(self, home_id: str) -> None:
        await self.io.write_fingerprint(home_id, None)
        if self.fingerprint.home_id == home_id:
            self.fingerprint.devices.clear()
            self.fingerprint.fingerprint = ""
            # Source does not change homeId, valid, tmp or getFingerPrintState.

    async def _status(self, status: Literal[7, 8]) -> None:
        if self.callback_present:
            await self.io.emit(SdkMetadataStatus(status))
