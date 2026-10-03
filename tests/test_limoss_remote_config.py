"""Manual app selection and physical-target local preferences."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.detection import detect_bed_type
from custom_components.adjustable_bed.pairing import (
    inheritable_child_fields,
    supports_single_address_pairing,
)

ADDRESS = "11:22:33:44:55:66"


def app_data(**extra):
    return {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "App bed",
        const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS_REMOTE,
        const.CONF_PRODUCT_TYPE: "bed",
        const.CONF_HAS_LIGHT: False,
        const.CONF_HAS_MASSAGE: False,
        **extra,
    }


@pytest.mark.parametrize("step", ["manual_entry", "manual_config", "bluetooth_confirm"])
async def test_all_setup_routes_collect_explicit_profile(hass, mock_bluetooth_service_info, step):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._discovery_info = mock_bluetooth_service_info
    flow._disconnect_choice_confirmed = True
    result = await getattr(flow, f"async_step_{step}")(
        {
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "App bed",
            const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS_REMOTE,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
            const.CONF_PREFERRED_ADAPTER: "auto",
        }
    )
    assert result["step_id"] == "limoss_remote"
    fields = {key.schema for key in result["data_schema"].schema}
    assert {const.CONF_PRODUCT_TYPE, const.CONF_HAS_LIGHT, const.CONF_HAS_MASSAGE} <= fields
    assert not fields.intersection(
        {
            const.CONF_MOTOR_COUNT,
            const.CONF_PROTOCOL_VARIANT,
            const.CONF_MOTOR_PULSE_COUNT,
            const.CONF_MOTOR_PULSE_DELAY_MS,
        }
    )
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_limoss_remote(
            {const.CONF_PRODUCT_TYPE: "chair", const.CONF_REVERSE_MOTORS[3]: True}
        )
    assert finish.await_args.args[0][const.CONF_PRODUCT_TYPE] == "chair"
    assert finish.await_args.args[0][const.CONF_REVERSE_MOTORS[3]] is True
    assert finish.await_args.args[0][const.CONF_DISABLE_ANGLE_SENSING] is True


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        {const.CONF_PRODUCT_TYPE: "unknown"},
        {const.CONF_PRODUCT_TYPE: "bed", const.CONF_LIMOSS_REMOTE_THEME: "made_up"},
    ],
)
async def test_invalid_profile_never_finishes_setup(hass, invalid):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = {CONF_ADDRESS: ADDRESS}
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        result = await flow.async_step_limoss_remote(invalid)
    assert result["errors"]
    finish.assert_not_awaited()


@pytest.mark.parametrize("name", ["limoss", "prefix limoss", "LIMOSS", "any"])
def test_shared_name_or_service_does_not_autoselect_app(name):
    info = MagicMock()
    info.name = name
    info.address = ADDRESS
    info.service_uuids = [const.LIMOSS_SERVICE_UUID]
    info.manufacturer_data = {}
    assert detect_bed_type(info) != const.BED_TYPE_LIMOSS_REMOTE
    assert not supports_single_address_pairing(const.BED_TYPE_LIMOSS_REMOTE)


def test_parent_options_cannot_override_physical_target_profile_or_memories():
    data = {
        **app_data(),
        const.CONF_LIMOSS_REMOTE_STATE: {"memories": {"8": {"name": "", "positions": {"0": -1}}}},
        const.CONF_PREFERRED_ADAPTER: "proxy",
    }
    inherited = inheritable_child_fields(data)
    # Shared light and massage keys are stored on every side.
    side_only = const.LIMOSS_REMOTE_CONFIG_KEYS - {const.CONF_HAS_LIGHT, const.CONF_HAS_MASSAGE}
    assert not (side_only | {const.CONF_LIMOSS_REMOTE_STATE}).intersection(inherited)
    assert inherited[const.CONF_PREFERRED_ADAPTER] == "proxy"


async def test_enabling_local_features_saves_options_without_ble(hass):
    entry = MockConfigEntry(domain=const.DOMAIN, data=app_data())
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    result = await flow.async_step_settings(
        {
            const.CONF_HAS_LIGHT: True,
            const.CONF_HAS_MASSAGE: True,
            const.CONF_LIMOSS_REMOTE_THEME: "bed_clear",
            const.CONF_REVERSE_MOTORS[0]: True,
        }
    )
    assert result["type"] == "create_entry"
    assert entry.data[const.CONF_HAS_LIGHT] is True
    assert entry.data[const.CONF_HAS_MASSAGE] is True
    assert entry.data[const.CONF_LIMOSS_REMOTE_THEME] == "bed_clear"
    assert entry.data[const.CONF_REVERSE_MOTORS[0]] is True


@pytest.mark.parametrize("fail", [False, True])
async def test_options_disable_finishes_exact_off_bursts_before_saving(hass, fail):
    from custom_components.adjustable_bed.beds.limoss import LimossController
    from custom_components.adjustable_bed.controller_factory import create_controller
    from tests.test_coordinator_limoss_remote import actual_coordinator

    coordinator = actual_coordinator(
        hass,
        **{
            const.CONF_HAS_LIGHT: True,
            const.CONF_HAS_MASSAGE: True,
            const.CONF_LIMOSS_REMOTE_STATE: {
                "capabilities": {
                    "key_count": 8,
                    "system": 0x12,
                    "vibration": 0,
                    "configuration": 0,
                    "memory_count": 8,
                }
            },
        },
    )
    controller = await create_controller(
        coordinator, const.BED_TYPE_LIMOSS_REMOTE, None, coordinator.client
    )
    previous = dict(coordinator.entry.data)
    payloads = []

    def write(char, packet, **kwargs):
        assert coordinator.entry.data == previous
        payloads.append(LimossController._tea_decrypt(packet[1:9])[1:6].hex())
        if fail:
            raise ConnectionError("OFF write failed")

    coordinator.client.write_gatt_char.side_effect = write

    async def execute(command, **kwargs):
        assert kwargs["cancel_running"] is True
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    flow = AdjustableBedOptionsFlow(coordinator.entry)
    flow.hass = hass
    flow.handler = coordinator.entry.entry_id
    result = await flow.async_step_settings(
        {const.CONF_HAS_LIGHT: False, const.CONF_HAS_MASSAGE: False}
    )
    if fail:
        assert result["errors"] == {"base": "limoss_remote_feature_update_failed"}
        assert coordinator.entry.data == previous
        assert payloads == ["7100000000"]
        assert controller.underbed_light and controller.massage
    else:
        assert result["type"] == "create_entry"
        assert payloads == ["7100000000"] * 10 + ["6600000000"] * 10
        assert coordinator.entry.data[const.CONF_HAS_LIGHT] is False
        assert coordinator.entry.data[const.CONF_HAS_MASSAGE] is False


def test_limoss_group_requires_explicit_app_or_legacy_selection():
    from custom_components.adjustable_bed.actuator_groups import (
        ACTUATOR_GROUPS,
        get_actuator_group_for_bed_type,
        get_bed_type_for_group,
    )
    from custom_components.adjustable_bed.const import BED_TYPE_LIMOSS, BED_TYPE_LIMOSS_REMOTE

    assert get_bed_type_for_group("limoss") is None
    variants = ACTUATOR_GROUPS["limoss"]["variants"]
    assert variants is not None
    assert {variant["type"] for variant in variants} == {
        BED_TYPE_LIMOSS, BED_TYPE_LIMOSS_REMOTE,
    }
    assert get_actuator_group_for_bed_type(BED_TYPE_LIMOSS) == (
        "limoss", "Legacy Limoss / Stawett",
    )
    assert get_actuator_group_for_bed_type(BED_TYPE_LIMOSS_REMOTE) == (
        "limoss", "Limoss Remote app",
    )
