"""One Malouf / Lucid app-or-receiver question, and guided changes between its routes (#676)."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.actuator_groups import SINGLE_TYPE_GROUPS
from custom_components.adjustable_bed.beds.malouf_app import require_app_transport
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _bed_type_selector,
)
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profile_migration import ControlChanges
from tests.test_sleepys_family_flow import (
    entry_for,
    finish_check,
    gatt_client,
    reconfigure,
)
from tests.test_vibradorm_family_flow import bluetooth_patches

ADDRESS = "11:22:33:44:55:66"
# Nordic UART with the Okin notify characteristic: the apps' okin_new transport.
OKIN_NEW = (
    "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
    "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
    "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
)
OKIN_LEGACY = ("0000ffe5-0000-1000-8000-00805f9b34fb", "0000ffe9-0000-1000-8000-00805f9b34fb")
OKIN_LEGACY_NOTIFY = (
    "0000ffe0-0000-1000-8000-00805f9b34fb",
    "0000ffe4-0000-1000-8000-00805f9b34fb",
)
RECEIVERS = (const.BED_TYPE_MALOUF_NEW_OKIN, const.BED_TYPE_MALOUF_LEGACY_OKIN)


def choices(result) -> list[str]:
    return list(result["data_schema"].schema["choice"].config["options"])


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


def test_one_row_names_both_apps_and_both_receivers():
    rows = {option["value"]: option["label"] for option in get_bed_type_options()}
    label = rows[const.BED_TYPE_MALOUF_APP]
    for name in ("Malouf Base", "Lucid Base", "Nordic UART", "FFE5"):
        assert name in label
    # The receiver routes are answers of the question, not rows of their own.
    assert not set(RECEIVERS) & set(rows)
    # The brand path opens the same question instead of a try-this-first list.
    assert SINGLE_TYPE_GROUPS["malouf"] == const.BED_TYPE_MALOUF_APP


@pytest.mark.parametrize("receiver", RECEIVERS)
def test_a_detected_receiver_is_shown_as_the_family_row(receiver):
    assert _bed_type_selector(receiver).shown(receiver).startswith("Malouf / Lucid:")


async def test_the_family_row_asks_the_app_or_receiver_and_has_nothing_to_keep(hass):
    result = await setup_flow(hass, const.BED_TYPE_MALOUF_APP).async_step_malouf_family()
    assert choices(result) == ["malouf", "lucid", "nordic_uart", "ffe5"]


async def test_a_detected_receiver_is_kept_with_its_layout(hass):
    flow = setup_flow(hass, const.BED_TYPE_MALOUF_NEW_OKIN)
    result = await flow.async_step_malouf_family()
    assert choices(result)[-1] == "keep"
    result = await flow.async_step_malouf_family({"choice": "keep"})
    assert result["step_id"] == "profile_questions"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions(
            {
                const.CONF_MOTOR_COUNT: "4",
                const.CONF_MALOUF_LAYOUT: const.MALOUF_LAYOUT_FOUR_MOTOR,
                const.CONF_MALOUF_MEMORY_SLOTS: "2",
            }
        )
    saved = finish.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_MALOUF_NEW_OKIN
    assert saved[const.CONF_MOTOR_COUNT] == 4
    assert saved[const.CONF_MALOUF_LAYOUT] == const.MALOUF_LAYOUT_FOUR_MOTOR
    assert saved[const.CONF_MALOUF_MEMORY_SLOTS] == 2


async def test_the_app_asks_its_own_models_and_the_receivers_role(hass):
    flow = setup_flow(hass, const.BED_TYPE_MALOUF_LEGACY_OKIN)
    result = await flow.async_step_malouf_family({"choice": "lucid"})
    assert result["step_id"] == "profile_questions"
    assert result["description_placeholders"]["profile"] == "Lucid Base"
    fields = {marker.schema for marker in result["data_schema"].schema}
    assert {const.CONF_MALOUF_APP_MODEL, const.CONF_MALOUF_APP_PRIMARY, "advanced"} <= fields
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions(
            {const.CONF_MALOUF_APP_MODEL: "L600", const.CONF_MALOUF_APP_PRIMARY: False}
        )
    saved = finish.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_MALOUF_APP
    assert (saved[const.CONF_MALOUF_APP_PROFILE], saved[const.CONF_MALOUF_APP_MODEL]) == (
        "lucid",
        "L600",
    )
    assert saved[const.CONF_MALOUF_APP_PRIMARY] is False
    assert saved[const.CONF_MALOUF_APP_TRANSPORT] == "auto"


async def test_choosing_the_other_app_drops_the_first_apps_model(hass):
    flow = setup_flow(hass, const.BED_TYPE_MALOUF_APP)
    flow._manual_data.update(
        {const.CONF_MALOUF_APP_PROFILE: "malouf", const.CONF_MALOUF_APP_MODEL: "S755"}
    )
    await flow.async_step_malouf_family({"choice": "lucid"})
    assert const.CONF_MALOUF_APP_MODEL not in flow._manual_data


async def test_receiver_entry_changes_to_the_app_after_checking_its_transport(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_MALOUF_NEW_OKIN})
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, gatt_client(OKIN_NEW))
        result = await reconfigure(hass, entry)
        assert result["step_id"] == "malouf_family"
        assert "keep" in choices(result)
        result = await manager.async_configure(result["flow_id"], {"choice": "malouf"})
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_MALOUF_APP_MODEL: "S755"}
        )
        result = await finish_check(hass, result)
        assert result["step_id"] == "migration_confirm"
        assert result["description_placeholders"]["selection"] == "Malouf Base: S755"
        assert entry.data == before
        result = await manager.async_configure(result["flow_id"], {"confirm": True})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_MALOUF_APP
    assert entry.data[const.CONF_MALOUF_APP_MODEL] == "S755"
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)


async def test_app_change_is_refused_when_the_transport_is_ambiguous(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_MALOUF_LEGACY_OKIN})
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        # Two Okin transports: automatic selection cannot pick one.
        bluetooth_patches(stack, gatt_client(OKIN_NEW, OKIN_LEGACY, OKIN_LEGACY_NOTIFY))
        result = await reconfigure(hass, entry)
        result = await manager.async_configure(result["flow_id"], {"choice": "lucid"})
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_MALOUF_APP_MODEL: "Premium"}
        )
        result = await finish_check(hass, result)
        assert result["step_id"] != "migration_confirm"
        assert result.get("errors")
        manager.async_abort(result["flow_id"])
    assert entry.data == before


async def test_keep_in_a_guided_change_leaves_the_entry_unchanged(hass, enable_custom_integrations):
    entry = entry_for(
        hass,
        {
            const.CONF_BED_TYPE: const.BED_TYPE_MALOUF_APP,
            const.CONF_MALOUF_APP_PROFILE: "malouf",
            const.CONF_MALOUF_APP_MODEL: "Forte",
        },
    )
    before = dict(entry.data)
    result = await reconfigure(hass, entry)
    assert choices(result)[-1] == "keep"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"choice": "keep"})
    assert result["reason"] == "migration_kept"
    assert {k: v for k, v in entry.data.items() if k in before} == before


async def test_configure_keeps_a_receivers_layout(hass):
    entry = entry_for(
        hass,
        {
            const.CONF_BED_TYPE: const.BED_TYPE_MALOUF_LEGACY_OKIN,
            const.CONF_MOTOR_COUNT: 3,
            const.CONF_MALOUF_LAYOUT: const.MALOUF_LAYOUT_LUMBAR,
        },
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow._async_options_form(None, step_id="settings")
    defaults = {marker.schema: marker.default() for marker in form["data_schema"].schema}
    assert defaults[const.CONF_MALOUF_LAYOUT] == const.MALOUF_LAYOUT_LUMBAR
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await flow._async_options_form(
            {const.CONF_MALOUF_LAYOUT: const.MALOUF_LAYOUT_HILO}, step_id="settings"
        )
    assert result["type"] == "create_entry"
    assert entry.data[const.CONF_MALOUF_LAYOUT] == const.MALOUF_LAYOUT_HILO
    assert entry.data[const.CONF_MOTOR_COUNT] == 3


@pytest.mark.parametrize(
    ("name", "services", "ok"),
    [
        # No name reads as Okin, and one Okin transport answers.
        (None, (OKIN_NEW,), True),
        ("OKIN-123456", (OKIN_LEGACY, OKIN_LEGACY_NOTIFY), True),
        ("OKIN-123456", (OKIN_NEW, OKIN_LEGACY, OKIN_LEGACY_NOTIFY), False),
        # A Richmat name needs a Richmat transport.
        ("QRRM123", (OKIN_LEGACY, OKIN_LEGACY_NOTIFY), False),
    ],
)
def test_transport_check_matches_the_apps_own_selection(name, services, ok):
    data = {const.CONF_MALOUF_APP_PROFILE: "malouf", const.CONF_MALOUF_APP_MODEL: "S755"}
    client = gatt_client(*services)
    if ok:
        require_app_transport(client, data, name)  # type: ignore[arg-type]
    else:
        with pytest.raises(ConnectionError):
            require_app_transport(client, data, name)  # type: ignore[arg-type]


RICHMAT_FRAMED = ("0000fee9-0000-1000-8000-00805f9b34fb", "d44bc439-abfd-45a2-b575-925416129600")


def advertised(name: str | None):
    """An advertisement whose service info falls back to the address for no name."""
    return SimpleNamespace(name=name or ADDRESS, device=SimpleNamespace(name=name))


async def _change_receiver_to_malouf_app(hass, client, name):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_MALOUF_NEW_OKIN})
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, client)
        stack.enter_context(
            patch(
                "custom_components.adjustable_bed.config_flow.bluetooth.async_last_service_info",
                return_value=advertised(name),
            )
        )
        changes = stack.enter_context(
            patch(
                "custom_components.adjustable_bed.config_flow.async_control_changes",
                new=AsyncMock(return_value=ControlChanges(known=False)),
            )
        )
        result = await reconfigure(hass, entry)
        result = await manager.async_configure(result["flow_id"], {"choice": "malouf"})
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_MALOUF_APP_MODEL: "S755"}
        )
        result = await finish_check(hass, result)
        if result["step_id"] == "migration_confirm":
            result = await manager.async_configure(result["flow_id"], {"confirm": True})
    return entry, result, changes


async def test_an_unnamed_bed_reads_as_okin_like_the_runtime(hass, enable_custom_integrations):
    entry, result, _changes = await _change_receiver_to_malouf_app(
        hass, gatt_client(OKIN_NEW), None
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_MALOUF_APP


async def test_the_confirm_step_lists_the_checked_transports_controls(
    hass, enable_custom_integrations
):
    entry, result, changes = await _change_receiver_to_malouf_app(
        hass, gatt_client(RICHMAT_FRAMED), "QRRM123"
    )
    assert result["reason"] == "reconfigure_successful"
    previewed = changes.await_args.args[2]
    assert previewed[const.CONF_MALOUF_APP_TRANSPORT] == "richmat_framed"
    # The entry keeps the automatic choice the user made.
    assert entry.data[const.CONF_MALOUF_APP_TRANSPORT] == "auto"


async def test_a_receiver_pair_asks_each_layout_once_on_its_own_step(
    hass, enable_custom_integrations
):
    from tests.test_paired_receiver_questions import child, fields, pair_entry, receiver_form

    receiver = {const.CONF_BED_TYPE: const.BED_TYPE_MALOUF_NEW_OKIN, const.CONF_MOTOR_COUNT: 3}
    entry = pair_entry(
        hass,
        {**receiver, const.CONF_MALOUF_LAYOUT: const.MALOUF_LAYOUT_LUMBAR},
        {**receiver, const.CONF_MALOUF_LAYOUT: const.MALOUF_LAYOUT_HEAD_TILT},
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    shared = await flow._async_options_form(None, step_id="settings")
    assert const.CONF_MALOUF_LAYOUT not in {marker.schema for marker in shared["data_schema"].schema}

    left = await receiver_form(hass, entry, "left")
    assert fields(left)[const.CONF_MALOUF_LAYOUT].default() == const.MALOUF_LAYOUT_LUMBAR
    with patch.object(hass.config_entries, "async_schedule_reload"):
        await hass.config_entries.options.async_configure(
            left["flow_id"],
            {**left["data_schema"]({}), const.CONF_MALOUF_LAYOUT: const.MALOUF_LAYOUT_HILO},
        )
    assert child(entry, "left")[const.CONF_MALOUF_LAYOUT] == const.MALOUF_LAYOUT_HILO
    assert child(entry, "right")[const.CONF_MALOUF_LAYOUT] == const.MALOUF_LAYOUT_HEAD_TILT
