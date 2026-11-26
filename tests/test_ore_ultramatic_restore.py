"""S1: discovered routes survive real startup and paired-side offline reload."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import _build_paired_children, const
from custom_components.adjustable_bed.beds.ore_ultramatic.controller import (
    LevaSleepController,
    OreUltramaticController,
)
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.pairing import get_child
from custom_components.adjustable_bed.profile_id import with_profile_ids
from custom_components.adjustable_bed.profiles import ore_ultramatic as app
from tests.test_ore_comfort_bed import _char

APP = const.KEESON_VARIANT_ORE_ULTRAMATIC


def paired_entry(hass, *, right_capabilities=None, variant=APP):
    def side(name, address, motors, capabilities):
        return {
            const.CONF_SIDE: name,
            "address": address,
            "name": name,
            const.CONF_BED_TYPE: const.BED_TYPE_KEESON,
            const.CONF_PROTOCOL_VARIANT: APP if name == const.SIDE_LEFT else variant,
            const.CONF_MOTOR_COUNT: motors,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_HAS_MASSAGE: True,
            "capabilities": capabilities,
        }

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Ultramatic pair",
        version=5,
        data=with_profile_ids({
            const.CONF_PAIR_ID: "ultramatic-restore",
            const.CONF_PAIR_MODE: const.PAIR_MODE_SEPARATE_ADDRESS,
            const.CONF_BED_TYPE: const.BED_TYPE_KEESON,
            const.CONF_PAIR_CHILDREN: [
                side(const.SIDE_LEFT, "AA:BB:CC:DD:15:84", 3,
                     {"keeson": {"ultramatic_route": "P1"}}),
                side(const.SIDE_RIGHT, "AA:BB:CC:DD:15:85", 4, right_capabilities),
            ],
        }),
    )
    entry.add_to_hass(hass)
    return entry


def gatt(client, route):
    client.services = [SimpleNamespace(
        uuid=app.SELECTOR if route == "P1" else "unrelated-service",
        characteristics=[_char(app.WRITE, ["write"]), _char(app.NOTIFY, ["notify"])],
    )]


@pytest.mark.parametrize("route", ("P1", "P2"))
@pytest.mark.parametrize("variant, key, controller_type", [
    (APP, "ultramatic_route", OreUltramaticController),
    (const.KEESON_VARIANT_LEVA_SLEEP, "leva_sleep_route", LevaSleepController),
])
async def test_snapshot_real_startup_persist_reload_unreachable_side(
    hass, mock_coordinator_connected, mock_bleak_client, mock_establish_connection,
    route, variant, key, controller_type,
):
    saved_route = "P2" if route == "P1" else "P1"
    entry = paired_entry(hass, variant=variant, right_capabilities={
        "keeson": {key: saved_route}, "retained": {"value": 158},
    })
    children = _build_paired_children(hass, entry)
    right = children[const.SIDE_RIGHT]
    right._max_retries = 1
    await right.async_prime_offline_controller()
    assert right.capability_controller.capability_snapshot() == {key: saved_route}
    left_before = deepcopy(get_child(entry.data, const.SIDE_LEFT))

    # The live service table overrides the saved route before startup persists.
    gatt(mock_bleak_client, route)
    assert await right.async_connect()
    assert isinstance(right.controller, controller_type)
    assert right.controller.capability_snapshot() == {key: route}
    descriptor = get_child(entry.data, const.SIDE_RIGHT)
    assert descriptor["capabilities"] == {
        "keeson": {key: route}, "retained": {"value": 158},
    }
    assert "capabilities" not in entry.data
    assert get_child(entry.data, const.SIDE_LEFT) == left_before
    assert not mock_bleak_client.write_gatt_char.called
    await right.async_shutdown()

    # Rebuild the actual ChildEntryViews as paired setup does after a reload.
    restored = _build_paired_children(hass, entry)
    pair = PairedBedCoordinator(hass, entry, restored, connection_mode="concurrent")
    offline = restored[const.SIDE_RIGHT]
    offline._max_retries = 1
    mock_establish_connection.reset_mock()
    mock_bleak_client.write_gatt_char.reset_mock()
    mock_bleak_client.start_notify.reset_mock()
    mock_bleak_client.read_gatt_char.reset_mock()
    await offline.async_prime_offline_controller()
    mock_establish_connection.assert_not_awaited()
    controller = offline.capability_controller
    assert isinstance(controller, controller_type)
    assert offline.controller is None and offline.client is None
    assert controller.capability_snapshot() == {key: route}
    assert controller.supports_memory_programming is (route == "P1")
    assert controller.supports_preset_tv is (route == "P2" and variant == APP)
    assert controller.supports_discrete_light_control is (route == "P1")
    assert tuple(spec.key for spec in controller.motor_control_specs) == ("back", "feet", "waist", "lumbar")

    mock_establish_connection.side_effect = ConnectionError("Receiver is unreachable")
    assert not await offline.async_connect()
    assert offline.capability_controller is controller
    assert len(_cover_entities_for(hass, offline)) == 4
    keys = {button.unique_id for button in _button_entities_for(hass, offline)}
    assert any("ore_comfort_program_flat" in key for key in keys) is (route == "P1")
    assert any("ultramatic_massage_head" in key for key in keys) is (route == "P2")
    assert not mock_bleak_client.write_gatt_char.called
    mock_bleak_client.start_notify.assert_not_awaited()
    mock_bleak_client.read_gatt_char.assert_not_awaited()
    await pair.async_shutdown()


@pytest.mark.parametrize("capabilities,variant", [
    (None, APP),
    ({}, APP),
    ({"keeson": {}}, APP),
    ({"keeson": {"ultramatic_route": "unknown"}}, APP),
    ({"keeson": {"ultramatic_route": "p1"}}, APP),
    ({"keeson": {"ultramatic_route": None}}, APP),
    ({"keeson": {"ultramatic_route": 1}}, APP),
    ({"keeson": {"route": "P1"}}, APP),
    ({"keeson": {"ultramatic_route": "P1", "other_profile": True}}, APP),
    ({"ore_ultramatic": {"ultramatic_route": "P1"}}, APP),
    ({"keeson": {"ultramatic_route": "P1"}}, const.VARIANT_AUTO),
    ({"keeson": {"ultramatic_route": "P2"}}, const.KEESON_VARIANT_SINO),
    ({"keeson": {"ultramatic_route": "P2"}}, const.KEESON_VARIANT_LEVA_SLEEP),
    ({"keeson": {"leva_sleep_route": "P1"}}, APP),
])
async def test_snapshot_missing_invalid_or_unrelated_cannot_restore(
    hass, mock_establish_connection, capabilities, variant,
):
    entry = paired_entry(hass, right_capabilities=capabilities, variant=variant)
    right = _build_paired_children(hass, entry)[const.SIDE_RIGHT]
    await right.async_prime_offline_controller()
    assert right.capability_controller is None
    if variant in const.ORE_GATT_ROUTED_VARIANTS:
        # Preview cannot expose a guessed default route through the factory either.
        await right.async_prime_offline_controller(preview=True)
        assert right.capability_controller is None
        with pytest.raises(ConnectionError, match="discover its bed route"):
            await create_controller(right, const.BED_TYPE_KEESON, variant, None)
    mock_establish_connection.assert_not_awaited()
    await right.async_shutdown()


async def test_snapshot_failed_startup_does_not_persist_discovered_route(
    hass, mock_coordinator_connected, mock_bleak_client,
):
    entry = paired_entry(hass)
    right = _build_paired_children(hass, entry)[const.SIDE_RIGHT]
    right._max_retries = 1
    gatt(mock_bleak_client, "P2")
    mock_bleak_client.start_notify.side_effect = RuntimeError("Subscription failed")
    assert not await right.async_connect()
    assert not get_child(entry.data, const.SIDE_RIGHT).get("capabilities")
    assert not mock_bleak_client.write_gatt_char.called
    await right.async_shutdown()
