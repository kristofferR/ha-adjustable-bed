"""Carpe Diem literal controls, original-link cleanup and HA entry points."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.linak.controller import LinakController
from custom_components.adjustable_bed.beds.linak.protocol import (
    LinakCapabilitySnapshot,
    LinakModelVariant,
    LinakProfile,
    decode_error,
    decode_reference,
)
from custom_components.adjustable_bed.beds.linak.services import async_register_linak_services
from custom_components.adjustable_bed.codec.linak import control_frame, selected_sections_frame
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.hold_lease_wire import virtual_clock

VECTORS = json.loads((Path(__file__).parent / "fixtures/carpe_diem_vectors.json").read_text())


def runtime(hass, motors=4, address="AA:BB:CC:DD:EE:67"):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            "address": address,
            "name": "Carpe Diem",
            "bed_type": "linak",
            "protocol_variant": "carpe_diem",
            "motor_count": motors,
            "has_massage": True,
            "disable_angle_sensing": True,
        },
    )
    entry.add_to_hass(hass)
    c = AdjustableBedCoordinator(hass, entry)
    c._client = MagicMock(is_connected=True)
    c._client.write_gatt_char = AsyncMock()
    c._client.start_notify = AsyncMock()
    c._client.stop_notify = AsyncMock()
    c._client.disconnect = AsyncMock()
    c._client.services.get_characteristic.return_value = SimpleNamespace(properties=["write"])
    c._client.services.get_service.return_value = None
    c._controller = LinakController(c, profile=LinakProfile.CARPE_DIEM)
    c._controller._capabilities = LinakCapabilitySnapshot(
        profile=LinakProfile.CARPE_DIEM,
        model_variant=LinakModelVariant.TD3,
        actuator_mask=0,
        discovery_complete=True,
    )
    c.async_ensure_connected = AsyncMock(return_value=True)
    c._async_refresh_controller_auth = AsyncMock()
    return c


def frames(client):
    return [call.args[1].hex() for call in client.write_gatt_char.call_args_list]


async def shutdown(c):
    c._client.is_connected = False
    await c.async_shutdown()


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["id"])
async def test_27_frozen_literals(hass, vector):
    c = runtime(hass)
    ctrl = c.controller
    inputs, op = vector["inputs"], vector["operation"]
    if op == "movement":
        result = selected_sections_frame(frozenset(inputs["sections"]), inputs["up"]).hex()
    elif op == "control":
        result = control_frame(inputs["opcode"]).hex()
    elif op == "massage":
        fn = {
            (True, True): ctrl.massage_toggle,
            (True, False): ctrl.massage_head_toggle,
            (False, True): ctrl.massage_foot_toggle,
            (False, False): ctrl.massage_off,
        }
        with virtual_clock():
            await fn[inputs["back"], inputs["legs"]]()
        result = ";".join(frames(c.client))
    elif op == "reference":
        state = decode_reference(bytes.fromhex(inputs["data"]), carpe_diem=True)
        result = {"extension": state.extension, "speed": state.speed, "flags": state.status_flags}
    else:
        state = decode_error(bytes.fromhex(inputs["data"]))
        result = None if state is None else {"code": state.code, "data": state.payload.hex()}
    assert result == vector["expected"]
    await shutdown(c)


@pytest.mark.parametrize(
    "sections,up,expected",
    [
        ({"back", "head", "feet"}, True, "2b00"),
        ({"back", "legs", "head"}, False, "3400"),
        ({"legs", "head", "feet"}, False, "2100"),
    ],
)
async def test_selector_priority_and_normal_cadence(hass, sections, up, expected):
    c = runtime(hass)
    times = []

    async def write(*_args, **_kwargs):
        times.append(asyncio.get_running_loop().time())

    c.client.write_gatt_char.side_effect = write
    with virtual_clock():
        await c.controller.move_selected_sections(frozenset(sections), up)
    assert frames(c.client) == [expected] * 4 + ["ff00"]
    assert [round(t - times[0], 3) for t in times[:4]] == [0, 0.3, 0.6, 0.9]
    await shutdown(c)


async def test_favorite_distinct_schedule_and_explicit_ha_release(hass):
    c = runtime(hass)
    times = []

    async def write(*_args, **_kwargs):
        times.append(asyncio.get_running_loop().time())
        if len(times) == 3:
            c.cancel_command.set()

    c.client.write_gatt_char.side_effect = write
    with virtual_clock():
        await c.controller.preset_memory(4)
    assert frames(c.client) == ["4400"] * 3 + ["ff00"]
    assert [round(t - times[0], 3) for t in times[:3]] == [0, 0.025, 0.225]
    await shutdown(c)


@pytest.mark.parametrize("replace", [False, True])
async def test_task_cancel_before_gatt_never_releases_or_migrates(hass, replace):
    c = runtime(hass)
    client = c.client
    await c.controller._ble_lock.acquire()
    task = asyncio.create_task(c.controller.move_back_up())
    await asyncio.sleep(0)
    if replace:
        c._client = MagicMock(
            is_connected=True,
            write_gatt_char=AsyncMock(),
            disconnect=AsyncMock(),
            stop_notify=AsyncMock(),
        )
        c.controller._ble_lock.release()
        with pytest.raises(ConnectionError):
            await task
    else:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        c.controller._ble_lock.release()
    assert frames(client) == [] and frames(c.client) == []
    await shutdown(c)


async def test_submitted_write_settles_before_exact_cleanup(hass):
    c = runtime(hass)
    entered, acknowledge = asyncio.Event(), asyncio.Event()

    async def write(_uuid, data, **_kwargs):
        if data != bytes.fromhex("ff00"):
            entered.set()
            await acknowledge.wait()

    c.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(c.controller.move_back_up())
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert frames(c.client) == ["0b00"]
    acknowledge.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(c.client) == ["0b00", "ff00"]
    await shutdown(c)


async def test_link_loss_does_not_send_cleanup_to_replacement(hass):
    c = runtime(hass)
    old = c.client
    replacement = MagicMock(
        is_connected=True,
        write_gatt_char=AsyncMock(),
        disconnect=AsyncMock(),
        stop_notify=AsyncMock(),
    )

    async def replace(*_args, **_kwargs):
        c._client = replacement

    old.write_gatt_char.side_effect = replace
    with virtual_clock(), pytest.raises(ConnectionError):
        await c.controller.move_back_up()
    assert frames(old) == ["0b00"] and frames(replacement) == []
    await shutdown(c)


async def test_profile_capabilities_and_native_card_controls(hass):
    c = runtime(hass)
    ctrl = c.controller
    assert not ctrl.supports_single_address_pairing
    assert not ctrl.supports_position_feedback and not ctrl.position_number_specs
    assert not ctrl.supports_automatic_drive and not ctrl.supports_device_rename
    assert ctrl.alarm_capability is None and ctrl.capability_snapshot() is None
    assert ctrl.memory_slot_count == 4 and ctrl.execution.hold == "stream"
    assert per_side_profile("linak", "carpe_diem").variant_owned
    # The shared native controls supply placement, rather than a card key list.
    assert {s.key for s in ctrl.motor_control_specs} == {"back", "legs", "head", "feet"}
    await shutdown(c)


async def test_native_sections_service_uses_real_target_registry(hass):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr

    c = runtime(hass)
    c.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(const.DOMAIN, {})[c.entry.entry_id] = c
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=c.entry.entry_id,
        identifiers={(const.DOMAIN, c.address)},
    )
    async_register_linak_services(hass)
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "linak_move_sections",
            {
                "device_id": [device.id],
                "sections": ["back", "legs", "head"],
                "direction": "up",
                "duration_ms": 650,
            },
            blocking=True,
        )
    assert frames(c.client)[-1] == "ff00"
    assert set(frames(c.client)[:-1]) == {"3700"}
    await shutdown(c)


@pytest.mark.parametrize("mask", [None, 0, 0xF8])
async def test_live_queries_exact_mask_and_stale_notification_receiver(hass, mask):
    c = runtime(hass)
    callbacks = {}
    c.client.services.get_service.side_effect = lambda uuid: (
        SimpleNamespace(uuid=uuid)
        if mask is not None
        and uuid
        in {
            const.LINAK_POSITION_SERVICE_UUID,
            const.LINAK_TIMER_SERVICE_UUID,
        }
        else None
    )
    c.client.read_gatt_char = AsyncMock(
        side_effect=lambda uuid: {
            const.LINAK_POSITION_MASK_UUID: bytes((mask or 0,)),
            const.LINAK_POSITION_BACK_UUID: bytes.fromhex("88134006"),
            const.LINAK_POSITION_LEG_UUID: bytes.fromhex("1027c8f9"),
            const.LINAK_ERROR_CHAR_UUID: bytes.fromhex("010002"),
            const.LINAK_DEVICE_NAME_UUID: b"Bed",
        }.get(uuid, bytes(4))
    )

    async def subscribe(uuid, callback):
        callbacks[uuid] = callback

    c.client.start_notify.side_effect = subscribe
    await c.controller.async_discover_capabilities()
    await c.controller.start_notify()
    assert c.controller.memory_slot_count == (0 if mask is None else 4)
    assert c.controller.protocol_diagnostics["model_variant"] == (
        "standard" if mask is None else "td3" if not mask else "advanced_with_alarm"
    )
    assert not c.controller.position_number_specs
    if mask:
        from custom_components.adjustable_bed.beds.linak.controller import _AxisKeys

        assert c.controller_state.get(_AxisKeys.of("back").extension) == 50
        assert c.controller_state.get(_AxisKeys.of("legs").extension) == 100
        old = callbacks[const.LINAK_POSITION_BACK_UUID]
        c._client = MagicMock(is_connected=True, disconnect=AsyncMock(), stop_notify=AsyncMock())
        old(None, bytearray(4))
        assert c.controller_state.get(_AxisKeys.of("back").extension) == 50
    await shutdown(c)


async def test_no_capability_inference_from_unreadable_mask(hass):
    c = runtime(hass)
    c.client.services.get_service.return_value = SimpleNamespace()
    c.client.read_gatt_char = AsyncMock(return_value=b"")
    await c.controller.async_discover_capabilities()
    assert c.controller._capabilities.actuator_mask is None
    assert not c.controller.controller_entity_discovery_complete
    assert c.controller.memory_slot_count == 0
    await shutdown(c)


@pytest.mark.parametrize("route", ["typed", "picked", "discovered"])
async def test_actual_setup_through_final_form(hass, mock_bluetooth_service_info, route):
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        _bed_type_selector,
    )
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.detection import bed_type_choice
    from tests.form_helpers import form_answers, form_fields, start_new_bed

    choice = bed_type_choice("linak", "carpe_diem")
    assert choice in _bed_type_selector(None).rows().values()
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": "user"}
    flow._discovery_info = mock_bluetooth_service_info
    result = await start_new_bed(flow, route, choice)
    assert result["step_id"] == "finish_settings", result
    fields = form_fields(result["data_schema"])
    assert "motor_count" in fields and "has_massage" in fields
    assert "disable_angle_sensing" not in fields
    # Submission reaches the real pairing operation without bypassing final normalization.
    answers = form_answers(result)

    def customize(values):
        for key, value in values.items():
            if isinstance(value, dict):
                customize(value)
            elif key == "motor_count":
                values[key] = 3
            elif key == "has_massage":
                values[key] = True

    customize(answers)
    await flow.async_step_finish_settings(answers)
    data = flow._manual_data
    assert data["motor_count"] == 3 and data["has_massage"]
    assert data["protocol_variant"] == "carpe_diem" and not data.get("read_positions", False)
    assert (data["motor_pulse_count"], data["motor_pulse_delay_ms"]) == (4, 300)
    c = runtime(hass, motors=3)
    ctrl = await create_controller(c, "linak", data["protocol_variant"], None)
    assert ctrl._profile is LinakProfile.CARPE_DIEM
    await shutdown(c)


async def test_stop_before_lazy_import_invalidates_later_target(hass):
    c = runtime(hass)
    entered, release = asyncio.Event(), asyncio.Event()

    async def import_later(*_args):
        entered.set()
        await release.wait()

    async_register_linak_services(hass)
    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(c, "both")], [])),
        patch(
            "custom_components.adjustable_bed.beds.linak.services.async_import_modules",
            import_later,
        ),
    ):
        task = asyncio.create_task(
            hass.services.async_call(
                const.DOMAIN,
                "linak_move_sections",
                {
                    "device_id": ["bed"],
                    "sections": ["back", "legs"],
                    "direction": "up",
                    "duration_ms": 650,
                },
                blocking=True,
            )
        )
        await entered.wait()
        await c.async_stop_command()
        c.client.write_gatt_char.reset_mock()
        release.set()
        await task
    assert frames(c.client) == []
    await shutdown(c)


async def test_two_address_right_child_keeps_physical_target(hass):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed import _async_ensure_paired_device_registry
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.paired_devices import side_identifier

    left, right = runtime(hass), runtime(hass, address="AA:BB:CC:DD:EE:68")
    entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": "carpe-two"})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = PairedBedCoordinator(
        hass, entry, {"left": left, "right": right}, connection_mode="concurrent"
    )
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = pair
    _async_ensure_paired_device_registry(hass, entry, pair)
    child = dr.async_get(hass).async_get_child_device_by_identifier(
        side_identifier(pair, "right"), entry.entry_id
    )
    assert child is not None
    async_register_linak_services(hass)
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "linak_move_sections",
            {
                "device_id": [child.id],
                "sections": ["back", "legs"],
                "direction": "up",
                "duration_ms": 400,
            },
            blocking=True,
        )
    assert frames(left.client) == []
    assert frames(right.client)[-1] == "ff00" and frames(right.client)[0] == "3700"
    await shutdown(left)
    await shutdown(right)


@pytest.mark.parametrize(
    "motors,axes",
    [(2, {"back", "legs"}), (3, {"back", "legs", "head"}), (4, {"back", "legs", "head", "feet"})],
)
async def test_declared_layout_and_native_light_button_card(hass, motors, axes):
    from custom_components.adjustable_bed.button import BUTTON_DESCRIPTIONS, AdjustableBedButton

    c = runtime(hass, motors=motors)
    assert {spec.key for spec in c.controller.motor_control_specs} == axes
    description = next(d for d in BUTTON_DESCRIPTIONS if d.key == "toggle_light")
    button = AdjustableBedButton(c, description)
    assert button.capability_attributes["card_section"] == "lighting"
    await button.async_press()
    assert frames(c.client) == ["9400"]
    await shutdown(c)


async def test_explicit_disconnected_stop_never_connects(hass):
    c = runtime(hass)
    c._client.is_connected = False
    await c.async_stop_command()
    c.async_ensure_connected.assert_not_awaited()
    assert frames(c.client) == []
    await shutdown(c)


async def test_paired_abort_uses_registered_original_release(hass):
    from custom_components.adjustable_bed.command_scheduler import (
        PAIRED_CLEANUP_STOP,
        PAIRED_SESSION_BOUND_ABORTS,
    )

    c = runtime(hass)
    release = AsyncMock()
    session_scope = PAIRED_SESSION_BOUND_ABORTS.set(frozenset({c.address}))
    cleanup_scope = PAIRED_CLEANUP_STOP.set({c.address: release})
    try:
        await c.async_stop_command()
        release.assert_awaited_once()
        assert frames(c.client) == []
    finally:
        PAIRED_CLEANUP_STOP.reset(cleanup_scope)
        PAIRED_SESSION_BOUND_ABORTS.reset(session_scope)
        await shutdown(c)


@pytest.mark.parametrize("ingress", ["selected_sections", "coordinator", "timed_move"])
@pytest.mark.parametrize("pause", ["ble", "command", "connect"])
@pytest.mark.parametrize("replace_link", [False, True])
async def test_failed_both_sections_never_releases_unattempted_member(
    hass, ingress, pause, replace_link
):
    from bleak.exc import BleakError
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed import _async_ensure_paired_device_registry
    from custom_components.adjustable_bed.command_scheduler import current_command_context
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    left, right = runtime(hass), runtime(hass, address="AA:BB:CC:DD:EE:68")
    entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": "carpe-abort"})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = PairedBedCoordinator(
        hass, entry, {"left": left, "right": right}, connection_mode="concurrent"
    )
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = pair
    _async_ensure_paired_device_registry(hass, entry, pair)
    parent = dr.async_get(hass).async_get_device_by_identifier(
        (const.DOMAIN, pair.pair_id), entry.entry_id
    )
    assert parent is not None
    if ingress == "timed_move":
        await services.async_register_services(hass)
    elif ingress == "selected_sections":
        async_register_linak_services(hass)
    preparing = asyncio.Event()

    async def ensure_connected(*args, **kwargs):
        context = current_command_context()
        if context is not None and context.group_id is not None:
            preparing.set()
        return await AdjustableBedCoordinator.async_ensure_connected(right, *args, **kwargs)

    async def fail_left(*_args, **_kwargs):
        if pause == "connect":
            await preparing.wait()
        raise BleakError("failing left write")

    left.client.write_gatt_char.side_effect = fail_left
    if pause == "connect":
        right.async_ensure_connected.side_effect = ensure_connected
    stop_admitted = asyncio.Event()
    admit = right.admit_stop_command

    def admit_stop(**kwargs):
        task = admit(**kwargs)
        stop_admitted.set()
        return task

    old_right_client = right.client
    lock = {
        "ble": right.controller._ble_lock,
        "command": right._command_lock,
        "connect": right._lock,
    }[pause]
    await lock.acquire()
    with patch.object(right, "admit_stop_command", side_effect=admit_stop):
        task = asyncio.create_task(
            pair.async_execute_controller_command(
                lambda ctrl: ctrl.move_back_up(), side="both", resource="motor:back"
            )
            if ingress == "coordinator"
            else hass.services.async_call(
                const.DOMAIN,
                "timed_move" if ingress == "timed_move" else "linak_move_sections",
                {
                    "device_id": [parent.id],
                    "direction": "up",
                    "duration_ms": 650,
                    **(
                        {"motor": "back"}
                        if ingress == "timed_move"
                        else {"sections": ["back", "legs"]}
                    ),
                },
                blocking=True,
            )
        )
        try:
            await asyncio.wait_for(stop_admitted.wait(), 2)
            if replace_link:
                right._client = MagicMock(
                    is_connected=True,
                    write_gatt_char=AsyncMock(),
                    disconnect=AsyncMock(),
                    stop_notify=AsyncMock(),
                )
        finally:
            lock.release()
        with pytest.raises(HomeAssistantError):
            await task
    assert frames(right.client) == []
    assert frames(old_right_client) == []
    assert frames(left.client) == ["3700" if ingress == "selected_sections" else "0b00", "ff00"]
    await shutdown(left)
    await shutdown(right)


@pytest.mark.parametrize("motor", [False, True], ids=["bed", "motor"])
@pytest.mark.parametrize("replacement", ["none", "client", "controller", "generation"])
async def test_queued_stop_stays_on_admitted_connection(hass, motor, replacement):
    from custom_components.adjustable_bed.errors import BedNotConnectedError

    c = runtime(hass)
    original_client = c.client
    admitted = asyncio.Event()
    admit = c._command_scheduler.admit_stop

    def admit_stop(*args, **kwargs):
        task = admit(*args, **kwargs)
        admitted.set()
        return task

    await c._command_lock.acquire()
    with patch.object(c._command_scheduler, "admit_stop", side_effect=admit_stop):
        task = (
            asyncio.create_task(
                c.async_stop_motor(
                    lambda ctrl: ctrl.move_back_stop(), "motor:back", require_current_link=True
                )
            )
            if motor
            else c.admit_stop_command(current_link_only=True)
        )
        await admitted.wait()
        if replacement == "client":
            c._client = MagicMock(
                is_connected=True,
                write_gatt_char=AsyncMock(),
                disconnect=AsyncMock(),
                stop_notify=AsyncMock(),
            )
        elif replacement == "controller":
            c._controller = LinakController(c, profile=LinakProfile.CARPE_DIEM)
        elif replacement == "generation":
            c._position_connection_generation += 1
        c._command_lock.release()
        if replacement == "none":
            await task
            assert frames(original_client) == ["ff00"]
        else:
            with pytest.raises(BedNotConnectedError):
                await task
            assert frames(original_client) == frames(c.client) == []
    c.async_ensure_connected.assert_not_awaited()
    await shutdown(c)


@pytest.mark.parametrize("motor", ["back", "legs", "head", "feet"])
@pytest.mark.parametrize("direction", ["up", "down"])
async def test_native_timed_move_owns_cadence_and_exact_release(hass, motor, direction):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr

    c = runtime(hass)
    c.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(const.DOMAIN, {})[c.entry.entry_id] = c
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=c.entry.entry_id, identifiers={(const.DOMAIN, c.address)}
    )
    await services.async_register_services(hass)
    times = []

    async def record(*_args, **_kwargs):
        times.append(asyncio.get_running_loop().time())

    c.client.write_gatt_char.side_effect = record
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {
                "device_id": [device.id],
                "motor": motor,
                "direction": direction,
                "duration_ms": 650,
            },
            blocking=True,
        )
    command = selected_sections_frame(frozenset({motor}), direction == "up").hex()
    assert frames(c.client) == [command] * 3 + ["ff00"]
    assert [round(t - times[0], 3) for t in times] == [0, 0.3, 0.6, 0.65]
    await shutdown(c)
