"""Accepted row126 catalog vectors, target ownership and public surface."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.casper_base.protocol import Request
from custom_components.adjustable_bed.beds.hush_base.catalog import ACTIONS, INDICES, PRODUCTS
from custom_components.adjustable_bed.beds.hush_base.controller import HushBaseController
from custom_components.adjustable_bed.beds.hush_sleep.controller import (
    HushRemoteController,
    HushSleepController,
)
from custom_components.adjustable_bed.codec.richmat import function
from custom_components.adjustable_bed.pairing import supports_single_address_pairing
from custom_components.adjustable_bed.profiles.hush import HUSH_BASE_VARIANTS
from custom_components.adjustable_bed.validators import get_variants_for_bed_type
from tests.test_casper_base import frames, make

FIXTURE = json.loads((Path(__file__).parent / "fixtures/hush_catalog.json").read_text())


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    real = asyncio.sleep

    async def tick(_):
        await real(0)

    monkeypatch.setattr(asyncio, "sleep", tick)


def hush(model="hushl400", *, transport=1, kind=None):
    _, c = make(transport=transport, kind=kind)
    controller = HushSleepController(c, kind=kind) if kind else HushBaseController(c, product=model)
    c.controller = controller
    return controller, c


@pytest.mark.parametrize("product", FIXTURE["products"][1:], ids=lambda p: p["name"])
async def test_all_exact_ordered_memberships_and_capabilities(product):
    key = product["name"].removeprefix("product").lower()
    controller, c = hush(key)
    actual = PRODUCTS[key]
    assert INDICES[key] == product["index"]
    assert list(actual[6:]) == product["flags"]
    for group, descriptors in zip(actual[1:6], product["groups"], strict=True):
        assert [list(ACTIONS[i]) for i in group] == [FIXTURE["descriptors"][d] for d in descriptors]
    assert {s.translation_key for s in controller.controller_button_specs} == {"hush_base_action"}
    assert supports_single_address_pairing("hush_base", key) == product["flags"][-1]
    assert not controller.supports_single_address_pairing
    assert all("None" not in s.key for s in controller.controller_button_specs)
    assert not frames(c)


@pytest.mark.parametrize("transport", range(6))
@pytest.mark.parametrize("side", [None, "left", "right", "both"])
async def test_transport_side_stop_and_initialization(transport, side):
    controller, c = hush("hushs575sh", transport=transport)
    await controller.start_notify()
    assert frames(c)[:4] == (
        ["00", "01", "01", "01"]
        if transport == 0
        else ["6e02010071", "6e08010178", "6e0a000179", "6e15010185"]
    )
    c.client.write_gatt_char.reset_mock()
    # command_side is bound by the coordinator's context manager in real use.
    token = controller._command_side.set(side)
    try:
        if side is not None and transport == 0:
            with pytest.raises(ValueError):
                await controller.stop_all()
            return
        c.cancel_command.set()
        await controller.move_back_up()
    finally:
        controller._command_side.reset(token)
    expected_sides = (0, 1) if side == "both" else (1,) if side == "right" else (0,)
    assert frames(c) == [function(0x6E, s, single=transport == 0).hex() for s in expected_sides]


async def test_profile_is_explicit_and_light_policy_is_hush_specific():
    assert set(get_variants_for_bed_type("hush_base")) == set(PRODUCTS)
    assert "restored" not in HUSH_BASE_VARIANTS["hushs175sh"]
    assert "restored" in HUSH_BASE_VARIANTS["casperpro"]
    with pytest.raises(ValueError):
        HushBaseController(MagicMock(), product="auto")
    rgb, c = hush("hushl400")
    rgb.events["light_available"] = {}
    await rgb.start_notify()
    c.client.write_gatt_char.reset_mock()
    await rgb.async_execute_casper_base_request(Request("rgb_power", enabled=True))
    assert frames(c) == ["6e20090404010001a1"]
    with pytest.raises(ValueError):
        rgb.validate_casper_base_request(Request("light_rgb"))
    plain, _ = hush("hushl200")
    plain.events["light_available"] = {}
    plain.validate_casper_base_request(Request("light_rgb"))
    with pytest.raises(ValueError):
        plain.validate_casper_base_request(Request("rgb_power"))


async def test_alarm_order_fan_release_and_saved_light():
    controller, c = hush()
    await controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    controller.events["clock_available"] = {}
    await controller.async_execute_casper_base_request(Request("alarm_cancel"))
    assert frames(c) == ["6e05000073", "6e06000074"]
    fan, c = hush("niscobaseplus")
    await fan.start_notify()
    c.client.write_gatt_char.reset_mock()
    await fan.async_perform_casper_base_action("FanWaveMode")
    assert frames(c) == ["6e0100a514", "6e01006edd"]
    controller.restore_persisted_app_state({"light_seconds": 720, "light_color": [1, 2, 3]})
    assert controller.persisted_app_state == {"light_seconds": 720, "light_color": [1, 2, 3]}
    with pytest.raises(ValueError):
        controller.restore_persisted_app_state({"light_seconds": True})


async def test_disconnect_during_tick_does_not_write_new_target(monkeypatch):
    controller, c = hush()
    await controller.start_notify()
    old = c.client
    assert isinstance(controller, HushBaseController)

    async def replace(_):
        controller.on_disconnect()
        c.client = MagicMock(is_connected=True)
        c.client.write_gatt_char = AsyncMock()

    monkeypatch.setattr(asyncio, "sleep", replace)
    old.write_gatt_char.reset_mock()
    with pytest.raises(ConnectionError):
        await controller._send(b"\x24")
    old.write_gatt_char.assert_not_awaited()
    c.client.write_gatt_char.assert_not_awaited()


async def test_remote_is_connect_only():
    _, c = hush()
    remote = HushRemoteController(c)
    await remote.start_notify()
    await remote.async_execute_casper_base_request(Request("remote_find"))
    c.client.write_gatt_char.assert_not_awaited()
    assert remote.supports_hush_base_controls


async def test_dedicated_music_descriptors_and_phone_only_exclusion():
    controller, c = hush("nisconup355b")
    await controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    controller.events["music_available"] = {}
    assert (
        len(
            [
                s
                for s in controller.controller_button_specs
                if s.key.startswith("casper_music_page_")
            ]
        )
        == 8
    )
    await controller.async_perform_casper_base_action("MusicSwitchSoundTrack", music_page=True)
    assert frames(c) == ["6e0100d847", "6e0100c433"]
    for key in PRODUCTS:
        other, _ = hush(key)
        assert "PhoneLight" not in other.actions
