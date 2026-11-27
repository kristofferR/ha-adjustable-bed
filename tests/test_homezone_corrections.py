"""Published Home Zone timeout delivery and translated settings rejections."""

import asyncio
from contextlib import suppress
from dataclasses import replace

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.richmat_classic.controller import PREFERENCES
from custom_components.adjustable_bed.beds.richmat_classic.homezone import HomeZoneController
from custom_components.adjustable_bed.beds.richmat_classic.resource_controller import LAMP_TIMEOUT
from custom_components.adjustable_bed.beds.richmat_classic.resource_protocol import Request
from custom_components.adjustable_bed.command_scheduler import current_command_context
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock
from tests.test_homezone import packets
from tests.test_homezone_runtime import runtime as runtime


@pytest.mark.parametrize("cancellation", ["event", "task"])
async def test_delivered_timeout_survives_cancellation_and_next_publish(runtime, cancellation):
    coordinator, ctrl, double = runtime
    ctrl._receive.light_capable = True
    await coordinator._async_restore_app_state(ctrl)
    entered, finish = asyncio.Event(), asyncio.Event()
    admitted = []

    async def write(*args, **kwargs):
        context = current_command_context()
        assert context is not None
        admitted.append(context.cancel_event)
        entered.set()
        await finish.wait()

    double.client.write_gatt_char.side_effect = write
    with virtual_clock():
        task = asyncio.create_task(
            coordinator.async_execute_controller_command(
                lambda c: c.execute_request(Request("lamp_timeout", seconds=120)),
                resource="configuration",
            )
        )
        await entered.wait()
        if cancellation == "event":
            admitted[0].set()
        else:
            task.cancel()
        await asyncio.sleep(0)
        finish.set()
        with suppress(asyncio.CancelledError):
            await task
    assert packets(double) == ["6e0b0078f1"]
    assert coordinator.controller_state[LAMP_TIMEOUT] == ctrl._lamp_timeout == 120
    assert coordinator.controller_state[PREFERENCES]["lamp_timeout"] == 120
    assert ctrl.persisted_app_state["lamp_timeout"] == 120
    assert (await coordinator._app_state_store.async_slot(coordinator._app_state_slots[ctrl]))[
        "lamp_timeout"
    ] == 120
    ctrl._publish()
    assert coordinator.controller_state[LAMP_TIMEOUT] == 120


@pytest.mark.parametrize("replacement", [False, True])
async def test_unsent_or_replaced_timeout_does_not_publish(runtime, replacement):
    coordinator, ctrl, double = runtime
    ctrl._receive.light_capable = True
    with virtual_clock():
        await coordinator.async_execute_controller_command(
            lambda c: c.execute_request(Request("lamp_timeout", seconds=30))
        )
    before = dict(ctrl.persisted_app_state)
    double.client.write_gatt_char.reset_mock()

    async def write(*args, **kwargs):
        ctrl._session = replace(ctrl._session)

    if replacement:
        double.client.write_gatt_char.side_effect = write

    async def operation(c):
        if not replacement:
            current_command_context().cancel_event.set()
        await c.execute_request(Request("lamp_timeout", seconds=120))

    with virtual_clock():
        await coordinator.async_execute_controller_command(operation)
    assert len(packets(double)) == int(replacement)
    assert coordinator.controller_state[LAMP_TIMEOUT] == ctrl._lamp_timeout == 30
    assert dict(ctrl.persisted_app_state) == before
    ctrl._publish()
    assert coordinator.controller_state[LAMP_TIMEOUT] == 30


def test_saved_timeout_is_a_preference_without_connection_permission(runtime):
    coordinator, _, double = runtime
    ctrl = HomeZoneController(coordinator)
    ctrl.restore_persisted_app_state({"lamp_timeout": 120})
    assert ctrl.persisted_app_state["lamp_timeout"] == 120
    assert ctrl._lamp_timeout is None and not ctrl._receive.light_capable
    assert ctrl.controller_number_specs == ()
    assert packets(double) == []


@pytest.mark.parametrize(
    "layout,operation,fields,key",
    [
        ("BTRM", "lamp_timeout", {}, "value_out_of_range"),
        ("BTRM", "lamp_timeout", {"seconds": 120}, "homezone_light_unavailable"),
        ("BTRM", "aroma", {"aroma_times": [0, 1, 1]}, "homezone_aroma_range"),
        ("BTRM", "aroma", {"aroma_times": [1, 1, 1]}, "homezone_aroma_unavailable"),
        ("BTRM", "massage_timer", {"progress": 2}, "homezone_massage_slider"),
        ("D1RM", "massage_timer", {}, "value_out_of_range"),
        ("Y6RM", "massage_popup", {}, "homezone_massage_popup"),
        ("BTRM", "rgb", {}, "homezone_color"),
        ("BTRM", "rgb", {"rgb_color": [1, 2, 3]}, "homezone_light_unavailable"),
    ],
)
async def test_public_settings_rejections_are_translated(
    hass, runtime, layout, operation, fields, key
):
    coordinator, original, double = runtime
    hass.config_entries.async_update_entry(
        coordinator.entry, data={**coordinator.entry.data, "product_type": layout}
    )
    ctrl = HomeZoneController(coordinator)
    ctrl._session = original._session
    coordinator._controller = ctrl
    with raises_key(key) as raised:
        await hass.services.async_call(
            const.DOMAIN,
            "homezone",
            {"device_id": ["bed"], "operation": operation, **fields},
            blocking=True,
        )
    assert raised.value.translation_domain == const.DOMAIN
    assert "reason" not in raised.value.translation_placeholders
    assert packets(double) == []
