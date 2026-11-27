"""AW MOTION literals and native Home Assistant admission paths."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.dreamsense import protocol
from custom_components.adjustable_bed.beds.dreamsense.awmotion import REPORTS, AwMotionController
from custom_components.adjustable_bed.beds.dreamsense.awmotion_receive import (
    AwMotionReceive,
    common,
    extra,
)
from custom_components.adjustable_bed.beds.dreamsense.transport import select
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.awmotion import CHOICES, PROFILES
from tests.error_helpers import raises_key
from tests.test_dreamsense import make_client, written

FIXTURES = Path(__file__).parent / "fixtures/awmotion"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())
PARSERS = json.loads((FIXTURES / "parser-vectors.json").read_text())
PRODUCTS = json.loads((FIXTURES / "products.json").read_text())
COMMANDS = json.loads((FIXTURES / "commands.json").read_text())


@pytest.mark.parametrize("row", VECTORS, ids=lambda r: r["id"])
def test_codec_matches_all_72_accepted_literals(row):
    x = row["inputs"]
    match row["builder"]:
        case "action":
            result = codec.function(x["opcode"], x["side"], single=x["nordic"])
        case "frame":
            result = codec.frame(*x["data"])
        case "countdown":
            result = codec.countdown(x["minutes"], x["mode"])
        case "light_timer":
            result = protocol.light_seconds(x["seconds"])
        case "color":
            result = codec.rgb(x["red"], x["green"], x["blue"])
        case "extended":
            result = codec.record_20_len(x["domain"], x["subtype"], x["kind"], x["payload"])
        case _:
            pytest.fail(row["builder"])
    frames = result if isinstance(result, tuple) else (result,)
    assert " / ".join(f.hex() for f in frames) == row["expected_bytes"]


@pytest.mark.parametrize("row", PARSERS, ids=lambda r: r["id"])
def test_all_20_accepted_parser_vectors(row):
    assert (common if row["parser"] == "common" else extra)(bytes.fromhex(row["input"])) == row[
        "expected"
    ]


def test_profiles_use_only_current_product_menus_and_program_values():
    assert set(PROFILES) == set(CHOICES) == {"SN300", "SN500", "HC800"}
    by_detail = {c["detail_id"]: c for c in COMMANDS}
    for row in PRODUCTS:
        p = PROFILES[row["fields"]["14"].strip('"')]
        menus = row["menus"]
        expected = [
            by_detail[d]
            for d in dict.fromkeys(menus["motor"] + menus["massage"] + menus["presets"])
        ]
        assert [(a.action, a.code, a.save) for a in p.controls] == [
            (c["action"], c["opcode"], c["program_opcode"]) for c in expected
        ]
        assert p.alarm == {
            by_detail[d]["action"]: by_detail[d]["opcode"] for d in menus["alarm_modes"]
        }
        assert not any((p.repeat, p.side, p.split, p.vibration))
        reset = next(a for a in p.controls if a.action == "MotorReset")
        assert not reset.held and reset.release


async def runtime(hass, model="SN300", layout=1):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="AW MOTION",
        data={
            CONF_ADDRESS: "11:22:33:44:55:79",
            CONF_NAME: "AW MOTION",
            const.CONF_BED_TYPE: "awmotion",
            const.CONF_PROTOCOL_VARIANT: model,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_HAS_MASSAGE: True,
        },
    )
    entry.add_to_hass(hass)
    c = AdjustableBedCoordinator(hass, entry)
    c._client = make_client(layout)
    ctrl = await create_controller(c, "awmotion", model, c._client)
    assert isinstance(ctrl, AwMotionController)
    c._controller = ctrl
    ctrl._wait = AsyncMock()
    await ctrl.start_notify()
    return c, ctrl


@pytest.mark.parametrize("layout", range(6))
@pytest.mark.parametrize("model", PROFILES)
async def test_startup_notify_and_wire_shape(hass, layout, model):
    c, ctrl = await runtime(hass, model, layout)
    assert written(c) == (
        ["00", "01", "01"] if layout == 0 else ["6e02010071", "6e08010178", "6e0a000179"]
    )
    assert not ctrl.supports_clock_sync and not ctrl.supports_single_address_pairing
    assert c.client.start_notify.call_args.args[0] is c.client.services[0].characteristics[1]
    assert all(
        call.args[0] is c.client.services[0].characteristics[0] and call.kwargs["response"] is False
        for call in c.client.write_gatt_char.await_args_list
    )
    await ctrl.start_notify()
    assert c.client.start_notify.await_count == 1


def test_independent_first_handles_and_last_route_enum():
    client = make_client(1, without_response=False)
    client.services[0].characteristics.pop()  # first service has only write
    client.services += make_client(0).services
    chosen = select(client, 1, "SN300", routes=AwMotionController._routes)
    assert chosen.write is client.services[0].characteristics[0]
    assert chosen.notify is client.services[1].characteristics[1]
    assert chosen.single and chosen.response
    client.services.reverse()
    assert not select(client, 1, "SN300", routes=AwMotionController._routes).single
    for svc in client.services:
        svc.characteristics[0].properties = ["write-without-response"]
    with raises_key("dreamsense_transport"):
        select(client, 1, "SN300", routes=AwMotionController._routes)


@pytest.mark.parametrize("model", PROFILES)
async def test_every_product_control_native_button_timer_and_save(hass, model):
    c, ctrl = await runtime(hass, model)
    buttons = {s.key: s for s in ctrl.controller_button_specs}
    for action in ctrl.profile.controls:
        c.client.write_gatt_char.reset_mock()
        if "MinuteTimer" in action.action:
            await c.async_execute_controller_command(
                lambda _ctrl, action=action: ctrl.set_massage_timer(int(action.action[7:9]))
            )
        elif action.held:
            # Use the finite public hold action, retaining its first tick and release.
            await c.async_execute_controller_command(
                lambda _ctrl, action=action: ctrl.hold_control(action.action, 100)
            )
            assert buttons[action.action].hold is not None
        else:
            await c.async_execute_controller_command(
                lambda _ctrl, action=action: buttons[action.action].press_fn(ctrl)
            )
        assert written(c) == [codec.command(action.code).hex()] + (
            [codec.command(codec.STOP).hex()] if action.release else []
        )
        if action.save is not None:
            c.client.write_gatt_char.reset_mock()
            await c.async_execute_controller_command(
                lambda _ctrl, action=action: buttons["save_" + action.action].press_fn(ctrl)
            )
            assert written(c) == [codec.command(action.save).hex()]
            assert any(call.args[0] == 3000 for call in ctrl._wait.await_args_list)


async def test_failure_has_no_command_retry_or_stale_state(hass):
    c, ctrl = await runtime(hass)
    c.client.write_gatt_char.reset_mock()
    c.client.write_gatt_char.side_effect = RuntimeError("failed")
    with pytest.raises(RuntimeError, match="failed"):
        await c.async_execute_controller_command(lambda _ctrl: ctrl.press("MotorReset"))
    assert written(c) == ["6e010031a0"]


async def test_cancelled_movement_releases_on_original_session_and_no_new_model_write(hass):
    c, ctrl = await runtime(hass)
    c.client.write_gatt_char.reset_mock()

    async def cancel_after_write(*_args, **_kwargs):
        c.cancel_command.set()

    c.client.write_gatt_char.side_effect = cancel_after_write
    await c.async_execute_controller_command(lambda _ctrl: ctrl.hold_control("HeadUp", 500))
    assert written(c) == ["6e01002493", "6e01006edd"]
    c.cancel_command.clear()
    hass.config_entries.async_update_entry(
        c.entry, data={**c.entry.data, const.CONF_PROTOCOL_VARIANT: "SN500"}
    )
    with raises_key("dreamsense_session"):
        await ctrl.press("HeadUp")
    assert len(written(c)) == 2


async def test_capability_gates_light_alarm_reports_and_disconnect(hass):
    c, ctrl = await runtime(hass, layout=0)
    c.client.write_gatt_char.reset_mock()
    with raises_key("dreamsense_capability"):
        await ctrl.light_settings(color=(18, 52, 86))
    notify = c.client.start_notify.call_args.args[1]
    notify(None, bytearray.fromhex("6e090100786e0e00037f6e90351e00"))
    assert c.controller_state.get(REPORTS)["motor_1"]["angle"] == 30
    await c.async_execute_controller_command(
        lambda _ctrl: ctrl.light_settings(color=(18, 52, 86), seconds=0)
    )
    await c.async_execute_controller_command(lambda _ctrl: ctrl.close_light())
    assert written(c) == ["6e0bffff77", "6e0cff128b6e0d345605", "75"]
    assert ctrl.controller_number_specs[0].native_max_value == 900
    c.client.write_gatt_char.reset_mock()
    await c.async_execute_controller_command(
        lambda _ctrl: ctrl.configure_alarm(
            AlarmRequest(enabled=False, reference_time=datetime.now(UTC))
        )
    )
    assert written(c) == ["6e05000073", "6e06000074"]
    with ctrl.side_scope(const.SIDE_RIGHT), raises_key("dreamsense_physical"):
        ctrl.validate_light(seconds=30)
    ctrl.on_disconnect()
    notify(None, bytearray.fromhex("6e90351e51"))
    assert c.controller_state.get(REPORTS) is None
    with raises_key("dreamsense_capability"):
        await ctrl.light_settings(seconds=30)


def test_stream_extended_fragmentation_and_common_early_consumption():
    r = AwMotionReceive()
    r.feed(bytes.fromhex("996e200c0102"))
    assert r.last_event is None
    r.feed(bytes.fromhex("0200012c052dfe6e0e00037f"))
    assert r.values["motor_extended"]["height"] == 30
    assert r.capabilities == {"light"}
    r.feed(bytes.fromhex("6e0901"))
    r.feed(bytes.fromhex("0078"))
    assert "clock" not in r.capabilities
    r.feed(bytes.fromhex("6e2000"))
    assert not r.pending


@pytest.mark.parametrize("model", PROFILES)
async def test_setup_profile_id_and_card_shapes(hass, model):
    from custom_components.adjustable_bed import _async_sync_profile_ids
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from tests.form_helpers import finish_new_bed
    from tests.test_richmat_family_flow import setup_flow

    flow = setup_flow(hass, **{const.CONF_BED_TYPE: "awmotion"})
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: model})
        result = await finish_new_bed(flow, result)
    entry = MockConfigEntry(domain=const.DOMAIN, data=result["data"])
    entry.add_to_hass(hass)
    _async_sync_profile_ids(hass, entry)
    assert entry.data[const.CONF_PROFILE_ID] == f"awmotion:{model}"
    assert const.CONF_PROTOCOL_VARIANT in per_side_profile("awmotion", model).keys
    c = AdjustableBedCoordinator(hass, entry)
    await c.async_prime_offline_controller()
    ctrl = c.capability_controller
    assert ctrl.profile == PROFILES[model]
    for spec in ctrl.controller_button_specs:
        if spec.hold is not None:
            assert spec.card.section == "motors"
        if spec.key.startswith("save_"):
            assert spec.card.role == "save"


async def test_native_service_preflights_all_targets_before_any_write(hass):
    first, enabled = await runtime(hass)
    second, unsupported = await runtime(hass, "SN500")
    enabled._receive.capabilities.update({"clock", "light"})
    await services.async_register_services(hass)
    first.client.write_gatt_char.reset_mock()
    second.client.write_gatt_char.reset_mock()
    with patch.object(
        services,
        "_resolve_sided_targets",
        return_value=([(first, const.SIDE_BOTH), (second, const.SIDE_BOTH)], []),
    ):
        # Live capability preflight must reject the second physical bed before
        # the first one's settings change.
        with raises_key("dreamsense_capability"):
            await hass.services.async_call(
                const.DOMAIN,
                "dreamsense_light",
                {"device_id": ["a", "b"], "rgb_color": [18, 52, 86]},
                blocking=True,
            )
        assert not written(first) and not written(second)
    with patch.object(
        services, "_resolve_sided_targets", return_value=([(first, const.SIDE_BOTH)], [])
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "dreamsense_light",
            {"device_id": "a", "rgb_color": [18, 52, 86]},
            blocking=True,
        )
        assert written(first) == ["6e0cff128b6e0d345605"]
        first.client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN, "set_alarm", {"device_id": "a", "enabled": False}, blocking=True
        )
        assert written(first) == ["6e05000073", "6e06000074"]


async def test_held_execution_is_scoped_to_this_products_axes(hass):
    _, ctrl = await runtime(hass, "SN500")
    assert set(ctrl.execution.hold_controls) == {
        "HeadUp",
        "HeadDown",
        "FootUp",
        "FootDown",
        "LumberUp",
        "LumberDown",
        "PillowUp",
        "PillowDown",
    }
    assert not ctrl.execution.concurrent
    with raises_key("dreamsense_action"):
        ctrl.validate_hold_control("MotorReset", 100)
    with raises_key("dreamsense_action"):
        ctrl.validate_hold_control("HeadAndFootUp", 100)
