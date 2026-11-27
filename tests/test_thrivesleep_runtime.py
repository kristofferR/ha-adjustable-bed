"""Explicit setup and real HA entities, scheduler and all-target service admission."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.thrivesleep.controller import ThriveSleepController
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.switch import _switch_entities_for
from tests.test_richmat_family_flow import setup_flow
from tests.test_thrivesleep import capabilities, notify
from tests.test_thrivesleep import clock as clock
from tests.test_thrivesleep_vectors import FIXTURES

GATT = json.loads((FIXTURES / "gatt.json").read_text())


@pytest.fixture
async def runtime(hass, request, mock_coordinator_connected, mock_bleak_client, clock):
    product = getattr(request, "param", "level5")
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Thrive Sleep",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:15",
            CONF_NAME: "Thrive Sleep",
            const.CONF_BED_TYPE: "thrivesleep",
            const.CONF_PROTOCOL_VARIANT: product,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_HAS_MASSAGE: product != "cool_flow",
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    target._max_retries = 1
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = target
    gatt = GATT[0]
    tx = SimpleNamespace(uuid=gatt["write"], properties=["write"], handle=15, descriptors=[])
    rx = SimpleNamespace(
        uuid=gatt["declared_notify"], properties=["notify"], handle=16, descriptors=[]
    )
    mock_bleak_client.services = [SimpleNamespace(uuid=gatt["service"], characteristics=[tx, rx])]
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    await target.async_prime_offline_controller()
    assert isinstance(target.capability_controller, ThriveSleepController)
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(target, "both")], []),
    ):
        yield target, mock_bleak_client
    await target.async_shutdown()


def written(client):
    return [call.args[1].hex() for call in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize(
    "product,motors,massage",
    [("cool_flow", 4, False), ("level5", 4, True), ("eco_comfort", 3, True)],
)
async def test_setup_demands_explicit_product_and_owns_side_settings(
    hass, product, motors, massage
):
    flow = setup_flow(hass, name="xQRRM123")
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_richmat_family({"choice": "thrivesleep"})
        assert result["step_id"] == "profile_questions"
        schema = result.get("data_schema")
        assert schema is not None
        result = await flow.async_step_profile_questions(
            schema({const.CONF_PROTOCOL_VARIANT: product})
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[const.CONF_BED_TYPE] == "thrivesleep"
    assert data[const.CONF_PROTOCOL_VARIANT] == product
    assert data[const.CONF_HAS_MASSAGE] is massage
    assert data[const.CONF_MOTOR_COUNT] == motors


async def test_real_cover_memory_timer_rgb_alarm_and_switch(hass, runtime):
    target, client = runtime
    assert await target.async_connect()
    ctrl = target.controller
    assert isinstance(ctrl, ThriveSleepController)
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(
        const.DOMAIN, "save_preset", {"device_id": ["bed"], "preset": 3}, blocking=True
    )
    assert written(client) == ["6e01002d9c"]
    motor = next(spec for spec in ctrl.motor_control_specs if spec.key == "back")
    cover = AdjustableBedCover(target, _build_cover_description(motor))
    cover.hass = hass
    cover.async_write_ha_state = MagicMock()
    client.write_gatt_char.reset_mock()
    await cover.async_open_cover()
    assert written(client)[-1] == "6e01006edd"
    assert set(written(client)[:-1]) == {"6e01002493"}
    assert ctrl.controller_number_specs
    assert "controller_number_thrivesleep_light_seconds" in ctrl.unavailable_controller_entity_keys
    capabilities(SimpleNamespace(client=client))
    timer = next(
        e
        for e in _number_entities_for(hass, target)
        if e.unique_id.endswith("thrivesleep_light_seconds")
    )
    client.write_gatt_char.reset_mock()
    await timer.async_set_native_value(300)
    assert written(client) == ["6e0b012ca6"]
    assert timer.capability_attributes["card_section"] == "lighting"
    assert cover.capability_attributes["card_section"] == "motors"
    await hass.services.async_call(
        const.DOMAIN,
        "thrivesleep",
        {"device_id": ["bed"], "operation": "light_rgb", "rgb_color": [1, 2, 3]},
        blocking=True,
    )
    assert written(client)[-1] == "6e0cff017a6e0d020380"
    await hass.services.async_call(
        const.DOMAIN,
        "set_alarm",
        {
            "device_id": ["bed"],
            "enabled": True,
            "time": "07:30:00",
            "slot": 1,
            "wake_action": "zero_g",
            "weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        },
        blocking=True,
    )
    assert written(client)[-1] == "6e200d0501010100071e45f906"
    notify(SimpleNamespace(client=client), "6e200d060302004245442d31cf")
    switch = next(
        e
        for e in _switch_entities_for(hass, target)
        if e.unique_id.endswith("thrivesleep_anti_snore")
    )
    await switch.async_turn_on()
    assert written(client)[-1] == "6e20090601010001a0"


@pytest.mark.parametrize("runtime", ("cool_flow", "eco_comfort"), indirect=True)
async def test_native_product_entities_do_not_expose_other_product_controls(hass, runtime):
    target, client = runtime
    assert await target.async_connect()
    buttons = _button_entities_for(hass, target)
    keys = [e.unique_id for e in buttons]
    if target.controller.profile.key == "cool_flow":
        assert any("fan" in key for key in keys)
        assert not any("massage" in key for key in keys)
    else:
        assert not any("fan" in key for key in keys)
        assert any("eco_sleep_soothing" in key for key in keys)
    assert not target.controller.controller_switch_specs


@pytest.mark.parametrize("mode", ("concurrent", "sequential"))
async def test_paired_side_identity_and_all_target_capability_preflight(hass, runtime, mode):
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.paired_topology import PairedSideError
    from tests.test_thrivesleep import make

    left, left_client = runtime
    assert await left.async_connect()
    capabilities(SimpleNamespace(client=left_client))
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Eco right",
        data={
            **left.entry.data,
            CONF_ADDRESS: "AA:BB:CC:DD:EE:16",
            const.CONF_PROTOCOL_VARIANT: "eco_comfort",
        },
    )
    entry.add_to_hass(hass)
    right = AdjustableBedCoordinator(hass, entry)
    _, stub = make("eco_comfort", "n1")
    stub.client.disconnect = AsyncMock()
    right._client = stub.client
    right._controller = ThriveSleepController(right, product="eco_comfort")
    hass.data[const.DOMAIN][entry.entry_id] = right
    right.async_ensure_connected = AsyncMock(return_value=True)
    await right.controller.start_notify()
    pair_entry = MockConfigEntry(domain=const.DOMAIN, version=5, data={"pair_id": "thrive-pair"})
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, pair_entry, {"left": left, "right": right}, connection_mode=mode
    )
    left_client.write_gatt_char.reset_mock()
    stub.client.write_gatt_char.reset_mock()
    try:
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "both")], []),
        ):
            with pytest.raises((ServiceValidationError, PairedSideError)):
                await hass.services.async_call(
                    const.DOMAIN,
                    "thrivesleep",
                    {"device_id": ["pair"], "operation": "light_rgb", "rgb_color": [1, 2, 3]},
                    blocking=True,
                )
            assert written(left_client) == written(stub.client) == []
            if mode == "sequential":
                return  # The topology released the checked link; no commands reached either bed.
            with (
                patch(
                    "custom_components.adjustable_bed.beds.thrivesleep.services.validate",
                    side_effect=ServiceValidationError("Changed selection"),
                ),
                pytest.raises(ServiceValidationError, match="Changed selection"),
            ):
                await hass.services.async_call(
                    const.DOMAIN,
                    "thrivesleep",
                    {"device_id": ["pair"], "operation": "light_rgb", "rgb_color": [1, 2, 3]},
                    blocking=True,
                )
            assert written(left_client) == written(stub.client) == []
            capabilities(stub)
            await hass.services.async_call(
                const.DOMAIN,
                "thrivesleep",
                {"device_id": ["pair"], "operation": "light_rgb", "rgb_color": [1, 2, 3]},
                blocking=True,
            )
            assert written(left_client) == written(stub.client) == ["6e0cff017a6e0d020380"]
        left_client.write_gatt_char.reset_mock()
        stub.client.write_gatt_char.reset_mock()
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "right")], []),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "save_preset",
                {"device_id": ["right-child"], "preset": 1},
                blocking=True,
            )
            assert written(left_client) == []
            assert written(stub.client) == ["2b"]
            with pytest.raises((ServiceValidationError, PairedSideError)):
                await hass.services.async_call(
                    const.DOMAIN,
                    "save_preset",
                    {"device_id": ["right-child"], "preset": 3},
                    blocking=True,
                )
    finally:
        await right.async_shutdown()
