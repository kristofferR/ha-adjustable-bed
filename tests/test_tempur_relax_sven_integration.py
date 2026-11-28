"""Public captured-lease release comparison for the Sven/Tempur merge."""

import asyncio

import pytest

from custom_components.adjustable_bed import const
from tests.hold_lease_wire import virtual_clock
from tests.test_carpe_diem import frames, shutdown
from tests.test_tempur_relax_full import paired_runtime, public_runtime


@pytest.mark.parametrize("combined", (False, True), ids=("standalone", "paired-parent"))
@pytest.mark.parametrize("cancelled", (False, True), ids=("normal-release", "cancellation"))
async def test_automatic_favorite_preserves_captured_release_distinction(hass, cancelled, combined):
    if combined:
        coordinator, left, right, device = await paired_runtime(hass, mode="concurrent")
        receivers = [left, right]
    else:
        coordinator, device = await public_runtime(hass, alarm=False)
        receivers = [coordinator]
    for receiver in receivers:
        await receiver.async_ensure_connected()
        receiver.controller._settings["automatic_drive"] = True
        receiver.client.write_gatt_char.reset_mock()
    entered = asyncio.Event()
    receivers[0].client.write_gatt_char.side_effect = lambda *_args, **_kwargs: entered.set()
    try:
        with virtual_clock():
            holding = asyncio.create_task(
                hass.services.async_call(
                    const.DOMAIN,
                    "hold_control",
                    {
                        "device_id": [device],
                        "control": "memory_1",
                        "duration": 0.75,
                        "hold_owner": "card-tempur",
                        "hold_generation": 1,
                    },
                    blocking=True,
                )
            )
            try:
                await asyncio.wait_for(entered.wait(), 1)
                await hass.services.async_call(
                    const.DOMAIN,
                    "stop_all",
                    {
                        "device_id": [device],
                        "hold_owner": "card-tempur",
                        "hold_generation": 1,
                        "hold_cancelled": cancelled,
                    },
                    blocking=True,
                )
                await asyncio.sleep(0)
                assert holding.done() is cancelled, [frames(receiver.client) for receiver in receivers]
                if not cancelled:
                    await asyncio.sleep(1)  # Past the original lease deadline.
                    assert not holding.done()
                    await hass.services.async_call(
                        const.DOMAIN, "stop_all",
                        {"device_id": [device], "hold_owner": "card-tempur",
                         "hold_generation": 1, "hold_cancelled": True},
                        blocking=True,
                    )
                    assert not holding.done()  # The released lease cannot cancel its continuation.
                    assert set(frames(receivers[0].client)) == {"0e00"}
                if combined:
                    assert frames(receivers[1].client) == []  # Favorites remain primary-owned.
            finally:
                await hass.services.async_call(
                    const.DOMAIN, "stop_all", {"device_id": [device]}, blocking=True
                )
                await holding
    finally:
        if combined:
            await coordinator.async_shutdown()
        else:
            await shutdown(coordinator)
