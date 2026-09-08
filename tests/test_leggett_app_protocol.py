"""Cluster-005 timer vectors and the additional U-Series BLE parser boundaries."""

import pytest

from custom_components.adjustable_bed.beds.leggett_okin import (
    _build_revision_0_command,
    parse_leggett_okin_feedback,
)
from custom_components.adjustable_bed.beds.okin_protocol import build_okin_command
from custom_components.adjustable_bed.leggett_app_protocol import (
    LEGGETT_APP_PROFILES,
    SLEEP_CANCEL_KEY,
    build_alarm,
    build_sleep_timer,
)


@pytest.mark.parametrize("profile", ["prodigy2l", "prodigy2", "prodigy4"])
@pytest.mark.parametrize(
    ("action", "expected"),
    [(1, "0402ff00005a"), (2, "0402ff01005a"), (3, "0402ff02005a"), (4, "0402ff03005a")],
)
def test_prodigy_sleep_bypasses_revision_zero_framing(profile, action, expected):
    # The packet remains six bytes even when ordinary keys use E5 FE 16.
    assert build_sleep_timer(profile, 90, action) == bytes.fromhex(expected)


@pytest.mark.parametrize(
    ("action", "minutes", "expected_key", "r0", "r1"),
    [
        (0, 15, 0xFF10000F, "e5fe16ff10000fe8", "0402ff10000f"),
        (1, 30, 0xFF00001E, "e5fe16ff00001ee9", "0402ff00001e"),
        (2, 45, 0xFF01002D, "e5fe16ff01002dd9", "0402ff01002d"),
        (3, 90, 0xFF02005A, "e5fe16ff02005aab", "0402ff02005a"),
    ],
)
def test_useries_sleep_uses_the_existing_key_revision_builder(
    action, minutes, expected_key, r0, r1
):
    key = build_sleep_timer("useries", minutes, action)
    assert key == expected_key
    assert isinstance(key, int)
    assert _build_revision_0_command(key).hex() == r0
    assert build_okin_command(key).hex() == r1


@pytest.mark.parametrize("profile", list(LEGGETT_APP_PROFILES))
def test_alarm_duration_and_profile_specific_stop(profile):
    key = build_alarm(profile, 90)
    assert key == 0xFD00005A
    assert _build_revision_0_command(key).hex() == "e5fe16fd00005aaf"
    assert build_okin_command(key).hex() == "0402fd00005a"
    assert build_alarm(profile, 1440) == 0xFD0005A0
    if profile == "useries":
        assert build_alarm(profile, None) == 0xFD000000
        assert _build_revision_0_command(build_alarm(profile, None)).hex() == "e5fe16fd00000009"
    else:
        assert build_alarm(profile, None) == 0xFD200000
        assert _build_revision_0_command(build_alarm(profile, None)).hex() == "e5fe16fd200000e9"
    assert _build_revision_0_command(SLEEP_CANCEL_KEY).hex() == "e5fe16ff200000e7"


@pytest.mark.parametrize("profile", ["prodigy2l", "prodigy2", "prodigy4"])
def test_sleep_picker_bounds_shared_by_all_prodigy_apps(profile):
    assert build_sleep_timer(profile, 1, 1) == bytes.fromhex("0402ff000001")
    assert build_sleep_timer(profile, 1439, 4) == bytes.fromhex("0402ff03059f")
    # 1440 is a defensive zero-normalization path; the app picker excludes zero.
    for minutes in (0, 1440, -1, True, 1.5):
        with pytest.raises(ValueError, match="sleep minutes"):
            build_sleep_timer(profile, minutes, 1)
    for action in (0, 5, True, 1.5):
        with pytest.raises(ValueError, match="favorite slot"):
            build_sleep_timer(profile, 30, action)


def test_useries_accepts_only_its_actual_picker_actions_and_delays():
    for minutes in (15, 30, 45, 60, 75, 90):
        assert build_sleep_timer("useries", minutes, 0) == 0xFF100000 | minutes
    for minutes in (0, 1, 16, 91, True, 15.5):
        with pytest.raises(ValueError):
            build_sleep_timer("useries", minutes, 0)
    for action in (-1, 4, True, 1.5):
        with pytest.raises(ValueError, match="sleep action"):
            build_sleep_timer("useries", 30, action)
    for minutes in (0, -1, 1441, True, 90.5):
        with pytest.raises(ValueError, match="alarm minutes"):
            build_alarm("useries", minutes)


def test_unknown_profile_cannot_default_to_another_packet_family():
    with pytest.raises(ValueError, match="Unknown"):
        build_sleep_timer("other", 30, 1)
    with pytest.raises(ValueError, match="Unknown"):
        build_alarm("other", None)


def test_profile_actuators_and_memory_do_not_inherit_dead_keys():
    two_l = LEGGETT_APP_PROFILES["prodigy2l"]
    assert (two_l.pillow, two_l.lumbar) == (False, True)
    two = LEGGETT_APP_PROFILES["prodigy2"]
    assert (two.pillow, two.lumbar) == (True, False)
    four = LEGGETT_APP_PROFILES["prodigy4"]
    assert (four.pillow, four.lumbar) == (True, True)
    u = LEGGETT_APP_PROFILES["useries"]
    assert (u.pillow, u.lumbar, u.memory_slots, u.settings) == (True, False, 2, False)
    assert all(
        LEGGETT_APP_PROFILES[name].memory_slots == 4
        for name in ("prodigy2l", "prodigy2", "prodigy4")
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("0600060000017f0002", (0x077F0003, 127)),
        ("060007ffffff80000f", (0x007FFFF0, -128)),
        ("05000b99f30f73ff", (0x0000710F, -1)),
        ("0f00060102030405060708090a0b0c0d0e0f", (0x0E0D0E0F, 4)),
    ],
)
def test_existing_ble_parser_covers_useries_long_wrap_and_odd_partition(payload, expected):
    assert parse_leggett_okin_feedback(bytes.fromhex(payload)) == expected
