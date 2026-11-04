"""Private source-bound SDK receive records and the calendar response codec.

These are internal consumers of the existing authenticated receive entry. They
do not expose an arbitrary packet action or supply transport/key defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .reverie_pairlink_sdk_models import (
    PairlinkModelBoundsError,
    PairlinkModelNegativeLengthError,
    PairlinkModelNullError,
    PairlinkSdkDevice,
    PairlinkSdkUnit,
    add_init_sensor,
    apply_nonbasic_tlv,
)


@dataclass(frozen=True, slots=True)
class PairlinkSdkMessage:
    """The source's mode-zero PacketSource and bounded LE16 opcode."""

    address_type: int
    address: bytes
    unit_index: int
    opcode: int
    data: bytes | None
    short_ping: bool = False
    groups: tuple[int, ...] | None = None
    target_mac: str = ""
    unit_mask: int = 0
    broadcast: bool = False


def sdk_mac(address: bytes) -> str:
    """Util.byte2BtAddr reads the wire MAC in reverse order."""
    return ":".join(f"{value:02X}" for value in reversed(address))


def calendar_payload(calendar: datetime, timezone_offset_ms: int) -> bytes:
    """MeshFunc.timeSet mode0: zero-based month, Sunday0, zone8, zeros9..12."""
    # Java integer division truncates toward zero. The formatter discards the
    # minute component; a negative sub-hour offset therefore also becomes zero.
    hours = abs(timezone_offset_ms) // 3_600_000
    if timezone_offset_ms < 0:
        hours = -hours
    return (
        (calendar.year & 0xFFFF).to_bytes(2, "little")
        + bytes(
            (
                calendar.month - 1,
                calendar.day,
                calendar.hour,
                calendar.minute,
                calendar.second,
                (calendar.weekday() + 1) % 7,
                hours & 0xFF,
            )
        )
        + bytes(4)
    )


def calendar_profile_frame(*, target: bytes, own_virtual_address: bytes, payload: bytes) -> bytes:
    """Build only the reachable timeSet(vAddr, unit0, mode0) profile packet."""
    if len(target) != 4 or len(own_virtual_address) != 4 or len(payload) != 13:
        raise ValueError("Pairlink calendar response has invalid fixed-width fields")
    # GenUnitControlPacket: mode00, mask1, control00, source kind1, ownVA4,
    # opcode0492. SendPacket uses profile channel20 for this false-group route.
    inner = b"\x00\x01\x00\x00\x01" + own_virtual_address + b"\x92\x04" + payload
    return b"\x03" + target + b"\x20" + inner


def _signed_byte(value: int) -> int:
    return value if value < 128 else value - 256


def _require(data: bytes, cursor: int, count: int) -> None:
    if count < 0 or cursor + count > len(data):
        raise PairlinkModelBoundsError("Incomplete Pairlink SDK ping field")


def _payload(data: bytes | None) -> bytes:
    if data is None:
        raise PairlinkModelNullError("null SDK receive payload")
    return data


def _copy(data: bytes, cursor: int, count: int) -> bytes:
    if count < 0:
        raise PairlinkModelNegativeLengthError("negative SDK copy length")
    _require(data, cursor, count)
    return data[cursor : cursor + count]


def _byte(data: bytes, cursor: int) -> int:
    _require(data, cursor, 1)
    return data[cursor]


def _u16(data: bytes, cursor: int, *, signed: bool = False) -> int:
    return int.from_bytes(_copy(data, cursor, 2), "little", signed=signed)


def sdk_basic(device: PairlinkSdkDevice, payload: bytes | None) -> None:
    """tlvBasic's nullable/short distinction and ordered canonical writes."""
    data = _payload(payload)
    if len(data) < 15:
        return
    device.app_id = _u16(data, 0, signed=True)
    device.version_major = _signed_byte(data[2])
    device.version_minor = _signed_byte(data[3])
    device.version = f"{device.app_id & 65535} {data[2]}.{data[3]}"
    device.company_id = _u16(data, 4, signed=True)
    device.product_id = _u16(data, 6, signed=True)
    device.bt_addr = sdk_mac(data[8:14])
    device.unit_num = _signed_byte(data[14])
    device.units.clear()
    device.units.extend(PairlinkSdkUnit() for _ in range(device.unit_num))


def sdk_composition(device: PairlinkSdkDevice, payload: bytes | None) -> None:
    """FuncMsgHandler 0001: partial writes precede later backing-array reads."""
    data = _payload(payload)
    device.appearance = _u16(data, 0)
    count = _signed_byte(_byte(data, 2))
    cursor = 3
    for index in range(count):
        # Missing units do not consume a function-count byte in the source.
        if index >= len(device.units):
            continue
        functions = _signed_byte(_byte(data, cursor))
        cursor += 1
        unit = device.units[index]
        unit.function_list.clear()
        for _ in range(functions):
            unit.function_list.append(_u16(data, cursor))
            cursor += 2


def _groups(device: PairlinkSdkDevice, data: bytes, cursor: int, width: int) -> int:
    for unit in device.units:
        bitmap = _copy(data, cursor, width)
        cursor += width
        unit.groups.clear()
        unit.groups.extend(bit for bit in range(width * 8) if bitmap[bit // 8] & (1 << (bit % 8)))
    return cursor


def _name_and_versions(
    device: PairlinkSdkDevice, data: bytes, cursor: int, *, required: bool
) -> int:
    # The special pre-parser reads these bytes unconditionally. The generic
    # parser guards each read using its declared backing-array remainder.
    name_count = _signed_byte(_byte(data, cursor)) if required or cursor < len(data) else 0
    cursor += int(required or cursor < len(data))
    if name_count > 0 and len(data) - cursor >= name_count:
        apply_nonbasic_tlv(device, 2, _copy(data, cursor, name_count))
        cursor += name_count
    count = _byte(data, cursor) if required or cursor < len(data) else 0
    cursor += int(required or cursor < len(data))
    if len(data) - cursor >= count * 3:
        # GroupNameManagement is excluded; consume its exact reads/cursor.
        for _ in range(count):
            _byte(data, cursor)
            _u16(data, cursor + 1)
            cursor += 3
    return cursor


def _legacy_unit(unit: PairlinkSdkUnit, data: bytes, cursor: int, *, j2: bool = False) -> int:
    unit.function_id = _u16(data, cursor)
    cursor += 2
    function = unit.function_id
    if function == 2 and not j2:
        unit.onoff = _byte(data, cursor) != 0
        return cursor + 1
    if function not in ((3, 4) if j2 else (3, 4, 5)):
        return cursor
    level = _u16(data, cursor)
    unit.onoff = level != 0
    if function == 3:
        if level or j2:
            unit.level = level
        return cursor + 2
    target = unit.ctl if function == 4 else unit.hsl
    if level or j2:
        target.lightness = level
    if function == 4:
        unit.ctl.temperature = _u16(data, cursor + 2)
        unit.ctl.delta_uv = _u16(data, cursor + 4)
    else:
        unit.hsl.hue = _u16(data, cursor + 2)
        unit.hsl.saturation = _u16(data, cursor + 4)
    return cursor + 6


def _legacy_ping(device: PairlinkSdkDevice, data: bytes) -> None:
    _require(data, 0, 15)
    sdk_basic(device, data[:15])
    width = _signed_byte(_byte(data, 15))
    cursor = 16
    special = device.app_id in (-3834, -3835, -3827)
    if special or (width and len(data) - cursor >= device.unit_num * width):
        cursor = _groups(device, data, cursor, width)
    if special:
        cursor = _name_and_versions(device, data, cursor, required=True)
        if device.app_id == -3834:
            add_init_sensor(device, 0, 1)
            add_init_sensor(device, 0, 2)
            if not device.units:
                raise PairlinkModelBoundsError("J2 unit zero")
            unit = device.units[0]
            cursor = _legacy_unit(unit, data, cursor, j2=True)
            unit.sensors[0].onoff = _byte(data, cursor) == 1
            unit.sensors[1].onoff = _byte(data, cursor + 1) == 1
            cursor += 2
            if len(data) - cursor >= 4:
                _byte(data, cursor)  # excluded vendor sensorAdc
                unit.sensors[0].sensitivity = _u16(data, cursor + 1)
                _byte(data, cursor + 3)  # excluded vendor autoMode
                cursor += 4
            if len(data) - cursor >= 4:
                _u16(data, cursor)
                _u16(data, cursor + 2)
                cursor += 4
            if len(data) - cursor >= 2:
                unit.sensors[1].sensitivity = _u16(data, cursor)
        elif device.app_id == -3827:
            _byte(data, cursor)  # excluded vendor role string
        # Tuya's guarded remaining UTF-8 fields have no bed consumer.
    elif width:
        for unit in device.units:
            if cursor >= len(data):
                break
            cursor = _legacy_unit(unit, data, cursor)
        _name_and_versions(device, data, cursor, required=False)
    if not special:
        device.online = True


def sdk_ping_device(message: PairlinkSdkMessage, *, rtt: int) -> PairlinkSdkDevice | None:
    """Fresh canonical bean, shared by every TLV in this actual source receive."""
    data = message.data or b""
    device = PairlinkSdkDevice(rtt=rtt)
    if message.address_type in (1, 3):
        device.vaddr = _copy(message.address, 0, 4)
    if message.opcode == 3:
        _legacy_ping(device, data)
        return device
    if message.opcode != 4:
        raise ValueError("not a full/TLV ping")
    cursor = 0
    while len(data) - cursor >= 2:
        length, subtype = data[cursor : cursor + 2]
        cursor += 2
        if length == 0:
            break
        count = length - 1
        payload = _copy(data, cursor, count) if count > 0 else None
        if subtype == 0:
            sdk_basic(device, payload)
        else:
            apply_nonbasic_tlv(device, _signed_byte(subtype), payload)
        cursor += count
    device.online = True
    return device if device.app_id or device.company_id or device.product_id else None


def sdk_low_power_device(message: PairlinkSdkMessage) -> PairlinkSdkDevice:
    """Separate opcode0006 LP parser, with no canonical-list/status8 completion."""
    data = message.data or b""
    device = PairlinkSdkDevice()
    cursor = 0
    while len(data) - cursor >= 3:
        length, subtype = data[cursor : cursor + 2]
        cursor += 2
        count = length - 1
        payload = _copy(data, cursor, count)
        subtype = _signed_byte(subtype)
        if subtype == 0 and count >= 10:
            device.bt_addr = sdk_mac(_copy(message.address, 0, 6))
            device.app_id = _u16(payload, 0, signed=True)
            device.version_major = _signed_byte(payload[2])
            device.version_minor = _signed_byte(payload[3])
            device.company_id = _u16(payload, 4, signed=True)
            device.product_id = _u16(payload, 6, signed=True)
            device.appearance = _u16(payload, 8, signed=True)
        elif subtype == 12:
            if device.bt_addr is None:
                raise PairlinkModelNullError("LP storage before basic")
            # StorageRx is disabled; no persistence/send is authorized here.
        elif subtype == 13 and count >= 2:
            device.profile_ver = _u16(payload, 0)
        cursor += count
    return device
