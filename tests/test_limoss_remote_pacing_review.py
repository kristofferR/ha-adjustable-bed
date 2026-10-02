"""Actual BLE starts retain the native minimum after synchronous trace work."""

from dataclasses import dataclass

import pytest

from custom_components.adjustable_bed.beds import limoss_remote
from tests.test_limoss_remote import inner_packets, make_controller


@dataclass
class Clock:
    now: float = 100.0

    def time(self) -> float:
        return self.now


@pytest.mark.parametrize("stall", [0.03, 0.12])
@pytest.mark.parametrize("trace_call", [1, 4, 6])
async def test_att_start_spacing_survives_synchronous_trace_stall(monkeypatch, stall, trace_call):
    controller = make_controller()
    clock = Clock()
    starts = []
    traces = 0

    async def sleep(seconds, event=None):
        assert seconds >= 0
        clock.now += seconds  # Controlled time; no real protocol timer waits.

    def trace(**kwargs):
        nonlocal traces
        traces += 1
        if traces == trace_call:
            clock.now += stall

    def write(*args, **kwargs):
        starts.append(clock.time())

    monkeypatch.setattr(limoss_remote.asyncio, "get_running_loop", lambda: clock)
    controller._sleep = sleep
    controller._coordinator.record_command_trace.side_effect = trace
    controller.client.write_gatt_char.side_effect = write
    await controller.write_command(bytes.fromhex("1200000000"), repeat_count=3, repeat_delay_ms=0)
    await controller.stop_all()

    assert [packet[1:6].hex() for packet in inner_packets(controller)] == [
        "1200000000", "1200000000", "1200000000",
        "ff00000000", "ff00000000", "ff00000000", "ff00000000", "ff00000000",
    ]
    assert [packet[6] for packet in inner_packets(controller)] == list(range(8))
    assert len(starts) == traces == 8
    assert all(b - a >= 0.08 - 1e-10 for a, b in zip(starts, starts[1:], strict=False))
