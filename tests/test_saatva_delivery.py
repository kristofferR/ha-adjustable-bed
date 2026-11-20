"""Interrupted Saatva command frames must settle as partial delivery."""

import asyncio
from contextlib import nullcontext
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.adjustable_bed.codec.richmat import command
from custom_components.adjustable_bed.command_scheduler import Delivery, delivered
from tests.test_saatva import runtime, written


@pytest.mark.parametrize("where", ["after_left", "during_right", "between_ticks"])
async def test_cancel_marks_required_unsent_frames(hass, where):
    c = await runtime(hass)
    entered = asyncio.Event()
    shown = []

    async def write(_uuid, packet, **_kwargs):
        if where == "after_left" and packet[2] == 0:
            c.cancel_command.set()
        if where == "during_right" and packet[2] == 1:
            entered.set()
            await asyncio.Event().wait()

    async def delay(operation, _event):
        operation.close()
        entered.set()
        await asyncio.Event().wait()

    async def run(ctrl):
        with delivered(shown.append):
            await ctrl.write_command(command(0x24), repeat_count=2)

    c.client.write_gatt_char.side_effect = write
    try:
        with (
            patch("custom_components.adjustable_bed.beds.saatva.cancellable", new=delay)
            if where == "between_ticks"
            else nullcontext()
        ):
            task = asyncio.create_task(c.async_execute_controller_command(run))
            if where != "after_left":
                await asyncio.wait_for(entered.wait(), 1)
                await c.async_stop_command()
            await task
        assert shown == [Delivery.PARTIAL]
        assert written(c)[0] == "6e01002493"
        assert len(written(c)) <= 2
    finally:
        await c.async_shutdown()


async def test_timer_failure_never_publishes_requested_state(hass):
    from bleak.exc import BleakError

    from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES

    c = await runtime(hass)
    try:
        await c.async_execute_controller_command(lambda ctrl: ctrl.set_massage_timer(10))
        c.client.write_gatt_char = AsyncMock(side_effect=BleakError("write failed"))
        with pytest.raises(BleakError):
            await c.async_execute_controller_command(lambda ctrl: ctrl.set_massage_timer(20))
        assert c.controller_state[MASSAGE_TIMER_MINUTES] == 10
    finally:
        await c.async_shutdown()
