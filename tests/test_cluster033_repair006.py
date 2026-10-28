"""Real HA options, all-target native preflight and supplemental ROW Reset proof."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import _async_update_listener, _build_paired_children
from custom_components.adjustable_bed.button import ControllerActionButton, _button_entities_for
from custom_components.adjustable_bed.cluster033_profiles import APP_LAYOUTS, DEFAULT_LAYOUTS
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_devices import child_device_info
from custom_components.adjustable_bed.pairing import get_child
from custom_components.adjustable_bed.services import async_register_services

from .test_cluster033 import coordinator as transport

NONDEFAULTS = [
    (app, layout)
    for app in ("ergo_slim", "ergomotion_app", "tempur_au", "qplus_app", "row_control")
    for layout in APP_LAYOUTS[app]
    if layout != DEFAULT_LAYOUTS[app]
]
RESET = bytes.fromhex("e5fe1600100008ee")
ZERO = bytes.fromhex("e5fe160000000006")


@pytest.fixture(autouse=True)
async def cleanup(hass, monkeypatch):
    # The HA options manager and update listener remain real; dependency setup
    # is outside this no-radio lifecycle test, as is the reload boundary below.
    monkeypatch.setattr("homeassistant.config_entries.async_process_deps_reqs", AsyncMock())
    yield
    for coord in hass.data.get("repair006_coordinators", []):
        await coord.async_shutdown()


def entry(hass, app, layout=None, **fields):
    number = len(hass.config_entries.async_entries(DOMAIN)) + 1
    data = {
        "address": f"AA:33:06:00:00:{number:02X}",
        "name": f"App {number}",
        "bed_type": app,
        "product_type": layout or DEFAULT_LAYOUTS.get(app),
        "protocol_variant": "auto",
        "motor_count": 2,
        "disable_angle_sensing": app != "serta_mp_remote",
        "octo_pin": "stale",
        "richmat_remote": "stale",
        **fields,
    }
    result = MockConfigEntry(
        domain=DOMAIN, title=f"App {number}", unique_id=data["address"], data=data, version=4
    )
    result.add_to_hass(hass)
    result.mock_state(hass, ConfigEntryState.LOADED)
    return result


def coordinator(hass, config):
    result = AdjustableBedCoordinator(hass, config)
    hass.data.setdefault("repair006_coordinators", []).append(result)
    return result


async def live(hass, monkeypatch, config, *, install=True):
    coord = coordinator(hass, config)
    client = transport().client

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    coord._client = client
    ctrl = await create_controller(
        coord,
        config.data["bed_type"],
        protocol_variant=config.data.get("protocol_variant", "auto"),
        client=client,
    )
    coord._controller, coord._ready = ctrl, True
    monkeypatch.setattr(ctrl, "_wait", AsyncMock(return_value=False))
    monkeypatch.setattr(coord, "async_ensure_connected", AsyncMock(return_value=True))
    await ctrl.start_notify(coord._handle_position_update)
    client.write_gatt_char.reset_mock()
    ctrl._wait.reset_mock()
    coord.async_ensure_connected.reset_mock()
    if install:
        hass.data.setdefault(DOMAIN, {})[config.entry_id] = coord
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config.entry_id, **coord.device_info
    )
    return coord, ctrl, client, device


def frames(client):
    return [c.args[1] for c in client.write_gatt_char.await_args_list]


async def save_options(hass, config, step="settings", **changes):
    menu = await hass.config_entries.options.async_init(config.entry_id)
    result = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": step}
    )
    assert result["type"] == "form", result
    submitted = {**result["data_schema"]({}), **changes}
    result = await hass.config_entries.options.async_configure(result["flow_id"], submitted)
    for _ in range(2):
        if result["type"] != "form":
            break
        assert not result.get("errors"), result
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], result["data_schema"]({})
        )
    assert result["type"] == "create_entry", result


@pytest.mark.parametrize("app,layout", NONDEFAULTS)
async def test_ordinary_options_reload_preserves_owned_app_layout(
    hass, monkeypatch, enable_custom_integrations, app, layout
):
    config = entry(hass, app, layout, protocol_variant="side_b" if app == "qplus_app" else "auto")
    initial = coordinator(hass, config)
    await initial.async_prime_offline_controller()
    before = initial.capability_controller
    expected_actions = {(a.key, a.mask, a.mode) for a in before.profile.actions}
    remove_listener = config.add_update_listener(_async_update_listener)
    reload = AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    try:
        await save_options(hass, config, idle_disconnect_seconds=47)
        await hass.async_block_till_done()
        reload.assert_any_await(config.entry_id)
    finally:
        remove_listener()
    fresh, ctrl, client, device = await live(hass, monkeypatch, config)
    assert ctrl.profile.layout == layout
    assert config.data["product_type"] == layout
    assert {(a.key, a.mask, a.mode) for a in ctrl.profile.actions} == expected_actions
    assert "octo_pin" not in config.data and "richmat_remote" not in config.data
    if app == "qplus_app":
        assert config.data["protocol_variant"] == "side_b"
    await async_register_services(hass)
    if app == "qplus_app" and layout == "MX":
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device.id], "control": "mx_memory1", "duration": 0.1},
            blocking=True,
        )
        assert frames(client) == [bytes.fromhex("040200010000"), b"\0\xb0", b"\0\xb0", b"\0\xb0"]
    if app == "row_control" and layout == "Zero-G Box":
        assert not ctrl.controller_state_sensor_specs
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device.id], "control": "lounge", "duration": 0.1},
            blocking=True,
        )
        assert frames(client) == [bytes.fromhex("e5fe160000010005"), ZERO]
        client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device.id], "control": "massage_head", "duration": 0.1},
            blocking=True,
        )
        assert frames(client) == [bytes.fromhex("e5fe1650000000b6"), ZERO]
    assert fresh.entry.data["idle_disconnect_seconds"] == 47


def paired_entry(hass, app, left_layout, right_layout, **extra):
    children = [
        {
            "side": side,
            "address": address,
            "name": side,
            "bed_type": app,
            "product_type": layout,
            "protocol_variant": ("side_a" if side == "left" else "side_b")
            if app == "qplus_app"
            else "auto",
            "motor_count": 2,
            "has_massage": False,
            "disable_angle_sensing": app != "serta_mp_remote",
            "octo_pin": "stale",
            **extra.get(side, {}),
        }
        for side, address, layout in (
            ("left", "AA:33:06:01:00:01", left_layout),
            ("right", "AA:33:06:01:00:02", right_layout),
        )
    ]
    config = MockConfigEntry(
        domain=DOMAIN,
        title="App pair",
        data={
            "pair_id": "repair006",
            "pair_mode": "separate_address",
            "pair_schema_version": 1,
            "pair_children": children,
            "bed_type": app,
            "name": "App pair",
        },
        version=4,
    )
    config.add_to_hass(hass)
    config.mock_state(hass, ConfigEntryState.LOADED)
    return config


@pytest.mark.parametrize("app,layout", NONDEFAULTS)
async def test_native_child_settings_and_shared_save_preserve_each_layout(
    hass, monkeypatch, enable_custom_integrations, app, layout
):
    partner = next(v for v in APP_LAYOUTS[app] if v != layout)
    config = paired_entry(hass, app, layout, partner)
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(return_value=True))
    remove_listener = config.add_update_listener(_async_update_listener)
    try:
        for side in ("left", "right"):
            await save_options(hass, config, step=side + "_settings", idle_disconnect_seconds=49)
            await hass.async_block_till_done()
            hass.config_entries.async_reload.assert_awaited_with(config.entry_id)
            hass.config_entries.async_reload.reset_mock()
            assert get_child(config.data, "left")["product_type"] == layout
            assert get_child(config.data, "right")["product_type"] == partner
        await save_options(hass, config, idle_disconnect_seconds=57)
        await hass.async_block_till_done()
        hass.config_entries.async_reload.assert_awaited_with(config.entry_id)
    finally:
        remove_listener()
    rebuilt = _build_paired_children(hass, config)
    hass.data.setdefault("repair006_coordinators", []).extend(rebuilt.values())
    for child in rebuilt.values():
        await child.async_prime_offline_controller()
    assert {s: c.capability_controller.profile.layout for s, c in rebuilt.items()} == {
        "left": layout,
        "right": partner,
    }
    assert all("octo_pin" not in get_child(config.data, s) for s in rebuilt)
    if app == "qplus_app":
        assert {s: c.entry.data["protocol_variant"] for s, c in rebuilt.items()} == {
            "left": "side_a",
            "right": "side_b",
        }


@pytest.mark.parametrize("selector", ["side_a", "side_b", "both"])
async def test_options_preserve_qplus_wire_selector(
    hass, monkeypatch, enable_custom_integrations, selector
):
    config = entry(hass, "qplus_app", "M3", protocol_variant=selector)
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(return_value=True))
    await save_options(hass, config, idle_disconnect_seconds=48)
    _, _, client, device = await live(hass, monkeypatch, config)
    await async_register_services(hass)
    await call(hass, device, "hold_control", control="head_up", duration=0.1)
    expected = {
        "side_a": ("e6fe16010000000103", "e6fe16000000000104"),
        "side_b": ("e6fe16010000000202", "e6fe16000000000203"),
        "both": ("e5fe160100000005", "e5fe160000000006"),
    }
    assert frames(client) == [bytes.fromhex(v) for v in expected[selector]]


async def test_options_preserve_custom_serta_memories_per_physical_child(
    hass, monkeypatch, enable_custom_integrations
):
    memories = {
        side: {
            f"serta_mp_memory_{slot}_{axis}": value
            for slot in range(1, 5)
            for axis, value in (("head", head), ("foot", foot))
        }
        for side, head, foot in (("left", 60, 45), ("right", 0, 0))
    }
    config = paired_entry(
        hass,
        "serta_mp_remote",
        DEFAULT_LAYOUTS["serta_mp_remote"],
        DEFAULT_LAYOUTS["serta_mp_remote"],
        **memories,
    )
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(return_value=True))
    for step in ("left_settings", "right_settings", "settings"):
        await save_options(hass, config, step=step, idle_disconnect_seconds=48)
    children = _build_paired_children(hass, config)
    hass.data.setdefault("repair006_coordinators", []).extend(children.values())
    for side, child in children.items():
        await child.async_prime_offline_controller()
        assert all(child.entry.data[k] == v for k, v in memories[side].items())
        assert child.capability_controller._memories == (
            ((60, 45),) * 4 if side == "left" else ((0, 0),) * 4
        )


async def pair(hass, monkeypatch, app, layout=None):
    rows = {
        s: await live(hass, monkeypatch, entry(hass, app, layout), install=False)
        for s in ("left", "right")
    }
    config = paired_entry(hass, app, layout or DEFAULT_LAYOUTS[app], layout or DEFAULT_LAYOUTS[app])
    owner = PairedBedCoordinator(hass, config, {s: r[0] for s, r in rows.items()})
    hass.data.setdefault(DOMAIN, {})[config.entry_id] = owner
    registry = dr.async_get(hass)
    parent = registry.async_get_or_create(config_entry_id=config.entry_id, **owner.device_info)
    children = {
        s: registry.async_get_or_create_child(
            config_entry_id=config.entry_id, **child_device_info(owner, s)
        )
        for s in rows
    }
    return owner, parent, children, rows


async def call(hass, device, action, **fields):
    await hass.services.async_call(
        DOMAIN, action, {"device_id": [device.id], **fields}, blocking=True
    )


@pytest.mark.parametrize("shape", ["standalone", "paired", "multi_target"])
@pytest.mark.parametrize("offline", [False, True])
async def test_serta_native_all_axis_all_target_preflight(hass, monkeypatch, shape, offline):
    """An earlier valid legs request must not write before back=61 is refused."""
    if shape == "paired":
        owner, parent, _, rows = await pair(hass, monkeypatch, "serta_mp_remote")
        devices = [parent.id]
        targets = [r[0] for r in rows.values()]
        clients = [r[2] for r in rows.values()]
    else:
        rows = [
            await live(hass, monkeypatch, entry(hass, "serta_mp_remote"))
            for _ in range(2 if shape == "multi_target" else 1)
        ]
        devices = [r[3].id for r in rows]
        targets, clients = [r[0] for r in rows], [r[2] for r in rows]
    for coord in targets:
        if offline:
            coord._controller = None
            coord._client.is_connected = False
            await coord.async_prime_offline_controller()
        monkeypatch.setattr(
            coord, "async_execute_command_group", AsyncMock(wraps=coord.async_execute_command_group)
        )
    await async_register_services(hass)
    with pytest.raises((ServiceValidationError, ValueError)) as rejection:
        await hass.services.async_call(
            DOMAIN,
            "set_positions",
            {
                "device_id": devices,
                "positions": [{"motor": "legs", "position": 35}, {"motor": "back", "position": 61}],
            },
            blocking=True,
        )
    assert all(not frames(c) for c in clients)
    for coord in targets:
        coord.async_execute_command_group.assert_not_awaited()
        # Connected validation failures may reset the existing idle timer;
        # none may reconnect for preflight or admit movement.
        assert all(
            c.kwargs == {"reset_timer": True} for c in coord.async_ensure_connected.await_args_list
        )
        if offline:
            coord.async_ensure_connected.assert_not_awaited()
    assert isinstance(rejection.value, ServiceValidationError)


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"back_max_angle": 90, "legs_max_angle": 90},
        {"back_max_angle": 20, "legs_max_angle": 20},
    ],
)
async def test_serta_native_endpoints_ignore_generic_overrides(hass, monkeypatch, overrides):
    coord, ctrl, client, device = await live(
        hass, monkeypatch, entry(hass, "serta_mp_remote", **overrides)
    )
    await async_register_services(hass)
    await call(
        hass,
        device,
        "set_positions",
        positions=[{"motor": "legs", "position": 45}, {"motor": "back", "position": 60}],
    )
    # Accepted calibrated maxima 11667 foot and 15500 head; other axis is 0x8000.
    assert frames(client) == [bytes.fromhex("e5fe170080932dc5"), bytes.fromhex("e5fe178c3c0080bd")]
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await call(
            hass,
            device,
            "set_positions",
            positions=[{"motor": "back", "position": 60}, {"motor": "legs", "position": 46}],
        )
    assert frames(client) == []


async def validation_target(hass, monkeypatch, **fields):
    config = entry(hass, "okimat", disable_angle_sensing=False, **fields)
    coord = coordinator(hass, config)
    coord._offline_controller = await create_controller(
        coord, "okimat", protocol_variant="auto", client=None
    )
    hass.data.setdefault(DOMAIN, {})[config.entry_id] = coord
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config.entry_id, **coord.device_info
    )
    # Validation is real; only the eventual motor execution boundary is a spy.
    monkeypatch.setattr(coord, "async_execute_command_group", AsyncMock())
    return coord, device


async def test_other_bed_configurable_limits_remain_in_registered_preflight(hass, monkeypatch):
    coord, device = await validation_target(hass, monkeypatch, legs_max_angle=30)
    await async_register_services(hass)
    with pytest.raises(ServiceValidationError):
        await call(hass, device, "set_positions", positions=[{"motor": "legs", "position": 31}])
    coord.async_execute_command_group.assert_not_awaited()
    await call(hass, device, "set_positions", positions=[{"motor": "legs", "position": 30}])
    coord.async_execute_command_group.assert_awaited_once()


async def test_later_native_target_preflight_cannot_start_earlier_valid_bed(hass, monkeypatch):
    earlier, first = await validation_target(hass, monkeypatch)
    later, _, client, second = await live(hass, monkeypatch, entry(hass, "serta_mp_remote"))
    monkeypatch.setattr(
        later, "async_execute_command_group", AsyncMock(wraps=later.async_execute_command_group)
    )
    await async_register_services(hass)
    requests = [{"motor": "legs", "position": 35}, {"motor": "back", "position": 61}]
    # Establish that the earlier actual bed accepts this complete plan.
    await call(hass, first, "set_positions", positions=requests)
    earlier.async_execute_command_group.assert_awaited_once()
    earlier.async_execute_command_group.reset_mock()
    with pytest.raises((ServiceValidationError, ValueError)) as rejection:
        await hass.services.async_call(
            DOMAIN,
            "set_positions",
            {
                "device_id": [first.id, second.id],
                "positions": requests,
            },
            blocking=True,
        )
    earlier.async_execute_command_group.assert_not_awaited()
    later.async_execute_command_group.assert_not_awaited()
    assert frames(client) == []
    assert isinstance(rejection.value, ServiceValidationError)


@pytest.mark.parametrize("layout", ["Elevate", "Lifestyle", "Curve"])
async def test_row_reset_supplemental_production_paths(hass, monkeypatch, layout):
    """Three supplemental V04 cases; original 370 receipt IDs stay unchanged."""
    coord, ctrl, client, device = await live(
        hass, monkeypatch, entry(hass, "row_control", layout, motor_pulse_count=3)
    )
    await async_setup_component(hass, "button", {})
    buttons = [
        b
        for b in _button_entities_for(hass, coord)
        if isinstance(b, ControllerActionButton) and b._spec.key == "reset"
    ]
    assert len(buttons) == 1
    button = buttons[0]
    button.entity_id = "button.row_reset"
    await hass.data["button"].async_add_entities([button])
    assert hass.states.get(button.entity_id).attributes["held_control"] == "reset"
    await hass.services.async_call(
        "button", "press", {"entity_id": button.entity_id}, blocking=True
    )
    assert frames(client) == [RESET] * 3 + [ZERO]
    assert [c.args[0] for c in ctrl._wait.await_args_list] == [100, 100, 100]
    await async_register_services(hass)
    client.write_gatt_char.reset_mock()
    await call(hass, device, "hold_control", control="reset", duration=0.3)
    assert frames(client) == [RESET] * 3 + [ZERO]
    owner, parent, children, rows = await pair(hass, monkeypatch, "row_control", layout)
    for side in ("left", "right", "both"):
        for r in rows.values():
            r[2].write_gatt_char.reset_mock()
        await call(hass, parent, "hold_control", side=side, control="reset", duration=0.1)
        for s, row in rows.items():
            assert frames(row[2]) == ([RESET, ZERO] if side in (s, "both") else [])
    for r in rows.values():
        r[2].write_gatt_char.reset_mock()
    started = asyncio.Event()
    right = rows["right"][0]

    async def wait_cancel(delay, *, cleanup=False):
        started.set()
        await right.cancel_command.wait()
        return True

    monkeypatch.setattr(rows["right"][1], "_wait", wait_cancel)
    task = asyncio.create_task(
        call(hass, children["right"], "hold_control", control="reset", duration=60)
    )
    await asyncio.wait_for(started.wait(), 2)
    await call(hass, children["right"], "stop_all")
    await asyncio.wait_for(task, 2)
    assert frames(rows["right"][2]) == [RESET, ZERO, ZERO]
    assert frames(rows["left"][2]) == []
    for inactive in ("Lifestyle Plus", "Zero-G Box"):
        inactive_coord, disabled, transport_client, target_device = await live(
            hass, monkeypatch, entry(hass, "row_control", inactive)
        )
        assert "reset" not in disabled.held_control_options
        assert all(
            b._spec.key != "reset"
            for b in _button_entities_for(hass, inactive_coord)
            if isinstance(b, ControllerActionButton)
        )
        with pytest.raises(ServiceValidationError):
            await call(hass, target_device, "hold_control", control="reset", duration=0.1)
        assert frames(transport_client) == []
