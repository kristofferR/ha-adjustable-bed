"""Accepted app differences, caller boundaries and physical session ownership."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.richmat_mh import protocol
from custom_components.adjustable_bed.beds.richmat_mh.app_catalog import catalog
from custom_components.adjustable_bed.beds.richmat_mh.app_controller import (
    DIAGNOSTIC_ROWS,
    RichmatMHAppClassifier,
    RichmatMHAppController,
    _HoldElapsed,
)
from custom_components.adjustable_bed.beds.richmat_mh.controller import resolve_model
from custom_components.adjustable_bed.profiles.richmat_mh_apps import (
    SURFACE_IDS,
    models,
    variants,
)
from tests.state_helpers import state_writer
from tests.test_richmat_mh import sleeps as sleeps

FIXTURES = Path(__file__).parent / "fixtures/richmat_cluster022"
DIAGNOSTICS = json.loads((FIXTURES / "mlily_diagnostic_cases.json").read_text())


def make(
    app: str, model: str = "garm", *, entry_data: dict[str, object] | None = None,
) -> RichmatMHAppController:
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 2
    coordinator.motor_pulse_delay_ms = 100
    coordinator.entry = SimpleNamespace(data=dict(entry_data or {}))
    coordinator.controller_state = {}
    coordinator.client = MagicMock(is_connected=True)
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.handle_controller_state_update.side_effect = coordinator.controller_state.__setitem__
    coordinator.handle_controller_state_updates.side_effect = state_writer(coordinator.controller_state)
    controller = RichmatMHAppController(coordinator, app=app, protocol_variant=f"model_{model}")
    controller._owner_client = coordinator.client
    controller._write_char = MagicMock(uuid=protocol.GATT_MAPS[0][1])
    return controller


def frames(controller: RichmatMHAppController) -> list[str]:
    return [bytes(call.args[1]).hex() for call in controller.client.write_gatt_char.call_args_list]


def test_app_catalogs_keep_independent_membership_and_selectors() -> None:
    assert len(SURFACE_IDS) == 341
    assert tuple(catalog("nisco")) == tuple(catalog("mlily_supreme")) == SURFACE_IDS
    assert "3i" not in models("nisco") and "3i" in models("mlily_supreme")
    assert "model_3i" not in variants("nisco") and "model_3i" in variants("mlily_supreme")
    assert 0x84 in {c.code for c in catalog("nisco")["cfrm"].controls if c.route == "L"}
    assert 0x84 not in {c.code for c in catalog("mlily_supreme")["cfrm"].controls if c.route == "L"}
    assert resolve_model("nisco", "model_3i", None) == (None, "unknown_model")
    assert resolve_model("mlily_supreme", "model_3i", None) == ("3i", None)
    assert resolve_model("nisco", "auto", "QRRM123")[1] == "choose_model"
    assert resolve_model("nisco", "auto", "CeRm123") == ("cerm", None)


@pytest.mark.parametrize("case", DIAGNOSTICS, ids=lambda case: case["id"])
def test_mlily_diagnostic_fixture(case) -> None:
    classifier = RichmatMHAppClassifier("mlily_supreme")
    classifier.rx_type = case["kwargs"].get("rx_type", "INIT")
    events = classifier.feed(bytes.fromhex(case["frame_hex"]))
    expected = case["expected"]
    route = expected["route"]
    kind = {
        "DetectionCall.onResult": "detection_result",
        "AreaCall.updateArea": "detection_available",
        "InitReceiverEvent": "init",
    }.get(route)
    if route == "DetectionCall.onChangeStatus":
        kind = "detection_started" if case["frame_hex"] == protocol.RX_START_DETECTION else "detection_stopped"
    if kind is None:
        assert not events
    else:
        assert [event.kind for event in events] == [kind]
    if expected["buffer_cleared"] is not None:
        assert (classifier.buffer == "") == expected["buffer_cleared"]
    if kind == "detection_result":
        fields = expected["fields"]
        assert events[0].extra == (fields["device_type"], fields["device_no"], fields["result"])
    controller = make("mlily_supreme")
    controller._detection = case["kwargs"].get("callback_registered", True)
    for event in events:
        controller._apply(event)
    row = expected.get("append_row")
    if row:
        observed = controller._diagnostic_rows
        assert len(observed) == 1
        assert observed[0]["component"] == row["device"]
        assert observed[0]["raw_result"] == row["result_code"]
        assert observed[0]["result"] == row["result"]
        for field in ("label_resource", "label", "result_label", "icon"):
            assert observed[0][field] == row[field]
    else:
        assert not controller._diagnostic_rows


def test_diagnostic_rows_append_and_stop_retains_them() -> None:
    controller = make("mlily_supreme")
    controller._detection = True
    event = protocol.Event("detection_result", "6e90c311d2", ("3", "1", "1"))
    controller._apply(event)
    controller._apply(event)
    assert len(controller._coordinator.controller_state[DIAGNOSTIC_ROWS]) == 2
    controller._apply(protocol.Event("detection_stopped"))
    assert len(controller._diagnostic_rows) == 2
    controller._apply(protocol.Event("detection_started"))
    assert controller._diagnostic_rows == []
    nisco = RichmatMHAppClassifier("nisco")
    nisco.rx_type = "INIT"
    assert [event.kind for event in nisco.feed(bytes.fromhex("6e90c311d2"))] == ["init"]


def test_motor_mode_groups_keep_their_own_domains() -> None:
    controller = make("mlily_supreme", "3i")
    controller._version, controller._call_page = "0001", True
    controller.set_group_type("GROUP_SYNC")
    assert controller.motor_mode_options == ("mode1", "mode2", "mode3")
    controller.set_group_type("GROUP_SPLIT")
    assert controller.motor_mode_options == ("mode1", "mode3")


async def test_nisco_snore_reads_mode_after_waiting_for_ble_lock() -> None:
    controller = make("nisco")
    await controller._ble_lock.acquire()
    task = asyncio.create_task(controller.set_snore("anti_snore"))
    await asyncio.sleep(0)
    controller.set_transmit_mode("2")
    controller._ble_lock.release()
    await task
    assert frames(controller) == ["6e130246c9"]
    assert controller.client.write_gatt_char.call_args.kwargs["response"] is True


@pytest.mark.parametrize("app", ["nisco", "mlily_supreme"])
async def test_gatt_priority_and_write_default_are_app_specific(app) -> None:
    from tests.test_richmat_mh import _char, _service

    controller = make(app)
    controller.client.services = [
        _service(service, _char(write, "write-without-response"), _char(notify, "indicate"))
        for service, write, notify in reversed(protocol.GATT_MAPS)
    ]
    await controller.async_discover_capabilities()
    assert controller._write_char.uuid == protocol.GATT_MAPS[0][1]
    assert [char.uuid for char in controller._notify_chars] == [protocol.GATT_MAPS[0][2]]
    await controller.write_command(protocol.TX_VERSION)
    assert controller.client.write_gatt_char.call_args.kwargs["response"] is True


async def test_fallback_write_first_last_roles_and_missing_preferred_fence() -> None:
    from tests.test_richmat_mh import _char, _service

    controller = make("nisco")
    first = _char("first", "notify")
    dual = _char("dual", "write", "notify")
    last = _char("last", "indicate")
    controller.client.services = [_service("12345678-0000-1000-8000-00805f9b34fb", first, dual, last)]
    await controller.async_discover_capabilities()
    assert controller._write_char is dual and controller._notify_chars == [last]
    service, write, _notify = protocol.GATT_MAPS[0]
    controller.client.services = [_service(service, _char(write, "write")), *controller.client.services]
    with pytest.raises(ValueError, match="lacks its fixed characteristics"):
        await controller.async_discover_capabilities()


@pytest.mark.parametrize(("app", "expected"), [("nisco", "6e0b012ca6"), ("mlily_supreme", "6e0b022ca7")])
async def test_light_timer_keeps_each_apps_final_mode_mask(app: str, expected: str) -> None:
    controller = make(app)
    controller._dev["led"] = True
    controller.set_transmit_mode("2")
    await controller.write_light_timer(300, 300)
    assert frames(controller) == [expected]


async def test_expired_hold_dispatch_does_not_write_after_wait() -> None:
    controller = make("nisco")
    with pytest.raises(_HoldElapsed):
        await controller._dispatch(protocol.control_frame(0x24), deadline=asyncio.get_running_loop().time() - 1)
    assert frames(controller) == []
    await controller._release(0)
    assert frames(controller) == ["6e01006edd"]


@pytest.mark.parametrize("renewed", [False, True])
async def test_dispatch_revalidates_the_current_lease_after_ble_wait(renewed) -> None:
    controller = make("nisco")
    now = asyncio.get_running_loop().time()
    context = SimpleNamespace(cancel_event=asyncio.Event(), lease=True, hold_deadline=now - 1)
    await controller._ble_lock.acquire()
    with patch("custom_components.adjustable_bed.beds.richmat_mh.app_controller.current_command_context", return_value=context):
        task = asyncio.create_task(controller._dispatch(protocol.control_frame(0x24)))
        await asyncio.sleep(0)
        if renewed:
            context.hold_deadline = now + 60
        controller._ble_lock.release()
        if renewed:
            await task
            assert frames(controller) == ["6e01002493"]
        else:
            with pytest.raises(_HoldElapsed):
                await task
            assert not frames(controller)


async def test_late_command_cannot_migrate_to_reconnected_client() -> None:
    controller = make("nisco")
    await controller._ble_lock.acquire()
    task = asyncio.create_task(controller.write_command(protocol.control_frame(0x24)))
    await asyncio.sleep(0)
    old = controller.client
    controller._coordinator.client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    controller._ble_lock.release()
    with pytest.raises(ConnectionError):
        await task
    old.write_gatt_char.assert_not_awaited()
    controller.client.write_gatt_char.assert_not_awaited()


async def test_cancelled_write_drains_before_independent_release() -> None:
    controller = make("nisco", "6brm")
    entered, finish = asyncio.Event(), asyncio.Event()
    order = []

    async def write(_char, payload, **_kwargs):
        if payload[3] != 0x6E:
            order.append("movement entered")
            entered.set()
            await finish.wait()
            order.append("movement drained")
        else:
            order.append("release")

    controller.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(controller.move_axis(controller._axes()[0].key, "up"))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    assert order == ["movement entered"]
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert order == ["movement entered", "movement drained", "release"]
    assert frames(controller)[-1] == "6e01006edd"


async def test_elapsed_hold_does_not_add_a_refresh_after_slow_write(sleeps) -> None:
    controller = make("nisco", "6brm")
    clock = [0.0]

    async def write(_char, payload, **_kwargs):
        if payload[3] != 0x6E:
            clock[0] += 0.25

    controller.client.write_gatt_char.side_effect = write
    with patch("custom_components.adjustable_bed.beds.richmat_mh.app_controller.asyncio.get_running_loop") as loop:
        loop.return_value.time.side_effect = lambda: clock[0]
        await controller._held(controller._axes()[0].up, 100)
    assert frames(controller) == ["6e01002493", "6e01006edd"]


@pytest.mark.parametrize("app", ["nisco", "mlily_supreme"])
@pytest.mark.parametrize("version", ["0000", "0001"])
async def test_startup_retains_query_order_and_excluded_timing_slots(app, version, sleeps) -> None:
    controller = make(app)
    original = controller._write_query

    async def query(frame):
        await original(frame)
        if frame == protocol.TX_VERSION and version == "0001":
            controller._apply(protocol.Event("version", version))

    controller._write_query = query
    await controller._run_session_setup()
    tasks = protocol.INIT_VER1 if version == "0001" else protocol.INIT_VER0
    assert frames(controller) == [protocol.TX_VERSION.hex(), *(
        frame.hex() for frame in tasks if frame not in (protocol.TX_AROMA, protocol.TX_SPEECH)
    )]
    assert sleeps == [0.3] * (2 + len(tasks))


async def test_stale_notification_closure_cannot_publish_after_stop(sleeps) -> None:
    controller = make("mlily_supreme")
    controller._notify_chars = [controller._write_char]
    controller.client.start_notify = AsyncMock()
    controller.client.stop_notify = AsyncMock()
    controller._start_session = lambda: asyncio.create_task(asyncio.sleep(0))
    await controller.start_notify()
    receive = controller.client.start_notify.call_args.args[1]
    before = dict(controller._coordinator.controller_state)
    await controller.stop_notify()
    receive(controller._write_char, bytearray.fromhex("6e90c311d2"))
    assert controller._coordinator.controller_state == before


async def test_native_memory_save_uses_attached_fixed_remote_long_caller(sleeps) -> None:
    controller = make("mlily_supreme", "aerm")
    controller._wait_cancel = AsyncMock()
    assert controller._remote_long_codes
    code = controller._remote_long_codes[0]
    await controller.tap(code)
    assert [call.args[0] for call in controller._wait_cancel.call_args_list] == [3, 0.15]
    assert frames(controller) == [protocol.control_frame(code).hex(), "6e01006edd"]


async def test_voice_queue_and_fixed_remote_keep_distinct_cadence(sleeps) -> None:
    controller = make("nisco", "garm")
    # Use this model's accepted map, never a cross-app voice capability union.
    mapped = next((source, target) for source, target in controller._speech.items()
                  if any(c.code == target and c.keep_ms for c in controller.model.controls))
    controller._coordinator.cancel_command.set()
    await controller.voice_queue(mapped[0])
    assert sleeps == [0.12]
    sleeps.clear()
    controller = make("nisco", "6brm")
    controller._coordinator.cancel_command.set()
    await controller._held(controller._axes()[0].up)
    assert sleeps == [0]


def test_aliases_and_entity_metadata_are_owned_by_each_catalog() -> None:
    import gzip

    from custom_components.adjustable_bed.beds.richmat_mh.app_catalog import details

    contract = json.loads(gzip.decompress((FIXTURES / "catalog_contracts.json.gz").read_bytes()))
    strings = json.loads((Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json").read_text())["entity"]
    for app in ("nisco", "mlily_supreme"):
        for model in models(app):
            controller = make(app, model)
            assert [(c.route, c.kind, c.area, c.group, c.label, c.code, c.keep_ms)
                    for c in controller.model.controls] == [tuple(row) for row in contract[app]["models"][model]["controls"]]
            assert details(app, model).model.app == app
            for version in ("0000", "0001"):
                controller._version, controller._call_page = version, version == "0001"
                controller._dev = {"alarm": True, "led": True, "snore": True}
                controller._detection = True
                for platform, specs in (
                    ("button", controller.controller_button_specs),
                    ("select", controller.controller_select_specs),
                    ("sensor", controller.controller_state_sensor_specs),
                    ("number", controller.controller_number_specs),
                    ("cover", controller.motor_control_specs),
                ):
                    assert len({spec.key for spec in specs}) == len(specs), (app, model, version, platform)
                    for spec in specs:
                        assert spec.translation_key in strings[platform], (app, model, spec)
                        if platform == "select":
                            assert {option.lower() for option in spec.options} <= strings[platform][spec.translation_key]["state"].keys()


@pytest.mark.parametrize("app", ("nisco", "mlily_supreme"))
def test_button_names_are_readable_and_unique_per_bed(app: str) -> None:
    from tests.test_entity_names import problems

    raw = re.compile(r"\b(Inc\d?|Dec|\d*Min|Zg2|Ubl|Flat2)\b")
    for model in models(app):
        for advanced in (False, True):
            controller = make(app, model)
            if advanced:
                controller._version, controller._call_page = "0001", True
            names = [spec.name for spec in controller.controller_button_specs]
            assert len(names) == len(set(names)), (model, names)
            for name in names:
                assert not raw.search(name) and not problems(name), (model, name)
            if model == "bhrm" and not advanced:
                assert {"Massage: Head Up", "Massage: Timer 10 Minutes"} <= set(names)


def test_undecoded_mlily_alarm_reply_never_sets_the_alarm_sensor() -> None:
    from custom_components.adjustable_bed.beds.richmat_mh.app_controller import LAST_REPLY
    from custom_components.adjustable_bed.beds.richmat_mh.controller import ALARM_STATUS_KEY

    controller = make("mlily_supreme")
    controller._apply(protocol.Event("alarm", "6e0601ff"))
    assert ALARM_STATUS_KEY not in controller._coordinator.controller_state
    assert controller._coordinator.controller_state[LAST_REPLY] == "6e0601ff"


async def test_nisco_alarm_cancel_uses_the_shared_set_alarm_route(sleeps) -> None:
    from datetime import datetime

    from custom_components.adjustable_bed.alarm import AlarmRequest

    controller = make("nisco", "cfrm")
    controller._dev["alarm"] = True
    assert controller.alarm_capability is not None
    request = AlarmRequest(enabled=False, reference_time=datetime(2026, 11, 18, 7, 0))
    controller.validate_alarm(request)
    await controller.configure_alarm(request)
    assert frames(controller) == [frame.hex() for frame in protocol.TX_ALARM_CANCEL]

