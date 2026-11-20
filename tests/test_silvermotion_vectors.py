"""Every native output, its embedded fields, and its actual transport slices."""

import pytest

from custom_components.adjustable_bed.codec import silvermotion as codec
from custom_components.adjustable_bed.profiles import silvermotion as app
from tests.silvermotion_vectors import VECTORS


@pytest.mark.parametrize("action,payload,repeat,delay,plain,wire,chunks", VECTORS)
def test_literal(action, payload, repeat, delay, plain, wire, chunks):
    assert app.COMMANDS[action] == bytes.fromhex(payload)
    assert app.repeat_count(action) == repeat
    assert codec.custom_plain(app.COMMANDS[action], repeat, app.ANDROID.delay).hex() == plain
    frame = codec.encode(app.COMMANDS[action], repeat, delay)
    assert frame.hex() == wire
    assert tuple(chunk.hex() for chunk in codec.chunks(frame)) == chunks
    rx = codec.Receiver()
    decoded = [message for chunk in codec.chunks(frame) for message in rx.feed(chunk)]
    assert decoded == [bytes.fromhex(plain)]


def test_profile_covers_all_literals_and_form_ids():
    assert set(app.COMMANDS) == {row[0] for row in VECTORS}
    assert app.COMMANDS["massage_form_two"] == bytes.fromhex("8d0200")
    assert app.COMMANDS["massage_form_three"] == bytes.fromhex("8d0100")


def test_split_escape_crc_lengths_and_bounded_receiver():
    assert codec.slip(bytes.fromhex("c0db")) == bytes.fromhex("c0dbdcdbddc0")
    wire = codec.encode(app.COMMANDS["legs_up"], 10)
    # Feed one byte at a time, including both halves of the escaped ciphertext.
    rx = codec.Receiver()
    assert [message for byte in wire for message in rx.feed(bytes((byte,)))] == [
        codec.custom_plain(app.COMMANDS["legs_up"], 10)
    ]
    assert rx.feed(b"\xc0" + b"\x01" * 300 + b"\xc0") == ()
    damaged = bytearray(wire)
    damaged[10] ^= 1
    assert codec.Receiver().feed(damaged) == ()
    for body in (b"", bytes(20), b"\x0c\xff" + bytes(18)):
        assert codec.decode_body(body) is None
