"""Typed zero-copy metadata projection and entry-owned source preference codec.

Only canonical SDK models cross this persistence boundary. Transport/session
objects, physical peer ownership, passwords and keys are never serialized.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterable, Iterator, Sequence
from dataclasses import fields
from typing import TYPE_CHECKING, SupportsIndex, overload
from weakref import WeakValueDictionary

from homeassistant.helpers.storage import Store

from .pairlink_sdk_metadata import (
    PairlinkSdkMetadata,
    SdkAttributeRecord,
    SdkAttributeUnit,
    SdkFingerprintRecord,
    SdkMetadataEffect,
)
from .pairlink_sdk_models import (
    PairlinkSdkCtl,
    PairlinkSdkDevice,
    PairlinkSdkHsl,
    PairlinkSdkSensor,
    PairlinkSdkSensorCadence,
    PairlinkSdkUnit,
)

if TYPE_CHECKING:
    from .pairlink_transport import PairlinkPeerIdentity

type JsonValue = None | bool | int | str | list[JsonValue] | dict[str, JsonValue]
type _Model = (
    PairlinkSdkDevice
    | PairlinkSdkUnit
    | PairlinkSdkCtl
    | PairlinkSdkHsl
    | PairlinkSdkSensor
    | PairlinkSdkSensorCadence
)
_MODELS = (
    PairlinkSdkDevice,
    PairlinkSdkUnit,
    PairlinkSdkCtl,
    PairlinkSdkHsl,
    PairlinkSdkSensor,
    PairlinkSdkSensorCadence,
)
# Exact Gson field names from the canonical DeviceBean / nested source classes.
_NAMES = {
    "bt_addr": "btAddrStr",
    "vaddr": "vAddr",
    "app_id": "appId",
    "company_id": "companyId",
    "product_id": "productId",
    "version_major": "versionMajor",
    "version_minor": "versionMinor",
    "version": "ver",
    "unit_num": "unitNum",
    "units": "unitInfoList",
    "device_name": "deviceName",
    "support_storage": "supportStorage",
    "profile_ver": "profileVer",
    "dynamic_running": "dynamicRunning",
    "vendor_business": "vendorBusiness",
    "function_id": "functionId",
    "function_list": "functionList",
    "groups": "groupList",
    "sensors": "sensorList",
    "restore_ctl": "restoreCtl",
    "restore_hsl": "restoreHsl",
    "restore_function_id": "restoreFunctionId",
    "restore_level": "restoreLevel",
    "level_toggle_up": "levelToggleUP",
    "temperature_toggle_up": "temperatureToggleUP",
    "hue_toggle_up": "hueToggleUP",
    "scene_toggle": "sceneToggle",
    "delta_uv": "deltaUv",
    "minimum": "temperatureMin",
    "maximum": "temperatureMax",
    "property_id": "property",
    "cadence": "candence",
    "delta_down": "deltaDown",
    "delta_up": "deltaUp",
    "fast_high": "fastHigh",
    "fast_low": "fastLow",
    "min_interval": "minInterval",
    "period_divisor": "periodDivisor",
    "publish_period": "publishPeriod",
}


class SdkUnitView:
    """A live accessor, never a second function list."""

    def __init__(self, unit: PairlinkSdkUnit) -> None:
        self.canonical = unit

    @property
    def functions(self) -> Sequence[int]:
        return self.canonical.function_list


class SdkDeviceView:
    """Stable object-identity projection, including source null-list failures."""

    def __init__(self, device: PairlinkSdkDevice | None) -> None:
        self.canonical = device

    def _device(self) -> PairlinkSdkDevice:
        if self.canonical is None:
            raise TypeError("null canonical SDK DeviceBean")
        return self.canonical

    @property
    def bt_address(self) -> str:
        address = self._device().bt_addr
        if address is None:
            raise TypeError("null canonical SDK MAC")
        return address

    @property
    def app_id(self) -> int:
        return self._device().app_id

    @property
    def company_id(self) -> int:
        return self._device().company_id

    @property
    def product_id(self) -> int:
        return self._device().product_id

    @property
    def appearance(self) -> int:
        return self._device().appearance

    @property
    def units(self) -> Sequence[SdkUnitView]:
        return tuple(SdkUnitView(unit) for unit in self._device().units)


class SdkDeviceViews(list[SdkDeviceView]):
    """Forward the metadata API's list operations to the actual canonical list.

    The empty list base supplies its declared API type only. No second catalog
    or MAC deduplication exists. Cache keys are object identities, so duplicate
    positions remain positions and fingerprint caches retain the same beans.
    """

    def __init__(self, canonical: list[PairlinkSdkDevice | None]) -> None:
        self.canonical = canonical
        self.on_clear: Callable[[], None] | None = None
        self.on_restore: Callable[[PairlinkSdkDevice | None], None] | None = None
        self._views: WeakValueDictionary[int, SdkDeviceView] = WeakValueDictionary()

    def view(self, device: PairlinkSdkDevice | None) -> SdkDeviceView:
        key = id(device)
        view = self._views.get(key)
        if view is None:
            view = SdkDeviceView(device)
            self._views[key] = view
        return view

    def __len__(self) -> int:
        return len(self.canonical)

    def __iter__(self) -> Iterator[SdkDeviceView]:
        return (self.view(device) for device in self.canonical)

    @overload
    def __getitem__(self, index: SupportsIndex) -> SdkDeviceView: ...

    @overload
    def __getitem__(self, index: slice) -> list[SdkDeviceView]: ...

    def __getitem__(self, index: SupportsIndex | slice) -> SdkDeviceView | list[SdkDeviceView]:
        if isinstance(index, slice):
            return [self.view(device) for device in self.canonical[index]]
        return self.view(self.canonical[index])

    def clear(self) -> None:
        self.canonical.clear()
        if self.on_clear is not None:
            self.on_clear()

    def extend(self, iterable: Iterable[SdkDeviceView]) -> None:
        for view in iterable:
            self.canonical.append(view.canonical)
            if self.on_restore is not None:
                self.on_restore(view.canonical)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise TypeError("SDK preference object expected")
    return dict(value.items())


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError("SDK preference array expected")
    return list(value)


def _integer(value: object) -> int:
    if type(value) is not int:
        raise TypeError("SDK preference integer expected")
    return value


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("SDK preference string expected")
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        raise TypeError("SDK preference boolean expected")
    return value


def _encode(value: object) -> JsonValue:
    if value is None or type(value) in (bool, int, str):
        assert value is None or isinstance(value, (bool, int, str))
        return value
    if isinstance(value, bytes):
        return [byte if byte < 128 else byte - 256 for byte in value]
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, _MODELS):
        result: dict[str, JsonValue] = {}
        for field in fields(value):
            member: object = getattr(value, field.name)
            if member is not None:  # Gson's default excludes null object fields.
                result[_NAMES.get(field.name, field.name)] = _encode(member)
        return result
    raise TypeError("not a canonical SDK value")


def _decode_model[ModelT: _Model](model_type: type[ModelT], value: object) -> ModelT:
    encoded = _mapping(value)
    model = model_type()
    for field in fields(model):
        key = _NAMES.get(field.name, field.name)
        if key not in encoded:
            continue  # Source constructor defaults, including Java null.
        item = encoded[key]
        current: object = getattr(model, field.name)
        decoded: object
        if field.name == "vaddr":
            decoded = bytes(_integer(v) & 255 for v in _array(item))
        elif field.name == "vendor_business":
            decoded = None if item is None else bytes(_integer(v) & 255 for v in _array(item))
        elif field.name in ("bt_addr", "device_name", "version"):
            decoded = None if item is None else _string(item)
        elif field.name == "cadence":
            decoded = None if item is None else _decode_model(PairlinkSdkSensorCadence, item)
        elif field.name == "units":
            decoded = [_decode_model(PairlinkSdkUnit, row) for row in _array(item)]
        elif field.name == "sensors":
            decoded = [_decode_model(PairlinkSdkSensor, row) for row in _array(item)]
        elif isinstance(current, PairlinkSdkCtl):
            decoded = _decode_model(PairlinkSdkCtl, item)
        elif isinstance(current, PairlinkSdkHsl):
            decoded = _decode_model(PairlinkSdkHsl, item)
        elif isinstance(current, list):
            decoded = [_integer(v) for v in _array(item)]
        elif isinstance(current, bool):
            decoded = _boolean(item)
        elif isinstance(current, int):
            decoded = _integer(item)
        elif isinstance(current, str):
            decoded = _string(item)
        else:
            raise TypeError("unmapped canonical SDK field")
        setattr(model, field.name, decoded)
    return model


def encode_attributes(records: list[SdkAttributeRecord]) -> str:
    return json.dumps(
        [
            {
                "appId": record.app_id,
                "companyId": record.company_id,
                "pidList": list(record.product_ids),
                "appearance": record.appearance,
                "unitList": [{"attributesList": list(unit.functions)} for unit in record.units],
            }
            for record in records
        ],
        separators=(",", ":"),
    )


def decode_attributes(value: str) -> list[SdkAttributeRecord] | None:
    raw: object = json.loads(value)
    if raw is None:
        return None
    records: list[SdkAttributeRecord] = []
    for item in _array(raw):
        row = _mapping(item)
        records.append(
            SdkAttributeRecord(
                _integer(row["appId"]),
                _integer(row["companyId"]),
                [_integer(v) for v in _array(row["pidList"])],
                _integer(row["appearance"]),
                [
                    SdkAttributeUnit(
                        [_integer(v) for v in _array(_mapping(unit)["attributesList"])]
                    )
                    for unit in _array(row["unitList"])
                ],
            )
        )
    return records


def encode_fingerprint(record: SdkFingerprintRecord[SdkDeviceView]) -> str:
    return json.dumps(
        {
            "homeId": record.home_id,
            "fingerPrint": record.fingerprint,
            "isFingerPrintValid": record.valid,
            "deviceList": [_encode(view.canonical) for view in record.devices],
        },
        separators=(",", ":"),
    )


def decode_fingerprint(
    value: str, views: SdkDeviceViews
) -> SdkFingerprintRecord[SdkDeviceView] | None:
    raw: object = json.loads(value)
    if raw is None:
        return None
    row = _mapping(raw)
    devices = [
        views.view(None if item is None else _decode_model(PairlinkSdkDevice, item))
        for item in _array(row["deviceList"])
    ]
    return SdkFingerprintRecord(
        _string(row["homeId"]),
        _string(row["fingerPrint"]),
        devices,
        _boolean(row["isFingerPrintValid"]),
    )


class PairlinkSdkStorage:
    """One entry's HA Store; preference values are immutable source JSON strings."""

    def __init__(
        self,
        store_factory: Callable[[], Store[dict[str, dict[str, str]]]],
        views: SdkDeviceViews,
        emit: Callable[[SdkMetadataEffect], Awaitable[None]],
    ) -> None:
        self._factory = store_factory
        self._store: Store[dict[str, dict[str, str]]] | None = None
        self._data: dict[str, dict[str, str]] | None = None
        self.views = views
        self._emit = emit

    async def emit(self, effect: SdkMetadataEffect) -> None:
        await self._emit(effect)

    async def _load(self) -> dict[str, dict[str, str]]:
        if self._data is None:
            if self._store is None:
                self._store = self._factory()
            raw = await self._store.async_load()
            self._data = (
                {}
                if raw is None
                else {namespace: dict(values) for namespace, values in raw.items()}
            )
        return self._data

    async def _write(self, namespace: str, key: str, value: str) -> bool:
        data = await self._load()
        updated = {name: dict(values) for name, values in data.items()}
        updated.setdefault(namespace, {})[key] = value
        assert self._store is not None
        await self._store.async_save(updated)
        self._data = updated
        return True

    async def read_attributes(
        self, defaults: list[SdkAttributeRecord]
    ) -> list[SdkAttributeRecord] | None:
        values = (await self._load()).get("attributesManagement", {})
        return defaults if "list" not in values else decode_attributes(values["list"])

    async def write_attributes(self, records: list[SdkAttributeRecord]) -> bool:
        snapshot = encode_attributes(records)  # Before any IO await.
        return await self._write("attributesManagement", "list", snapshot)

    async def read_fingerprint(self, home_id: str) -> SdkFingerprintRecord[SdkDeviceView] | None:
        value = (await self._load()).get("pl_finger_print", {}).get(home_id, "")
        return decode_fingerprint(value, self.views) if value else None

    async def write_fingerprint(
        self, home_id: str, record: SdkFingerprintRecord[SdkDeviceView] | None
    ) -> bool:
        snapshot = "" if record is None else encode_fingerprint(record)
        return await self._write("pl_finger_print", home_id, snapshot)


class PairlinkSdkState:
    """The runtime owns one metadata/list/IO lane for the entire config entry."""

    def __init__(
        self,
        store_factory: Callable[[], Store[dict[str, dict[str, str]]]],
        emit: Callable[[SdkMetadataEffect], Awaitable[None]],
    ) -> None:
        self.devices: list[PairlinkSdkDevice | None] = []
        self.owners: dict[int, tuple[int, str, PairlinkPeerIdentity | None]] = {}
        self.views = SdkDeviceViews(self.devices)
        self.io = PairlinkSdkStorage(store_factory, self.views, emit)
        self.metadata = PairlinkSdkMetadata(self.views, self.io)
        self.receive_lock = asyncio.Lock()
        self.initialized = False
        self.home_id: str | None = None
        self.expected_devices = 0  # MeshService.device_num static initialization
        self.started_ms = 0  # MeshService.startTime static long initialization
