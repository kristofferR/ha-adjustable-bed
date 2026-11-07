"""Pure codecs and state rules for the accepted Reverie Pairlink route."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

PAIRLINK_SERVICE_UUID = "9e5d1e47-5c13-43a0-8635-82adffc0386f"
PAIRLINK_WRITE_UUID = "9e5d1e47-5c13-43a0-8635-82adffc1386f"
PAIRLINK_NOTIFY_UUID = "9e5d1e47-5c13-43a0-8635-82adffc2386f"
PAIRLINK_LOW_POWER_SERVICE_UUID = "0000ffd0-0000-1000-8000-00805f9b34fb"
PAIRLINK_LOW_POWER_WRITE_UUID = "0000ffd1-0000-1000-8000-00805f9b34fb"
PAIRLINK_LOW_POWER_NOTIFY_UUID = "0000ffd2-0000-1000-8000-00805f9b34fb"
PAIRLINK_EXIT_COMMAND = bytes.fromhex("011555")

PAIRLINK_EVENT_KEY_SUFFIX = b"EVENTKEY"
PAIRLINK_BROADCAST_ADDRESS = bytes.fromhex("FFFFFFFF")
PAIRLINK_STATE_QUERY_TYPES = (1, 2, 3, 5, 6, 17, 7, 8, 9, 10, 11, 12, 13, 14)


class GattWriter(Protocol):
    """Small central-client surface used by the fragment sender."""

    async def write_gatt_char(
        self,
        char_specifier: str,
        data: bytes,
        response: bool | None = None,
    ) -> None: ...


def build_default_event_key(home_id: int, password: bytes) -> bytes:
    """Build the fixed 16-byte event key input from interleaved fields."""
    if isinstance(home_id, bool) or not isinstance(home_id, int):
        raise ValueError("Pairlink home ID must be an integer")
    if not 0 <= home_id <= 0xFFFFFFFF:
        raise ValueError("Pairlink home ID must fit four bytes")
    if len(password) != 4:
        raise ValueError("Pairlink password must be exactly four bytes")
    home_bytes = home_id.to_bytes(4, "little")
    interleaved = b"".join(
        bytes((home_byte, password_byte))
        for home_byte, password_byte in zip(home_bytes, password, strict=True)
    )
    return interleaved + PAIRLINK_EVENT_KEY_SUFFIX


def build_user_frame(
    payload: bytes,
    *,
    destination: bytes,
    channel: int,
    own_virtual_address: bytes,
    send_appearance: bool = False,
) -> bytes:
    """Create a type-3 frame from exact four-byte mesh fields."""
    if len(destination) != 4:
        raise ValueError("Pairlink destination must be four bytes")
    if len(own_virtual_address) != 4:
        raise ValueError("Pairlink virtual address must be four bytes")
    if not 0 <= channel <= 255:
        raise ValueError("Pairlink channel must fit one byte")
    if len(payload) % 4:
        raise ValueError("Pairlink user payload must contain four-byte blocks")
    wire_channel = channel + 1 if send_appearance else channel
    if wire_channel > 255:
        raise ValueError("Pairlink wire channel must fit one byte")
    return b"\x03" + destination + bytes((wire_channel,)) + own_virtual_address + payload


def encrypt_user_frame(
    frame: bytes,
    *,
    event_key: bytes,
    device_key: bytes,
) -> bytes:
    """Encrypt the frame body, then XOR it with the target's four-byte key.

    ``device_key`` is mandatory and must come from an exact target/MAC lookup.
    The synthetic accepted test vector is not a production default.
    """
    if len(event_key) != 16:
        raise ValueError("Pairlink event key must be exactly 16 bytes")
    if len(device_key) != 4:
        raise ValueError("Pairlink device key must be exactly four bytes")
    if len(frame) < 6 or frame[0] != 0x03:
        raise ValueError("Pairlink crypto requires a complete type-3 frame")

    try:
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as err:
        raise RuntimeError("The installed Home Assistant runtime lacks cryptography") from err

    body = frame[6:]
    algorithm = algorithms.AES(event_key)
    padder = padding.PKCS7(algorithm.block_size).padder()
    padded_body = padder.update(body) + padder.finalize()
    encryptor = Cipher(algorithm, modes.ECB()).encryptor()
    encrypted = encryptor.update(padded_body) + encryptor.finalize()
    masked = bytes(value ^ device_key[index % 4] for index, value in enumerate(encrypted))
    return b"\x06" + frame[1:6] + masked


def decrypt_user_frame(
    frame: bytes,
    *,
    event_key: bytes,
    device_key: bytes,
) -> bytes:
    """Decode one safe fixed-password native 0x06 frame for a known MAC.

    The native routine accepts several malformed padding cases. This host
    implementation preserves its valid fixed-mode wire format while rejecting
    short, oversized, or non-block-aligned inputs before touching session state.
    It intentionally does not implement the unsafe variable-password branch.
    """
    if len(event_key) != 16:
        raise ValueError("Pairlink event key must be exactly 16 bytes")
    if len(device_key) != 4:
        raise ValueError("Pairlink device key must be exactly four bytes")
    if len(frame) < 22 or len(frame) >= 256 or frame[0] != 0x06:
        raise ValueError("Pairlink encrypted frame is outside the safe fixed-mode domain")
    encrypted_body = frame[6:]
    if not encrypted_body or len(encrypted_body) % 16:
        raise ValueError("Pairlink encrypted body must contain complete AES blocks")

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as err:
        raise RuntimeError("The installed Home Assistant runtime lacks cryptography") from err

    ciphertext = bytes(
        value ^ device_key[index % 4] for index, value in enumerate(encrypted_body)
    )
    decryptor = Cipher(algorithms.AES(event_key), modes.ECB()).decryptor()
    padded_body = decryptor.update(ciphertext) + decryptor.finalize()
    padding_length = padded_body[-1]
    # Native fixed-mode code accepts zero and inconsistent padding bytes. It
    # only bounds the trailing length byte before truncating the returned data.
    if padding_length > 16 or padding_length > len(padded_body):
        raise ValueError("Pairlink encrypted frame has invalid native padding length")
    body = padded_body[: len(padded_body) - padding_length]
    return b"\x03" + frame[1:6] + body


def encrypt_login_block(block: bytes, *, login_key: bytes) -> bytes:
    """Encrypt one complete accepted 16-byte login/reply block."""
    return _aes_ecb(block, login_key, encrypt=True)


def decrypt_login_block(block: bytes, *, login_key: bytes) -> bytes:
    """Decrypt one complete accepted 16-byte login/reply block."""
    return _aes_ecb(block, login_key, encrypt=False)


def _aes_ecb(block: bytes, key: bytes, *, encrypt: bool) -> bytes:
    if len(key) != 16 or len(block) != 16:
        raise ValueError("Pairlink login cryptography requires one 16-byte block and key")
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as err:
        raise RuntimeError("The installed Home Assistant runtime lacks cryptography") from err
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    context = cipher.encryptor() if encrypt else cipher.decryptor()
    return context.update(block) + context.finalize()


def cmac_aes(key: bytes, message: bytes) -> bytes:
    """Return AES-CMAC for the accepted Pairlink fixed-key receive algorithm."""
    if len(key) != 16:
        raise ValueError("Pairlink CMAC key must be 16 bytes")
    try:
        from cryptography.hazmat.primitives import cmac
        from cryptography.hazmat.primitives.ciphers import algorithms
    except ImportError as err:
        raise RuntimeError("The installed Home Assistant runtime lacks cryptography") from err
    context = cmac.CMAC(algorithms.AES(key))
    context.update(message)
    return context.finalize()


def _encrypt_padded_aes_ecb(plaintext: bytes, *, key: bytes) -> bytes:
    """Encrypt one source-sized provision payload with AES-ECB/PKCS#7."""
    if len(key) != 16:
        raise ValueError("Pairlink provision key must be exactly 16 bytes")
    try:
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as err:
        raise RuntimeError("The installed Home Assistant runtime lacks cryptography") from err

    aes = algorithms.AES(key)
    padder = padding.PKCS7(aes.block_size).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(aes, modes.ECB()).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def derive_event_key_from_seed(seed: bytes, *, variable_password: bytes = b"") -> bytes:
    """Port the accepted receive-driven Bluetooth Mesh K1 event-key update."""
    if len(seed) != 4:
        raise ValueError("Pairlink event seed must be exactly four bytes")
    salt = cmac_aes(bytes(16), seed)
    intermediate = cmac_aes(salt, variable_password)
    return cmac_aes(intermediate, b"EVENTKEY")


def derive_event_key_index(event_key: bytes) -> bytes:
    """Return the exact four-byte LE index computed by the native nested CMACs."""
    if len(event_key) != 16:
        raise ValueError("Pairlink event key must be exactly 16 bytes")
    first = cmac_aes(bytes(16), b"keyidx")
    second = cmac_aes(first, event_key)
    third = cmac_aes(second, b"id32")
    return third[:4]


def fragment_central_frame(frame: bytes, *, att_mtu: int) -> tuple[bytes, ...]:
    """Apply the app's encrypted central GATT fragment header and payload size."""
    real_mtu = att_mtu - 3
    if real_mtu <= 0:
        raise ValueError("ATT MTU must leave a usable GATT payload")
    if len(frame) <= real_mtu:
        return (frame,)

    chunk_size = real_mtu - 3
    if chunk_size <= 0:
        raise ValueError("ATT MTU is too small for Pairlink fragment headers")
    count = math.ceil(len(frame) / chunk_size)
    return tuple(
        bytes((0x01, 0x21, ((count & 0x0F) << 4) | (index & 0x0F)))
        + frame[offset : offset + chunk_size]
        for index, offset in enumerate(range(0, len(frame), chunk_size), start=1)
    )


def dashboard_payload(command: int, value: int = 0) -> bytes:
    """Build the accepted four-byte direct dashboard payload."""
    _validate_byte(command, "command")
    _validate_byte(value, "value")
    return bytes((0x01, command, value, 0x00))


def a7_payload(selector: int, value: int) -> bytes:
    """Build one accepted four-byte A7 setting payload."""
    _validate_byte(selector, "selector")
    _validate_byte(value, "value")
    return bytes((0x01, 0xA7, selector, value))


def state_query_payloads() -> tuple[bytes, ...]:
    """Build the accepted one-shot A7 selector-20 state requests in source order."""
    return tuple(bytes((0x01, 0xA7, 0x20, query_type)) for query_type in PAIRLINK_STATE_QUERY_TYPES)


def status_sync_payloads() -> tuple[bytes, bytes]:
    """Build the distinct A8/A9 active-session synchronization requests."""
    return (bytes.fromhex("01A80000"), bytes.fromhex("01A90000"))


def comfort_payloads(
    *,
    values: Mapping[str, int],
    current: Mapping[str, int] | None,
    force: bool,
) -> tuple[bytes, ...]:
    """Build the ordered P4 comfort sequence using accepted changed/no-state rules."""
    if not isinstance(force, bool):
        raise ValueError("Pairlink comfort force flag must be a boolean")
    current_values = current or {}
    ordered = (
        ("head_position", 1, False),
        ("foot_position", 4, False),
        ("lumbar_position", 7, True),
        ("head_massage", 77, False),
        ("foot_massage", 79, False),
    )
    payloads: list[bytes] = [bytes((0x01, 0xA7, 0x17, 0x01))]
    for name, command, inverse in ordered:
        value = values.get(name)
        if value is None:
            continue
        if name.endswith("position"):
            if not 0 <= value <= 100:
                raise ValueError(f"{name} must be between 0 and 100")
            wire_value = 100 - value if inverse else value
        else:
            if not 0 <= value <= 10:
                raise ValueError(f"{name} must be between 0 and 10")
            wire_value = 0 if value == 0 else 5 * value + 15
        if force or name not in current_values or current_values[name] != value:
            payloads.append(dashboard_payload(command, wire_value))

    for name, selector in (("timer_byte", 0x16), ("mode", 0x15)):
        value = values.get(name)
        if value is None:
            continue
        maximum = 255 if name == "timer_byte" else 4
        if not 0 <= value <= maximum:
            raise ValueError(f"{name} must be between 0 and {maximum}")
        if force or name not in current_values or current_values[name] != value:
            payloads.append(a7_payload(selector, value))
    return tuple(payloads)


def _validate_byte(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise ValueError(f"Pairlink {name} must fit one byte")


async def send_central_frame(
    writer: GattWriter,
    frame: bytes,
    *,
    characteristic: str,
    att_mtu: int,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Send one encrypted frame and preserve the 15 ms inter-fragment cadence."""
    fragments = fragment_central_frame(frame, att_mtu=att_mtu)
    for fragment in fragments:
        await writer.write_gatt_char(characteristic, fragment, response=False)
        if len(fragments) > 1:
            await sleep(0.015)


@dataclass(slots=True)
class PairlinkSignGate:
    """The accepted global broadcast and per-device sign-list gate."""

    sign_all: bool = True
    device_signs: dict[str, str] = field(default_factory=dict)

    def allows(self, destination: bytes, channel: int, *, target_mac: str) -> bool:
        if len(destination) != 4 or not 0 <= channel <= 255:
            return False
        if destination == PAIRLINK_BROADCAST_ADDRESS and 32 <= channel <= 63 and not self.sign_all:
            return False
        mac = normalize_mac(target_mac)
        device_sign = self.device_signs.get(mac)
        return device_sign is None or device_sign == "1"

    def process_type48(self, target_mac: str, status: int) -> None:
        if isinstance(status, bool) or not isinstance(status, int) or not 0 <= status <= 255:
            raise ValueError("Pairlink sign status must be one byte")
        mac = normalize_mac(target_mac)
        self.device_signs[mac] = str(status if status < 128 else status - 256)
        if status != 1:
            self.sign_all = False

    def process_network_info(self) -> None:
        self.device_signs.clear()
        self.sign_all = True


def normalize_mac(value: str) -> str:
    """Normalize one exact six-byte colon- or hyphen-separated MAC address."""
    if not isinstance(value, str) or len(value) != 17:
        raise ValueError("Pairlink target MAC must contain six hexadecimal octets")
    separator = value[2]
    if separator not in (":", "-"):
        raise ValueError("Pairlink target MAC must contain six hexadecimal octets")
    parts = value.split(separator)
    if len(parts) != 6 or any(
        len(part) != 2 or any(character not in "0123456789abcdefABCDEF" for character in part)
        for part in parts
    ):
        raise ValueError("Pairlink target MAC must contain six hexadecimal octets")
    octets = [int(part, 16) for part in parts]
    return ":".join(f"{octet:02X}" for octet in octets)


def parse_state_event(
    event_type: int | None,
    event_data: bytes | None,
) -> tuple[tuple[str, object], ...]:
    """Parse the accepted Pairlink type-32 A7/A8/A9 response subset."""
    if event_type is None or event_type != 32:
        return ()
    if event_data is None or len(event_data) < 8:
        return ()
    inner = event_data[4:]
    if len(inner) < 4 or inner[0] != 0x02:
        return ()
    message = inner[1:]
    if message[0] == 0xA7:
        if len(message) < 3:
            return ()
        selector, value = message[1], message[2]
        if selector in (15, 16):
            return (("pairlink_selector_event", (selector, value)),)
        state = _state_key(selector, value)
        return () if state is None else (state,)
    if message[0] == 0xA8:
        if len(message) < 3:
            return ()
        selectors = [index + 1 for index in range(8) if message[1] & (1 << index)]
        selectors.extend(index + 9 for index in range(5) if message[2] & (1 << index))
        if message[2] & 0xE0:
            selectors.append(14)
        return (("pairlink_changed_selectors", tuple(dict.fromkeys(selectors))),)
    if message[0] == 0xA9:
        if len(message) < 2:
            return ()
        selectors = [index + 7 for index in range(4) if message[1] & (1 << (index + 1))]
        if message[1] & 0x01:
            selectors.append(17)
        return (("pairlink_changed_selectors", tuple(dict.fromkeys(selectors))),)
    return ()


def _state_key(selector: int, value: int) -> tuple[str, object] | None:
    scalar_keys = {
        1: "back_position",
        2: "legs_position",
        3: "reverie_pairlink_head2_position",
        4: "reverie_pairlink_head2_position",
        5: "massage_head_intensity",
        6: "massage_foot_intensity",
        7: "light_level",
        11: "pairlink_low_battery",
        12: "reverie_massage_mode",
        13: "reverie_massage_rhythm",
        14: "reverie_massage_timer",
        17: "under_bed_lights_on",
    }
    key = scalar_keys.get(selector)
    if key is not None:
        if selector in (5, 6):
            return key, max(0, min(10, (value - 15) // 5)) if value else 0
        if selector == 11:
            return key, value == 3
        if selector == 12:
            return key, value if 1 <= value <= 4 else 0
        if selector == 13:
            return key, value == 1
        if selector == 17:
            return key, value != 0
        return key, value
    if selector in (8, 9, 10):
        return f"reverie_pairlink_rgb_{selector - 7}", value
    return None
