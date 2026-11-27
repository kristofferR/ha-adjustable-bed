"""iFit's accepted literals through native controls and exact BLE sessions."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.ifit.controller import IfitController
from custom_components.adjustable_bed.codec import okin_5a as codec
from custom_components.adjustable_bed.profiles.ifit import IFIT
from tests.hold_lease_wire import virtual_clock

ROWS = json.loads((Path(__file__).parent / "fixtures/ifit/vectors.json").read_text())
ADDRESS = "AA:BB:CC:DD:01:25"
ACTIONS = {
    "lightsOff": "light_off",
    "toggleLights": "light_toggle",
    "lightsOn": "light_on",
    "massageFootSub": "massage_foot_down",
    "massageFootAdd": "massage_foot_up",
    "massageHeadSub": "massage_head_down",
    "massageHeadAdd": "massage_head_up",
    "massageStop": "massage_off",
    "massageWave1": "massage_wave_1",
    "massageWave2": "massage_wave_2",
    "massageWave3": "massage_wave_3",
    "memoryFlat": "flat",
    "memoryZero": "zero_g",
    "memoryLounge": "lounge",
    "memoryRead": "incline",
    "memoryAntiSnore": "anti_snore",
    "memoryStretch": "stretch",
    "memoryInverse": "inverse",
    "stopCommand": "stop",
    "headUp": "head_up",
    "headDown": "head_down",
    "footUp": "feet_up",
    "footDown": "feet_down",
    "legUp": "legs_up",
    "legDown": "legs_down",
    "headUpMax": "head_up_max",
    "headDownMax": "head_down_max",
    "footUpMax": "feet_up_max",
    "footDownMax": "feet_down_max",
    "legUpMax": "legs_up_max",
    "legDownMax": "legs_down_max",
    "setMemoryZero": "save_zero_g",
    "setMemoryLounge": "save_lounge",
    "setMemoryRead": "save_incline",
    "setMemoryAntiSnore": "save_anti_snore",
}


@dataclass(eq=False)
class Char:
    uuid: str
    properties: list[str]
    handle: int
    descriptors: list[object]


def gatt(properties=("write", "write-without-response")):
    transport = codec.TRANSPORTS["nus"]
    char = Char(uuid=transport.write_uuid, properties=list(properties), handle=25, descriptors=[])
    return [
        SimpleNamespace(
            uuid=transport.service_uuid,
            characteristics=[char],
            get_characteristic=lambda uuid: char if uuid == char.uuid else None,
        )
    ]


def client():
    return SimpleNamespace(
        services=gatt(),
        is_connected=True,
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )


async def connected():
    coordinator = MagicMock(client=client(), cancel_command=asyncio.Event(), motor_pulse_count=2)
    controller = IfitController(coordinator)
    coordinator.controller = controller
    await controller.async_discover_capabilities()
    await controller.async_on_connect(SimpleNamespace(is_current=lambda: True))
    coordinator.client.write_gatt_char.reset_mock()
    return controller, coordinator


def written(c):
    return [bytes(call.args[1]) for call in c.write_gatt_char.call_args_list]


@pytest.mark.parametrize("row", ROWS, ids=lambda row: row["id"])
def test_all_accepted_literals_use_the_existing_codec(row):
    data = bytes.fromhex(row["expected_bytes"])
    actual = codec.request(data[1]) if len(data) == 4 else codec.command(data[5], data[4])
    assert actual == data
    assert actual == (IFIT.wake[0] if len(data) == 4 else IFIT.frame(ACTIONS[row["action"]]))


def test_profile_census_does_not_promote_unused_asset_keys():
    assert len(ROWS) == 36
    assert len(IFIT.frames) == 35
    assert {bytes.fromhex(r["expected_bytes"]) for r in ROWS} == {*IFIT.frames.values(), *IFIT.wake}


async def test_native_entities_and_services_reach_every_frozen_frame(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
):
    mock_bleak_client.services = gatt()
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="iFit",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "iFit",
            const.CONF_BED_TYPE: "ifit",
            const.CONF_MOTOR_COUNT: 3,
            const.CONF_HAS_MASSAGE: True,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_PROTOCOL_VARIANT: "auto",
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[const.DOMAIN][entry.entry_id]
    controller = coordinator.controller
    assert isinstance(controller, IfitController)
    assert codec.WAKE in written(mock_bleak_client)
    assert mock_bleak_client.write_gatt_char.call_args_list[0].kwargs["response"] is False
    assert not mock_bleak_client.start_notify.called
    registry = er.async_get(hass)
    entities = [e for e in registry.entities.values() if e.config_entry_id == entry.entry_id]
    device = entities[0].device_id
    entity_by_key = {e.unique_id.removeprefix(ADDRESS + "_"): e for e in entities}

    async def button(key):
        entity = next(e for e in entities if e.unique_id.endswith("_" + key))
        assert not entity.disabled_by, (key, entity.disabled_by)
        await hass.services.async_call(
            "button", "press", {"entity_id": entity.entity_id}, blocking=True
        )

    with virtual_clock():
        for row in ROWS[:-1]:
            action = ACTIONS[row["action"]]
            mock_bleak_client.write_gatt_char.reset_mock()
            if action in {"head_up", "head_down", "feet_up", "feet_down", "legs_up", "legs_down"}:
                axis, direction = action.rsplit("_", 1)
                await hass.services.async_call(
                    const.DOMAIN,
                    "timed_move",
                    {
                        "device_id": device,
                        "motor": axis,
                        "direction": direction,
                        "duration_ms": 100,
                    },
                    blocking=True,
                )
            elif action.startswith("save_"):
                await hass.services.async_call(
                    const.DOMAIN,
                    "ifit_save_preset",
                    {
                        "device_id": device,
                        "preset": action.removeprefix("save_"),
                    },
                    blocking=True,
                )
            elif action in {"flat", "zero_g", "anti_snore", "lounge", "incline"}:
                await button("preset_" + action)
            elif action in {"light_on", "light_off"}:
                entity = next(e for e in entities if e.domain == "light")
                await hass.services.async_call(
                    "light",
                    "turn_on" if action == "light_on" else "turn_off",
                    {"entity_id": entity.entity_id},
                    blocking=True,
                )
            elif action == "stop":
                await button("stop")
            else:
                key = {"light_toggle": "light_position", "massage_off": "massage_all_off"}.get(
                    action, action
                )
                await button(key)
            assert bytes.fromhex(row["expected_bytes"]) in written(mock_bleak_client), (
                action,
                entity_by_key.keys(),
            )
            assert all(
                call.kwargs["response"] is True
                for call in mock_bleak_client.write_gatt_char.call_args_list
            )
    assert {s.key for s in controller.motor_control_specs} == {"head", "feet", "legs"}
    assert controller.light_state_is_assumed
    assert not controller.supports_single_address_pairing
    assert controller.memory_slot_count == 0
    assert not controller.supports_preset_tv
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    ("control", "duration", "interval", "count"),
    [
        ("head_up", 500, 220, 3),
        ("legs_down", 500, 220, 3),
        ("inverse", 350, 100, 4),
        ("massage_head_up", 2200, 1000, 3),
        ("flat", 4000, 250, 12),
    ],
)
async def test_screen_holds_end_refresh_without_trailing_stop(control, duration, interval, count):
    ctrl, c = await connected()
    times = []
    with virtual_clock() as clock:
        c.client.write_gatt_char.side_effect = lambda *a, **kw: times.append(
            round(clock.now * 1000)
        )
        await ctrl.hold_control(control, duration)
    assert written(c.client) == [IFIT.frame(control)] * count
    assert times == list(range(0, count * interval, interval))


@pytest.mark.parametrize(
    ("control", "threshold"), [("light_position", 3000), ("light_massage", 1000)]
)
async def test_page_specific_light_thresholds(control, threshold):
    ctrl, c = await connected()
    with virtual_clock():
        await ctrl.hold_control(control, threshold + 500)
    assert (
        written(c.client)
        == [IFIT.frame("light_toggle")] * (threshold // 250) + [IFIT.frame("light_off")] * 2
    )


async def test_preset_hold_alone_never_saves_and_combined_save_has_flat_precondition():
    ctrl, c = await connected()
    with virtual_clock():
        await ctrl.hold_control("zero_g", 3500)
    assert set(written(c.client)) == {IFIT.frame("zero_g")}
    c.client.write_gatt_char.reset_mock()
    times = []
    with virtual_clock() as clock:
        c.client.write_gatt_char.side_effect = lambda *a, **kw: times.append(
            (round(clock.now * 1000), a[1])
        )
        await ctrl.save_named_preset("zero_g")
    assert times[0] == (0, IFIT.frame("flat"))
    assert [t for t, f in times if f == IFIT.frame("flat")] == list(range(0, 3000, 250))
    assert [t for t, f in times if f == IFIT.frame("zero_g")] == list(range(0, 3000, 100))
    assert times[-1] == (3000, IFIT.frame("save_zero_g"))
    c.client.write_gatt_char.reset_mock()
    with virtual_clock():
        await ctrl.hold_control("zero_g", 3200)
    assert IFIT.frame("save_zero_g") not in written(c.client)


@pytest.mark.parametrize(
    "action", ["stop", "head_up_max", "zero_g", "light_on", "light_off", "light_toggle"]
)
@pytest.mark.parametrize("write_latency", [0, 0.02])
async def test_direct_voice_forwarding_burst(action, write_latency):
    ctrl, c = await connected()
    times = []
    with virtual_clock() as clock:

        async def write(*args, **kwargs):
            times.append(round(clock.now * 1000))
            await asyncio.sleep(write_latency)

        c.client.write_gatt_char.side_effect = write
        await ctrl.perform_action(action)
    assert times == ([250] if action == "light_toggle" else [250, 500, 750])
    assert set(written(c.client)) == {IFIT.frame(action)}


@pytest.mark.parametrize("replacement", ["disconnect", "client", "controller", "rediscover"])
async def test_old_operation_never_writes_to_replacement_session(replacement):
    ctrl, c = await connected()
    original = c.client

    async def replace(*args, **kwargs):
        if replacement == "disconnect":
            ctrl.on_disconnect()
        elif replacement == "client":
            c.client = client()
        elif replacement == "controller":
            c.controller = object()
        else:
            await ctrl.async_discover_capabilities()

    original.write_gatt_char.side_effect = replace
    with virtual_clock(), pytest.raises(ConnectionError):
        await ctrl.hold_control("head_up", 1000)
    assert written(original) == [IFIT.frame("head_up")]
    if replacement == "client":
        assert written(c.client) == []


async def test_cancelled_save_has_no_latch_or_delayed_save():
    ctrl, c = await connected()

    def cancel_on_flat(*args, **kwargs):
        c.cancel_command.set()

    c.client.write_gatt_char.side_effect = cancel_on_flat
    with virtual_clock():
        await ctrl.save_named_preset("zero_g")
    assert written(c.client) == [IFIT.frame("flat")]
    c.client.write_gatt_char.reset_mock(side_effect=True)
    c.cancel_command.clear()
    with virtual_clock():
        await ctrl.hold_control("zero_g", 3200)
    assert IFIT.frame("save_zero_g") not in written(c.client)


async def test_expired_frame_queued_on_ble_lock_is_not_written():
    ctrl, c = await connected()
    with virtual_clock():
        await ctrl._ble_lock.acquire()
        task = asyncio.create_task(ctrl.hold_control("head_up", 100))
        await asyncio.sleep(0.2)
        ctrl._ble_lock.release()
        await task
    assert not written(c.client)


async def test_backend_write_settles_before_cancellation_releases_ble_lock():
    ctrl, c = await connected()
    submitted, finish = asyncio.Event(), asyncio.Event()

    async def slow(*args, **kwargs):
        submitted.set()
        await finish.wait()

    c.client.write_gatt_char.side_effect = slow
    task = asyncio.create_task(ctrl.hold_control("head_up", 1000))
    await submitted.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert ctrl._ble_lock.locked()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not ctrl._ble_lock.locked()
    assert written(c.client) == [IFIT.frame("head_up")]


async def test_manual_selection_owns_fixed_profile_fields(hass):
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    from tests.form_helpers import finish_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES["ifit"]})
    result = await flow.async_step_manual_entry({"address": ADDRESS})
    await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[const.CONF_MOTOR_COUNT] == 3
    assert saved[const.CONF_HAS_MASSAGE] is True
    assert saved.get(const.CONF_READ_POSITIONS, False) is False
    assert saved[const.CONF_MOTOR_PULSE_DELAY_MS] == 220
    assert resolve_profile_id(saved) == "ifit"
    assert per_side_profile("ifit", "auto") is not None


@pytest.mark.parametrize("props", [("write",), ("write-without-response",), ("read",)])
async def test_no_property_based_write_mode_fallback(props):
    ctrl, c = await connected()
    c.client.services = gatt(props)
    with pytest.raises(ConnectionError):
        await ctrl.async_discover_capabilities()
    with pytest.raises(ConnectionError):
        await ctrl.perform_action("head_up_max")
    assert written(c.client) == []


async def test_startup_failure_does_not_admit_controls():
    ctrl, c = await connected()
    await ctrl.async_discover_capabilities()
    c.client.write_gatt_char.side_effect = ConnectionError("startup failed")
    with pytest.raises(ConnectionError):
        await ctrl.async_on_connect(SimpleNamespace(is_current=lambda: True))
    c.client.write_gatt_char.reset_mock(side_effect=True)
    with virtual_clock(), pytest.raises(ConnectionError):
        await ctrl.perform_action("head_up_max")
    assert written(c.client) == []


async def target(hass):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    number = len(hass.data.get("ifit_test_targets", [])) + 1
    address = f"AA:BB:CC:DD:25:{number:02X}"
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="iFit",
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "iFit",
            const.CONF_BED_TYPE: "ifit",
            const.CONF_PROTOCOL_VARIANT: "auto",
            const.CONF_MOTOR_COUNT: 3,
            const.CONF_HAS_MASSAGE: True,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            "disconnect_after_command": False,
            "idle_disconnect_seconds": 0,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    c = client()
    c.disconnect = AsyncMock()
    coordinator._client = c
    controller = IfitController(coordinator)
    coordinator._controller = coordinator._offline_controller = controller
    await controller.async_discover_capabilities()
    await controller.async_on_connect(SimpleNamespace(is_current=lambda: True))
    c.write_gatt_char.reset_mock()
    coordinator._ready = True
    entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coordinator
    hass.data.setdefault("ifit_test_targets", []).append(coordinator)
    device = dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=coordinator.device_info
    )
    return coordinator, controller, c, device


@pytest.fixture(autouse=True)
async def cleanup(hass):
    yield
    for coordinator in hass.data.get("ifit_test_targets", []):
        await coordinator.async_shutdown()


async def test_save_preflights_all_targets_before_any_flat_command(hass):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.beds.okin_nordic import OkinNordicController
    from custom_components.adjustable_bed.services import async_register_services

    first, second = await target(hass), await target(hass)
    second[0]._controller = second[0]._offline_controller = OkinNordicController(second[0])
    await async_register_services(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            const.DOMAIN,
            "ifit_save_preset",
            {
                "device_id": [first[3].id, second[3].id],
                "preset": "zero_g",
            },
            blocking=True,
        )
    assert not written(first[2])
    assert not written(second[2])


async def test_stop_during_service_import_cancels_pending_save_admission(hass, monkeypatch):
    from custom_components.adjustable_bed.beds.ifit import services
    from custom_components.adjustable_bed.services import async_register_services

    first, second = await target(hass), await target(hass)
    await async_register_services(hass)
    imported, proceed = asyncio.Event(), asyncio.Event()
    original = services.async_import_modules

    async def delayed(*args):
        imported.set()
        await proceed.wait()
        await original(*args)

    monkeypatch.setattr(services, "async_import_modules", delayed)
    with virtual_clock():
        task = asyncio.create_task(
            hass.services.async_call(
                const.DOMAIN,
                "ifit_save_preset",
                {
                    "device_id": [first[3].id, second[3].id],
                    "preset": "zero_g",
                },
                blocking=True,
            )
        )
        await imported.wait()
        await second[0].async_stop_command()
        second[2].write_gatt_char.reset_mock()
        proceed.set()
        await task
    assert not written(second[2])


async def test_paired_child_save_preserves_the_physical_target(hass):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.paired_devices import child_device_info
    from custom_components.adjustable_bed.services import async_register_services

    sides = {"left": await target(hass), "right": await target(hass)}
    entry = MockConfigEntry(domain=const.DOMAIN, data={const.CONF_PAIR_ID: "ifit-test"})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = PairedBedCoordinator(hass, entry, {side: value[0] for side, value in sides.items()})
    hass.data[const.DOMAIN][entry.entry_id] = pair
    registry = dr.async_get(hass)
    registry.async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=pair.device_info
    )
    right = registry.async_get_or_create_child_from_info(
        config_entry_id=entry.entry_id, device_info=child_device_info(pair, "right")
    )
    await async_register_services(hass)
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "ifit_save_preset",
            {
                "device_id": right.id,
                "preset": "lounge",
            },
            blocking=True,
        )
    assert written(sides["left"][2]) == []
    assert written(sides["right"][2])[-1] == IFIT.frame("save_lounge")


async def test_native_release_button_ends_refresh_without_explicit_stop(hass):
    from custom_components.adjustable_bed.button import ControllerActionButton

    coord, controller, c, _ = await target(hass)
    spec = next(s for s in controller.controller_button_specs if s.key == "ifit_release")
    button = ControllerActionButton(coord, spec)
    with virtual_clock():
        task = asyncio.create_task(
            coord.async_execute_controller_command(lambda ctrl: ctrl.hold_control("head_up", 5000))
        )
        await asyncio.sleep(0.3)
        await button.async_press()
        await task
    assert written(c) == [IFIT.frame("head_up")] * 2
    c.write_gatt_char.reset_mock()
    with virtual_clock():
        await coord.async_stop_command()
    assert written(c) == [IFIT.frame("stop")] * 3


async def test_sequential_pair_explicit_stop_reconnects_after_completed_max(hass, monkeypatch):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.paired_coordinator import (
        PairedBedCoordinator,
        PairedSideProxy,
    )

    sides = {side: await target(hass) for side in ("left", "right")}
    connects = []
    for coord, ctrl, c, _ in sides.values():

        async def connect(*args, coord=coord, ctrl=ctrl, c=c, **kwargs):
            connects.append(coord)
            if not c.is_connected:
                c.is_connected = True
                await ctrl.async_discover_capabilities()
                await ctrl.async_on_connect(SimpleNamespace(is_current=lambda: True))
            return True

        async def disconnect(*args, ctrl=ctrl, c=c, **kwargs):
            c.is_connected = False
            ctrl.on_disconnect()
            return True

        monkeypatch.setattr(coord, "async_connect", connect)
        monkeypatch.setattr(coord, "async_ensure_connected", connect)
        monkeypatch.setattr(coord, "async_disconnect", disconnect)
    entry = MockConfigEntry(domain=const.DOMAIN, data={const.CONF_PAIR_ID: "ifit-sequential-stop"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, entry, {side: t[0] for side, t in sides.items()}, connection_mode="sequential"
    )
    from homeassistant.helpers import device_registry as dr

    dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=pair.device_info
    )
    proxy = PairedSideProxy(pair, sides["left"][0], "left")
    specs = {s.key: s for s in sides["left"][1].controller_button_specs}
    maximum = ControllerActionButton(proxy, specs["head_up_max"])
    maximum.hass = hass
    release = ControllerActionButton(proxy, specs["ifit_release"])
    with virtual_clock():
        await maximum.async_press()
        assert written(sides["left"][2]) == [IFIT.frame("head_up_max")] * 3
        assert not sides["left"][0].is_connected
        sides["left"][2].write_gatt_char.reset_mock()
        sides["right"][2].write_gatt_char.reset_mock()
        connects.clear()
        await release.async_press()
        assert not connects
        assert written(sides["left"][2]) == []
        await pair.async_stop_command(side="left")
    assert written(sides["left"][2]) == [IFIT.wake[0]] + [IFIT.frame("stop")] * 3
    assert written(sides["right"][2]) == []


async def test_all_light_routes_update_the_primary_assumed_light(hass):
    from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedOnOffLight
    from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON

    coord, ctrl, c, _ = await target(hass)
    light = AdjustableBedOnOffLight(coord, LIGHT_DESCRIPTION)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    unsub = coord.register_controller_state_callback(light._handle_controller_state_update)
    try:
        with virtual_clock():
            # A toggle cannot establish an unknown starting estimate.
            await coord.async_execute_controller_command(lambda ctrl: ctrl.lights_toggle())
            assert UNDER_BED_LIGHTS_ON in coord.controller_state
            assert light.is_on is None
            await light.async_turn_on()
            assert light.is_on is True
            await coord.async_execute_controller_command(
                lambda ctrl: ctrl.hold_control("light_massage", 1500)
            )
            assert written(c)[-1] == IFIT.frame("light_off")
            assert light.is_on is False
            await coord.async_execute_controller_command(lambda ctrl: ctrl.lights_toggle())
            assert light.is_on is True
            await coord.async_execute_controller_command(
                lambda ctrl: ctrl.hold_control("light_position", 100)
            )
            assert light.is_on is False
            # Also cover the light-page button's native direct forwarding route.
            from custom_components.adjustable_bed.button import ControllerActionButton

            button = ControllerActionButton(
                coord, next(s for s in ctrl.controller_button_specs if s.key == "light_position")
            )
            button.hass = hass
            await button.async_press()
            assert light.is_on is True
            await light.async_turn_off()
            assert light.is_on is False
    finally:
        unsub()


@pytest.mark.parametrize("replacement", ["disconnect", "client", "controller", "rediscover"])
async def test_successful_stale_light_write_never_publishes_new_intent(hass, replacement):
    from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON

    coord, ctrl, c, _ = await target(hass)
    with virtual_clock():
        await coord.async_execute_controller_command(lambda ctrl: ctrl.lights_off())
        assert coord.controller_state[UNDER_BED_LIGHTS_ON] is False

        async def replace(*args, **kwargs):
            if replacement == "disconnect":
                ctrl.on_disconnect()
            elif replacement == "client":
                coord._client = client()
            elif replacement == "controller":
                coord._controller = IfitController(coord)
            else:
                await ctrl.async_discover_capabilities()

        c.write_gatt_char.side_effect = replace
        with pytest.raises(ConnectionError):
            await coord.async_execute_controller_command(lambda ctrl: ctrl.lights_on())
    assert coord.controller_state.get(UNDER_BED_LIGHTS_ON) is False
    coord._client, coord._controller = c, ctrl


async def test_light_intent_waits_for_successful_current_session_write(hass):
    from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON

    coord, ctrl, c, _ = await target(hass)
    submitted, finish = asyncio.Event(), asyncio.Event()

    async def slow(*args, **kwargs):
        submitted.set()
        await finish.wait()

    c.write_gatt_char.side_effect = slow
    with virtual_clock():
        task = asyncio.create_task(
            coord.async_execute_controller_command(lambda ctrl: ctrl.lights_on())
        )
        await submitted.wait()
        assert coord.controller_state.get(UNDER_BED_LIGHTS_ON) is None
        task.cancel()
        await asyncio.sleep(0)
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert coord.controller_state.get(UNDER_BED_LIGHTS_ON) is True


@pytest.mark.parametrize("write_latency", [0.08, 0.1])
async def test_native_save_skips_overdue_refreshes_and_attempts_save(hass, write_latency):
    from custom_components.adjustable_bed.services import async_register_services

    coord, ctrl, c, device = await target(hass)
    await async_register_services(hass)
    times = []
    with virtual_clock() as clock:

        async def write(char, frame, **kwargs):
            times.append((clock.now, bytes(frame)))
            await asyncio.sleep(write_latency)

        c.write_gatt_char.side_effect = write
        await hass.services.async_call(
            const.DOMAIN,
            "ifit_save_preset",
            {
                "device_id": device.id,
                "preset": "zero_g",
            },
            blocking=True,
        )
    assert times[0] == (0, IFIT.frame("flat"))
    saves = [t for t, f in times if f == IFIT.frame("save_zero_g")]
    assert len(saves) == 1
    assert 3 <= saves[0] <= 3 + write_latency + 0.000001
    assert times[-1][1] == IFIT.frame("save_zero_g")
    assert all(t < 3 for t, f in times if f != IFIT.frame("save_zero_g"))
    assert len(times) < 32  # At most one current batch, never all42 old refreshes.
    # The first recall may follow Flat in the same event. Other writes do not
    # replay expired50ms slots immediately after the prior acknowledgement.
    assert any(b[0] - a[0] > write_latency + 0.001 for a, b in zip(times, times[1:], strict=False))


async def test_native_save_reports_failed_save_instead_of_success(hass):
    from bleak.exc import BleakError
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.adjustable_bed.services import async_register_services

    coord, ctrl, c, device = await target(hass)
    await async_register_services(hass)
    with virtual_clock() as clock:

        async def write(char, frame, **kwargs):
            if frame == IFIT.frame("save_zero_g"):
                raise BleakError("save write failed")
            await asyncio.sleep(0.1)

        c.write_gatt_char.side_effect = write
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                const.DOMAIN,
                "ifit_save_preset",
                {
                    "device_id": device.id,
                    "preset": "zero_g",
                },
                blocking=True,
            )
        assert clock.now >= 3
    assert written(c)[-1] == IFIT.frame("save_zero_g")


@pytest.mark.parametrize(
    ("control", "threshold", "duration"),
    [
        ("light_massage", 1, 1500),
        ("light_position", 3, 3500),
        ("flat", 3, 4000),
    ],
)
async def test_hold_thresholds_follow_elapsed_time_with_slow_writes(
    hass, control, threshold, duration
):
    coord, ctrl, c, _ = await target(hass)
    times = []
    with virtual_clock() as clock:

        async def write(char, frame, **kwargs):
            times.append((clock.now, bytes(frame)))
            await asyncio.sleep(0.6)

        c.write_gatt_char.side_effect = write
        await coord.async_execute_controller_command(lambda c: c.hold_control(control, duration))
    assert times
    if control == "flat":
        assert all(t < threshold for t, f in times)
    else:
        assert IFIT.frame("light_off") in [f for t, f in times]
        assert all(
            f == IFIT.frame("light_toggle") if t < threshold else f == IFIT.frame("light_off")
            for t, f in times
        )
    assert all(
        b[0] - a[0] >= 0.749999 for a, b in zip(times, times[1:], strict=False) if a[1] == b[1]
    )


async def test_queued_toggle_crossing_off_threshold_uses_off(hass):
    coord, ctrl, c, _ = await target(hass)
    with virtual_clock():
        await ctrl._ble_lock.acquire()
        task = asyncio.create_task(
            coord.async_execute_controller_command(lambda c: c.hold_control("light_massage", 1500))
        )
        await asyncio.sleep(1.1)
        ctrl._ble_lock.release()
        await task
    assert written(c) and set(written(c)) == {IFIT.frame("light_off")}


async def test_diagnostic_notification_cleanup_preserves_control_and_stop(hass):
    from custom_components.adjustable_bed.ble_diagnostics import BLEDiagnosticRunner
    from custom_components.adjustable_bed.button import ControllerActionButton

    coord, ctrl, c, _ = await target(hass)
    runner = BLEDiagnosticRunner(hass, coord.address, capture_duration=0, coordinator=coord)
    runner._client = c
    runner._using_coordinator_connection = True
    with virtual_clock():
        await runner._subscribe_to_notifications([])
        assert runner._diagnostic_notifications_started
        await runner._unsubscribe_from_notifications([])
        assert not runner._diagnostic_notifications_started
        assert c.is_connected
        button = ControllerActionButton(
            coord, next(s for s in ctrl.controller_button_specs if s.key == "head_up_max")
        )
        button.hass = hass
        await button.async_press()
        await coord.async_stop_command()
    assert written(c) == [IFIT.frame("head_up_max")] * 3 + [IFIT.frame("stop")] * 3
    assert not c.start_notify.called and not c.stop_notify.called
    # Physical disconnect still retires the session, independently of cleanup.
    ctrl.on_disconnect()
    with pytest.raises(ConnectionError):
        await ctrl.perform_action("head_up_max")


async def test_save_attempts_after_refresh_write_crosses_threshold(hass):
    coord, ctrl, c, _ = await target(hass)
    times = []
    with virtual_clock() as clock:

        async def write(char, frame, **kwargs):
            times.append((clock.now, bytes(frame)))
            # The2.9s recall has already been admitted. Its acknowledgement
            # arrives after the former3.1s deadline, but SAVE must still run.
            await asyncio.sleep(0.25 if clock.now >= 2.899 else 0.007)

        c.write_gatt_char.side_effect = write
        await coord.async_execute_controller_command(lambda c: c.save_named_preset("zero_g"))
    assert times[-1][1] == IFIT.frame("save_zero_g")
    assert 3.14 < times[-1][0] < 3.16


async def test_skipped_mandatory_save_without_cancellation_is_an_error(hass, monkeypatch):
    from custom_components.adjustable_bed.command_scheduler import note_frame_skipped
    from custom_components.adjustable_bed.errors import BedCommandTimedOutError

    coord, ctrl, c, _ = await target(hass)
    original = ctrl._write_gatt_with_retry

    async def write(uuid, frame, **kwargs):
        if frame == IFIT.frame("save_zero_g"):
            note_frame_skipped()
            return
        await original(uuid, frame, **kwargs)

    monkeypatch.setattr(ctrl, "_write_gatt_with_retry", write)
    with virtual_clock(), pytest.raises(BedCommandTimedOutError):
        await coord.async_execute_controller_command(lambda c: c.save_named_preset("zero_g"))
