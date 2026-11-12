"""Full row084 bed surface, session ownership and actual caller lifecycles."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.kaidi.comfy import LOCK_STATUS, ComfyController
from custom_components.adjustable_bed.codec import kaidi as codec
from custom_components.adjustable_bed.profiles.comfy import (
    COMFY_ACTIONS,
    ComfyProfile,
    comfy_advertisement,
    validate_comfy_profile,
    wire_target,
)
from tests.test_comfy_vectors import VECTORS
from tests.test_isleep import make_controller as make_isleep
from tests.test_isleep import notify, packets


@pytest.fixture(autouse=True)
def no_real_timers(monkeypatch):
    monkeypatch.setattr(ComfyProfile, "write_spacing_s", 0)
    monkeypatch.setattr(ComfyProfile, "first_write_s", 0)
    monkeypatch.setattr(ComfyProfile, "memory_repeat_s", 0.001)
    monkeypatch.setattr(ComfyProfile, "join_timeout_s", 0.03)


def make_controller(app="komfyd", product=130, *, ready=True):
    _, co, client = make_isleep()
    co.entry.async_on_unload = MagicMock()
    co.entry.data.update(
        {
            const.CONF_BED_TYPE: app,
            const.CONF_PRODUCT_TYPE: product,
            const.CONF_KAIDI_SOFA_ACU_NO: 0xF322,
        }
    )
    c = ComfyController(co)
    if ready:
        c._ready, c._own, c._target = True, 0x11223344, 0x12345678
    return c, co, client


@pytest.mark.parametrize("app", ("komfyd", "comfyds"))
@pytest.mark.parametrize("lane", (0, 1, 2))
async def test_every_reachable_opcode_at_real_controller_callers(app, lane):
    c, co, client = make_controller(app)
    own = VECTORS[app][0]["inputs"]["own"]
    c._own = own
    with c.side_scope(("left", "right", "both")[lane]):
        for action, codes in c.profile.commands.items():
            client.write_gatt_char.reset_mock()
            c._lock_status = "unlocked"
            if action.startswith("memory_"):

                async def ack(*_args, **_kwargs):
                    notify(c, "0300000000200000000001290000")

                client.write_gatt_char.side_effect = ack
                await c.preset_memory(int(action[-1]))
                client.write_gatt_char.side_effect = None
            elif action.startswith("save_"):
                await c.program_memory(int(action[-1]))
            elif action.startswith("timer_") and action[6:].isdigit():
                await c.select_timer(int(action[6:]))
            elif action in COMFY_ACTIONS:
                await c.control(action)
            elif action == "flat":
                await c.preset_flat()
            elif action in ("light_on", "light_off"):
                await (c.lights_on() if action == "light_on" else c.lights_off())
            elif action == "preset_stop":
                # Only a preset gesture owns this release, not a global STOP.
                await c.preset_flat()
                assert packets(client)[-1][11] == codes[lane]
                continue
            else:
                axis, direction = action.rsplit("_", 1)
                public_axis = "back" if axis == "head" else axis
                await getattr(c, f"move_{public_axis}_{direction}")()
            assert packets(client)[0] == codec.control(c._target, own, codes[lane]), action
            if action.endswith(("_up", "_down")) or action in ("flat", "zero"):
                assert len(packets(client)) == 2
                release = c._opcode(
                    "preset_stop"
                    if action in ("flat", "zero")
                    else action.rsplit("_", 1)[0] + "_stop"
                )
                assert packets(client)[-1][11] == release
    c._stop_countdown()


@pytest.mark.parametrize("app", ("komfyd", "comfyds"))
@pytest.mark.parametrize("raw", range(256))
def test_full_raw_type_inventory(app, raw):
    data = bytearray.fromhex("ffffc0ff0178563412811322000000000000")
    data[9] = raw
    ad = comfy_advertisement({0xFFFF: bytes(data)})
    assert (ad is not None) == (raw in (129, 130, 131))
    if ad:
        assert ad.product_id == (129 if raw == 131 else raw)
        profile = validate_comfy_profile(
            {
                const.CONF_BED_TYPE: app,
                const.CONF_PRODUCT_TYPE: raw,
                const.CONF_KAIDI_ROOM_ID: -1,
                const.CONF_KAIDI_SOFA_ACU_NO: 0xF322,
            }
        )
        assert profile.raw_type == raw and profile.product == ad.product_id
        assert profile.axes == ("back", "legs", "lumbar")
        assert profile.split == (raw == 130)


@pytest.mark.parametrize("app", ("komfyd", "comfyds"))
@pytest.mark.parametrize("raw", (129, 130, 131))
@pytest.mark.parametrize("selection", (None, 0, 1, 2))
def test_feature_side_domains(app, raw, selection):
    c, _, _ = make_controller(app, raw)
    c._selected_side = selection
    normal = {0: 0, 1: 2, 2: 1}.get(selection, 1)
    assert c._lane == (normal if raw == 130 else 0)
    assert (
        c._feature_lane("light") == (2 if selection is None else normal)
        if raw == 130
        else c._feature_lane("light") == 0
    )
    assert (
        c._feature_lane("timer") == (0 if selection is None else normal)
        if raw == 130
        else c._feature_lane("timer") == 0
    )
    assert c._feature_lane("lock") == (2 if selection is None else normal)
    assert c._opcode("memory_4") == 44 and c._opcode("save_4") == 40


@pytest.mark.parametrize("target", (-2, -1, -(2**31), 2**31 - 1))
async def test_signed_ordinary_and_direct_helper_boundaries(target):
    c, co, client = make_controller()
    c._target = target
    if target > 0 or target == -2:
        await c.move_back_up()
    else:
        with pytest.raises(ValueError):
            await c.move_back_up()
    await c.control("query")
    await c.program_memory(4)
    assert packets(client)[-1] == codec.control(wire_target(target), c._own, 40)
    c._target = 0
    with pytest.raises(ValueError):
        await c.control("query")


async def test_release_captures_side_source_target_and_ignores_new_lock():
    c, co, client = make_controller()
    co.motor_pulse_count, co.motor_pulse_delay_ms = 1, 10000
    wrote = asyncio.Event()

    async def write(*_args, **_kwargs):
        wrote.set()

    client.write_gatt_char.side_effect = write
    with c.side_scope("right"):
        task = asyncio.create_task(c.move_back_up())
    await wrote.wait()
    c._own, c._target, c._selected_side, c._lock_status = 8, -2, 1, "other"
    co.cancel_command.set()
    await task
    assert [frame[11] for frame in packets(client)] == [10, 12]
    assert packets(client)[-1][1:10] == packets(client)[0][1:10]


async def test_disconnected_gesture_never_releases_into_new_session():
    c, co, client = make_controller()
    co.motor_pulse_delay_ms = 1000

    async def disconnect(*_args, **_kwargs):
        c.on_disconnect()
        co.cancel_command.set()

    client.write_gatt_char.side_effect = disconnect
    await c.move_back_up()
    assert [p[11] for p in packets(client)] == [1]


@pytest.mark.parametrize("ack", range(37, 61))
async def test_full_ack_domain_ends_memory_without_stop(ack):
    c, _, client = make_controller()

    async def reply(*_args, **_kwargs):
        notify(c, codec.control(9, 8, ack).hex())

    client.write_gatt_char.side_effect = reply
    await c.preset_memory(4)
    assert [p[11] for p in packets(client)] == [44]


async def test_recall_uses_live_future_addresses_but_stops_on_session_loss():
    c, _, client = make_controller("comfyds")

    async def change(*_args, **_kwargs):
        if client.write_gatt_char.call_count == 1:
            c._own, c._target = 8, -(2**31)
        else:
            c.on_disconnect()

    client.write_gatt_char.side_effect = change
    await c.preset_memory(1)
    assert packets(client) == [
        codec.control(0x12345678, 0x11223344, 41),
        codec.control(-(2**31), 8, 41),
    ]
    c._ready, c._target = True, 10
    await c.control("query")
    assert len(packets(client)) == 3  # no surviving Android callback


@pytest.mark.parametrize("app", ("komfyd", "comfyds"))
async def test_auth_source_ping_query_and_reconnect(app):
    c, _, client = make_controller(app, ready=False)

    async def respond(_uuid, frame, **_kwargs):
        if frame[:3] == b"\x01\x16\x01":
            notify(c, "021600")
            notify(c, "010a44332211")
        elif frame[:6] == bytes.fromhex("03fffffffffe"):
            notify(c, "0300000000ffffeeddccbbaa00000000")

    client.write_gatt_char.side_effect = respond
    await c.async_after_connect(MagicMock())
    assert [p.hex() for p in packets(client)] == [
        codec.join(c.profile.room).hex(),
        codec.ping(0x11223344).hex(),
        codec.control(0, 0x11223344, 70).hex(),
    ]
    assert c._target == -2
    c.on_disconnect()
    assert c._target is None and not c._ready
    assert c._own == (0x11223344 if app == "comfyds" else None)


@pytest.mark.parametrize("owner", range(256))
def test_unsigned_lock_ownership_and_exact_payload(owner):
    c, _, _ = make_controller()
    notify(c, codec.control(0, 8, 61, owner).hex())
    assert c._lock_owner == owner
    notify(c, codec.control(0, 8, 70, owner).hex())
    assert c._lock_status == ("local" if owner else "unlocked")
    notify(c, codec.control(0, 8, 70, (owner + 1) % 256).hex())
    assert c._lock_status == ("unlocked" if owner == 255 else "other")
    status = c._lock_status
    notify(c, codec.control(0, 8, 70, 0).hex() + "00")
    assert c._lock_status == status


async def test_restore_local_side_timer_light_without_wire_or_recall():
    c, co, client = make_controller("comfyds")
    c._select_side("right")
    await c.lights_on()
    await c.select_timer(30)
    await c.control("timer_start")
    saved = c.persisted_app_state
    other, other_co, other_client = make_controller("comfyds", ready=False)
    other.restore_persisted_app_state(saved)
    assert other._selected_side == 2 and other._led[1]
    assert other._timer_minutes[1] == 30 and other._timer_started[1] > 0
    assert not packets(other_client) and not other._ready and other._target is None
    assert LOCK_STATUS in other_co.controller_state
    c._stop_countdown()
    other._stop_countdown()


async def test_store_gate_and_no_fabricated_capabilities():
    c, co, client = make_controller()
    assert c.supports_memory_programming
    co.entry.data[const.CONF_KAIDI_SOFA_ACU_NO] = 0x322
    c = ComfyController(co)
    assert not c.supports_memory_programming
    with pytest.raises(ValueError):
        await c.program_memory(1)
    assert not packets(client)
    assert not c.supports_massage and not c.supports_preset_zero_g
    assert not c.position_number_specs and c.memory_slot_count == 4
    assert len(c.motor_control_specs) == 3
    assert len(c.controller_button_specs) == len(COMFY_ACTIONS)
    assert not any("enroll" in s.key for s in c.controller_button_specs)


async def test_constructed_frame_keeps_bytes_and_rejects_a_new_link():
    c, co, client = make_controller("comfyds")
    await c._write_lane.acquire()
    captured = asyncio.Event()
    original = c.write_command

    async def write(frame, **kwargs):
        captured.set()
        await original(frame, **kwargs)

    c.write_command = write
    task = asyncio.create_task(c.control("query"))
    await captured.wait()
    c._own, c._target = 9, -2
    c._write_lane.release()
    await task
    assert packets(client) == [codec.control(0x12345678, 0x11223344, 70)]
    await c._write_lane.acquire()
    captured.clear()
    task = asyncio.create_task(c.control("query"))
    await captured.wait()
    c.on_disconnect()
    co.client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._write_lane.release()
    with pytest.raises(ConnectionError):
        await task
    co.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("app", ("komfyd", "comfyds"))
def test_conditional_sdk_fields_never_select_capabilities(app):
    c, _, _ = make_controller(app)
    frame = bytes.fromhex("0300000000237856341280665544332211ff0000")
    notify(c, frame.hex())
    if app == "komfyd":
        assert c._sdk_nodes == {}
        return
    assert c._sdk_nodes == {"11:22:33:44:55:66": {"virtual": 0x12345678, "product": -1}}
    # Existing-row quirk reads virtual from raw12..15, not raw6..9.
    notify(c, frame.hex())
    assert c._sdk_nodes["11:22:33:44:55:66"]["virtual"] == 0x22334455
    group = bytes.fromhex("03000000002455443322d700000000000000fe00")
    notify(c, group.hex())
    assert c._sdk_nodes["11:22:33:44:55:66"]["group"] == -2
    assert c.profile.product == 130 and c.memory_slot_count == 4


def test_comfyds_unknown_hf_missing_record_requires_explicit_side():
    c, _, _ = make_controller("comfyds")
    c._selected_side = None
    with pytest.raises(ValueError, match="Select a bed side"):
        c._opcode("h_increase")
    with c.side_scope("right"):
        assert c._opcode("h_increase") == 74
    k, _, _ = make_controller("komfyd")
    k._selected_side = None
    assert k._opcode("h_increase") == 74


def test_complete_capability_validation_and_retained_high_bit_domain():
    # Exhaust the BE16 parameter, including the unvalidated bar3 high bit.
    payload = bytearray.fromhex("ffffc0ff0178563412810000000000000000")
    for capability in range(65536):
        payload[10:12] = capability.to_bytes(2, "big")
        ad = comfy_advertisement({0xFFFF: bytes(payload)})
        valid = (
            (capability >> 8 & 7) <= 5 and (capability & 15) <= 5 and (capability >> 4 & 15) <= 5
        )
        assert (ad is not None) == valid
        if ad:
            assert ad.sofa_acu_no == capability


def test_single_receiver_sides_share_one_ha_callback_owner():
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed.paired_topology import SingleLinkSideAwareTopology

    c, _, _ = make_controller()
    assert c.commands_share_timer
    # The existing topology contracts exercise replacement and STOP fan-out
    # for this declaration; this app must opt in even with independent op banks.
    pair = MagicMock()
    pair._single_inner.capability_controller = c
    assert SingleLinkSideAwareTopology(pair, native_both=True).shared_command_timer


@pytest.mark.parametrize("mode,marker,size", ((1, 0, 18), (2, 0xA0, 25), (2, 0xA1, 25), (2, 0, 28)))
@pytest.mark.parametrize("signed", (0, -1, -2, -(2**31), 2**31 - 1))
def test_all_advertised_layouts_keep_signed_room_and_node(mode, marker, size, signed):
    raw = bytearray(size)
    raw[:5] = bytes.fromhex("ffffc0ff") + bytes((mode,))
    raw[5:9] = signed.to_bytes(4, "little", signed=True)
    if mode == 1:
        raw[9], raw[10:12] = 131, bytes.fromhex("1322")
    else:
        raw[20] = marker
        index = 17 if marker else 25
        raw[index], raw[index + 1 : index + 3] = 131, bytes.fromhex("1322")
        raw[21:25] = signed.to_bytes(4, "little", signed=True)
    ad = comfy_advertisement({0xFFFF: bytes(raw)[2:]})
    assert ad is not None and ad.room_id == signed and ad.product_id == 129
    if mode == 2:
        assert ad.vaddr == signed  # discovery zero stays zero, not ping's -2
    for end in range(5, size):
        assert comfy_advertisement({0xFFFF: bytes(raw[:end])}) is None


async def test_gatt_session_finds_exact_chars_across_arbitrary_services():
    from tests.hold_lease_wire import _tool

    tool = _tool()
    clock = tool.FakeClock()
    recorder = tool.Recorder(clock)
    scenario = tool.default_scenario("comfyds")
    layout = {
        "services": {
            "11111111-2222-3333-4444-555555555555": [codec.WRITE_CHAR_UUID],
            "99999999-aaaa-bbbb-cccc-dddddddddddd": [codec.NOTIFY_CHAR_UUID],
        }
    }
    with tool.virtual_time(clock):
        controller = await tool._build(
            scenario, tool.FakeClient(recorder, layout, scenario.replies)
        )
        result = await tool._connect(controller, recorder, clock)
    assert result["status"] == "ok"
    assert controller._ready and controller._target == 0x01020304
