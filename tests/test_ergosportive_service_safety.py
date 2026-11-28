"""Timed native movement and cleanup retain their original physical session."""

import asyncio

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.keeson import ergosportive as bed
from custom_components.adjustable_bed.codec import sleep_assistant as codec
from tests.hold_lease_wire import virtual_clock
from tests.test_ergosportive import connected, native


@pytest.mark.parametrize("variant", ["remote", "hardware221"])
async def test_native_timed_move_does_not_send_after_elapsed_duration(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, variant
):
    entry, coordinator = await native(hass, mock_bleak_client, variant)
    entities = [
        e for e in er.async_get(hass).entities.values() if e.config_entry_id == entry.entry_id
    ]
    writes = []

    async def slow_write(char, frame, **kwargs):
        writes.append((round(asyncio.get_running_loop().time() * 1000), bytes(frame)))
        if frame == codec.instruction(1):
            await asyncio.sleep(0.3)

    mock_bleak_client.write_gatt_char.side_effect = slow_write
    with virtual_clock():
        start = round(asyncio.get_running_loop().time() * 1000)
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {
                "device_id": entities[0].device_id,
                "motor": "back",
                "direction": "up",
                "duration_ms": 200,
            },
            blocking=True,
        )
    relative = [(t - start, f.hex()) for t, f in writes]
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert all(t - start < 200 for t, f in writes if f == codec.instruction(1)), relative


@pytest.mark.parametrize("variant", ["remote", "hardware221"])
@pytest.mark.parametrize("phase", ["movement", "release"])
async def test_revision_mid_command_still_releases_the_original_live_link(
    hass, mock_bleak_client, variant, phase
):
    coordinator, controller = await connected(hass, mock_bleak_client, variant)
    coordinator.entry.add_to_hass(hass)

    async def revise(char, frame, **kwargs):
        if frame == codec.instruction(1 if phase == "movement" else 0):
            hass.config_entries.async_update_entry(
                coordinator.entry,
                data={**coordinator.entry.data, "ergosportive_controls": ["feet"]},
            )

    mock_bleak_client.write_gatt_char.side_effect = revise
    with virtual_clock():
        try:
            await controller.hold_control("head_up", 100)
        except ConnectionError:
            pass
    frames = [c.args[1] for c in mock_bleak_client.write_gatt_char.await_args_list]
    assert codec.instruction(0) in frames
    if variant == "hardware221":
        assert codec.ergosportive_secondary_release() in frames


async def test_disconnect_during_brightness_does_not_restore_connection_scoped_state(
    hass, mock_bleak_client
):
    coordinator, controller = await connected(hass, mock_bleak_client)

    async def disconnect(char, frame, **kwargs):
        if frame == codec.light(13, False):
            controller.on_disconnect()
            mock_bleak_client.is_connected = False

    mock_bleak_client.write_gatt_char.side_effect = disconnect
    with virtual_clock():
        await controller.set_brightness(13)
    assert coordinator.controller_state[bed.BRIGHTNESS] is None
