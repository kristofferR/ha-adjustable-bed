"""One Sleepy's Elite app-or-receiver question, and guided changes between its routes (#676)."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.actuator_groups import SINGLE_TYPE_GROUPS
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.controller_factory import require_sleepys_route
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from tests.test_jiecang_app_controller import _Services
from tests.test_vibradorm_family_flow import bluetooth_patches

ADDRESS = "11:22:33:44:55:66"
NUS = (
    const.NORDIC_UART_SERVICE_UUID,
    const.NORDIC_UART_WRITE_CHAR_UUID,
    const.NORDIC_UART_READ_CHAR_UUID,
)
OKIN_64 = (const.SLEEPYS_BOX24_SERVICE_UUID, const.SLEEPYS_BOX24_WRITE_CHAR_UUID)
FFE5 = (const.KEESON_BASE_SERVICE_UUID, const.KEESON_BASE_WRITE_CHAR_UUID)


def gatt_client(*services: tuple[str, ...]) -> SimpleNamespace:
    """A connected link exposing exactly these services and their characteristics."""
    built = {}
    for service_uuid, *chars in services:
        members = {
            uuid: SimpleNamespace(uuid=uuid, properties=["write", "notify"]) for uuid in chars
        }
        built[service_uuid] = SimpleNamespace(
            uuid=service_uuid,
            characteristics=list(members.values()),
            get_characteristic=members.get,
        )
    client = SimpleNamespace(
        is_connected=True,
        address=ADDRESS,
        services=_Services(built, get_service=built.get),
        pair=AsyncMock(),
    )

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    return client


def setup_flow(hass, bed_type: str) -> AdjustableBedConfigFlow:
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Bed",
        const.CONF_BED_TYPE: bed_type,
        const.CONF_MOTOR_COUNT: 2,
        const.CONF_HAS_MASSAGE: False,
    }
    return flow


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


def choices(result) -> list[str]:
    return [option["value"] for option in result["data_schema"].schema["choice"].config["options"]]


async def reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )


async def finish_check(hass, result):
    """Run the connection check the staged route needs, then return its result.

    A passed check opens the review; a failed one says nothing was changed.
    """
    assert result["type"] == FlowResultType.SHOW_PROGRESS
    await hass.async_block_till_done()
    return await hass.config_entries.flow.async_configure(result["flow_id"])


def test_one_row_names_the_app_and_every_receiver():
    rows = {option["value"]: option["label"] for option in get_bed_type_options()}
    assert "MFRM Sleepy's Elite app" in rows[const.BED_TYPE_SLEEPYS_ELITE_APP]
    for receiver in ("BOX15", "BOX24", "BOX25"):
        assert receiver in rows[const.BED_TYPE_SLEEPYS_ELITE_APP]
    # The receiver routes are answers of the question, not rows of their own.
    assert not {
        const.BED_TYPE_SLEEPYS_BOX15,
        const.BED_TYPE_SLEEPYS_BOX24,
        const.BED_TYPE_SLEEPYS_BOX25,
    } & set(rows)
    # The brand path opens the same question instead of a try-this-first list.
    assert SINGLE_TYPE_GROUPS["sleepys"] == const.BED_TYPE_SLEEPYS_ELITE_APP


def test_a_detected_receiver_is_shown_as_the_family_row():
    from custom_components.adjustable_bed.config_flow import _bed_type_selector

    label = _bed_type_selector(const.BED_TYPE_SLEEPYS_BOX24).shown(const.BED_TYPE_SLEEPYS_BOX24)
    assert label.startswith("Sleepy's Elite: MFRM Sleepy's Elite app")


async def test_the_family_row_asks_the_app_or_receiver_and_has_nothing_to_keep(hass):
    result = await setup_flow(hass, const.BED_TYPE_SLEEPYS_ELITE_APP).async_step_sleepys_family()
    assert choices(result) == ["app", "box25", "box24", "box15"]


async def test_a_detected_receiver_is_kept_with_its_motor_count(hass):
    flow = setup_flow(hass, const.BED_TYPE_SLEEPYS_BOX24)
    result = await flow.async_step_sleepys_family()
    assert choices(result)[-1] == "keep"
    result = await flow.async_step_sleepys_family({"choice": "keep"})
    assert result["step_id"] == "keep_detected"
    result = await flow.async_step_keep_continue()
    assert result["step_id"] == "profile_questions"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_MOTOR_COUNT: "3"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_SLEEPYS_BOX24
    assert saved[const.CONF_MOTOR_COUNT] == 3


async def test_box25_asks_massage_and_leaves_its_dialect_to_auto(hass):
    flow = setup_flow(hass, const.BED_TYPE_SLEEPYS_ELITE_APP)
    result = await flow.async_step_sleepys_family({"choice": "box25"})
    assert result["step_id"] == "profile_questions"
    fields = {marker.schema for marker in result["data_schema"].schema}
    assert {const.CONF_HAS_MASSAGE, "advanced"} <= fields
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_HAS_MASSAGE: True})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_SLEEPYS_BOX25
    assert saved[const.CONF_PROTOCOL_VARIANT] == const.VARIANT_AUTO
    assert saved[const.CONF_HAS_MASSAGE] is True


async def test_a_box25_receiver_offers_the_apps_its_review_suggests(hass):
    flow = setup_flow(hass, const.BED_TYPE_SLEEPYS_BOX25)
    result = await flow.async_step_sleepys_family()
    assert const.BED_TYPE_ADJUSTABLE_LUMBAR in choices(result)
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_sleepys_family({"choice": const.BED_TYPE_ADJUSTABLE_LUMBAR})
    assert finish.call_args.args[0][const.CONF_BED_TYPE] == const.BED_TYPE_ADJUSTABLE_LUMBAR


async def test_receiver_entry_changes_to_the_app_after_checking_its_routes(
    hass, enable_custom_integrations
):
    entry = entry_for(
        hass, {const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_BOX24, const.CONF_MOTOR_COUNT: 2}
    )
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, gatt_client(NUS))
        result = await reconfigure(hass, entry)
        assert result["step_id"] == "sleepys_family"
        assert "keep" in choices(result)
        result = await manager.async_configure(result["flow_id"], {"choice": "app"})
        assert result["step_id"] == "profile_questions"
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_SLEEPYS_ELITE_SELECTOR: "BOX24"}
        )
        result = await finish_check(hass, result)
        assert result["step_id"] == "migration_confirm"
        assert result["description_placeholders"]["selection"].endswith(": BOX24")
        assert entry.data == before
        result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_SLEEPYS_ELITE_APP
    assert entry.data[const.CONF_SLEEPYS_ELITE_SELECTOR] == "BOX24"
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)


async def test_receiver_change_is_refused_when_the_link_lacks_its_endpoint(
    hass, enable_custom_integrations
):
    entry = entry_for(
        hass,
        {
            const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_ELITE_APP,
            const.CONF_SLEEPYS_ELITE_SELECTOR: "BOX24",
        },
    )
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        # The app's BOX24 selector runs on Nordic UART; the BOX24 receiver route does not.
        bluetooth_patches(stack, gatt_client(NUS))
        result = await reconfigure(hass, entry)
        result = await manager.async_configure(result["flow_id"], {"choice": "box24"})
        result = await manager.async_configure(result["flow_id"], {const.CONF_MOTOR_COUNT: "2"})
        result = await finish_check(hass, result)
        assert result["step_id"] == "migration_check_failed"
        manager.async_abort(result["flow_id"])
    assert entry.data == before


async def test_keep_in_a_guided_change_leaves_the_entry_unchanged(hass, enable_custom_integrations):
    entry = entry_for(
        hass,
        {
            const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_ELITE_APP,
            const.CONF_SLEEPYS_ELITE_SELECTOR: "BOX15",
        },
    )
    before = dict(entry.data)
    result = await reconfigure(hass, entry)
    assert choices(result)[-1] == "keep"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"choice": "keep"})
    assert result["reason"] == "migration_kept"
    assert {k: v for k, v in entry.data.items() if k in before} == before


async def test_configure_sends_a_dialect_change_to_the_guided_change(hass):
    entry = entry_for(
        hass, {const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_BOX25, const.CONF_HAS_MASSAGE: True}
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow._async_options_form(None, step_id="settings")
    fields = {marker.schema for marker in form["data_schema"].schema}
    # Routine settings stay; the dialect changes only through Reconfigure.
    assert const.CONF_HAS_MASSAGE in fields
    assert const.CONF_PROTOCOL_VARIANT not in fields
    result = await flow._async_options_form(
        {const.CONF_PROTOCOL_VARIANT: const.SLEEPYS_BOX25_VARIANT_LEGACY}, step_id="settings"
    )
    assert result["errors"] == {"base": "migration_reconfigure_required"}
    assert const.CONF_PROTOCOL_VARIANT not in entry.data


async def test_configure_into_the_app_from_another_bed_type_asks_its_selector(hass):
    entry = entry_for(
        hass, {const.CONF_BED_TYPE: const.BED_TYPE_LINAK, const.CONF_MOTOR_COUNT: 2}
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow._async_options_form(
        {const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_ELITE_APP}, step_id="settings"
    )
    # Only an entry already on the family leaves the selector to Reconfigure.
    assert const.CONF_SLEEPYS_ELITE_SELECTOR in {
        marker.schema for marker in form["data_schema"].schema
    }
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await flow._async_options_form(
            {const.CONF_SLEEPYS_ELITE_SELECTOR: "BOX25"}, step_id="settings"
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_SLEEPYS_ELITE_APP
    assert entry.data[const.CONF_SLEEPYS_ELITE_SELECTOR] == "BOX25"
    assert entry.data[const.CONF_HAS_MASSAGE] is True


@pytest.mark.parametrize(
    ("data", "services", "ok"),
    [
        ({const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_BOX15}, (FFE5,), True),
        ({const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_BOX15}, (NUS,), False),
        ({const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_BOX24}, (OKIN_64,), True),
        ({const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_BOX25}, (NUS,), True),
        (
            {
                const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_ELITE_APP,
                const.CONF_SLEEPYS_ELITE_SELECTOR: "BOX25_STAR",
            },
            (NUS,),
            True,
        ),
        # The app's BOX15 selector needs its FFE0 response service too.
        (
            {
                const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_ELITE_APP,
                const.CONF_SLEEPYS_ELITE_SELECTOR: "BOX15",
            },
            (FFE5,),
            False,
        ),
    ],
)
def test_route_check_matches_what_each_route_needs(data, services, ok):
    client = gatt_client(*services)
    if ok:
        require_sleepys_route(client, data)  # type: ignore[arg-type]
    else:
        with pytest.raises(ConnectionError):
            require_sleepys_route(client, data)  # type: ignore[arg-type]
