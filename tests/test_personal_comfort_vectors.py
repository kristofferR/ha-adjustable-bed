"""Personal Comfort 2.6.1 independent encoding and parser examples."""

import pytest

from custom_components.adjustable_bed.codec import personal_comfort as codec
from custom_components.adjustable_bed.codec import richmat


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0x3F, "6e01003fae"),
        (0x40, "6e010040af"),
        (0x24, "6e01002493"),
        (0x25, "6e01002594"),
        (0x26, "6e01002695"),
        (0x27, "6e01002796"),
        (0x45, "6e010045b4"),
        (0x31, "6e010031a0"),
        (0x46, "6e010046b5"),
        (0x2E, "6e01002e9d"),
        (0x2B, "6e01002b9a"),
        (0x2F, "6e01002f9e"),
        (0x2C, "6e01002c9b"),
        (0x3C, "6e01003cab"),
        (0x4C, "6e01004cbb"),
        (0x4D, "6e01004dbc"),
        (0x48, "6e010048b7"),
        (0x4E, "6e01004ebd"),
        (0x4F, "6e01004fbe"),
        (0x47, "6e010047b6"),
    ],
)
def test_richmat_carrier_fit(code, expected):
    assert richmat.command(code, side=0).hex() == expected


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((0x83, 0, 0, 3), "5504830000000003dfaa"),
        ((0x69, 40, 40, 3), "550469282800000315aa"),
        ((1, 40, 40, 3), "5504012828000003adaa"),
        ((2, 20, 20, 3), "550402141400000386aa"),
        ((1, 0, 35, 2), "55040100230000027faa"),
        ((0x85,), "5504850000000000deaa"),
    ],
)
def test_anm3(args, expected):
    assert codec.anm3(*args).hex() == expected


@pytest.mark.parametrize(
    ("action", "side", "value", "expected"),
    [
        ("select", "left", 5, b"C>TPCH>0\n"),
        ("query", "left", 5, b"R>SP\n"),
        ("stop", "left", 5, b"C>STOPN\n"),
        ("set", "left", 30, b"C>SETP>0>36\n"),
        ("set", "right", 50, b"C>SETP>1>66\n"),
        ("set", "left", 0, b"C>SETP>0>0\n"),
        ("set", "right", 99, b"C>SETP>1>66\n"),
    ],
)
def test_anm5(action, side, value, expected):
    assert codec.anm5(action, side, value) == expected


@pytest.mark.parametrize(
    ("value", "expected"), [(5, "0a0f0f"), (25, "320f0f"), (50, "640f0f"), (130, "040f0f")]
)
def test_ra(value, expected):
    assert codec.ra(value).hex() == expected


@pytest.mark.parametrize(
    ("code", "data", "expected"),
    [
        (1, b"", "550154"),
        (3, b"", "550356"),
        (2, b"", "550257"),
        (4, b"", "550451"),
        (0x15, b"", "551540"),
        (5, b"", "550550"),
        (0x16, b"", "551643"),
        (0x31, b"", "553164"),
        (0x32, b"", "553267"),
        (0x35, b"", "553560"),
        (0xFF, b"", "55ffaa"),
        (0x41, b"\xcc", "5541ccd8"),
        (0x45, b"\xcc", "5545ccdc"),
    ],
)
def test_reverie_xor(code, data, expected):
    assert codec.xor(code, data).hex() == expected


def test_receive_examples():
    assert codec.parse_anm3(bytes.fromhex("550483002832000000aa")) == codec.AirReply(0x83, 50, 40)
    assert codec.parse_anm3(bytes.fromhex("000083000a1400000000")) == codec.AirReply(0x83, 20, 10)
    assert codec.parse_anm5(b"RET>SP>00004221420042") == codec.AirReply(0, 27, 50, 50, 5, 50, 0)
    assert codec.parse_anm5(b"RET>SP>00014200000000") == codec.AirReply(1, 5, 5, 50, 5, 5, 0)
    assert codec.parse_anm5(b"IGNORE>00004221420042") is None
    assert codec.ra_status(bytes.fromhex("0300")) == 768
    assert codec.ra_status(bytes.fromhex("8000")) == 32768
    assert codec.parse_anm3(b"\x55") is None
    assert codec.parse_anm5(b"RET>SP>00") is None


@pytest.mark.parametrize("firmware", ["71RU2265.00", "71RU2265.01", "71RU2265.02", "71RU2265.03"])
def test_exact_legacy_firmware(firmware):
    assert codec.ra_number(b"\x32", firmware) == 50


@pytest.mark.parametrize("firmware", ["71RU2265.04", "71RU2265.03\n", "unknown", ""])
def test_other_firmware(firmware):
    assert codec.ra_number(b"\x33", firmware) == 25


@pytest.mark.parametrize(
    ("action", "prefix", "expected"),
    [
        ("pillow_up", "db801020", "01"),
        ("pillow_down", "db801020", "02"),
        ("head_up", "db801021", "01"),
        ("head_down", "db801021", "02"),
        ("feet_up", "db801022", "01"),
        ("feet_down", "db801022", "02"),
        ("zero_g", "db8010d0", "01"),
        ("flat", "db8010d0", "03"),
        ("anti_snore", "db8010d0", "02"),
        ("memory_1", "db8010d0", "04"),
        ("save_1", "db8010d0", "84"),
        ("memory_2", "db8010d0", "05"),
        ("save_2", "db8010d0", "85"),
        ("massage_head", "db801061", "32"),
        ("massage_foot", "db801060", "32"),
        ("massage_off", "db801080", "00"),
        ("massage_mode", "db801080", "01"),
    ],
)
def test_reverie_v2_destinations(action, prefix, expected):
    characteristic, packet = codec.base6(action)
    assert characteristic == prefix + "-f324-29c3-38d1-85c0c2e86885"
    assert packet.hex() == expected
