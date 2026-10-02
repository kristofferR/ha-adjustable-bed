"""Restonic BT Remote (com.keeson.restonicBT 1.2.0) Keeson app profiles.

Every frame literal comes from the accepted clean-room report (row058). Remote A
and remote B are the app's user-selected remote styles.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import yaml
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.actuator_groups import ACTUATOR_GROUPS
from custom_components.adjustable_bed.beds import keeson
from custom_components.adjustable_bed.beds.keeson import (
    RESTONIC_A_CONTROLS,
    RESTONIC_B_CONTROLS,
    RESTONIC_ZZZ_BUTTON_KEY,
    KeesonController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_KEESON,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_BASE_WRITE_CHAR_UUID,
    KEESON_VARIANT_BASE,
    KEESON_VARIANT_RESTONIC_A,
    KEESON_VARIANT_RESTONIC_B,
    KEESON_VARIANTS,
    SIDE_BOTH,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services

NAME = "base-i4.00002574"
ZERO = "e5fe160000000006"

Action = Callable[[KeesonController], Awaitable[None]]

# (action, app resource id, frame, repeats while held) shared by both remotes.
COMMON_VECTORS: list[tuple[Action, str, str, bool]] = [
    (lambda c: c.preset_flat(), "flat", "e5fe1600000008fe", False),
    (lambda c: c.move_feet_down(), "foot_down", "e5fe1608000000fe", True),
    (lambda c: c.move_feet_up(), "foot_up", "e5fe160400000002", True),
    (lambda c: c.move_head_down(), "head_down", "e5fe160200000004", True),
    (lambda c: c.move_head_up(), "head_up", "e5fe160100000005", True),
]
A_VECTORS = [
    *COMMON_VECTORS,
    (lambda c: c.preset_zero_g(), "iv_zerog", "e5fe1600100000f6", True),
]
B_VECTORS = [
    *COMMON_VECTORS,
    (lambda c: c.move_back_legs_down(), "iv_back_down", "e5fe160a000000fc", True),
    (lambda c: c.move_back_legs_up(), "iv_back_up", "e5fe160500000001", True),
    (lambda c: c.lights_toggle(), "iv_light", "e5fe160000020004", False),
    (lambda c: c.preset_zero_g(), "iv_zerog", "e5fe1600100000f6", False),
    (lambda c: c.restonic_zzz(), "iv_zzz", "e5fe160080000086", False),
]


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:58",
            CONF_NAME: NAME,
            CONF_BED_TYPE: BED_TYPE_KEESON,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:58",
        entry_id="restonic_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def coordinator(
    hass: HomeAssistant, entry: MockConfigEntry, mock_coordinator_connected
) -> AdjustableBedCoordinator:
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_connect()
    return coordinator


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.base.asyncio.sleep", sleep)
    return sleep


def _restonic(coordinator: AdjustableBedCoordinator, variant: str) -> KeesonController:
    return KeesonController(coordinator, variant=variant, device_name=NAME)


def _frame(hex_bytes: str, response: bool = True):
    return call(KEESON_BASE_WRITE_CHAR_UUID, bytes.fromhex(hex_bytes), response=response)


@pytest.mark.parametrize(
    ("variant", "vectors"),
    [(KEESON_VARIANT_RESTONIC_A, A_VECTORS), (KEESON_VARIANT_RESTONIC_B, B_VECTORS)],
    ids=["remoteA", "remoteB"],
)
async def test_every_app_control_sends_its_literal_frame_then_the_delayed_zero(
    coordinator, mock_bleak_client: MagicMock, no_sleep, variant, vectors
):
    """Held controls refresh every 100 ms; every control releases with one zero frame +100 ms."""
    controller = _restonic(coordinator, variant)
    for action, ui_id, frame, repeats in vectors:
        mock_bleak_client.write_gatt_char.reset_mock()
        no_sleep.reset_mock()
        await action(controller)
        writes = 10 if repeats else 1
        assert mock_bleak_client.write_gatt_char.await_args_list == (
            [_frame(frame)] * writes + [_frame(ZERO)]
        ), ui_id
        # 100 ms between refreshes, then the 100 ms release delay.
        assert no_sleep.await_args_list == [call(0.1)] * writes, ui_id


@pytest.mark.parametrize(
    ("command", "frame"),
    [
        (0x00000000, ZERO),
        (0x12345678, "e5fe1678563412f2"),
        (0xFFFFFFFF, "e5fe16ffffffff0a"),
        (0x80000000, "e5fe160000008086"),
    ],
)
async def test_builder_boundary_vectors(coordinator, command, frame):
    """Little-endian 32-bit value and complemented additive checksum (report width vectors)."""
    controller = _restonic(coordinator, KEESON_VARIANT_RESTONIC_A)
    assert controller._build_command(command) == bytes.fromhex(frame)


async def test_safety_stop_sends_the_zero_frame_immediately(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    await _restonic(coordinator, KEESON_VARIANT_RESTONIC_B).stop_all()
    assert mock_bleak_client.write_gatt_char.await_args_list == [_frame(ZERO)]
    no_sleep.assert_not_awaited()


async def test_cancellation_ends_the_refresh_and_still_releases(
    coordinator, mock_bleak_client: MagicMock, monkeypatch: pytest.MonkeyPatch
):
    async def cancel(_delay: float) -> None:
        coordinator.cancel_command.set()

    monkeypatch.setattr("custom_components.adjustable_bed.beds.base.asyncio.sleep", cancel)
    await _restonic(coordinator, KEESON_VARIANT_RESTONIC_A).move_head_up()
    assert mock_bleak_client.write_gatt_char.await_args_list == [
        _frame("e5fe160100000005"),
        _frame(ZERO),
    ]


async def test_cadence_defaults_to_the_app_and_keeps_custom_settings(coordinator):
    assert _restonic(coordinator, KEESON_VARIANT_RESTONIC_A).motor_pulse_settings() == (10, 100)
    coordinator._motor_pulse_count = 7
    coordinator._motor_pulse_delay_ms = 150
    assert _restonic(coordinator, KEESON_VARIANT_RESTONIC_B).motor_pulse_settings() == (7, 150)


@pytest.mark.parametrize(
    ("properties", "response"),
    [(["write", "write-without-response"], False), (["write"], True)],
)
async def test_fixed_target_and_android_default_write_type(
    coordinator, mock_bleak_client: MagicMock, no_sleep, properties, response
):
    """The app writes only FFE5/FFE9 and inherits Android's characteristic write type."""
    mock_bleak_client.services = [
        SimpleNamespace(
            uuid="0000fff0-0000-1000-8000-00805f9b34fb",
            characteristics=[
                SimpleNamespace(uuid="0000fff2-0000-1000-8000-00805f9b34fb", properties=["write"])
            ],
        ),
        SimpleNamespace(
            uuid="0000ffe5-0000-1000-8000-00805f9b34fb",
            characteristics=[
                SimpleNamespace(uuid=KEESON_BASE_WRITE_CHAR_UUID, properties=properties)
            ],
        ),
    ]
    controller = _restonic(coordinator, KEESON_VARIANT_RESTONIC_A)
    assert controller.control_characteristic_uuid == KEESON_BASE_WRITE_CHAR_UUID
    await controller.preset_flat()
    assert mock_bleak_client.write_gatt_char.await_args_list == [
        _frame("e5fe1600000008fe", response),
        _frame(ZERO, response),
    ]


async def test_remote_capabilities(coordinator):
    """Each remote exposes only its own controls; neither has memory, massage or STOP."""
    coordinator._motor_count = 4
    for variant, remote_b in ((KEESON_VARIANT_RESTONIC_A, False), (KEESON_VARIANT_RESTONIC_B, True)):
        controller = _restonic(coordinator, variant)
        assert [spec.key for spec in controller.motor_control_specs] == (
            ["head", "feet", "back_legs"] if remote_b else ["head", "feet"]
        )
        assert "back_legs" in controller.stale_motor_entity_keys
        assert controller.held_control_options == tuple(
            RESTONIC_B_CONTROLS if remote_b else RESTONIC_A_CONTROLS
        )
        assert [spec.key for spec in controller.controller_button_specs] == (
            [RESTONIC_ZZZ_BUTTON_KEY] if remote_b else []
        )
        assert controller.supports_light_toggle_control is remote_b
        assert controller.supports_lights is remote_b
        assert controller.supports_preset_flat
        assert controller.supports_preset_zero_g
        assert not controller.supports_memory_presets
        assert controller.memory_slot_count == 0
        assert not controller.supports_memory_programming
        assert not controller.supports_preset_lounge
        assert not controller.supports_preset_tv
        assert not controller.supports_preset_anti_snore
        assert not controller.supports_stop_all
        assert not controller.supports_discrete_light_control
        assert not controller.auto_enable_massage
        assert not controller.supports_massage_toggle_control
        assert not controller.supports_massage_intensity_step_control
        assert not controller.supports_head_massage_toggle_control
        assert not controller.supports_foot_massage_toggle_control
        assert not controller.supports_head_massage_intensity_step_control
        assert not controller.supports_foot_massage_intensity_step_control
        assert not controller.supports_massage_mode_step_control
        assert not controller.supports_massage_off_control
        assert not controller.supports_massage_wave_direction_control
        assert not controller.supports_massage_intensity_preset_control
        assert controller.position_number_specs == ()
        assert not controller.requires_notification_channel


async def test_controls_absent_from_the_selected_remote_send_nothing(
    coordinator, mock_bleak_client: MagicMock
):
    remote_a = _restonic(coordinator, KEESON_VARIANT_RESTONIC_A)
    for action in (
        remote_a.lights_toggle,
        remote_a.restonic_zzz,
        remote_a.move_back_legs_up,
        lambda: remote_a.preset_memory(1),
        lambda: _restonic(coordinator, KEESON_VARIANT_RESTONIC_B).preset_memory(1),
    ):
        with pytest.raises(NotImplementedError):
            await action()
    for preset in (remote_a.preset_tv, remote_a.preset_anti_snore, remote_a.preset_lounge):
        await preset()
    mock_bleak_client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize(
    ("variant", "control", "duration_ms", "frame", "writes", "wait"),
    [
        (KEESON_VARIANT_RESTONIC_A, "zero_g", 250, "e5fe1600100000f6", 3, 0.05),
        (KEESON_VARIANT_RESTONIC_A, "head_up", 100, "e5fe160100000005", 1, 0.1),
        (KEESON_VARIANT_RESTONIC_B, "zero_g", 2000, "e5fe1600100000f6", 1, 2.0),
        (KEESON_VARIANT_RESTONIC_B, "back_legs_down", 300, "e5fe160a000000fc", 3, 0.1),
        (KEESON_VARIANT_RESTONIC_B, "zzz", 500, "e5fe160080000086", 1, 0.5),
        (KEESON_VARIANT_RESTONIC_B, "light", 100, "e5fe160000020004", 1, 0.1),
        (KEESON_VARIANT_RESTONIC_B, "flat", 1500, "e5fe1600000008fe", 1, 1.5),
    ],
)
async def test_hold_follows_the_touch_lifecycle(
    coordinator,
    mock_bleak_client: MagicMock,
    no_sleep,
    monkeypatch: pytest.MonkeyPatch,
    variant,
    control,
    duration_ms,
    frame,
    writes,
    wait,
):
    """Touch-down writes (repeating or once), the hold ends, then the zero frame +100 ms."""
    hold_wait = AsyncMock()
    monkeypatch.setattr(keeson, "_wait_unless_cancelled", hold_wait)
    await _restonic(coordinator, variant).hold_control(control, duration_ms)
    assert mock_bleak_client.write_gatt_char.await_args_list == (
        [_frame(frame)] * writes + [_frame(ZERO)]
    )
    assert hold_wait.await_args_list == [call(coordinator.cancel_command, pytest.approx(wait))]
    assert no_sleep.await_args_list == [call(0.1)] * writes


@pytest.mark.parametrize(
    ("variant", "control", "duration_ms"),
    [
        (KEESON_VARIANT_RESTONIC_A, "light", 1000),
        (KEESON_VARIANT_RESTONIC_A, "back_legs_up", 1000),
        (KEESON_VARIANT_RESTONIC_B, "tilt_up", 1000),
        (KEESON_VARIANT_RESTONIC_B, "flat", 99),
        (KEESON_VARIANT_RESTONIC_B, "flat", 60001),
    ],
)
async def test_hold_rejects_controls_and_durations_outside_the_remote(
    coordinator, mock_bleak_client: MagicMock, variant, control, duration_ms
):
    with pytest.raises(ValueError):
        await _restonic(coordinator, variant).hold_control(control, duration_ms)
    mock_bleak_client.write_gatt_char.assert_not_awaited()


async def test_hold_wait_ends_at_stop_without_a_real_timer():
    event = asyncio.Event()
    event.set()
    await asyncio.wait_for(keeson._wait_unless_cancelled(event, 60), 1)

    pending = asyncio.Event()
    asyncio.get_running_loop().call_soon(pending.set)
    await asyncio.wait_for(keeson._wait_unless_cancelled(pending, 60), 1)


async def test_profiles_are_selected_only_explicitly(coordinator):
    for name in (NAME, "base-i5.00000682", "base-i4"):
        auto = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_KEESON,
            protocol_variant="auto",
            client=coordinator.client,
            device_name=name,
        )
        assert isinstance(auto, KeesonController)
        assert auto._variant == KEESON_VARIANT_BASE

    for variant in (KEESON_VARIANT_RESTONIC_A, KEESON_VARIANT_RESTONIC_B):
        explicit = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_KEESON,
            protocol_variant=variant,
            client=coordinator.client,
            device_name="any name",
        )
        assert isinstance(explicit, KeesonController)
        assert explicit._variant == variant
        assert variant in KEESON_VARIANTS
        assert any(
            option["variant"] == variant for option in ACTUATOR_GROUPS["keeson"]["variants"] or ()
        )


def test_service_metadata_lists_every_held_control():
    root = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
    services = yaml.safe_load((root / "services.yaml").read_text())
    options = services["restonic_hold_control"]["fields"]["control"]["selector"]["select"]["options"]
    assert set(options) == set(RESTONIC_A_CONTROLS) | set(RESTONIC_B_CONTROLS)
    assert len(options) == len(set(options))


def _service_target(coordinator: AdjustableBedCoordinator, variant: str):
    controller = _restonic(coordinator, variant)
    controller.hold_control = AsyncMock()
    target = MagicMock(spec=AdjustableBedCoordinator)
    target.name = "Restonic"
    target.bed_type = BED_TYPE_KEESON
    target.entry = SimpleNamespace(data={})
    target.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    target.async_execute_controller_command = AsyncMock(side_effect=execute)
    return target, controller


@pytest.mark.parametrize(
    ("variant", "control", "error"),
    [
        (KEESON_VARIANT_RESTONIC_A, "zero_g", None),
        (KEESON_VARIANT_RESTONIC_B, "zzz", None),
        (KEESON_VARIANT_RESTONIC_A, "zzz", "does not support control 'zzz'"),
        (KEESON_VARIANT_BASE, "flat", "Restonic BT"),
    ],
)
async def test_hold_service_preflights_before_writing(
    hass: HomeAssistant, coordinator, variant, control, error
):
    await async_register_services(hass)
    target, controller = _service_target(coordinator, variant)
    data = {"device_id": "bed", "control": control, "duration": 1.5}
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(target, SIDE_BOTH)], []),
    ):
        if error:
            with pytest.raises(ServiceValidationError, match=error):
                await hass.services.async_call(
                    DOMAIN, "restonic_hold_control", data, blocking=True
                )
            target.async_execute_controller_command.assert_not_awaited()
            controller.hold_control.assert_not_awaited()
        else:
            await hass.services.async_call(DOMAIN, "restonic_hold_control", data, blocking=True)
            controller.hold_control.assert_awaited_once_with(control, 1500)


def _exists(hass: HomeAssistant, address: str, platform: str, key: str) -> bool:
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    return registry.async_get_entity_id(platform, DOMAIN, f"{address}_{key}") is not None


async def test_setup_exposes_each_remote_surface_and_retires_remote_b_controls(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_async_ble_device_from_address: MagicMock,
    enable_custom_integrations,
):
    """Remote B gets its extra controls; switching to remote A removes them."""
    mock_async_ble_device_from_address.return_value.name = NAME
    address = "AA:BB:CC:DD:EE:59"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: NAME,
            CONF_BED_TYPE: BED_TYPE_KEESON,
            CONF_PROTOCOL_VARIANT: KEESON_VARIANT_RESTONIC_B,
            CONF_MOTOR_COUNT: 4,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id=address,
        entry_id="restonic_setup_entry",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    remote_b_only = (
        ("cover", "back_legs"),
        ("button", "toggle_light"),
        ("button", RESTONIC_ZZZ_BUTTON_KEY),
    )
    never = (
        ("cover", "tilt"),
        ("cover", "lumbar"),
        ("button", "preset_memory_1"),
        ("button", "program_memory_1"),
        ("button", "preset_lounge"),
        ("button", "preset_tv"),
        ("button", "preset_anti_snore"),
        ("button", "massage_all_toggle"),
        ("button", "massage_head_up"),
        ("button", "massage_mode_step"),
        ("button", "massage_wave_next"),
        ("button", "stop"),
    )
    for platform, key in (
        ("cover", "head"),
        ("cover", "feet"),
        ("button", "preset_flat"),
        ("button", "preset_zero_g"),
        *remote_b_only,
    ):
        assert _exists(hass, address, platform, key), key
    for platform, key in never:
        assert not _exists(hass, address, platform, key), key

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_PROTOCOL_VARIANT: KEESON_VARIANT_RESTONIC_A}
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    for platform, key in remote_b_only + never:
        assert not _exists(hass, address, platform, key), key
    for platform, key in (("cover", "head"), ("cover", "feet"), ("button", "preset_zero_g")):
        assert _exists(hass, address, platform, key), key

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
