"""Actual HA light admission/state, with independent C/D/U selectors."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.starcode_abm5_4 import StarcodeAbm5_4Controller
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.starcode_abm5_4_vectors import BUILDER_VECTORS
from tests.test_starcode_abm5_4 import make_controller

PROFILES = [
    ("BOX25", "BOX25", "BOX25", True),
    ("BOX25_STAR", "BOX25_STAR", "BOX25_STAR", True),
    ("BOX25", "BOX1220", "BOX25", False),
    ("BOX3633", "BOX3633", "BOX3633", False),
    ("BOX1220", "BOX1220", "BOX1220", False),
    ("BOX15", "BOX15", "BOX1220", False),
    ("BOX25", "BOX25", "BOX3633", False),
    ("BOX1220", "BOX25", "BOX1220", True),
]


def native_frame(selector, action):
    return bytes.fromhex(
        next(row[3] for row in BUILDER_VECTORS if row[:3] == (selector, action, 0))
    )


@pytest.mark.parametrize("command,ui,transport,feedback", PROFILES)
async def test_actual_HA_light_catalog_does_not_claim_impossible_fresh_feedback(
    hass, enable_custom_integrations, mock_coordinator_connected, command, ui, transport, feedback
):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        version=4,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Native floor controls",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_STARCODE_COMMAND_SELECTOR: command,
            const.CONF_STARCODE_UI_SELECTOR: ui,
            const.CONF_STARCODE_TRANSPORT_SELECTOR: transport,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)

    async def connect(coordinator):
        client = make_controller(device=transport).client
        client.read_gatt_char.return_value = b"star" if command == "BOX25_STAR" else b"ordinary"

        async def disconnect():
            client.is_connected = False

        client.disconnect = AsyncMock(side_effect=disconnect)
        coordinator._client = client
        coordinator._controller = await create_controller(
            coordinator, const.BED_TYPE_STARCODE_ABM5_4, None, client
        )
        await coordinator._controller.start_notify()
        return True

    with (
        patch.object(AdjustableBedCoordinator, "async_connect", connect),
        patch.object(AdjustableBedCoordinator, "_schedule_position_hydration"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = hass.data[const.DOMAIN][entry.entry_id]
        assert isinstance(coordinator, AdjustableBedCoordinator)
        controller = coordinator.controller
        assert isinstance(controller, StarcodeAbm5_4Controller)
        registry = er.async_get(hass)
        rows = er.async_entries_for_config_entry(registry, entry.entry_id)
        assumed = [row for row in rows if row.unique_id.endswith("_under_bed_lights_assumed")]
        lights = [row for row in rows if row.domain == "light" and row not in assumed]
        assert len(lights) == int(feedback)
        assert len(assumed) == int(not feedback)
        for row in assumed:
            assert row.disabled_by is er.RegistryEntryDisabler.INTEGRATION
            assert hass.states.get(row.entity_id) is None
        assert not any(
            row.domain == "switch" and row.translation_key == "under_bed_lights" for row in rows
        )
        if feedback:
            light = lights[0]
            assert hass.states.get(light.entity_id).state == "unknown"
            for service, builder in [
                ("turn_on", "turnonUnderbedLighting"),
                ("turn_off", "turnoffUnderbedLighting"),
                ("toggle", "underbedLighting"),
            ]:
                controller._last_light_time_ms = None
                await hass.services.async_call(
                    "light", service, {"entity_id": light.entity_id}, blocking=True
                )
                assert controller.client.write_gatt_char.await_args.args[1] == native_frame(
                    command, builder
                )
                assert hass.states.get(light.entity_id).state == "unknown"
            packet = bytearray.fromhex("a50b0e00000100010000000000004100")
            controller._notification(
                controller.client,
                controller._session_generation,
                controller.client.services[0].characteristics[1],
                packet,
            )
            assert hass.states.get(light.entity_id).state == (
                "on" if command in ("BOX25", "BOX25_STAR") else "off"
            )
            state_before = hass.states.get(light.entity_id).state
            controller._last_light_time_ms = None
            await hass.services.async_call(
                "light", "turn_off", {"entity_id": light.entity_id}, blocking=True
            )
            assert hass.states.get(light.entity_id).state == state_before
        else:
            toggle = next(
                row
                for row in rows
                if row.domain == "button" and row.translation_key == "toggle_light"
            )
            controller._last_light_time_ms = None
            await hass.services.async_call(
                "button", "press", {"entity_id": toggle.entity_id}, blocking=True
            )
            assert controller.client.write_gatt_char.await_args.args[1] == native_frame(
                command, "underbedLighting"
            )
            power = {
                row.translation_key: row
                for row in rows
                if row.domain == "button"
                and row.translation_key in ("starcode_abm5_4_light_on", "starcode_abm5_4_light_off")
            }
            assert len(power) == (2 if command in ("BOX3633", "BOX25", "BOX25_STAR") else 0)
            for key, builder in [
                ("starcode_abm5_4_light_on", "turnonUnderbedLighting"),
                ("starcode_abm5_4_light_off", "turnoffUnderbedLighting"),
            ]:
                if key in power:
                    controller._last_light_time_ms = None
                    await hass.services.async_call(
                        "button", "press", {"entity_id": power[key].entity_id}, blocking=True
                    )
                    assert controller.client.write_gatt_char.await_args.args[1] == native_frame(
                        command, builder
                    )
            assert controller.get_light_state()["is_on"] is None
            observed_sensor = next(
                row
                for row in rows
                if row.translation_key == "starcode_abm5_4_light_on" and row.domain == "sensor"
            )
            assert hass.states.get(observed_sensor.entity_id).state == "unknown"
        observed = controller.supports_light_state_feedback
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert observed is feedback


@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize("transition", ["gain", "lose"])
async def test_actual_HA_positive_C_feedback_boundary_reloads_exact_child_catalog(
    hass, enable_custom_integrations, paired, transition
):
    from custom_components.adjustable_bed.beds.starcode_abm5_4_profiles import RetainedAppState
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    left, right = "AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"
    transport = "BOX25" if transition == "gain" else "BOX1220"
    ui = "BOX1220" if transition == "gain" else "BOX25"
    data = {
        CONF_ADDRESS: left,
        CONF_NAME: "Feedback boundary",
        const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
        const.CONF_MOTOR_COUNT: 2,
        const.CONF_HAS_MASSAGE: True,
        const.CONF_STARCODE_COMMAND_SELECTOR: "BOX25",
        const.CONF_STARCODE_UI_SELECTOR: ui,
        const.CONF_STARCODE_TRANSPORT_SELECTOR: transport,
        const.CONF_DISABLE_ANGLE_SENSING: True,
        const.CONF_DISCONNECT_AFTER_COMMAND: False,
    }
    if paired:
        data.update(
            {
                const.CONF_PAIR_ID: "light-boundary-pair",
                const.CONF_PAIR_MODE: const.PAIR_MODE_SEPARATE_ADDRESS,
                const.CONF_PAIR_SCHEMA_VERSION: 1,
                const.CONF_PAIR_MEMBER_ADDRESSES: [left, right],
                const.CONF_PAIR_CHILDREN: [
                    {**data, const.CONF_SIDE: "left", CONF_NAME: "Left"},
                    {
                        **data,
                        CONF_ADDRESS: right,
                        CONF_NAME: "Right",
                        const.CONF_SIDE: "right",
                        const.CONF_STARCODE_UI_SELECTOR: "BOX25",
                        const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX25",
                    },
                ],
            }
        )
        data.pop(CONF_ADDRESS)
    entry = MockConfigEntry(domain=const.DOMAIN, version=4, data=data)
    entry.add_to_hass(hass)

    async def connect(coordinator):
        device = coordinator.entry.data[const.CONF_STARCODE_TRANSPORT_SELECTOR]
        assert isinstance(device, str)
        client = make_controller(device=device).client
        client.read_gatt_char.return_value = b"ordinary"

        async def disconnect():
            client.is_connected = False

        client.disconnect = AsyncMock(side_effect=disconnect)
        coordinator._client = client
        coordinator._controller = await create_controller(
            coordinator, const.BED_TYPE_STARCODE_ABM5_4, None, client
        )
        await coordinator._controller.start_notify()
        return True

    def child():
        loaded = hass.data[const.DOMAIN][entry.entry_id]
        if paired:
            assert isinstance(loaded, PairedBedCoordinator)
            loaded = loaded.child_for_side("left")
        assert isinstance(loaded, AdjustableBedCoordinator)
        return loaded

    registry = er.async_get(hass)
    with (
        patch.object(AdjustableBedCoordinator, "async_connect", connect),
        patch.object(AdjustableBedCoordinator, "_schedule_position_hydration"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        before_rows = er.async_entries_for_config_entry(registry, entry.entry_id)
        identities = {
            (row.domain, row.unique_id): (row.entity_id, row.device_id) for row in before_rows
        }
        coordinator = child()
        controller = coordinator.controller
        assert isinstance(controller, StarcodeAbm5_4Controller)
        retained = RetainedAppState(left, True, True, True, 4, 2, 2, 4, 1, True, 1000)
        assert controller.restore_retained_app_state(retained)
        adopt = next(
            row.entity_id
            for row in before_rows
            if left in row.unique_id
            and row.translation_key == "starcode_abm5_4_use_detected_profile"
        )
        assert controller.command_selector == "BOX25"
        old_feedback = controller.supports_light_state_feedback
        with patch.object(
            hass.config_entries, "async_reload", wraps=hass.config_entries.async_reload
        ) as reload:
            await hass.services.async_call("button", "press", {"entity_id": adopt}, blocking=True)
            await hass.async_block_till_done()
            assert bool(controller.controller_number_specs)
            assert controller.supports_light_state_feedback is not old_feedback
            assert coordinator._pending_capability_reload
            reload.assert_not_awaited()
            await coordinator.async_disconnect(serialize_with_commands=True)
            await hass.async_block_till_done()
            reload.assert_awaited_once_with(entry.entry_id)
            rebuilt = child()
            adopted = rebuilt.controller
            assert isinstance(adopted, StarcodeAbm5_4Controller)
            assert (adopted.command_selector, adopted.ui_selector) == (transport, transport)
            assert adopted.supports_light_state_feedback == (transition == "gain")
            assert rebuilt.starcode_app_retained_state == retained
            assert adopted.get_light_state()["is_on"] is True
            assert not adopted._parser_state_observed
            if transition == "gain":
                assert native_frame("BOX25", "change2White") not in [
                    call.args[1] for call in adopted.client.write_gatt_char.await_args_list
                ]
            current_rows = er.async_entries_for_config_entry(registry, entry.entry_id)
            current = {
                (row.domain, row.unique_id): (row.entity_id, row.device_id) for row in current_rows
            }
            retired = {
                ("light", coordinator.entity_unique_id(key))
                for key in ("under_bed_lights", "under_bed_lights_assumed")
            } | {
                ("button", coordinator.entity_unique_id(key))
                for key in ("toggle_light", "starcode_abm5_4_light_on", "starcode_abm5_4_light_off")
            }
            assert all(
                current.get(key) == value for key, value in identities.items() if key not in retired
            )
            left_rows = [row for row in current_rows if left in row.unique_id]
            assumed = [
                row for row in left_rows if row.unique_id.endswith("_under_bed_lights_assumed")
            ]
            assert sum(row.domain == "light" and row not in assumed for row in left_rows) == int(
                transition == "gain"
            )
            assert len(assumed) == int(transition == "lose")
            for row in assumed:
                assert row.disabled_by is er.RegistryEntryDisabler.INTEGRATION
                assert hass.states.get(row.entity_id) is None
            assert sum(row.translation_key == "toggle_light" for row in left_rows) == int(
                transition == "lose"
            )
            assert not any(
                row.domain == "switch" and row.translation_key == "under_bed_lights"
                for row in left_rows
            )
            assert not any(
                row.domain == "button"
                and row.translation_key in ("starcode_abm5_4_light_on", "starcode_abm5_4_light_off")
                for row in left_rows
            )
            if paired:
                assert all(
                    current[key] == value for key, value in identities.items() if right in key[1]
                )
                assert (
                    entry.data[const.CONF_PAIR_CHILDREN][1][const.CONF_STARCODE_UI_SELECTOR]
                    == "BOX25"
                )
            await hass.services.async_call("button", "press", {"entity_id": adopt}, blocking=True)
            await hass.async_block_till_done()
            assert (
                not rebuilt._pending_capability_reload
                and rebuilt._pending_internal_bond_marker is None
            )
            assert reload.await_count == 1
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_actual_HA_reconnect_classification_adds_power_buttons_without_positive_C_change(
    hass, enable_custom_integrations
):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        version=4,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Late manufacturer",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_STARCODE_COMMAND_SELECTOR: "BOX1220",
            const.CONF_STARCODE_UI_SELECTOR: "BOX1220",
            const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX25",
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    manufacturer = None

    async def connect(coordinator, *, reset_timer=True):
        client = make_controller(device="BOX25").client

        async def read(_role):
            if manufacturer is None:
                raise OSError("Optional identity temporarily unavailable")
            return manufacturer

        async def disconnect():
            client.is_connected = False

        client.read_gatt_char.side_effect = read
        client.disconnect = AsyncMock(side_effect=disconnect)
        coordinator._client = client
        coordinator._controller = await create_controller(
            coordinator, const.BED_TYPE_STARCODE_ABM5_4, None, client
        )
        await coordinator._controller.start_notify()
        return True

    with (
        patch.object(AdjustableBedCoordinator, "async_connect", connect),
        patch.object(AdjustableBedCoordinator, "_async_connect_locked", connect),
        patch.object(AdjustableBedCoordinator, "_schedule_position_hydration"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = hass.data[const.DOMAIN][entry.entry_id]
        assert isinstance(coordinator, AdjustableBedCoordinator)
        registry = er.async_get(hass)
        original_rows = er.async_entries_for_config_entry(registry, entry.entry_id)
        original = {
            (row.domain, row.unique_id): (row.entity_id, row.device_id) for row in original_rows
        }
        toggle = next(
            row.entity_id for row in original_rows if row.translation_key == "toggle_light"
        )
        assert not any(
            row.domain == "button" and row.translation_key == "starcode_abm5_4_light_on"
            for row in original_rows
        )
        assert isinstance(coordinator.controller, StarcodeAbm5_4Controller)
        assert coordinator.controller.controller_number_specs
        await coordinator.async_disconnect(serialize_with_commands=True)
        manufacturer = b"star"
        with patch.object(
            hass.config_entries, "async_reload", wraps=hass.config_entries.async_reload
        ) as reload:
            await hass.services.async_call("button", "press", {"entity_id": toggle}, blocking=True)
            await hass.async_block_till_done()
            controller = coordinator.controller
            assert isinstance(controller, StarcodeAbm5_4Controller)
            assert (
                controller.command_selector == "BOX25_STAR" and controller.ui_selector == "BOX1220"
            )
            assert (
                controller.controller_number_specs and not controller.supports_light_state_feedback
            )
            assert (
                coordinator._pending_capability_reload
                and coordinator._pending_internal_bond_marker is None
            )
            assert controller.client.write_gatt_char.await_args.args[1] == native_frame(
                "BOX25_STAR", "underbedLighting"
            )
            reload.assert_not_awaited()
            await coordinator.async_disconnect(serialize_with_commands=True)
            await hass.async_block_till_done()
            reload.assert_awaited_once_with(entry.entry_id)
            current_rows = er.async_entries_for_config_entry(registry, entry.entry_id)
            current = {
                (row.domain, row.unique_id): (row.entity_id, row.device_id) for row in current_rows
            }
            changed_identity = {
                key: (value, current.get(key))
                for key, value in original.items()
                if current.get(key) != value
            }
            assert not changed_identity
            assert (
                sum(
                    row.domain == "button"
                    and row.translation_key
                    in ("starcode_abm5_4_light_on", "starcode_abm5_4_light_off")
                    for row in current_rows
                )
                == 2
            )
            assumed = [
                row for row in current_rows if row.unique_id.endswith("_under_bed_lights_assumed")
            ]
            assert len(assumed) == 1
            assert assumed[0].disabled_by is er.RegistryEntryDisabler.INTEGRATION
            assert hass.states.get(assumed[0].entity_id) is None
            assert not any(
                row.domain in ("light", "switch") and row not in assumed for row in current_rows
            )
            assert entry.data[const.CONF_STARCODE_UI_SELECTOR] == "BOX1220"
            assert entry.data[const.CONF_STARCODE_TRANSPORT_SELECTOR] == "BOX25"
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
