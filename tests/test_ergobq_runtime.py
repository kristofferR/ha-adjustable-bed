"""ErgoBQ's actual setup form, registered actions and native entity callbacks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.ergobq.services import register_services
from custom_components.adjustable_bed.codec import ergobq as codec
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.profiles import ergobq as app
from tests.error_helpers import raises_key
from tests.test_ergobq import bed, frames


@pytest.mark.parametrize(
    ("name", "service_data", "expected"),
    [
        ("Bed", None, False),
        ("Bed", {}, False),
        ("Bed", {codec.IDENTITY_SERVICE: b"txbazdssmqcnndfc"}, True),
        ("Bed", {codec.IDENTITY_SERVICE: b"txbazdssmqcnndfd"}, True),
        ("MindLax", {codec.IDENTITY_SERVICE: b"txbazdssmqcnndfc"}, False),
    ],
)
def test_detection_keeps_exact_identity_gate_with_partial_advertisements(name, service_data, expected):
    info = MagicMock(
        spec=BluetoothServiceInfoBleak, address="AA:BB:CC:DD:EE:FF", rssi=-60,
        manufacturer_data=None, service_data=service_data,
        service_uuids=[codec.SERVICE], source="local", device=None,
        advertisement=None, connectable=True, time=0, tx_power=None,
    )
    info.name = name
    result = detect_bed_type_detailed(info)
    assert (result.bed_type == "ergobq") is expected


async def target():
    controller, _, client, _, _ = await bed()
    child = MagicMock(spec=AdjustableBedCoordinator)
    child.name, child.bed_type = "ErgoBQ", "ergobq"
    child.entry = SimpleNamespace(data={})
    child.controller_side = None
    child.capability_controller = controller
    child.stop_epoch = 0

    async def execute(command, **kwargs):
        if kwargs.get("expected_stop_epoch", child.stop_epoch) == child.stop_epoch:
            await command(controller)

    child.async_execute_controller_command = AsyncMock(side_effect=execute)
    return child, controller, client


@pytest.mark.parametrize("status", [0, 1, 2])
async def test_registered_complete_schedule_never_uses_a_partial_collection_cache(hass, status):
    child, _, client = await target()
    register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(child, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "ergobq_schedule",
            {
                "device_id": ["bed"],
                "task": 1,
                "status": status,
                "hour": 7,
                "minute": 30,
                "weekdays": ["sunday", "monday"],
                "position": True,
                "scene": "tv",
            },
            blocking=True,
        )
    packet = codec.parse_frame(bytes.fromhex(frames(client)[0]))
    record = codec.parse_dps(packet.payload)[41]
    assert isinstance(record, bytes) and len(record) == 24
    assert record[:8] == bytes([1, status, 6, 7, 30, 0, 1, 1])


async def test_service_rejects_invalid_sync_and_program_before_any_target_writes(hass):
    child, _, client = await target()
    register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(child, SIDE_BOTH)], []),
    ):
        with raises_key("ergobq_request_invalid", ServiceValidationError) as error:
            await hass.services.async_call(
                DOMAIN,
                "ergobq_schedule",
                {
                    "device_id": ["bed"],
                    "task": 1,
                    "status": 2,
                    "hour": 7,
                    "minute": 30,
                    "sync_massage": True,
                    "head": {"intensity": 3},
                    "legs": {"intensity": 2},
                },
                blocking=True,
            )
        assert error.value.translation_domain == DOMAIN
        assert isinstance(error.value.__cause__, ValueError)
        with raises_key("ergobq_request_invalid", ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "ergobq_diy",
                {
                    "device_id": ["bed"],
                    "mode": 11,
                    "program_hex": "0b01000a8001010203aabb",
                },
                blocking=True,
            )
        client.write_gatt_char.assert_not_awaited()
        await hass.services.async_call(
            DOMAIN,
            "ergobq_massage",
            {
                "device_id": ["bed"],
                "zone": "head",
                "on": True,
                "intensity": 3,
                "minutes": 15,
            },
            blocking=True,
        )
    assert frames(client) == ["55aa000400080c0000040103000f6254"]


@pytest.mark.parametrize("program", [None, "", " \t\n"])
@pytest.mark.parametrize("mode", [10, 31, 255])
async def test_blank_program_requires_saved_mode_before_public_service_execution(hass, program, mode):
    child, _, client = await target()
    register_services(hass)
    data = {"device_id": ["bed"], "mode": mode}
    if program is not None:
        data["program_hex"] = program
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(child, SIDE_BOTH)], []),
    ), raises_key("ergobq_request_invalid", ServiceValidationError):
        await hass.services.async_call(DOMAIN, "ergobq_diy", data, blocking=True)
    client.write_gatt_char.assert_not_awaited()
    child.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize("mode", [0, 11, 255])
async def test_public_diy_accepts_complete_program_and_preserves_supplied_mode_bounds(hass, mode):
    child, _, client = await target()
    register_services(hass)
    program = "0b01000a070001020304050600000132112233445500000a"
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(child, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN, "ergobq_diy",
            {"device_id": ["bed"], "mode": mode, "program_hex": f"  {program}  "},
            blocking=True,
        )
    assert len(frames(client)) == 1
    values = codec.parse_dps(codec.parse_frame(bytes.fromhex(frames(client)[0])).payload)
    assert list(values) == [61, 60]
    assert values == {60: bytes.fromhex(program), 61: bytes([mode, 0, 0, 0])}


@pytest.mark.parametrize("mode", [11, 30])
async def test_public_diy_accepts_blank_program_at_saved_mode_boundaries(hass, mode):
    child, _, client = await target()
    register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(child, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN, "ergobq_diy",
            {"device_id": ["bed"], "mode": mode, "program_hex": " \t\n"},
            blocking=True,
        )
    assert frames(client) == [codec.publish(codec.run_diy(mode)).hex()]


async def test_profile_form_requires_bed_identity_and_saves_the_serial_layout(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {"address": "AA:BB:CC:DD:EE:FF", "name": "Bed", "bed_type": "ergobq"}
    form = await flow.async_step_profile_questions()
    assert form["step_id"] == "profile_questions"
    schema = form["data_schema"]
    assert schema is not None
    with pytest.raises(vol.Invalid):
        schema({})
    answer = schema(
        {"product_type": "txbazdssmqcnndfc", app.SERIAL: "010203040405", app.STAMP: "12"}
    )
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions(answer)
    data = finish.call_args.args[0]
    assert data["motor_count"] == 4 and data["has_massage"] is True
    assert data["disable_angle_sensing"] is True
    assert data[app.STAMP] == "12"


async def test_unlink_native_number_selector_accepts_its_integral_float(hass):
    child, _, client = await target()
    receive = client.start_notify.call_args.args[1]
    client.write_gatt_char.side_effect = lambda *_args, **_kwargs: receive(
        None, bytearray(codec.frame(3, b"\x01"))
    )
    register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(child, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "ergobq_unlink",
            {
                "device_id": ["bed"],
                "phase": 2.0,
            },
            blocking=True,
        )
    assert frames(client) == [codec.auth("12", phase=2).hex()]
    client.disconnect.assert_awaited_once()


async def test_fragmented_auth_trace_and_original_session_cleanup_never_leak_stamp():
    c, co, client, _, _ = await bed()
    client.mtu_size = 23
    await c.write_command(codec.auth("a-sensitive-stamp-that-fragments"))
    assert len(frames(client)) > 1
    for call in co.record_command_trace.call_args_list:
        assert call.kwargs["payload"]["hex"] == "**REDACTED**"


async def test_all_new_entity_keys_and_the_latched_hold_are_covered():
    from tests.entity_translation_reachability import entity_strings, missing_translations

    c, _, _, _, _ = await bed(serial="010203040405")
    assert missing_translations(entity_strings(), [c]) == {}
    assert c.execution.hold == "latched"
    assert not c.execution.concurrent
