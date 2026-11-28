"""AMINACH Platinum's B0 keys and B1 initiator-address response."""

from typing import Final

ADDRESS_REQUEST: Final = bytes.fromhex("b0 02 01 01 b4")


def _checked(prefix: bytes) -> bytes:
    return prefix + bytes((sum(prefix) & 0xFF,))


def control(key: int) -> bytes:
    """Encode a little-endian 16-bit key with the low byte of the byte sum."""
    return _checked(b"\xb0\x05\x10\x00\xc1" + key.to_bytes(2, "little"))


def adapter_response(address: str) -> bytes:
    """Use the initiating adapter's address, in display order, never the bed's."""
    octets = address.split(":")
    if len(octets) != 6 or any(len(octet) != 2 for octet in octets):
        raise ValueError("Expected six colon-separated adapter address octets")
    raw = bytes(int(octet, 16) for octet in octets)
    return _checked(b"\xb1\x07\x00" + raw)


def title_indicator(data: bytes) -> int | None:
    """Preserve the app's unchecksummed B2 field, with a safe length guard."""
    return data[2] if len(data) >= 4 and data[:2] == b"\xb2\x02" and data[2] in (0, 1) else None
