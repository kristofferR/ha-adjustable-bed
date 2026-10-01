"""Source-anchored Motion Bed parser vectors and semantic branch checks."""

from dataclasses import replace

import pytest

from custom_components.adjustable_bed.motion_bed_state import (
    MotionBedContext,
    MotionBedFollowup,
    MotionBedRoute,
    MotionBedState,
    PresetVariant,
    k4_short_recall_selected,
    parse_motion_bed_k4_text,
    parse_motion_bed_notification,
)


def parse(
    raw: str,
    *contexts: MotionBedContext,
    state: MotionBedState | None = None,
    variant: PresetVariant = "K1",
    alternate: bool = False,
):
    return parse_motion_bed_notification(
        bytes.fromhex(raw),
        MotionBedRoute(
            preset_variant=variant, alternate_identity=alternate, contexts=frozenset(contexts)
        ),
        state or MotionBedState(),
    )


@pytest.mark.parametrize("variant", ["K1", "K2", "K2M", "K3", "K8", "K9", "K11"])
@pytest.mark.parametrize(
    "index,field", enumerate(("memory_1", "memory_2", "tv", "zero_gravity", "snore"))
)
def test_preset_selector_variants(variant: PresetVariant, index: int, field: str) -> None:
    alternate = variant in ("K3", "K8", "K9")
    selectors = (
        ("0A", "0B", "05", "09", "0F")
        if alternate
        else ("AA", "AB", "AB" if variant in ("K2", "K2M") else "A5", "A9", "AF")
    )
    result = parse(
        "FFFFFFFF" + ("030600" if alternate else "031200") + selectors[index],
        "preset",
        variant=variant,
    )
    assert getattr(result.state, field) == (not (index == 4 and variant in ("K3", "K8")))
    if result.matched_records:
        assert result.matched_records == (f"Kuaijie{variant}Fragment:handleReceiveData",)


@pytest.mark.parametrize("variant", ["K2", "K2M"])
def test_duplicate_ab_and_conditional_alternate(variant: PresetVariant) -> None:
    duplicate = parse("FFFFFFFF031200AB", "preset", variant=variant)
    assert duplicate.state.memory_2 and duplicate.state.tv
    assert not parse("FFFFFFFF031200A5", "preset", variant=variant).state.tv
    assert not parse("FFFFFFFF031200AB", "preset", variant=variant, alternate=True).state.tv
    assert parse("FFFFFFFF03060005", "preset", variant=variant, alternate=True).state.tv


@pytest.mark.parametrize(
    "field,set_echo,clear_echo",
    [
        ("memory_1", "A00A2F07", "AF0A2AF7"),
        ("memory_2", "B00BE307", "BF0BE6F7"),
        ("tv", "50052B03", "5F052EF3"),
        ("zero_gravity", "90097B06", "9F097EF6"),
        ("snore", "F00FD304", "FF0FD6F4"),
    ],
)
@pytest.mark.parametrize("variant", ["K1", "K2", "K2M", "K3", "K8", "K9", "K11", "modular"])
def test_exact_echo_set_clear(
    variant: PresetVariant, field: str, set_echo: str, clear_echo: str
) -> None:
    selected = parse("FFFFFFFF050000" + set_echo, "preset", variant=variant)
    supported = not (field == "snore" and variant in ("K3", "K8"))
    assert getattr(selected.state, field) == supported
    assert not getattr(
        parse("FFFFFFFF050000" + clear_echo, "preset", variant=variant, state=selected.state).state,
        field,
    )
    damaged = set_echo[:-2] + "00"
    assert not getattr(parse("FFFFFFFF050000" + damaged, "preset", variant=variant).state, field)


@pytest.mark.parametrize(
    "field,selector,set_echo,clear_echo",
    [
        ("left_tv", "31", "10311B14", "1F311EE4"),
        ("right_tv", "32", "20324F15", "2F324AE5"),
        ("left_zero_gravity", "33", "30338315", "3F3386E5"),
        ("right_zero_gravity", "34", "4034E717", "4F34E2E7"),
    ],
)
def test_k4_repaired_selectors_and_all_eight_echoes(
    field: str, selector: str, set_echo: str, clear_echo: str
) -> None:
    selected = parse("FFFFFFFF031200" + selector, "preset", variant="K4")
    assert getattr(selected.state, field)
    assert getattr(parse("FFFFFFFF050000" + set_echo, "preset", variant="K4").state, field)
    assert not getattr(
        parse("FFFFFFFF050000" + clear_echo, "preset", variant="K4", state=selected.state).state,
        field,
    )
    # Independent contains branches execute in source order, regardless of wire order.
    combined = "FFFFFFFF050000" + clear_echo + "FFFFFFFF050000" + set_echo
    assert not getattr(parse(combined, "preset", variant="K4").state, field)


@pytest.mark.parametrize(
    "selector",
    [
        "031200AA",
        "031200AB",
        "031200A5",
        "031200A9",
        "031200AF",
        "0306000A",
        "0306000B",
        "03060005",
        "03060009",
        "0306000F",
    ],
)
def test_k4_ordinary_selectors_do_nothing(selector: str) -> None:
    assert parse("FFFFFFFF" + selector, "preset", variant="K4").state == MotionBedState()


@pytest.mark.parametrize("left,right", [(False, False), (True, False), (False, True), (True, True)])
def test_k4_short_recall_cross_flags(left: bool, right: bool) -> None:
    state = MotionBedState(
        left_tv=left, right_tv=right, left_zero_gravity=not left, right_zero_gravity=not right
    )
    for field in ("left_tv", "right_tv", "left_zero_gravity"):
        assert k4_short_recall_selected(state, field) == left
    assert k4_short_recall_selected(state, "right_zero_gravity") == right
    with pytest.raises(ValueError):
        k4_short_recall_selected(state, "tv")


def test_k5_coupled_memory_flags_and_no_echo_clear() -> None:
    state = parse("FFFFFFFF03120033FFFFFFFF03120034", "preset", variant="K5").state
    assert state.left_memory and state.right_memory
    assert state.coupled_left_memory and state.coupled_right_memory
    assert parse("FFFFFFFF050000AF0A2AF7", "preset", variant="K5", state=state).state == state
    assert parse("FFFFFFFF03120031", "preset", variant="K5").state.left_tv
    assert parse("FFFFFFFF03120032", "preset", variant="K5").state.right_tv


@pytest.mark.parametrize(
    "raw,field,value",
    [
        ("0500000100D690", "upper_massage", 0),
        ("050000011E5698", "upper_massage", 1),
        ("050000011F9758", "upper_massage", 2),
        ("0500000120D748", "upper_massage", 3),
        ("0500000200D660", "lower_massage", 0),
        ("05000002211678", "lower_massage", 1),
        ("05000002225679", "lower_massage", 2),
        ("050000022397B9", "lower_massage", 3),
        ("0500000324D7EB", "massage_wave", 1),
        ("0500000325162B", "massage_wave", 2),
        ("0500000326562A", "massage_wave", 3),
        ("050000032797EA", "massage_wave", 4),
    ],
)
def test_massage_exact_literals(raw: str, field: str, value: int) -> None:
    result = parse("FFFFFFFF" + raw, "massage", "motor_settings")
    assert getattr(result.state, field) == value
    assert set(result.matched_records) == {
        "AnmoFragment:handleReceiveData",
        "DianDongSetActivity:handleReceiveData",
    }


def test_light_and_motor_defaults() -> None:
    assert parse("FFFFFFFF05000109", "light").state.brightness == 9
    assert (
        parse("FFFFFFFF05000100", "light", state=MotionBedState(light_timer=3)).state.light_timer
        == 0
    )
    for timer in range(4):
        result = parse("FFFFFFFF01001C1402000A" + f"{timer:02X}", "motor_settings")
        assert result.state.brightness == 10 and result.state.light_timer == timer
    for timer in range(3):
        state = parse("FFFFFFFF01001C1404010203" + f"{timer:02X}", "motor_settings").state
        assert (state.upper_massage, state.lower_massage, state.massage_wave) == (1, 2, 3)
        assert state.massage_timer == (timer + 1) * 10
        assert state.massage_timer_raw == timer
    assert parse("FFFFFFFF01001C1401", "motor_settings").receipts == ("motor_defaults_saved_01",)
    assert parse("FFFFFFFF01001C1403", "motor_settings").receipts == ("motor_defaults_saved_03",)
    assert parse("FFFFFFFF0100130B85", "motor_settings").state.alarm_music == 5
    assert parse("FFFFFFFF0100150B8A", "preset", variant="K2M").state.audio_volume == 10


@pytest.mark.parametrize(
    "context,owner",
    [
        ("home", "HomeActivity"),
        ("motor", "DiandongFragment"),
        ("motor_settings", "DianDongSetActivity"),
    ],
)
@pytest.mark.parametrize(
    "flag,enabled,audio",
    [(15, True, False), (31, True, True), (175, False, False), (161, False, True)],
)
@pytest.mark.parametrize("mode", [1, 2, 3, 4, 5, 6])
def test_all_alarm_receivers_modes(
    context: MotionBedContext, owner: str, flag: int, enabled: bool, audio: bool, mode: int
) -> None:
    raw = "FFFFFFFF01000413" + f"{flag:02X}" + "0630008200" + f"{mode:02X}" + "01020000"
    result = parse(raw, context)
    assert result.state.alarm_enabled == enabled and result.state.audio_available == audio
    assert result.state.alarm_hour == "06" and result.state.alarm_minute == "30"
    assert result.state.alarm_weekdays == (1, 7) and result.state.alarm_repeat
    assert result.state.alarm_mode == mode and result.state.alarm_massage
    assert not result.state.alarm_sound and result.state.alarm_music == 2
    assert set(result.matched_records) == {owner + ":handleReceiveData", owner + ":setHasAlarm"}


def test_no_alarm_audio_override_and_sync() -> None:
    assert not parse("FFFFFFFF0100030B00", "home").state.audio_available
    assert parse("FFFFFFFF0100030B01", "home").state.audio_available
    assert not parse("FFFFFFFF0100030B01", "home", alternate=True).state.audio_available
    assert parse("FFFFFFFF0100030B00", "motor").state.first_modular_alarm
    assert parse("FFFFFFFF0100030B01", "motor").state == MotionBedState()
    for opcode in (9, 10):
        for enabled in (0, 1, 15):
            state = parse(f"FFFFFFFF0100{opcode:02X}0B{enabled:02X}", "home").state
            assert state.sync_visible and state.sync_enabled == (enabled == 1)


def test_modular_capabilities_sensor_mac_and_followup() -> None:
    for flags in range(32):
        result = parse("FFFFFFFF01002A14" + f"{flags:02X}" + "01000101", "motor", variant="modular")
        assert (
            result.state.tv,
            result.state.zero_gravity,
            result.state.memory_1,
            result.state.memory_2,
            result.state.snore,
        ) == tuple(bool(flags & (1 << i)) for i in range(5))
        assert result.state.motor_sensor_enabled and not result.state.motor_massage_visible
        assert result.state.motor_light_enabled and result.state.motor_massage_enabled
        assert result.effects == (MotionBedFollowup("sensor_query", 200),)
    disabled = parse("FFFFFFFF01002A140000010000", "motor").state
    assert disabled.sensor_present is False and disabled.motor_massage_visible
    result = parse("FFFFFFFF01000C11030123456789AB", "motor")
    assert result.state.sensor_present and result.state.sensor_mac == "0123456789AB"
    absent = parse("FFFFFFFF01000C11000123456789AB", "motor", state=result.state).state
    assert absent.sensor_present is False and absent.sensor_mac == "0123456789AB"


@pytest.mark.parametrize(
    "motor,air,thermal", [(bool(i & 1), bool(i & 2), bool(i & 4)) for i in range(8)]
)
def test_hub_module_bytes_priority_and_all_receivers(motor: bool, air: bool, thermal: bool) -> None:
    raw = (
        "FFFFFFFF0100271400"
        + ("0A" if motor else "00")
        + "0000"
        + ("0B" if air else "00")
        + "0000"
        + ("0C" if thermal else "00")
    )
    result = parse(raw, "module_startup", "module_binding", "module_settings", "module_change")
    assert result.state.motor_module_present == motor
    assert result.state.air_module_present == air and result.state.thermal_module_present == thermal
    assert result.state.first_module_type == (
        10 if motor else 11 if air else 12 if thermal else None
    )
    assert len(result.matched_records) == 4
    bound = parse("FFFFFFFF01002914", "module_binding")
    assert bound.effects == (MotionBedFollowup("module_status_query"),)
    deleted = parse("FFFFFFFF01002814", "module_change", "module_settings", state=result.state)
    assert deleted.state.motor_module_present is None
    assert deleted.effects == (MotionBedFollowup("module_status_query"),)
    assert set(deleted.matched_records) == {
        "Setting2Activity:handleReceiveData",
        "ChangeDeviceActivity:handleReceiveData",
    }


@pytest.mark.parametrize(
    "part,expected",
    [
        ("6008", "head"),
        ("4002", "head"),
        ("6009", "back"),
        ("4004", "back"),
        ("600C", "left_hip"),
        ("600D", "right_hip"),
        ("6007", "left_leg"),
        ("600A", "right_leg"),
        ("60CD", "hip"),
        ("400D", "hip"),
        ("607A", "leg"),
        ("400A", "leg"),
        ("0860", ""),
    ],
)
@pytest.mark.parametrize(
    "code,expected_fault",
    [
        ("000A", "broken_motor"),
        ("0014", "motor_overload"),
        ("001E", "motor_short_circuit"),
        ("00C8", "distance_sensor_fault"),
        ("00D2", "same_group_distance_sensor_fault"),
        ("00DC", "excessive_distance_difference"),
        ("00E6", "reverse_motor"),
        ("0064", "distance_out_of_range"),
        ("006E", "distance_jump"),
        ("0078", "target_position_deviation"),
        ("0000", "normal"),
        ("0A00", ""),
    ],
)
def test_fault_raw_string_semantics(
    part: str, expected: str, code: str, expected_fault: str
) -> None:
    result = parse("FFFFFFFF0304" + part + code, "fault_settings")
    assert (result.state.fault_part_raw, result.state.fault_code_raw) == (part, code)
    assert (result.state.fault_part, result.state.fault) == (expected, expected_fault)
    assert result.effects == ()
    assert result.matched_records == (
        "SettingActivity:handleReceiveData",
        "FaultDebugDialog:setFaultBody",
    )


@pytest.mark.parametrize("custom", range(4))
def test_air_custom_partial_flags_and_adaptive(custom: int) -> None:
    old = MotionBedState(air_full_custom=True, air_back_custom=True, air_adaptive=True)
    state = parse("FFFFFFFFFF14020901" + f"{custom:02X}" + "00", "air", state=old).state
    assert state.air_full_custom and state.air_back_custom and state.air_adaptive
    fresh = parse("FFFFFFFFFF14020901" + f"{custom:02X}" + "01", "air").state
    assert fresh.air_full_custom == (custom in (1, 3))
    assert fresh.air_back_custom == (custom in (2, 3)) and fresh.air_adaptive
    for zone in (3, 18):
        for saved in (0, 1, 15):
            state = parse(f"FFFFFFFFFF14030D01{saved:02X}{zone:02X}", "air", state=old).state
            assert (state.air_full_custom if zone == 3 else state.air_back_custom) == (saved == 1)
    assert parse("FFFFFFFFFF0D030C0100", "air", state=old).state.air_adaptive is False
    assert parse("FFFFFFFFFF0D030C0101", "air").state.air_adaptive is True


@pytest.mark.parametrize("mode", [3, 18, 5, 4, 12])
@pytest.mark.parametrize("gear", range(1, 9))
@pytest.mark.parametrize("timer", range(3))
def test_air_settings_readback(mode: int, gear: int, timer: int) -> None:
    raw = f"FFFFFFFFFF14020801{mode:02X}{gear * 10:02X}005000{timer:02X}"
    result = parse(raw, "air_settings")
    assert result.state.air_setting_mode == mode
    assert result.state.air_upper_raw == gear * 10 and result.state.air_upper_gear == gear
    assert result.state.air_lower_raw == 80 and result.state.air_lower_gear == 8
    assert result.state.air_timer == timer
    assert parse("FFFFFFFFFF14030E01", "air_settings").receipts == ("air_settings_saved",)


def test_pressure_exact_47_bytes_triplets_and_integer_scaling() -> None:
    raw = (
        "FFFFFFFFFF2F020401"
        + "".join(f"{i:02X}" + (i * 10 + 9).to_bytes(2, "little").hex() for i in range(12))
        + "0000"
    )
    result = parse(raw, "pressure_settings")
    assert result.state.pressure_values == tuple(range(12))
    assert result.state.pressure_raw == tuple(i * 10 + 9 for i in range(12))
    assert result.state.pressure_triplet_tags == tuple(range(12))
    assert (
        parse(raw + "00", "pressure_settings").rejection == "pressure_reply_requires_exact_47_bytes"
    )
    assert parse("FFFFFFFFFF2F030501", "pressure_settings").receipts == ("pressure_settings_saved",)


@pytest.mark.parametrize(
    "mode,gear,index", [(0, 0, 4), (1, 1, 5), (1, 4, 8), (2, 1, 3), (2, 4, 0), (3, 4, 4), (4, 4, 4)]
)
@pytest.mark.parametrize("timer", [False, True])
def test_thermal_decimal_fields_and_timer_persistence(
    mode: int, gear: int, index: int, timer: bool
) -> None:
    raw = f"FFFFFFFFFE14000001{(16 if timer else 0) + mode:02X}{gear:02X}213002043025190000"
    old = MotionBedState(
        thermal_timer_hour="08",
        thermal_timer_minute="00",
        thermal_timer_mode=1,
        thermal_timer_gear="02",
    )
    result = parse(raw, "thermal", state=old)
    assert result.state.thermal_mode == mode and result.state.thermal_slider_index == index
    assert (
        result.state.thermal_temperature == 30.25
        and result.state.thermal_temperature_display == "30.25"
    )
    assert result.state.thermal_water == 19 and result.state.thermal_low_water
    assert result.state.thermal_timer_enabled == timer
    assert result.state.thermal_timer_hour == ("21" if timer else "08")
    assert result.state.thermal_timer_minute == ("30" if timer else "00")
    assert result.state.thermal_timer_mode == (2 if timer else 1)
    periodic = parse("FFFFFFFFFE140001010202080002011005", "thermal", state=result.state)
    assert periodic.state.thermal_temperature == 10.5 and periodic.state.thermal_slider_index == 2
    assert periodic.state.thermal_timer_enabled == timer and periodic.state.thermal_water == 19
    assert parse("FFFFFFFFFE14000701", "thermal").receipts == ("thermal_clock_received",)
    assert parse("FFFFFFFFFE14000201", "thermal_schedule").receipts == (
        "thermal_schedule_received",
    )


def test_thermal_invalid_decimal_handling_and_source_temperature_branches() -> None:
    old = MotionBedState(thermal_temperature=12.5, thermal_temperature_display="12.5")
    full = parse("FFFFFFFFFE14000001000400000000ABCD200000", "thermal", state=old)
    assert full.state.thermal_temperature == 12.5
    periodic = parse("FFFFFFFFFE14000101000400000000ABCD", "thermal", state=old)
    assert periodic.state.thermal_temperature is None
    assert (
        parse("FFFFFFFFFE14000001010A000000003025200000", "thermal").rejection
        == "thermal_gear_not_decimal_digits"
    )
    assert (
        parse("FFFFFFFFFE140000010004000000003025AF0000", "thermal").rejection
        == "thermal_water_not_decimal_digits"
    )


def test_sleep_positions_calibration_and_switches() -> None:
    raw = "FFFFFFFF02000A1400000A0B00000F00010100"
    result = parse(raw, "smart_sleep", "calibration", "network")
    assert result.state.sleep_enabled and result.state.night_light_enabled
    assert result.state.calibration_flat == 10 and result.state.calibration_side == 22
    assert (
        result.state.network_status == "connected" and result.state.provisioning_status == "success"
    )
    assert parse("FFFFFFFF02000E0B0300", "home", "smart_sleep").state.sleep_timer == 3
    positions = parse("FFFFFFFF02000F0EAFBF0102", "sleep_adjust")
    assert positions.state.raw_positions == (175, 191, 1, 2)
    stored = parse("FFFFFFFF020010120001020304050607", "sleep_adjust")
    assert stored.state.stored_flat_positions == (0, 1, 2, 3)
    assert stored.state.stored_side_positions == (4, 5, 6, 7)
    assert stored.effects == (MotionBedFollowup("position_query", 100),)
    assert parse("FFFFFFFF0200090D010102", "calibration").state.calibration_flat == 1026
    assert parse("FFFFFFFF0200090D020102", "calibration").state.calibration_side == 513
    capture = parse("FFFFFFFF0200090F0301020304", "calibration_capture")
    assert (capture.state.calibration_aa, capture.state.calibration_kk) == (513, 1027)
    assert parse("FFFFFFFF0200090F0301020304", "calibration").state.calibration_aa is None
    assert parse("FFFFFFFF0500008208B666", "calibration").state.calibration_reset_received
    assert parse("FFFFFFFF0200160B04", "sleep_report").state.fall_timer == 4


@pytest.mark.parametrize(
    "status,expected",
    [(0, "not_configured"), (1, "not_connected"), (10, "unstable"), (15, "connected")],
)
def test_sensor_network_status_and_finite_polling(status: int, expected: str) -> None:
    raw = "FFFFFFFF02000A14000000000000" + f"{status:02X}"
    result = parse(raw, "network")
    assert result.state.network_status == expected
    assert bool(result.effects) == (status in (0, 1))
    if result.effects:
        assert result.effects[0] == MotionBedFollowup("network_status_query", 6000)
    exhausted = parse(raw, "network", state=MotionBedState(network_poll_attempts=10))
    assert not exhausted.effects
    if status in (0, 1):
        assert exhausted.state.provisioning_status == "failed"
    for reply, outcome in ((0, "failed"), (1, "waiting"), (15, "success")):
        result = parse(f"FFFFFFFF0200191300{reply:02X}", "network")
        assert result.state.provisioning_status == outcome
        assert result.effects == (
            MotionBedFollowup("network_status_query", 6000 if reply == 1 else 0),
        )


@pytest.mark.parametrize("operation", [4, 5, 20])
@pytest.mark.parametrize(
    "segment,historical,flat,side,total,unit",
    [
        (1, False, 10, 20, 30, "minutes"),
        (6, False, 1, 2, 3, "hours"),
        (60, False, 10, 20, 30, "hours"),
        (1, True, 1, 2, 3, "hours"),
    ],
)
def test_day_metric_segments(
    operation: int,
    segment: int,
    historical: bool,
    flat: float,
    side: float,
    total: float,
    unit: str,
) -> None:
    raw = f"FFFFFFFF0200{operation:02X}14{segment:02X}0A1403010203040506"
    route = MotionBedRoute(contexts=frozenset({"day_report"}), historical_day=historical)
    result = parse_motion_bed_notification(bytes.fromhex(raw), route, MotionBedState())
    assert (result.state.day_flat, result.state.day_side, result.state.day_total) == (
        flat,
        side,
        total,
    )
    assert result.state.day_rolls == 3 and result.state.day_unit == unit
    assert result.state.day_slots[:6] == (1, 2, 3, 4, 5, 6)


@pytest.mark.parametrize("historical", [False, True])
@pytest.mark.parametrize("offset", range(5))
def test_day_segment_aggregation_windows_and_app_assignment(historical: bool, offset: int) -> None:
    state = MotionBedState(day_slots=tuple(range(24)))
    route = MotionBedRoute(
        contexts=frozenset({"day_report"}), historical_day=historical, day_window_offset=offset
    )
    second = parse_motion_bed_notification(
        bytes.fromhex("FFFFFFFF0200041402010203040506070809"), route, state
    )
    assert second.state.day_slots[6:15] == tuple(range(1, 10))
    result = parse_motion_bed_notification(
        bytes.fromhex("FFFFFFFF0200041403010203040506070809"), route, second.state
    )
    assert result.state.day_slots[15:] == tuple(range(1, 10))
    slots = result.state.day_slots
    start = 8 + offset if historical else 8
    assert result.state.day_window == slots[start : start + 12]
    if not historical:
        assert result.state.day_previous_window == slots[:12]
        assert result.state.day_next_window == slots[12:24]
        assert result.state.app_day_previous_window == slots[12:24]
        assert result.state.app_day_next_window == (0,) * 12
    assert result.state.day_received_segments == (2, 3)


def test_month_report_all_fields_broad_source_recognition() -> None:
    state = parse("FFFFFFFF02009914010A141E0203042832", "month_report").state
    assert (
        state.month_days,
        state.month_average_sleep,
        state.month_maximum_sleep,
        state.month_minimum_sleep,
    ) == (1, 1, 2, 3)
    assert (state.month_average_rolls, state.month_maximum_rolls, state.month_minimum_rolls) == (
        2,
        3,
        4,
    )
    assert (state.month_flat, state.month_side) == (4, 5)
    assert parse("FFFFFFFF02009914010A141E0203042832", "home").state.month_days is None


@pytest.mark.parametrize(
    "context,raw",
    [
        ("light", "FFFFFFFF05000101"),
        ("home", "FFFFFFFF010004130F06300082000101010000"),
        ("motor_settings", "FFFFFFFF01001C140401020301"),
        ("motor", "FFFFFFFF01002A141F01010101"),
        ("motor", "FFFFFFFF01000C11030123456789AB"),
        ("module_startup", "FFFFFFFF01002714000A00000B00000C"),
        ("fault_settings", "FFFFFFFF03046008000A"),
        ("air", "FFFFFFFFFF140209010301"),
        ("air_settings", "FFFFFFFFFF14020801035000500002"),
        ("pressure_settings", "FFFFFFFFFF2F020401" + "000A00" * 12 + "0000"),
        ("thermal", "FFFFFFFFFE140000011204080002011005500000"),
        ("smart_sleep", "FFFFFFFF02000A140000000000000F00010100"),
        ("sleep_adjust", "FFFFFFFF02000F0E01020304"),
        ("sleep_adjust", "FFFFFFFF020010120001020304050607"),
        ("calibration", "FFFFFFFF0200090D010102"),
        ("calibration_capture", "FFFFFFFF0200090F0301020304"),
        ("network", "FFFFFFFF020019130001"),
        ("day_report", "FFFFFFFF02000414010A1403010203040506"),
        ("month_report", "FFFFFFFF02009914010A141E0203042832"),
    ],
)
def test_absolute_offset_parsers_reject_embedded_match_without_side_effects(
    context: MotionBedContext, raw: str
) -> None:
    old = MotionBedState(memory_1=True, thermal_temperature=12.5)
    result = parse("00" + raw, context, state=old)
    assert result.rejection == "nonzero_match_absolute_offset"
    assert result.state is old and not result.effects and not result.receipts


@pytest.mark.parametrize(
    "context,raw",
    [
        ("home", "FFFFFFFF010004130F"),
        ("motor", "FFFFFFFF01002A1401"),
        ("fault_settings", "FFFFFFFF03046008"),
        ("sleep_adjust", "FFFFFFFF02000F0E010203"),
        ("sleep_adjust", "FFFFFFFF0200101200010203040506"),
        ("month_report", "FFFFFFFF0200041401000000000000"),
        ("thermal", "FFFFFFFFFE1400010101040000000030"),
        ("pressure_settings", "FFFFFFFFFF2F020401" + "000A00" * 12),
    ],
)
def test_underlength_guards_are_atomic(context: MotionBedContext, raw: str) -> None:
    old = MotionBedState(memory_1=True)
    result = parse(raw, context, state=old)
    assert result.rejection == "underlength"
    assert result.state is old and result.matched_records == () and result.effects == ()


def test_target_contexts_and_public_updates() -> None:
    raw = "FFFFFFFFFF140209010301"
    assert parse(raw, "home").state == MotionBedState()
    updates = MotionBedState(raw_positions=(175, 191, 1, 2), fault="normal").to_updates()
    assert updates["raw_positions"] == "[175, 191, 1, 2]"
    assert updates["fault"] == "normal" and updates["air_timer"] is None
    with pytest.raises(ValueError):
        MotionBedRoute(day_window_offset=5)


# Every registered parser vector from the accepted package report.
_REGISTERED_PARSER_VECTORS = (
    (
        "pressure-state-0",
        "FFFFFFFFFF2F0204010100000100000100000100000100000100000100000100000100000100000100000100000000",
        "pressure_settings",
        "K1",
        False,
        0,
        {"pressure_values": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)},
    ),
    (
        "pressure-state-9",
        "FFFFFFFFFF2F020401015A00015A00015A00015A00015A00015A00015A00015A00015A00015A00015A00015A000000",
        "pressure_settings",
        "K1",
        False,
        0,
        {"pressure_values": (9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9)},
    ),
    (
        "air-state",
        "FFFFFFFFFF14020801035000341202",
        "air_settings",
        "K1",
        False,
        0,
        {"air_setting_mode": 3, "air_upper_raw": 80, "air_lower_raw": 4660, "air_timer": 2},
    ),
    (
        "cal-state-saved",
        "FFFFFFFF02000A1400000A46",
        "calibration",
        "K1",
        False,
        0,
        {"calibration_flat": 10, "calibration_side": 140},
    ),
    (
        "cal-state-flat",
        "FFFFFFFF0200090D013412",
        "calibration",
        "K1",
        False,
        0,
        {"calibration_flat": 9320},
    ),
    (
        "cal-state-side",
        "FFFFFFFF0200090D023412",
        "calibration",
        "K1",
        False,
        0,
        {"calibration_side": 4660},
    ),
    (
        "cal-state-live",
        "FFFFFFFF0200090F0334127856",
        "calibration_capture",
        "K1",
        False,
        0,
        {"calibration_aa": 4660, "calibration_kk": 22136},
    ),
    (
        "month",
        "FFFFFFFF020003141E50643C030501283C",
        "month_report",
        "K1",
        False,
        0,
        {
            "month_days": 30,
            "month_average_sleep": 8.0,
            "month_maximum_sleep": 10.0,
            "month_minimum_sleep": 6.0,
            "month_average_rolls": 3,
            "month_maximum_rolls": 5,
            "month_minimum_rolls": 1,
            "month_flat": 4.0,
            "month_side": 6.0,
        },
    ),
    (
        "day-1-False",
        "FFFFFFFF02000414010A1403010203040506",
        "day_report",
        "K1",
        False,
        0,
        {
            "day_flat": 10,
            "day_side": 20,
            "day_total": 30,
            "day_rolls": 3,
            "day_unit": "minutes",
            "source_slot_offset": 0,
            "source_slots": (1, 2, 3, 4, 5, 6),
        },
    ),
    (
        "day-6-False",
        "FFFFFFFF02000414060A1403010203040506",
        "day_report",
        "K1",
        False,
        0,
        {
            "day_flat": 1.0,
            "day_side": 2.0,
            "day_total": 3.0,
            "day_rolls": 3,
            "day_unit": "hours",
            "source_slot_offset": 0,
            "source_slots": (1, 2, 3, 4, 5, 6),
        },
    ),
    (
        "day-60-False",
        "FFFFFFFF020004143C0A1403010203040506",
        "day_report",
        "K1",
        False,
        0,
        {
            "day_flat": 10,
            "day_side": 20,
            "day_total": 30,
            "day_rolls": 3,
            "day_unit": "hours",
            "source_slot_offset": 0,
            "source_slots": (1, 2, 3, 4, 5, 6),
        },
    ),
    (
        "day-1-True",
        "FFFFFFFF02000414010A1403010203040506",
        "day_report",
        "K1",
        True,
        0,
        {
            "day_flat": 1.0,
            "day_side": 2.0,
            "day_total": 3.0,
            "day_rolls": 3,
            "day_unit": "hours",
            "source_slot_offset": 0,
            "source_slots": (1, 2, 3, 4, 5, 6),
        },
    ),
    (
        "day-segment-2",
        "FFFFFFFF0200041402010203040506070809",
        "day_report",
        "K1",
        False,
        0,
        {"source_slot_offset": 6, "source_slots": (1, 2, 3, 4, 5, 6, 7, 8, 9)},
    ),
    (
        "day-segment-3",
        "FFFFFFFF0200041403010203040506070809",
        "day_report",
        "K1",
        False,
        0,
        {"source_slot_offset": 15, "source_slots": (1, 2, 3, 4, 5, 6, 7, 8, 9)},
    ),
    (
        "thermal-hot4",
        "FFFFFFFFFE14000001010421300104302519000000",
        "thermal",
        "K1",
        False,
        0,
        {
            "thermal_slider_index": 8,
            "thermal_timer_enabled": False,
            "thermal_temperature_display": "30.25",
            "thermal_water": 19,
        },
    ),
    (
        "thermal-cool2",
        "FFFFFFFFFE14000001120208000201100550000000",
        "thermal",
        "K1",
        False,
        0,
        {
            "thermal_slider_index": 2,
            "thermal_timer_enabled": True,
            "thermal_temperature_display": "10.5",
            "thermal_water": 50,
            "thermal_timer_hour": "08",
            "thermal_timer_minute": "00",
            "thermal_timer_mode": 2,
            "thermal_timer_gear": "01",
        },
    ),
    (
        "IA001-F001:selector-31-initial-0",
        "FF FF FF FF 03 12 00 31 00 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": True,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:selector-32-initial-0",
        "FF FF FF FF 03 12 00 32 00 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": True,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:selector-33-initial-0",
        "FF FF FF FF 03 12 00 33 00 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": True,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:selector-34-initial-0",
        "FF FF FF FF 03 12 00 34 00 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": True,
        },
    ),
    (
        "IA001-F001:set-31-initial-0",
        "FF FF FF FF 05 00 00 10 31 1B 14 00 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": True,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:set-32-initial-0",
        "FF FF FF FF 05 00 00 20 32 4F 15 00 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": True,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:set-33-initial-0",
        "FF FF FF FF 05 00 00 30 33 83 15 00 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": True,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:set-34-initial-0",
        "FF FF FF FF 05 00 00 40 34 E7 17 00 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": True,
        },
    ),
    (
        "IA001-F001:clear-31-initial-0",
        "FF FF FF FF 05 00 00 1F 31 1E E4 00 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:clear-32-initial-0",
        "FF FF FF FF 05 00 00 2F 32 4A E5 00 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:clear-33-initial-0",
        "FF FF FF FF 05 00 00 3F 33 86 E5 00 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:clear-34-initial-0",
        "FF FF FF FF 05 00 00 4F 34 E2 E7 00 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:excluded-031200-AA-initial-0",
        "FF FF FF FF 03 12 00 AA 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:excluded-031200-AB-initial-0",
        "FF FF FF FF 03 12 00 AB 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:excluded-031200-A5-initial-0",
        "FF FF FF FF 03 12 00 A5 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:excluded-031200-A9-initial-0",
        "FF FF FF FF 03 12 00 A9 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:excluded-031200-AF-initial-0",
        "FF FF FF FF 03 12 00 AF 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:excluded-030600-0A-initial-0",
        "FF FF FF FF 03 06 00 0A 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:excluded-030600-0B-initial-0",
        "FF FF FF FF 03 06 00 0B 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:excluded-030600-05-initial-0",
        "FF FF FF FF 03 06 00 05 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:excluded-030600-09-initial-0",
        "FF FF FF FF 03 06 00 09 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:excluded-030600-0F-initial-0",
        "FF FF FF FF 03 06 00 0F 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:selector-31-initial-15",
        "FF FF FF FF 03 12 00 31 00 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:selector-32-initial-15",
        "FF FF FF FF 03 12 00 32 00 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:selector-33-initial-15",
        "FF FF FF FF 03 12 00 33 00 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:selector-34-initial-15",
        "FF FF FF FF 03 12 00 34 00 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:set-31-initial-15",
        "FF FF FF FF 05 00 00 10 31 1B 14 00 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:set-32-initial-15",
        "FF FF FF FF 05 00 00 20 32 4F 15 00 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:set-33-initial-15",
        "FF FF FF FF 05 00 00 30 33 83 15 00 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:set-34-initial-15",
        "FF FF FF FF 05 00 00 40 34 E7 17 00 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:clear-31-initial-15",
        "FF FF FF FF 05 00 00 1F 31 1E E4 00 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": False, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:clear-32-initial-15",
        "FF FF FF FF 05 00 00 2F 32 4A E5 00 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": False, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:clear-33-initial-15",
        "FF FF FF FF 05 00 00 3F 33 86 E5 00 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": False, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:clear-34-initial-15",
        "FF FF FF FF 05 00 00 4F 34 E2 E7 00 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": False},
    ),
    (
        "IA001-F001:excluded-031200-AA-initial-15",
        "FF FF FF FF 03 12 00 AA 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:excluded-031200-AB-initial-15",
        "FF FF FF FF 03 12 00 AB 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:excluded-031200-A5-initial-15",
        "FF FF FF FF 03 12 00 A5 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:excluded-031200-A9-initial-15",
        "FF FF FF FF 03 12 00 A9 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:excluded-031200-AF-initial-15",
        "FF FF FF FF 03 12 00 AF 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:excluded-030600-0A-initial-15",
        "FF FF FF FF 03 06 00 0A 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:excluded-030600-0B-initial-15",
        "FF FF FF FF 03 06 00 0B 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:excluded-030600-05-initial-15",
        "FF FF FF FF 03 06 00 05 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:excluded-030600-09-initial-15",
        "FF FF FF FF 03 06 00 09 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:excluded-030600-0F-initial-15",
        "FF FF FF FF 03 06 00 0F 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:lowercase-initial-0",
        "ff ff ff ff 03 12 00 31",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:unspaced-initial-0",
        "FFFFFFFF03120031",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:double-spaced-initial-0",
        "FF  FF  FF  FF  03  12  00  31",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:truncated-initial-0",
        "FF FF FF FF 03 12 00 3",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:wrong-echo-checksum-initial-0",
        "FF FF FF FF 05 00 00 10 31 1B 00",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:lowercase-initial-15",
        "ff ff ff ff 03 12 00 31",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:unspaced-initial-15",
        "FFFFFFFF03120031",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:double-spaced-initial-15",
        "FF  FF  FF  FF  03  12  00  31",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:truncated-initial-15",
        "FF FF FF FF 03 12 00 3",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:wrong-echo-checksum-initial-15",
        "FF FF FF FF 05 00 00 10 31 1B 00",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:nonzero-match",
        "ignored FF FF FF FF 03 12 00 31 trailing",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": True,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:selector-suffix",
        "FF FF FF FF 03 12 00 310",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": True,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:all-selectors",
        "FF FF FF FF 03 12 00 31 / FF FF FF FF 03 12 00 32 / FF FF FF FF 03 12 00 33 / FF FF FF FF 03 12 00 34",
        "preset",
        "K4",
        False,
        0,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:set-and-clear",
        "FF FF FF FF 05 00 00 10 31 1B 14 / FF FF FF FF 05 00 00 1F 31 1E E4",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:clear-before-set",
        "FF FF FF FF 05 00 00 1F 31 1E E4 / FF FF FF FF 05 00 00 10 31 1B 14",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:all-echoes",
        "FF FF FF FF 05 00 00 10 31 1B 14 / FF FF FF FF 05 00 00 20 32 4F 15 / FF FF FF FF 05 00 00 30 33 83 15 / FF FF FF FF 05 00 00 40 34 E7 17 / FF FF FF FF 05 00 00 1F 31 1E E4 / FF FF FF FF 05 00 00 2F 32 4A E5 / FF FF FF FF 05 00 00 3F 33 86 E5 / FF FF FF FF 05 00 00 4F 34 E2 E7",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:dependency-state-mask-0",
        "",
        "preset",
        "K4",
        False,
        0,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:dependency-state-mask-1",
        "",
        "preset",
        "K4",
        False,
        1,
        {
            "left_tv": True,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:dependency-state-mask-2",
        "",
        "preset",
        "K4",
        False,
        2,
        {
            "left_tv": False,
            "right_tv": True,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:dependency-state-mask-3",
        "",
        "preset",
        "K4",
        False,
        3,
        {
            "left_tv": True,
            "right_tv": True,
            "left_zero_gravity": False,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:dependency-state-mask-4",
        "",
        "preset",
        "K4",
        False,
        4,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": True,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:dependency-state-mask-5",
        "",
        "preset",
        "K4",
        False,
        5,
        {
            "left_tv": True,
            "right_tv": False,
            "left_zero_gravity": True,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:dependency-state-mask-6",
        "",
        "preset",
        "K4",
        False,
        6,
        {
            "left_tv": False,
            "right_tv": True,
            "left_zero_gravity": True,
            "right_zero_gravity": False,
        },
    ),
    (
        "IA001-F001:dependency-state-mask-7",
        "",
        "preset",
        "K4",
        False,
        7,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": False},
    ),
    (
        "IA001-F001:dependency-state-mask-8",
        "",
        "preset",
        "K4",
        False,
        8,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": True,
        },
    ),
    (
        "IA001-F001:dependency-state-mask-9",
        "",
        "preset",
        "K4",
        False,
        9,
        {
            "left_tv": True,
            "right_tv": False,
            "left_zero_gravity": False,
            "right_zero_gravity": True,
        },
    ),
    (
        "IA001-F001:dependency-state-mask-10",
        "",
        "preset",
        "K4",
        False,
        10,
        {
            "left_tv": False,
            "right_tv": True,
            "left_zero_gravity": False,
            "right_zero_gravity": True,
        },
    ),
    (
        "IA001-F001:dependency-state-mask-11",
        "",
        "preset",
        "K4",
        False,
        11,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": False, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:dependency-state-mask-12",
        "",
        "preset",
        "K4",
        False,
        12,
        {
            "left_tv": False,
            "right_tv": False,
            "left_zero_gravity": True,
            "right_zero_gravity": True,
        },
    ),
    (
        "IA001-F001:dependency-state-mask-13",
        "",
        "preset",
        "K4",
        False,
        13,
        {"left_tv": True, "right_tv": False, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:dependency-state-mask-14",
        "",
        "preset",
        "K4",
        False,
        14,
        {"left_tv": False, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    (
        "IA001-F001:dependency-state-mask-15",
        "",
        "preset",
        "K4",
        False,
        15,
        {"left_tv": True, "right_tv": True, "left_zero_gravity": True, "right_zero_gravity": True},
    ),
    ('module-3', 'FFFFFFFF01002714000A00000B00000D0000', 'module_startup', 'modular', False, 0, {'motor_module_present': True, 'air_module_present': True, 'thermal_module_present': False}),
    ('module-all', 'FFFFFFFF01002714000A00000B00000C', 'module_startup', 'modular', False, 0, {'motor_module_present': True, 'air_module_present': True, 'thermal_module_present': True}),
    ('module-none', 'FFFFFFFF010027140000000000000000', 'module_startup', 'modular', False, 0, {'motor_module_present': False, 'air_module_present': False, 'thermal_module_present': False}),
    ('caps-all', 'FFFFFFFF01002A141F01010101', 'motor', 'modular', False, 0, {'tv': True, 'zero_gravity': True, 'memory_1': True, 'memory_2': True, 'snore': True, 'motor_sensor_enabled': True, 'motor_massage_visible': True, 'motor_light_enabled': True, 'motor_massage_enabled': True}),
    ('caps-none', 'FFFFFFFF01002A140000000000', 'motor', 'modular', False, 0, {'tv': False, 'zero_gravity': False, 'memory_1': False, 'memory_2': False, 'snore': False, 'motor_sensor_enabled': False, 'motor_massage_visible': False, 'motor_light_enabled': False, 'motor_massage_enabled': False}),
    ('positions-unsigned', 'FFFFFFFF02000F0EAFBFFF01', 'sleep_adjust', 'K1', False, 0, {'raw_positions': (175, 191, 255, 1)}),
    ('positions-zero', 'FFFFFFFF02000F0E00000000', 'sleep_adjust', 'K1', False, 0, {'raw_positions': (0, 0, 0, 0)}),

)


@pytest.mark.parametrize(
    "vector_id,raw,context,variant,historical,mask,expected",
    _REGISTERED_PARSER_VECTORS,
    ids=[row[0] for row in _REGISTERED_PARSER_VECTORS],
)
def test_registered_parser_vectors(
    vector_id: str,
    raw: str,
    context: MotionBedContext,
    variant: PresetVariant,
    historical: bool,
    mask: int,
    expected: dict[str, object],
) -> None:
    initial = MotionBedState(
        left_tv=bool(mask & 1),
        right_tv=bool(mask & 2),
        left_zero_gravity=bool(mask & 4),
        right_zero_gravity=bool(mask & 8),
    )
    route = MotionBedRoute(
        preset_variant=variant, contexts=frozenset({context}), historical_day=historical
    )
    result = (
        parse_motion_bed_k4_text(raw, initial)
        if variant == "K4"
        else parse_motion_bed_notification(bytes.fromhex(raw), route, initial)
    )
    assert result.rejection is None, vector_id
    for field, value in expected.items():
        if field not in ("source_slot_offset", "source_slots"):
            assert getattr(result.state, field) == value, (vector_id, field)
    if "source_slots" in expected:
        offset = expected["source_slot_offset"]
        assert isinstance(offset, int)
        source_slots = expected["source_slots"]
        assert isinstance(source_slots, tuple)
        assert result.state.day_slots[offset : offset + len(source_slots)] == source_slots
    if variant == "K4":
        assert k4_short_recall_selected(result.state, "left_tv") == result.state.left_tv
        assert k4_short_recall_selected(result.state, "right_tv") == result.state.left_tv
        assert k4_short_recall_selected(result.state, "left_zero_gravity") == result.state.left_tv
        assert k4_short_recall_selected(result.state, "right_zero_gravity") == result.state.right_tv


def test_unrecognized_air_settings_retain_selected_state_but_keep_raw_limits() -> None:
    old = MotionBedState(air_setting_mode=3, air_timer=2, air_upper_gear=4, air_lower_gear=8)
    result = parse("FFFFFFFFFF14020801AA341278560F", "air_settings", state=old)
    assert result.state.air_setting_mode == 3 and result.state.air_timer == 2
    assert result.state.air_upper_raw == 0x1234 and result.state.air_lower_raw == 0x5678
    assert result.state.air_upper_gear == 4 and result.state.air_lower_gear == 8
    assert parse("FFFFFFFFFF14030D010100", "air").state == MotionBedState()


def test_network_unknown_reply_keeps_status_and_source_followup() -> None:
    old = MotionBedState(provisioning_status="waiting", network_status="connected")
    result = parse("FFFFFFFF0200191300AA", "network", state=old)
    assert result.state == old
    assert result.effects == (MotionBedFollowup("network_status_query"),)
    exhausted = parse(
        "FFFFFFFF020019130001", "network", state=replace(old, network_poll_attempts=10)
    )
    assert exhausted.state.provisioning_status == "failed" and not exhausted.effects
    unknown = parse("FFFFFFFF02000A14000000000000AA", "network", state=old)
    assert unknown.state.network_code == 170 and unknown.state.network_status == "connected"


def test_day_raw_unit_and_app_label_persistence_are_distinct() -> None:
    first = parse("FFFFFFFF02000414060A1403010203040506", "day_report")
    second = parse("FFFFFFFF02000414010A1403010203040506", "day_report", state=first.state)
    assert second.state.day_unit == "minutes" and second.state.app_day_unit == "hours"
    assert second.state.day_flat == 10 and second.state.day_total == 30
    assert parse("FFFFFFFF02009914010A1403010203040506", "day_report").state == MotionBedState()
    assert parse("FFFFFFFF02000414040A1403010203040506", "day_report").state == MotionBedState()


def test_thermal_decimal_gear_and_unknown_mode_source_branches() -> None:
    full = parse("FFFFFFFFFE140000010110000000003005200000", "thermal")
    assert full.state.thermal_gear == 10 and full.state.thermal_slider_index == 14
    assert full.state.thermal_temperature_display == "30.5"
    assert not full.state.thermal_low_water
    unknown_full = parse("FFFFFFFFFE140000010500000000003005200000", "thermal")
    unknown_periodic = parse("FFFFFFFFFE140001010500000000003005", "thermal")
    assert unknown_full.state.thermal_slider_index == 4
    assert unknown_periodic.state.thermal_slider_index == 0


def test_sleep_false_states_and_independent_context_minimums() -> None:
    status = parse("FFFFFFFF02000A140000000000000000000000", "smart_sleep")
    assert status.state.sleep_enabled is False and status.state.night_light_enabled is False
    calibration = parse("FFFFFFFF02000A1400000A46", "calibration")
    assert calibration.rejection is None
    assert calibration.state.calibration_flat == 10 and calibration.state.calibration_side == 140
    assert parse("FFFFFFFF02000A1400000A46", "home").state == MotionBedState()


def test_massage_source_first_group_and_same_group_order() -> None:
    combined = "FFFFFFFF0500000100D690FFFFFFFF0500000120D748FFFFFFFF050000022397B9"
    result = parse(combined, "massage")
    assert result.state.upper_massage == 3 and result.state.lower_massage is None
    unmatched_first = parse("FFFFFFFF05000001FFFFFFFF050000022397B9", "massage")
    assert (
        unmatched_first.state.upper_massage is None and unmatched_first.state.lower_massage is None
    )


def test_hub_current_priority_and_initial_app_navigation_are_distinct() -> None:
    first = parse("FFFFFFFF01002714000000000B00000C", "module_startup")
    assert first.state.first_module_type == 11 and first.state.app_initial_module_type == 11
    next_result = parse("FFFFFFFF01002714000A00000B00000C", "module_startup", state=first.state)
    assert (
        next_result.state.first_module_type == 10
        and next_result.state.app_initial_module_type == 11
    )
