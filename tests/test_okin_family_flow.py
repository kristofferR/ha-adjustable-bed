"""One Okin app-or-remote question, and guided changes between its routes (#676)."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.const import (
    CONF_STAIRCASE_LAYOUT_CONFIRMED,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
    OKIMAT_SERVICE_UUID,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_DOT_FURNIMOVE_VARIANTS,
)
from custom_components.adjustable_bed.controller_factory import require_okin_route_endpoint
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from tests.test_jiecang_app_controller import _Services
from tests.test_vibradorm_family_flow import bluetooth_patches

ADDRESS = "11:22:33:44:55:66"
OKIN = (OKIMAT_SERVICE_UUID, OKIMAT_WRITE_CHAR_UUID)
DOT = (NORDIC_UART_SERVICE_UUID, NORDIC_UART_WRITE_CHAR_UUID)


def okin_client(*endpoints: tuple[str, str]) -> SimpleNamespace:
    """A connected link exposing exactly the given writable command endpoints."""
    services = {
        service: SimpleNamespace(
            uuid=service,
            characteristics=[SimpleNamespace(uuid=char, properties=["write"])],
            get_characteristic={char: SimpleNamespace(uuid=char)}.get,
        )
        for service, char in endpoints
    }
    client = SimpleNamespace(
        is_connected=True,
        address=ADDRESS,
        services=_Services(services, get_service=services.get),
        pair=AsyncMock(),
    )

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    return client


def entry_for(hass, data) -> MockConfigEntry:
    data = {CONF_ADDRESS: ADDRESS, const.CONF_PREFERRED_ADAPTER: "auto", **data}
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Bedroom",
        unique_id=ADDRESS,
        version=5,
        data={**data, const.CONF_PROFILE_ID: resolve_profile_id(data)},
    )
    entry.add_to_hass(hass)
    return entry


def setup_flow(hass, bed_type: str) -> AdjustableBedConfigFlow:
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Bed",
        const.CONF_BED_TYPE: bed_type,
        const.CONF_MOTOR_COUNT: 2,
    }
    return flow


def choices(result) -> list[str]:
    return [option["value"] for option in result["data_schema"].schema["choice"].config["options"]]


async def reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )


async def finish_check(hass, result):
    """Run the connection check a route needs, then return the review."""
    manager = hass.config_entries.flow
    if result["type"] == FlowResultType.FORM and result["step_id"] == "manual_pairing":
        result = await manager.async_configure(result["flow_id"], {"action": "pair_now"})
    assert result["type"] == FlowResultType.SHOW_PROGRESS
    await hass.async_block_till_done()
    result = await manager.async_configure(result["flow_id"])
    if result["step_id"] == "pairing_result":
        # A passed pairing shows its outcome before the review.
        result = await manager.async_configure(result["flow_id"], {})
    return result


async def test_detected_receiver_offers_routes_review_apps_and_keep(hass):
    flow = setup_flow(hass, const.BED_TYPE_OKIN_UUID)
    result = await flow.async_step_okin_family()
    offered = choices(result)
    assert offered[:4] == ["furnimove", "okin_uuid", "okin_dot", "okin_rf_eco_bt"]
    # The apps the app review suggests for this route are one answer away.
    assert {"serenity", "tranquil", "adjustable_lumbar"} <= set(offered)
    assert offered[-1] == "keep"
    result = await flow.async_step_okin_family({"choice": "keep"})
    assert result["step_id"] == "keep_detected"
    result = await flow.async_step_keep_continue()
    assert result["step_id"] == "profile_questions"
    assert flow._manual_data[const.CONF_BED_TYPE] == const.BED_TYPE_OKIN_UUID


@pytest.mark.parametrize(
    ("bed_type", "variant"),
    [
        (const.BED_TYPE_OKIN_UUID, "auto"),
        (const.BED_TYPE_OKIMAT, "62612"),
        (const.BED_TYPE_OKIN_DOT, "97450"),
    ],
)
@pytest.mark.parametrize("motor_count", [3, 4])
async def test_keep_detected_controls_collects_motors_without_changing_route(
    hass, bed_type, variant, motor_count
):
    flow = setup_flow(hass, bed_type)
    assert flow._manual_data is not None
    flow._manual_data[const.CONF_PROTOCOL_VARIANT] = variant
    before = dict(flow._manual_data)
    result = await flow.async_step_okin_family({"choice": "keep"})
    assert result["step_id"] == "keep_detected"
    result = await flow.async_step_keep_continue()
    assert result["step_id"] == "profile_questions"
    assert result["data_schema"] is not None
    answers = result["data_schema"]({const.CONF_MOTOR_COUNT: str(motor_count)})
    with patch.object(flow, "_async_finish_family_route", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions(answers)
    finish.assert_awaited_once()
    # Only the answers change: the route stays, and the massage and angle
    # sensing the FurniMove row's form never showed take their defaults.
    assert answers[const.CONF_MOTOR_COUNT] == motor_count
    assert flow._manual_data == {**before, **answers}


async def test_family_row_has_no_route_to_keep(hass):
    flow = setup_flow(hass, const.BED_TYPE_FURNIMOVE)
    result = await flow.async_step_okin_family()
    assert "keep" not in choices(result)
    result = await flow.async_step_okin_family({"choice": "furnimove"})
    assert result["step_id"] == "profile_questions"


async def test_dot_remote_asks_its_code_and_motors_with_its_own_cadence(hass):
    flow = setup_flow(hass, const.BED_TYPE_FURNIMOVE)
    result = await flow.async_step_okin_family({"choice": "okin_dot"})
    assert result["step_id"] == "profile_questions"
    codes = result["data_schema"].schema[const.CONF_PROTOCOL_VARIANT].container
    # FurniMove's DOT handsets belong to the app answer, not this one.
    assert OKIN_DOT_FURNIMOVE_VARIANTS.isdisjoint(codes)
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions(
            {const.CONF_PROTOCOL_VARIANT: "97450", const.CONF_MOTOR_COUNT: "2"}
        )
    saved = finish.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_OKIN_DOT
    assert saved[const.CONF_PROTOCOL_VARIANT] == "97450"
    assert saved[const.CONF_MOTOR_COUNT] == 2
    assert (saved[const.CONF_MOTOR_PULSE_COUNT], saved[const.CONF_MOTOR_PULSE_DELAY_MS]) == (
        const.get_motor_pulse_defaults(const.BED_TYPE_OKIN_DOT, "97450")
    )
    assert saved[const.CONF_MOTOR_PULSE_USER_SET] is False


async def test_choosing_the_staircase_confirms_it(hass):
    flow = setup_flow(hass, const.BED_TYPE_FURNIMOVE)
    with patch.object(flow, "async_step_manual_pairing", new=AsyncMock()) as pairing:
        await flow.async_step_okin_family({"choice": "okin_rf_eco_bt"})
    pairing.assert_awaited_once()
    assert flow._manual_data[const.CONF_BED_TYPE] == const.BED_TYPE_OKIN_RF_ECO_BT
    assert flow._manual_data[CONF_STAIRCASE_LAYOUT_CONFIRMED] is True
    assert flow._manual_data[const.CONF_MOTOR_COUNT] == 1


async def test_review_app_answer_switches_to_that_app(hass):
    flow = setup_flow(hass, const.BED_TYPE_OKIMAT)
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_okin_family({"choice": "customatic_zseries:z230"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_ZSERIES
    assert saved[const.CONF_PROTOCOL_VARIANT] == const.ZSERIES_VARIANT_Z230


async def test_okin_uuid_entry_changes_to_furnimove_after_checking_its_endpoint(
    hass, enable_custom_integrations
):
    entry = entry_for(
        hass, {const.CONF_BED_TYPE: const.BED_TYPE_OKIN_UUID, const.CONF_MOTOR_COUNT: 2}
    )
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, okin_client(OKIN))
        result = await reconfigure(hass, entry)
        assert result["step_id"] == "okin_family"
        assert "keep" in choices(result)
        result = await manager.async_configure(result["flow_id"], {"choice": "furnimove"})
        assert result["step_id"] == "profile_questions"
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_FURNIMOVE_REMOTE: "82417"}
        )
        result = await finish_check(hass, result)
        assert result["step_id"] == "migration_confirm"
        assert entry.data == before
        result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_FURNIMOVE
    assert entry.data[const.CONF_FURNIMOVE_REMOTE] == "82417"
    assert const.CONF_PROTOCOL_VARIANT not in entry.data
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)
    assert entry.data[const.CONF_PROFILE_ID] != before[const.CONF_PROFILE_ID]


async def test_furnimove_handset_is_corrected_through_the_guided_change(
    hass, enable_custom_integrations
):
    entry = entry_for(
        hass,
        {
            const.CONF_BED_TYPE: const.BED_TYPE_FURNIMOVE,
            const.CONF_FURNIMOVE_REMOTE: "90167",
            const.CONF_MOTOR_COUNT: 2,
        },
    )
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, okin_client(DOT))
        result = await reconfigure(hass, entry)
        result = await manager.async_configure(result["flow_id"], {"choice": "furnimove"})
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_FURNIMOVE_REMOTE: "82417"}
        )
        result = await finish_check(hass, result)
        result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_FURNIMOVE_REMOTE] == "82417"


async def test_change_is_refused_when_the_link_lacks_the_routes_endpoint(
    hass, enable_custom_integrations
):
    entry = entry_for(
        hass, {const.CONF_BED_TYPE: const.BED_TYPE_OKIN_UUID, const.CONF_MOTOR_COUNT: 2}
    )
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, okin_client(OKIN))
        result = await reconfigure(hass, entry)
        result = await manager.async_configure(result["flow_id"], {"choice": "okin_dot"})
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_PROTOCOL_VARIANT: "auto", const.CONF_MOTOR_COUNT: 2}
        )
        result = await finish_check(hass, result)
        assert result["step_id"] == "migration_check_failed"
        manager.async_abort(result["flow_id"])
    assert entry.data == before


async def test_okimat_code_change_keeps_the_saved_id_and_needs_the_bond(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_OKIMAT, const.CONF_MOTOR_COUNT: 2})
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, okin_client(OKIN))
        result = await reconfigure(hass, entry)
        result = await manager.async_configure(result["flow_id"], {"choice": "okin_uuid"})
        assert result["step_id"] == "profile_questions"
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_PROTOCOL_VARIANT: "62612", const.CONF_MOTOR_COUNT: 4}
        )
        assert result["step_id"] == "manual_pairing"
        result = await finish_check(hass, result)
        assert result["step_id"] == "migration_confirm"
        result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_OKIMAT
    assert entry.data[const.CONF_PROTOCOL_VARIANT] == "62612"
    assert entry.data[const.CONF_MOTOR_COUNT] == 4


async def test_okin_entry_changes_to_a_review_app_like_configure_did(
    hass, enable_custom_integrations
):
    entry = entry_for(
        hass, {const.CONF_BED_TYPE: const.BED_TYPE_OKIN_UUID, const.CONF_MOTOR_COUNT: 2}
    )
    manager = hass.config_entries.flow
    result = await reconfigure(hass, entry)
    result = await manager.async_configure(result["flow_id"], {"choice": "customatic_zseries:z230"})
    assert result["step_id"] == "migration_confirm"
    result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_ZSERIES
    assert entry.data[const.CONF_PROTOCOL_VARIANT] == const.ZSERIES_VARIANT_Z230
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)


async def test_keep_in_a_guided_change_leaves_the_entry_unchanged(hass, enable_custom_integrations):
    entry = entry_for(
        hass, {const.CONF_BED_TYPE: const.BED_TYPE_OKIN_DOT, const.CONF_MOTOR_COUNT: 2}
    )
    before = dict(entry.data)
    result = await reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"choice": "keep"})
    assert result["reason"] == "migration_kept"
    assert {k: v for k, v in entry.data.items() if k in before} == before


async def test_configure_saves_settings_but_sends_a_code_change_to_the_guided_change(hass):
    entry = entry_for(
        hass, {const.CONF_BED_TYPE: const.BED_TYPE_OKIN_UUID, const.CONF_MOTOR_COUNT: 2}
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    result = await flow._async_options_form(
        {const.CONF_PROTOCOL_VARIANT: "62612"}, step_id="settings"
    )
    assert result["errors"] == {"base": "migration_reconfigure_required"}
    assert const.CONF_PROTOCOL_VARIANT not in entry.data


@pytest.mark.parametrize(
    ("bed_type", "endpoints", "ok"),
    [
        (const.BED_TYPE_OKIN_UUID, (OKIN,), True),
        # An Okin UUID entry also drives a DOT box.
        (const.BED_TYPE_OKIN_UUID, (DOT,), True),
        (const.BED_TYPE_FURNIMOVE, (DOT,), True),
        (const.BED_TYPE_OKIN_DOT, (OKIN,), False),
        (const.BED_TYPE_OKIN_RF_ECO_BT, (DOT,), False),
        (const.BED_TYPE_FURNIMOVE, (), False),
    ],
)
def test_endpoint_check_matches_what_each_route_writes(bed_type, endpoints, ok):
    client = okin_client(*endpoints)
    if ok:
        require_okin_route_endpoint(client, bed_type)  # type: ignore[arg-type]
    else:
        with pytest.raises(ConnectionError):
            require_okin_route_endpoint(client, bed_type)  # type: ignore[arg-type]


async def test_discovered_cst_bed_is_asked_with_its_apps_first(
    hass, enable_custom_integrations, mock_bluetooth_service_info_okimat
):
    """A bed chosen as Okin CST on discovery (#573) gets the Okin question."""
    from homeassistant.config_entries import SOURCE_BLUETOOTH

    info = mock_bluetooth_service_info_okimat
    info.name = "OKIN-003444"
    manager = hass.config_entries.flow
    result = await manager.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )
    assert result["step_id"] == "bluetooth_disambiguate"
    result = await manager.async_configure(
        result["flow_id"], {"bed_type_choice": const.BED_TYPE_OKIN_CST}
    )
    assert result["step_id"] == "okin_family"
    offered = choices(result)
    cst_apps = [f"okin_cst:{v}" for v in const.OKIN_CST_VARIANTS if v != const.VARIANT_AUTO]
    apps = ["serenity", "tranquil", "customatic_zseries:z230", "customatic_zseries:z280"]
    routes = ["furnimove", "okin_uuid", "okin_dot", "okin_rf_eco_bt"]
    # A discovered bed's question also searches every other app.
    assert offered == [*cst_apps, *apps, *routes, "another", "keep"]
    manager.async_abort(result["flow_id"])


@pytest.mark.parametrize(
    ("choice", "bed_type", "variant"),
    [
        ("okin_cst:cst_resident", const.BED_TYPE_OKIN_CST, "cst_resident"),
        ("okin_cst:cst_nectar_move", const.BED_TYPE_OKIN_CST, "cst_nectar_move"),
        ("serenity", const.BED_TYPE_SERENITY, None),
        ("keep", const.BED_TYPE_OKIN_CST, "auto"),
    ],
)
async def test_cst_answer_saves_its_route(hass, choice, bed_type, variant):
    flow = setup_flow(hass, const.BED_TYPE_OKIN_CST)
    assert flow._manual_data is not None
    flow._manual_data[const.CONF_PROTOCOL_VARIANT] = const.VARIANT_AUTO
    with patch.object(flow, "_async_finish_family_route", new=AsyncMock()) as finish:
        result = await flow.async_step_okin_family({"choice": choice})
        if choice == "keep":
            assert result["step_id"] == "keep_detected"
            await flow.async_step_keep_continue()
    finish.assert_awaited_once()
    assert flow._manual_data[const.CONF_BED_TYPE] == bed_type
    assert flow._manual_data.get(const.CONF_PROTOCOL_VARIANT) == variant


@pytest.mark.parametrize(
    "variant", [const.OKIN_CST_VARIANT_NECTAR_MOVE, const.OKIN_CST_VARIANT_CAREFREE]
)
async def test_a_chosen_cst_app_skips_the_question(hass, variant):
    """The Nectar Move row, or an explicit product, already names the app."""
    flow = setup_flow(hass, const.BED_TYPE_OKIN_CST)
    assert flow._manual_data is not None
    flow._manual_data[const.CONF_PROTOCOL_VARIANT] = variant
    with patch.object(flow, "_async_finish_family_route", new=AsyncMock()) as finish:
        await flow.async_step_okin_family()
    finish.assert_awaited_once()


async def test_a_cst_entry_changes_to_an_okin_route_after_checking_its_endpoint(
    hass, enable_custom_integrations
):
    """CST keeps Configure for its products; Reconfigure reaches the other Okin routes."""
    entry = entry_for(
        hass,
        {
            const.CONF_BED_TYPE: const.BED_TYPE_OKIN_CST,
            const.CONF_PROTOCOL_VARIANT: const.OKIN_CST_VARIANT_CAREFREE,
            const.CONF_MOTOR_COUNT: 2,
        },
    )
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, okin_client(DOT))
        result = await reconfigure(hass, entry)
        assert result["step_id"] == "okin_family"
        offered = choices(result)
        # Its own products come first, and Keep leaves it as it is.
        assert offered[0].startswith("okin_cst:") and offered[-1] == "keep"
        assert {"okin_uuid", "okin_dot", "okin_rf_eco_bt"} <= set(offered)
        result = await manager.async_configure(result["flow_id"], {"choice": "okin_dot"})
        assert result["step_id"] == "profile_questions"
        result = await manager.async_configure(result["flow_id"], result["data_schema"]({}))
        result = await finish_check(hass, result)
        assert result["step_id"] == "migration_confirm"
        result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_OKIN_DOT
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)
