"""MoodBase carrier fit against literal frames and status bodies."""

import pytest

from custom_components.adjustable_bed.beds.bedgear.protocol import color_parameters, token_fields
from custom_components.adjustable_bed.codec import motomotion
from custom_components.adjustable_bed.profiles.moodbase import lighting_frame


@pytest.mark.parametrize(
    "letter,raw,wrapped",
    [
        ("K", b"$K", b"$#$KR\r"),
        ("L", b"$L", b"$#$LR\r"),
        ("M", b"$M", b"$#$MR\r"),
        ("N", b"$N", b"$#$NR\r"),
        ("p", b"$p", b"$#$pR\r"),
        ("q", b"$q", b"$#$qR\r"),
        ("P", b"$P", b"$#$PR\r"),
        ("Q", b"$Q", b"$#$QR\r"),
        ("O", b"$O", b"$#$OR\r"),
        ("R", b"$R", b"$#$RR\r"),
        ("S", b"$S", b"$#$SR\r"),
        ("T", b"$T", b"$#$TR\r"),
        ("A", b"$A", b"$#$AR\r"),
        ("C", b"$C", b"$#$CR\r"),
        ("B", b"$B", b"$#$BR\r"),
        ("D", b"$D", b"$#$DR\r"),
        ("E", b"$E", b"$#$ER\r"),
        ("F", b"$F", b"$#$FR\r"),
        ("I", b"$I", b"$#$IR\r"),
        ("G", b"$G", b"$#$GR\r"),
        ("H", b"$H", b"$#$HR\r"),
        ("J", b"$J", b"$#$JR\r"),
        ("U", b"$U", b"$#$UR\r"),
        ("V", b"$V", b"$#$VR\r"),
        ("Z", b"$Z", b"$#$ZR\r"),
        ("a", b"$a", b"$#$aR\r"),
        ("W", b"$W", b"$#$WR\r"),
        ("b", b"$b", b"$#$bR\r"),
        ("z", b"$z", None),
    ],
)
def test_letter_carrier(letter, raw, wrapped):
    assert motomotion.short_transport("$" + letter, wrapped=False) == raw
    assert motomotion.short_transport("$" + letter, wrapped=True) == wrapped


@pytest.mark.parametrize(
    "first,second,expected",
    [
        ("00015", "00000", b"$#000150000000004R\r"),
        ("00012", "00000", b"$#000120000000003R\r"),
        ("33049", "00001", b"$#330490000100012R\r"),
        ("073000", "0017", b"$#073000001700002R\r"),
        ("064500", "0219", b"$#064500021900013R\r"),
    ],
)
def test_decimal_fields(first, second, expected):
    assert motomotion.decimal_fields(first, second) == expected
    assert motomotion.short_transport(expected.decode("ascii"), wrapped=True) == expected


@pytest.mark.parametrize(
    "channel,value,brightness,expected",
    [
        (0, 255, 1, b"$#001200031500004R\r"),
        (0, 21, 1, b"$#000000031500007R\r"),
        (0, 22, 1, b"$#000100031500006R\r"),
        (1, 63, 1, b"$#000000031600004R\r"),
        (1, 64, 1, b"$#000300031600007R\r"),
        (2, 128, 0.5, b"$#000300031700006R\r"),
        (2, 255, 1, b"$#001200031700006R\r"),
    ],
)
def test_rgb_thresholds_and_field_order(channel, value, brightness, expected):
    scaled = color_parameters((value, value, value), brightness)[channel]
    assert lighting_frame((315, 316, 317)[channel], scaled) == expected


@pytest.mark.parametrize(
    "minutes,expected",
    [
        (90, b"$#000900031900002R\r"),
        (10, b"$#000100031900010R\r"),
        (0, b"$#000000031900011R\r"),
    ],
)
def test_rgb_timer(minutes, expected):
    assert lighting_frame(319, minutes) == expected


def test_vibration_uses_only_its_own_channel():
    vibration = motomotion.music_command("V", 22)
    assert vibration == b"$#V22\r"
    assert motomotion.short_transport(vibration.decode("ascii"), wrapped=True) == b"$#V22\rR\r"


@pytest.mark.parametrize("count", (39, 44, 71, 75))
def test_status_vectors(count):
    tokens = ["0"] * count
    color_indices = (28, 29, 30, 54) if count == 75 else (18, 19, 20, 30)
    for index, token in zip(color_indices, ("120", "45", "60", "90"), strict=True):
        tokens[index] = token
    if count == 75:
        tokens[8], tokens[9], tokens[11] = "07", "30", "2"
    if count == 39:
        tokens[24], tokens[27] = "1", "00065"
    fields = token_fields(" ".join(tokens), alarm_indices=(8, 9, 11))
    assert fields["rgb_timer"] == ["120", "45", "60", "90"]
    assert fields.get("alarm") == (["07", "30", "2"] if count == 75 else None)
    if count == 39:
        assert fields["bind"] == {"available": True, "active": True}
        assert fields["sync_type"] == 1
        assert fields["event"] == "OK"
