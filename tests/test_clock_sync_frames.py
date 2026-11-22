"""The shared Set bed clock action sends exactly what each bed's own clock operation did.

These beds set their clock through a bed-specific action or button before v5 moved
clock setting to ``sync_clock``. Each expected row was captured from that old
operation on the wire snapshot's harness at its frozen time: ``[ms, characteristic,
with response, frame, repeats, interval ms]``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import patch

import pytest

from tests.clock_frames import capture

CASES = [
    pytest.param(
        'suta',
        {},
        [
            [100, '0000fff2-0000-1000-8000-00805f9b34fb', True, '41542b53443d323630313032303330340d0a', 3, 107],
        ],
        id='suta',
    ),
    pytest.param(
        'suta:SUTA-B201*',
        {},
        [
            [100, '0000fff2-0000-1000-8000-00805f9b34fb', True, '41542b53443d323630313032303330340d0a', 3, 107],
        ],
        id='suta:SUTA-B201*',
    ),
    pytest.param(
        'sonicsleep',
        {},
        [
            [100, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e0c20080201695735a5003f', 1, 0],
            [207, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e0d20080301380102030405ee', 1, 0],
        ],
        id='sonicsleep',
    ),
    pytest.param(
        'mlily_remote:ms600:n1',
        {},
        [
            [93, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '6e200d080301380102030405ee', 1, 0],
        ],
        id='mlily_remote:ms600:n1',
    ),
    pytest.param(
        'mlily_remote:ms200:w1',
        {},
        [
            [93, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e200d080301380102030405ee', 1, 0],
        ],
        id='mlily_remote:ms200:w1',
    ),
    pytest.param(
        'bobpowerbase:elite:n1',
        {},
        [
            [93, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '6e200d080301380102030405ee', 1, 0],
        ],
        id='bobpowerbase:elite:n1',
    ),
    pytest.param(
        'hjbed',
        {},
        [
            [93, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e0c20080201695735a5003f', 1, 0],
            [193, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e0d20080301380102030405ee', 1, 0],
        ],
        id='hjbed',
    ),
    pytest.param(
        'richmat_app',
        {},
        [
            [93, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e200c080201695735a5003f', 1, 0],
            [193, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e200d080301380102030405ee', 1, 0],
        ],
        id='richmat_app',
    ),
    pytest.param(
        'richmat_app_sleep',
        {},
        [
            [100, '00000002-3c17-d293-8e48-14fe2e4da212', True, '000301003e0000110343554437007b226964223a332c22636d64223a22735f74696d65222c2276616c223a7b227473223a313736373332333034352c22757463223a307d7d', 1, 0],
        ],
        id='richmat_app_sleep',
    ),
    pytest.param(
        'goodvibe:selector-0004',
        {},
        [
            [0, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e200c080201695735a5003f', 1, 0],
            [7, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e200d080301380102030405ee', 1, 0],
        ],
        id='goodvibe:selector-0004',
    ),
    pytest.param(
        'goodvibe:sleep_rm:goodvibe_sleep',
        {},
        [
            [0, '00000002-3c17-d293-8e48-14fe2e4da212', False, '0002010041000011034355443a007b226964223a322c22636d64223a22735f74696d65222c2276616c223a7b227473223a313736373332333034352c22747a223a22555443227d7d', 1, 0],
        ],
        id='goodvibe:sleep_rm:goodvibe_sleep',
    ),
    pytest.param(
        'galaxy:D1RM',
        {},
        [
            [100, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e0c20080201695735a5003f', 1, 0],
            [207, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e0d20080301380102030405ee', 1, 0],
        ],
        id='galaxy:D1RM',
    ),
    pytest.param(
        'mlily:brrm:mlily',
        {},
        [
            [93, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e200c080201695735a5003f', 1, 0],
            [193, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e200d080301380102030405ee', 1, 0],
        ],
        id='mlily:brrm:mlily',
    ),
    pytest.param(
        'majestichome',
        {},
        [
            [93, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e0c20080201695735a5003f', 1, 0],
            [193, 'd44bc439-abfd-45a2-b575-925416129600', False, '6e0d20080301380102030405ee', 1, 0],
        ],
        id='majestichome',
    ),
    pytest.param(
        'majestichome:FARM:n1',
        {},
        [
            [93, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '6e0c20080201695735a5003f', 1, 0],
            [193, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '6e0d20080301380102030405ee', 1, 0],
        ],
        id='majestichome:FARM:n1',
    ),
    pytest.param(
        'okimiki:IQRM:nordic',
        {},
        [
            [93, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '6e0c20080201695735a5003f', 1, 0],
            [193, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '6e0d20080301380102030405ee', 1, 0],
        ],
        id='okimiki:IQRM:nordic',
    ),
    pytest.param(
        'okimiki:KWRN:nordic',
        {},
        [
            [93, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '6e0c20080201695735a5003f', 1, 0],
            [193, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '6e0d20080301380102030405ee', 1, 0],
        ],
        id='okimiki:KWRN:nordic',
    ),
    pytest.param(
        'motion_bed',
        {},
        [
            [0, '0000ffe1-0000-1000-8000-00805f9b34fb', True, 'ffffffff01000111030409052601024d04', 1, 0],
        ],
        id='motion_bed',
    ),
    pytest.param(
        'motion_bed',
        {'ble_device_name': 'TL-B'},
        [
            [0, '0000ffe1-0000-1000-8000-00805f9b34fb', True, 'ffffffff01000111030405052601024904', 1, 0],
        ],
        id='motion_bed/TL-B',
    ),
    pytest.param(
        'motion_bed',
        {'ble_device_name': 'TL-W'},
        [
            [0, '0000ffe1-0000-1000-8000-00805f9b34fb', True, 'fffffffffe14000700002601020304050500aedf', 1, 0],
        ],
        id='motion_bed/TL-W',
    ),
    pytest.param(
        'gmmotor',
        {'product_type': 'A0RN'},
        [
            [93, '00000002-3c17-d293-8e48-14fe2e4da212', False, '6e0c20080201695735a5003f', 1, 0],
            [193, '00000002-3c17-d293-8e48-14fe2e4da212', False, '6e0d20080301380102030405ee', 1, 0],
        ],
        id='gmmotor/A0RN',
    ),
    pytest.param(
        'gmmotor',
        {'product_type': 'HNRN'},
        [
            [93, '00000002-3c17-d293-8e48-14fe2e4da212', False, '6e0c20080201695735a5003f', 1, 0],
            [193, '00000002-3c17-d293-8e48-14fe2e4da212', False, '6e0d20080301380102030405ee', 1, 0],
        ],
        id='gmmotor/HNRN',
    ),
    pytest.param(
        'doublesleep:p1',
        {},
        [
            [0, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '07047e000204030405', 1, 0],
        ],
        id='doublesleep:p1',
    ),
    pytest.param(
        'doublesleep:p2',
        {},
        [
            [0, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, 'aa00000301081a01020503040500', 1, 0],
        ],
        id='doublesleep:p2',
    ),
    pytest.param(
        'doublesleep:p3',
        {},
        [
            [0, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', True, '020e01003f0000110359445938007b226964223a31332c22636d64223a22735f74696d65222c2276616c223a7b227473223a313736373332333034362c22757463223a307d7d', 1, 0],
        ],
        id='doublesleep:p3',
    ),
    # The bed's own clock button, captured before it was removed (v5 round 3).
    pytest.param(
        'yamada',
        {},
        [
            [0, '0000ffe9-0000-1000-8000-00805f9b34fb', True, 'e780017e00020304050b', 1, 0],
        ],
        id='yamada',
    ),
    pytest.param(
        'symphony_sleep',
        {},
        [
            [0, '0000ffe9-0000-1000-8000-00805f9b34fb', True, 'e780017e00020304050b', 1, 0],
        ],
        id='symphony_sleep',
    ),
    pytest.param(
        'simmons',
        {},
        [
            [0, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '07047e000203040505', 1, 0],
        ],
        id='simmons',
    ),
    pytest.param(
        'resident',
        {},
        [
            [0, '62741525-52f9-8864-b1ab-3b3a8d65950b', True, 'e780017e0002030405', 1, 0],
            [100, '62741525-52f9-8864-b1ab-3b3a8d65950b', True, '0802e18001', 1, 0],
        ],
        id='resident',
    ),
    pytest.param(
        'ultramatic_smart_bed',
        {},
        [
            [0, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '070426010205030405', 2, 500],
        ],
        id='ultramatic_smart_bed',
    ),
    pytest.param(
        'doublesleep',
        {},
        [
            [0, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '07047e000204030405', 1, 0],
        ],
        id='doublesleep',
    ),
    pytest.param(
        'simmons:simmons_okin',
        {},
        [
            [0, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', True, 'e780017e00020304050b', 1, 0],
        ],
        id='simmons:simmons_okin',
    ),
    pytest.param(
        'symphony_sleep:400E:box2',
        {},
        [
            [0, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', True, '070426010205030405', 1, 0],
        ],
        id='symphony_sleep:400E:box2',
    ),
    pytest.param(
        'yamada:p2',
        {},
        [
            [0, '0000ffe9-0000-1000-8000-00805f9b34fb', True, '07047e000205030405', 1, 0],
        ],
        id='yamada:p2',
    ),
    pytest.param(
        'eshine_okin:eshine_e2000',
        {},
        [
            [100, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '07041a010205030405', 1, 0],
            [307, '6e400002-b5a3-f393-e0a9-e50e24dcca9e', False, '00c0', 1, 0],
        ],
        id='eshine_okin:eshine_e2000',
    ),
    pytest.param(
        'suta:SUTA-MOON*',
        {},
        [
            [100, '0000ffe1-0000-1000-8000-00805f9b34fb', True, '41542b53443d323630313032303330340d0a', 3, 107],
        ],
        id='suta:SUTA-MOON*',
    ),
]


@pytest.mark.parametrize(("scenario", "entry_data", "expected"), CASES)
async def test_sync_clock_sends_the_frames_of_the_old_clock_operation(
    scenario: str, entry_data: dict[str, Any], expected: list[list[Any]]
) -> None:
    async def sync(controller: Any) -> None:
        assert controller.supports_clock_sync
        controller.validate_clock_sync()
        await controller.sync_clock()

    assert await capture(scenario, sync, entry_data=entry_data) == expected


async def test_okimiki_without_an_alarm_has_no_clock() -> None:
    async def check(controller: Any) -> None:
        assert not controller.supports_clock_sync

    assert await capture("okimiki:IPRM:nordic", check) == []


@pytest.mark.parametrize(
    ("protocol", "characteristic", "expected"),
    [
        ("p1", "0000ffe9-0000-1000-8000-00805f9b34fb", "e2fe162d1e0c02b0"),
        ("p2", "0000ffe9-0000-1000-8000-00805f9b34fb", "e780017e060e0c1e2dae"),
        ("p3", "6e400002-b5a3-f393-e0a9-e50e24dcca9e", "07041a070e020c1e2d"),
    ],
)
async def test_betterliving2_shared_clock_uses_accepted_app_literal(
    protocol, characteristic, expected
):
    """P1-time/P2-time/P3-time in the frozen BetterLiving2 vectors, at their own time."""

    async def sync(controller):
        assert controller.supports_clock_sync
        controller.validate_clock_sync()
        with patch(
            "custom_components.adjustable_bed.beds.keeson.betterliving2.dt_util.now",
            return_value=datetime(2026, 7, 14, 12, 30, 45),
        ):
            await controller.sync_clock()

    assert await capture(f"betterliving2:{protocol}:2", sync) == [
        [0, characteristic, True, expected, 1, 0]
    ]
