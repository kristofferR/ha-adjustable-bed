"""Unit162 through HA setup, real coordinators, entities and sided service admission."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.beds.goodvibe.controller import Link
from custom_components.adjustable_bed.beds.mlily_remote.controller import MlilyRemoteController
from custom_components.adjustable_bed.beds.mlily_remote.services import register_services
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideProxy,
    SingleAddressPairedCoordinator,
)
from tests.hold_lease_wire import virtual_clock


def runtime(hass, product="ms600", suffix=1, layout="single"):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: f"AA:BB:CC:DD:EE:{suffix:02X}",
            CONF_NAME: "MLILY Remote",
            const.CONF_BED_TYPE: const.BED_TYPE_MLILY_REMOTE,
            const.CONF_PROTOCOL_VARIANT: product,
            const.CONF_PRODUCT_TYPE: layout,
        },
    )
    entry.add_to_hass(hass)
    c = AdjustableBedCoordinator(hass, entry)
    c._client = MagicMock(is_connected=True)
    c._client.write_gatt_char = AsyncMock()
    c._client.stop_notify = AsyncMock()
    c._client.disconnect = AsyncMock()
    c._controller = MlilyRemoteController(c, product=product, layout=layout)
    c._offline_controller = MlilyRemoteController(c, product=product, layout=layout)
    c._controller._link = Link(
        c._client,
        SimpleNamespace(uuid="tx", handle=1, properties=["write"]),
        SimpleNamespace(uuid="rx", handle=2, properties=["notify"]),
        False,
    )
    c._controller._event("deviceCharacteristicsSubscriptionClockEvent", None)
    c.async_ensure_connected = AsyncMock(return_value=True)
    c._async_refresh_controller_auth = AsyncMock()
    return c


def frames(c):
    return [bytes(call.args[1]).hex() for call in c._client.write_gatt_char.call_args_list]


async def shutdown(*coordinators):
    for c in coordinators:
        c._client.is_connected = False
        await c.async_shutdown()


async def test_native_entity_and_renewable_hold_use_scheduler_and_captured_stop(hass):
    c = runtime(hass)
    register_services(hass)
    hass.services.async_register(const.DOMAIN, "hold_control", services.handle_hold_control)
    with virtual_clock():
        light = next(s for s in c.controller.controller_button_specs if s.key.endswith("bedlight"))
        await ControllerActionButton(c, light).async_press()
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(c, "both")], []),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "hold_control",
                {
                    "device_id": ["bed"],
                    "control": "mlily_remote_HeadUp",
                    "duration": 0.35,
                    "hold_owner": "mlily",
                    "hold_generation": 1,
                },
                blocking=True,
            )
    assert frames(c)[0] == "6e01003cab"
    assert frames(c)[-1] == "6e01006edd"
    assert frames(c).count("6e01002493") >= 1
    await shutdown(c)


@pytest.mark.parametrize("operation", ["anti_snore", "alarm"])
async def test_every_target_stop_epoch_is_captured_before_first_import_await(hass, operation):
    product = "ms300_sh" if operation == "anti_snore" else "ms600"
    a, b = runtime(hass, product), runtime(hass, product, suffix=2)
    register_services(hass)
    entered, release = asyncio.Event(), asyncio.Event()

    async def lazy_import(*_args):
        entered.set()
        await release.wait()

    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(a, "both"), (b, "both")], []),
        ),
        patch(
            "custom_components.adjustable_bed.beds.mlily_remote.services.async_import_modules",
            lazy_import,
        ),
    ):
        task = asyncio.create_task(
            hass.services.async_call(
                const.DOMAIN,
                "mlily_remote",
                {
                    "device_id": ["a", "b"],
                    "operation": operation,
                },
                blocking=True,
            )
        )
        await entered.wait()
        await b.async_stop_command()
        b._client.write_gatt_char.reset_mock()
        release.set()
        with virtual_clock():
            await task
    # The earlier target may execute, but a STOP on the later target must not
    # become stale just because the service awaited an import/preflight first.
    assert not frames(b)
    assert frames(a)
    await shutdown(a, b)


async def test_all_product_gates_precede_any_write(hass):
    a, b = runtime(hass), runtime(hass, product="powercool", suffix=2)
    register_services(hass)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(a, "both"), (b, "both")], []),
        ),
        pytest.raises(ServiceValidationError, match="no alarm mode"),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "mlily_remote",
            {
                "device_id": ["a", "b"],
                "operation": "alarm",
                "mode": "memory_1",
            },
            blocking=True,
        )
    assert not frames(a) and not frames(b)
    await shutdown(a, b)


async def test_one_address_children_keep_side_and_reject_nordic_side_alias(hass):
    c = runtime(hass, layout="double")
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            const.CONF_BED_TYPE: const.BED_TYPE_MLILY_REMOTE,
            "pair_id": "mlily-one",
            const.CONF_PAIR_MODE: const.PAIR_MODE_SINGLE_ADDRESS,
        },
    )
    entry.add_to_hass(hass)
    pair = SingleAddressPairedCoordinator(hass, entry, c)
    from custom_components.adjustable_bed import _async_ensure_paired_device_registry

    _async_ensure_paired_device_registry(hass, entry, pair)
    right = PairedSideProxy(pair, pair.children["right"], "right")
    obj = c.controller
    spec = next(s for s in obj.controller_button_specs if s.key.endswith("bedlight"))
    with virtual_clock():
        await ControllerActionButton(right, spec).async_press()
    assert frames(c) == ["6e01013cac"]
    c._client.write_gatt_char.reset_mock()
    obj._link = Link(obj._link.client, obj._link.tx, obj._link.rx, True)
    with pytest.raises(ValueError, match="side selector"), obj.side_scope("right"):
        await obj.hold_control("mlily_remote_HeadUp", 100)
    assert not frames(c)
    await shutdown(c)


async def test_two_address_alarm_preflight_keeps_distinct_product_and_target(hass):
    a, b = runtime(hass), runtime(hass, product="ms200", suffix=2)
    entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": "mlily-two"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, entry, {"left": a, "right": b}, connection_mode="concurrent")
    register_services(hass)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "both")], []),
        ),
        pytest.raises(ServiceValidationError, match="no alarm mode"),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "mlily_remote",
            {
                "device_id": ["pair"],
                "operation": "alarm",
            },
            blocking=True,
        )
    assert not frames(a) and not frames(b)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "left")], []),
        ),
        virtual_clock(),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "mlily_remote",
            {
                "device_id": ["pair"],
                "operation": "alarm",
                "mode": "tv",
            },
            blocking=True,
        )
    assert len(frames(a)) == 2 and not frames(b)
    await shutdown(a, b)


@pytest.mark.parametrize(
    "product,expected_motors,has_massage",
    [("ms200", 2, False), ("ms600", 4, True), ("powercool", 2, False)],
)
async def test_production_profile_question_flow_and_builder(
    hass, product, expected_motors, has_massage
):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.setup_questions import setup_profile

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": "user"}
    flow._manual_data = {
        CONF_ADDRESS: "11:22:33:44:55:66",
        CONF_NAME: "MLILY Remote",
        const.CONF_BED_TYPE: const.BED_TYPE_MLILY_REMOTE,
        const.CONF_MOTOR_COUNT: 3,
        const.CONF_MOTOR_PULSE_COUNT: 99,
    }
    with patch.object(
        flow, "_async_finish_family_route", AsyncMock(return_value={"type": "finished"})
    ):
        result = await flow.async_step_profile_questions()
        assert result["step_id"] == "profile_questions"
        await flow.async_step_profile_questions(
            {const.CONF_PROTOCOL_VARIANT: product, const.CONF_PRODUCT_TYPE: "double"}
        )
    data = flow._manual_data
    assert data[const.CONF_MOTOR_COUNT] == expected_motors
    assert data[const.CONF_HAS_MASSAGE] is has_massage
    assert data[const.CONF_MOTOR_PULSE_COUNT] == 10
    assert data[const.CONF_MOTOR_PULSE_DELAY_MS] == 100
    assert data[const.CONF_DISABLE_ANGLE_SENSING]
    c = runtime(hass, product=product, layout="double")
    # Real import executor and builder, not a direct-only controller test.
    obj = await create_controller(c, const.BED_TYPE_MLILY_REMOTE, product, None)
    assert isinstance(obj, MlilyRemoteController)
    assert obj.layout == "double" and obj.model == product
    assert setup_profile(const.BED_TYPE_MLILY_REMOTE).questions[1].key == const.CONF_PRODUCT_TYPE
    await shutdown(c)


@pytest.mark.parametrize("selection", ["right", "parent", "both", "children", "left"])
async def test_default_left_intervention_resolves_real_registry_targets_before_admission(hass, selection):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed import _async_ensure_paired_device_registry
    from custom_components.adjustable_bed.beds.mlily_remote import services as mlily_services
    from custom_components.adjustable_bed.paired_devices import side_identifier

    c = runtime(hass, product="ms300_sh", layout="double")
    entry = MockConfigEntry(domain=const.DOMAIN, data={
        const.CONF_BED_TYPE: const.BED_TYPE_MLILY_REMOTE,
        const.CONF_PAIR_MODE: const.PAIR_MODE_SINGLE_ADDRESS,
        const.CONF_PAIR_ID: "mlily-intervention",
    })
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = SingleAddressPairedCoordinator(hass, entry, c)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = pair
    _async_ensure_paired_device_registry(hass, entry, pair)
    registry = dr.async_get(hass)
    parent = registry.async_get_device_by_identifier(next(iter(pair.device_info["identifiers"])), entry.entry_id)
    left = registry.async_get_child_device_by_identifier(side_identifier(pair, "left"), entry.entry_id)
    right = registry.async_get_child_device_by_identifier(side_identifier(pair, "right"), entry.entry_id)
    assert parent is not None and left is not None and right is not None
    ids = {"right": [right.id], "parent": [parent.id], "both": [parent.id], "children": [left.id, right.id], "left": [left.id]}
    data = {"device_id": ids[selection], "operation": "anti_snore"}
    if selection == "both":
        data["side"] = "both"
    register_services(hass)
    original_import = mlily_services.async_import_modules
    with patch("custom_components.adjustable_bed.services._capture_command_admission", wraps=services._capture_command_admission) as capture:
        async def import_after_admission(*args):
            assert capture.call_count == 1
            assert capture.call_args.args == (pair, "left")
            await original_import(*args)

        with patch.object(mlily_services, "async_import_modules", import_after_admission), virtual_clock():
            if selection == "right":
                with pytest.raises(ServiceValidationError, match="cannot target Right"):
                    await hass.services.async_call(const.DOMAIN, "mlily_remote", data, blocking=True)
                capture.assert_not_called()
                assert not frames(c)
            else:
                await hass.services.async_call(const.DOMAIN, "mlily_remote", data, blocking=True)
                assert frames(c) == ["6e010046b5"]
                capture.assert_called_once()
    if selection == "right":
        # The ordinary preset still belongs to the targeted Right child.
        right_owner = PairedSideProxy(pair, pair.children["right"], "right")
        spec = next(s for s in c.controller.controller_button_specs if s.key.endswith("antisnoring"))
        with virtual_clock():
            await ControllerActionButton(right_owner, spec).async_press()
        assert frames(c) == ["6e010146b6"]
    await shutdown(c)
