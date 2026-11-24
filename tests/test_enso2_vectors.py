"""Independent frame literals from ENSO Sleep Control 1.0.7."""

import pytest

from custom_components.adjustable_bed.codec import richmat


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        (richmat.command(0x24), "6e01002493"),
        (richmat.encode("nordic", 0x34), "34"),
        (richmat.command(0x24, 1), "6e01012494"),
        (richmat.command(0x6E, 2), "6e01026edf"),
        (richmat.encode("nordic", 0x6E), "6e"),
        (b"".join(richmat.countdown(1440, 0x45)), "6e05a000136e060545be"),
        (richmat.rgb(0x12, 0x34, 0x56), "6e0cff128b6e0d345605"),
        (richmat.light_timer(1, 44), "6e0b012ca6"),
        (richmat.frame(0x6E, 0x1B, 0, 60), "6e1b003cc5"),
        (richmat.frame(0x6E, 0x1C, 0, 1), "6e1c00018b"),
        (richmat.frame(0x6E, 0x1D, 0, 12), "6e1d000c97"),
        (richmat.frame(0x6E, 2, 1, 0), "6e02010071"),
        (richmat.frame(0x6E, 8, 1, 1), "6e08010178"),
        (richmat.frame(0x6E, 0xA, 0, 1), "6e0a000179"),
        (richmat.frame(0x6E, 0x1A, 0, 0), "6e1a000088"),
    ],
)
def test_existing_richmat_codec(actual: bytes, expected: str) -> None:
    assert actual == bytes.fromhex(expected)
