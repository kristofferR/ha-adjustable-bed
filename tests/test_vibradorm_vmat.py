"""VMAT artifact vectors through actual controller delivery and setup roles."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.vibradorm_app import (
    CBI,
    COMMAND,
    LIGHT,
    MEMORY,
    MOTORS,
    RESPONSE,
    VibradormAppController,
    validate_vibradorm_app_profile,
)
from custom_components.adjustable_bed.vibradorm_vmat_profiles import VMAT_REMOTES
from custom_components.adjustable_bed.vibradorm_vmat_setup import (
    DIS,
    DIS_FIELDS,
    MANAGEMENT,
    MANAGEMENT_SERVICE,
    SERVICE,
    validate_vmat_roles,
)

VECTORS = json.loads((Path(__file__).parent / "fixtures/vibradorm_vmat_vectors.json").read_text())


def make_vmat(remote: str = "13") -> VibradormAppController:
    selected = VMAT_REMOTES[remote]
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.cancel_command = asyncio.Event()
    coordinator.client = MagicMock(is_connected=True, mtu_size=23)
    roles = [
        (SERVICE, [(CBI, ["write", "write-without-response"]), (COMMAND, ["write"]),
                   (LIGHT, ["write"]), (RESPONSE, ["notify"])]),
        (DIS, [(uuid, ["read"]) for _, uuid in DIS_FIELDS]),
        (MANAGEMENT_SERVICE, [(MANAGEMENT, [])]),
    ]
    coordinator.client.services = [
        MagicMock(uuid=service, characteristics=[
            MagicMock(uuid=uuid, properties=properties, handle=i + 1)
            for i, (uuid, properties) in enumerate(characteristics)
        ]) for service, characteristics in roles
    ]
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    coordinator.client.read_gatt_char = AsyncMock(return_value=b" identity ")
    coordinator.entry.data = {}
    return VibradormAppController(
        coordinator, app_profile="vmat", control_type=selected.control_type,
        remote=remote, floor_light=selected.floor_light, rgb=selected.rgb,
        massage=selected.massage, light_extension=selected.light_extension,
    )


def frames(c: VibradormAppController) -> list[str]:
    return [call.args[1].hex() for call in c.client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("remote", VMAT_REMOTES)
def test_remote_contract_and_no_guessed_capabilities(remote):
    c = make_vmat(remote)
    r = VMAT_REMOTES[remote]
    assert c.profile.control_type == r.control_type
    assert c.profile.groups == r.groups
    assert c.supports_lights == r.floor_light
    assert c.supports_massage == r.massage
    assert c.profile.rgb == r.rgb
    assert c.profile.light_extension == r.light_extension
    assert c.memory_slot_count == (0 if r.control_type == 2 else 6)
    assert c.profile.sync == (r.control_type in (8, 9))
    assert c.requires_notification_channel
    assert not c.supports_position_feedback and not c.supports_preset_flat


@pytest.mark.parametrize("remote", VMAT_REMOTES)
def test_remote_flags_cannot_be_spoofed(remote):
    r = VMAT_REMOTES[remote]
    with pytest.raises(ValueError):
        validate_vibradorm_app_profile(
            "vmat", r.control_type, remote=remote, floor_light=not r.floor_light,
            rgb=r.rgb, massage=r.massage, light_extension=r.light_extension,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", ["01", "07"])
@pytest.mark.parametrize(("level", "raw"), enumerate((0, 32, 64, 96, 128, 160, 192, 224, 250)))
@pytest.mark.parametrize("toggle", [0, 0x8000])
async def test_floor_delivery_full_shipped_range(remote, level, raw, toggle):
    c = make_vmat(remote)
    c._toggle = toggle
    await c.set_pending_floor_timer(30)
    await c.execute_app_action("floor_timer_toggle")
    assert not frames(c)
    await c._floor(level)
    expected = bytes((raw, 0, 30)) if remote == "01" else (0x11 | toggle).to_bytes(2, "big") + bytes((raw, 30))
    assert frames(c) == [expected.hex()]
    call = c.client.write_gatt_char.call_args
    assert call.args[0].uuid == (LIGHT if remote == "01" else CBI)
    assert call.kwargs["response"] is (remote == "01")
    assert c._toggle == toggle  # construction and P1 execution flips cancel
    assert c.get_light_state()["light_level"] == level


@pytest.mark.asyncio
@pytest.mark.parametrize("v", [v for v in VECTORS["vectors"] if v["id"].startswith("UI-color-")], ids=lambda v: v["id"])
async def test_all_shipped_palette_packets(v):
    c = make_vmat("12" if v["inputs"]["basic"] else "13")
    c._toggle = v["inputs"]["T"]
    option = tuple(c.mood_palette)[v["inputs"]["palette_index"]]
    await c.set_mood_palette(option)
    assert frames(c) == [bytes.fromhex(v["expected_bytes"]).hex()]
    assert c.client.write_gatt_char.call_args.kwargs["response"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", ["12", "13"])
@pytest.mark.parametrize("speed", range(9))
@pytest.mark.parametrize("toggle", [0, 0x8000])
async def test_all_mood_speed_positions(remote, speed, toggle):
    c = make_vmat(remote)
    c._toggle = toggle
    await c.set_mood_speed(speed)
    opcode = (0x77 if remote == "12" else 0x1077) | toggle
    assert frames(c) == [(opcode.to_bytes(2, "big") + bytes((9, 18 - 2 * speed))).hex()]


@pytest.mark.asyncio
@pytest.mark.parametrize("v", VECTORS["parsers"]["save_sequences"])
async def test_complete_nine_frame_save_sequence(v):
    c = make_vmat("13")
    c._toggle = v["toggle"]
    await c.program_memory(v["slot"])
    assert frames(c) == [bytes.fromhex(f["bytes"]).hex() for f in v["frames"]]
    assert all(call.args[0].uuid == CBI and call.kwargs["response"] is False for call in c.client.write_gatt_char.call_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", ["00", "07", "11", "13"])
@pytest.mark.parametrize("toggle", [0, 0x8000])
async def test_every_reachable_held_control_releases(remote, toggle):
    probe = make_vmat(remote)
    for control in probe.held_control_options:
        if control == "sync":
            continue
        c = make_vmat(remote)
        c._toggle = toggle
        c.client.write_gatt_char.reset_mock()
        await c.hold_control(control, 100)
        opcode = MEMORY[int(control[7:]) - 1] if control.startswith("memory_") else MOTORS[control]
        packet = bytes((opcode,)) if c.profile.basic else (opcode | toggle).to_bytes(2, "big")
        assert frames(c) == [packet.hex(), "ff" if c.profile.basic else "00ff"]
        assert all(call.kwargs["response"] is c.profile.basic for call in c.client.write_gatt_char.call_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", ["01", "07"])
async def test_floor_failure_rolls_back_current_and_remembered_intent(remote):
    c = make_vmat(remote)
    c._floor_level = 3
    c.client.write_gatt_char.side_effect = OSError("failed")
    with pytest.raises(OSError):
        await c.lights_off()
    assert c._floor_level == 3 and c._floor_default == 8
    c._coordinator.remember_vibradorm_app_floor_default.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["mood", "mode", "speed", "wave", "zone"])
async def test_accessory_failure_does_not_publish_or_change_local_intent(action):
    c = make_vmat("13")
    if action in ("wave", "zone"):
        await c.execute_app_action("massage_automatic")
    before = asdict(c._massage)
    c.client.write_gatt_char.side_effect = OSError("failed")
    c._coordinator.handle_controller_state_updates.reset_mock()
    with pytest.raises(OSError):
        if action == "mood":
            await c.set_mood_palette("#00aba9")
        elif action == "mode":
            await c.execute_app_action("massage_automatic")
        elif action == "speed":
            await c.set_massage_speed(4)
        elif action == "wave":
            await c.set_massage_wave("3")
        else:
            await c.massage_head_up()
    assert asdict(c._massage) == before
    assert c.protocol_diagnostics["mood_intent"] == {}


@pytest.mark.parametrize("role", [CBI, RESPONSE, COMMAND, LIGHT, *(uuid for _, uuid in DIS_FIELDS), MANAGEMENT])
def test_setup_requires_all_exact_roles_even_basic_without_floor_ui(role):
    c = make_vmat("00")
    for service in c.client.services:
        service.characteristics = [char for char in service.characteristics if char.uuid != role]
    with pytest.raises(ValueError):
        validate_vmat_roles(c.client, basic=True, onboarding=True)


@pytest.mark.asyncio
async def test_single_shots_wait_after_success_completion_and_stop_bypasses_delay():
    c = make_vmat("13")
    completed = []
    started = []
    clock = [100.0]
    sleeps = []
    real_sleep = asyncio.sleep

    async def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay
        await real_sleep(0)

    async def write(*args, **kwargs):
        started.append(clock[0])
        await asyncio.sleep(0.03)
        completed.append(clock[0])

    c.client.write_gatt_char.side_effect = write
    with (
        patch.object(asyncio.get_running_loop(), "time", side_effect=lambda: clock[0]),
        patch("custom_components.adjustable_bed.beds.vibradorm_app.asyncio.sleep", new=sleep),
    ):
        await c.set_mood_speed(0)
        await c.set_mood_speed(1)
        await c.stop_all()
    assert sleeps == pytest.approx([0.03, 0.1, 0.03, 0.03])
    assert started[1] - completed[0] == pytest.approx(0.1)
    assert started[2] == completed[1]
    assert frames(c)[-1] == "00ff"


@pytest.mark.asyncio
@pytest.mark.parametrize(("remote", "active", "opcode"), [("07", True, 25), ("11", False, 24)])
async def test_sync_only_streams_while_response_is_pending_and_held(remote, active, opcode):
    c = make_vmat(remote)

    async def write(characteristic, packet, **kwargs):
        if packet[1:] == b"\x3d\x3f":
            c._notification(characteristic, bytearray((0x20, 0x3F, 0x40 if active else 0)))

    c.client.write_gatt_char.side_effect = write
    await c.hold_control("sync", 250)
    assert frames(c)[0] == "003d3f" and frames(c)[-1] == "00ff"
    assert frames(c)[1] == (0x8000 | opcode).to_bytes(2, "big").hex()
    before = len(frames(c))
    c._notification(c.client.services[0].characteristics[0], bytearray.fromhex("203f40"))
    assert len(frames(c)) == before


@pytest.mark.asyncio
async def test_registered_notifications_are_bound_to_live_role_and_generation():
    c = make_vmat("07")
    old_client = c.client
    await c.start_notify()
    callback = old_client.start_notify.call_args.args[1]
    role = old_client.start_notify.call_args.args[0]
    waiter = asyncio.get_running_loop().create_future()
    c._sync_reply = waiter
    callback(old_client.services[0].characteristics[0], bytearray.fromhex("203f40"))
    assert c._sync_observed is None and not waiter.done()
    callback(role, bytearray.fromhex("203f40"))
    assert c._sync_observed is True and waiter.result() is True
    await c.stop_notify()
    c._sync_observed = None
    current_waiter = asyncio.get_running_loop().create_future()
    c._sync_reply = current_waiter
    callback(role, bytearray.fromhex("203f40"))
    assert c._sync_observed is None and not current_waiter.done()
    await c.start_notify()
    new_callback = old_client.start_notify.call_args.args[1]
    callback(role, bytearray.fromhex("203f40"))
    assert c._sync_observed is None and not current_waiter.done()
    c._coordinator.client = make_vmat("07").client
    new_callback(role, bytearray.fromhex("203f40"))
    assert c._sync_observed is None and not current_waiter.done()
    await c.start_notify()
    replacement = c.client.start_notify.call_args
    replacement.args[1](replacement.args[0], bytearray.fromhex("203f00"))
    assert c._sync_observed is False
    await c.stop_notify()


@pytest.mark.asyncio
@pytest.mark.parametrize("v", [v for v in VECTORS["vectors"] if v["inputs"].get("kind") == "massage"], ids=lambda v: v["id"])
async def test_full_massage_state_packets_from_frozen_builder_vectors(v):
    values = v["inputs"]
    c = make_vmat("12" if values["basic"] else "13")
    c._toggle = values["toggle"]
    c._massage.effect = values["effect"]
    c._massage.speed = values["speed"]
    c._massage.zones = (values["zone1"], values["zone2"])
    await c._send_massage()
    assert frames(c) == [bytes.fromhex(v["expected_bytes"]).hex()]


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", ["12", "13"])
async def test_automatic_individual_restore_clamps_and_exact_off_restore_order(remote):
    c = make_vmat(remote)
    group = "00" if remote == "12" else "10"
    await c.execute_app_action("massage_automatic")
    assert frames(c) == [group + "300101030300000000"]
    assert c._massage.zones == (3, 3) and c._massage.automatic == 7
    await c.set_massage_wave("4")
    for _ in range(6):
        await c.massage_head_down()
    assert c._massage.zones[0] == 1
    c._toggle = 0
    await c.execute_app_action("massage_individual")
    assert frames(c)[-2:] == [group + "3400", ("80" if remote == "12" else "90") + "300001000000000000"]
    assert c._massage.effect == 0
    await c.massage_head_toggle()
    assert c._massage.zones[0] == 1 and c._massage.flags[0]
    for _ in range(6):
        await c.massage_head_up()
    assert c._massage.zones[0] == 5
    await c.massage_head_toggle()
    assert c._massage.zones[0] == 0
    await c.massage_head_toggle()
    assert c._massage.zones[0] == 5


@pytest.mark.asyncio
async def test_normal_session_reads_dis_without_any_onboarding_query_or_position_poll():
    c = make_vmat("07")
    await c.async_discover_capabilities()
    await c.refresh_device_info()
    assert c.client.read_gatt_char.await_count == 3
    assert not frames(c)
    c.client.start_notify.assert_awaited_once()
    assert c._metadata.model == " identity "


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", VMAT_REMOTES)
async def test_disabled_actions_fail_without_a_write(remote):
    c = make_vmat(remote)
    unsupported = set(MOTORS) - set(c.held_control_options)
    for action in unsupported:
        with pytest.raises(ValueError):
            await c.hold_control(action, 100)
    if not c.supports_lights:
        with pytest.raises(ValueError):
            await c.lights_on()
    if not c.profile.rgb:
        with pytest.raises(ValueError):
            await c.set_mood_palette("#ffffff")
    if not c.supports_massage:
        with pytest.raises(ValueError):
            await c.set_massage_speed(1)
    if not c.memory_slot_count:
        with pytest.raises(ValueError):
            await c.program_memory(1)
    assert not frames(c)
