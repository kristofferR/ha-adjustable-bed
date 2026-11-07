"""Source-vector tests for Pairlink credentials, sessions, and receive reducers."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS

from custom_components.adjustable_bed.beds.reverie.pairlink_protocol import (
    build_user_frame,
    decrypt_login_block,
    derive_event_key_from_seed,
    derive_event_key_index,
    encrypt_login_block,
)
from custom_components.adjustable_bed.beds.reverie.pairlink_runtime import (
    PairlinkCredentials,
    PairlinkHomeIdOrigin,
    PairlinkMeshEvent,
    PairlinkRole,
    PairlinkRuntime,
    PairlinkRuntimeNotReadyError,
    PairlinkSendReply,
    _derive_provision_confirmation,
    _derive_provision_data,
    create_pairlink_runtime_for_entry,
    encode_pairlink_password,
    normalize_home_id,
)
from custom_components.adjustable_bed.beds.reverie.pairlink_transport import PairlinkPeerIdentity
from custom_components.adjustable_bed.const import CONF_PAIRLINK_HOME_ID

_HOME = 5566
_HOME_LE = _HOME.to_bytes(4, "little")
_PASSWORD = b"1122"
_CENTRAL = "AA:BB:CC:DD:EE:FF"
_LOGIN_CONTEXT = b"".join(
    bytes((home, password)) for home, password in zip(_HOME_LE, _PASSWORD, strict=True)
) + b"LOGINKEY"


def _credentials() -> PairlinkCredentials:
    return PairlinkCredentials.from_inputs(
        _HOME,
        home_id_origin=PairlinkHomeIdOrigin.DECLARED_HA_POLICY,
    )


def _central_runtime() -> PairlinkRuntime:
    runtime = PairlinkRuntime(
        _credentials(),
        role=PairlinkRole.CENTRAL,
        target_mac=_CENTRAL,
        local_join_bt_mac=bytes.fromhex("010203040506"),
    )
    runtime.central_connected(_CENTRAL)
    return runtime


def _local_identity(last_octet: int, generation: int) -> PairlinkPeerIdentity:
    address = f"02:00:00:00:00:{last_octet:02X}"
    return PairlinkPeerIdentity(
        "/org/bluez/hci3",
        f"/org/bluez/hci3/dev_{address.replace(':', '_')}",
        address,
        generation,
    )


def _login_payload(home: bytes = _HOME_LE, session: bytes = bytes.fromhex("10203040")) -> bytes:
    return b"\x01\x19" + encrypt_login_block(home + session + b"ignored!", login_key=_LOGIN_CONTEXT)


def test_ha_password_policy_is_exact_and_secrets_are_not_repr_material() -> None:
    credentials = PairlinkCredentials.from_inputs(
        -1,
        home_id_origin=PairlinkHomeIdOrigin.EXPLICIT_CONFIG,
        password_text="éé",
    )
    assert credentials.home_id_le == bytes.fromhex("FFFFFFFF")
    assert credentials.password == "éé".encode()
    assert credentials.password_origin == "utf8_text"
    assert "éé" not in repr(credentials)
    assert bytes.fromhex("31313232") not in repr(credentials).encode()

    assert encode_pairlink_password(password_hex="41424344") == (
        b"ABCD",
        "exact_hex",
    )
    with pytest.raises(ValueError, match="exactly four bytes"):
        encode_pairlink_password(password_text="abc")
    with pytest.raises(ValueError, match="overrides only"):
        encode_pairlink_password(password_text="2233", password_hex="41424344")
    with pytest.raises(ValueError, match="exactly eight digits"):
        encode_pairlink_password(password_hex="4142434Z")


def test_entry_uses_source_home_id_precedence_and_rejects_invalid_explicit_value() -> None:
    default_runtime = create_pairlink_runtime_for_entry(
        {CONF_ADDRESS: _CENTRAL},
        {},
        manufacturer_data=None,
    )
    assert default_runtime.credentials.home_id_le == (5566).to_bytes(4, "little")
    assert (
        default_runtime.credentials.home_id_origin
        is PairlinkHomeIdOrigin.DECLARED_HA_POLICY
    )
    assert normalize_home_id(-1) == bytes.fromhex("FFFFFFFF")

    with pytest.raises(ValueError, match="decimal integer"):
        create_pairlink_runtime_for_entry(
            {CONF_ADDRESS: _CENTRAL, CONF_PAIRLINK_HOME_ID: "not-a-home-id"},
            {},
            manufacturer_data=None,
        )


def test_native_provision_cmac_and_cipher_match_the_accepted_arithmetic_vector() -> None:
    capability = bytes(7)
    start = bytes(3)
    local_public = bytes(range(64))
    peer_public = bytes(range(64, 128))
    shared_secret = bytes(range(32))
    local_random = bytes(range(16))
    peer_random = bytes(range(16, 32))

    confirmation_salt, confirmation = _derive_provision_confirmation(
        capability=capability,
        start=start,
        local_public_key=local_public,
        peer_public_key=peer_public,
        shared_secret=shared_secret,
        local_random=local_random,
        auth=bytes(16),
    )
    device_key, session_key, nonce_material, ciphertext = _derive_provision_data(
        confirmation_salt=confirmation_salt,
        shared_secret=shared_secret,
        local_random=local_random,
        peer_random=peer_random,
        plaintext=bytes.fromhex("5566AABB0501BE1500000504313132320203A6"),
    )

    assert confirmation_salt == bytes.fromhex("003587903CF4BA39F9CC6D1075CBB734")
    assert confirmation == bytes.fromhex("5EAE07CAB22C9E9B8DC9309C912EA195")
    assert device_key == bytes.fromhex("0DD2649A0232FD2276DB0C70F260677C")
    assert session_key == bytes.fromhex("CB17CE65D595D9A8750A2D7D7851DEB3")
    assert nonce_material == bytes.fromhex("73BA113E80F65A5ADC820D42E7903E6E")
    assert ciphertext == bytes.fromhex(
        "20BC9FD12F12F42EFD7DD53B90F9C0CB"
        "7E90420266EC08AC7C3517937152F992"
    )


def test_native_login_admits_seven_unique_peers_and_replies_without_duplicate_refresh() -> None:
    pytest.importorskip("cryptography")
    runtime = PairlinkRuntime(
        _credentials(),
        role=PairlinkRole.PERIPHERAL,
        target_mac=None,
        local_join_bt_mac=bytes.fromhex("010203040506"),
    )
    runtime.host_adapter_path = "/org/bluez/hci3"
    first_peer = _local_identity(1, 1)
    runtime.peer_connected(first_peer)
    first = runtime.process_transport_packet(
        _login_payload(), source_mac=first_peer.address, peer=first_peer
    )
    assert len(first) == 1 and isinstance(first[0], PairlinkSendReply)
    assert first[0].payload.startswith(b"\x02\x19")
    original_session = runtime._peer_keys[first_peer.address]

    duplicate_session = bytes.fromhex("AABBCCDD")
    duplicate = runtime.process_transport_packet(
        _login_payload(session=duplicate_session),
        source_mac=first_peer.address,
        peer=first_peer,
    )
    assert len(duplicate) == 1 and isinstance(duplicate[0], PairlinkSendReply)
    assert runtime._peer_keys[first_peer.address] == original_session
    duplicate_plain = decrypt_login_block(duplicate[0].payload[2:], login_key=_LOGIN_CONTEXT)
    assert duplicate_plain[8:12] == duplicate_session

    for index in range(2, 8):
        peer = _local_identity(index, index)
        runtime.peer_connected(peer)
        effects = runtime.process_transport_packet(
            _login_payload(session=index.to_bytes(4, "little")),
            source_mac=peer.address,
            peer=peer,
        )
        assert len(effects) == 1
    assert runtime.admitted_peer_count == 7

    full_peer = _local_identity(0xFE, 8)
    runtime.peer_connected(full_peer)
    full_table = runtime.process_transport_packet(
        _login_payload(session=bytes.fromhex("FFEEDDCC")),
        source_mac=full_peer.address,
        peer=full_peer,
    )
    assert len(full_table) == 1 and isinstance(full_table[0], PairlinkSendReply)
    assert runtime.admitted_peer_count == 7
    assert full_peer.address not in runtime._peer_keys


def test_wrong_home_and_malformed_login_have_no_native_session_effect() -> None:
    pytest.importorskip("cryptography")
    runtime = _central_runtime()

    assert runtime.process_transport_packet(b"\x01\x19short", source_mac=_CENTRAL) == ()
    wrong_home = runtime.process_transport_packet(
        _login_payload(home=(5567).to_bytes(4, "little")), source_mac=_CENTRAL
    )

    assert wrong_home == ()
    assert runtime.admitted_peer_count == 0
    assert runtime.central_add_pending is True
    assert runtime.joined is False


def test_event_seed_replacement_matches_native_cmac_history_and_zero_reset() -> None:
    pytest.importorskip("cryptography")
    runtime = _central_runtime()

    first_seed = bytes.fromhex("01020304")
    runtime.process_transport_packet(
        b"\x01\x02\x00\x00\x00\x00\x00\x00\x00\x00" + first_seed,
        source_mac=_CENTRAL,
    )
    first_key = derive_event_key_from_seed(first_seed)
    first_index = derive_event_key_index(first_key)
    assert runtime.current_event_key == first_key
    assert runtime.event_key_index == first_index
    assert runtime.event_key_history[-1] == (bytes(4), first_index, first_key)

    second_seed = bytes.fromhex("A1A2A3A4")
    encrypted_channel11 = b"\x03\xFF\xFF\xFF\xFF\x11\x32" + second_seed
    # The encrypted receive route requires an admitted target key.
    runtime.process_transport_packet(_login_payload(), source_mac=_CENTRAL)
    from custom_components.adjustable_bed.beds.reverie.pairlink_protocol import encrypt_user_frame

    encrypted = encrypt_user_frame(
        encrypted_channel11,
        event_key=first_key,
        device_key=bytes.fromhex("10203040"),
    )
    runtime.process_transport_packet(encrypted, source_mac=_CENTRAL)
    second_key = derive_event_key_from_seed(second_seed)
    second_index = derive_event_key_index(second_key)
    assert runtime.current_event_key == second_key
    assert runtime.event_key_index == second_index
    assert runtime.event_key_history[-1] == (bytes(4), second_index, second_key)

    runtime.process_transport_packet(
        b"\x01\x02\x00\x00\x00\x00\x00\x00\x00\x00" + bytes(4),
        source_mac=_CENTRAL,
    )
    assert runtime.current_event_key == second_key
    assert runtime.event_key_index == bytes(4)
    assert runtime.event_key_history[-1] == (bytes(4), second_index, second_key)


def test_central_disconnect_clears_native_session_and_own_address_but_keeps_key_history() -> None:
    pytest.importorskip("cryptography")
    runtime = _central_runtime()
    runtime.process_transport_packet(_login_payload(), source_mac=_CENTRAL)
    runtime.source_joined(_CENTRAL)
    runtime.process_transport_packet(bytes.fromhex("010A11223344"), source_mac=_CENTRAL)
    runtime.process_transport_packet(
        b"\x01\x02\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04",
        source_mac=_CENTRAL,
    )
    retained_key = runtime.current_event_key
    retained_index = runtime.event_key_index
    retained_history = runtime.event_key_history

    runtime.central_disconnected(_CENTRAL)

    assert runtime.admitted_peer_count == 0
    assert runtime.joined is False
    assert runtime.own_virtual_address == bytes(4)
    assert runtime.own_virtual_address_assigned is False
    assert runtime.current_event_key == retained_key
    assert runtime.event_key_index == retained_index
    assert runtime.event_key_history == retained_history


def test_local_peer_identity_and_subscription_lifetimes_are_independent() -> None:
    runtime = PairlinkRuntime(
        _credentials(),
        role=PairlinkRole.PERIPHERAL,
        target_mac=None,
        local_join_bt_mac=bytes.fromhex("010203040506"),
    )
    runtime.host_adapter_path = "/org/bluez/hci3"
    first = PairlinkPeerIdentity(
        "/org/bluez/hci3",
        "/org/bluez/hci3/dev_11_22_33_44_55_66",
        "11:22:33:44:55:66",
        1,
    )
    second = PairlinkPeerIdentity(
        "/org/bluez/hci3",
        "/org/bluez/hci3/dev_22_33_44_55_66_77",
        "22:33:44:55:66:77",
        2,
    )

    runtime.peer_connected(first)
    runtime.peer_connected(second)
    assert runtime.process_transport_packet(b"\x01\x00" + bytes(4), source_mac=first.address, peer=first) == ()
    assert runtime.process_transport_packet(b"\x01\x00" + bytes(4), source_mac=second.address, peer=second) == ()
    assert set(runtime.peer_sessions) == {first.address, second.address}

    runtime.peer_subscribed(first, 64)
    runtime.peer_unsubscribed(first)
    assert runtime.peer_sessions[first.address].connected is True
    assert runtime.peer_sessions[first.address].subscribed is False
    assert runtime.peer_sessions[second.address].connected is True
    runtime.peer_disconnected(first)
    assert first.address not in runtime.peer_sessions
    assert second.address in runtime.peer_sessions

    wrong_adapter = PairlinkPeerIdentity(
        "/org/bluez/hci4",
        "/org/bluez/hci4/dev_33_44_55_66_77_88",
        "33:44:55:66:77:88",
        3,
    )
    with pytest.raises(ConnectionError, match="another local adapter"):
        runtime.peer_connected(wrong_adapter)


def test_fragment_assembly_is_peer_generation_scoped_and_restarts_on_new_first() -> None:
    runtime = PairlinkRuntime(
        _credentials(),
        role=PairlinkRole.PERIPHERAL,
        target_mac=None,
        local_join_bt_mac=bytes.fromhex("010203040506"),
    )
    runtime.host_adapter_path = "/org/bluez/hci3"
    first_peer = _local_identity(0x21, 21)
    second_peer = _local_identity(0x22, 22)
    runtime.peer_connected(first_peer)
    runtime.peer_connected(second_peer)

    first_frame = build_user_frame(
        b"\x02\xA7\x01\x35",
        destination=bytes.fromhex("01020304"),
        channel=32,
        own_virtual_address=bytes.fromhex("AABBCCDD"),
    )
    second_frame = build_user_frame(
        b"\x02\xA7\x01\x49",
        destination=bytes.fromhex("05060708"),
        channel=32,
        own_virtual_address=bytes.fromhex("11223344"),
    )

    def fragments(frame: bytes) -> tuple[bytes, bytes]:
        split = len(frame) // 2
        return (
            b"\x04\x04\x21" + frame[:split],
            b"\x04\x04\x22" + frame[split:],
        )

    first_part, first_final = fragments(first_frame)
    second_part, second_final = fragments(second_frame)
    assert runtime.process_transport_packet(
        first_part, source_mac=first_peer.address, peer=first_peer
    ) == ()

    assert runtime.process_transport_packet(
        second_part, source_mac=second_peer.address, peer=second_peer
    ) == ()
    second_effects = runtime.process_transport_packet(
        second_final, source_mac=second_peer.address, peer=second_peer
    )
    assert len(second_effects) == 1
    assert isinstance(second_effects[0], PairlinkMeshEvent)
    assert second_effects[0].event_data == b"\x11\x22\x33\x44\x02\xA7\x01\x49"
    assert second_effects[0].source_mac == second_peer.address

    runtime.peer_disconnected(first_peer)
    fresh_peer = _local_identity(0x21, 23)
    runtime.peer_connected(fresh_peer)
    assert runtime.process_transport_packet(
        first_final, source_mac=fresh_peer.address, peer=fresh_peer
    ) == ()

    fresh_frame = build_user_frame(
        b"\x02\xA7\x01\x5A",
        destination=bytes.fromhex("090A0B0C"),
        channel=32,
        own_virtual_address=bytes.fromhex("55667788"),
    )
    fresh_part, fresh_final = fragments(fresh_frame)
    assert runtime.process_transport_packet(
        fresh_part, source_mac=fresh_peer.address, peer=fresh_peer
    ) == ()
    fresh_effects = runtime.process_transport_packet(
        fresh_final, source_mac=fresh_peer.address, peer=fresh_peer
    )
    assert len(fresh_effects) == 1
    assert isinstance(fresh_effects[0], PairlinkMeshEvent)
    assert fresh_effects[0].event_data == b"\x55\x66\x77\x88\x02\xA7\x01\x5A"


def test_fragment_duplicate_first_preserves_active_source_transfer() -> None:
    runtime = PairlinkRuntime(
        _credentials(),
        role=PairlinkRole.PERIPHERAL,
        target_mac=None,
        local_join_bt_mac=bytes.fromhex("010203040506"),
    )
    runtime.host_adapter_path = "/org/bluez/hci3"
    peer = _local_identity(0x21, 21)
    runtime.peer_connected(peer)

    # Frozen SDK_STATE source vector: the repeated first fragment is a gap.
    first = bytes.fromhex("04042103FFFFFFFF")
    duplicate_first = bytes.fromhex("0404210301020304")
    final = bytes.fromhex("0404222002A70144")

    assert runtime.process_transport_packet(
        first, source_mac=peer.address, peer=peer
    ) == ()
    assert runtime.process_transport_packet(
        duplicate_first, source_mac=peer.address, peer=peer
    ) == ()
    effects = runtime.process_transport_packet(
        final, source_mac=peer.address, peer=peer
    )

    assert len(effects) == 1
    event = effects[0]
    assert isinstance(event, PairlinkMeshEvent)
    assert event.broadcast is True
    assert event.event_type == 0x20
    assert event.event_data == bytes.fromhex("02A70144")
    assert event.source_mac == peer.address


def test_fragment_valid_gap_does_not_change_expected_sequence_or_payload() -> None:
    runtime = PairlinkRuntime(
        _credentials(),
        role=PairlinkRole.PERIPHERAL,
        target_mac=None,
        local_join_bt_mac=bytes.fromhex("010203040506"),
    )
    runtime.host_adapter_path = "/org/bluez/hci3"
    peer = _local_identity(0x21, 21)
    runtime.peer_connected(peer)

    first = bytes.fromhex("04043103FFFFFFFF")
    gap = bytes.fromhex("04043303DEADBEEF")
    second = bytes.fromhex("0404322002A7")
    final = bytes.fromhex("0404330144")

    assert runtime.process_transport_packet(
        first, source_mac=peer.address, peer=peer
    ) == ()
    assert runtime.process_transport_packet(
        gap, source_mac=peer.address, peer=peer
    ) == ()
    assert runtime.process_transport_packet(
        second, source_mac=peer.address, peer=peer
    ) == ()
    effects = runtime.process_transport_packet(
        final, source_mac=peer.address, peer=peer
    )

    assert len(effects) == 1
    event = effects[0]
    assert isinstance(event, PairlinkMeshEvent)
    assert event.broadcast is True
    assert event.event_type == 0x20
    assert event.event_data == bytes.fromhex("02A70144")
    assert event.source_mac == peer.address


def test_local_join_does_not_infer_remote_device_type_or_crypto_branch() -> None:
    runtime = PairlinkRuntime(
        _credentials(),
        role=PairlinkRole.PERIPHERAL,
        target_mac=None,
        local_join_bt_mac=bytes.fromhex("010203040506"),
    )
    runtime.host_adapter_path = "/org/bluez/hci3"
    peer = _local_identity(0x22, 1)
    runtime.peer_connected(peer)
    runtime.peer_subscribed(peer, 64)
    runtime.source_joined(peer.address)

    assert runtime.joined is True
    assert runtime.primary_mac == peer.address
    assert runtime.peer_sessions[peer.address].device_type is None
    with pytest.raises(PairlinkRuntimeNotReadyError, match="peer type is not established"):
        runtime.prepare_send()


def test_local_peer_generations_and_auth_are_isolated_from_other_peer_changes() -> None:
    pytest.importorskip("cryptography")
    runtime = PairlinkRuntime(
        _credentials(),
        role=PairlinkRole.PERIPHERAL,
        target_mac=None,
        local_join_bt_mac=bytes.fromhex("010203040506"),
    )
    runtime.host_adapter_path = "/org/bluez/hci3"
    primary = _local_identity(0x21, 21)
    backup = _local_identity(0x22, 22)

    runtime.peer_connected(primary)
    runtime.peer_subscribed(primary, 64)
    runtime.process_transport_packet(
        _login_payload(), source_mac=primary.address, peer=primary
    )
    runtime.process_transport_packet(
        b"\x02\x31\x08", source_mac=primary.address, peer=primary
    )
    primary_snapshot = runtime.prepare_send()

    runtime.peer_connected(backup)
    runtime.peer_subscribed(backup, 64)
    runtime.process_transport_packet(
        _login_payload(session=bytes.fromhex("A1A2A3A4")),
        source_mac=backup.address,
        peer=backup,
    )
    assert runtime.snapshot_is_current(primary_snapshot)
    assert runtime.peer_sessions[backup.address].backup is True

    runtime.peer_unsubscribed(backup)
    assert runtime.snapshot_is_current(primary_snapshot)
    runtime.peer_disconnected(backup)
    assert runtime.snapshot_is_current(primary_snapshot)
    assert primary.address in runtime._peer_keys
    assert backup.address not in runtime._peer_keys

    runtime.peer_unsubscribed(primary)
    assert not runtime.snapshot_is_current(primary_snapshot)
    runtime.peer_subscribed(primary, 64)
    assert not runtime.snapshot_is_current(primary_snapshot)
