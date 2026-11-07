"""Manual app selection and physical-target local preferences."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.codec import limoss as codec
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.detection import detect_bed_type
from custom_components.adjustable_bed.pairing import (
    build_pair_entry_data,
    get_child,
    inheritable_child_fields,
    supports_single_address_pairing,
)
from tests.form_helpers import NEW_BED_ROUTES, finish_new_bed, shown_markers, start_new_bed

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


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_all_setup_routes_collect_explicit_profile(hass, mock_bluetooth_service_info, route):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._discovery_info = mock_bluetooth_service_info
    settings = {
        CONF_NAME: "App bed",
        const.CONF_DISCONNECT_AFTER_COMMAND: False,
        const.CONF_PREFERRED_ADAPTER: "auto",
    }
    result = await start_new_bed(flow, route, const.BED_TYPE_LIMOSS_REMOTE)
    # Limoss Remote arrives as the app itself, so the family question is
    # answered; its own questions come on the generic step.
    assert result["step_id"] == "profile_questions"
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
        result = await finish_new_bed(flow, await flow.async_step_profile_questions(
            {const.CONF_PRODUCT_TYPE: "chair", const.CONF_REVERSE_MOTORS[3]: True}
        ), settings)
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
    flow._manual_data = {CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS_REMOTE}
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        result = await flow.async_step_profile_questions(invalid)
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
        payloads.append(codec.decrypt(packet[1:9])[1:6].hex())
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


@pytest.mark.parametrize("outcome", ["sent", "failed", "cancelled"])
async def test_a_pair_receiver_finishes_its_off_bursts_before_saving(
    hass, enable_custom_integrations, outcome
):
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from tests.test_coordinator_limoss_remote import actual_coordinator

    features = {const.CONF_HAS_LIGHT: True, const.CONF_HAS_MASSAGE: True}
    receiver = actual_coordinator(
        hass,
        **features,
        **{
            const.CONF_LIMOSS_REMOTE_STATE: {
                "capabilities": {
                    "key_count": 8,
                    "system": 0x12,
                    "vibration": 0,
                    "configuration": 0,
                    "memory_count": 8,
                }
            }
        },
    )
    controller = await create_controller(
        receiver, const.BED_TYPE_LIMOSS_REMOTE, None, receiver.client
    )
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        version=5,
        data=build_pair_entry_data(
            app_data(**features),
            app_data(**features, **{CONF_ADDRESS: "11:22:33:44:55:77", CONF_NAME: "Right"}),
            name="Pair",
        ),
    )
    entry.add_to_hass(hass)
    previous = dict(entry.data)
    payloads = []

    def write(char, packet, **kwargs):
        assert entry.data == previous
        payloads.append(codec.decrypt(packet[1:9])[1:6].hex())
        if outcome == "failed":
            raise ConnectionError("OFF write failed")

    receiver.client.write_gatt_char.side_effect = write

    async def execute(command, *, side, cancel_running):
        # The pair runs the commands on this receiver's lane, as its entities do.
        assert (side, cancel_running) == ("left", True)
        if outcome == "cancelled":
            receiver.cancel_command.set()
        try:
            await command(controller)
        except asyncio.CancelledError:
            pass  # The coordinator absorbs a command it cancelled.

    pair = MagicMock(spec=PairedBedCoordinator)
    pair.child_for_side.return_value = receiver
    pair.async_execute_controller_command = AsyncMock(side_effect=execute)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = pair

    menu = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "left_settings"}
    )
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {**form["data_schema"]({}), const.CONF_HAS_LIGHT: False, const.CONF_HAS_MASSAGE: False},
    )
    pair.child_for_side.assert_called_with("left")
    if outcome == "sent":
        assert result["type"] == "create_entry"
        assert payloads == ["7100000000"] * 10 + ["6600000000"] * 10
        left = get_child(entry.data, "left") or {}
        assert not left[const.CONF_HAS_LIGHT] and not left[const.CONF_HAS_MASSAGE]
    else:
        assert result["errors"] == {"base": "limoss_remote_feature_update_failed"}
        assert entry.data == previous


def test_limoss_group_requires_explicit_app_or_legacy_selection():
    """The brand opens the Limoss question, which offers both apps and the generic controls."""
    from custom_components.adjustable_bed.actuator_groups import ACTUATOR_GROUPS
    from custom_components.adjustable_bed.app_families import LIMOSS_FAMILY
    from custom_components.adjustable_bed.const import (
        BED_TYPE_FSM_RELAX,
        BED_TYPE_LIMOSS,
        BED_TYPE_LIMOSS_REMOTE,
    )

    assert ACTUATOR_GROUPS["limoss"] == ((BED_TYPE_LIMOSS, None),)
    assert {answer.bed_type for answer in LIMOSS_FAMILY.answers.values()} == {
        BED_TYPE_LIMOSS,
        BED_TYPE_LIMOSS_REMOTE,
        BED_TYPE_FSM_RELAX,
    }


async def test_options_keep_the_apps_own_massage_question(hass):
    """The app asks massage itself, so the form shows its field for the stored route."""
    entry = MockConfigEntry(domain=const.DOMAIN, data=app_data())
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    form = await flow.async_step_settings()
    assert const.CONF_HAS_MASSAGE in shown_markers(form)
