"""Local comfort guards run after the acquired peer writer becomes available."""

import asyncio

import pytest

from custom_components.adjustable_bed.beds.reverie.comfort import ReverieComfortRequest
from custom_components.adjustable_bed.beds.reverie.pairlink_protocol import (
    PAIRLINK_BROADCAST_ADDRESS,
    decrypt_user_frame,
    encrypt_user_frame,
)
from custom_components.adjustable_bed.beds.reverie.pairlink_runtime import (
    PairlinkRuntimeNotReadyError,
)
from custom_components.adjustable_bed.const import DOMAIN
from tests.test_reverie_pairlink_production import (
    _PEER_PATH,
    _device_for_address,
    _send_peer_write,
    _send_state_selector,
)
from tests.test_reverie_pairlink_sdk_wiring import _local_canonical, _read_available

VALUES = {
    "head_position": 35,
    "foot_position": 45,
    "lumbar_position": 55,
    "head_massage": 5,
    "foot_massage": 6,
    "timer_byte": 8,
    "mode": 2,
}


@pytest.mark.parametrize("mutation", ["feedback", "key", "sign", "stop"])
async def test_registered_local_comfort_revalidates_inside_peer_writer(
    hass, monkeypatch, enable_custom_integrations, mutation
):
    async with _local_canonical(hass, monkeypatch) as (controller, bus, socket, _entry):
        runtime = controller._runtime
        backend = runtime.peripheral_backend
        assert backend is not None
        device = _device_for_address(hass, controller._coordinator.address)
        assert device is not None
        _read_available(socket)
        captured = runtime.prepare_send()
        plan = controller.prepare_comfort(ReverieComfortRequest(**VALUES))
        blocked_payload = plan.payloads[1]
        original_send = backend.async_notify_to_peer
        entered = asyncio.Event()
        sends = 0
        held = False
        stop_task = None

        async def feedback():
            generation = runtime.prepare_send().peer_state_generation
            await _send_state_selector(bus, _PEER_PATH, runtime, 1, 20)
            for _ in range(20):
                if runtime.prepare_send().peer_state_generation != generation:
                    break
                await asyncio.sleep(0)
            assert runtime.prepare_send().peer_state_generation != generation

        async def queued_send(peer, value, **kwargs):
            nonlocal sends, held
            sends += 1
            if sends == 2:
                entered.set()
            await original_send(peer, value, **kwargs)
            if sends == 1:
                await feedback()
                await backend._lock.acquire()
                held = True

        monkeypatch.setattr(backend, "async_notify_to_peer", queued_send)
        call = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "reverie_set_comfort",
                {"device_id": [device.id], "comfort": VALUES},
                blocking=True,
            )
        )
        try:
            await asyncio.wait_for(entered.wait(), 2)
            assert len(_read_available(socket)) == 1
            assert backend._lock._waiters and any(
                not waiter.done() for waiter in backend._lock._waiters
            )
            if mutation == "feedback":
                await feedback()
            elif mutation == "key":
                runtime._peer_keys[runtime.primary_mac] = bytes.fromhex("AABBCCDD")
            elif mutation == "sign":
                event = (
                    b"\x03"
                    + PAIRLINK_BROADCAST_ADDRESS
                    + b"\x12\x30"
                    + bytes.fromhex(runtime.primary_mac.replace(":", ""))[::-1]
                    + b"\x00"
                )
                await _send_peer_write(
                    bus,
                    _PEER_PATH,
                    encrypt_user_frame(
                        event, event_key=captured.event_key, device_key=captured.device_key
                    ),
                )
                for _ in range(20):
                    if runtime.sign_gate.sign_all is False:
                        break
                    await asyncio.sleep(0)
                assert runtime.sign_gate.sign_all is False
            else:
                stop_task = asyncio.create_task(controller._coordinator.async_stop_command())
                await asyncio.sleep(0)
                assert controller._coordinator.cancel_command.is_set()
            backend._lock.release()
            held = False
            result = (await asyncio.gather(call, return_exceptions=True))[0]
            if stop_task is not None:
                await stop_task
            emitted = _read_available(socket)
            payloads = [
                decrypt_user_frame(
                    value, event_key=captured.event_key, device_key=captured.device_key
                )[10:]
                for value in emitted
            ]
            if mutation == "feedback":
                assert result is None
                assert len(payloads) == len(plan.payloads) - 1
            else:
                assert isinstance(result, BaseException)
                # Fresh STOP frames are allowed; the queued position write is not.
                assert blocked_payload not in payloads
        finally:
            if held:
                backend._lock.release()
            if not call.done():
                call.cancel()
            await asyncio.gather(call, return_exceptions=True)
            if stop_task is not None:
                await asyncio.gather(stop_task, return_exceptions=True)


async def test_local_comfort_preflight_stays_strict_before_first_send(
    hass, monkeypatch, enable_custom_integrations
):
    async with _local_canonical(hass, monkeypatch) as (controller, bus, socket, _entry):
        request = ReverieComfortRequest(**VALUES)
        plan = controller.prepare_comfort(request)
        _read_available(socket)
        await _send_state_selector(bus, _PEER_PATH, controller._runtime, 1, 20)
        await hass.async_block_till_done()
        assert not controller.comfort_plan_is_current(request, plan)
        with pytest.raises(PairlinkRuntimeNotReadyError):
            await controller.async_set_comfort(request, prepared_plan=plan)
        assert not _read_available(socket)
