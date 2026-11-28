"""Accepted unit171 normal-route literals, checked before profile implementation."""

import json
from pathlib import Path

from custom_components.adjustable_bed.codec import richmat as codec

FROZEN = json.loads((Path(__file__).parent / "fixtures/purely_sleep_vectors.json").read_text())


def test_all_90_frozen_vectors_match_the_existing_richmat_codec():
    vectors = FROZEN["vectors"]
    assert len(vectors) == 90
    for vector in vectors:
        args = vector["inputs"]
        if "opcode" in args:
            packet = codec.function(args["opcode"], args["side"], single=vector["protocol"] == "P2")
        else:
            packet = codec.frame(*args["prefix_payload"])
        assert packet == bytes.fromhex(vector["expected_bytes"]), vector["id"]


def test_all_six_declared_gatt_roles_match_the_existing_codec():
    for key, row in zip(("n1", "w1", "w2", "w3", "w4", "w5"), FROZEN["routes"], strict=True):
        route = codec.TRANSPORTS[key]
        assert (route.service_uuid, route.write_uuid, route.notify_uuid) == tuple(
            row[field].lower() for field in ("service", "write", "declared_notify")
        )
