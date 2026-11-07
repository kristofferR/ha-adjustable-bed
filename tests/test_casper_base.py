"""Row101 product, transport, cleanup and live sensor integration contracts."""

from __future__ import annotations

import asyncio
import gzip
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.beds.casper_base.catalog import ACTIONS, PRODUCTS
from custom_components.adjustable_bed.beds.casper_base.controller import CasperBaseController
from custom_components.adjustable_bed.beds.casper_base.protocol import Event, Request
from custom_components.adjustable_bed.beds.casper_sleep.controller import CasperSleepController
from custom_components.adjustable_bed.beds.casper_sleep.protocol import (
    NOTIFY,
    SERVICES,
    WRITE,
    envelope,
)
from custom_components.adjustable_bed.codec.richmat import TRANSPORTS
from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
from custom_components.adjustable_bed.profiles.casper import TRANSPORTS as PROFILE_TRANSPORTS
from custom_components.adjustable_bed.validators import get_variants_for_bed_type
from tests.state_helpers import state_writer


def char(uuid, *properties):
    return SimpleNamespace(uuid=uuid, handle=1, properties=list(properties))


def make(model="casperpro", *, transport=1, kind=None):
    c = MagicMock()
    c._protocol_variant = model
    c.cancel_command = asyncio.Event()
    c.motor_pulse_count = 3
    c.controller_state = {}
    c.handle_controller_state_update.side_effect = lambda k, v: c.controller_state.update({k: v})
    c.handle_controller_state_updates.side_effect = state_writer(c.controller_state)
    c.client = MagicMock(is_connected=True, mtu_size=23)
    c.client.write_gatt_char = AsyncMock()
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    gatt = TRANSPORTS[PROFILE_TRANSPORTS[transport]]
    service, write = gatt.service_uuid, gatt.write_uuid
    chars = [char(write, "write", "write-without-response"), char("1234", "notify")]
    if kind:
        service = SERVICES[0]
        chars = [char(WRITE, "write", "write-without-response"), char(NOTIFY, "notify")]
    c.client.services = [SimpleNamespace(uuid=service, characteristics=chars)]
    ctrl = CasperSleepController(c, kind=kind) if kind else CasperBaseController(c, product=model)
    return ctrl, c


def frames(c):
    return [bytes(call.args[1]).hex() for call in c.client.write_gatt_char.call_args_list]


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    delays = []
    real = asyncio.sleep

    async def short(delay):
        delays.append(delay)
        await real(0)

    monkeypatch.setattr(asyncio, "sleep", short)
    return delays


@pytest.mark.parametrize("transport", range(6))
async def test_gatt_init_and_write_type(transport):
    ctrl, c = make(transport=transport)
    await ctrl.start_notify()
    expected = (
        ["00", "01", "01", "01"]
        if transport == 0
        else ["6e02010071", "6e08010178", "6e0a000179", "6e15010185"]
    )
    assert frames(c) == expected
    assert all(call.kwargs["response"] is False for call in c.client.write_gatt_char.call_args_list)
    assert ctrl._single == (transport == 0)
    assert c.client.start_notify.call_args.args[0].uuid == "1234"


@pytest.mark.parametrize("model", PRODUCTS)
async def test_every_product_has_exact_catalog_actions(model):
    ctrl, c = make(model)
    expected = {
        ACTIONS[i][0]: (ACTIONS[i][1], ACTIONS[i][2])
        for group in PRODUCTS[model][1:6]
        for i in group
    }
    assert ctrl.actions == expected
    assert not ctrl.supports_single_address_pairing  # Transport must be verified first.
    assert len({s.key for s in ctrl.controller_button_specs}) == len(ctrl.controller_button_specs)
    assert ctrl.memory_slot_count == max(
        [i for i in range(1, 4) if f"MemoryPosition{i}" in expected], default=0
    )
    with pytest.raises(ValueError):
        await ctrl.async_perform_casper_base_action("None")
    assert not frames(c)


async def test_model_axes_and_cancelled_cleanup(fast_sleep):
    pro, c = make()
    await pro.start_notify()
    c.client.write_gatt_char.reset_mock()

    async def write(*args, **kwargs):
        c.cancel_command.set()

    c.client.write_gatt_char.side_effect = write
    await pro.async_perform_casper_base_action("LumberUp")
    assert frames(c) == ["6e01003fae", "6e01006edd"]
    maxctrl, c = make("caspermax")
    await maxctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    await maxctrl.async_perform_casper_base_action("LumberUp")
    assert frames(c) == ["6e010041b0"] * 3 + ["6e01006edd"]
    assert fast_sleep.count(0.1) >= 4


async def test_cleanup_on_task_cancel():
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()

    async def write(*args, **kwargs):
        if bytes(args[1])[3] == 0x24:
            raise asyncio.CancelledError

    c.client.write_gatt_char.side_effect = write
    with pytest.raises(asyncio.CancelledError):
        await ctrl.move_back_up()
    assert frames(c) == ["6e01002493", "6e01006edd"]


async def test_side_binding_and_music_default_left():
    ctrl, c = make("hushl400sh")
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    with ctrl.side_scope("right"):
        await ctrl.async_perform_casper_base_action("MotorReset")
    assert frames(c) == ["6e010131a1"]
    ctrl, c = make("nisconup355b")
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError):
        await ctrl.async_perform_casper_base_action("MusicNextSong", music_page=True)
    ctrl._consume(Event("music_available", {}))
    await ctrl.async_perform_casper_base_action("MusicNextSong", music_page=True)
    assert frames(c) == ["6e0100d342"]


async def test_external_detector_threshold_distinct_from_manual():
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    for _ in range(4):
        await ctrl._snore_result(1)
    await ctrl._snore_result(2)
    assert not frames(c)
    await ctrl._snore_result(1)
    assert frames(c) == ["6e010046b5"]
    assert ctrl._snore_count == 0
    await ctrl.async_perform_casper_base_action("AntiSnoring", save=True)
    assert frames(c)[-1] == "6e010069d8"
    await ctrl._snore_result(1)
    await ctrl._snore_result(None)
    assert ctrl._snore_count == 0


async def test_alarm_and_light_capability_gates():
    ctrl, c = make("nisconup355b")
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError):
        await ctrl.async_execute_casper_base_request(Request("rgb_power"))
    ctrl._consume(Event("light_available", {}))
    await ctrl.async_execute_casper_base_request(Request("rgb_timer", value=300))
    assert frames(c) == ["6e200a04020100012ccc"]
    with pytest.raises(ValueError):
        await ctrl.async_execute_casper_base_request(Request("rgb_timer", value=301))
    ctrl._consume(Event("clock_available", {}))
    await ctrl.async_execute_casper_base_request(
        Request("repeat_alarm", slot=1, hour=7, minute=30, mode="ZeroGravity", days=(0,))
    )
    assert frames(c)[-1] == "6e200d0501010100071e45818e"
    with pytest.raises(ValueError):
        await ctrl.async_execute_casper_base_request(
            Request("repeat_alarm", mode="MemoryPosition3")
        )


@pytest.mark.parametrize("kind", ["mm", "sxb"])
async def test_sensor_mtu_write_type_and_per_device_sequence(kind):
    ctrl, c = make(kind=kind)
    await ctrl.start_notify()
    assert all(len(bytes(x.args[1])) <= 20 for x in c.client.write_gatt_char.call_args_list)
    assert all(
        x.kwargs["response"] == (kind == "sxb") for x in c.client.write_gatt_char.call_args_list
    )
    ctrl._sequence = 255
    c.client.write_gatt_char.reset_mock()
    assert isinstance(ctrl, CasperSleepController)
    await ctrl._send("q_part", Request("sensor_query_part"))
    packet = bytes.fromhex("".join(frames(c)))
    assert packet[1] == 1
    assert json.loads(packet[14:]) == {
        "id": 1,
        "cmd": "s_part" if kind == "mm" else "q_part",
        "val": None,
    }
    assert ctrl._sequence == 2


@pytest.mark.parametrize("kind", ["mm", "sxb"])
async def test_late_reply_to_another_command_cannot_complete_a_query(kind):
    ctrl, c = make(kind=kind)
    await ctrl.start_notify()  # sends s_time without awaiting its reply
    ctrl._receive.reset("q_part")
    ctrl._pending = asyncio.get_running_loop().create_future()

    late = {"id": 1, "cmd": "s_time", "val": {"error": 0, "type": "bed-sensor", "ver": "1"}}
    ctrl._on_notification(None, bytearray(envelope(late, 1)))
    assert not ctrl._pending.done()
    assert "casper_sleep_part" not in c.controller_state

    reply = {"id": 2, "cmd": "s_part" if kind == "mm" else "q_part", "val": 3}
    ctrl._on_notification(None, bytearray(envelope(reply, 2)))
    assert ctrl._pending.result() == reply
    assert c.controller_state["casper_sleep_part"] == 3


async def test_information_nullable_error_ignoring_merge():
    ctrl, c = make(kind="sxb")
    ctrl._receive.reset("s_init")
    ctrl._consume({"id": 1, "cmd": "s_init", "val": {"error": 5, "type": "bed-sensor", "ver": "1"}})
    ctrl._consume({"val": {"error": 9, "ver": "2"}})
    assert c.controller_state["casper_sleep_info"] == {"error": 9, "type": "bed-sensor", "ver": "2"}
    with pytest.raises(ValueError):
        ctrl._consume({"val": {"type": 5}})
    assert c.controller_state["casper_sleep_info"]["type"] == "bed-sensor"


@pytest.mark.parametrize("kind", ["mm", "sxb"])
async def test_sensor_report_handshake_and_decode(kind):
    ctrl, c = make(kind=kind)
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    r = Request("sensor_report", part=1 if kind == "mm" else 11, year=2026, month=11, day=3)
    ctrl._report_request = r
    ctrl._receive.reset("q_report")
    ctrl._consume({"id": 1, "cmd": "q_report", "val": {"fsize": 20}})
    assert ctrl._receive.report_size == 20
    ctrl._receive.reset("q_report_allow")
    body = gzip.compress(json.dumps({"day": "2026-11-03", "score": 80}).encode())
    ctrl._receive.report_size = len(body)
    raw = body if kind == "mm" else bytes(14) + body
    ctrl._on_notification(None, bytearray(raw))
    report = c.controller_state["casper_sleep_report"]
    assert report["key"] == f"2026-11-03-{r.part}"
    assert report["data"]["score"] == 80
    ctrl.on_disconnect()
    assert ctrl._receive.action is None


def test_findable_product_variants_and_profile_ownership():
    assert "Casper Base" in BED_TYPE_DISPLAY_NAMES["casper_base"]
    assert set(get_variants_for_bed_type("casper_base")) == set(PRODUCTS)
    assert per_side_profile("casper_base", "caspermax").variant_owned
    assert "motor_count" in hidden_generic_fields("casper_base", "caspermax")


async def test_automatic_detector_timer_replacement_and_disposal(hass, monkeypatch):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    c.hass = hass

    async def execute(fn, **kwargs):
        await fn(ctrl)

    c.async_execute_controller_command = AsyncMock(side_effect=execute)
    real_sleep = asyncio.sleep
    ticks = asyncio.Queue()

    async def controlled_sleep(delay):
        if delay == 3:
            await ticks.get()
        else:
            await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", controlled_sleep)
    hass.states.async_set("sensor.external_detector", "1")
    request = Request("snore_detector", source="sensor.external_detector")
    await ctrl.async_execute_casper_base_request(request)
    first = ctrl._snore_poll
    await real_sleep(0)
    assert not frames(c)  # First sample waits a full detector period.
    await ctrl.async_execute_casper_base_request(request)
    second = ctrl._snore_poll
    await real_sleep(0)
    assert first.cancelled() and ctrl._snore_poll is second
    for _ in range(5):
        ticks.put_nowait(None)
    async with asyncio.timeout(1):
        while not frames(c):
            await real_sleep(0)
    assert frames(c) == ["6e010046b5"]
    ctrl.on_disconnect()
    await real_sleep(0)
    assert second.cancelled() and ctrl._snore_poll is None
    count = len(frames(c))
    ticks.put_nowait(None)
    await real_sleep(0)
    assert len(frames(c)) == count


async def test_sensor_live_replacement_and_local_stop(hass, monkeypatch):
    ctrl, c = make(kind="mm")
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    c.hass = hass
    real_sleep = asyncio.sleep
    ticks = asyncio.Queue()

    async def sleep_tick(delay):
        if delay == 2:
            await ticks.get()
        else:
            await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", sleep_tick)

    async def execute(fn, **kwargs):
        await fn(ctrl)

    c.async_execute_controller_command = AsyncMock(side_effect=execute)
    ctrl._query_live = AsyncMock()
    await ctrl.async_execute_casper_base_request(Request("sensor_live"))
    first = ctrl._poll
    await real_sleep(0)
    await ctrl.async_execute_casper_base_request(Request("sensor_live"))
    second = ctrl._poll
    await real_sleep(0)
    assert first.cancelled() and ctrl._poll is second
    ticks.put_nowait(None)
    async with asyncio.timeout(1):
        while not ctrl._query_live.await_count:
            await real_sleep(0)
    await ctrl.async_execute_casper_base_request(Request("sensor_stop"))
    await real_sleep(0)
    assert second.cancelled() and ctrl._poll is None and ctrl._receive.action is None
    assert not frames(c)  # No fabricated sensor STOP packet.


async def test_remote_finder_sends_no_bed_setup_or_locator_command():
    from custom_components.adjustable_bed.beds.casper_sleep.controller import CasperRemoteController

    _, c = make()
    c.client.services = []
    ctrl = CasperRemoteController(c)
    await ctrl.start_notify()
    await ctrl.async_execute_casper_base_request(Request("remote_find"))
    assert not frames(c)
    assert c.controller_state["casper_remote_status"] == "connected"
    with pytest.raises(ValueError):
        ctrl.validate_casper_base_request(Request("sensor_time"))


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("RM-123", "casper_sleep_mm"),
        ("HJ-123", "casper_sleep_sxb"),
        ("rm-123", None),
        ("prefixRM-123", None),
    ],
)
def test_sensor_classifier_is_separate_from_scan_substring(name, expected):
    from custom_components.adjustable_bed.detection import detect_bed_type

    info = SimpleNamespace(
        name=name,
        address="AA:BB:CC:DD:EE:FF",
        service_uuids=[],
        manufacturer_data={},
        service_data={},
    )
    result = detect_bed_type(info)
    assert (result if result in ("casper_sleep_mm", "casper_sleep_sxb") else None) == expected


async def test_side_bound_button_and_cover_callbacks_keep_their_side():
    ctrl, c = make("hushl400sh")
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    with ctrl.side_scope("right"):
        spec = next(s for s in ctrl.controller_button_specs if s.key == "casper_motorreset")
        await spec.press_fn(ctrl)
        assert frames(c) == ["6e010131a1"]
        c.client.write_gatt_char.reset_mock()
        back = next(s for s in ctrl.motor_control_specs if s.key == "back")
        await back.open_fn(ctrl)
    assert frames(c) == ["6e01012494"] * 3 + ["6e01016ede"]
