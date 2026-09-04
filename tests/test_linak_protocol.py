"""Artifact-vector tests for the Linak Bed Control protocol helpers."""

from __future__ import annotations

import itertools

import pytest

from custom_components.adjustable_bed.beds.linak_protocol import (
    LINAK_ERROR_NAMES,
    LinakAlarmAction,
    LinakAlarmStep,
    LinakCapabilitySnapshot,
    LinakModelVariant,
    LinakProfile,
    build_automatic_drive,
    build_simultaneous_command,
    build_timer_event,
    build_timer_recurrence,
    decode_error,
    decode_reference,
    decode_timer,
)


def test_reference_vector_decodes_extension_flags_and_speed() -> None:
    """Freeze the modern app's exact four-byte reference vector."""
    state = decode_reference(bytes.fromhex("D2 04 A5 00"))

    assert state.extension == pytest.approx(12.34)
    assert state.raw_extension == 1234
    assert state.status_flags == 5
    assert state.raw_speed == 10
    assert state.speed == pytest.approx(0.9765625)
    assert state.speed_direction == "positive"
    assert state.sls is True
    assert state.end_position_up is False
    assert state.end_position_down is True
    assert state.position_lost is False


@pytest.mark.parametrize(
    ("payload", "raw_extension", "extension"),
    [("FE FF 00 00", 0xFFFE, -0.02), ("FF FF 00 00", 0xFFFF, -0.01)],
)
def test_reference_extension_is_signed(
    payload: str,
    raw_extension: int,
    extension: float,
) -> None:
    """Keep the raw word while publishing sub-zero extension counts as signed."""
    state = decode_reference(bytes.fromhex(payload))

    assert state.raw_extension == raw_extension
    assert state.extension == pytest.approx(extension)


def test_reference_speed_is_sign_extended_but_reported_as_magnitude() -> None:
    """The high twelve bits are signed; the app publishes their magnitude."""
    word = 1234 | (0x0A << 16) | (0xFF6 << 20)
    state = decode_reference(word.to_bytes(4, "little"))

    assert state.raw_speed == -10
    assert state.speed == pytest.approx(0.9765625)
    assert state.speed_direction == "negative"
    assert state.end_position_up is True
    assert state.position_lost is True


@pytest.mark.parametrize("length", [0, 1, 2, 3, 5])
def test_reference_parser_rejects_every_non_four_byte_payload(length: int) -> None:
    with pytest.raises(ValueError, match="exactly 4 bytes"):
        decode_reference(bytes(length))


def test_all_104_error_codes_follow_the_one_based_enum() -> None:
    """Every frozen diagnostic enum member is reachable through its exact index."""
    assert len(LINAK_ERROR_NAMES) == 104
    for code, expected_name in enumerate(LINAK_ERROR_NAMES, start=1):
        state = decode_error(bytes((1, 0, code, 0xAA)))
        assert state is not None
        assert state.code == code
        assert state.name == expected_name
        assert state.payload == bytes((code, 0xAA))

    assert decode_error(bytes((1, 0, 0))) is None
    assert decode_error(b"") is None
    with pytest.raises(ValueError, match="Unsupported Linak error type"):
        decode_error(bytes((2, 0, 1)))
    with pytest.raises(ValueError, match="Unknown Linak error code"):
        decode_error(bytes((1, 0, 105)))


def test_timer_builders_match_frozen_vectors() -> None:
    assert build_timer_event(
        3600,
        (LinakAlarmStep(LinakAlarmAction.MEMORY_1),),
    ) == bytes.fromhex("00 10 0E 01 0E 00 01 00")
    assert build_timer_event(
        70000,
        (LinakAlarmStep(LinakAlarmAction.MASSAGE_TOGGLE),),
    ) == bytes.fromhex("01 70 11 01 91 00 01 00")
    assert build_timer_event(
        3600,
        (
            LinakAlarmStep(LinakAlarmAction.MEMORY_1),
            LinakAlarmStep(LinakAlarmAction.LIGHT_TOGGLE, lifetime=2, pause=3),
        ),
    ) == bytes.fromhex("00 10 0E 01 0E 00 01 00 94 00 02 03")
    assert build_timer_recurrence(31, 1440) == bytes.fromhex("10 A0 FD")


def test_timer_parser_covers_info_lifecycle_and_errors() -> None:
    info = decode_timer(bytes.fromhex("20 10 0E 01 0E 00 01 00"))
    assert info.status == "scheduled"
    assert info.enabled is True
    assert info.seconds == 3600
    assert info.first_action == LinakAlarmStep(LinakAlarmAction.MEMORY_1)

    high = decode_timer(bytes.fromhex("21 70 11 01 91 00 02 03"))
    assert high.seconds == 70000
    assert high.first_action == LinakAlarmStep(
        LinakAlarmAction.MASSAGE_TOGGLE,
        lifetime=2,
        pause=3,
    )

    for prefix, status in ((0x80, "elapsed"), (0x90, "interrupted"), (0xA0, "action_done")):
        for offset in range(4):
            state = decode_timer(bytes((prefix + offset,)))
            assert state.status == status
            assert state.timer_index == offset + 1

    for code, name in {
        1: "unsupported_action",
        2: "illegal_length",
        3: "illegal_event_action",
        4: "illegal_recurrence",
    }.items():
        state = decode_timer(bytes((0xFF, code)))
        assert state.status == f"error_{name}"
        assert state.error_code == code


def test_configuration_and_all_40_two_section_commands() -> None:
    assert build_automatic_drive(True) == bytes.fromhex("89 3B 80 00 01")
    assert build_automatic_drive(False) == bytes.fromhex("89 3B 80 00 00")
    assert build_simultaneous_command("back", True, "legs", False) == bytes.fromhex("35 00")

    axes = ("base", "feet", "head", "legs", "back")
    packets = {
        build_simultaneous_command(first, first_up, second, second_up)
        for first, second in itertools.combinations(axes, 2)
        for first_up in (False, True)
        for second_up in (False, True)
    }
    assert len(packets) == 40
    assert packets == {bytes((opcode, 0)) for opcode in range(0x10, 0x38)}


@pytest.mark.parametrize(
    ("variant", "mask", "axes", "memory_slots"),
    [
        (LinakModelVariant.STANDARD, None, (), 0),
        (LinakModelVariant.TD3, 0, (), 4),
        (LinakModelVariant.ADVANCED, 0xC0, ("back", "legs"), 4),
        (
            LinakModelVariant.ADVANCED_WITH_ALARM,
            0xF8,
            ("back", "legs", "head", "feet", "base"),
            4,
        ),
    ],
)
def test_model_snapshot_gates_exact_axes_and_memories(
    variant: LinakModelVariant,
    mask: int | None,
    axes: tuple[str, ...],
    memory_slots: int,
) -> None:
    snapshot = LinakCapabilitySnapshot(
        model_variant=variant,
        actuator_mask=mask,
        timer_supported=variant is LinakModelVariant.ADVANCED_WITH_ALARM,
        discovery_complete=True,
    )

    assert snapshot.position_axes == axes
    assert snapshot.memory_slots == memory_slots
    assert (
        LinakCapabilitySnapshot.from_mapping(
            snapshot.as_dict(),
            profile=LinakProfile.BED_CONTROL,
        )
        == snapshot
    )


def test_performance_snapshot_has_four_memories_without_position_claims() -> None:
    snapshot = LinakCapabilitySnapshot(
        profile=LinakProfile.PERFORMANCE,
        discovery_complete=True,
    )

    assert snapshot.memory_slots == 4
    assert snapshot.position_axes == ()
