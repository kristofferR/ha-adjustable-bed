"""Independent frozen APK vectors and real Customatic controller lifecycle."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.customatic import (
    COMMAND_CHARACTERISTIC,
    COMMAND_SERVICE,
    DEVICE_INFO_FIELDS,
    DEVICE_INFO_SERVICE,
    CustomaticController,
    command_frame,
)


def make_controller(
    profile: str = "clarity", *, properties: tuple[str, ...] = ("write",)
) -> CustomaticController:
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 2
    coordinator.motor_count = 4  # Profile, not generic configuration, determines axes.
    coordinator.client = MagicMock(
        is_connected=True,
        services=[
            MagicMock(
                uuid=COMMAND_SERVICE,
                characteristics=[
                    MagicMock(uuid=COMMAND_CHARACTERISTIC, properties=properties, handle=1)
                ],
            )
        ],
    )
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.read_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    return CustomaticController(coordinator, profile=profile)


def written(controller: CustomaticController) -> list[str]:
    return [call.args[1].hex() for call in controller.client.write_gatt_char.call_args_list]


# Independent package-local memory table, including the source reset helper's
# dead semantic name but its reachable flat+ZG mask, and the toast-only flat+ANTI.
MEMORY_VECTORS = (
    ("flat", "040208000000"),
    ("zg", "040200001000"),
    ("anti", "040200008000"),
    ("program", "040280000000"),
    ("incline", "040200004000"),
    ("flat+zg", "040208001000"),
    ("flat+anti", "040208008000"),
    ("flat+program", "040288000000"),
    ("flat+incline", "040208004000"),
    ("zg+anti", "040200009000"),
    ("zg+program", "040280001000"),
    ("zg+incline", "040200005000"),
    ("anti+program", "040280008000"),
    ("anti+incline", "04020000c000"),
    ("program+incline", "040280004000"),
    ("flat+zg+anti", "040208009000"),
    ("flat+zg+program", "040288001000"),
    ("flat+zg+incline", "040208005000"),
    ("flat+anti+program", "040288008000"),
    ("flat+anti+incline", "04020800c000"),
    ("flat+program+incline", "040288004000"),
    ("zg+anti+program", "040280009000"),
    ("zg+anti+incline", "04020000d000"),
    ("zg+program+incline", "040280005000"),
    ("anti+program+incline", "04028000c000"),
    ("flat+zg+anti+program", "040288009000"),
    ("flat+zg+anti+incline", "04020800d000"),
    ("flat+zg+program+incline", "040288005000"),
    ("flat+anti+program+incline", "04028800c000"),
    ("zg+anti+program+incline", "04028000d000"),
    ("flat+zg+anti+program+incline", "04028800d000"),
)


@pytest.mark.parametrize("profile", ["clarity", "remedy"])
@pytest.mark.parametrize(("control", "expected"), MEMORY_VECTORS)
@pytest.mark.asyncio
async def test_all_artifact_memory_subsets_no_release(
    profile: str, control: str, expected: str
) -> None:
    controller = make_controller(profile)
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.hold_control(control, 250)
    assert written(controller) == [expected] * 4
    assert control in controller.held_control_options


MOTOR_VECTORS = (
    ("back_up", 0x01),
    ("back_down", 0x02),
    ("legs_up", 0x04),
    ("legs_down", 0x08),
    ("back_up+legs_up", 0x05),
    ("back_up+legs_down", 0x09),
    ("back_down+legs_up", 0x06),
    ("back_down+legs_down", 0x0A),
    ("lumbar_up", 0x10),
    ("lumbar_down", 0x20),
    ("back_up+lumbar_up", 0x11),
    ("back_up+lumbar_down", 0x21),
    ("back_down+lumbar_up", 0x12),
    ("back_down+lumbar_down", 0x22),
    ("legs_up+lumbar_up", 0x14),
    ("legs_up+lumbar_down", 0x24),
    ("legs_down+lumbar_up", 0x18),
    ("legs_down+lumbar_down", 0x28),
    ("back_up+legs_up+lumbar_up", 0x15),
    ("back_up+legs_up+lumbar_down", 0x25),
    ("back_up+legs_down+lumbar_up", 0x19),
    ("back_up+legs_down+lumbar_down", 0x29),
    ("back_down+legs_up+lumbar_up", 0x16),
    ("back_down+legs_up+lumbar_down", 0x26),
    ("back_down+legs_down+lumbar_up", 0x1A),
    ("back_down+legs_down+lumbar_down", 0x2A),
)


@pytest.mark.parametrize(
    ("profile", "control", "mask"),
    [
        (profile, control, mask)
        for profile in ("clarity", "jeromes", "remedy")
        for control, mask in MOTOR_VECTORS
        if profile == "remedy" or "lumbar" not in control
    ],
)
@pytest.mark.asyncio
async def test_all_safe_motor_masks_release(profile: str, control: str, mask: int) -> None:
    controller = make_controller(profile)
    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        await controller.hold_control(control, 120)
    assert written(controller) == [f"0402000000{mask:02x}"] * 2 + ["040200000000"]
    assert sleep.call_args_list[-1].args == (0.1,)
    assert control in controller.held_control_options


@pytest.mark.parametrize(
    ("profile", "axes", "option_count", "light"),
    [
        ("clarity", ("back", "legs"), 39, True),
        ("jeromes", ("back", "legs"), 8, False),
        ("remedy", ("back", "legs", "lumbar"), 57, True),
    ],
)
def test_exact_profile_capabilities(
    profile: str, axes: tuple[str, ...], option_count: int, light: bool
) -> None:
    controller = make_controller(profile)
    assert tuple(spec.key for spec in controller.motor_control_specs) == axes
    assert all(spec.scheduler_resource == "*" for spec in controller.motor_control_specs)
    assert controller.simultaneous_movement_axes == axes
    assert len(controller.held_control_options) == option_count
    assert controller.supports_held_control
    assert controller.supports_simultaneous_movement
    assert controller.supports_lights is light
    assert controller.supports_light_toggle_control is light
    assert not controller.supports_discrete_light_control
    assert not controller.supports_light_state_feedback
    assert not controller.supports_massage
    assert not controller.supports_position_feedback
    assert not controller.requires_notification_channel
    assert not controller.supports_memory_presets
    assert not controller.supports_memory_programming
    assert controller.memory_slot_count == 0


@pytest.mark.parametrize("profile", ["clarity", "jeromes", "remedy"])
@pytest.mark.asyncio
async def test_profile_flat_and_light_vectors(profile: str) -> None:
    controller = make_controller(profile)
    await controller.preset_flat()
    assert written(controller) == (
        ["040210000000"] * 3 if profile == "jeromes" else ["040208000000"]
    )
    controller.client.write_gatt_char.reset_mock()
    if profile == "jeromes":
        await controller.execute_app_control("restored_flat")
        assert written(controller) == ["040208000000"]
        with pytest.raises(ValueError):
            await controller.lights_toggle()
    else:
        await controller.lights_toggle()
        assert written(controller) == ["040200020000"]


@pytest.mark.parametrize(
    ("profile", "action"),
    [
        ("jeromes", "zg"),
        ("jeromes", "flat+program"),
        ("jeromes", "lumbar_up"),
        ("clarity", "lumbar_down"),
        ("clarity", "back_up+back_down"),
        ("remedy", "back_up+back_up"),
        ("remedy", "zg+back_up"),
        ("remedy", ""),
        ("remedy", "zg+"),
        ("remedy", "zero_g"),
    ],
)
@pytest.mark.asyncio
async def test_unreachable_and_unsafe_controls_fail_before_writes(
    profile: str, action: str
) -> None:
    controller = make_controller(profile)
    with pytest.raises(ValueError):
        await controller.hold_control(action, 100)
    assert written(controller) == []


@pytest.mark.parametrize("duration", [0, -1, True, 100.5, 60001])
@pytest.mark.asyncio
async def test_invalid_duration_has_no_release_or_commands(duration: int) -> None:
    controller = make_controller()
    with pytest.raises(ValueError):
        await controller.hold_control("back_up", duration)
    assert written(controller) == []


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("ZG", "040200001000"),
        ("ANTI", "040200008000"),
        ("Incline", "040200004000"),
        ("Program", "040280000000"),
        ("Save ZG", "040280001000"),
        ("Save Incline", "040280004000"),
        ("Reset", "040288000000"),
    ],
)
@pytest.mark.asyncio
async def test_named_button_callback_real_delivery(action: str, expected: str) -> None:
    controller = make_controller()
    spec = next(spec for spec in controller.controller_button_specs if spec.name == action)
    with patch("asyncio.sleep", new=AsyncMock()):
        await spec.press_fn(controller.bind_side("left"))
    assert written(controller) == [expected] * 24


@pytest.mark.parametrize("profile", ["clarity", "jeromes", "remedy"])
@pytest.mark.asyncio
async def test_numbered_memory_rejected(profile: str) -> None:
    controller = make_controller(profile)
    with pytest.raises(ValueError):
        await controller.preset_memory(1)
    with pytest.raises(ValueError):
        await controller.program_memory(1)
    assert written(controller) == []


@pytest.mark.asyncio
async def test_timed_motor_deadline_and_release_outside_deadline() -> None:
    controller = make_controller("remedy")
    timestamps = []
    start = asyncio.get_running_loop().time()

    async def record(*args, **kwargs) -> None:
        timestamps.append(asyncio.get_running_loop().time() - start)

    controller.client.write_gatt_char.side_effect = record
    await controller.hold_control("back_up+legs_down+lumbar_up", 250)
    assert written(controller) == ["040200000019"] * 3 + ["040200000000"]
    assert all(timestamp < 0.25 for timestamp in timestamps[:-1])
    assert timestamps[-1] >= 0.35


@pytest.mark.asyncio
async def test_timed_memory_deadline_no_final_stop() -> None:
    controller = make_controller()
    await controller.hold_control("flat+zg+anti+program+incline", 250)
    assert written(controller) == ["04028800d000"] * 3


@pytest.mark.parametrize("motor", [True, False])
@pytest.mark.asyncio
async def test_task_cancellation_cleanup(motor: bool) -> None:
    controller = make_controller()
    started = asyncio.Event()

    async def block(uuid, packet, **kwargs) -> None:
        if packet != bytes.fromhex("040200000000"):
            started.set()
            await asyncio.Event().wait()

    controller.client.write_gatt_char.side_effect = block
    task = asyncio.create_task(controller.hold_control("back_up" if motor else "zg", 2000))
    await started.wait()
    controller._coordinator.cancel_command.set()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written(controller) == (["040200000001", "040200000000"] if motor else ["040200001000"])


@pytest.mark.asyncio
async def test_real_controller_timeout_propagates_after_cleanup() -> None:
    controller = make_controller()
    controller.client.write_gatt_char.side_effect = [TimeoutError("BLE deadline"), None]
    with pytest.raises(TimeoutError, match="BLE deadline"):
        await controller.hold_control("back_up", 1000)
    assert written(controller) == ["040200000001", "040200000000"]


@pytest.mark.asyncio
async def test_cancel_signal_ends_refresh_but_cannot_suppress_stop() -> None:
    controller = make_controller()

    async def cancel_on_first(uuid, packet, **kwargs) -> None:
        controller._coordinator.cancel_command.set()

    controller.client.write_gatt_char.side_effect = cancel_on_first
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.move_back_up()
    assert written(controller) == ["040200000001", "040200000000"]


@pytest.mark.parametrize(
    ("axis", "up", "expected"),
    [
        ("back", True, "040200000001"),
        ("back", False, "040200000002"),
        ("legs", True, "040200000004"),
        ("legs", False, "040200000008"),
        ("lumbar", True, "040200000010"),
        ("lumbar", False, "040200000020"),
    ],
)
@pytest.mark.asyncio
async def test_motor_entity_callbacks_delegate_to_bound_controller(
    axis: str, up: bool, expected: str
) -> None:
    original = make_controller("remedy")
    target = make_controller("remedy")
    spec = next(spec for spec in original.motor_control_specs if spec.key == axis)
    with patch("asyncio.sleep", new=AsyncMock()):
        await (spec.open_fn if up else spec.close_fn)(target.bind_side("right"))
    assert written(original) == []
    assert written(target) == [expected] * 2 + ["040200000000"]


@pytest.mark.asyncio
async def test_two_axis_base_api_exact_or_and_preflight() -> None:
    controller = make_controller()
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.move_simultaneously("back", True, "legs", False)
    assert written(controller) == ["040200000009"] * 2 + ["040200000000"]
    controller.client.write_gatt_char.reset_mock()
    for args in [
        ("back", True, "back", False),
        ("head", True, "legs", True),
        ("back", 1, "legs", False),
    ]:
        with pytest.raises(ValueError):
            await controller.move_simultaneously(*args)
    assert written(controller) == []


@pytest.mark.parametrize(
    ("properties", "response"),
    [
        (("write",), True),
        (("write-without-response",), False),
        (("write", "write-without-response"), True),
    ],
)
@pytest.mark.asyncio
async def test_host_write_policy_from_exact_role(
    properties: tuple[str, ...], response: bool
) -> None:
    controller = make_controller(properties=properties)
    await controller.preset_flat()
    assert controller.client.write_gatt_char.call_args.kwargs["response"] is response


@pytest.mark.parametrize("defect", ["wrong_service", "wrong_char", "not_write", "duplicate"])
@pytest.mark.asyncio
async def test_gatt_role_validation_before_command(defect: str) -> None:
    controller = make_controller()
    service = controller.client.services[0]
    if defect == "wrong_service":
        service.uuid = DEVICE_INFO_SERVICE
    elif defect == "wrong_char":
        service.characteristics[0].uuid = "62741625-52f9-8864-b1ab-3b3a8d65950b"
    elif defect == "not_write":
        service.characteristics[0].properties = ["read"]
    else:
        service.characteristics.append(service.characteristics[0])
    with pytest.raises(ValueError):
        await controller.preset_flat()
    assert written(controller) == []


def add_device_info(controller: CustomaticController) -> None:
    controller.client.services.append(
        MagicMock(
            uuid=DEVICE_INFO_SERVICE,
            characteristics=[
                MagicMock(uuid=uuid, properties=["read"]) for _, uuid in DEVICE_INFO_FIELDS
            ],
        )
    )


@pytest.mark.asyncio
async def test_device_info_five_reads_order_spacing_decoding_cache_and_refresh() -> None:
    controller = make_controller("remedy")
    add_device_info(controller)
    controller.client.read_gatt_char.side_effect = [
        b"Vendor",
        b"HW",
        b"SW",
        b"FW",
        b"Clarity\xff",
    ] * 2
    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        await controller.async_discover_capabilities()
        assert [call.args[0].uuid for call in controller.client.read_gatt_char.call_args_list] == [
            "00002a29-0000-1000-8000-00805f9b34fb",
            "00002a27-0000-1000-8000-00805f9b34fb",
            "00002a28-0000-1000-8000-00805f9b34fb",
            "00002a26-0000-1000-8000-00805f9b34fb",
            "00002a24-0000-1000-8000-00805f9b34fb",
        ]
        assert [call.args for call in sleep.call_args_list] == [(0.12,)] * 4
        await controller.refresh_device_info(only_if_missing=True)
        assert controller.client.read_gatt_char.await_count == 5
        spec = next(
            spec
            for spec in controller.controller_button_specs
            if spec.key == "customatic_refresh_device_info"
        )
        await spec.press_fn(controller)
    assert controller.client.read_gatt_char.await_count == 10
    info = controller.protocol_diagnostics["device_info"]
    assert isinstance(info, dict)
    assert info["model"] == "Clarity\ufffd"
    assert controller.simultaneous_movement_axes == ("back", "legs", "lumbar")
    assert controller._coordinator.handle_controller_state_update.call_args.args == (
        "customatic_model",
        "Clarity\ufffd",
    )
    assert tuple(spec.state_key for spec in controller.controller_state_sensor_specs) == (
        "customatic_manufacturer",
        "customatic_hardware_revision",
        "customatic_software_revision",
        "customatic_firmware_revision",
        "customatic_model",
    )
    controller.client.start_notify.assert_not_called()
    assert written(controller) == []


@pytest.mark.parametrize(
    "error", [BleakError("absent"), OSError("adapter disappeared"), TimeoutError("read timeout")]
)
@pytest.mark.asyncio
async def test_device_info_failure_retries_entire_batch_and_missing_dis_not_gate(
    error: Exception,
) -> None:
    controller = make_controller()
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.async_discover_capabilities()
    controller.client.read_gatt_char.assert_not_called()
    add_device_info(controller)
    controller.client.read_gatt_char.side_effect = [error, b"H", b"S", b"F", b"M"] + [b""] * 5
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.refresh_device_info(only_if_missing=True)
        await controller.refresh_device_info(only_if_missing=True)
        await controller.refresh_device_info(only_if_missing=True)
    assert controller.client.read_gatt_char.await_count == 10
    info = controller.protocol_diagnostics["device_info"]
    assert isinstance(info, dict)
    assert all(value == "" for value in info.values())
    await controller.preset_flat()
    assert written(controller) == ["040208000000"]


def test_constructor_and_packet_validation() -> None:
    with pytest.raises(ValueError):
        make_controller("auto")
    for mask in (-1, 0x100000000, True):
        with pytest.raises(ValueError):
            command_frame(mask)
    assert command_frame(0xFFFFFFFF).hex() == "0402ffffffff"
