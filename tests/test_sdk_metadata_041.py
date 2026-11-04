"""Private source-component vectors; these do not assert runtime integration."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

import pytest

from custom_components.adjustable_bed.beds.reverie_pairlink_sdk_metadata import (
    PairlinkSdkMetadata,
    SdkAttributeRecord,
    SdkAttributeUnit,
    SdkCompositionQuery,
    SdkFingerprintQuery,
    SdkFingerprintRecord,
    SdkFingerprintStatus,
    SdkMetadataEffect,
    SdkMetadataStatus,
    SdkMetadataTimer,
    default_attribute_records,
)


@pytest.fixture(autouse=True)
def fixed_clock(freezer):
    freezer.move_to("2026-11-02 12:00:00")


@dataclass
class Unit:
    functions: list[int] = field(default_factory=list)


@dataclass
class Device:
    app_id: int = 123
    company_id: int = 456
    product_id: int = 789
    appearance: int = 1000
    bt_address: str = "010203040506"
    units: list[Unit] = field(default_factory=list)
    # Full canonical bean state must survive fingerprint persistence.
    bed_state: bytes = b"bed-state"


class Io:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.catalog: list[SdkAttributeRecord] | None = None
        self.use_defaults = False
        self.saved: dict[str, SdkFingerprintRecord[Device] | None] = {}
        self.fail_on: str | type[object] | None = None
        self.commit_result = True

    def _fail(self, operation: str | type[object]) -> None:
        if self.fail_on == operation:
            raise RuntimeError("injected boundary failure")

    async def read_attributes(
        self,
        defaults: list[SdkAttributeRecord],
    ) -> list[SdkAttributeRecord] | None:
        self.events.append("read_attributes")
        self._fail("read_attributes")
        return copy.deepcopy(defaults if self.use_defaults else self.catalog)

    async def write_attributes(self, records: list[SdkAttributeRecord]) -> bool:
        self.events.append("write_attributes")
        self._fail("write_attributes")
        self.catalog = copy.deepcopy(records)
        return self.commit_result

    async def read_fingerprint(
        self, home_id: str
    ) -> SdkFingerprintRecord[Device] | None:
        self.events.append(("read_fingerprint", home_id))
        self._fail("read_fingerprint")
        return copy.deepcopy(self.saved.get(home_id))

    async def write_fingerprint(
        self,
        home_id: str,
        record: SdkFingerprintRecord[Device] | None,
    ) -> bool:
        self.events.append(("write_fingerprint", home_id))
        self._fail("write_fingerprint")
        self.saved[home_id] = copy.deepcopy(record)
        return self.commit_result

    async def emit(self, effect: SdkMetadataEffect) -> None:
        self.events.append(effect)
        self._fail(type(effect))


def setup(
    devices: list[Device] | None = None,
) -> tuple[PairlinkSdkMetadata[Device], Io]:
    io = Io()
    return PairlinkSdkMetadata([] if devices is None else devices, io), io


@pytest.mark.asyncio
async def test_initialize_defaults_null_and_home_identity() -> None:
    state, io = setup()
    io.use_defaults = True
    await state.initialize("BE150000")
    assert len(state.attributes) == 15
    assert state.fingerprint.home_id == "BE150000"
    assert not state.fingerprint.valid
    assert not state.fingerprint_enabled
    assert state.fingerprint_state == 0
    assert io.events == ["read_attributes", ("read_fingerprint", "BE150000")]
    io.use_defaults = False
    await state.initialize("other")
    assert state.attributes == []
    assert state.fingerprint.home_id == "other"


def test_default_catalog_exact_vectors_and_fresh_allocations() -> None:
    records = default_attribute_records()
    assert [
        (
            r.app_id,
            r.company_id,
            r.product_ids,
            r.appearance,
            [u.functions for u in r.units],
        )
        for r in records
    ] == [
        (4369, 1465, [65535], 1984, [[2, 3]]),
        (4370, 1465, [4370], 1984, [[2, 3, 4, 5]]),
        (61697, 1465, [61697], 1984, [[2, 3, 4]]),
        (61698, 1465, [61698], 1984, [[2, 3, 4, 5]]),
        (61699, 1465, [61699], 1218, [[2], [2]]),
        (61700, 1465, [61700], 1860, [[2, 3]]),
        (61702, 32769, [0, 1], 1984, [[2, 3]]),
        (61702, 32769, [2, 3], 1984, [[2, 3, 4]]),
        (61703, 32769, [4], 1218, [[9]]),
        (61705, 32770, [65535], 1984, [[2, 3, 4]]),
        (61706, 32770, [256], 1984, [[2, 3, 4]]),
        (61711, 32770, [257], 1218, [[9]]),
        (61714, 32771, [0], 1218, [[2], [2]]),
        (61716, 32771, [1], 1218, [[2], [2]]),
        (61717, 1465, [256], 1984, [[2, 3, 4]]),
    ]
    records[0].units[0].functions.append(999)
    assert default_attribute_records()[0].units[0].functions == [2, 3]


@pytest.mark.asyncio
async def test_add_unknown_copies_masks_duplicates_and_status8_order() -> None:
    device = Device(-1, 0x10002, -3, 0x123456, units=[Unit([4, 5, 3, 4]), Unit([2])])
    state, io = setup([device])
    # No start or scheduler enable. False commit is ignored, then status8/finish.
    io.commit_result = False
    assert await state.add(device)
    assert state.attributes == [
        SdkAttributeRecord(
            65535,
            2,
            [65533],
            0x123456,
            [SdkAttributeUnit([4, 3, 5, 3, 4]), SdkAttributeUnit([2])],
        ),
    ]
    assert io.events == [
        "write_attributes",
        SdkMetadataStatus(8),
        SdkMetadataTimer("attributes", None),
    ]
    device.units[0].functions.clear()
    assert state.attributes[0].units[0].functions == [4, 3, 5, 3, 4]
    assert state.identity_key(device) == "65535_2_65533"


@pytest.mark.asyncio
async def test_known_add_is_complete_noop_even_with_queue_and_different_functions() -> (
    None
):
    device = Device(units=[Unit([9])])
    state, io = setup()
    state.attributes = [SdkAttributeRecord(123, 456, [65535], 77)]
    state.unknown_identities.append("unrelated")
    assert not await state.add(device)
    assert io.events == []
    assert state.unknown_identities == ["unrelated"]
    assert state.attributes[0].appearance == 77


@pytest.mark.asyncio
async def test_add_failure_retains_append_and_suppresses_following_effects() -> None:
    state, io = setup()
    io.fail_on = "write_attributes"
    with pytest.raises(RuntimeError):
        await state.add(Device())
    assert len(state.attributes) == 1
    assert io.events == ["write_attributes"]
    io.fail_on = None
    assert not await state.add(Device())  # source dedupe means no implicit retry
    assert io.events == ["write_attributes"]


@pytest.mark.asyncio
async def test_add_callback_failure_prevents_finish_but_not_persistence() -> None:
    state, io = setup()
    io.fail_on = SdkMetadataStatus
    with pytest.raises(RuntimeError):
        await state.add(Device())
    assert io.catalog == state.attributes
    assert io.events == ["write_attributes", SdkMetadataStatus(8)]


@pytest.mark.asyncio
async def test_add_absent_callback_still_persists_and_finishes() -> None:
    state, io = setup()
    state.callback_present = False
    await state.add(Device())
    assert io.events == ["write_attributes", SdkMetadataTimer("attributes", None)]


@pytest.mark.asyncio
@pytest.mark.parametrize("remaining", [False, True])
async def test_queue_removes_first_even_when_unrelated_and_never_emits_status8(
    remaining: bool,
) -> None:
    next_device = Device(987, 654, 321)
    state, io = setup([next_device])
    state.unknown_identities = ["unrelated"]
    if remaining:
        state.unknown_identities.append("987_654_321")
    await state.add(Device())
    assert io.events == (
        [
            "write_attributes",
            SdkMetadataTimer("attributes", None),
            SdkMetadataTimer("attributes", 3000),
            SdkCompositionQuery("010203040506"),
        ]
        if remaining
        else ["write_attributes", SdkMetadataTimer("attributes", None)]
    )
    assert state.unknown_identities == (["987_654_321"] if remaining else [])


@pytest.mark.asyncio
async def test_queue_no_matching_device_leaves_it_pending_without_new_effects() -> None:
    state, io = setup()
    state.unknown_identities = ["remove-me", "missing"]
    await state.add(Device())
    assert state.unknown_identities == ["missing"]
    assert io.events == ["write_attributes"]


def test_matching_distinct_pid_wildcard_and_exact_order() -> None:
    state, _ = setup()
    state.attributes = [
        SdkAttributeRecord(1, 2, [65535], 100, [SdkAttributeUnit([4])]),
        SdkAttributeRecord(3, 2, [9], 200, [SdkAttributeUnit([5])]),
        SdkAttributeRecord(1, 2, [9], 300, [SdkAttributeUnit([5])]),
    ]
    assert state.is_known(65537, 65538, 65545)
    assert state.appearance(2, 9) == 200  # wildcard app does NOT wildcard PID
    assert state.appearance(2, 8) == 0
    assert state.appearance(2, 9, app_id=1) == 100
    assert state.supports(1, 2, 9, 0, 4)
    assert not state.supports(1, 2, 9, 0, 5)  # no merge or later record fallback
    assert not state.supports(1, 2, 9, 1, 4)
    assert not state.supports(4, 2, 9, -1, 4)  # unmatched: never indexes
    with pytest.raises(IndexError):
        state.supports(1, 2, 9, -1, 4)


@pytest.mark.asyncio
async def test_clear_attributes_writes_defaults_without_reload() -> None:
    state, io = setup()
    state.attributes = [SdkAttributeRecord(1, 2, [3], 4)]
    before = state.attributes
    await state.clear_attributes()
    assert state.attributes is before and state.attributes[0].app_id == 1
    assert io.catalog == default_attribute_records()


@pytest.mark.asyncio
async def test_fingerprint_start_is_optional_one_shot_and_timer_is_symbolic() -> None:
    state, io = setup()
    assert not await state.begin_fingerprint()
    assert io.events == []
    state.fingerprint_enabled = True
    assert await state.begin_fingerprint()
    assert state.fingerprint_state == 1
    assert io.events == [
        SdkFingerprintQuery(),
        SdkMetadataTimer("fingerprint", None),
        SdkMetadataTimer("fingerprint", 500),
    ]
    assert not await state.begin_fingerprint()
    await state.fingerprint_timeout()
    assert state.fingerprint_state == 3
    assert io.events[-1] == SdkMetadataStatus(7)
    state.pending_fingerprint = "retained"
    state.reset_join_state()
    assert state.fingerprint_state == 0
    assert state.pending_fingerprint == "retained"


@pytest.mark.asyncio
async def test_fingerprint_send_exception_does_not_arm_timer_after_state1() -> None:
    state, io = setup()
    state.fingerprint_enabled = True
    io.fail_on = SdkFingerprintQuery
    with pytest.raises(RuntimeError):
        await state.begin_fingerprint()
    assert state.fingerprint_state == 1
    assert io.events == [SdkFingerprintQuery()]


@pytest.mark.asyncio
async def test_fingerprint_match_replaces_live_list_with_same_beans_before_status8() -> (
    None
):
    cached = Device(bed_state=b"complete-bean")
    live = [Device(999)]
    state, io = setup(live)
    state.fingerprint = SdkFingerprintRecord("home", "AbCd001122334455", [cached], True)
    state.fingerprint_state = 1
    io.commit_result = False
    assert await state.receive_fingerprint(bytes.fromhex("0242abcd001122334455ff"))
    assert state.devices is live and live == [cached] and live[0] is cached
    assert state.fingerprint.devices[0] is cached
    assert not state.fingerprint.valid
    assert state.fingerprint_state == 3
    assert io.events == [
        SdkMetadataTimer("fingerprint", None),
        ("write_fingerprint", "home"),
        SdkMetadataStatus(8),
    ]
    assert io.saved["home"].devices[0].bed_state == b"complete-bean"
    assert not io.saved["home"].valid


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "packet",
    [
        b"",
        b"\x02",
        b"\x02\x42" + bytes(7),
        b"\x01\x42" + bytes(8),
        b"\x02\x41" + bytes(8),
    ],
)
async def test_fingerprint_short_or_other_packet_has_no_effects(packet: bytes) -> None:
    state, io = setup()
    assert not await state.receive_fingerprint(packet)
    assert io.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "valid,value", [(True, bytes(8)), (False, b"abcdefgh"), (True, b"mismatch")]
)
async def test_fingerprint_miss_preserves_live_list_and_sets_pending(
    valid: bool,
    value: bytes,
) -> None:
    device = Device()
    state, io = setup([device])
    state.fingerprint = SdkFingerprintRecord("home", "6162636465666768", [], valid)
    state.fingerprint_state = 1
    await state.receive_fingerprint(b"\x02\x42" + value)
    assert state.devices == [device]
    assert state.fingerprint_state == 2
    assert state.pending_fingerprint == value.hex().upper()
    assert io.events == [SdkMetadataTimer("fingerprint", None), SdkMetadataStatus(7)]


@pytest.mark.asyncio
async def test_unsolicited_fingerprint_callback_only_and_absent_callback() -> None:
    state, io = setup()
    state.pending_fingerprint = "unchanged"
    await state.receive_fingerprint(b"\x02\x42abcdefgh")
    assert io.events == [
        SdkMetadataTimer("fingerprint", None),
        SdkFingerprintStatus("6162636465666768"),
    ]
    assert state.fingerprint_state == 0 and state.last_checked_fingerprint == ""
    assert state.pending_fingerprint == "unchanged"
    state.callback_present = False
    io.events.clear()
    await state.receive_fingerprint(b"\x02\x42abcdefgh")
    assert io.events == [SdkMetadataTimer("fingerprint", None)]


@pytest.mark.asyncio
async def test_fingerprint_load_failure_retains_state3_list_and_invalid_flag() -> None:
    cached = Device(111)
    state, io = setup([Device(999)])
    state.fingerprint = SdkFingerprintRecord("home", "6162636465666768", [cached], True)
    state.fingerprint_state = 1
    io.fail_on = "write_fingerprint"
    with pytest.raises(RuntimeError):
        await state.receive_fingerprint(b"\x02\x42abcdefgh")
    assert state.devices[0] is cached
    assert state.fingerprint_state == 3 and not state.fingerprint.valid
    assert SdkMetadataStatus(8) not in io.events


@pytest.mark.asyncio
async def test_ping_tail_save_then_state3_and_count_state_gates() -> None:
    device = Device()
    state, io = setup([device])
    state.fingerprint.home_id = "home"
    state.pending_fingerprint = "6162636465666768"
    state.fingerprint_state = 1
    assert not await state.ping_list_complete(1)
    state.fingerprint_state = 2
    assert not await state.ping_list_complete(2)
    io.fail_on = "write_fingerprint"
    with pytest.raises(RuntimeError):
        await state.ping_list_complete(1)
    assert state.fingerprint_state == 2
    assert state.fingerprint.devices[0] is device
    assert state.fingerprint.fingerprint == "6162636465666768"
    io.fail_on = None
    assert await state.ping_list_complete(1)
    assert state.fingerprint_state == 3 and not state.fingerprint.valid


@pytest.mark.asyncio
async def test_save_empty_home_is_noop_but_ping_still_sets_state3() -> None:
    state, io = setup([Device()])
    state.fingerprint_state = 2
    assert not await state.save_fingerprint("value")
    assert await state.ping_list_complete(1)
    assert state.fingerprint_state == 3
    assert io.events == []


@pytest.mark.asyncio
async def test_exit_save_status_guards_valid_flag_before_write_and_snapshot() -> None:
    device = Device()
    state, io = setup([device])
    state.fingerprint = SdkFingerprintRecord("home", "value", [], False)
    assert not await state.save_status()
    state.fingerprint_enabled = True
    io.fail_on = "write_fingerprint"
    with pytest.raises(RuntimeError):
        await state.save_status()
    assert state.fingerprint.valid
    assert state.fingerprint.devices[0] is device
    assert not await state.save_status()  # source doesn't retry valid failed save
    state.fingerprint.valid = False
    io.fail_on = None
    io.commit_result = False
    assert await state.save_status()
    device.bed_state = b"later"
    assert io.saved["home"].devices[0].bed_state == b"bed-state"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["home", "fingerprint", "devices"])
async def test_exit_missing_inputs_skip_persistence(missing: str) -> None:
    state, io = setup([Device()])
    state.fingerprint_enabled = True
    state.fingerprint = SdkFingerprintRecord("home", "value", [], False)
    if missing == "home":
        state.fingerprint.home_id = ""
    elif missing == "fingerprint":
        state.fingerprint.fingerprint = ""
    else:
        state.devices.clear()
    assert not await state.save_status()
    assert io.events == []


@pytest.mark.asyncio
async def test_clear_fingerprint_persists_first_matching_home_only_and_keeps_valid() -> (
    None
):
    state, io = setup([Device()])
    cached = Device(222)
    state.fingerprint = SdkFingerprintRecord("home", "value", [cached], True)
    state.fingerprint_state = 2
    await state.clear_fingerprint("other")
    assert state.fingerprint.devices == [cached]
    io.fail_on = "write_fingerprint"
    with pytest.raises(RuntimeError):
        await state.clear_fingerprint("home")
    assert state.fingerprint.fingerprint == "value"
    io.fail_on = None
    await state.clear_fingerprint("home")
    assert state.fingerprint.devices == [] and state.fingerprint.fingerprint == ""
    assert state.fingerprint.home_id == "home" and state.fingerprint.valid
    assert state.fingerprint_state == 2 and state.devices


@pytest.mark.asyncio
async def test_fingerprint_init_loaded_identity_and_null_reset_preserve_session_fields() -> (
    None
):
    state, io = setup()
    io.saved["lookup"] = SdkFingerprintRecord("stored", "value", [Device()], True)
    state.pending_fingerprint = "pending"
    state.last_checked_fingerprint = "tmp"
    state.fingerprint_state = 2
    await state.initialize_fingerprint("lookup")
    assert state.fingerprint.home_id == "stored"
    await state.initialize_fingerprint("missing")
    assert state.fingerprint.home_id == "missing"
    assert state.fingerprint.devices == [] and not state.fingerprint.valid
    assert state.fingerprint_state == 2 and state.pending_fingerprint == "pending"
    assert state.last_checked_fingerprint == "tmp"


@pytest.mark.asyncio
async def test_initialization_decoder_exception_propagates_without_fallback() -> None:
    state, io = setup()
    io.use_defaults = True
    io.fail_on = "read_fingerprint"
    with pytest.raises(RuntimeError):
        await state.initialize("home")
    assert len(state.attributes) == 15
    assert state.fingerprint.home_id == ""


@pytest.mark.asyncio
async def test_instances_share_no_identity_catalog_or_cache_state() -> None:
    left, _ = setup([Device()])
    right, other_io = setup([Device()])
    await left.add(left.devices[0])
    left.fingerprint.home_id = "left"
    left.fingerprint_enabled = True
    assert not right.attributes and not right.fingerprint_enabled
    assert right.fingerprint.home_id == ""
    assert other_io.events == []


def test_persisted_ids_are_not_remasked_and_support_uses_raw_function_value() -> None:
    state, _ = setup()
    state.attributes = [
        SdkAttributeRecord(65537, 2, [3], 4, [SdkAttributeUnit([65541])])
    ]
    assert not state.is_known(1, 2, 3)
    assert not state.supports(1, 2, 3, 0, 5)
    state.attributes[0].app_id = 1
    assert not state.supports(1, 2, 3, 0, 5)
    assert state.supports(1, 2, 3, 0, 65541)


@pytest.mark.asyncio
async def test_timer_cancellation_failure_precedes_fingerprint_state_test() -> None:
    state, io = setup()
    state.fingerprint_state = 1
    state.fingerprint = SdkFingerprintRecord("home", "6162636465666768", [], True)
    io.fail_on = SdkMetadataTimer
    with pytest.raises(RuntimeError):
        await state.receive_fingerprint(b"\x02\x42abcdefgh")
    assert state.fingerprint_state == 1
    assert state.last_checked_fingerprint == ""
    assert state.fingerprint.valid


@pytest.mark.asyncio
async def test_receive_state1_does_not_recheck_optional_enable_and_callback_absence() -> (
    None
):
    device = Device()
    state, io = setup()
    state.fingerprint = SdkFingerprintRecord("home", "6162636465666768", [device], True)
    state.fingerprint_state = 1
    state.callback_present = False
    assert not state.fingerprint_enabled
    await state.receive_fingerprint(b"\x02\x42abcdefgh")
    assert state.devices[0] is device and state.fingerprint_state == 3
    assert io.events == [
        SdkMetadataTimer("fingerprint", None),
        ("write_fingerprint", "home"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("queued", [False, True])
async def test_existing_attribute_worker_empty_before_removal_controls_status8(
    queued: bool,
) -> None:
    state, io = setup()
    if queued:
        state.unknown_identities.append("pending")
    await state.attributes_timeout()
    assert state.unknown_identities == []
    assert io.events == (
        [SdkMetadataTimer("attributes", None)]
        if queued
        else [SdkMetadataStatus(8), SdkMetadataTimer("attributes", None)]
    )


@pytest.mark.asyncio
async def test_existing_attribute_worker_continues_next_source_identity() -> None:
    state, io = setup([Device()])
    state.unknown_identities = ["expired", "123_456_789"]
    await state.attributes_timeout()
    assert io.events == [
        SdkMetadataTimer("attributes", None),
        SdkMetadataTimer("attributes", 3000),
        SdkCompositionQuery("010203040506"),
    ]
    assert state.unknown_identities == ["123_456_789"]
