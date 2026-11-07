"""Private source-bound SDK receive models; these are not HA bed capabilities.

The dispatcher owns framing, source/session gates, basic identity, status callbacks
and receive lifetime. Helpers mutate live objects and propagate partial failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cmp_to_key


@dataclass(slots=True)
class PairlinkSdkCtl:
    lightness: int = 0
    temperature: int = 0
    delta_uv: int = 0
    kelvin: bool = False
    minimum: int = 0
    maximum: int = 65535


@dataclass(slots=True)
class PairlinkSdkHsl:
    lightness: int = 0
    hue: int = 0
    saturation: int = 0


@dataclass(slots=True)
class PairlinkSdkSensorCadence:
    delta_down: int = 0
    delta_up: int = 0
    fast_high: int = 0
    fast_low: int = 0
    min_interval: int = 0
    period_divisor: int = 0
    publish_period: int = 0


@dataclass(slots=True)
class PairlinkSdkSensor:
    property_id: int = 0
    onoff: bool = False
    sensitivity: int = 0
    # The source spells this field candence; the default reference is null.
    cadence: PairlinkSdkSensorCadence | None = None


@dataclass(slots=True)
class PairlinkSdkUnit:
    valid: bool = True
    name: str = ""
    function_id: int = 0
    function_list: list[int] = field(default_factory=list)
    groups: list[int] = field(default_factory=list)
    sensors: list[PairlinkSdkSensor] = field(default_factory=list)
    onoff: bool = False
    level: int = 0
    ctl: PairlinkSdkCtl = field(default_factory=PairlinkSdkCtl)
    hsl: PairlinkSdkHsl = field(default_factory=PairlinkSdkHsl)
    restore_function_id: int = 0
    restore_level: int = 0
    restore_ctl: PairlinkSdkCtl = field(default_factory=PairlinkSdkCtl)
    restore_hsl: PairlinkSdkHsl = field(default_factory=PairlinkSdkHsl)
    level_toggle_up: bool = True
    temperature_toggle_up: bool = True
    hue_toggle_up: bool = True
    scene_toggle: int = -1


@dataclass(slots=True)
class PairlinkSdkDevice:
    bt_addr: str | None = None
    vaddr: bytes = bytes(4)
    app_id: int = 0
    company_id: int = 0
    product_id: int = 0
    version_major: int = 0
    version_minor: int = 0
    version: str | None = None
    appearance: int = 0
    rtt: int = 0
    unit_num: int = 0
    units: list[PairlinkSdkUnit] = field(default_factory=list)
    device_name: str | None = None
    online: bool = False
    deleted: bool = False
    support_storage: bool = False
    profile_ver: int = 0
    dynamic_running: bool = False
    reboot_times: int = 0
    mesh_changed_times: int = 0
    vendor_business: bytes | None = None


@dataclass(frozen=True, slots=True)
class PairlinkGroupNameVersion:
    group: int
    version: int
    vaddr_hex: str | None
    bt_addr: str | None


@dataclass(frozen=True, slots=True)
class PairlinkModelResult:
    handled: bool = True
    warnings: tuple[str, ...] = ()
    group_name_versions: tuple[PairlinkGroupNameVersion, ...] = ()
    # Observation of the disabled StorageRx boundary, never a send/persist request.
    storage_ping: bool = False


class PairlinkModelBoundsError(IndexError):
    """Source array/List bounds failure; earlier field writes remain visible."""


class PairlinkModelNullError(TypeError):
    """Source null payload dereference, distinct from an empty byte array."""


class PairlinkModelNegativeLengthError(ValueError):
    """Source new-array negative length before its copy or assignment."""


def _length(data: bytes | None) -> int:
    if data is None:
        raise PairlinkModelNullError("null SDK model payload")
    return len(data)


def _byte(data: bytes | None, index: int) -> int:
    length = _length(data)
    if index < 0 or index >= length:
        raise PairlinkModelBoundsError("SDK model byte index")
    assert data is not None
    return data[index]


def _signed8(value: int) -> int:
    return (value & 255) - (256 if value & 128 else 0)


def _u16(data: bytes | None, index: int) -> int:
    return _byte(data, index) | (_byte(data, index + 1) << 8)


def _unit(device: PairlinkSdkDevice, index: int) -> PairlinkSdkUnit:
    if index < 0 or index >= len(device.units):
        raise PairlinkModelBoundsError("SDK model unit index")
    return device.units[index]


def _utf8(data: bytes | None) -> str:
    _length(data)
    assert data is not None
    # Java consumes an encoded surrogate as one malformed sequence. Python
    # consumes each byte separately, so preserve the Java replacement boundary.
    pieces: list[str] = []
    while data:
        try:
            pieces.append(data.decode("utf-8"))
            break
        except UnicodeDecodeError as err:
            pieces.append(data[: err.start].decode("utf-8"))
            pieces.append("\ufffd")
            end = err.end
            if (
                data[err.start] == 0xED
                and len(data) >= err.start + 3
                and 0xA0 <= data[err.start + 1] <= 0xBF
                and 0x80 <= data[err.start + 2] <= 0xBF
            ):
                end = err.start + 3
            data = data[end:]
    return "".join(pieces)


def _utf8_range(data: bytes | None, start: int, end: int) -> str:
    if start == end:
        return ""
    if end < start:
        raise PairlinkModelNegativeLengthError("SDK model name length")
    if start < 0 or end > _length(data):
        raise PairlinkModelBoundsError("SDK model name copy")
    assert data is not None
    return _utf8(data[start:end])


def add_init_sensor(device: PairlinkSdkDevice, unit_index: int, property_id: int) -> None:
    """MeshFunc.addInitSensor: first duplicate prevents append."""
    sensors = _unit(device, unit_index).sensors
    if not any(row.property_id == property_id for row in sensors):
        sensors.append(PairlinkSdkSensor(property_id))


def set_sensor_onoff(
    device: PairlinkSdkDevice, property_id: int, unit_index: int, value: bool
) -> None:
    """DeviceBean.setSensorOnoff: update every duplicate at the supplied unit."""
    for row in _unit(device, unit_index).sensors:
        if row.property_id == property_id:
            row.onoff = value


def set_sensor_sensitivity(
    device: PairlinkSdkDevice, property_id: int, unit_index: int, value: int
) -> None:
    """DeviceBean.setSensorSensitivity: always unit zero, every duplicate."""
    for row in _unit(device, 0).sensors:
        if row.property_id == property_id:
            row.sensitivity = value


def apply_nonbasic_tlv(
    device: PairlinkSdkDevice,
    subtype: int,
    payload: bytes | None,
) -> PairlinkModelResult:
    """MeshFunc.tlvHandler model branches AFTER the dispatcher copies payload.

    Positive wire lengths must be exact copies; zero/negative length gives None.
    Unknown/basic/original-address/role-peer branches return handled=False. No
    helper catches decoding errors, rolls back, emits a packet or calls HA.
    """
    if subtype in (1, 8, 19, 22):
        _status(device, payload, subtype)
    elif subtype == 2:
        device.device_name = _utf8(payload)
    elif subtype == 3:
        count = _signed8(_byte(payload, 0))
        if count == 0 or _length(payload) != device.unit_num * count + 1:
            return PairlinkModelResult(warnings=("tlvGroup length",))
        cursor = 1
        for index in range(device.unit_num):
            unit = _unit(device, index)
            # A negative count cannot satisfy the size equation for positive units.
            if count < 0:
                raise PairlinkModelNegativeLengthError("SDK group bitmap length")
            unit.groups.clear()
            for bit in range(count * 8):
                if _byte(payload, cursor + bit // 8) & (1 << (bit % 8)):
                    unit.groups.append(bit)
            cursor += count
    elif subtype == 4:
        count = _signed8(_byte(payload, 0))
        if _length(payload) != count * 3 + 1:
            return PairlinkModelResult(warnings=("tlvGroupNameVer length",))
        return PairlinkModelResult(
            group_name_versions=tuple(
                PairlinkGroupNameVersion(
                    _byte(payload, 1 + i * 3),
                    _u16(payload, 2 + i * 3),
                    device.vaddr.hex() if device.vaddr else None,
                    device.bt_addr,
                )
                for i in range(count)
            )
        )
    elif subtype == 5:
        length = _length(payload)
        for cursor in range(0, length - length % 4, 4):
            prop = _signed8(_byte(payload, cursor))
            onoff = _byte(payload, cursor + 1) != 0
            sensitivity = _u16(payload, cursor + 2)
            add_init_sensor(device, 0, prop)
            set_sensor_onoff(device, prop, 0, onoff)
            set_sensor_sensitivity(device, prop, 0, sensitivity)
        return PairlinkModelResult(warnings=("tlvSensor length",) if length % 4 else ())
    elif subtype == 6:
        cursor = 0
        for index in range(device.unit_num):
            if cursor >= _length(payload):
                break
            count = _signed8(_byte(payload, cursor))
            cursor += 1
            unit = _unit(device, index)
            unit.name = _utf8_range(payload, cursor, cursor + count)
            cursor += count
    elif subtype in (7, 17):
        cursor = 0
        for index in range(device.unit_num):
            count = _signed8(_byte(payload, cursor))
            cursor += 1
            if count == 0:
                continue
            groups = _unit(device, index).groups
            groups.clear()
            for _ in range(count):
                groups.append(_u16(payload, cursor) if subtype == 17 else _byte(payload, cursor))
                cursor += 2 if subtype == 17 else 1
    elif subtype in (9, 10, 20):
        cursor = 0
        for index in range(device.unit_num):
            if cursor >= _length(payload):
                break
            unit = _unit(device, index)
            if subtype == 9:
                unit.level_toggle_up = _byte(payload, cursor) == 1
                _unit(device, index).temperature_toggle_up = _byte(payload, cursor + 1) == 1
                cursor += 2
            elif subtype == 10:
                value = _u16(payload, cursor)
                unit.scene_toggle = value - (65536 if value & 32768 else 0)
                cursor += 2
            else:
                unit.hue_toggle_up = _byte(payload, cursor) == 1
                cursor += 1
    elif subtype == 12:
        device.support_storage = True
        # Accepted default StorageRx.getEnable() is false, before payload access.
        return PairlinkModelResult(storage_ping=True)
    elif subtype == 13:
        if payload is not None and len(payload) >= 2:
            device.profile_ver = _u16(payload, 0)
    elif subtype == 16:
        device.deleted = True
    elif subtype == 18:
        if payload:
            device.vendor_business = bytes(bytearray(payload))
    elif subtype == 23:
        if device.unit_num * 4 > _length(payload):
            return PairlinkModelResult()
        for index in range(device.unit_num):
            ctl = _unit(device, index).ctl
            ctl.minimum = _u16(payload, index * 4)
            ctl.maximum = _u16(payload, index * 4 + 2)
    elif subtype == 24:
        if payload:
            device.dynamic_running = _byte(payload, 0) != 0
    elif subtype == -3:
        device.reboot_times = _u16(payload, 0)
        device.mesh_changed_times = _u16(payload, 2)
    else:
        return PairlinkModelResult(handled=False)
    return PairlinkModelResult()


def _status(device: PairlinkSdkDevice, data: bytes | None, subtype: int) -> None:
    cursor = 2 if subtype == 22 else 0
    shared = _u16(data, 0) if subtype == 22 else 0
    for index in range(device.unit_num):
        if cursor >= _length(data):
            return
        unit = _unit(device, index)
        function = shared if subtype == 22 else _u16(data, cursor)
        if subtype in (8, 19):
            unit.restore_function_id = function
        if subtype != 8:
            unit.function_id = function
        if subtype != 22:
            cursor += 2
        if subtype == 8:
            if function == 3:
                unit.restore_level = _u16(data, cursor)
                cursor += 2
            elif unit.function_id in (4, 20, 5):
                color = unit.restore_hsl if unit.function_id == 5 else unit.restore_ctl
                _read_color(color, data, cursor)
                if isinstance(color, PairlinkSdkCtl):
                    color.kelvin = unit.function_id == 20
                cursor += 6
        elif function == 2:
            unit.onoff = _byte(data, cursor) != 0
            cursor += 1
        elif function == 3:
            value = _u16(data, cursor)
            if subtype == 19:
                unit.restore_level = value
                unit.onoff = _signed8(_byte(data, cursor + 2)) > 0
                unit.level = value
                cursor += 3
            else:
                unit.onoff = value != 0
                if unit.onoff:
                    unit.level = value
                cursor += 2
        elif function in (4, 20, 5) and subtype != 22:
            color = unit.hsl if function == 5 else unit.ctl
            if subtype == 19:
                restore = unit.restore_hsl if function == 5 else unit.restore_ctl
                _read_color(restore, data, cursor)
                unit.onoff = _signed8(_byte(data, cursor + 6)) > 0
                color.lightness = restore.lightness
                unit.level = color.lightness
                if isinstance(color, PairlinkSdkCtl) and isinstance(restore, PairlinkSdkCtl):
                    color.temperature = restore.temperature
                    color.delta_uv = restore.delta_uv
                    restore.kelvin = color.kelvin = function == 20
                elif isinstance(color, PairlinkSdkHsl) and isinstance(restore, PairlinkSdkHsl):
                    color.hue = restore.hue
                    color.saturation = restore.saturation
                cursor += 7
            else:
                value = _u16(data, cursor)
                unit.onoff = value != 0
                if unit.onoff:
                    color.lightness = value
                unit.level = color.lightness
                # Preserve each source assignment before a later short read fails.
                if isinstance(color, PairlinkSdkCtl):
                    color.temperature = _u16(data, cursor + 2)
                    color.delta_uv = _u16(data, cursor + 4)
                    color.kelvin = function == 20
                    if function == 20:
                        unit.function_id = 4
                else:
                    color.hue = _u16(data, cursor + 2)
                    color.saturation = _u16(data, cursor + 4)
                cursor += 6


def _read_color(color: PairlinkSdkCtl | PairlinkSdkHsl, data: bytes | None, cursor: int) -> None:
    color.lightness = _u16(data, cursor)
    if isinstance(color, PairlinkSdkCtl):
        color.temperature = _u16(data, cursor + 2)
        color.delta_uv = _u16(data, cursor + 4)
    else:
        color.hue = _u16(data, cursor + 2)
        color.saturation = _u16(data, cursor + 4)


def replace_ping_device(
    devices: list[PairlinkSdkDevice | None],
    incoming: PairlinkSdkDevice | None,
) -> None:
    """pingStatusAfterHandler list substep, including forward-removal skip.

    The caller owns later online-count/Attributes/status8 effects. This helper
    preserves the list getter and remove IndexError boundaries; comparison and
    sort errors propagate.
    """
    if incoming is None:
        return
    index = 0
    while index < len(devices):
        stored = _device_from_list(devices, index)
        if stored is not None and _address(stored) == incoming.bt_addr:
            try:
                devices.pop(index)
            except IndexError:
                pass
        index += 1
    devices.append(incoming)
    # Source compareTo delegates to String.compareTo (UTF-16 code units).
    devices.sort(key=cmp_to_key(_compare_devices))


def _address(device: PairlinkSdkDevice | None) -> str:
    if device is None or device.bt_addr is None:
        raise PairlinkModelNullError("null SDK address during equals/compareTo")
    return device.bt_addr


def _compare_devices(first: PairlinkSdkDevice | None, second: PairlinkSdkDevice | None) -> int:
    left = _address(first).encode("utf-16-be", "surrogatepass")
    right = _address(second).encode("utf-16-be", "surrogatepass")
    return (left > right) - (left < right)


def _device_from_list(
    devices: list[PairlinkSdkDevice | None],
    index: int,
) -> PairlinkSdkDevice | None:
    # MeshService.getDeviceBeanFromList has its own narrow bounds boundary.
    if index >= len(devices):
        return None
    try:
        if index < 0:
            raise IndexError("SDK List.get negative index")
        return devices[index]
    except IndexError:
        return None
