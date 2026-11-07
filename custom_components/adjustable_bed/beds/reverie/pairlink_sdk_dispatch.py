"""Source-bound private SDK dispatch, independent of unit-model semantics."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from .reverie_pairlink_sdk import PairlinkSdkMessage, sdk_mac


class PairlinkSdkReadError(ValueError):
    """A source field/copy cannot complete on the current backing array."""


@dataclass(frozen=True, slots=True)
class PairlinkSdkCallbackEvent:
    """An actual library callback; the app inherits these as no-ops."""

    kind: Literal["channel", "sensor", "sensor_raw", "key", "dynamic_group"]
    address_type: int
    address: bytes
    data: bytes | None
    values: tuple[int, ...] = ()
    groups: tuple[int, ...] | None = None

    @property
    def mac(self) -> str | None:
        """The channel callback receives Util.byte2BtAddr, not raw bytes."""
        return sdk_mac(self.address) if self.kind == "channel" else None


PairlinkSdkDispatch = PairlinkSdkMessage | PairlinkSdkCallbackEvent
_NESTED_UNIT_OPS = frozenset((0x344, 0x364, 0x394, 0x3B3, 0x3D4, 0x30E))
_SINGLE_MAC_OPS = frozenset((0x342, 0x349, 0x362, 0x392, 0x3D2))


def _signed(value: int) -> int:
    return value if value < 128 else value - 256


def _need(data: bytes, offset: int, count: int) -> bytes:
    if count < 0 or offset < 0 or offset + count > len(data):
        raise PairlinkSdkReadError("Incomplete SDK field")
    return data[offset : offset + count]


def _byte(data: bytes, offset: int) -> int:
    return _need(data, offset, 1)[0]


def _short(data: bytes, offset: int, *, signed: bool = False) -> int:
    return int.from_bytes(_need(data, offset, 2), "little", signed=signed)


def _range(data: bytes, start: int, end: int) -> bytes:
    """Java Arrays.copyOfRange permits a zero-padded end beyond the backing."""
    if start < 0 or start > len(data) or end < start:
        raise PairlinkSdkReadError("Invalid SDK copyOfRange")
    return data[start:end] + bytes(max(0, end - len(data)))


def _message(
    data: bytes,
    offset: int,
    address_type: int,
    address: bytes,
    unit: int,
    *,
    groups: tuple[int, ...] | None = None,
    target_mac: str = "",
    unit_mask: int = 0,
    broadcast: bool = False,
) -> PairlinkSdkMessage:
    opcode = _short(data, offset, signed=True)
    return PairlinkSdkMessage(
        address_type,
        address,
        unit,
        opcode,
        data[offset + 2 :] or None,
        groups=groups,
        target_mac=target_mac,
        unit_mask=unit_mask,
        broadcast=broadcast,
    )


def _source(
    data: bytes,
    cursor: int,
    address_type: int,
    *,
    grouped: bool,
) -> tuple[bytes, int]:
    width = 4 if address_type in (1, 3) else 6 if address_type in (2, 4) else 0
    if not width:
        # The grouped source still invokes GroupMsgHandler with its constructor
        # addrData and unknown type. Unicast unknown types return before FuncMsg.
        return bytes(6), cursor
    address = _need(data, cursor, width).ljust(6, b"\x00")
    cursor += width
    # Raw DEX group types3/4 both advance over UID2. This differs from two prose
    # rows of the frozen G14 matrix; the actual instructions are authoritative.
    if address_type in (3, 4):
        if not grouped:
            _need(data, cursor, 2)  # Unicast logs/reads the UID.
        cursor += 2
    return address, cursor


def _sensor(
    address_type: int,
    address: bytes,
    payload: bytes | None,
) -> PairlinkSdkCallbackEvent:
    if payload is not None and len(payload) == 4 and payload[:2] == b"\x03\x02":
        return PairlinkSdkCallbackEvent("sensor", address_type, address, payload[2:], (2,))
    return PairlinkSdkCallbackEvent("sensor_raw", address_type, address, payload)


def _group_events(
    message: PairlinkSdkMessage, *, callback_present: bool
) -> Iterator[PairlinkSdkDispatch]:
    # GroupMsgHandler reduces shared status first. Yielding preserves that
    # ordering: a failed model consumer cannot fall through to a callback.
    yield message
    if (message.opcode & 0xFFFF) >= 0x8000:
        return
    if message.opcode == 0x45C:
        if message.data is None:
            raise PairlinkSdkReadError("Source group sensor payload is null")
        if not callback_present:
            # GroupMsgHandler dereferences mCallback here without a null guard.
            raise PairlinkSdkReadError("Source group sensor callback is null")
        yield _sensor(message.address_type, message.address, message.data)
    elif message.opcode == 0x503 and message.data and callback_present:
        yield PairlinkSdkCallbackEvent(
            "dynamic_group",
            message.address_type,
            message.address,
            None,
            (_signed(message.data[0]),),
            message.groups,
        )


def _nested(
    data: bytes,
    *,
    multi: bool,
    callback_present: bool,
) -> Iterator[PairlinkSdkDispatch]:
    length = _byte(data, 0)
    if _byte(data, 1) != 0 or length < 3 or len(data) - 2 < length - 2:
        return
    unit = _signed(_byte(data, 2))
    address_type = _signed(_byte(data, 3))
    count = min(length - 3, 6)
    address = _need(data, 4, count).ljust(6, b"\x00")
    # Source increments the cursor only for the first six copied bytes, even
    # when the declared address TLV exceeds the six-byte PacketSource array.
    cursor = 4 + count
    command = b""
    if not multi:
        command_length = _byte(data, cursor)
        command_type = _byte(data, cursor + 1)
        cursor += 2
        if command_type == 6:
            _short(data, cursor)  # CID/PID read for logging, then source stride.
            cursor += command_length - 1
            command_length = _byte(data, cursor)
            command_type = _byte(data, cursor + 1)
            cursor += 2
        if command_type != 1 or command_length < 2 or len(data) - cursor < command_length - 2:
            return
        command = _range(data, cursor, cursor + command_length - 1)
        cursor += command_length - 1
        if len(command) >= 2 and _short(command, 0) in _NESTED_UNIT_OPS:
            yield _message(command, 0, address_type, address, unit)

    while len(data) - cursor >= 3:
        start = cursor
        length = _byte(data, start)
        if len(data) - (start + 1) < length - 1:
            return
        kind = _byte(data, start + 1)
        payload = start + 2
        size = length - 1
        if multi and kind in (4, 5, 14):
            if kind == 4:
                if size < 10:
                    cursor = payload + size
                    continue
                target = _need(data, payload, 6)
                mask = _short(data, start + 8, signed=True)
                cmd = _range(data, start + 10, payload + length - 1)
                groups = None
            elif kind == 5:
                groups = (_byte(data, payload),)
                cmd = _range(data, start + 3, payload + length - 1)
                target, mask = b"", 0
            else:
                groups = (_short(data, payload),)
                cmd = _range(data, start + 4, payload + length - 2)
                target, mask = b"", 0
            op = _short(cmd, 0, signed=True)
            if callback_present and 0x46C <= op <= 0x471:
                yield PairlinkSdkCallbackEvent("sensor", address_type, address, b"\x01", (1,))
                return
            if kind == 4:
                if op in _NESTED_UNIT_OPS:
                    if not mask & 0xFFFF:
                        return
                    unit = next(index for index in range(16) if mask & (1 << index))
                yield _message(
                    cmd,
                    0,
                    address_type,
                    address,
                    unit,
                    target_mac=sdk_mac(target),
                    unit_mask=mask,
                    broadcast=target == b"\xff" * 6,
                )
            else:
                yield from _group_events(
                    _message(cmd, 0, address_type, address, unit, groups=groups),
                    callback_present=callback_present,
                )
        elif not multi and kind == 2:
            if size % 8 == 0:
                for index in range(max(size // 8, 0)):
                    offset = payload + index * 8
                    target = _need(data, offset, 6)
                    mask = _short(data, offset + 6, signed=True)
                    yield _message(
                        command,
                        0,
                        address_type,
                        address,
                        unit,
                        target_mac=sdk_mac(target),
                        unit_mask=mask,
                        broadcast=target == b"\xff" * 6,
                    )
        elif not multi and kind in (3, 13):
            raw = _need(data, payload, max(size, 0))
            groups = (
                tuple(raw)
                if kind == 3
                else tuple(_short(raw, index) for index in range(0, len(raw) - 1, 2))
            )
            yield from _group_events(
                _message(command, 0, address_type, address, unit, groups=groups),
                callback_present=callback_present,
            )
        elif kind == 8 and size % 2 == 0:
            _need(data, payload, max(size, 0))  # Source pair reads are logging only.
        elif kind == 9 and length == 3 and callback_present:
            yield PairlinkSdkCallbackEvent(
                "key",
                address_type,
                address,
                None,
                (_signed(_byte(data, payload)), _signed(_byte(data, start + 3))),
            )
        # Source zero-length records advance by one byte, never a host loop.
        cursor = payload + size


def decode_sdk_dispatch(
    frame: bytes,
    *,
    local_mac: str,
    known_macs: set[str],
    callback_present: bool,
) -> Iterator[PairlinkSdkDispatch]:
    """Yield actual SDK private consumers in source execution order."""
    if len(frame) < 6 or frame[0] != 3:
        return
    channel = frame[5]
    cursor = 6
    broadcast = frame[1:5] == b"\xff" * 4
    restricted = False
    destination: str | None = None
    if channel == 0x14:
        destination = sdk_mac(_need(frame, 6, 6))
        if _byte(frame, 12) != 0x20:
            return
        cursor = 13
        if destination == local_mac:
            broadcast = False
        elif destination != "FF:FF:FF:FF:FF:FF":
            restricted = True
    elif channel not in (0x20, 0x21):
        return

    mode = _byte(frame, cursor)
    cursor += 1
    if mode == 0:
        mask = _short(frame, cursor, signed=True)
        unit = _signed(_byte(frame, cursor + 2))
        address_type = _signed(_byte(frame, cursor + 3))
        cursor += 4
        if address_type not in (1, 2, 3, 4):
            return
        address, cursor = _source(frame, cursor, address_type, grouped=False)
        if restricted:
            assert destination is not None
            if address_type != 2 and address_type != 4:
                return
            opcode = _short(frame, cursor)
            if opcode in _SINGLE_MAC_OPS:
                yield _message(
                    frame,
                    cursor,
                    address_type,
                    address,
                    0,
                    target_mac=destination,
                    unit_mask=mask,
                )
            elif destination not in known_macs and address_type == 2 and opcode == 0x45C:
                data = frame[cursor + 2 :]
                if data and callback_present:
                    yield _sensor(address_type, address, data)
            return
        yield _message(
            frame,
            cursor,
            address_type,
            address,
            unit,
            broadcast=broadcast,
            unit_mask=mask,
            target_mac=destination if destination is not None else "",
        )
    elif restricted:
        return
    elif mode in (1, 11):
        count = _byte(frame, cursor)
        cursor += 1
        width = 1 if mode == 1 else 2
        _need(frame, cursor, count * width)
        groups = tuple(
            _byte(frame, cursor + index) if width == 1 else _short(frame, cursor + index * 2)
            for index in range(count)
        )
        cursor += count * width
        unit = _signed(_byte(frame, cursor))
        address_type = _signed(_byte(frame, cursor + 1))
        address, cursor = _source(frame, cursor + 2, address_type, grouped=True)
        yield from _group_events(
            _message(frame, cursor, address_type, address, unit, groups=groups),
            callback_present=callback_present,
        )
    elif mode == 2:
        count = _signed(_byte(frame, cursor))
        cursor += 1
        last_channel = 0
        for _ in range(max(count, 0)):
            last_channel = _signed(_byte(frame, cursor))
            cursor += 1
        _byte(frame, cursor)  # unit
        address_type = _signed(_byte(frame, cursor + 1))
        cursor += 2
        if address_type != 2:
            return
        address = _need(frame, cursor, 6)  # Logging reads before callback guard.
        if callback_present:
            yield PairlinkSdkCallbackEvent(
                "channel",
                address_type,
                address,
                frame[cursor + 6 :],
                (last_channel,),
            )
    elif mode in (3, 4):
        yield from _nested(frame[cursor:], multi=mode == 4, callback_present=callback_present)
    elif mode == 8:
        if len(frame) - cursor < 13:
            return
        address = _need(frame, cursor, 6)
        virtual_address = _need(frame, cursor + 6, 4)
        unit = _signed(_byte(frame, cursor + 10))
        opcode = _short(frame, cursor + 11, signed=True)
        yield PairlinkSdkMessage(2, address, unit, opcode, virtual_address, short_ping=True)
