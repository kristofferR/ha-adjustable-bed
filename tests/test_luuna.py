"""Accepted unit146 literals, profile gates and safe BLE lifecycle behavior."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.casper_base.protocol import (
    MainReceive,
    Request,
    alarm_countdown,
)
from custom_components.adjustable_bed.beds.luuna.controller import LuunaController, brightness_rgb
from custom_components.adjustable_bed.beds.luuna.protocol import decode
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.casper import light_duration
from custom_components.adjustable_bed.profiles.luuna import PROFILES
from custom_components.adjustable_bed.setup_questions import _luuna_settings
from tests.test_casper_base import char, frames
from tests.test_casper_base import make as make_casper

FIXTURES = Path(__file__).parent / "fixtures" / "luuna"
ORIGINAL = json.loads((FIXTURES / "vectors.json").read_text())
CONTINUATION = json.loads((FIXTURES / "continuation-vectors.json").read_text())


def make(product="rise", transport=1):
    _, coordinator = make_casper(transport=transport)
    controller = LuunaController(coordinator, product=product)
    coordinator.controller = controller
    return controller, coordinator


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    real = asyncio.sleep

    async def short(delay):
        await real(0)

    monkeypatch.setattr(asyncio, "sleep", short)


@pytest.mark.parametrize("vector", ORIGINAL, ids=lambda v: v["id"])
def test_literal_commands(vector):
    value = vector["inputs"]
    assert (
        codec.function(value["opcode"], single=not value["framed"]).hex()
        == vector["expected_bytes"]
    )


@pytest.mark.parametrize(
    "vector",
    [v for v in CONTINUATION if v["kind"] == "builder" and v["builder"] != "sleep_envelope"],
    ids=lambda v: v["id"],
)
def test_literal_builders(vector):
    x, kind = vector["inputs"], vector["builder"]
    if kind == "special":
        action = "deviceFunctionItem" + vector["id"].split("-")[0]
        result = codec.function(x["opcode"], single=x["raw"], action=action)
    elif kind == "alarm":
        result = b"".join(codec.countdown(x["minutes"], x["opcode"]))
    elif kind == "alarm_countdown":
        target, now = datetime.fromisoformat(x["target"]), datetime.fromisoformat(x["now"])
        result = b"".join(
            codec.countdown(alarm_countdown(target.hour, target.minute, now), x["opcode"])
        )
    elif kind == "light_seconds":
        result = codec.light_timer(*light_duration(x["seconds"]))
    elif kind in ("color", "brightness"):
        rgb = tuple(x["rgb"])
        result = codec.rgb(*(brightness_rgb(rgb, x["brightness"]) if kind == "brightness" else rgb))
    elif kind == "clock_sync":
        result = codec.calendar(datetime(**x), build=codec.record_20_len)
    else:
        assert kind == "sleep_name"
        result = codec.record_20_len(6, 3, 0, (0,))
    assert result.hex() == vector["expected_bytes"]


@pytest.mark.parametrize(
    "vector", [v for v in CONTINUATION if v["kind"] == "parser"], ids=lambda v: v["id"]
)
def test_notification_fields(vector):
    data = bytes.fromhex(vector["expected_bytes"])
    # Frozen synthetic parser vectors entered after checksum admission. Re-sum
    # those placeholders for HA's integrated decoder; keep the input fields.
    if data[1] == 0x20 and data[-1] == 0:
        data = codec.frame(*data[:-1])
    event = decode(data)
    expected = vector["expected_event"]
    if expected is None:
        assert event is None
    else:
        assert event is not None
        assert event.name == expected["name"]
        values = expected["values"]
        # Check packets retain the checksum-admitted bytes.
        if event.name == "check":
            values = {**values, "raw": data.hex()}
        assert event.values == values


@pytest.mark.parametrize("product", PROFILES)
def test_product_catalog_and_setup(product):
    ctrl, _ = make(product)
    row = next(
        p for p in json.loads((FIXTURES / "products.json").read_text()) if p["key"] == product
    )
    controls = {
        c["name"].removeprefix("deviceFunctionItem"): c["opcode"]
        for section in row["sections"].values()
        for c in section
    }
    assert {key: value[0] for key, value in ctrl.actions.items()} == controls
    assert ctrl.memory_slot_count == (2 if product == "risepro" else 1)
    assert len(ctrl.motor_control_specs) == (2 if product == "rise" else 4)
    assert not ctrl.supports_single_address_pairing
    assert ctrl.execution.hold == "stream" and not ctrl.execution.concurrent
    assert not ctrl.supports_casper_base_controls
    assert per_side_profile("luuna", product) is not None
    settings = _luuna_settings({"protocol_variant": product})
    assert settings["motor_count"] == (2 if product == "rise" else 4)
    assert settings["has_massage"] == (product != "rise")


@pytest.mark.parametrize(
    "gatt", json.loads((FIXTURES / "gatt.json").read_text()), ids=lambda v: v["name"]
)
async def test_gatt_and_startup(gatt):
    from types import SimpleNamespace

    ctrl, c = make()
    c.client.services = [
        SimpleNamespace(
            uuid=gatt["service"].lower(),
            characteristics=[
                char(gatt["write"].lower(), "write", "write-without-response"),
                char("1234", "notify"),
            ],
        )
    ]
    await ctrl.start_notify()
    sent = frames(c)
    single = gatt["name"] == "bleServiceUUIDNordic"
    assert sent[0] == ("00" if single else "6e02010071")
    assert sent[1].startswith("6e200d080301")
    assert sent[2] == "6e2008060300009f"
    assert sent[3:] == (["01", "01"] if single else ["6e08010178", "6e0a000179"])
    assert all(call.kwargs["response"] is False for call in c.client.write_gatt_char.call_args_list)


async def test_no_notifications_rejects_startup_before_writes():
    ctrl, c = make()
    c.client.services[0].characteristics.pop()
    with pytest.raises(ValueError, match="notification"):
        await ctrl.start_notify()
    assert not frames(c)


async def test_movement_release_and_massage_never_invent_stop():
    ctrl, c = make("risepro")
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    await ctrl.move_back_up()
    assert frames(c) == ["6e01002493"] * c.motor_pulse_count
    c.client.write_gatt_char.reset_mock()
    await ctrl.async_perform_casper_base_action("MassageHeadInstensityStrengthen")
    await ctrl.stop_all()
    assert frames(c) == ["6e01004cbb"]
    c.cancel_command.set()
    await ctrl.move_back_up()
    assert frames(c) == ["6e01004cbb"]


async def test_capability_gates_alarm_order_light_and_forbidden_operations():
    ctrl, c = make("riseprolight")
    await ctrl.start_notify()
    alarm = Request("alarm", mode="ZeroGravity", hour=10, minute=30)
    for request in (alarm, Request("light_rgb")):
        with pytest.raises(ValueError, match="page unavailable"):
            ctrl.validate_casper_base_request(request)
    for raw in ("6e09010078", "6e0e00037f"):
        ctrl._on_notification(MagicMock(), bytearray.fromhex(raw))
    c.client.write_gatt_char.reset_mock()
    await ctrl.async_execute_casper_base_request(replace(alarm, operation="alarm_cancel"))
    assert frames(c) == ["6e05000073", "6e06000074"]
    c.client.write_gatt_char.reset_mock()
    await ctrl.async_execute_casper_base_request(Request("light_warm", value=50))
    assert frames(c) == ["6e0cff80f96e0d460acb"]
    for op in ("repeat_alarm", "snore_detector", "rgb_power", "sensor_live"):
        with pytest.raises(ValueError, match="Unsupported"):
            ctrl.validate_casper_base_request(Request(op))
    other, _ = make("risepro")
    other._consume(decode(bytes.fromhex("6e0e00037f")))
    assert "light_available" not in other.events


async def test_disconnect_cancels_pending_write_and_stale_notification():
    ctrl, c = make()
    await ctrl.start_notify()
    callback = c.client.start_notify.call_args.args[1]
    c.client.write_gatt_char.reset_mock()
    with pytest.MonkeyPatch.context() as patch:

        async def disconnect(_delay):
            ctrl.on_disconnect()

        patch.setattr(asyncio, "sleep", disconnect)
        with pytest.raises(ConnectionError):
            await ctrl.move_back_up()
    callback(MagicMock(), bytearray.fromhex("6e09010078"))
    assert not ctrl.events
    assert not frames(c)


async def test_lease_outlives_finite_count_and_cancellation_ends_refresh():
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
        HoldLease,
    )

    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    c.motor_pulse_count = 2

    async def cancel_after_six(*_args, **_kwargs):
        if c.client.write_gatt_char.await_count == 6:
            c.cancel_command.set()

    c.client.write_gatt_char.side_effect = cancel_after_six
    token = _CURRENT_COMMAND_CONTEXT.set(
        CommandContext(
            scheduler_token=object(),
            cancel_event=c.cancel_command,
            admitted_stop_epoch=0,
            intent_id="luuna-lease",
            kind=CommandKind.HOLD,
            group_id=None,
            resources=frozenset({"motor:back"}),
            lease=HoldLease(owner="card", generation=1, action="up", duration_s=1),
        )
    )
    try:
        await ctrl.move_back_up()
        await ctrl.stop_all()
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
    assert frames(c) == ["6e01002493"] * 6


def live_runtime(hass, product="riseprolight", address="AA:BB:CC:DD:EE:FF"):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    _, mocked = make(product)
    entry = MockConfigEntry(
        domain="adjustable_bed",
        title="Luuna",
        unique_id=address,
        version=5,
        data={
            "address": address,
            "name": "Luuna",
            "bed_type": "luuna",
            "protocol_variant": product,
            "disable_angle_sensing": True,
            "motor_pulse_count": 1,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = mocked.client
    controller = LuunaController(coordinator, product=product)
    coordinator._controller = controller
    hass.data.setdefault("adjustable_bed", {})[entry.entry_id] = coordinator
    return coordinator, controller


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("light_warm", "6e0cff80f96e0d460acb"),
        ("alarm_cancel", "6e06000074"),
    ],
)
async def test_service_reconnects_idle_controller_and_requires_fresh_reply(
    hass, operation, expected
):
    from unittest.mock import AsyncMock, patch

    from custom_components.adjustable_bed.beds.casper_base.services import (
        async_register_casper_base_services,
    )

    async_register_casper_base_services(hass)
    coordinator, ctrl = live_runtime(hass)
    await ctrl.start_notify()
    ctrl._consume(decode(bytes.fromhex("6e09010078")))
    ctrl._consume(decode(bytes.fromhex("6e0e00037f")))
    coordinator.cache_capability_controller()
    ctrl.on_disconnect()
    coordinator.client.is_connected = False
    assert not ctrl.events
    coordinator.client.write_gatt_char.reset_mock()
    reconnects = []

    async def reply(_char, data, **_kwargs):
        received = {"6e08010178": "6e09010078", "6e0a000179": "6e0e00037f"}.get(bytes(data).hex())
        if received:
            hass.loop.call_soon(ctrl._on_notification, MagicMock(), bytearray.fromhex(received))

    coordinator.client.write_gatt_char.side_effect = reply

    async def connect(**_kwargs):
        if not coordinator.client.is_connected:
            reconnects.append(True)
            coordinator.client.is_connected = True
            await ctrl.start_notify()
        return True

    with (
        patch.object(coordinator, "async_ensure_connected", AsyncMock(side_effect=connect)),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ),
    ):
        await hass.services.async_call(
            "adjustable_bed",
            "luuna",
            {"device_id": "a", "operation": operation, "value": 50},
            blocking=True,
        )
    assert reconnects == [True]
    assert frames(coordinator)[-1] == expected
    assert "clock_available" in ctrl.events and "light_available" in ctrl.events
    coordinator._cancel_disconnect_timer()


async def test_service_does_not_reuse_previous_connection_capability(hass, monkeypatch):
    from unittest.mock import AsyncMock, patch

    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.beds.casper_base.services import (
        async_register_casper_base_services,
    )

    async_register_casper_base_services(hass)
    coordinator, ctrl = live_runtime(hass)
    await ctrl.start_notify()
    ctrl._consume(decode(bytes.fromhex("6e0e00037f")))
    coordinator.cache_capability_controller()
    ctrl.on_disconnect()
    coordinator.client.is_connected = False
    coordinator.client.write_gatt_char.reset_mock()
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.luuna.controller.CAPABILITY_WAIT_S", 0
    )

    async def connect(**_kwargs):
        coordinator.client.is_connected = True
        await ctrl.start_notify()
        return True

    with (
        patch.object(coordinator, "async_ensure_connected", AsyncMock(side_effect=connect)),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ),
        pytest.raises(ServiceValidationError, match="has not reported"),
    ):
        await hass.services.async_call(
            "adjustable_bed",
            "luuna",
            {"device_id": "a", "operation": "light_warm", "value": 50},
            blocking=True,
        )
    assert "6e0cff80f96e0d460acb" not in frames(coordinator)
    assert "light_available" not in ctrl.events
    coordinator._cancel_disconnect_timer()


async def test_luuna_service_preflight_blocks_all_targets_and_has_finite_operations(hass):
    from unittest.mock import patch

    import voluptuous as vol
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.beds.casper_base.services import (
        async_register_casper_base_services,
    )

    async_register_casper_base_services(hass)
    a, ac = live_runtime(hass)
    b, bc = live_runtime(hass, "rise", "11:22:33:44:55:66")
    await ac.start_notify()
    await bc.start_notify()
    ac._consume(decode(bytes.fromhex("6e0e00037f")))
    a.client.write_gatt_char.reset_mock()
    b.client.write_gatt_char.reset_mock()
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(a, "both"), (b, "both")], []),
        ),
        pytest.raises(ServiceValidationError, match="light page unavailable"),
    ):
        await hass.services.async_call(
            "adjustable_bed",
            "luuna",
            {"device_id": ["a", "b"], "operation": "light_rgb"},
            blocking=True,
        )
    assert not frames(a) and not frames(b)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            "adjustable_bed", "luuna", {"device_id": "a", "operation": "sensor_live"}, blocking=True
        )
    a._cancel_disconnect_timer()
    b._cancel_disconnect_timer()


@pytest.mark.parametrize("name", ["QRRM1234", "COOL1234", "MPE_1234", "209A1234", "BED-1234"])
def test_name_only_discovery_offers_richmat_family_without_inferring_product(name):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    result = detect_bed_type_detailed(_make_service_info(name=name))
    assert "richmat" in {result.bed_type, *(result.ambiguous_types or ())}
    assert "luuna" not in {result.bed_type, *(result.ambiguous_types or ())}
    assert "name:richmat_app_candidate" in result.signals


def test_safe_receive_preserves_fragments_and_rejects_bad_lengths_and_checksum():
    rx = MainReceive()
    assert rx.feed(bytes.fromhex("6e0901")) == []
    assert rx.feed(bytes.fromhex("0078")) == [bytes.fromhex("6e09010078")]
    assert rx.feed(bytes.fromhex("6e200c0603")) == []
    assert rx.feed(bytes.fromhex("0300524d2d41b3")) == [bytes.fromhex("6e200c06030300524d2d41b3")]
    assert rx.feed(bytes.fromhex("6e200c06030300524d2d4100")) == []
    with pytest.raises(ValueError):
        rx.feed(bytes.fromhex("6e2000"))
