"""Unit149 frozen literal coverage, product gates and safe HA lifecycles."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.kaidi.rize import BATTERY_MODE, RizeController
from custom_components.adjustable_bed.codec import kaidi as codec
from custom_components.adjustable_bed.profiles.kaidi import (
    RIZE_DEFAULT_PARAMETERS,
    RIZE_PRODUCTS,
    RizeProfile,
    add_rize_metadata,
    rize_advertisement,
    validate_rize_profile,
)
from tests.rize_vectors import COMMANDS, VECTORS
from tests.test_isleep import make_controller as make_isleep
from tests.test_isleep import notify, packets

OWN, TARGET = 0xA1B2C3D4, 0x11223344


@pytest.fixture(autouse=True)
def no_protocol_waits(monkeypatch):
    monkeypatch.setattr(RizeProfile, "write_spacing_s", 0)


def make_controller(product=130, *, split=True, ready=True):
    _, co, client = make_isleep()
    co.entry.data.update({const.CONF_PRODUCT_TYPE: product, const.CONF_KAIDI_SOFA_ACU_NO: 1 if split else 2})
    c = RizeController(co)
    if ready:
        c._ready, c._own, c._target = True, OWN, TARGET
    return c, co, client


@pytest.mark.parametrize("row", VECTORS, ids=lambda r: r["id"])
def test_all_225_frozen_vectors_through_codec(row):
    args, builder = row["inputs"], row["builder"]
    if builder == "bed_frame":
        dst = 0 if args["destination"] == -2 else args["destination"]
        actual = codec.control(dst, args["own"], args["opcode"], args.get("parameter", 0), args.get("parameter2", 0))
    elif builder in ("password_check", "enroll", "ping"):
        actual = {"password_check": codec.join, "enroll": codec.enroll, "ping": codec.ping}[builder](**args)
    elif builder == "advertisement":
        ad = rize_advertisement({0xFFFF: bytes.fromhex(args["data"])})
        assert ad is not None
        assert {"product": ad.product_id, "capability_be16": ad.sofa_acu_no, "room": ad.room_id} == row["expected_value"]
        return
    elif builder == "own_address":
        result = codec.parse_notification(bytes.fromhex(args["data"]))
        assert isinstance(result, codec.OwnAddress)
        assert (result.vaddr or codec.BROADCAST) == row["expected_value"]
        return
    elif builder == "power_flag":
        result = codec.parse_notification(bytes.fromhex(args["data"]))
        assert isinstance(result, codec.ControlReply) and result.command == 166
        assert (result.value == 1) == row["expected_value"]
        return
    else:
        assert builder == "artifact_branch"
        stage = "after_action" if args["kind"] == "movement" else "after_completion"
        frames = []
        for call in row["expected_stages"][stage]:
            values = call["args"]
            op, target = values[0], values[-1]
            param = values[1] if call["method"] == "plBleSendProgress" else 0
            frames.append(codec.control(args["address_map"][target], args["own"], op, param).hex())
        assert frames == row["expected_frames"]
        assert len(frames) == row["expected_write_count"]
        return
    assert actual.hex() == row["expected_bytes"]


CORE_ACTIONS = {
    "HEAD": "back", "FOOT": "legs", "ALL": "all", "BACK": "back", "WAIST": "lumbar", "NECK": "neck", "NEW_ALL": "all",
}
ALIASES = {
    "ALL_MOTOR_STOP": "flat", "ZG": "zero_g", "ANTI_SNORE": "anti_snore",
    "MASSAGE_START": "massage_on", "MASSAGE_STOP": "massage_off",
    "HEAD_MASSAGE_SETTING": "head_strength", "LEG_MASSAGE_SETTING": "foot_strength",
    "BED_LIGHT_ON": "light_on", "BED_LIGHT_OFF": "light_off", "BOOK": "book", "LEISURE": "leisure",
    "MASSAGE_MODE_CACEL": "pattern_cancel", "TIME_CACEL": "timer_cancel",
    **{f"MEMORY_POSITION_{letter}": f"save_{i}" for i, letter in enumerate("ABC", 1)},
    **{f"RUN_TO_POSITION_{letter}": f"memory_{i}" for i, letter in enumerate("ABC", 1)},
    **{f"MASSAGE_MODE{i}": f"pattern_{i}" for i in range(1, 4)},
    **{f"MASSAGE_{minutes}": f"timer_{i}" for i, minutes in enumerate((15, 30, 45), 1)},
}
ACTION_VECTORS = {r["action"]: r for r in VECTORS if r["id"].startswith("C-")}
REACHABLE = [r for r in COMMANDS if r["normal_setup_disposition"] == "REACHABLE" and r["opcode"] is not None]


@pytest.mark.parametrize("row", REACHABLE, ids=lambda r: r["action"])
async def test_every_reachable_command_through_control(row):
    symbol = row["action"]
    lane = "left"
    product = 130
    suffix = symbol
    for prefix, selected in (("SEAT_1_2_", "both"), ("SEAT_2_", "right"), ("SEAT_1_", "left")):
        if symbol.startswith(prefix):
            suffix, lane = symbol[len(prefix):], selected
            break
    if suffix.startswith(("BACK_", "WAIST_")):
        product = 132
    elif suffix.startswith(("NECK_", "NEW_ALL_")) or suffix in ("BOOK", "LEISURE", "LEG_MASSAGE_SETTING"):
        product = 138
    elif symbol.startswith(("SEAT_HOT_", "MCU_", "set_current_", "massage_mode4")):
        product = 140
    c, co, client = make_controller(product)
    expected = ACTION_VECTORS[symbol]
    parameter = expected["inputs"]["parameter"]
    with c.side_scope(lane):
        if suffix.endswith(("_UP", "_DOWN", "_STOP")) and suffix not in ("ALL_MOTOR_STOP", "MASSAGE_STOP"):
            axis_name, direction = suffix.rsplit("_", 1)
            axis = CORE_ACTIONS[axis_name]
            if direction == "STOP":
                await c._stop(axis)
            else:
                await c._move(axis, direction == "UP")
        elif symbol == "add_device_success":
            c._pending_ack = True
            await c._flush_pending_ack()
        elif symbol.startswith("set_current_default_position_"):
            preset = next(k for k, v in RIZE_DEFAULT_PARAMETERS.items() if v == parameter)
            await c.program_preset(preset, True)
        elif symbol.startswith("massage_mode4"):
            if symbol.endswith("cancel"):
                c._patterns[0] = 4
            await c.set_pattern(4)
        elif symbol == "MCU_POWER_SUPPLY":
            await c.async_refresh_diagnostics()
        elif symbol.startswith("SEAT_HOT_SENSOR_"):
            spec = next(s for s in c.controller_button_specs if s.key == f"rize_motion_{symbol.rsplit('_', 1)[1].lower()}")
            await spec.press_fn(c)
        else:
            action = ALIASES[suffix]
            if action in ("flat", "zero_g", "anti_snore"):
                await getattr(c, "preset_" + action)()
            elif action in ("book", "leisure"):
                await getattr(c, "preset_" + ("tv" if action == "book" else "lounge"))()
            elif action.startswith("save_"):
                await c.program_memory(int(action[-1]))
            elif action.startswith("memory_"):
                await c.preset_memory(int(action[-1]))
            elif action.startswith("light_"):
                await getattr(c, "lights_" + action[6:])()
            elif action == "massage_on":
                await c.massage_toggle()
            elif action == "massage_off":
                await c.massage_off()
            elif action.endswith("strength"):
                await c.set_massage_intensity(action.split("_")[0], parameter)
            elif action.startswith("pattern_"):
                await c.set_pattern(0 if action.endswith("cancel") else int(action[-1]))
            elif action.startswith("timer_"):
                await c.set_massage_timer(0 if action.endswith("cancel") else [15, 30, 45][int(action[-1])-1])
            else:
                pytest.fail(action)
    assert packets(client)[0].hex() == expected["expected_bytes"]
    assert client.write_gatt_char.call_args.kwargs["response"] is True


@pytest.mark.parametrize("split,side,opcodes", [(False,"both",(122,123,124)), (True,"left",(1,2,3)), (True,"right",(10,11,12)), (True,"both",(19,20,21))])
async def test_clarity_topology_start_and_matching_release(split, side, opcodes):
    c, co, client = make_controller(141, split=split)
    with c.side_scope(side):
        await c.move_back_up()
        await c.move_back_down()
        await c.stop_all()
    assert [p[11] for p in packets(client)][:4] == [opcodes[0],opcodes[2],opcodes[1],opcodes[2]]
    assert packets(client)[4][11] == opcodes[2]
    assert all(p[11] not in (28,29,30) for p in packets(client))
    assert not any(s.key.startswith("rize_all_") for s in c.controller_button_specs)


async def test_strength_resets_before_movement_and_fresh_cancelled_release():
    c, co, client = make_controller(140)
    await c.set_massage_intensity("head", 50)
    co.motor_pulse_delay_ms = 1000
    started = asyncio.Event()
    async def write(_uuid, data, **_kwargs):
        if data[11] == 1:
            started.set()
    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(c.move_back_up())
    await started.wait()
    co.cancel_command.set()
    await task
    assert [p[10:] for p in packets(client)] == [bytes.fromhex("014d3200"), bytes.fromhex("01010000"), bytes.fromhex("01030000")]


async def test_failed_start_still_releases_but_disconnect_never_retargets_cleanup():
    c, co, client = make_controller(130)
    client.write_gatt_char.side_effect = [RuntimeError("write failed"), None]
    with pytest.raises(RuntimeError, match="write failed"):
        await c.move_back_up()
    assert [p[11] for p in packets(client)] == [19,21]
    client.write_gatt_char.reset_mock(side_effect=True)
    async def disconnected(*_args, **_kwargs):
        c.on_disconnect()
    client.write_gatt_char.side_effect = disconnected
    await c.move_back_up()
    assert len(packets(client)) == 1
    await c.stop_all()
    assert len(packets(client)) == 1


async def test_special_parameter_separation_and_confirmation():
    c, co, client = make_controller(140)
    with pytest.raises(ValueError):
        await c.program_preset("book", False)
    assert not packets(client)
    await c.set_pattern(4)
    await c.set_pattern(4)
    await c.program_preset("book", True)
    await c.move_back_up()
    assert [p[10:] for p in packets(client)][:3] == [bytes.fromhex("01a70101"),bytes.fromhex("01a70104"),bytes.fromhex("01a70700")]
    assert packets(client)[3][12:] == bytes(2)
    c.profile = replace(c.profile, product=141)
    with pytest.raises(ValueError):
        await c.set_pattern(4)
    with pytest.raises(ValueError):
        await c.program_preset("zero_g", True)


async def test_power_feedback_gate_and_live_only_polling():
    c, co, client = make_controller(135)
    notify(c, "03ffffffff200102030405a60100")
    assert co.controller_state[BATTERY_MODE] is True
    with pytest.raises(ValueError, match="battery"):
        await c.move_back_up()
    await c.move_back_down()
    await c.async_refresh_diagnostics()
    assert packets(client)[-1][11] == 166
    notify(c, "0301000000200102030405a60000")  # another phone's destination
    assert co.controller_state[BATTERY_MODE] is True
    notify(c, "03ffffffff200102030405a60000")
    assert co.controller_state[BATTERY_MODE] is False
    c.on_disconnect()
    assert co.controller_state[BATTERY_MODE] is None
    client.write_gatt_char.reset_mock()
    await c.async_refresh_diagnostics()
    assert not packets(client)


@pytest.mark.parametrize("product", RIZE_PRODUCTS)
def test_product_axes_and_gates(product):
    c, _, _ = make_controller(product)
    assert tuple(spec.key for spec in c.motor_control_specs) == c.profile.axes
    assert not c.position_number_specs and not c.supports_position_feedback
    assert not c.supports_direct_position_control
    assert c.supports_single_address_pairing == (product in (130,141))
    assert c.memory_slot_count == 3 and c.supports_lights and c.supports_massage
    assert c.pattern_count == (4 if product==140 else 3)
    assert c.diagnostic_poll_interval == (3 if product in (135,136,137,138,140) else None)
    assert c.supports_preset_tv == c.profile.extended
    assert c.massage_intensity_zones == (["head","foot"] if c.profile.extended else ["head"])


async def test_session_auth_roster_zero_and_stale_callbacks():
    c, co, client = make_controller(135, ready=False)
    async def written(_uuid, frame, **_kwargs):
        if frame[0] == 1:
            notify(c, "021600")
            notify(c, "010a00000000")
        elif frame[5] == 254:
            notify(c, "03ffffffffff" + "ffeeddccbbaa" + "00000000")
    client.write_gatt_char.side_effect = written
    await c._ensure_session()
    await c.preset_flat()
    assert c._target == 0 and c._own == codec.BROADCAST
    assert packets(client)[0] == codec.join(c.profile.room)
    assert packets(client)[1] == codec.ping(codec.BROADCAST)
    assert packets(client)[2] == codec.control(0,codec.BROADCAST,28)
    old_callback = client.start_notify.call_args.args[1]
    c.on_disconnect()
    old_callback(MagicMock(),bytearray.fromhex("010a01000000"))
    assert c._own is None


async def test_auth_failure_blocks_commands_and_enrollment_ack_survives():
    c, co, client = make_controller(135, ready=False)
    async def rejected(*_args, **_kwargs):
        notify(c, "021601")
    client.write_gatt_char.side_effect = rejected
    with pytest.raises(ConnectionError,match="authentication"):
        await c.preset_flat()
    assert all(p[0]!=3 for p in packets(client))
    c._ready,c._own,c._target,c._pending_ack = True,OWN,TARGET,True
    client.write_gatt_char.side_effect = RuntimeError("lost ack")
    with pytest.raises(RuntimeError):
        await c._flush_pending_ack()
    assert c._pending_ack
    client.write_gatt_char.side_effect = None
    await c._flush_pending_ack()
    assert not c._pending_ack


def test_scan_gates_setup_seeding_and_field_ownership():
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.setup_questions import setup_profile_for

    payload = bytes.fromhex("ffffc0ff01102700008d000200000000000000")
    ad = rize_advertisement({0xffff:payload})
    assert ad is not None and ad.product_id == 141
    assert rize_advertisement({1:payload}) is None
    assert rize_advertisement({0xffff:payload[:10]}) is None
    assert rize_advertisement({0xffff:payload[:10]+bytes.fromhex("0010")+payload[12:]}) is None
    data = {const.CONF_BED_TYPE:const.BED_TYPE_RIZE}
    seeded = add_rize_metadata(data,{0xffff:payload})
    assert validate_rize_profile(seeded) == RizeProfile(141,10000,2)
    assert const.CONF_KAIDI_ROOM_ID in per_side_profile(const.BED_TYPE_RIZE, None).keys
    assert setup_profile_for(data).questions


async def test_enrollment_uses_rize_product_and_ack_contract():
    from homeassistant.components import bluetooth

    c, co, client = make_controller(140, ready=False)
    # Unprovisioned mode09, KD company, product140 and valid capability bytes.
    ad = bytes.fromhex("ffffc0ff09000000000000444b00008c0002")
    async def written(*_args, **_kwargs):
        notify(c, "020300")
    client.write_gatt_char.side_effect = written
    with patch.object(bluetooth, "async_last_service_info", return_value=MagicMock(manufacturer_data={0xffff: ad})):
        await c.enroll_room()
    assert packets(client) == [codec.enroll(c.profile.room)]
    assert c._pending_ack and c.profile.enroll_wait_s == 30
    co.async_write_app_state.assert_awaited_once()
    co.async_disconnect.assert_awaited_once()


async def test_program_service_rejects_ambiguous_pair_before_admission(hass):
    from homeassistant.core import ServiceCall
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.beds.kaidi import rize_services
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    call = ServiceCall(hass, const.DOMAIN, "rize_program_preset", {"preset": "book", "confirm": True})
    pair = MagicMock(spec=PairedBedCoordinator)
    with patch.object(rize_services, "_call_targets", return_value=[(pair,"both")]), patch.object(rize_services, "_preflight_capability", new_callable=AsyncMock) as preflight:
        with pytest.raises(ServiceValidationError, match="one physical"):
            await rize_services.handle_rize_program_preset(call)
        preflight.assert_not_awaited()


@pytest.mark.parametrize("row", [v for v in VECTORS if v["builder"] == "artifact_branch" and v["inputs"]["kind"] == "default_program"], ids=lambda r:r["id"])
async def test_default_program_uses_explicit_target_with_no_dialog_writes(row):
    """The safe HA action preserves the proven single-write frame, not app globals."""
    c, _, client = make_controller(row["inputs"]["product"])
    preset = {1:"zero_g",3:"anti_snore",4:"book",5:"leisure"}[row["inputs"]["preset"]]
    # Select the observed confirmation target explicitly. Device-list order and
    # a later global target change are not part of the HA service contract.
    writes = row["expected_stages"]["after_completion"]
    if writes:
        target_name = writes[0]["args"][-1]
        c._target = row["inputs"]["address_map"][target_name]
        await c.program_preset(preset, True)
        assert [p.hex() for p in packets(client)] == row["expected_frames"]
    else:
        with pytest.raises(ValueError):
            await c.program_preset(preset, False)
        assert not packets(client)


async def test_coordinator_startup_reaches_unprovisioned_enrollment(
    hass, mock_coordinator_connected, mock_bleak_client,
):
    """A mode09 node can enroll through HA's real connection and command path."""
    from homeassistant.components import bluetooth
    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    address = "AA:BB:CC:DD:EE:FF"
    entry = MockConfigEntry(domain=const.DOMAIN, data={
        CONF_ADDRESS: address, CONF_NAME: "Rize", const.CONF_BED_TYPE: const.BED_TYPE_RIZE,
        const.CONF_PRODUCT_TYPE: 140, const.CONF_KAIDI_ROOM_ID: 10000,
        const.CONF_KAIDI_SOFA_ACU_NO: 2, const.CONF_DISABLE_ANGLE_SENSING: True,
    })
    entry.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, entry)
    ad = bytes.fromhex("ffffc0ff09000000000000444b00008c0002")

    async def written(_uuid, frame, **_kwargs):
        assert frame == codec.enroll(10000), "Startup must not join an unprovisioned node"
        callback = mock_bleak_client.start_notify.call_args.args[1]
        callback(MagicMock(), bytearray.fromhex("020300"))

    mock_bleak_client.write_gatt_char.side_effect = written
    with patch.object(bluetooth, "async_last_service_info", return_value=MagicMock(manufacturer_data={0xffff: ad})):
        assert await co.async_connect()
        controller = co.controller
        assert isinstance(controller, RizeController) and not controller._ready
        assert not packets(mock_bleak_client)
        await co.async_execute_controller_command(lambda c: c.enroll_room())
    assert packets(mock_bleak_client) == [codec.enroll(10000)]
    assert controller._pending_ack
    await co.async_shutdown()


@pytest.mark.parametrize("product", (135,136,137,138,140))
async def test_reading_programming_gate_preserves_voice_recall(product):
    c, _, client = make_controller(product)
    await c.preset_tv()
    assert packets(client) == [codec.control(TARGET, OWN, 158)]
    client.write_gatt_char.reset_mock()
    if product in (135,136,140):
        await c.program_preset("book", True)
        assert packets(client) == [codec.control(TARGET, OWN, 167, 7)]
    else:
        with pytest.raises(ValueError):
            await c.program_preset("book", True)
        assert not packets(client)
        # Other proven default controls on layouts7/8 remain programmable.
        await c.program_preset("leisure", True)
        assert packets(client) == [codec.control(TARGET, OWN, 167, 10)]
