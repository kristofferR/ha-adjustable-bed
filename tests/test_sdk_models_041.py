"""Focused source vectors for private SDK models, not receive integration proof."""

from copy import deepcopy
from typing import Never, SupportsIndex

import pytest

from custom_components.adjustable_bed.beds.reverie_pairlink_sdk_models import (
    PairlinkModelBoundsError,
    PairlinkModelNegativeLengthError,
    PairlinkModelNullError,
    PairlinkSdkDevice,
    PairlinkSdkSensor,
    PairlinkSdkSensorCadence,
    PairlinkSdkUnit,
    add_init_sensor,
    apply_nonbasic_tlv,
    replace_ping_device,
    set_sensor_onoff,
    set_sensor_sensitivity,
)


def device(count: int = 1) -> PairlinkSdkDevice:
    return PairlinkSdkDevice(unit_num=count, units=[PairlinkSdkUnit() for _ in range(count)])


def words(*values: int) -> bytes:
    return b"".join(value.to_bytes(2, "little") for value in values)


def test_extracted_constructor_vector() -> None:
    # Frozen control-models Vectors.java: model-constructor-defaults.
    bean = device(2)
    unit = bean.units[0]
    assert bean.profile_ver == 0
    assert (unit.valid, unit.onoff, unit.function_id, unit.level) == (True, False, 0, 0)
    assert (unit.scene_toggle, unit.restore_function_id, unit.restore_level) == (-1, 0, 0)
    assert unit.level_toggle_up and unit.temperature_toggle_up and unit.hue_toggle_up
    assert (unit.ctl.minimum, unit.ctl.maximum, unit.ctl.kelvin) == (0, 65535, False)
    assert unit.ctl is not unit.restore_ctl
    assert unit.hsl is not unit.restore_hsl
    assert unit.groups is not bean.units[1].groups


@pytest.mark.parametrize("function", [2, 3, 4, 5, 20, 65535])
def test_status_function_widths(function: int) -> None:
    bean = device()
    data = {
        2: b"\xff",
        3: words(0xFFFE),
        4: words(17, 0x8000, 0xFFFF),
        5: words(17, 0x8000, 0xFFFF),
        20: words(17, 0x8000, 0xFFFF),
    }.get(function, b"")
    apply_nonbasic_tlv(bean, 1, words(function) + data)
    unit = bean.units[0]
    assert unit.function_id == (4 if function == 20 else function)
    assert unit.onoff == (function != 65535)
    if function in (4, 20):
        assert (unit.level, unit.ctl.lightness, unit.ctl.temperature, unit.ctl.delta_uv) == (
            17,
            17,
            32768,
            65535,
        )
        assert unit.ctl.kelvin == (function == 20)
    elif function == 5:
        assert (unit.level, unit.hsl.lightness, unit.hsl.hue, unit.hsl.saturation) == (
            17,
            17,
            32768,
            65535,
        )


@pytest.mark.parametrize("function", [3, 4, 5, 20])
def test_zero_status_preserves_individual_brightness(function: int) -> None:
    bean = device()
    unit = bean.units[0]
    unit.level, unit.ctl.lightness, unit.hsl.lightness = 11, 22, 33
    apply_nonbasic_tlv(bean, 1, words(function, 0, 7, 8))
    assert not unit.onoff
    assert unit.level == {3: 11, 4: 22, 20: 22, 5: 33}[function]
    assert (unit.ctl.lightness, unit.hsl.lightness) == (22, 33)


def test_status_short_record_preserves_ordered_partial_writes() -> None:
    bean = device()
    with pytest.raises(PairlinkModelBoundsError):
        apply_nonbasic_tlv(bean, 1, words(20, 123, 456) + b"\xff")
    unit = bean.units[0]
    assert unit.function_id == 20  # remap to4 occurs only after deltaUv read
    assert (unit.onoff, unit.level, unit.ctl.temperature) == (True, 123, 456)
    assert not unit.ctl.kelvin


def test_status_mixed_unit_record_strides() -> None:
    bean = device(4)
    apply_nonbasic_tlv(bean, 1, words(2) + b"\x01" + words(3, 77, 5, 11, 22, 33, 20, 44, 55, 66))
    assert [u.function_id for u in bean.units] == [2, 3, 5, 4]
    assert [u.level for u in bean.units] == [0, 77, 11, 44]


def test_status_list_failure_after_prior_unit_write() -> None:
    bean = device()
    bean.unit_num = 2
    with pytest.raises(PairlinkModelBoundsError):
        apply_nonbasic_tlv(bean, 1, words(2) + b"\x01" + words(2) + b"\x00")
    assert bean.units[0].onoff


def test_same_function_unknown_reuses_cursor_for_every_unit() -> None:
    bean = device(3)
    apply_nonbasic_tlv(bean, 22, words(4) + b"\x01")
    assert [unit.function_id for unit in bean.units] == [4, 4, 4]
    assert not any(unit.onoff for unit in bean.units)
    apply_nonbasic_tlv(bean, 22, words(2) + b"\x80\x00")
    assert [unit.onoff for unit in bean.units] == [True, False, False]


def test_same_function_header_read_even_for_no_units() -> None:
    with pytest.raises(PairlinkModelBoundsError):
        apply_nonbasic_tlv(device(0), 22, b"\x03")
    with pytest.raises(PairlinkModelNullError):
        apply_nonbasic_tlv(device(0), 22, None)


@pytest.mark.parametrize("current,restore", [(4, 2), (20, 5), (5, 2)])
def test_restore_color_selects_current_function(current: int, restore: int) -> None:
    bean = device()
    unit = bean.units[0]
    unit.function_id = current
    apply_nonbasic_tlv(bean, 8, words(restore, 1, 2, 65535))
    assert (unit.function_id, unit.restore_function_id) == (current, restore)
    color = unit.restore_hsl if current == 5 else unit.restore_ctl
    assert color.lightness == 1
    if current in (4, 20):
        assert (unit.restore_ctl.temperature, unit.restore_ctl.delta_uv) == (2, 65535)
        assert unit.restore_ctl.kelvin == (current == 20)
    else:
        assert (unit.restore_hsl.hue, unit.restore_hsl.saturation) == (2, 65535)


def test_restore_level_overrides_current_color_selection() -> None:
    bean = device(2)
    bean.units[0].function_id = 20
    apply_nonbasic_tlv(bean, 8, words(3, 17, 2))
    assert bean.units[0].restore_level == 17
    assert bean.units[1].restore_function_id == 2
    assert bean.units[0].function_id == 20


@pytest.mark.parametrize("function", [2, 3, 4, 5, 20])
@pytest.mark.parametrize("onoff", [0, 1, 127, 128, 255])
def test_restore_v2_signed_onoff_and_live_color(function: int, onoff: int) -> None:
    bean = device()
    fields = {2: b"", 3: words(7), 4: words(7, 8, 9), 5: words(7, 8, 9), 20: words(7, 8, 9)}
    apply_nonbasic_tlv(bean, 19, words(function) + fields[function] + bytes([onoff]))
    unit = bean.units[0]
    assert (unit.function_id, unit.restore_function_id) == (function, function)
    assert unit.onoff == (onoff != 0 if function == 2 else 0 < onoff < 128)
    if function in (4, 20):
        assert unit.level == unit.ctl.lightness == unit.restore_ctl.lightness == 7
        assert unit.ctl.temperature == unit.restore_ctl.temperature == 8
        assert unit.ctl.delta_uv == unit.restore_ctl.delta_uv == 9
        assert unit.ctl.kelvin == unit.restore_ctl.kelvin == (function == 20)
    elif function == 5:
        assert unit.level == unit.hsl.lightness == unit.restore_hsl.lightness == 7
        assert unit.hsl.hue == unit.restore_hsl.hue == 8
        assert unit.hsl.saturation == unit.restore_hsl.saturation == 9
    elif function == 3:
        assert unit.level == unit.restore_level == 7


def test_restore_v2_missing_onoff_does_not_copy_restore_to_live() -> None:
    bean = device()
    with pytest.raises(PairlinkModelBoundsError):
        apply_nonbasic_tlv(bean, 19, words(20, 11, 22, 33))
    unit = bean.units[0]
    assert (unit.function_id, unit.restore_function_id) == (20, 20)
    assert (
        unit.restore_ctl.lightness,
        unit.restore_ctl.temperature,
        unit.restore_ctl.delta_uv,
    ) == (11, 22, 33)
    assert unit.ctl.lightness == 0 and not unit.restore_ctl.kelvin


@pytest.mark.parametrize("subtype,width", [(7, 1), (17, 2)])
def test_group_duplicates_zero_preserve_and_negative_clear(subtype: int, width: int) -> None:
    bean = device(3)
    for unit in bean.units:
        unit.groups[:] = [99]
    entry = (lambda v: bytes([v])) if width == 1 else (lambda v: words(v))
    apply_nonbasic_tlv(bean, subtype, b"\x02" + entry(7) * 2 + b"\x00\xff")
    assert [u.groups for u in bean.units] == [[7, 7], [99], []]


@pytest.mark.parametrize("subtype", [7, 17])
def test_group_short_tail_leaves_cleared_and_partly_filled(subtype: int) -> None:
    bean = device()
    bean.units[0].groups[:] = [99]
    with pytest.raises(PairlinkModelBoundsError):
        apply_nonbasic_tlv(
            bean,
            subtype,
            b"\x02" + (b"\x07" if subtype == 7 else words(7)) + (b"" if subtype == 7 else b"\xff"),
        )
    assert bean.units[0].groups == [7]


def test_bitmap_groups_and_rejected_size() -> None:
    bean = device(2)
    apply_nonbasic_tlv(bean, 3, b"\x02\x81\x01\x00\x80")
    assert [u.groups for u in bean.units] == [[0, 7, 8], [15]]
    prior = deepcopy(bean)
    assert apply_nonbasic_tlv(bean, 3, b"\x00").warnings
    assert apply_nonbasic_tlv(bean, 3, b"\x02\x01").warnings
    assert bean == prior


def test_group_versions_preserve_duplicate_order_and_exact_address() -> None:
    bean = device()
    bean.vaddr, bean.bt_addr = bytes.fromhex("01a0ff00"), "AA:BB:CC:DD:EE:FF"
    result = apply_nonbasic_tlv(bean, 4, b"\x02\xff" + words(65535) + b"\xff" + words(2))
    assert [(r.group, r.version, r.vaddr_hex, r.bt_addr) for r in result.group_name_versions] == [
        (255, 65535, "01a0ff00", bean.bt_addr),
        (255, 2, "01a0ff00", bean.bt_addr),
    ]
    assert apply_nonbasic_tlv(bean, 4, b"\xff").warnings


def test_unit_names_signed_lengths_and_partial_names() -> None:
    bean = device(2)
    apply_nonbasic_tlv(bean, 6, b"\x02Hi\x00")
    assert [u.name for u in bean.units] == ["Hi", ""]
    with pytest.raises(PairlinkModelNegativeLengthError):
        apply_nonbasic_tlv(bean, 6, b"\x01A\xff")
    assert [u.name for u in bean.units] == ["A", ""]
    with pytest.raises(PairlinkModelBoundsError):
        apply_nonbasic_tlv(bean, 6, b"\x02x")
    assert bean.units[0].name == "A"


@pytest.mark.parametrize(
    "raw,expected",
    [
        (b"", ""),
        (b"A\x00", "A\x00"),
        ("æ😀".encode(), "æ😀"),
        (b"\xed\xa0\x80", "\ufffd"),
        (b"\xed\xa0\x80\xff", "\ufffd\ufffd"),
        (b"\xe2\x82", "\ufffd"),
    ],
)
def test_device_name_utf8_replacement(raw: bytes, expected: str) -> None:
    bean = device()
    apply_nonbasic_tlv(bean, 2, raw)
    assert bean.device_name == expected
    with pytest.raises(PairlinkModelNullError):
        apply_nonbasic_tlv(bean, 2, None)
    assert bean.device_name == expected


def test_toggle_odd_tail_changes_level_direction_before_failure() -> None:
    bean = device()
    with pytest.raises(PairlinkModelBoundsError):
        apply_nonbasic_tlv(bean, 9, b"\xff")
    unit = bean.units[0]
    assert not unit.level_toggle_up and unit.temperature_toggle_up
    apply_nonbasic_tlv(bean, 9, b"\x01\x02")
    assert unit.level_toggle_up and not unit.temperature_toggle_up
    apply_nonbasic_tlv(bean, 20, b"\x00")
    assert not unit.hue_toggle_up
    apply_nonbasic_tlv(bean, 10, words(65534))
    assert unit.scene_toggle == -2


def test_extracted_sensor_duplicate_vectors() -> None:
    # Frozen SensorSemanticsHost.java duplicate and unit-zero setter vectors.
    bean = device(2)
    add_init_sensor(bean, 0, -1)
    first = bean.units[0].sensors[0]
    first.onoff, first.sensitivity = True, 19
    add_init_sensor(bean, 0, -1)
    assert bean.units[0].sensors == [first]
    assert first.onoff and first.sensitivity == 19
    second = PairlinkSdkSensor(-1, False, 20)
    bean.units[0].sensors.append(second)
    bean.units[1].sensors.append(PairlinkSdkSensor(-1, False, 30))
    set_sensor_onoff(bean, -1, 1, True)
    set_sensor_sensitivity(bean, -1, 1, 70000)
    assert [r.sensitivity for r in bean.units[0].sensors] == [70000, 70000]
    assert bean.units[1].sensors[0].sensitivity == 30
    assert bean.units[1].sensors[0].onoff
    set_sensor_onoff(bean, -1, 0, False)
    assert not any(r.onoff for r in bean.units[0].sensors)
    result = apply_nonbasic_tlv(bean, 5, b"\xff\x80\xff\xff\xff\x00\x34\x12\x99")
    assert result.warnings
    assert all(not r.onoff and r.sensitivity == 0x1234 for r in bean.units[0].sensors)
    assert len(bean.units[0].sensors) == 2


@pytest.mark.parametrize("index", [-1, 2])
def test_sensor_invalid_unit_fails_without_allocating(index: int) -> None:
    bean = device()
    with pytest.raises(PairlinkModelBoundsError):
        add_init_sensor(bean, index, 7)
    assert not bean.units[0].sensors


def test_sensor_empty_and_short_prefix_never_allocates_units() -> None:
    bean = device(0)
    assert apply_nonbasic_tlv(bean, 5, b"\x01").warnings
    with pytest.raises(PairlinkModelBoundsError):
        apply_nonbasic_tlv(bean, 5, b"\x01\x01\x00\x00")


def test_misc_metadata_is_private_and_guards_keep_source_null_semantics() -> None:
    bean = device()
    assert apply_nonbasic_tlv(bean, 12, None).storage_ping
    assert bean.support_storage
    apply_nonbasic_tlv(bean, 13, None)  # declared len0 returns before payload read
    apply_nonbasic_tlv(bean, 16, None)
    assert bean.deleted
    apply_nonbasic_tlv(bean, 13, words(65535))
    assert bean.profile_ver == 65535
    apply_nonbasic_tlv(bean, 18, b"abc")
    apply_nonbasic_tlv(bean, 18, None)
    assert bean.vendor_business == b"abc"
    apply_nonbasic_tlv(bean, 24, b"\xff")
    apply_nonbasic_tlv(bean, 24, None)
    assert bean.dynamic_running
    apply_nonbasic_tlv(bean, 23, words(60000, 100))
    assert (bean.units[0].ctl.minimum, bean.units[0].ctl.maximum) == (60000, 100)
    with pytest.raises(PairlinkModelBoundsError):
        apply_nonbasic_tlv(bean, -3, words(42) + b"\x00")
    assert (bean.reboot_times, bean.mesh_changed_times) == (42, 0)


@pytest.mark.parametrize("subtype", [0, 14, 21, 11, -2, 127])
def test_unowned_or_excluded_dispatch_branch_is_not_invented(subtype: int) -> None:
    bean = device()
    prior = deepcopy(bean)
    assert not apply_nonbasic_tlv(bean, subtype, None).handled
    assert bean == prior


def test_forward_removal_leaves_adjacent_duplicate_then_appends_and_sorts() -> None:
    first, adjacent, separated = [PairlinkSdkDevice(bt_addr="B") for _ in range(3)]
    other, incoming = PairlinkSdkDevice(bt_addr="A"), PairlinkSdkDevice(bt_addr="B")
    rows = [first, adjacent, other, separated]
    replace_ping_device(rows, incoming)
    assert rows == [other, adjacent, incoming]
    assert rows[1] is adjacent and rows[2] is incoming


def test_duplicate_list_nulls_and_empty_incoming() -> None:
    rows = [None]
    replace_ping_device(rows, None)
    assert rows == [None]
    with pytest.raises(PairlinkModelNullError):
        replace_ping_device(rows, PairlinkSdkDevice(bt_addr="A"))
    assert len(rows) == 2  # append is not rolled back by sort failure
    single: list[PairlinkSdkDevice | None] = []
    replace_ping_device(single, PairlinkSdkDevice(bt_addr=None))
    assert len(single) == 1  # Java performs no comparison for a one-row sort
    with pytest.raises(PairlinkModelNullError):
        replace_ping_device(single, PairlinkSdkDevice(bt_addr="A"))


def test_duplicate_sort_uses_utf16_order() -> None:
    rows = [PairlinkSdkDevice(bt_addr="\ue000")]
    incoming = PairlinkSdkDevice(bt_addr="😀")
    replace_ping_device(rows, incoming)
    assert rows[0] is incoming


def test_only_remove_index_error_is_caught() -> None:
    class RemoveFails(list[PairlinkSdkDevice | None]):
        def pop(self, index: SupportsIndex = -1) -> PairlinkSdkDevice | None:
            raise IndexError("source concurrent-remove seam")

    old = PairlinkSdkDevice(bt_addr="A")
    rows = RemoveFails([old])
    incoming = PairlinkSdkDevice(bt_addr="A")
    replace_ping_device(rows, incoming)
    assert rows == [old, incoming]


@pytest.mark.parametrize("subtype", [1, 8, 9, 10, 19, 20, 6])
def test_nonpositive_unit_count_does_not_dereference_null(subtype: int) -> None:
    apply_nonbasic_tlv(device(-1), subtype, None)


@pytest.mark.parametrize("subtype", [1, 3, 4, 5, 6, 7, 8, 9, 10, 17, 19, 20, 22, 23, -3])
def test_positive_units_propagate_null_helper_failure(subtype: int) -> None:
    with pytest.raises(PairlinkModelNullError):
        apply_nonbasic_tlv(device(), subtype, None)


def test_raw_constructor_nullable_fields_and_cadence_preservation() -> None:
    bean = device()
    assert bean.bt_addr is None and bean.device_name is None
    assert bean.vendor_business is None and bean.version is None
    add_init_sensor(bean, 0, 1)
    row = bean.units[0].sensors[0]
    assert row.cadence is None
    cadence = PairlinkSdkSensorCadence(delta_down=77, publish_period=123456789012)
    row.cadence = cadence
    apply_nonbasic_tlv(bean, 5, b"\x01\x01\x01\x00")
    assert row.cadence is cadence
    assert (cadence.delta_down, cadence.publish_period) == (77, 123456789012)


def test_nested_list_getter_bounds_are_caught_before_append() -> None:
    class LookupFails(list[PairlinkSdkDevice | None]):
        def __getitem__(self, index: SupportsIndex | slice) -> Never:
            raise IndexError("source getter concurrent-remove seam")

    old = PairlinkSdkDevice(bt_addr="A")
    rows = LookupFails([old])
    incoming = PairlinkSdkDevice(bt_addr="B")
    replace_ping_device(rows, incoming)
    assert list(rows) == [old, incoming]


def test_group_name_version_hex_conversion_retains_null_for_empty() -> None:
    bean = device()
    bean.vaddr = b""
    row = apply_nonbasic_tlv(bean, 4, b"\x01\x07\x01\x00").group_name_versions[0]
    assert row.vaddr_hex is None and row.bt_addr is None
