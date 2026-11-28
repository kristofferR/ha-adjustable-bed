"""Flexx Motion's bounded static subset, without runnable bed/session claims."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles import flexx_motion as profile

ACCEPTED = json.loads((Path(__file__).parent / "fixtures/flexx_motion/accepted.json").read_text())
PRESET_KEYS = {
    "M1": "memory_1",
    "M2": "memory_2",
    "Anti-snoring": "anti_snore",
    "Zero Gravity": "zero_g",
    "Soothing Sleep": "soothing_sleep",
    "TV": "tv",
    "Lounge": "lounge",
}


@pytest.mark.parametrize("row", ACCEPTED["tx_vectors"], ids=lambda row: row["id"])
def test_existing_codec_matches_all_frozen_transmit_literals(row):
    args = row["inputs"]
    assert codec.function(args["opcode"], args["side"], single=args["nordic"]) == bytes.fromhex(
        row["expected_bytes"]
    )


@pytest.mark.parametrize(
    "row", ACCEPTED["preset_rows"], ids=lambda row: row["path"] + row["action"]
)
def test_profile_matches_every_accepted_preset_and_product_membership(row):
    operation, label = row["action"].split(" ", 1)
    preset = next(p for p in profile.PRESETS if p.key == PRESET_KEYS[label])
    assert getattr(preset, operation) == row["opcode"]
    assert [s.product for s in profile.SUBSETS if preset in s.presets] == row["products"]


@pytest.mark.parametrize("row", ACCEPTED["gatt_catalog"])
def test_catalog_roles_match_existing_codec_without_claiming_matching_predicates(row):
    key = profile.CATALOG_TRANSPORTS[row["ordinal"]]
    transport = codec.TRANSPORTS[key]
    assert transport.service_uuid == row["service"].lower()
    assert transport.write_uuid == row["write_hint"].lower()
    assert transport.notify_uuid == row["notify_hint"].lower()


def test_no_synthetic_save_or_motion_capabilities_in_partial_profiles():
    assert profile.SOOTHING_SLEEP.save is None
    assert profile.PRESET_WRITES == 1 and profile.PRESET_RELEASE is False
    assert profile.QUEUE_CYCLE_MS == 100 and profile.RECEIVE_EXPIRY_S == 0.5
    assert {s.product for s in profile.SUBSETS} == {
        product for row in ACCEPTED["preset_rows"] for product in row["products"]
    }
    for subset in profile.SUBSETS:
        assert {p.key for p in subset.presets} == {
            PRESET_KEYS[row["action"].split(" ", 1)[1]]
            for row in ACCEPTED["preset_rows"]
            if subset.product in row["products"]
        }


@pytest.mark.parametrize("row", ACCEPTED["rx_literals"], ids=lambda row: row["id"])
def test_literal_receive_records_are_frames_without_capability_inference(row):
    parser = codec.NextHeaderBuffer()
    assert parser.feed(bytes.fromhex(row["inputs"]["received_hex"])) == [
        bytes.fromhex(row["expected_bytes"])
    ]
    assert not parser.pending


def test_common_boundaries_preserve_early_dispatch_and_have_no_blanket_sum_check():
    parser = codec.NextHeaderBuffer()
    alarm, light = (bytes.fromhex(row["expected_bytes"]) for row in ACCEPTED["rx_literals"])
    assert parser.feed(b"\x01\x02" + alarm + light) == [alarm, light]
    assert parser.feed(alarm[:3]) == [alarm[:3]]  # No fixed-length common reassembly.
    assert parser.feed(alarm[3:] + light) == [light]
    assert parser.feed(light[:-1] + b"\x00") == [light[:-1] + b"\x00"]
    assert not parser.pending


def test_length_record_fragments_checksum_rejection_and_following_common_record():
    parser = codec.NextHeaderBuffer()
    # Synthetic positive-length envelope from repair_reproduce.py, not a state vector.
    record = bytes.fromhex("6e20050194")
    light = bytes.fromhex(ACCEPTED["rx_literals"][1]["expected_bytes"])
    for part in (record[:2], record[2:4]):
        assert parser.feed(part) == []
    assert parser.feed(record[4:] + record[:-1] + b"\x95" + light) == [record, light]
    assert not parser.pending
    assert parser.feed(record[:3]) == []
    parser.expire()
    assert not parser.pending
    assert parser.feed(light) == [light]


def test_excluded_envelopes_are_consumed_without_payload_dispatch():
    parser = codec.NextHeaderBuffer()
    # Synthetic desk/firmware boundaries stay out of direct-bed responses.
    desk = bytes.fromhex("6e21050094")
    firmware = bytes.fromhex("6e40000800017753")
    light = bytes.fromhex(ACCEPTED["rx_literals"][1]["expected_bytes"])
    assert parser.feed(firmware[:3]) == []  # Safe divergence from the app's short guard.
    assert parser.feed(firmware[3:] + desk + light) == [light]
    assert not parser.pending


@pytest.mark.parametrize("raw", ("6e40000800017753", "6e40000801027401"))
def test_existing_crc_matches_repair_synthetic_checks_without_ota_support(raw):
    record = bytes.fromhex(raw)
    assert codec.is_valid_crc(record)
    assert not codec.is_valid_crc(record[:-1] + bytes((record[-1] ^ 1,)))


@pytest.mark.parametrize("kind,minimum", ((0x20, 4), (0x21, 4), (0x40, 6)))
def test_malformed_lengths_are_rejected_instead_of_emulating_unverified_app_behavior(kind, minimum):
    for size in range(minimum):
        parser = codec.NextHeaderBuffer()
        length = size.to_bytes(2 if kind == 0x40 else 1, "big")
        assert parser.feed(bytes((codec.BED, kind)) + length + b"\x01\x02") == []
        assert not parser.pending


def test_noise_resynchronization_retains_a_short_header_until_expiry():
    parser = codec.NextHeaderBuffer()
    assert parser.feed(b"\x00\x01\x02") == []
    assert not parser.pending
    assert parser.feed(b"\x01\x02\x6e") == []
    assert parser.pending == b"\x6e"
    parser.expire()
    assert not parser.pending
