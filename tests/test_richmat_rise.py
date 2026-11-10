"""Accepted artifact vectors and actual controller, platform and service behavior."""

from dataclasses import replace

import pytest

from custom_components.adjustable_bed.beds.richmat_classic import rise
from custom_components.adjustable_bed.beds.richmat_classic.caller import Selection, selected_operand
from custom_components.adjustable_bed.beds.richmat_classic.profiles import (
    load_catalog,
    resolve_layout,
)
from custom_components.adjustable_bed.beds.richmat_classic.protocol import (
    alarm,
    control,
    rgb,
    worker_interval,
)
from custom_components.adjustable_bed.codec import richmat as codec
from tests.richmat_rise_vectors import records
from tests.test_richmat_classic import controller, packets
from tests.test_richmat_classic import instant as instant


@pytest.mark.parametrize("app,total", [("luunarise2", 417), ("powercool", 22)])
def test_frozen_artifact_vectors(app, total):
    vectors = records(app, "vectors")
    assert len(vectors) == total
    checked = 0
    for vector in vectors:
        args = vector["inputs"]
        kind = args.get("builder", vector.get("kind"))
        if kind == "control":
            result = control(bytes.fromhex(args["code"]), "RAW" if args["nordic"] else "FRAMED", args["mode"])
        elif kind == "button":
            result = control(bytes((args["command"],)), "RAW" if args.get("vendor") == "raw" else "FRAMED", args.get("mode", 0))
        elif kind == "sum":
            result = codec.frame(*args.get("data", args.get("body")))
        elif kind == "rgb":
            color = bytes.fromhex(args["rgb"]) if isinstance(args["rgb"], str) else args["rgb"]
            result = rgb(*color)
        elif kind == "lamp":
            result = rise.lamp_timer(args["seconds"], save=not args.get("slider", True))
        elif kind == "alarm":
            result = b"".join(alarm(args.get("minutes", args.get("delay_minutes")), int(args["code"], 16) if "code" in args else args["action"]))
        elif kind == "diagnostic":
            result = codec.motor_test_schedule(tuple(zip(args["orders"], args["run_seconds"], args["rest_seconds"], strict=True)), args["total_rest"], args["total_run"], args["tx"], args["code"], 1, tuple(args["motors"]))
        elif kind == "factory":
            result = rise.Schedule(tuple(tuple(row) for row in args["records"]), args["pause"], args["count"], args["tx_type"], args["code_type"], args["identifier"], tuple(args["motors"])).encode()
        elif kind == "receive":
            from custom_components.adjustable_bed.beds.richmat_classic.receive import ReceiveState
            state = ReceiveState()
            result = bytes.fromhex(args["notification"])
            state.feed(result, app=app, layout="A8RM", desk_bound=False, table_controls_bound=False)
            assert state.alarm_capable or state.light_capable
        else:
            assert kind == "ascii"  # Excluded radio network administration.
            continue
        assert result.hex() == vector["expected_bytes"].replace(" ", "").lower(), vector["id"]
        checked += 1
    assert checked >= total - 2


@pytest.mark.parametrize("app,total", [("luunarise2", 21046), ("powercool", 20664)])
def test_every_frozen_resource_event_uses_its_member_getter_and_wire(app, total):
    catalog = load_catalog(app)
    commands = records(app, "commands")
    assert len(commands) == total
    for row in commands:
        if app == "luunarise2":
            button = next(c for c in catalog.models[row["variant"].upper()].controls if c.node == row["node"])
            raw = row["protocol"] == "P1"
            resource = row["resource"]
            if row["scope"] != "EXCLUDED_NON_BED_DESK":
                excluded = button.excluded_long if "long" in row["event"] else button.excluded_short
                assert excluded == (row["scope"] == "EXCLUDED_ACCESSORY"), row
            # Every ordinary frozen event remains bound to this app's exact
            # getter. Dynamic selector branches are exercised below.
            assert resource in button.resource_keys.values() or row["event"] == "release" or row.get("dynamic") or "stop" in row["event"].lower(), row
            for mode, literal in row["bytes"].items():
                code = bytes.fromhex(row["command_hex"])
                assert control(code, "RAW" if raw else "FRAMED", int(mode)).hex() == literal.lower(), row
        else:
            if row["variant"] == "shared":
                assert row["parameters"]["opcode"] == 0x6E
            else:
                assert any(c.node == row["node"] for c in catalog.models[row["variant"].upper()].controls)
            params = row["parameters"]
            literal = row["bytes"].lower()
            code = params.get("opcode")
            if code is not None:
                assert control(bytes((code,)), "RAW" if row["protocol"] == "P2" else "FRAMED", params.get("mode", 0)).hex() == literal, row


def test_member_layout_identity_modes_and_manual_aliases():
    luuna, power = (load_catalog(app) for app in ("luunarise2", "powercool"))
    assert (len(luuna.models), len(power.models)) == (604, 586)
    assert set(luuna.models) - set(power.models) == {"HARM", "HBRM", "HCRM", "HDRM", "HERM", "HKRM", "HLRM", "HMRM", "HNRM", "HPRM", "HQRM", "HRRM", "HTRM", "HURM", "HVRM", "HWRM", "HXRM", "HYRM"}
    assert luuna.models["HKRM"].modes == (0, 1)
    assert next(c for c in luuna.models["AHRM"].controls if c.node == 12).short == "5E"
    assert next(c for c in power.models["AHRM"].controls if c.node == 12).short == "5D"
    assert next(c for c in luuna.models["H9RM"].controls if c.node == 13).short == "62"
    assert not any(c.node == 13 and c.rich_button for c in power.models["H9RM"].controls)
    for app in ("luunarise2", "powercool"):
        assert resolve_layout(app, "B6RU") == "B6RM"
        assert resolve_layout(app, "Cool Touch 123", from_name=True) == "QRRM"
        assert resolve_layout(app, "OTRM", russian=True) == "O0RM"
    assert worker_interval("6BRM0001", "RAW", rise=True) == 170
    assert worker_interval("6BRM0001", "FRAMED", rise=True) == 150


@pytest.mark.parametrize("app,total", [("luunarise2", 8966), ("powercool", 8623)])
def test_every_accepted_control_attribute_survives_import(app, total):
    catalog = load_catalog(app)
    count = 0
    for model in records(app, "catalog"):
        controls = {c.node: c for c in catalog.models[model["layout"]].controls}
        assert len(controls) == len(model["nodes"])
        for node in model["nodes"]:
            c = controls[node["node"]]
            source = node["attributes"]
            assert (c.short, c.short_old, c.long, c.tag, c.extra, c.alarm_clock) == tuple(source.get(key) for key in ("press_short", "press_short_old", "press_long", "tag", "extra", "alarm_clock"))
            assert c.status == int(source.get("press_status", 0))
            assert c.threshold_ms == int(source.get("press_long_time", 3000))
            assert c.visibility == source.get("visibility", "visible")
            assert c.rich_button == node["class"].endswith(".RichButton")
            count += 1
    assert count == total


@pytest.mark.parametrize("app", ["luunarise2", "powercool"])
@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_e3rm_held_recall_and_next_poll_save_use_50ms_cleanup(app, wire, instant):
    ctrl, coord = controller(app, "E3RM", wire)
    assert any(s.key == "richmat_classic_program" for s in ctrl.controller_select_specs)
    await ctrl.execute_action(1, hold_ms=300)
    values = packets(coord)
    assert values[:-1] and set(values[:-1]) == {"2e" if wire == "RAW" else "6e01002e9d"}
    assert values[-1] == ("6e" if wire == "RAW" else "6e01006edd")
    coord.client.write_gatt_char.reset_mock()
    ctrl._select("program", "armed")
    await ctrl.execute_action(1)
    assert packets(coord) == (["2b", "6e"] if wire == "RAW" else ["6e01002b9a", "6e01006edd"])
    assert not ctrl._selection.armed


@pytest.mark.parametrize("app", ["luunarise2", "powercool"])
async def test_music_short_exclusion_does_not_consume_lock_long(app, instant):
    ctrl, coord = controller(app, "FGRM")
    with pytest.raises(ValueError, match="excluded"):
        await ctrl.execute_action(1)
    await ctrl.execute_action(1, long=True)
    assert packets(coord) == ["6e010084f3", "6e01006edd"]
    keys = {s.key for s in ctrl.controller_button_specs}
    assert "richmat_classic_1_long" in keys and "richmat_classic_1" not in keys


@pytest.mark.parametrize("app", ["luunarise2", "powercool"])
def test_dynamic_getters_do_not_invent_a_foot_bank(app):
    buttons = load_catalog(app).models["GVRM"].controls
    button = next(c for c in buttons if c.node == 2)
    assert selected_operand(button, "RAW", 1, Selection()) == bytes.fromhex("37")
    assert selected_operand(button, "FRAMED", 1, Selection(head=False)) is None
    up = next(c for c in load_catalog(app).models["U3RM"].controls if c.tag == "51")
    assert [selected_operand(up, "FRAMED", 1, replace(Selection(), press_flag=flag)) for flag in ("53", "54", "55")] == [b"?", b"A", b"q"]


@pytest.mark.parametrize("app", ["luunarise2", "powercool"])
async def test_direct_utilities_keep_raw_route_and_own_cleanup(app, instant):
    ctrl, coord = controller(app, "D1RM", "RAW")
    ctrl._receive.menu.update(("alarm", "light"))
    for value in range(6):
        await ctrl.async_execute_richmat_rise_request(rise.Request("massage_timer", progress=value))
    assert packets(coord) == ["6e01005ecd", "6e01000170", "6e01005fce", "6e010063d2", "6e01000473", "6e010061d0"]
    other, other_coord = controller(app, "D9RM", "RAW")
    await other.async_execute_richmat_rise_request(rise.Request("massage_timer", progress=0))
    assert packets(other_coord) == ["6e01008bfa"]
    coord.client.write_gatt_char.reset_mock()
    for seconds, save in [(0, False), (0, True), (300, False)]:
        await ctrl.async_execute_richmat_rise_request(rise.Request("lamp_timer", seconds=seconds, timer_save=save))
    await ctrl.async_execute_richmat_rise_request(rise.Request("rgb", color=(1, 221, 255)))
    assert packets(coord) == ["6e0bffff77", "6e0b000079", "6e0b012ca6", "6e0cff017a6e0dddff57"]
    with pytest.raises(ValueError):
        rise.lamp_timer(301, save=True)


def test_complete_alarm_combinations_reduction_and_unsupported_choices():
    expected = {
        0x58: (0x77, 0x7A, 0x7D), 0x46: (0x78, 0x7B, 0x7E),
        0x45: (0x79, 0x7C, 0x7F), 0x59: (0xAC, 0xAD, 0xAE),
        0x2E: (0x81, 0x82, 0x83), 0x2F: (0xA6, 0xA7, 0xA8), 0x30: (0xA9, 0xAA, 0xAB),
    }
    for preset, codes in expected.items():
        for massage, code in zip((0x5D, 0x4C, 0x4E), codes, strict=True):
            assert rise.alarm_action({"bed": preset, "massage": massage}, ("bed", "massage")) == code
    choices = {"bed": 0x58, "all": 0x5D, "head": 0x4C, "foot": 0x4E}
    assert rise.alarm_action(choices, ("head", "bed", "foot")) == 0x77
    assert rise.alarm_action(choices, ("all", "head", "bed", "foot")) == 0x7D
    assert rise.alarm_action({"buzzer": 0x80, "head": 0x4C}, ("head", "buzzer")) == 0x80
    for preset in (0xB0, 0xB1, 0xF6):
        with pytest.raises(ValueError, match="no alarm packet"):
            rise.alarm_action({"bed": preset, "head": 0x4C}, ("bed", "head"))


async def test_notification_discovers_real_number_platform_and_old_session_is_ignored(hass, instant):
    from custom_components.adjustable_bed.number import _number_entities_for
    from tests.test_malouf_app_entities import configure_entity_runtime

    ctrl, coord = controller("luunarise2", "A8RM")
    runtime = configure_entity_runtime(hass, ctrl, "richmat_classic_apps")
    assert _number_entities_for(hass, runtime) == []
    old = ctrl._session
    ctrl._notification(old, old.notify, bytearray.fromhex("6e0e00037f"))
    entities = _number_entities_for(hass, runtime)
    assert len(entities) == 1
    assert entities[0].native_max_value == 300

    async def execute(fn, **kwargs):
        await fn(ctrl)

    runtime.async_execute_controller_command.side_effect = execute
    await entities[0].async_set_native_value(300)
    assert packets(coord) == ["6e0b012ca6"]
    ctrl.on_disconnect()
    assert not ctrl.controller_number_specs
    ctrl._notification(old, old.notify, bytearray.fromhex("6e0e00037f"))
    assert not ctrl.controller_number_specs


@pytest.mark.parametrize("app", ["luunarise2", "powercool"])
async def test_failed_local_notify_does_not_block_controls_or_emit_initialization(app, instant):
    from tests.test_richmat_classic_transport import Services, route

    ctrl, coord = controller(app, "6BRM")
    coord.client.services = Services([route(0)])
    coord.entry.data["ble_device_name"] = "6BRM0001"
    coord.client.start_notify.return_value = False
    await ctrl.start_notify()
    assert packets(coord) == ["6e0a000179"]
    await ctrl.execute_action(1, hold_ms=0)
    assert packets(coord)[-2:] == ["6e01002493", "6e01006edd"]


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_diagnostic_cancel_is_a_movement_and_sends_fresh_stop(wire, instant):
    ctrl, coord = controller("powercool", "TEST", wire)
    async def write(_channel, data, **kwargs):
        coord.cancel_command.set()
    coord.client.write_gatt_char.side_effect = write
    await ctrl.async_execute_richmat_rise_request(rise.Request("diagnostic_cycle"))
    assert packets(coord) == (["24", "6e"] if wire == "RAW" else ["6e01002493", "6e01006edd"])


async def test_schedule_fragmentation_preserves_bytes_and_does_not_invent_stop(instant):
    ctrl, coord = controller("powercool", "RMCS", "RAW")
    vector = records("powercool", "vectors")[-1]
    a = vector["inputs"]
    schedule = rise.Schedule(tuple(zip(a["orders"], a["run_seconds"], a["rest_seconds"], strict=True)), 0, 0, "ble", "new", 1, (1, 2, 3, 4))
    await ctrl.async_execute_richmat_rise_request(rise.Request("program_schedule", schedule=schedule))
    data = packets(coord)
    assert [len(bytes.fromhex(x)) for x in data] == [20, 20, 20, 20, 9]
    assert "".join(data) == vector["expected_bytes"].lower()
    overflow = replace(schedule, rest=0x123456)
    assert overflow.encode()[74:76] == bytes.fromhex("1234")
    with pytest.raises(ValueError):
        replace(schedule, motors=(1, 1, 2, 3)).encode()


async def test_service_reconnects_and_proves_capability_before_rgb(hass, instant):
    from unittest.mock import AsyncMock, patch

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services
    from tests.test_generic_services import target
    from tests.test_richmat_classic_transport import Services, route

    ctrl, coord = controller("powercool", "A8RM")
    ctrl._session = None
    coord.entry.data["ble_device_name"] = "A8RM0001"
    coord.client.services = Services([route(2)])
    owner, _ = target(family=type(ctrl))
    owner.capability_controller = ctrl

    async def write(channel, data, **kwargs):
        if data.hex() == "6e0a000179":
            ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f"))

    coord.client.write_gatt_char.side_effect = write

    async def query(fn, **kwargs):
        await ctrl.start_notify()
        return await fn(ctrl)

    async def execute(fn, **kwargs):
        await fn(ctrl)

    owner.async_execute_controller_query = AsyncMock(side_effect=query)
    owner.async_execute_controller_command.side_effect = execute
    await async_register_services(hass)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(owner, "both")], [])):
        await hass.services.async_call(DOMAIN, "richmat_rise", {"device_id": "bed", "operation": "rgb", "rgb_color": [1, 221, 255]}, blocking=True)
    assert packets(coord)[-1] == "6e0cff017a6e0dddff57"
    assert owner.async_execute_controller_query.await_count == 1


async def test_real_command_context_renews_e3rm_hold_past_finite_pulse_count():
    from tests.hold_lease_wire import intervals, leased_hold

    async def move(ctrl):
        await ctrl.hold_control("richmat_classic_1", 60000)

    result = await leased_hold(
        "richmat_classic_apps:powercool:E3RM:nordic", move,
        end_after_s=2.1, end="stop", entry_data={"motor_pulse_count": 1},
    )
    assert len(result.held) > result.pulse_count
    assert {write.data for write in result.held} == {bytes.fromhex("2e")}
    # The fake ATT write takes 7 ms; the source poll waits 150 ms after it.
    assert set(intervals(result.held)) == {157}
    assert result.after and all(write.data == bytes.fromhex("6e") for write in result.after)


@pytest.mark.parametrize("app", ["luunarise2", "powercool"])
@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
@pytest.mark.parametrize("initially_armed", [False, True])
async def test_retained_e3rm_entity_follows_mem_and_replacement_controller(
    hass, instant, app, wire, initially_armed,
):
    from unittest.mock import patch

    from homeassistant.exceptions import ServiceValidationError
    from pytest_homeassistant.common import MockEntityPlatform

    from custom_components.adjustable_bed.button import ControllerActionButton, _button_entities_for
    from custom_components.adjustable_bed.const import BED_TYPE_RICHMAT_CLASSIC_APPS, DOMAIN
    from custom_components.adjustable_bed.services import async_register_services
    from tests.state_helpers import published
    from tests.test_malouf_app_entities import configure_entity_runtime

    ctrl, radio = controller(app, "E3RM", wire)
    ctrl._select("program", "armed" if initially_armed else "recall")
    runtime = configure_entity_runtime(hass, ctrl, BED_TYPE_RICHMAT_CLASSIC_APPS)
    runtime.controller_side = None
    runtime.bed_type = BED_TYPE_RICHMAT_CLASSIC_APPS
    runtime.stop_epoch = 0
    callbacks = set()

    def register(fn):
        callbacks.add(fn)
        return lambda: callbacks.discard(fn)

    runtime.register_controller_state_callback.side_effect = register

    def bind(current, transport):
        runtime.capability_controller = runtime.controller = current
        transport.handle_controller_state_updates.side_effect = lambda *updates: [
            fn(published(*updates)) for fn in tuple(callbacks)
        ]

    async def execute(fn, **kwargs):
        await fn(runtime.controller)

    runtime.async_execute_controller_command.side_effect = execute
    bind(ctrl, radio)
    button = next(
        entity for entity in _button_entities_for(hass, runtime)
        if isinstance(entity, ControllerActionButton) and entity._spec.key == "richmat_classic_1"
    )
    platform = MockEntityPlatform(hass, domain="button", platform_name=DOMAIN)
    await platform.platform_data.async_load_translations()
    await platform.async_add_entities([button])
    await async_register_services(hass)

    def assert_card_route(held):
        state = hass.states.get(button.entity_id)
        assert state is not None
        keys = {key for key in state.attributes if key.startswith(("hold_", "held_"))}
        if held:
            assert state.attributes["held_control"] == "richmat_classic_1"
            assert state.attributes["hold_lease_mode"] == "stream"
            runtime.controller.validate_hold_control("richmat_classic_1", 60000)
        else:
            assert not keys
            with pytest.raises(ValueError, match="available held control"):
                runtime.controller.validate_hold_control("richmat_classic_1", 60000)

    assert_card_route(not initially_armed)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(runtime, "both")], [])):
        for reconnect in (False, True):
            if reconnect:
                replacement, replacement_radio = controller(app, "E3RM", wire)
                replacement._select("program", "armed")
                bind(replacement, replacement_radio)
                ctrl, radio = replacement, replacement_radio
                ctrl._publish()
                assert_card_route(False)
            ctrl._select("program", "recall")
            assert_card_route(True)
            await hass.services.async_call(DOMAIN, "hold_control", {
                "device_id": "bed", "control": "richmat_classic_1", "duration": 0.1,
            }, blocking=True)
            values = packets(radio)
            assert values[:-1] and set(values[:-1]) == {"2e" if wire == "RAW" else "6e01002e9d"}
            assert values[-1] == ("6e" if wire == "RAW" else "6e01006edd")
            radio.client.write_gatt_char.reset_mock()
            ctrl._select("program", "armed")
            assert_card_route(False)
            with pytest.raises(ServiceValidationError):
                await hass.services.async_call(DOMAIN, "hold_control", {
                    "device_id": "bed", "control": "richmat_classic_1", "duration": 0.1,
                }, blocking=True)
            assert packets(radio) == []
            waits = []

            async def wait(milliseconds, cancel, recorded=waits):
                recorded.append(milliseconds)
                return not cancel.is_set()

            ctrl._wait = wait
            await button.async_press()
            assert packets(radio) == (["2b", "6e"] if wire == "RAW" else ["6e01002b9a", "6e01006edd"])
            assert waits == [50]
            assert_card_route(True)
            radio.client.write_gatt_char.reset_mock()
    await platform.async_reset()
