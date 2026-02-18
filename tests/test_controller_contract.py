"""Contract tests for controller capabilities and factory completeness."""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.const import (
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_OCTO,
    BED_TYPE_RICHMAT,
    BED_TYPE_SBI,
    KEESON_VARIANT_SINO,
    LEGGETT_VARIANT_OKIN,
    OCTO_VARIANT_STANDARD,
    RICHMAT_VARIANT_NORDIC,
    SBI_VARIANT_BOTH,
    SUPPORTED_BED_TYPES,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.controller_factory import create_controller

SHARED_CAPABILITY_FLAGS: tuple[str, ...] = (
    "supports_memory_presets",
    "supports_memory_programming",
    "supports_lights",
    "supports_light",
    "supports_under_bed_lights",
    "supports_discrete_light_control",
    "supports_light_cycle",
    "supports_position_feedback",
    "supports_massage",
    "supports_motor_control",
    "supports_stop_all",
    "supports_fan_control",
)


class _FactoryCoordinator(SimpleNamespace):
    """Minimal coordinator stub used for controller factory tests."""

    def __init__(self) -> None:
        super().__init__(
            client=None,
            cancel_command=asyncio.Event(),
            motor_pulse_count=10,
            motor_pulse_delay_ms=100,
            address="AA:BB:CC:DD:EE:FF",
            name="Contract Test Bed",
            motor_count=2,
            has_massage=False,
            disable_angle_sensing=True,
        )

    async def async_execute_controller_command(self, *args: Any, **kwargs: Any) -> None:
        """Stub command executor used by keepalive-capable controllers."""
        return None


def _protocol_variant_for_bed_type(bed_type: str) -> str | None:
    """Return a deterministic protocol variant for factory-completeness tests."""
    if bed_type == BED_TYPE_RICHMAT:
        return RICHMAT_VARIANT_NORDIC
    if bed_type == BED_TYPE_LEGGETT_PLATT:
        return LEGGETT_VARIANT_OKIN
    if bed_type == BED_TYPE_SBI:
        return SBI_VARIANT_BOTH
    if bed_type == BED_TYPE_OCTO:
        return OCTO_VARIANT_STANDARD
    return None


def _make_connected_client() -> SimpleNamespace:
    """Create a minimal connected BLE client for factory calls that need one."""
    return SimpleNamespace(
        is_connected=True,
        services=[SimpleNamespace(uuid="0000")],
        address="AA:BB:CC:DD:EE:FF",
    )


async def _create_controller_for_bed_type(bed_type: str) -> BedController:
    """Create a controller through the factory for the given bed type."""
    coordinator = _FactoryCoordinator()
    client = _make_connected_client()
    variant = _protocol_variant_for_bed_type(bed_type)
    return await create_controller(coordinator, bed_type, variant, client)


def _is_overridden(controller: BedController, method_name: str) -> bool:
    """Return True when the controller overrides a method from BedController."""
    subclass_method = getattr(type(controller), method_name, None)
    base_method = getattr(BedController, method_name, None)
    return subclass_method is not None and subclass_method is not base_method


class _ContractController(BedController):
    """Minimal concrete controller used to validate base cleanup semantics."""

    def __init__(self, coordinator: _FactoryCoordinator, *, fail_write: bool = False) -> None:
        super().__init__(coordinator)
        self._fail_write = fail_write
        self.stop_calls = 0

    @property
    def control_characteristic_uuid(self) -> str:
        return "00000000-0000-0000-0000-000000000000"

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        del command, repeat_count, repeat_delay_ms, cancel_event
        if self._fail_write:
            raise RuntimeError("write failed")

    async def _send_stop(self) -> None:
        self.stop_calls += 1

    async def move_head_up(self) -> None:
        return None

    async def move_head_down(self) -> None:
        return None

    async def move_head_stop(self) -> None:
        return None

    async def move_back_up(self) -> None:
        return None

    async def move_back_down(self) -> None:
        return None

    async def move_back_stop(self) -> None:
        return None

    async def move_legs_up(self) -> None:
        return None

    async def move_legs_down(self) -> None:
        return None

    async def move_legs_stop(self) -> None:
        return None

    async def move_feet_up(self) -> None:
        return None

    async def move_feet_down(self) -> None:
        return None

    async def move_feet_stop(self) -> None:
        return None

    async def stop_all(self) -> None:
        return None

    async def preset_flat(self) -> None:
        return None

    async def preset_memory(self, memory_num: int) -> None:
        del memory_num
        return None

    async def program_memory(self, memory_num: int) -> None:
        del memory_num
        return None


def test_base_declares_shared_capability_flags() -> None:
    """Base controller should define all shared capability flags."""
    for flag in SHARED_CAPABILITY_FLAGS:
        assert hasattr(BedController, flag), f"Missing shared capability on base: {flag}"


@pytest.mark.parametrize("bed_type", SUPPORTED_BED_TYPES)
async def test_factory_resolves_every_supported_bed_type(bed_type: str) -> None:
    """Every supported bed type should resolve through create_controller."""
    controller = await _create_controller_for_bed_type(bed_type)
    assert isinstance(controller, BedController)


async def test_factory_auto_detects_keeson_sino_variant_for_okin_ble_signature() -> None:
    """Keeson auto mode should select Sino for BetterLiving-style BLE signature."""
    coordinator = _FactoryCoordinator()
    client = SimpleNamespace(
        is_connected=True,
        services=[
            SimpleNamespace(uuid="0000fff0-0000-1000-8000-00805f9b34fb"),
            SimpleNamespace(uuid="0000ffb0-0000-1000-8000-00805f9b34fb"),
        ],
        address="AA:BB:CC:DD:EE:FF",
    )

    controller = await create_controller(
        coordinator=coordinator,
        bed_type=BED_TYPE_KEESON,
        protocol_variant=VARIANT_AUTO,
        client=client,
        device_name="OKIN-BLE00000",
    )

    assert isinstance(controller, BedController)
    assert getattr(controller, "_variant", None) == KEESON_VARIANT_SINO


@pytest.mark.parametrize("bed_type", SUPPORTED_BED_TYPES)
async def test_controllers_expose_shared_capabilities_as_bools(bed_type: str) -> None:
    """Controllers should expose all shared capabilities as boolean values."""
    controller = await _create_controller_for_bed_type(bed_type)

    for flag in SHARED_CAPABILITY_FLAGS:
        value = getattr(controller, flag)
        assert isinstance(value, bool), f"{type(controller).__name__}.{flag} must be bool"

    assert controller.supports_light == controller.supports_lights


@pytest.mark.parametrize("bed_type", SUPPORTED_BED_TYPES)
async def test_declared_capabilities_map_to_implemented_methods(bed_type: str) -> None:
    """Capability flags should correspond to relevant concrete behavior."""
    controller = await _create_controller_for_bed_type(bed_type)

    if controller.supports_lights:
        assert any(
            _is_overridden(controller, method_name)
            for method_name in ("lights_on", "lights_off", "lights_toggle")
        )

    if controller.supports_discrete_light_control:
        assert _is_overridden(controller, "lights_on")
        assert _is_overridden(controller, "lights_off")

    if controller.supports_memory_presets:
        assert controller.memory_slot_count > 0

    if controller.supports_massage:
        assert any(
            _is_overridden(controller, method_name)
            for method_name in (
                "massage_off",
                "massage_toggle",
                "massage_head_toggle",
                "massage_foot_toggle",
                "massage_mode_step",
            )
        )

    if controller.supports_circulation_massage:
        for method_name in (
            "massage_circulation_full_body",
            "massage_circulation_head",
            "massage_circulation_leg",
            "massage_circulation_hip",
        ):
            assert _is_overridden(controller, method_name)

    if controller.supports_fan_control:
        for method_name in ("fan_left_cycle", "fan_right_cycle", "fan_sync_cycle"):
            assert _is_overridden(controller, method_name)
        assert controller.fan_level_max > 0


async def test_base_move_with_stop_always_sends_stop_on_error() -> None:
    """Base _move_with_stop should send stop in cleanup even on write failure."""
    controller = _ContractController(_FactoryCoordinator(), fail_write=True)

    with pytest.raises(RuntimeError, match="write failed"):
        await controller._move_with_stop(b"\x01")

    assert controller.stop_calls == 1


async def test_base_preset_with_stop_always_sends_stop_on_error() -> None:
    """Base _preset_with_stop should send stop in cleanup even on write failure."""
    controller = _ContractController(_FactoryCoordinator(), fail_write=True)

    with pytest.raises(RuntimeError, match="write failed"):
        await controller._preset_with_stop(b"\x02")

    assert controller.stop_calls == 1


async def test_overridden_stop_helpers_keep_finally_cleanup() -> None:
    """Controllers overriding stop helpers should preserve finally-based cleanup.

    Linak is excluded from _move_with_stop finally enforcement because it
    explicitly auto-stops when commands cease.
    """
    instantiated: dict[type[BedController], BedController] = {}

    for bed_type in SUPPORTED_BED_TYPES:
        controller = await _create_controller_for_bed_type(bed_type)
        instantiated[type(controller)] = controller

    for controller in instantiated.values():
        controller_cls = type(controller)

        if (
            controller_cls._move_with_stop is not BedController._move_with_stop
            and not controller.auto_stops_on_idle
        ):
            source = inspect.getsource(controller_cls._move_with_stop)
            assert "finally" in source, f"{controller_cls.__name__}._move_with_stop missing finally"

        if controller_cls._preset_with_stop is not BedController._preset_with_stop:
            source = inspect.getsource(controller_cls._preset_with_stop)
            assert (
                "finally" in source
            ), f"{controller_cls.__name__}._preset_with_stop missing finally"
