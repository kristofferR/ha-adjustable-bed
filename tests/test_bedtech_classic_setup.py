"""Bed Tech stays explicit across setup, reconfiguration, restore and pairing."""

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.bedtech.classic import BedTechClassicController
from custom_components.adjustable_bed.beds.bedtech.sleep import BedTechSleepController
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profile_id import profile_route, resolve_profile_id
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_richmat_family_flow import answer, entry_for, fields, setup_flow


async def test_setup_and_configure_keep_selected_app(hass):
    flow = setup_flow(hass, name="CFRM0001")
    form, finish = await answer(flow, "bedtech_classic")
    assert form["step_id"] == "profile_questions"
    finish.assert_not_awaited()
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: "model_5i"})
    data = finish.call_args.args[0]
    assert data[const.CONF_BED_TYPE] == "bedtech_classic"
    assert profile_route(resolve_profile_id(data)).variant == "model_5i"
    entry = entry_for(
        hass, **{const.CONF_BED_TYPE: "bedtech_classic", const.CONF_PROTOCOL_VARIANT: "model_5i"}
    )
    options = AdjustableBedOptionsFlow(entry)
    options.hass, options.handler = hass, entry.entry_id
    form = await options.async_step_settings()
    assert const.CONF_PROTOCOL_VARIANT not in fields(form)


async def test_restored_native_profile_selects_actual_factory(hass):
    for variant, cls in (
        ("model_cfrm", BedTechClassicController),
        ("sleep", BedTechSleepController),
    ):
        data = {
            CONF_ADDRESS: "11:22:33:44:55:66",
            const.CONF_BED_TYPE: "bedtech_classic",
            const.CONF_PROTOCOL_VARIANT: variant,
            const.CONF_BLE_DEVICE_NAME: "VORM1234",
        }
        data[const.CONF_PROFILE_ID] = resolve_profile_id(data)
        entry = MockConfigEntry(domain=const.DOMAIN, source="import", version=5, data=data)
        entry.add_to_hass(hass)
        coordinator = _FactoryCoordinator()
        coordinator.hass, coordinator.entry = hass, entry
        route = profile_route(data[const.CONF_PROFILE_ID])
        ctrl = await create_controller(coordinator, route.bed_type, route.variant, None)
        assert isinstance(ctrl, cls)
        assert not ctrl.supports_single_address_pairing


async def test_pair_keeps_each_selected_model_and_runtime_mode(hass):
    from custom_components.adjustable_bed import _async_sync_profile_ids, _build_paired_children
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from tests.test_paired_receiver_questions import child, pair_entry

    entry = pair_entry(
        hass,
        {const.CONF_BED_TYPE: "bedtech_classic", const.CONF_PROTOCOL_VARIANT: "model_cfrm"},
        {const.CONF_BED_TYPE: "bedtech_classic", const.CONF_PROTOCOL_VARIANT: "model_5i"},
    )
    _async_sync_profile_ids(hass, entry)
    children = _build_paired_children(hass, entry)
    paired = PairedBedCoordinator(hass, entry, children)
    try:
        left = await create_controller(children["left"], "bedtech_classic", "model_cfrm", None)
        right = await create_controller(children["right"], "bedtech_classic", "model_5i", None)
        assert isinstance(left, BedTechClassicController)
        assert isinstance(right, BedTechClassicController)
        left.set_transmit_mode("2")
        saved_left = child(entry, "left")
        right.set_transmit_mode("1")
        assert child(entry, "left") == saved_left
        assert child(entry, "right")["capabilities"]["richmat_mh"]["transmit_mode"] == 1
        assert profile_route(child(entry, "left")[const.CONF_PROFILE_ID]).variant == "model_cfrm"
        restored = await create_controller(children["right"], "bedtech_classic", "model_5i", None)
        assert isinstance(restored, BedTechClassicController) and restored._transmit_mode == 1
    finally:
        await paired.async_shutdown()


async def test_local_mode_rechecks_profile_and_stop_after_import(hass):
    from custom_components.adjustable_bed.beds.richmat_mh import app_services as actions
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.services import async_register_services
    from tests.error_helpers import raises_key

    data = {
        CONF_ADDRESS: "11:22:33:44:55:77",
        const.CONF_BED_TYPE: "bedtech_classic",
        const.CONF_PROTOCOL_VARIANT: "model_5i",
        "capabilities": {"richmat_mh": {"app": "bedtech_classic", "model": "5i"}},
    }
    data[const.CONF_PROFILE_ID] = resolve_profile_id(data)
    entry = MockConfigEntry(domain=const.DOMAIN, version=5, data=data)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_prime_offline_controller()
    ctrl = coordinator.capability_controller
    assert isinstance(ctrl, BedTechClassicController)
    await async_register_services(hass)

    async def change_profile(*_args):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, const.CONF_PROTOCOL_VARIANT: "model_cfrm"}
        )

    async def stop(*_args):
        epoch = coordinator.command_scheduler.request_stop()
        coordinator.command_scheduler.finish_stop(epoch)

    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, "both")], []),
    ):
        with (
            patch.object(actions, "async_import_modules", side_effect=change_profile),
            raises_key("bed_changed"),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                actions.SERVICE,
                {
                    "device_id": ["bed"],
                    "action": "app_mode",
                    "transmit_mode": "mode_2",
                },
                blocking=True,
            )
        assert ctrl._transmit_mode == 0
        with patch.object(actions, "async_import_modules", side_effect=stop):
            await hass.services.async_call(
                const.DOMAIN,
                actions.SERVICE,
                {
                    "device_id": ["bed"],
                    "action": "app_mode",
                    "transmit_mode": "mode_1",
                },
                blocking=True,
            )
        assert ctrl._transmit_mode == 0
