"""Accepted row064 artifact vectors and action lifecycles (no hardware claims)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.isleep import IsleepController
from custom_components.adjustable_bed.codec import kaidi as codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_ISLEEP,
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_PRODUCT_TYPE,
    KAIDI_NOTIFY_CHAR_UUID,
    KAIDI_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.profiles.kaidi import (
    ISLEEP_PRODUCTS,
    add_isleep_metadata,
    isleep_advertisement,
    validate_isleep_profile,
)

ROWS = json.loads((Path(__file__).parent / "fixtures/isleep_row064_commands.json").read_text())
OWN = 0x90ABCDEF
TARGET = 0x12345678
MAC = "AA:BB:CC:DD:EE:FF"


def make_controller(product=129, *, split=False, ready=True):
    client = MagicMock(is_connected=True, services=[])
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.disconnect = AsyncMock()
    co = SimpleNamespace(
        client=client,
        address=MAC,
        name="ISleep",
        cancel_command=asyncio.Event(),
        motor_count=2,
        has_massage=True,
        motor_pulse_count=10,
        motor_pulse_delay_ms=0,
        entry=SimpleNamespace(
            data={
                CONF_PRODUCT_TYPE: product,
                CONF_KAIDI_ROOM_ID: 10001,
                CONF_KAIDI_SOFA_ACU_NO: 1 if split else 2,
            }
        ),
        record_command_trace=MagicMock(),
        handle_controller_state_updates=MagicMock(),
        save_app_state=MagicMock(),
        async_write_app_state=AsyncMock(),
        async_disconnect=AsyncMock(),
        hass=MagicMock(),
    )
    c = IsleepController(co)
    if ready:
        c._ready = True
        c._own, c._target = OWN, TARGET
    return c, co, client


def packets(client):
    return [call.args[1] for call in client.write_gatt_char.call_args_list]


def notify(c, frame):
    c._notification(MagicMock(), bytearray.fromhex(frame))


@pytest.mark.parametrize("row", ROWS, ids=lambda r: f"C{r['row']:03}")
async def test_all_108_ui_rows_each_product_and_lane(row):
    """Every rendered action, gated by product and side, through public methods."""
    for product in row["products"]:
        c, co, client = make_controller(product, split=row["lane"] != 0 or product in (130, 143))
        c._parameter = 50
        with c.side_scope(("left", "right", "both")[row["lane"]]):
            action = row["action"]
            if action.endswith(("_up", "_down", "_stop")):
                axis, direction = action.rsplit("_", 1)
                if axis == "all":
                    if direction == "stop":
                        await c._stop("all")
                    else:
                        await c._move("all", direction == "up")
                else:
                    await getattr(c, f"move_{axis}_{direction}")()
            elif action.startswith("save_"):
                await c.program_memory(int(action[-1]))
            elif action.startswith("memory_"):
                await c.preset_memory(int(action[-1]))
            elif action in ("flat", "zero_g", "anti_snore"):
                await getattr(c, "preset_" + action)()
            elif action.startswith("light_"):
                await getattr(c, "lights_" + action[6:])()
            elif action == "massage_on":
                await c.massage_toggle()
            elif action == "massage_off":
                await c.massage_off()
            elif action.endswith("_strength"):
                await c.set_massage_intensity(action.split("_")[0], 50)
            elif action.startswith("pattern_"):
                await c.set_pattern(0 if action == "pattern_cancel" else int(action[-1]))
            elif action.startswith("timer_"):
                await c.set_massage_timer(
                    0 if action == "timer_cancel" else c.massage_timer_options[int(action[-1]) - 1]
                )
            else:
                pytest.fail(action)
        expected = bytes.fromhex("037856341220efcdab9001") + bytes([row["opcode"], 50, 0])
        assert packets(client)[0] == expected
        assert client.write_gatt_char.call_args_list[0].kwargs["response"] is True
        if action.endswith(("_up", "_down")):
            assert len(packets(client)) == 2
            assert packets(client)[1][11] == row["opcode"] + (2 if action.endswith("_up") else 1)
        else:
            assert len(packets(client)) == 1


@pytest.mark.parametrize(
    "product,axes",
    [
        (129, ("back", "legs")),
        (130, ("back", "legs")),
        (131, ("back", "legs", "head")),
        (132, ("back", "legs", "head", "lumbar")),
        (133, ("back", "legs", "head")),
        (134, ("back", "legs", "head", "lumbar")),
        (142, ("back", "legs")),
        (143, ("back", "legs")),
    ],
)
def test_exact_product_capabilities(product, axes):
    c, _, _ = make_controller(product)
    assert tuple(s.key for s in c.motor_control_specs) == axes
    assert c.position_number_specs == ()
    assert not c.supports_direct_position_control
    assert not c.supports_position_feedback
    assert not c.supports_preset_tv and not c.supports_preset_lounge
    assert c.memory_slot_count == 3
    assert c.supports_lights and c.supports_massage
    assert c.massage_intensity_zones == (["head"] if product == 143 else ["head", "foot"])
    assert c.massage_timer_options == ([10, 20, 30] if product == 143 else [15, 30, 45])


@pytest.mark.parametrize("product", ISLEEP_PRODUCTS)
@pytest.mark.parametrize("actuators", [0, 1, 2, 3, 256])
def test_exact_role1_side_gate(product, actuators):
    p = validate_isleep_profile(
        {CONF_PRODUCT_TYPE: product, CONF_KAIDI_ROOM_ID: 10000, CONF_KAIDI_SOFA_ACU_NO: actuators}
    )
    assert p.split == (product in (130, 143) and actuators != 2)


async def test_strength_retained_into_move_release_and_preset():
    c, _, client = make_controller()
    await c.set_massage_intensity("head", 50)
    await c.move_back_up()
    await c.preset_flat()
    assert [x.hex() for x in packets(client)] == [
        "037856341220efcdab90014d3200",
        "037856341220efcdab9001013200",
        "037856341220efcdab9001033200",
        "037856341220efcdab90011c3200",
    ]


async def test_cancelled_hold_releases_same_lane_and_original_target():
    c, co, client = make_controller(130, split=True)
    co.motor_pulse_delay_ms = 100
    wrote = asyncio.Event()

    async def write(_uuid, data, **kwargs):
        if data[11] == 10:
            wrote.set()

    client.write_gatt_char.side_effect = write
    with c.side_scope("right"):
        task = asyncio.create_task(c.move_back_up())
    await wrote.wait()
    c._target = 0x01020304
    co.cancel_command.set()
    await task
    assert [p[11] for p in packets(client)] == [10, 12]
    assert packets(client)[1][1:5] == bytes.fromhex("78563412")


async def test_task_cancellation_and_write_failure_both_release():
    for failure in ("cancel", "bleak"):
        c, co, client = make_controller()
        co.motor_pulse_delay_ms = 100
        wrote = asyncio.Event()

        async def write(_uuid, data, *, wrote=wrote, failure=failure, **kwargs):
            if data[11] == 1:
                wrote.set()
                if failure == "bleak":
                    raise BleakError("failed write")

        client.write_gatt_char.side_effect = write
        task = asyncio.create_task(c.move_back_up())
        await wrote.wait()
        if failure == "cancel":
            task.cancel()
        with pytest.raises(asyncio.CancelledError if failure == "cancel" else BleakError):
            await task
        assert [p[11] for p in packets(client)] == [1, 3]


async def test_disconnect_during_hold_never_reconnects_to_deliver_release():
    c, co, client = make_controller()

    async def write(_uuid, data, **kwargs):
        c.on_disconnect()
        client.is_connected = False

    client.write_gatt_char.side_effect = write
    await c.move_back_up()
    assert len(packets(client)) == 1
    await c.stop_all()
    assert len(packets(client)) == 1
    assert c._own is None and c._target is None


async def test_stop_uses_axis_releases_never_flat():
    c, co, client = make_controller(132)
    co.cancel_command.set()
    await c.stop_all()
    assert [p[11] for p in packets(client)] == [124, 6, 3, 133, 9]
    assert not ({28, 29, 30} & {p[11] for p in packets(client)})


async def test_invalid_actions_and_cancelled_admission_write_nothing():
    c, co, client = make_controller(143)
    for method, args in [
        (c.set_massage_intensity, ("foot", 50)),
        (c.set_massage_intensity, ("head", 101)),
        (c.program_memory, (4,)),
        (c.preset_memory, (0,)),
        (c.set_massage_timer, (45,)),
        (c.set_pattern, (4,)),
        (c.move_head_up, ()),
    ]:
        with pytest.raises(ValueError):
            await method(*args)
    co.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await c.massage_toggle()
    assert not c._massage[0]
    assert packets(client) == []


async def test_pattern_and_timer_toggle_cancel_are_distinct_from_massage_off():
    c, _, client = make_controller(143)
    await c.set_pattern(2)
    await c.set_pattern(2)
    await c.set_massage_timer(10)
    await c.set_massage_timer(10)
    await c.set_massage_timer(20)
    await c.set_massage_timer(0)
    assert [p[11] for p in packets(client)] == [110, 116, 83, 119, 84, 119]


async def test_exact_auth_ping_and_current_mac_roster():
    c, _, client = make_controller(ready=False)

    async def write(uuid, data, **kwargs):
        if data[:2] == b"\x01\x16":
            notify(c, "021600")
            notify(c, "010aefcdab90")
        elif data[5] == 0xFE:
            notify(c, "0300000000ff01020304050678563412")
            assert c._target is None
            notify(c, "0300000000ffffeeddccbbaa78563412")

    client.write_gatt_char.side_effect = write
    await c.lights_on()
    assert [p.hex() for p in packets(client)] == [
        "0116011127000031313232",
        "03fffffffffeefcdab90",
        "037856341220efcdab90015c0000",
    ]
    assert client.start_notify.call_args.args[0] == KAIDI_NOTIFY_CHAR_UUID
    assert all(
        call.args[0] == KAIDI_WRITE_CHAR_UUID for call in client.write_gatt_char.call_args_list
    )


@pytest.mark.parametrize("status", [1, 255])
async def test_auth_rejection_never_writes_control(status):
    c, _, client = make_controller(ready=False)

    async def write(uuid, data, **kwargs):
        notify(c, f"0216{status:02x}")

    client.write_gatt_char.side_effect = write
    with pytest.raises(ConnectionError):
        await c.preset_flat()
    assert len(packets(client)) == 1 and not c._ready


async def test_timeout_and_disconnect_unblock_without_controls():
    c, _, client = make_controller(ready=False)

    async def write(uuid, data, **kwargs):
        c.on_disconnect()

    client.write_gatt_char.side_effect = write
    with pytest.raises(ConnectionError):
        await c.preset_flat()
    assert len(packets(client)) == 1
    c, _, client = make_controller(ready=False)
    with patch.object(c, "_wait", AsyncMock(side_effect=TimeoutError)), pytest.raises(TimeoutError):
        await c.preset_flat()
    assert len(packets(client)) == 1


def test_parser_sentinels_lengths_and_no_false_telemetry():
    c, _, _ = make_controller(ready=False)
    for frame in ["", "02", "0216", "010a", "010a000000", "0300000000", "0300000000ffffeeddccbbaa"]:
        notify(c, frame)
    assert c._own is None and c._target is None and not c._auth.is_set()
    notify(c, "010a00000000")
    assert c._own == 0xFFFFFFFF
    notify(c, "0300000000ffffeeddccbbaa00000000")
    assert c._target == 0
    notify(c, "0300000000ffffeeddccbbaafeffffff")
    assert c._target == 0
    notify(c, "0300000000ffffeeddccbbaaffffffff")
    assert c._target == 0xFFFFFFFF
    notify(c, "01020000000000000300")
    assert c._target is None
    for channel in ["20", "2f", "23", "24", "25", "28", "12"]:
        notify(c, "0300000000" + channel + "0000000080000000000000000000")
    assert c._target is None and not c.supports_position_feedback


def manufacturer(mode, product=129, actuators=2):
    payload = bytearray.fromhex("ffffc0ff") + bytearray(24)
    payload[4] = mode
    payload[5:9] = (10001).to_bytes(4, "little")
    if mode == 1:
        payload[9] = product
        payload[10:12] = actuators.to_bytes(2, "big")
    elif mode == 9:
        payload[11:13] = bytes.fromhex("444b")
        payload[15] = product
        payload[16:18] = actuators.to_bytes(2, "big")
    else:
        payload[17] = product
        payload[18:20] = actuators.to_bytes(2, "big")
        payload[20] = 0xA1
        payload[21:25] = TARGET.to_bytes(4, "little")
    return {0xFFFF: bytes(payload[2:])}


@pytest.mark.parametrize("mode", [1, 2, 9])
@pytest.mark.parametrize("product", ISLEEP_PRODUCTS)
def test_advertisement_and_explicit_room_seed(mode, product):
    md = manufacturer(mode, product)
    ad = isleep_advertisement(md)
    assert ad and ad.product_id == product and ad.sofa_acu_no == 2
    seed = add_isleep_metadata({}, md)
    assert seed[CONF_PRODUCT_TYPE] == product
    assert seed.get(CONF_KAIDI_ROOM_ID) == (None if mode == 9 else 10001)
    assert add_isleep_metadata({CONF_KAIDI_ROOM_ID: 10200}, md)[CONF_KAIDI_ROOM_ID] == 10200


def test_discovery_gates_and_truncated_mode2_alternate():
    assert isleep_advertisement(manufacturer(1, 135)) is None
    assert isleep_advertisement(manufacturer(1, 129, 16)) is None
    assert isleep_advertisement({123: next(iter(manufacturer(1).values()))}) is None
    bad = bytearray(manufacturer(9)[0xFFFF])
    bad[9] = 0
    assert isleep_advertisement({0xFFFF: bytes(bad)}) is None
    for n in range(23):
        assert isleep_advertisement({0xFFFF: manufacturer(2)[0xFFFF][:n]}) is None
    alt = bytearray(manufacturer(2)[0xFFFF])
    alt[18] = 0
    alt[23] = 132
    alt[24:26] = b"\0\2"
    assert isleep_advertisement({0xFFFF: bytes(alt)}).product_id == 132


@pytest.mark.parametrize(
    "room,auth,enroll",
    [
        (10001, "0116011127000031313232", "0103112700003131323200000000"),
        (10100, "0116017427000031313232", "0103742700003131323200000000"),
        (-1, "011601ffffffff31313232", "0103ffffffff3131323200000000"),
    ],
)
def test_exact_room_builders(room, auth, enroll):
    assert codec.join(room).hex() == auth
    assert codec.enroll(room).hex() == enroll
    assert codec.control(TARGET, OWN, 1, 0).hex() == "037856341220efcdab9001010000"


async def test_enrollment_is_explicit_fresh_only_and_ack_is_durable():
    c, co, client = make_controller(ready=False)

    async def write(uuid, data, **kwargs):
        notify(c, "020300")

    client.write_gatt_char.side_effect = write
    info = SimpleNamespace(manufacturer_data=manufacturer(9))
    with patch("homeassistant.components.bluetooth.async_last_service_info", return_value=info):
        await c.enroll_room()
    assert packets(client) == [bytes.fromhex("0103112700003131323200000000")]
    co.async_disconnect.assert_awaited_once()
    assert co.async_write_app_state.call_args.args[1]["pending_ack"] is True
    assert co.async_write_app_state.call_args.args[1]["room"] == 10001
    fresh, _, _ = make_controller()
    fresh.restore_persisted_app_state(c.persisted_app_state)
    assert fresh._pending_ack
    fresh.restore_persisted_app_state({"pending_ack": True, "room": 1})
    assert not fresh._pending_ack


@pytest.mark.parametrize("mode", [1, 2])
async def test_enrollment_never_resets_foreign_or_same_room(mode):
    c, _, client = make_controller(ready=False)
    with (
        patch(
            "homeassistant.components.bluetooth.async_last_service_info",
            return_value=SimpleNamespace(manufacturer_data=manufacturer(mode)),
        ),
        pytest.raises(ValueError),
    ):
        await c.enroll_room()
    assert packets(client) == []


async def test_pending_ack_requires_matching_live_roster_and_successful_write():
    c, co, client = make_controller(ready=False)
    c.restore_persisted_app_state({"pending_ack": True, "room": 10001})

    async def write(uuid, data, **kwargs):
        if data[:2] == b"\x01\x16":
            notify(c, "021600")
            notify(c, "010a00000000")
        elif data[5] == 0xFE:
            notify(c, "0300000000ffffeeddccbbaa00000000")

    client.write_gatt_char.side_effect = write
    await c.preset_flat()
    assert [p.hex() for p in packets(client)][2:] == [
        "030000000020ffffffff01450000",
        "030000000020ffffffff011c0000",
    ]
    assert not c._pending_ack
    assert co.async_write_app_state.call_args.args[1]["pending_ack"] is False


async def test_failed_ack_is_retried_on_the_established_session():
    c, co, client = make_controller(ready=False)
    c.restore_persisted_app_state({"pending_ack": True, "room": 10001})
    ack = "030000000020ffffffff01450000"
    failed = []

    async def write(uuid, data, **kwargs):
        if data[:2] == b"\x01\x16":
            notify(c, "021600")
            notify(c, "010a00000000")
        elif data[5] == 0xFE:
            notify(c, "0300000000ffffeeddccbbaa00000000")
        elif data.hex() == ack and not failed:
            failed.append(data)
            raise BleakError("ack write failed")

    client.write_gatt_char.side_effect = write
    with pytest.raises(BleakError):
        await c.preset_flat()
    assert c._pending_ack
    client.write_gatt_char.reset_mock()

    await c.preset_flat()  # same connection: no re-authentication or roster query
    assert [p.hex() for p in packets(client)] == [ack, "030000000020ffffffff011c0000"]
    assert not c._pending_ack
    assert co.async_write_app_state.call_args.args[1]["pending_ack"] is False


async def test_setup_and_options_preserve_explicit_profile(hass):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        AdjustableBedOptionsFlow,
    )
    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_HAS_MASSAGE,
        DOMAIN,
    )

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._manual_data = {CONF_ADDRESS: MAC, CONF_BED_TYPE: BED_TYPE_ISLEEP}
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    with patch(
        "homeassistant.components.bluetooth.async_last_service_info",
        return_value=SimpleNamespace(manufacturer_data=manufacturer(1, 132)),
    ):
        form = await flow.async_step_profile_questions()
        assert form["step_id"] == "profile_questions"
        assert form["data_schema"] is not None
        assert (
            form["data_schema"](
                {CONF_PRODUCT_TYPE: "132", CONF_KAIDI_ROOM_ID: 10001, CONF_KAIDI_SOFA_ACU_NO: 2}
            )[CONF_PRODUCT_TYPE]
            == 132
        )
        await flow.async_step_profile_questions(
            {CONF_PRODUCT_TYPE: "132", CONF_KAIDI_ROOM_ID: 10200, CONF_KAIDI_SOFA_ACU_NO: 2}
        )
    data = flow._finish_with_verify.call_args.args[0]
    assert data[CONF_PRODUCT_TYPE] == 132 and data[CONF_KAIDI_ROOM_ID] == 10200
    assert data[CONF_HAS_MASSAGE] and data[CONF_DISABLE_ANGLE_SENSING]
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=4)
    entry.add_to_hass(hass)
    options = AdjustableBedOptionsFlow(entry)
    options.hass = hass
    # Shared profile keys survive options cleanup and do not spill into unrelated bed types.
    updated = dict(data)
    options._remove_irrelevant_bed_settings(updated, BED_TYPE_ISLEEP)
    assert updated[CONF_PRODUCT_TYPE] == 132
    assert updated[CONF_KAIDI_ROOM_ID] == 10200


def test_profile_ownership_and_app_search():
    from custom_components.adjustable_bed.app_profiles import (
        hidden_generic_fields,
        per_side_profile,
    )
    from custom_components.adjustable_bed.config_flow import _per_side_refusal
    from custom_components.adjustable_bed.const import CONF_HAS_MASSAGE, CONF_MOTOR_COUNT
    from custom_components.adjustable_bed.detection import get_bed_type_options

    assert any(
        option["value"] == BED_TYPE_ISLEEP and "ISleep" in option["label"]
        for option in get_bed_type_options()
    )
    assert {CONF_MOTOR_COUNT, CONF_HAS_MASSAGE} <= hidden_generic_fields(BED_TYPE_ISLEEP, None)
    assert {CONF_PRODUCT_TYPE, CONF_KAIDI_ROOM_ID, CONF_KAIDI_SOFA_ACU_NO} <= per_side_profile(
        BED_TYPE_ISLEEP, None
    ).keys
    assert _per_side_refusal(
        (BED_TYPE_ISLEEP, None), [(BED_TYPE_ISLEEP, None)] * 2, {CONF_KAIDI_ROOM_ID: 1}
    ) == (CONF_KAIDI_ROOM_ID, "ISleep")


async def test_enrollment_failure_and_timeout_never_save_success():
    for outcome in ("rejected", "timeout"):
        c, co, client = make_controller(ready=False)

        async def write(uuid, data, *, c=c, **kwargs):
            notify(c, "020301")

        client.write_gatt_char.side_effect = write
        with patch(
            "homeassistant.components.bluetooth.async_last_service_info",
            return_value=SimpleNamespace(manufacturer_data=manufacturer(9)),
        ):
            if outcome == "timeout":
                c._wait = AsyncMock(side_effect=TimeoutError)
            with pytest.raises((ConnectionError, TimeoutError)):
                await c.enroll_room()
        co.async_disconnect.assert_awaited_once()
        co.async_write_app_state.assert_not_awaited()
        assert not c._pending_ack


async def test_saved_intent_survives_reconnect_without_restoring_live_addresses():
    c, _, _ = make_controller(130, split=True)
    with c.side_scope("both"):
        await c.massage_toggle()
    with c.side_scope("both"):
        await c.set_massage_intensity("head", 50)
    state = c.persisted_app_state
    with c.side_scope("right"):
        await c.set_massage_intensity("head", 60)
    assert state["strengths"][1]["head"] == 50  # store snapshots cannot alias mutable state
    new, _, _ = make_controller(130, split=True, ready=False)
    new.restore_persisted_app_state(state)
    assert new._own is None and new._target is None and not new._ready
    assert new._parameter == 50
    with new.side_scope("left"):
        assert new.get_massage_state()["head_active"]
    with new.side_scope("right"):
        assert new.get_massage_state()["head_intensity"] == 50
    new.restore_persisted_app_state({})
    assert new._parameter == 0 and not new._massage[0]


async def test_old_notification_callback_cannot_poison_reconnected_session():
    c, _, client = make_controller(ready=False)
    await c.start_notify()
    callback = client.start_notify.call_args.args[1]
    c.on_disconnect()
    callback(MagicMock(), bytearray.fromhex("010aefcdab90"))
    assert c._own is None


@pytest.mark.parametrize("product,descriptor", [(130, 2), (129, 1)])
async def test_single_address_options_reject_losing_split_controls(hass, product, descriptor):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_PAIR_ID,
        CONF_PAIR_MODE,
        DOMAIN,
        PAIR_MODE_SINGLE_ADDRESS,
    )

    data = {
        CONF_ADDRESS: MAC,
        CONF_BED_TYPE: BED_TYPE_ISLEEP,
        CONF_PRODUCT_TYPE: 130,
        CONF_KAIDI_ROOM_ID: 10001,
        CONF_KAIDI_SOFA_ACU_NO: 1,
        CONF_PAIR_ID: "pair_isleep",
        CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=4)
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    result = await flow.async_step_settings(
        {CONF_PRODUCT_TYPE: str(product), CONF_KAIDI_SOFA_ACU_NO: descriptor}
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "isleep_unpair_first"}
    assert dict(entry.data) == data


async def test_massage_entity_state_survives_idle_disconnect_and_reconnect_per_side(hass):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_HAS_MASSAGE, DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.number import (
        MASSAGE_NUMBER_DESCRIPTIONS,
        AdjustableBedMassageNumber,
    )
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.select import (
        MASSAGE_TIMER_DESCRIPTION,
        AdjustableBedMassageTimerSelect,
    )

    data = {
        CONF_ADDRESS: MAC,
        CONF_BED_TYPE: BED_TYPE_ISLEEP,
        CONF_PRODUCT_TYPE: 130,
        CONF_KAIDI_ROOM_ID: 10001,
        CONF_KAIDI_SOFA_ACU_NO: 1,
        CONF_HAS_MASSAGE: True,
    }
    data.update({"pair_id": "pair_isleep", "pair_mode": "single_address"})
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=4)
    entry.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, entry)
    _, _, client = make_controller()
    co._client = client
    c = IsleepController(co)
    co._controller = c
    c._own, c._target, c._ready = OWN, TARGET, True
    await co._async_restore_app_state(c)
    pair = SingleAddressPairedCoordinator(hass, entry, co)
    left, right = pair._children["left"], pair._children["right"]
    lt = AdjustableBedMassageTimerSelect(left, MASSAGE_TIMER_DESCRIPTION, [15, 30, 45])
    rt = AdjustableBedMassageTimerSelect(right, MASSAGE_TIMER_DESCRIPTION, [15, 30, 45])
    head = next(d for d in MASSAGE_NUMBER_DESCRIPTIONS if d.massage_zone == "head")
    ln, rn = AdjustableBedMassageNumber(left, head), AdjustableBedMassageNumber(right, head)
    await lt.async_select_option("15 min")
    await rt.async_select_option("30 min")
    await ln.async_set_native_value(40)
    await rn.async_set_native_value(60)
    assert (lt.current_option, rt.current_option, ln.native_value, rn.native_value) == (
        "15 min",
        "30 min",
        40,
        60,
    )
    co._intentional_disconnect = True
    co._on_disconnect(client)
    assert co.controller is None
    assert (lt.current_option, rt.current_option, ln.native_value, rn.native_value) == (
        "15 min",
        "30 min",
        40,
        60,
    )
    # Restore the real coordinator's saved intent into its next connection controller.
    co._client = client
    restored = IsleepController(co)
    co._controller = restored
    await co._async_restore_app_state(restored)
    restored._own, restored._target, restored._ready = OWN, TARGET, True
    client.write_gatt_char.reset_mock()
    await lt.async_select_option("45 min")
    assert packets(client)[0][11] == 85
    assert (lt.current_option, rt.current_option, ln.native_value, rn.native_value) == (
        "45 min",
        "30 min",
        40,
        60,
    )
    await lt.async_select_option("45 min")
    assert packets(client)[1][11] == 119
    assert lt.current_option == "Off" and rt.current_option == "30 min"
    await pair.async_shutdown()


async def test_configure_rejects_an_out_of_range_room(hass, enable_custom_integrations):
    """The room field itself rejects a room outside the signed 32-bit range."""
    from homeassistant.const import CONF_ADDRESS
    from homeassistant.data_entry_flow import InvalidData
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import CONF_BED_TYPE, DOMAIN

    data = {
        CONF_ADDRESS: MAC,
        CONF_BED_TYPE: BED_TYPE_ISLEEP,
        CONF_PRODUCT_TYPE: 129,
        CONF_KAIDI_ROOM_ID: 10000,
        CONF_KAIDI_SOFA_ACU_NO: 2,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "settings"}
    )
    with pytest.raises(InvalidData) as error:
        await hass.config_entries.options.async_configure(
            form["flow_id"], {**form["data_schema"]({}), CONF_KAIDI_ROOM_ID: 2**31}
        )
    assert CONF_KAIDI_ROOM_ID in error.value.schema_errors
    assert dict(entry.data) == data
