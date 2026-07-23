"""Tests for MotoSleep, Power Bob, and binary MOTO model routing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.adjustable_bed.beds.motosleep import (
    MotoSleepController,
    build_moto_binary_frame,
    build_motosleep_numeric_frame,
    build_motosleep_sync_frame,
    build_power_bob_numeric_frame,
)
from custom_components.adjustable_bed.beds.motosleep_profiles import (
    MotoSleepTransport,
    resolve_motosleep_profile,
)
from custom_components.adjustable_bed.const import BED_TYPE_MOTOSLEEP, MOTOSLEEP_CHAR_UUID
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.cover import _build_cover_description


def _moto_name(page: str, *, feature: str = "Q", led: str = "D") -> str:
    """Build an exact-length name accepted by MotoPageModel."""
    return f"MOTOB00{page}4{led}{feature}NX" + "0" * 15


@pytest.mark.parametrize(
    ("name", "profile_id"),
    [
        ("HHC0000015CDEF", "power_bob_a15"),
        ("HHC0000035CDEF", "power_bob_d345"),
        ("HHC0000040CDEF", "power_bob_four"),
        ("HHC0000095CDEF", "power_bob_wr1140"),
        ("HHC0000000CDEF", "power_bob_zero"),
        ("HHC0000010CDEF", "power_bob_one"),
        ("HHC0000020CDEF", "power_bob_two"),
        ("HHC0000030CDEF", "power_bob_three"),
        ("HHC0000050CDEF", "power_bob_five"),
        ("HHC0000060CDEF", "power_bob_six"),
        ("HHC0000070CDEF", "power_bob_seven"),
        ("HHC0000080CDEF", "power_bob_eight"),
        ("HHC0000090CDEF", "power_bob_nine"),
        ("HHC00000D0CDEF", "power_bob_six_zg"),
    ],
)
def test_power_bob_selector_matrix(name: str, profile_id: str) -> None:
    """Every root selector from Power Bob 2.0.3 resolves independently."""
    assert len(name) == 14
    assert resolve_motosleep_profile(name).profile_id == profile_id
    assert resolve_motosleep_profile(name.lower()).profile_id == profile_id


def test_issue_445_name_routes_pq_to_lumbar() -> None:
    """The reported A15 name uses P/Q, not p/q, for manual lumbar."""
    profile = resolve_motosleep_profile("HHC0069815CDEF")

    assert profile.profile_id == "power_bob_a15"
    assert profile.transport is MotoSleepTransport.POWER_BOB_ASCII
    assert profile.motors["lumbar"] == ("P", "Q")
    assert "auxiliary" not in profile.motors


async def test_issue_468_short_panel_eight_keeps_home_preset() -> None:
    """The reported short HHC PanelEight bed retains its working Home action."""
    controller, client = _controller("HHC0120182CDEH")

    assert controller.profile.profile_id == "power_bob_eight"
    assert controller.supports_preset_flat is True

    await controller.preset_flat()

    client.write_gatt_char.assert_awaited_once_with(
        MOTOSLEEP_CHAR_UUID, b"$O", response=False
    )


def test_power_bob_accepts_exact_length_name_containing_hhc() -> None:
    """Power Bob filters for a case-sensitive HHC substring, not a prefix."""
    profile = resolve_motosleep_profile("XXHHC000150000")

    assert len("XXHHC000150000") == 14
    assert profile.profile_id == "power_bob_a15"


def test_power_bob_unmatched_selector_exposes_no_guessed_panel() -> None:
    """The APK has no default root route for unmatched 14-character selectors."""
    profile = resolve_motosleep_profile("XXHHC000X00000")

    assert len("XXHHC000X00000") == 14
    assert profile.profile_id == "power_bob_unknown"
    assert not profile.motors
    assert profile.stop is None


def test_power_bob_capabilities_are_not_universal() -> None:
    """A two-button PanelFive must not inherit lumbar, memory, or lights."""
    profile = resolve_motosleep_profile("HHC0000050CDEF")

    assert profile.motors == {"back": ("K", "L")}
    assert not profile.presets
    assert not profile.memory_recall
    assert profile.light_toggle is None
    assert profile.stop is None


@pytest.mark.parametrize("name", ["HHC0000010CDEF", "HHC0000050CDEF"])
def test_power_bob_minimal_panels_keep_orthogonal_rgb_settings(name: str) -> None:
    """Mood/Night PanelRGB routing is independent of the root motor panel."""
    profile = resolve_motosleep_profile(name)
    controller, _client = _controller(name)

    assert profile.profile_id in {"power_bob_one", "power_bob_five"}
    assert profile.rgb_light is True
    assert profile.light_toggle is None
    assert controller.supports_light_color_control is True
    assert controller.supports_light_toggle_control is False


def test_neutral_axis_builds_a_generic_cover_description() -> None:
    """An APK-proven axis with tentative semantics must still create an entity."""
    controller, _client = _controller("HHC0000040CDEF")
    auxiliary = next(spec for spec in controller.motor_control_specs if spec.key == "auxiliary_1")
    coordinator = MagicMock()
    coordinator.bed_type = "motosleep"

    description = _build_cover_description(coordinator, auxiliary)

    assert description.key == "auxiliary_1"
    assert description.translation_key == "auxiliary_1"
    assert description.icon == "mdi:bed-outline"


def _hhc_name(c16: str, c18: str = "0", c22: str = "0", c26: str = "0") -> str:
    chars = list("HHC" + "0" * 24)
    chars[16] = c16
    chars[18] = c18
    chars[22] = c22
    chars[26] = c26
    return "".join(chars)


@pytest.mark.parametrize(
    ("name", "profile_id"),
    [
        (_hhc_name("F"), "motosleep_hhc_f"),
        (_hhc_name("G"), "motosleep_hhc_g"),
        (_hhc_name("H"), "motosleep_hhc_h"),
        (_hhc_name("1", "5"), "motosleep_hhc_a"),
        (_hhc_name("4", "6"), "motosleep_hhc_one"),
        (_hhc_name("3", "5"), "motosleep_hhc_d"),
        (_hhc_name("4", "0"), "motosleep_hhc_four"),
        (_hhc_name("9", "5"), "motosleep_hhc_wr1140"),
        (_hhc_name("0"), "motosleep_hhc_zero"),
        (_hhc_name("2"), "motosleep_hhc_two"),
        (_hhc_name("3"), "motosleep_hhc_three"),
        (_hhc_name("5", c26="I"), "motosleep_hhc_five_new"),
        (_hhc_name("5"), "motosleep_hhc_five"),
        (_hhc_name("6", c26="I"), "motosleep_hhc_six_new"),
        (_hhc_name("6"), "motosleep_hhc_six"),
        (_hhc_name("7"), "motosleep_hhc_seven"),
        (_hhc_name("8", c26="I"), "motosleep_hhc_eight_new"),
        (_hhc_name("8"), "motosleep_hhc_eight"),
        (_hhc_name("9"), "motosleep_hhc_nine"),
        (_hhc_name("D"), "motosleep_hhc_six_zg"),
        (_hhc_name("E"), "motosleep_hhc_e"),
    ],
)
def test_motosleep_hhc_selector_matrix(name: str, profile_id: str) -> None:
    """Every MotoSleep HHC page selector resolves to its own profile."""
    assert resolve_motosleep_profile(name).profile_id == profile_id
    assert resolve_motosleep_profile(name.lower()).profile_id == profile_id


def test_hhc_raw_and_wrapped_transport_selection() -> None:
    """Name index 22 selects the APK's raw HHC write path."""
    raw = resolve_motosleep_profile(_hhc_name("G"))
    wrapped = resolve_motosleep_profile(_hhc_name("G", c22="M"))

    assert raw.raw_hhc is True
    assert wrapped.raw_hhc is False


def test_panel_e_preserves_unlabelled_w_action() -> None:
    """PanelE's proven $W callsite remains available under a neutral label."""
    profile = resolve_motosleep_profile(_hhc_name("E"))

    assert profile.auxiliary_action == "W"


def test_current_hhc_accepts_long_name_containing_hhc() -> None:
    """MotoSleep's scan filter also accepts HHC away from index zero."""
    chars = list(_hhc_name("G"))
    chars[:6] = "XXXHHC"

    assert resolve_motosleep_profile("".join(chars)).profile_id == "motosleep_hhc_g"


@pytest.mark.parametrize(
    ("name", "expected_motors"),
    [
        (
            _hhc_name("1", "5", c26="H"),
            {"back": ("K", "L"), "legs": ("M", "N"), "lumbar": ("p", "q")},
        ),
        (_hhc_name("1", "5"), {"back": ("K", "L"), "legs": ("M", "N"), "tilt": ("P", "Q")}),
        (
            _hhc_name("3", "5", c26="H"),
            {"back": ("K", "L"), "legs": ("M", "N"), "neck": ("p", "q")},
        ),
        (_hhc_name("3", "6"), {"back": ("K", "L"), "legs": ("M", "N"), "tilt": ("P", "Q")}),
        (
            _hhc_name("4", "5", c26="H"),
            {"back": ("K", "L"), "legs": ("M", "N"), "lumbar": ("p", "q")},
        ),
        (_hhc_name("8", "5"), {"back": ("K", "L"), "legs": ("M", "N"), "tilt": ("P", "Q")}),
        (_hhc_name("C"), {"back": ("K", "L"), "legs": ("M", "N"), "auxiliary": ("P", "Q")}),
    ],
)
def test_hhc_conditional_axis_labels(
    name: str, expected_motors: dict[str, tuple[str, str]]
) -> None:
    """Only axes with an APK-proven physical label receive that label."""
    assert resolve_motosleep_profile(name).motors == expected_motors


@pytest.mark.parametrize(
    ("page", "profile_id"),
    [
        ("0", "motosleep_moto_wrs23ms"),
        ("1", "motosleep_moto_wrs14dmm"),
        ("2", "motosleep_moto_wrs18ms"),
        ("3", "motosleep_moto_wrs14ms"),
        ("4", "motosleep_moto_wrs20ms"),
        ("5", "motosleep_moto_wrs16ms"),
        ("6", "motosleep_moto_wrc30mms"),
        ("7", "motosleep_moto_wrs27ms"),
        ("8", "motosleep_moto_wrs20ms_swing"),
        ("9", "motosleep_moto_wr219"),
    ],
)
def test_binary_moto_selector_matrix(page: str, profile_id: str) -> None:
    """All ten binary bed pages resolve from local-name index 7."""
    name = _moto_name(page)

    assert len(name) == 28
    assert resolve_motosleep_profile(name).profile_id == profile_id


@pytest.mark.parametrize(
    ("page", "expected_motors"),
    [
        (
            "0",
            {
                "back": (0x0002, 0x0001),
                "legs": (0x0200, 0x0100),
                "head": (0x0020, 0x0010),
                "lumbar": (0x0080, 0x0040),
                "feet": (0x0008, 0x0004),
            },
        ),
        ("1", {"back": (0x0020, 0x0010), "legs": (0x0200, 0x0100), "head": (0x0002, 0x0001)}),
        (
            "2",
            {
                "back": (0x0002, 0x0001),
                "legs": (0x0200, 0x0100),
                "lumbar": (0x0080, 0x0040),
                "feet": (0x0008, 0x0004),
            },
        ),
        ("3", {"back": (0x0002, 0x0001), "legs": (0x0200, 0x0100), "feet": (0x0008, 0x0004)}),
        (
            "4",
            {
                "back": (0x0002, 0x0001),
                "legs": (0x0200, 0x0100),
                "head": (0x0020, 0x0010),
                "lumbar": (0x0080, 0x0040),
                "feet": (0x0008, 0x0004),
            },
        ),
        ("5", {"back": (0x0002, 0x0001), "legs": (0x0200, 0x0100), "feet": (0x0008, 0x0004)}),
        (
            "6",
            {
                "neck": (0x0020, 0x0010),
                "back": (0x0002, 0x0001),
                "lumbar": (0x0080, 0x0040),
                "legs": (0x0008, 0x0004),
            },
        ),
        ("7", {"back": (0x0002, 0x0001), "legs": (0x0008, 0x0004), "lumbar": (0x0080, 0x0040)}),
        (
            "8",
            {
                "back": (0x0002, 0x0001),
                "legs": (0x0200, 0x0100),
                "head": (0x0020, 0x0010),
                "lumbar": (0x0080, 0x0040),
                "feet": (0x0008, 0x0004),
            },
        ),
        ("9", {"back": (0x000A, 0x0005), "lumbar": (0x0200, 0x0100), "legs": (0x00A0, 0x0050)}),
    ],
)
def test_binary_moto_motor_matrix(page: str, expected_motors: dict[str, tuple[int, int]]) -> None:
    """Every binary page exposes only its app-rendered actuator matrix."""
    assert resolve_motosleep_profile(_moto_name(page)).motors == expected_motors


def test_binary_moto_unknown_name_is_conservative() -> None:
    """MOTO-like audio/amplifier names do not inherit bed controls."""
    profile = resolve_motosleep_profile("MOTOAMP")

    assert profile.profile_id == "motosleep_moto_unknown"
    assert not profile.motors
    assert profile.stop is None


def test_binary_moto_unknown_page_is_conservative() -> None:
    """A regex-shaped name with an unknown page cannot crash profile routing."""
    profile = resolve_motosleep_profile(_moto_name("X"))

    assert profile.profile_id == "motosleep_moto_unknown"
    assert profile.transport is MotoSleepTransport.MOTO_BINARY
    assert not profile.motors
    assert profile.stop is None


def test_lowercase_moto_name_routes_to_the_exact_binary_profile() -> None:
    """Case-insensitive detection and profile routing select the same model."""
    profile = resolve_motosleep_profile(_moto_name("4").lower())

    assert profile.profile_id == "motosleep_moto_wrs20ms"
    assert profile.transport is MotoSleepTransport.MOTO_BINARY
    assert profile.motors["lumbar"] == (0x0080, 0x0040)
    assert profile.stop == ((0x0000, 0), 5, 100)


@pytest.mark.parametrize(
    ("command", "data", "expected"),
    [
        (0x0000, 0, "24230000000000410d"),
        (0x0002, 0, "24230002000002410d"),
        (0x8009, 0, "24238009000089410d"),
        (0x9088, 1, "24239088000119410d"),
    ],
)
def test_binary_frame_matches_clean_room_vectors(command: int, data: int, expected: str) -> None:
    """Binary framing and XOR match the frozen MotoSleep APK vectors."""
    assert build_moto_binary_frame(command, data).hex() == expected


def test_numeric_frame_order_differs_between_apps() -> None:
    """Power Bob and MotoSleep place selector/value fields in opposite order."""
    assert build_power_bob_numeric_frame("00319", "00128") == b"$#003190012800000R\r"
    assert build_motosleep_numeric_frame("00128", "00319") == b"$#001280031900000R\r"
    assert build_motosleep_sync_frame("00015") == b"$#000150000000004R\r"


def _controller(name: str) -> tuple[MotoSleepController, MagicMock]:
    client = MagicMock()
    client.is_connected = True
    client.services = []
    client.write_gatt_char = AsyncMock()
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.client = client
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 1
    coordinator.record_command_trace = MagicMock()
    return MotoSleepController(coordinator, device_name=name), client


async def test_issue_445_manual_lumbar_writes_raw_p_uppercase() -> None:
    """A15 manual lumbar uses the Power Bob no-response P command."""
    controller, client = _controller("HHC0069815CDEF")

    with patch("custom_components.adjustable_bed.beds.motosleep.asyncio.sleep") as sleep:
        await controller.move_lumbar_up()

    sleep.assert_awaited_once_with(0.1)
    client.write_gatt_char.assert_awaited_once_with(MOTOSLEEP_CHAR_UUID, b"$P", response=False)


async def test_factory_passes_device_name_into_profile_routing() -> None:
    """Controller creation retains the advertised name used by both APK routers."""
    coordinator = MagicMock()
    controller = await create_controller(
        coordinator,
        BED_TYPE_MOTOSLEEP,
        protocol_variant=None,
        client=None,
        device_name="HHC0069815CDEF",
    )

    assert isinstance(controller, MotoSleepController)
    assert controller.profile.profile_id == "power_bob_a15"


async def test_current_hhc_wraps_short_actions_and_stops_five_times() -> None:
    """MotoSleep HHC writes wrapped actions and the recovered release schedule."""
    controller, client = _controller(_hhc_name("G", c22="M"))

    await controller.move_lumbar_up()

    calls = client.write_gatt_char.await_args_list
    assert calls[0].args[1] == b"$#$pR\r"
    assert [call.args[1] for call in calls[1:]] == [b"$#$bR\r"] * 5
    assert all(call.kwargs["response"] is True for call in calls)


async def test_panel_e_auxiliary_action_writes_exact_frame() -> None:
    """The neutral PanelE action follows its model's exact raw transport."""
    controller, client = _controller(_hhc_name("E"))

    await controller.auxiliary_action()

    client.write_gatt_char.assert_awaited_once_with(MOTOSLEEP_CHAR_UUID, b"$W", response=True)


def test_control_characteristic_prefers_ffe1_and_falls_back_to_fff1() -> None:
    """The controller follows both APKs' discovered write-role precedence."""
    controller, client = _controller(_hhc_name("G"))
    fff1 = MagicMock(uuid="0000fff1-0000-1000-8000-00805f9b34fb")
    client.services = [MagicMock(characteristics=[fff1])]
    assert controller.control_characteristic_uuid == fff1.uuid

    ffe1 = MagicMock(uuid="0000ffe1-0000-1000-8000-00805f9b34fb")
    client.services = [MagicMock(characteristics=[fff1, ffe1])]
    assert controller.control_characteristic_uuid == ffe1.uuid


async def test_power_bob_presets_and_memory_are_single_raw_no_response_writes() -> None:
    """Power Bob action buttons use their exact raw one-shot transport."""
    controller, client = _controller("HHC0069815CDEF")

    await controller.preset_flat()
    await controller.preset_memory(2)
    await controller.program_memory(1)

    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        b"$O",
        b"$V",
        b"$Z",
    ]
    assert all(call.kwargs["response"] is False for call in client.write_gatt_char.await_args_list)


async def test_hhc_massage_uses_only_profile_proven_controls() -> None:
    """HHC massage capabilities and bytes come from the selected panel."""
    controller, client = _controller(_hhc_name("F", c22="M"))

    assert controller.auto_enable_massage is True
    assert controller.supports_head_massage_toggle_control is True
    assert controller.supports_head_massage_intensity_step_control is False
    await controller.massage_head_toggle()
    await controller.massage_off()

    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        b"$#$CR\r",
        b"$#$DR\r",
    ]


async def test_hhc_zero_profile_uses_separate_massage_intensity_actions() -> None:
    """PanelZero retains its extended head and foot massage command family."""
    controller, client = _controller(_hhc_name("0"))

    assert controller.supports_head_massage_intensity_step_control is True
    assert controller.supports_foot_massage_intensity_step_control is True
    await controller.massage_head_up()
    await controller.massage_foot_down()

    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        b"$G",
        b"$F",
    ]


async def test_hhc_zero_profile_routes_zone_on_off_actions_as_toggles() -> None:
    """PanelZero J/I actions retain their APK-proven on-off semantics."""
    controller, client = _controller(_hhc_name("0"))

    assert controller.profile.massage["head_toggle"] == "J"
    assert controller.profile.massage["foot_toggle"] == "I"
    assert controller.supports_head_massage_toggle_control is True
    assert controller.supports_foot_massage_toggle_control is True
    await controller.massage_head_toggle()
    await controller.massage_foot_toggle()

    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        b"$J",
        b"$I",
    ]


async def test_power_bob_rgb_matches_clean_room_channel_vectors() -> None:
    """Power Bob scales RGB and sends selector-before-value channel frames."""
    controller, client = _controller("HHC0069815CDEF")

    with patch("custom_components.adjustable_bed.beds.motosleep.asyncio.sleep") as sleep:
        await controller.set_light_color((255, 128, 0))

    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        b"$#003150012000004R\r",
        b"$#003160006000002R\r",
        b"$#003170000000005R\r",
    ]
    assert all(call.kwargs["response"] is False for call in client.write_gatt_char.await_args_list)
    assert sleep.await_args_list == [call(0.02), call(0.02)]


async def test_rgb_off_uses_absolute_zero_channels() -> None:
    """RGB profiles expose idempotent off instead of the unrelated $A toggle."""
    controller, client = _controller(_hhc_name("5", c22="M", c26="I"))

    assert controller.supports_discrete_light_control is True
    assert controller.supports_explicit_light_on_control is False
    await controller.lights_off()

    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        build_motosleep_numeric_frame("00000", selector) for selector in ("00315", "00316", "00317")
    ]


async def test_hhc_sync_uses_distinct_enable_and_disable_opcodes() -> None:
    """Current MainPanel bind state maps to the two proven numeric frames."""
    controller, client = _controller(_hhc_name("G", c22="M"))

    assert controller.supports_synchro is True
    await controller.set_synchro(True)
    await controller.set_synchro(False)

    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        build_motosleep_sync_frame("00012"),
        build_motosleep_sync_frame("00015"),
    ]


async def test_binary_preset_and_memory_frames_are_model_specific() -> None:
    """Normal MOTO pages use binary preset recall and save commands."""
    controller, client = _controller(_moto_name("4"))

    await controller.preset_tv()
    await controller.preset_memory(1)
    await controller.program_memory(2)

    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        build_moto_binary_frame(0x800A),
        build_moto_binary_frame(0x800C),
        build_moto_binary_frame(0x811E),
    ]


async def test_binary_standard_release_uses_five_zero_stop_frames() -> None:
    """Normal MOTO movement uses the standard five-write release helper."""
    controller, client = _controller(_moto_name("4"))

    await controller.move_back_up()

    assert [call.args[1] for call in client.write_gatt_char.await_args_list[1:]] == [
        build_moto_binary_frame(0x0000, 0)
    ] * 5


async def test_binary_wr219_uses_second_stop_vector() -> None:
    """WR219 movement ends with six 0x9088/data=1 STOP frames."""
    controller, client = _controller(_moto_name("9"))

    await controller.move_back_up()

    calls = client.write_gatt_char.await_args_list
    assert calls[0].args[1] == build_moto_binary_frame(0x000A)
    assert [call.args[1] for call in calls[1:]] == [build_moto_binary_frame(0x9088, 1)] * 6


def test_swing_is_only_exposed_by_swing_models() -> None:
    """Binary swing commands are model-specific bed functions, not audio."""
    swing = _controller(_moto_name("8"))[0]
    wr219 = _controller(_moto_name("9"))[0]
    normal = _controller(_moto_name("4"))[0]

    assert swing.supports_preset_swing is True
    assert swing.profile.swing == 0x8014
    assert wr219.profile.swing == 0x9089
    assert normal.supports_preset_swing is False
