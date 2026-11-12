"""Row150 frozen literals, production callers and session boundaries."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds import okin_motionbed as app
from custom_components.adjustable_bed.codec import keeson, okin_nframe
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.okin_nframe import OKIN_MOTIONBED as PROFILE

VECTORS = json.loads((Path(__file__).parent / "fixtures/okin_motionbed_vectors.json").read_text())
WRITE, NOTIFY = const.KEESON_BASE_WRITE_CHAR_UUID, const.KEESON_BASE_NOTIFY_CHAR_UUID
ACTIONS = {
    "cmd_back_on": "back_up",
    "cmd_back_off": "back_down",
    "cmd_head_on": "middle_up",
    "cmd_head_off": "middle_down",
    "cmd_leg_on": "legs_up",
    "cmd_leg_off": "legs_down",
    "cmd_stop": "stop",
    "cmd_position_STOP": "preset_stop",
    "cmd_ZEROG_call": "zero_g",
    "cmd_FLAT_call": "flat",
    "cmd_MemoryA_call": "memory_1",
    "cmd_MemoryB_call": "memory_2",
    "cmd_MemoryA_save": "save_memory_1",
    "cmd_MemoryB_save": "save_memory_2",
    "cmd_Light_on": "light_parameter_0",
    "cmd_Light_off": "light_parameter_1",
}


@pytest.mark.parametrize("row", VECTORS, ids=lambda r: r["id"])
def test_frozen_frames(row):
    """Keep all 35 inputs, including excluded arithmetic and repair emissions."""
    if row["kind"] == "incoming-input-not-a-write":
        assert row["inputs"]["data"] == row["expected_bytes"]
        return
    if row["id"].removeprefix("V.") in ACTIONS:
        word = PROFILE.keys[ACTIONS[row["id"][2:]]]
        assert okin_nframe.gateway_frame(word).hex().upper() == row["expected_bytes"]
        return
    for frame in row["expected_bytes"].split():
        data = bytes.fromhex(frame)
        if data[:3] == bytes.fromhex("E5FE16"):
            assert okin_nframe.gateway_frame(int.from_bytes(data[3:7], "big")) == data
        else:
            assert keeson.checked(data[:-1]) == data  # Dead time helper, never a supported action.


def char(uuid, props, handle=1):
    return SimpleNamespace(
        uuid=uuid,
        properties=props,
        handle=handle,
        descriptors=[],
        description="Synthetic row150 role",
    )


def layout(write=None, notify=None):
    return [
        SimpleNamespace(
            uuid="12345678-1234-1234-1234-123456789abc",
            characteristics=[
                write or char(WRITE, ["write"]),
                notify or char(NOTIFY, ["notify"]),
            ],
        )
    ]


def client(services=None):
    return SimpleNamespace(
        is_connected=True,
        services=services or layout(),
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )


@pytest.fixture
def bed(monkeypatch):
    c = MagicMock()
    c.client = client()
    c.cancel_command = asyncio.Event()
    c.motor_pulse_count = 5
    c.motor_count = 4  # Generic saved count cannot invent a fourth axis.
    monkeypatch.setattr(app, "_pause", AsyncMock(return_value=False))
    return app.OkinMotionBedController(c), c


def frames(c):
    return [call.args[1].hex().upper() for call in c.client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("action", tuple(PROFILE.keys))
async def test_every_live_action_has_a_production_caller(bed, action):
    ctrl, c = bed
    if action.endswith(("_up", "_down")):
        axis, direction = action.rsplit("_", 1)
        spec = next(s for s in ctrl.motor_control_specs if s.key == axis)
        await (spec.open_fn if direction == "up" else spec.close_fn)(ctrl)
        assert frames(c) == [okin_nframe.gateway_frame(PROFILE.keys[action]).hex().upper()] * 5 + [
            "E5FE160000000006"
        ]
        assert isinstance(app._pause, AsyncMock)
        assert [a.args[1] for a in app._pause.await_args_list] == [0.2] * 5
    else:
        if action == "stop":
            await ctrl.stop_all()
        elif action in ("flat", "zero_g"):
            await getattr(ctrl, f"preset_{action}")()
        elif action.startswith("memory_"):
            await ctrl.preset_memory(int(action[-1]))
        elif action.startswith("save_memory_"):
            await ctrl.program_memory(int(action[-1]))
        else:
            key = "motionbed_preset_stop" if action == "preset_stop" else f"motionbed_{action}"
            await next(s for s in ctrl.controller_button_specs if s.key == key).press_fn(ctrl)
        assert okin_nframe.gateway_frame(PROFILE.keys[action]).hex().upper() in frames(c)
    assert all(call.kwargs["response"] is True for call in c.client.write_gatt_char.await_args_list)


async def test_memory_actions_are_explicit_after_save_and_stop(bed):
    ctrl, c = bed
    for slot in (1, 2):
        await ctrl.program_memory(slot)
        await ctrl.preset_memory(slot)
        await ctrl.stop_preset()
        await ctrl.preset_memory(slot)
    assert frames(c) == [
        "E5FE1620000014D2",
        "E5FE1621000004E1",
        "E5FE1621000000E5",
        "E5FE1621000004E1",
        "E5FE1620000016D0",
        "E5FE1621000006DF",
        "E5FE1621000000E5",
        "E5FE1621000006DF",
    ]
    for slot in (0, 3):
        with pytest.raises(ValueError):
            await ctrl.program_memory(slot)
    c.client.is_connected = False
    with pytest.raises(ConnectionError):
        await ctrl.program_memory(1)


@pytest.mark.parametrize("failure", ("cancel", "error", "task_cancel"))
async def test_manual_release_survives_cancellation_and_failure(bed, monkeypatch, failure):
    ctrl, c = bed

    async def write(*args, **kwargs):
        if args[1] == okin_nframe.gateway_frame(1):
            c.cancel_command.set()
            if failure == "error":
                raise BleakError("write failed")
            if failure == "task_cancel":
                raise asyncio.CancelledError

    c.client.write_gatt_char.side_effect = write
    if failure == "cancel":
        await ctrl.hold_control("back_up", 500)
    else:
        with pytest.raises(BleakError if failure == "error" else asyncio.CancelledError):
            await ctrl.hold_control("back_up", 500)
    assert frames(c)[-1] == "E5FE160000000006"
    assert len(frames(c)) == 2


async def test_cancel_waiting_for_gatt_never_writes_a_queued_refresh(bed):
    ctrl, c = bed
    await ctrl.ble_lock.acquire()
    task = asyncio.create_task(ctrl.hold_control("back_up", 500))
    await asyncio.sleep(0)
    c.cancel_command.set()
    ctrl.ble_lock.release()
    await task
    assert frames(c) == ["E5FE160000000006"]


async def test_gatt_sort_properties_reconnect_and_stale_callbacks(bed):
    ctrl, c = bed
    first = char(WRITE, ["write"], 1)
    last = char(WRITE, ["write", "write-without-response"], 2)
    notify = char(NOTIFY, ["notify"], 3)
    c.client.services = [
        SimpleNamespace(
            uuid="70000000-0000-0000-0000-000000000000", characteristics=[last, notify]
        ),
        SimpleNamespace(uuid="80000000-0000-0000-0000-000000000000", characteristics=[first]),
    ]
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    old_callback = c.client.start_notify.await_args.args[1]
    await ctrl.preset_flat()
    assert c.client.write_gatt_char.await_args.args[0] is last
    for data in ("E2FE16", "E2FE160000000000", "E2FE", "E5FE160000000006"):
        old_callback(notify, bytearray.fromhex(data))
    assert c.handle_controller_state_updates.call_count == 0
    old = c.client
    await ctrl.stop_notify()
    old.stop_notify.assert_awaited_once_with(notify)
    c.client = client()
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    ctrl.forward_raw_notification = MagicMock()
    old_callback(notify, bytearray.fromhex("E2FE16"))
    ctrl.forward_raw_notification.assert_not_called()
    await ctrl.preset_flat()
    assert c.client.write_gatt_char.await_args.args[0] is not last


async def test_missing_or_nonwritable_gatt_recovers_without_stale_targets(bed):
    ctrl, c = bed
    await ctrl.async_discover_capabilities()
    c.client = client(layout(char(WRITE, ["write-without-response"])))
    with pytest.raises(ConnectionError):
        await ctrl.async_discover_capabilities()
    assert ctrl._write_char is None
    c.client.write_gatt_char.assert_not_awaited()
    c.client = client()
    c.client.start_notify.side_effect = BleakError("subscribe failed")
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    await ctrl.preset_flat()  # The report proves no notify-ready barrier.
    assert frames(c) == ["E5FE1621000002E3"]


async def test_replaced_client_does_not_receive_old_hold_cleanup(bed, monkeypatch):
    ctrl, c = bed
    old = c.client

    async def replace_client(*_):
        c.client = client()
        ctrl.on_disconnect()
        return True

    monkeypatch.setattr(app, "_pause", replace_client)
    await ctrl.hold_control("middle_up", 500)
    assert old.write_gatt_char.await_count == 1
    c.client.write_gatt_char.assert_not_awaited()


async def test_renewable_hold_runs_past_a_tap_and_expiry_releases_on_virtual_time():
    from tests.hold_lease_wire import leased_hold

    result = await leased_hold(
        "okin_motionbed",
        lambda ctrl: ctrl.hold_control("middle_up", 1000),
        end_after_s=1.37,
        end="expire",
    )
    assert len(result.held) > 5
    assert {w.data.hex() for w in result.held} == {"e5fe160000000501"}
    assert [w.data.hex() for w in result.after] == ["e5fe160000000006"]


async def test_app_picker_manual_setup_and_configure_keep_fixed_profile(
    hass, enable_custom_integrations
):
    from homeassistant.config_entries import SOURCE_USER
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.detection import bed_type_choice, detect_bed_type_detailed
    from custom_components.adjustable_bed.profile_id import resolve_profile_id, with_profile_ids
    from tests.test_config_flow import _advance_progress, _open_options_form, form_fields
    from tests.test_detection import _make_service_info

    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info", return_value=[]
    ):
        result = await hass.config_entries.flow.async_init(
            const.DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "select_by_app"}
        )
        picker = result["data_schema"].schema[const.CONF_BED_TYPE]
        choice = next(row for row in picker.rows() if "OKIN Motion Bed" in row)
        assert "com.okin.motionbed" in choice
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_BED_TYPE: choice}
        )
    assert result["step_id"] == "manual_entry"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "11:22:33:44:55:68"}
    )
    assert result["step_id"] == "finish_settings"
    fields = {m.schema for m in form_fields(result["data_schema"])}
    assert (
        not {
            const.CONF_MOTOR_COUNT,
            const.CONF_HAS_MASSAGE,
            const.CONF_DISABLE_ANGLE_SENSING,
            const.CONF_MOTOR_PULSE_DELAY_MS,
        }
        & fields
    )
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "Motion Bed", "preferred_adapter": "auto"}
        )
        result = await _advance_progress(hass, result)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert resolve_profile_id(result["data"]) == "okin_motionbed"
    assert per_side_profile("okin_motionbed", None).label == "OKIN Motion Bed"
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Motion Bed",
        data=with_profile_ids(result["data"]),
        unique_id="11:22:33:44:55:68",
    )
    entry.add_to_hass(hass)
    options = await _open_options_form(hass, entry.entry_id)
    assert options["type"] == FlowResultType.FORM
    saved = await hass.config_entries.options.async_configure(
        options["flow_id"], {const.CONF_BED_TYPE: bed_type_choice("okin_motionbed", None)}
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_PROFILE_ID] == "okin_motionbed"
    for name in ("OKIN", "OKIN Motion Bed", "Any bed"):
        detected = detect_bed_type_detailed(
            _make_service_info(name=name, service_uuids=["0000ffe5-0000-1000-8000-00805f9b34fb"])
        )
        assert detected.bed_type != "okin_motionbed"


@pytest.mark.usefixtures("mock_coordinator_connected")
async def test_real_coordinator_failure_idle_reconnect_entities_and_services(
    hass, mock_bleak_client, monkeypatch
):
    from custom_components.adjustable_bed.button import (
        BUTTON_DESCRIPTIONS,
        AdjustableBedButton,
        ControllerActionButton,
    )
    from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
    from custom_components.adjustable_bed.services import async_register_services
    from custom_components.adjustable_bed.setup_questions import setup_profile_for

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            const.CONF_BED_TYPE: const.BED_TYPE_OKIN_MOTIONBED,
            const.CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._max_retries = 1
    services = layout(char(WRITE, ["write-without-response"]))
    mock_bleak_client.services.__iter__ = lambda _: iter(services)
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    mock_bleak_client.write_gatt_char = AsyncMock()
    monkeypatch.setattr(app, "_pause", AsyncMock(return_value=False))
    with patch(
        "custom_components.adjustable_bed.coordinator_connection.read_ble_device_info",
        new_callable=AsyncMock,
    ) as info:
        assert not await coordinator.async_connect()
        services[:] = layout()
        assert await coordinator.async_connect()
        ctrl = coordinator.controller
        assert isinstance(ctrl, app.OkinMotionBedController)
        assert mock_bleak_client.start_notify.await_count == 1
        info.assert_not_awaited()
        settings = setup_profile_for({const.CONF_BED_TYPE: const.BED_TYPE_OKIN_MOTIONBED})
        assert not settings.questions and settings.owns[const.CONF_HAS_MASSAGE] is False
        assert {s.key for s in ctrl.motor_control_specs} == {"back", "middle", "legs"}
        assert not ctrl.supports_position_feedback and not ctrl.supports_lights
        assert all(
            s.scheduler_resource == "*" and s.hold.stop_scope == "side"
            for s in ctrl.motor_control_specs
        )
        coordinator._cancel_disconnect_timer()
        await coordinator._async_idle_disconnect()
        assert await coordinator.async_ensure_connected()
        ctrl = coordinator.controller
        assert isinstance(ctrl, app.OkinMotionBedController)
        assert mock_bleak_client.start_notify.await_count == 2
        # Real entity callers execute the new live controller after reconnect.
        button = AdjustableBedButton(
            coordinator, next(d for d in BUTTON_DESCRIPTIONS if d.key == "preset_memory_1")
        )
        button.hass = hass
        await button.async_press()
        light = ControllerActionButton(coordinator, ctrl.controller_button_specs[1])
        light.hass = hass
        await light.async_press()
        cover = AdjustableBedCover(
            coordinator, _build_cover_description(ctrl.motor_control_specs[1])
        )
        cover.hass = hass
        monkeypatch.setattr(cover, "async_write_ha_state", MagicMock())
        before_cover = mock_bleak_client.write_gatt_char.await_count
        coordinator._motor_pulse_count = 2
        await cover.async_open_cover()
        assert [
            a.args[1].hex().upper()
            for a in mock_bleak_client.write_gatt_char.await_args_list[before_cover:]
        ] == [
            "E5FE160000000501",
            "E5FE160000000501",
            "E5FE160000000006",
        ]
        coordinator._motor_pulse_count = 5
        await async_register_services(hass)
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, const.SIDE_BOTH)], []),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "hold_control",
                {"device_id": "bed", "control": "legs_down", "duration": 0.5},
                blocking=True,
            )
            await hass.services.async_call(
                const.DOMAIN, "save_preset", {"device_id": "bed", "preset": 2}, blocking=True
            )
        written = [
            a.args[1].hex().upper() for a in mock_bleak_client.write_gatt_char.await_args_list
        ]
        assert {
            "E5FE1621000004E1",
            "E5FE1631000000D5",
            "E5FE160000000501",
            "E5FE1600000008FE",
            "E5FE1620000016D0",
        } <= set(written)
        # A card UP/CANCEL uses the declared release entity. Only the held
        # command owns the manual STOP; a global Stop still covers presets.
        mock_bleak_client.write_gatt_char.reset_mock()
        started = asyncio.Event()

        async def observe(*_args, **_kwargs):
            started.set()

        async def wait_for_cancel(cancel, _seconds):
            await cancel.wait()
            return True

        mock_bleak_client.write_gatt_char.side_effect = observe
        monkeypatch.setattr(app, "_pause", wait_for_cancel)
        holding = asyncio.create_task(
            coordinator.async_execute_controller_command(
                lambda running: running.hold_control("middle_up", 1000),
                resource="*",
            )
        )
        await started.wait()
        release = ControllerActionButton(
            coordinator, next(s for s in ctrl.controller_button_specs if s.release_only)
        )
        release.hass = hass
        await release.async_press()
        await holding
        assert [
            a.args[1].hex().upper() for a in mock_bleak_client.write_gatt_char.await_args_list
        ] == [
            "E5FE160000000501",
            "E5FE160000000006",
        ]
        await coordinator.async_disconnect()
