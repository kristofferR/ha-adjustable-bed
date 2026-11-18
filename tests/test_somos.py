"""Somos real HA callers, explicit setup and connection ownership."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.keeson import somos as bed
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import somos as app
from custom_components.adjustable_bed.profiles.keeson import encode
from tests.hold_lease_wire import virtual_clock
from tests.somos_vectors import VECTORS

ADDRESS = "AA:BB:CC:DD:00:99"


class Char:
    def __init__(self, uuid, properties, handle):
        self.uuid, self.properties, self.handle = uuid, properties, handle
        self.descriptors = []


def gatt(variant):
    transport = bed.codec.TRANSPORTS[app.PRODUCTS[variant].profile.transport]
    tx = Char(transport.write_uuid, ["write"], 1)
    rx = Char(transport.notify_uuid, ["notify"], 2)

    def service(uuid, chars):
        return SimpleNamespace(
            uuid=uuid,
            characteristics=chars,
            get_characteristic=lambda key: next((c for c in chars if c.uuid == key), None),
        )

    return (
        [
            service(transport.service_uuid, [tx]),
            service("0000ffe0-0000-1000-8000-00805f9b34fb", [rx]),
        ]
        if variant in ("a", "c")
        else [service(transport.service_uuid, [tx, rx])]
    )


def entry(hass, variant, address=ADDRESS):
    from custom_components.adjustable_bed.setup_questions import _somos_settings

    data = {
        CONF_ADDRESS: address,
        CONF_NAME: "Somos",
        const.CONF_BED_TYPE: "somos",
        const.CONF_PROTOCOL_VARIANT: variant,
        const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        **_somos_settings({const.CONF_PROTOCOL_VARIANT: variant}),
    }
    e = MockConfigEntry(domain=const.DOMAIN, title="Somos", unique_id=address, data=data)
    e.add_to_hass(hass)
    return e


def written(client):
    return [bytes(call.args[1]).hex() for call in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("variant", "abcde")
async def test_real_setup_native_entities_and_every_accepted_caller(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, variant
):
    mock_bleak_client.services = gatt(variant)
    e = entry(hass, variant)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    target = hass.data[const.DOMAIN][e.entry_id]
    c = target.controller
    assert isinstance(c, bed.SomosController)
    registry = er.async_get(hass)
    for axis, _, _ in app.PRODUCTS[variant].axes:
        entity_id = registry.async_get_entity_id("cover", const.DOMAIN, f"{ADDRESS}_{axis}")
        assert entity_id is not None
        assert hass.states.get(entity_id).attributes["hold_lease_mode"] == "stream"
    assert not c.supports_single_address_pairing
    assert not c.supports_memory_programming
    device = next(
        item.device_id for item in registry.entities.values() if item.config_entry_id == e.entry_id
    )
    # Every frozen row reaches a real registered caller, including the D/E
    # neutral-axis holds. No direct controller-only vector can hide a missing UI.
    controls = {"foot": "feet", "lumbar_tilt": "lumbar_tilt"}
    aliases = {
        "zero_gravity": "zero_g",
        "memory_1_button": "memory_1",
        "memory_2_button": "memory_2",
        "memory_3_button": "memory_3",
        "favorite_M_button": "memory_1",
        "head_massage_button": "head_massage",
        "foot_massage_button": "foot_massage",
        "massage_timer_cycle_button": "massage_timer_cycle",
        "light_button": "light",
    }
    with virtual_clock():
        for row in (row for row in VECTORS if row["variant"].lower() == variant):
            mock_bleak_client.write_gatt_char.reset_mock()
            action = row["action"]
            if action.endswith(("_up", "_down")):
                axis, direction = action.rsplit("_", 1)
                control = f"{controls.get(axis, axis)}_{direction}"
                await hass.services.async_call(
                    const.DOMAIN,
                    "hold_control",
                    {"device_id": device, "control": control, "duration": 0.1},
                    blocking=True,
                )
            else:
                await hass.services.async_call(
                    const.DOMAIN,
                    "somos_action",
                    {"device_id": device, "action": aliases.get(action, action)},
                    blocking=True,
                )
            assert written(mock_bleak_client)[0] == bytes.fromhex(row["expected_bytes"]).hex(), row[
                "id"
            ]
            allowed = {bytes.fromhex(row["expected_bytes"]).hex()}
            if variant == "b":
                allowed.add(bed.codec.STATUS_QUERY.hex())
            assert set(written(mock_bleak_client)) <= allowed
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("variant", "abcde")
async def test_manual_setup_configure_import_and_factory(hass, variant):
    from homeassistant.config_entries import SOURCE_RECONFIGURE

    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    from tests.form_helpers import finish_new_bed
    from tests.test_controller_contract import _FactoryCoordinator

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES["somos"]})
    result = await flow.async_step_manual_entry({"address": ADDRESS})
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: variant})
    await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[const.CONF_MOTOR_COUNT] == len(app.PRODUCTS[variant].axes)
    assert saved[const.CONF_HAS_MASSAGE] == app.PRODUCTS[variant].massage
    assert resolve_profile_id(saved) == f"somos:{variant}"
    assert per_side_profile("somos", variant).variant_owned
    coordinator = _FactoryCoordinator()
    coordinator.entry.data = saved
    restored = await create_controller(coordinator, "somos", variant, None)
    assert restored.profile.key == f"somos_{variant}"
    e = entry(hass, "a")
    # The product is the entry's bed model, chosen in Reconfigure.
    manager = hass.config_entries.flow
    result = await manager.async_init(
        const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": e.entry_id}
    )
    assert result["step_id"] == "reconfigure_bed_type"
    result = await manager.async_configure(result["flow_id"], {const.CONF_BED_TYPE: "somos"})
    result = await manager.async_configure(
        result["flow_id"], {const.CONF_PROTOCOL_VARIANT: variant}
    )
    if variant != "a":
        assert result["step_id"] == "migration_confirm"
        with patch.object(hass.config_entries, "async_schedule_reload"):
            await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert e.data[const.CONF_PROTOCOL_VARIANT] == variant
    assert e.data[const.CONF_MOTOR_COUNT] == len(app.PRODUCTS[variant].axes)
    # Saved entry import is the factory path; HA has no YAML import step.
    for invalid in ("", "auto", "unknown"):
        with pytest.raises(ValueError, match="Choose a Somos"):
            await create_controller(coordinator, "somos", invalid, None)


@pytest.mark.parametrize(
    ("variant", "packet", "expected"),
    [
        ("b", "0000000293", (659, 10)),
        ("b", "0000000294", (660, 20)),
        ("e", "000004ec", (1260, 30)),
        ("c", "00000000000000000070110100", (700, 20)),
        ("c", "000000000000000000ffffff7f", (21474836, 30)),
        ("c", "00000000000000000000000080", (-21474836, 0)),
    ],
)
def test_parser_boundaries_signed_arithmetic(variant, packet, expected):
    assert bed.parse_timer(variant, bytes.fromhex(packet)) == expected
    assert bed.parse_timer(variant, b"\0") is None


async def test_stop_before_lazy_import_prevents_any_write(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    from custom_components.adjustable_bed.beds.keeson import somos_services

    mock_bleak_client.services = gatt("e")
    e = entry(hass, "e")
    assert await hass.config_entries.async_setup(e.entry_id)
    target = hass.data[const.DOMAIN][e.entry_id]
    real = somos_services.async_import_modules

    async def importing(*args, **kwargs):
        await target.async_stop_command()
        await real(*args, **kwargs)

    mock_bleak_client.write_gatt_char.reset_mock()
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(target, "both")], []),
        ),
        patch.object(somos_services, "async_import_modules", importing),
    ):
        await hass.services.async_call(
            const.DOMAIN, "somos_action", {"device_id": "bed", "action": "light"}, blocking=True
        )
    assert not written(mock_bleak_client)
    assert await hass.config_entries.async_unload(e.entry_id)


async def test_session_parser_polling_burst_and_physical_ownership(
    hass, mock_coordinator_connected, mock_bleak_client
):
    client = mock_bleak_client
    client.services = gatt("b")
    target = AdjustableBedCoordinator(hass, entry(hass, "b"))
    assert await target.async_connect()
    c = target.controller
    assert isinstance(c, bed.SomosController)
    char, notify = client.start_notify.call_args.args
    notify(char, bytearray.fromhex("0000000294"))
    assert target.controller_state[bed.TIMER_INDICATOR] == 20
    assert target.controller_state[bed.REMAINING_SECONDS] == 660
    notify(char, bytearray(2))
    assert target.controller_state[bed.REMAINING_SECONDS] == 660
    with virtual_clock():
        c._next_query = asyncio.get_running_loop().time() + 2
        client.write_gatt_char.reset_mock()
        await c.async_refresh_diagnostics()
        assert not written(client)
        await asyncio.sleep(2)
        await c.async_refresh_diagnostics()
        assert written(client) == [bed.codec.STATUS_QUERY.hex()]
        client.write_gatt_char.reset_mock()
        await target.async_execute_controller_command(lambda ctrl: ctrl.preset_flat())
        assert written(client) == [encode(c.profile, 0x08000000).hex()] + ["00b0"] * 3
        c.on_disconnect()
        notify(char, bytearray.fromhex("0000000293"))
        assert target.controller_state[bed.TIMER_INDICATOR] is None
        with pytest.raises(ConnectionError):
            await c.perform_action("flat")
        await c.async_discover_capabilities()
        target.cancel_command.clear()
        client.write_gatt_char.reset_mock()
        sent = asyncio.Event()

        async def switch(_char, packet, **kwargs):
            sent.set()
            target._address = "AA:BB:CC:DD:FF:99"

        client.write_gatt_char.side_effect = switch
        with pytest.raises(ConnectionError):
            await c.hold_control("head_up", 1000)
        assert sent.is_set()
        assert len(written(client)) == 1
    await target.async_shutdown()


async def test_card_renewable_neutral_axis_survives_finite_batch_then_stop(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    client = mock_bleak_client
    client.services = gatt("e")
    e = entry(hass, "e")
    assert await hass.config_entries.async_setup(e.entry_id)
    target = hass.data[const.DOMAIN][e.entry_id]
    target._motor_pulse_count = 1
    c = target.controller
    registry = er.async_get(hass)
    device = next(
        item.device_id for item in registry.entities.values() if item.config_entry_id == e.entry_id
    )

    async def renew():
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {
                "device_id": device,
                "motor": "axis_2",
                "direction": "up",
                "duration_ms": 200,
                "hold_owner": "card",
                "hold_generation": 1,
            },
            blocking=True,
        )

    client.write_gatt_char.reset_mock()
    with virtual_clock():
        active = asyncio.create_task(renew())
        for _ in range(6):
            await asyncio.sleep(0.1)
            await renew()
            assert not active.done()
        await target.async_stop_command()
        await active
        count = len(written(client))
        await asyncio.sleep(0.7)
        assert len(written(client)) == count
    assert len(written(client)) >= 2
    assert set(written(client)) == {encode(c.profile, 4).hex()}
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("side", [const.SIDE_LEFT, const.SIDE_BOTH])
async def test_paired_products_preflight_every_target_and_side(hass, monkeypatch, side):
    from functools import partial

    from custom_components.adjustable_bed import services
    from tests.test_controller_contract import _FactoryCoordinator
    from tests.test_paired_coordinator import _pair

    pair, left, right = _pair([])
    controls = []
    for child, variant in ((left, "e"), (right, "a")):
        coordinator = _FactoryCoordinator()
        controller = bed.SomosController(coordinator, variant=variant)
        controls.append(controller)
        controller.perform_action = AsyncMock()
        monkeypatch.setattr(child, "capability_controller", controller, raising=False)

        async def execute(ctrl, command, **kwargs):
            await command(ctrl)

        monkeypatch.setattr(child, "async_execute_controller_command", partial(execute, controller))
    monkeypatch.setattr(services, "_resolve_sided_targets", lambda *_: ([(pair, side)], []))
    await services.async_register_services(hass)
    if side == const.SIDE_BOTH:
        with pytest.raises(ServiceValidationError, match="unavailable"):
            await hass.services.async_call(
                const.DOMAIN,
                "somos_action",
                {"device_id": "pair", "action": "light"},
                blocking=True,
            )
        assert all(not c.perform_action.called for c in controls)
    else:
        await hass.services.async_call(
            const.DOMAIN, "somos_action", {"device_id": "pair", "action": "light"}, blocking=True
        )
        controls[0].perform_action.assert_awaited_once_with("light")
        controls[1].perform_action.assert_not_awaited()


@pytest.mark.parametrize(
    ("variant", "packet", "expected"),
    [
        ("b", "0000000258", (600, 10)),
        ("e", "000004b0", (1200, 20)),
        ("e", "00000744", (1860, 30)),
        ("c", "000000000000000000c0d40100", (1200, 20)),
        ("c", "000000000000000000ffffffff", (0, 0)),
    ],
)
def test_remaining_accepted_parser_literals(variant, packet, expected):
    assert bed.parse_timer(variant, bytes.fromhex(packet)) == expected
