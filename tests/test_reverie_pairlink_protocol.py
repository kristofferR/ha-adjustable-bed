"""Focused artifact-vector tests for the Pairlink central protocol helpers."""

import pytest

from custom_components.adjustable_bed.beds.reverie_pairlink_protocol import (
    PAIRLINK_BROADCAST_ADDRESS,
    PAIRLINK_WRITE_UUID,
    PairlinkSignGate,
    a7_payload,
    build_default_event_key,
    build_user_frame,
    comfort_payloads,
    dashboard_payload,
    encrypt_user_frame,
    fragment_central_frame,
    normalize_mac,
    parse_state_event,
    send_central_frame,
    state_query_payloads,
    status_sync_payloads,
)

_SYNTHETIC_PASSWORD_BYTES = b"1122"


def test_accepted_synthetic_frame_and_event_key_vector() -> None:
    key = build_default_event_key(5566, _SYNTHETIC_PASSWORD_BYTES)
    frame = build_user_frame(
        bytes.fromhex("0101FF00"),
        destination=PAIRLINK_BROADCAST_ADDRESS,
        channel=32,
        own_virtual_address=bytes.fromhex("11223344"),
    )

    assert key.hex() == "be311531003200324556454e544b4559"
    assert frame.hex() == "03ffffffff20112233440101ff00"


def test_accepted_synthetic_encryption_vector() -> None:
    pytest.importorskip("cryptography")
    event_key = build_default_event_key(5566, _SYNTHETIC_PASSWORD_BYTES)
    frame = build_user_frame(
        bytes.fromhex("0101FF00"),
        destination=bytes.fromhex("FFFFFFFF"),
        channel=32,
        own_virtual_address=bytes.fromhex("11223344"),
    )

    encrypted = encrypt_user_frame(
        frame,
        event_key=event_key,
        device_key=bytes.fromhex("10203040"),
    )

    assert encrypted.hex() == "06ffffffff20b8abb7ebe90ad638109bf63bb25df787"


def test_crypto_requires_an_explicit_four_byte_device_key() -> None:
    with pytest.raises(ValueError, match="device key"):
        encrypt_user_frame(
            bytes.fromhex("03FFFFFFFF21112233440101FF00"),
            event_key=bytes.fromhex("BE311531003200324556454E544B4559"),
            device_key=b"",
        )


def test_fragmenter_uses_accepted_nibble_header_and_real_mtu() -> None:
    frame = bytes(range(21))

    fragments = fragment_central_frame(frame, att_mtu=23)

    assert fragments == (
        bytes.fromhex("012121") + bytes(range(17)),
        bytes.fromhex("012122") + bytes(range(17, 21)),
    )
    assert fragment_central_frame(b"short", att_mtu=23) == (b"short",)


def test_dashboard_and_a7_payloads_match_accepted_command_bytes() -> None:
    assert dashboard_payload(92).hex() == "015c0000"
    assert a7_payload(16, 100).hex() == "01a71064"


def test_state_queries_and_active_status_sync_match_accepted_vectors() -> None:
    assert tuple(payload.hex() for payload in state_query_payloads()) == tuple(
        f"01a720{query_type:02x}" for query_type in (1, 2, 3, 5, 6, 17, 7, 8, 9, 10, 11, 12, 13, 14)
    )
    assert tuple(payload.hex() for payload in status_sync_payloads()) == (
        "01a80000",
        "01a90000",
    )


def test_comfort_sequence_deduplicates_known_state_and_force_sends_eight_frames() -> None:
    values = {
        "head_position": 25,
        "foot_position": 60,
        "lumbar_position": 12,
        "head_massage": 0,
        "foot_massage": 5,
        "timer_byte": 15,
        "mode": 3,
    }
    expected = tuple(
        bytes.fromhex(frame)
        for frame in (
            "01A71701",
            "01011900",
            "01043C00",
            "01075800",
            "014D0000",
            "014F2800",
            "01A7160F",
            "01A71503",
        )
    )

    assert comfort_payloads(values=values, current=None, force=True) == expected
    assert comfort_payloads(values=values, current=values, force=False) == (
        bytes.fromhex("01A71701"),
    )
    changed = {**values, "head_position": 20}
    assert comfort_payloads(values=changed, current=values, force=False) == (
        bytes.fromhex("01A71701"),
        bytes.fromhex("01011400"),
    )


def test_sign_gate_preserves_global_and_device_specific_rules() -> None:
    gate = PairlinkSignGate()
    mac = "aa-bb-cc-dd-ee-ff"
    broadcast = bytes.fromhex("FFFFFFFF")

    gate.process_type48(mac, 0)
    assert not gate.allows(broadcast, 33, target_mac=mac)
    assert not gate.allows(bytes.fromhex("01020304"), 33, target_mac=mac)
    assert gate.allows(bytes.fromhex("01020304"), 33, target_mac="11:22:33:44:55:66")
    gate.process_type48(mac, 1)
    assert gate.allows(bytes.fromhex("01020304"), 33, target_mac=mac)
    assert not gate.allows(broadcast, 33, target_mac=mac)
    gate.process_network_info()
    assert gate.allows(broadcast, 33, target_mac=mac)


def test_mac_normalization_requires_six_exact_hex_octets() -> None:
    assert normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"
    for malformed in (
        "+1:bb:cc:dd:ee:ff",
        " 1:bb:cc:dd:ee:ff",
        "aa-bb:cc-dd-ee-ff",
        "aa:bb:cc:dd:ee:fg",
    ):
        with pytest.raises(ValueError, match="six hexadecimal octets"):
            normalize_mac(malformed)


def test_state_parser_keeps_duplicate_a7_and_deduplicates_a8_flags() -> None:
    a7 = bytes.fromhex("0000000002A70164")
    a8 = bytes.fromhex("0000000002A8FF20")
    a9 = bytes.fromhex("0000000002A91F00")

    assert parse_state_event(32, a7) == (("back_position", 100),)
    assert parse_state_event(32, a7) == (("back_position", 100),)
    assert parse_state_event(32, a8) == (
        ("pairlink_changed_selectors", tuple(range(1, 9)) + (14,)),
    )
    assert parse_state_event(32, a9) == (("pairlink_changed_selectors", (7, 8, 9, 10, 17)),)


def test_state_parser_rejects_unrecognized_event_envelopes() -> None:
    valid = bytes.fromhex("0000000002A70164")
    assert parse_state_event(47, valid) == ()
    assert parse_state_event(31, valid) == ()
    assert parse_state_event(32, None) == ()
    assert parse_state_event(32, valid[:7]) == ()
    assert parse_state_event(32, bytes.fromhex("0000000003A70164")) == ()


async def test_sender_uses_no_response_and_sleeps_after_every_fragment() -> None:
    class Writer:
        def __init__(self) -> None:
            self.writes: list[tuple[str, bytes, bool]] = []

        async def write_gatt_char(
            self, characteristic: str, data: bytes, *, response: bool
        ) -> None:
            self.writes.append((characteristic, data, response))

    writer = Writer()
    sleeps: list[float] = []

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    await send_central_frame(
        writer,
        bytes(range(21)),
        characteristic=PAIRLINK_WRITE_UUID,
        att_mtu=23,
        sleep=record_sleep,
    )

    assert [(uuid, response) for uuid, _, response in writer.writes] == [
        (PAIRLINK_WRITE_UUID, False),
        (PAIRLINK_WRITE_UUID, False),
    ]
    assert sleeps == [0.015, 0.015]
