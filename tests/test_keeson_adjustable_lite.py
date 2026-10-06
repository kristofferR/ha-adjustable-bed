"""Adjustable Lite (com.keeson.adjustablelite 1.0.2) app profile.

Every packet literal comes from the accepted clean-room report (row051); the
parser inputs are its synthetic branch vectors, not captured traffic.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.keeson import (
    STATE_ADJUSTABLE_LITE_LIGHT,
    STATE_ADJUSTABLE_LITE_MASSAGE_TIMER,
    STATE_ADJUSTABLE_LITE_MASSAGE_TIMER_RAW,
    KeesonController,
    parse_adjustable_lite_status,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_KEESON,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    KEESON_KSBT_CHAR_UUID,
    KEESON_VARIANT_ADJUSTABLE_LITE,
    KEESON_VARIANT_KSBT,
    NORDIC_UART_READ_CHAR_UUID,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

KSBT01C = "KSBT01C000015046"
KSBT03C = "KSBT03C000015046"

Action = Callable[[KeesonController], Awaitable[None]]

# (action, app UI id, frame) shared by both remotes.
COMMON_VECTORS: list[tuple[Action, str, str]] = [
    (lambda c: c.preset_memory(1), "iv_m", "040200010000"),
    (lambda c: c.preset_memory(2), "iv_read", "040200002000"),
    (lambda c: c.preset_memory(3), "iv_tv", "040200004000"),
    (lambda c: c.move_head_up(), "v_1", "040200000001"),
    (lambda c: c.move_legs_up(), "v_2", "040200000004"),
    (lambda c: c.preset_flat(), "v_4", "040208000000"),
    (lambda c: c.move_head_down(), "v_6", "040200000002"),
    (lambda c: c.move_legs_down(), "v_7", "040200000008"),
    (lambda c: c.lights_toggle(), "v_light", "040200020000"),
    (lambda c: c.preset_zero_g(), "v_zg", "040200001000"),
]
# Controls only the KSBT03C remote has.
KSBT03C_VECTORS: list[tuple[Action, str, str]] = [
    (lambda c: c.massage_mode_step(), "v_10", "040200000200"),
    (lambda c: c.preset_anti_snore(), "v_11", "040200008000"),
    (lambda c: c.massage_foot_up(), "v_12", "040200000400"),
    (lambda c: c.massage_foot_down(), "v_13", "040201000000"),
    (lambda c: c.massage_head_up(), "v_8", "040200000800"),
    (lambda c: c.massage_head_down(), "v_9", "040200800000"),
]
MOVEMENT_IDS = {"v_1", "v_2", "v_6", "v_7"}

# (length, big-endian bytes 3-4, byte 12) -> (light, KSBT03C indicator)
PARSER_VECTORS = [
    (12, 0, 1, None, None),
    (13, 0, 0, False, 0),
    (13, 1, 1, True, 10),
    (13, 600, 2, False, 10),
    (13, 601, 1, True, 20),
    (13, 1200, 0, False, 20),
    (13, 1201, 1, True, 30),
    (13, 65535, 255, False, 30),
]


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=KSBT03C,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:51",
            CONF_NAME: KSBT03C,
            CONF_BED_TYPE: BED_TYPE_KEESON,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:51",
        entry_id="adjustable_lite_entry",
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


def _lite(coordinator: AdjustableBedCoordinator, name: str | None) -> KeesonController:
    return KeesonController(coordinator, variant=KEESON_VARIANT_ADJUSTABLE_LITE, device_name=name)


def _frame(hex_bytes: str, response: bool = True):
    return call(KEESON_KSBT_CHAR_UUID, bytes.fromhex(hex_bytes), response=response)


@pytest.mark.parametrize(
    ("name", "vectors"),
    [(KSBT01C, COMMON_VECTORS), (KSBT03C, COMMON_VECTORS + KSBT03C_VECTORS)],
    ids=["KSBT01C", "KSBT03C"],
)
async def test_every_app_control_sends_its_literal_frame(
    coordinator, mock_bleak_client: MagicMock, no_sleep, name, vectors
):
    """Each remote control sends exactly the app frame, with no release frame."""
    controller = _lite(coordinator, name)
    for action, ui_id, frame in vectors:
        mock_bleak_client.write_gatt_char.reset_mock()
        await action(controller)
        writes = 4 if ui_id in MOVEMENT_IDS else 1
        assert mock_bleak_client.write_gatt_char.await_args_list == [_frame(frame)] * writes, ui_id


async def test_status_query_is_the_two_byte_literal(coordinator, mock_bleak_client: MagicMock):
    controller = _lite(coordinator, KSBT01C)
    assert controller.diagnostic_poll_interval == 0.5
    await controller.async_refresh_diagnostics()
    mock_bleak_client.write_gatt_char.assert_awaited_once_with(
        KEESON_KSBT_CHAR_UUID, bytes.fromhex("00b0"), response=True
    )


async def test_hold_repeats_every_300_ms_and_release_sends_nothing(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    controller = _lite(coordinator, KSBT01C)
    assert controller.motor_pulse_settings() == (4, 300)
    await controller.move_head_up()
    assert mock_bleak_client.write_gatt_char.await_args_list == [_frame("040200000001")] * 4
    assert no_sleep.await_args_list == [call(0.3)] * 3

    mock_bleak_client.write_gatt_char.reset_mock()
    await controller.stop_all()
    mock_bleak_client.write_gatt_char.assert_not_awaited()


async def test_cancellation_ends_the_refresh_without_a_frame(
    coordinator, mock_bleak_client: MagicMock, monkeypatch: pytest.MonkeyPatch
):
    controller = _lite(coordinator, KSBT03C)

    async def cancel(_delay: float) -> None:
        coordinator.cancel_command.set()

    monkeypatch.setattr("custom_components.adjustable_bed.beds.base.asyncio.sleep", cancel)
    await controller.move_legs_down()
    assert mock_bleak_client.write_gatt_char.await_args_list == [_frame("040200000008")]


async def test_custom_cadence_is_preserved(coordinator):
    coordinator._motor_pulse_count = 7
    coordinator._motor_pulse_delay_ms = 150
    assert _lite(coordinator, KSBT01C).motor_pulse_settings() == (7, 150)


@pytest.mark.parametrize(
    ("properties", "response"),
    [(["write", "write-without-response"], False), (["write"], True)],
)
async def test_write_type_mirrors_android_default(
    coordinator, mock_bleak_client: MagicMock, properties, response
):
    """The app never sets a write type, so Android's characteristic default applies."""
    mock_bleak_client.services = [
        SimpleNamespace(
            uuid="6e400001-b5a3-f393-e0a9-e50e24dcca9e",
            characteristics=[SimpleNamespace(uuid=KEESON_KSBT_CHAR_UUID, properties=properties)],
        )
    ]
    controller = _lite(coordinator, KSBT01C)
    assert controller.control_characteristic_uuid == KEESON_KSBT_CHAR_UUID
    await controller.preset_flat()
    assert mock_bleak_client.write_gatt_char.await_args_list == [_frame("040208000000", response)]


@pytest.mark.parametrize(("length", "raw", "light_byte", "light", "indicator"), PARSER_VECTORS)
def test_parser_branch_vectors(length, raw, light_byte, light, indicator):
    data = bytearray(length)
    data[3:5] = raw.to_bytes(2, "big")
    if length > 12:
        data[12] = light_byte
    ksbt01c = parse_adjustable_lite_status(bytes(data), massage_timer=False)
    ksbt03c = parse_adjustable_lite_status(bytes(data), massage_timer=True)
    if light is None:
        assert ksbt01c is None
        assert ksbt03c is None
        return
    assert ksbt01c == {STATE_ADJUSTABLE_LITE_LIGHT: light}
    assert ksbt03c == {
        STATE_ADJUSTABLE_LITE_LIGHT: light,
        STATE_ADJUSTABLE_LITE_MASSAGE_TIMER_RAW: raw,
        STATE_ADJUSTABLE_LITE_MASSAGE_TIMER: indicator,
    }


async def test_notifications_publish_state_and_session_end_clears_it(
    coordinator, mock_bleak_client: MagicMock
):
    controller = _lite(coordinator, KSBT03C)
    assert controller.requires_notification_channel
    await controller.start_notify(None)
    mock_bleak_client.start_notify.assert_awaited_once()
    assert mock_bleak_client.start_notify.await_args.args[0] == NORDIC_UART_READ_CHAR_UUID

    payload = bytearray(13)
    payload[3:5] = (900).to_bytes(2, "big")
    payload[12] = 1
    controller._on_notification(MagicMock(), payload)
    assert coordinator.controller_state[STATE_ADJUSTABLE_LITE_LIGHT] is True
    assert coordinator.controller_state[STATE_ADJUSTABLE_LITE_MASSAGE_TIMER] == 20
    assert coordinator.controller_state[STATE_ADJUSTABLE_LITE_MASSAGE_TIMER_RAW] == 900

    controller._on_notification(MagicMock(), bytearray(12))
    assert coordinator.controller_state[STATE_ADJUSTABLE_LITE_LIGHT] is True

    controller.invalidate_diagnostics()
    assert coordinator.controller_state[STATE_ADJUSTABLE_LITE_LIGHT] is None
    assert coordinator.controller_state[STATE_ADJUSTABLE_LITE_MASSAGE_TIMER] is None


async def test_failed_subscription_does_not_block_control(
    coordinator, mock_bleak_client: MagicMock
):
    """The app gates controls only on the connection, never on the CCCD write."""
    mock_bleak_client.start_notify.side_effect = BleakError("no CCCD")
    controller = _lite(coordinator, KSBT01C)
    await controller.start_notify(None)
    await controller.preset_zero_g()
    assert mock_bleak_client.write_gatt_char.await_args_list == [_frame("040200001000")]


async def test_ksbt01c_remote_ignores_timer_bytes(coordinator):
    controller = _lite(coordinator, KSBT01C)
    payload = bytearray(13)
    payload[3:5] = (1500).to_bytes(2, "big")
    controller._on_notification(MagicMock(), payload)
    assert coordinator.controller_state[STATE_ADJUSTABLE_LITE_LIGHT] is False
    assert STATE_ADJUSTABLE_LITE_MASSAGE_TIMER not in coordinator.controller_state


async def test_remote_capabilities(coordinator):
    """The app exposes two zones, three recall slots and KSBT03C-only massage."""
    coordinator._motor_count = 4
    # Without a live BLE name the configured entry name (KSBT03C...) decides.
    for name, ksbt03c in ((KSBT01C, False), (KSBT03C, True), (None, True)):
        controller = _lite(coordinator, name)
        assert [spec.key for spec in controller.motor_control_specs] == ["head", "feet"]
        assert controller.protocol_diagnostics == {
            "adjustable_lite_remote": "KSBT03C" if ksbt03c else "KSBT01C"
        }
        assert controller.memory_slot_count == 3
        assert not controller.supports_memory_programming
        assert not controller.supports_preset_lounge
        assert not controller.supports_preset_tv
        assert not controller.supports_stop_all
        assert controller.supports_light_toggle_control
        assert not controller.supports_discrete_light_control
        assert not controller.supports_light_color_control
        assert not controller.supports_massage_timer
        assert controller.position_number_specs == ()
        assert controller.supports_preset_anti_snore is ksbt03c
        assert controller.auto_enable_massage is ksbt03c
        assert controller.supports_head_massage_intensity_step_control is ksbt03c
        assert controller.supports_foot_massage_intensity_step_control is ksbt03c
        assert controller.supports_massage_mode_step_control is ksbt03c
        assert controller.massage_mode_step_is_timer
        assert not controller.supports_massage_toggle_control
        assert not controller.supports_massage_intensity_step_control
        assert not controller.supports_head_massage_toggle_control
        assert not controller.supports_foot_massage_toggle_control
        assert not controller.supports_massage_off_control
        assert [spec.key for spec in controller.controller_state_binary_sensor_specs] == [
            STATE_ADJUSTABLE_LITE_LIGHT
        ]
        assert [spec.key for spec in controller.controller_state_sensor_specs] == (
            [STATE_ADJUSTABLE_LITE_MASSAGE_TIMER] if ksbt03c else []
        )


async def test_ksbt03c_token_is_case_sensitive_like_the_app(coordinator):
    assert not _lite(coordinator, "ksbt03c000015046").supports_preset_anti_snore
    assert _lite(coordinator, "X" + KSBT03C).supports_preset_anti_snore


@pytest.mark.parametrize("name", [KSBT01C, "KSSF05C201000322"])
async def test_explicit_massage_option_restores_proven_controls_without_remapping_remote(
    coordinator, name, mock_bleak_client, no_sleep
):
    """Issue #669: an app name fallback must not discard configured hardware features."""
    from custom_components.adjustable_bed.button import BUTTON_DESCRIPTIONS, _should_add_button

    coordinator._has_massage = True
    controller = _lite(coordinator, name)
    massage_buttons = {
        description.key: description
        for description in BUTTON_DESCRIPTIONS
        if description.requires_massage and _should_add_button(description, controller, True)
    }
    assert set(massage_buttons) == {
        "massage_head_up", "massage_head_down", "massage_foot_up", "massage_foot_down",
        "massage_mode_step",
    }
    for key, frame in (
        ("massage_head_up", "040200000800"),
        ("massage_head_down", "040200800000"),
        ("massage_foot_up", "040200000400"),
        ("massage_foot_down", "040201000000"),
        ("massage_mode_step", "040200000200"),
    ):
        mock_bleak_client.write_gatt_char.reset_mock()
        press = massage_buttons[key].press_fn
        assert press is not None
        await press(controller)
        assert mock_bleak_client.write_gatt_char.call_args_list == [_frame(frame)]
    # The option is affirmative hardware evidence, not a KSBT03C identity or parser proof.
    assert controller.protocol_diagnostics == {"adjustable_lite_remote": "KSBT01C"}
    assert not controller.auto_enable_massage
    assert not controller.supports_preset_anti_snore
    assert controller.controller_state_sensor_specs == ()


async def test_other_keeson_profiles_drop_adjustable_lite_state_entities(coordinator):
    controller = KeesonController(coordinator, variant=KEESON_VARIANT_KSBT, device_name=KSBT03C)
    assert controller.controller_state_binary_sensor_specs == ()
    assert controller.controller_state_sensor_specs == ()
    assert controller.stale_controller_state_binary_sensor_entity_keys == {
        STATE_ADJUSTABLE_LITE_LIGHT
    }
    assert controller.stale_controller_state_sensor_entity_keys == {
        STATE_ADJUSTABLE_LITE_MASSAGE_TIMER
    }
    assert controller.diagnostic_poll_interval is None
    assert not controller.requires_notification_channel


async def test_profile_is_selected_only_explicitly(coordinator):
    auto = await create_controller(
        coordinator=coordinator,
        bed_type=BED_TYPE_KEESON,
        protocol_variant="auto",
        client=coordinator.client,
        device_name=KSBT01C,
    )
    assert isinstance(auto, KeesonController)
    assert auto._variant == KEESON_VARIANT_KSBT

    explicit = await create_controller(
        coordinator=coordinator,
        bed_type=BED_TYPE_KEESON,
        protocol_variant=KEESON_VARIANT_ADJUSTABLE_LITE,
        client=coordinator.client,
        device_name=KSBT03C,
    )
    assert isinstance(explicit, KeesonController)
    assert explicit._variant == KEESON_VARIANT_ADJUSTABLE_LITE
    assert explicit.supports_preset_anti_snore


@pytest.mark.parametrize("name", ["Bed KSBT01C000015046", "XKSBT03CR00015046"])
async def test_auto_keeps_legacy_routing_for_embedded_identities(coordinator, name):
    """Upgrade safety: Auto still routes only KSBT-prefixed names to KSBT frames.

    A mid-name KSBT03CR must never get six-byte 0x04 frames, and existing Auto
    entries whose names never matched keep their Base frames. Users of the app
    with such names select the explicit profile.
    """
    controller = await create_controller(
        coordinator=coordinator,
        bed_type=BED_TYPE_KEESON,
        protocol_variant="auto",
        client=coordinator.client,
        device_name=name,
    )
    assert isinstance(controller, KeesonController)
    assert controller._variant == "base"


async def test_unknown_memory_slot_sends_nothing(coordinator, mock_bleak_client: MagicMock):
    await _lite(coordinator, KSBT01C).preset_memory(4)
    mock_bleak_client.write_gatt_char.assert_not_awaited()


async def test_status_query_is_not_suppressed_by_a_pending_stop(
    coordinator, mock_bleak_client: MagicMock
):
    coordinator.cancel_command.set()
    await _lite(coordinator, KSBT01C).async_refresh_diagnostics()
    mock_bleak_client.write_gatt_char.assert_awaited_once()


async def test_setup_exposes_only_the_app_surface(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_async_ble_device_from_address: MagicMock,
    enable_custom_integrations,
):
    """A KSBT03C entry on the profile gets the app controls and nothing invented."""
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.const import CONF_PROTOCOL_VARIANT

    mock_async_ble_device_from_address.return_value.name = KSBT03C
    address = "AA:BB:CC:DD:EE:52"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=KSBT03C,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: KSBT03C,
            CONF_BED_TYPE: BED_TYPE_KEESON,
            CONF_PROTOCOL_VARIANT: KEESON_VARIANT_ADJUSTABLE_LITE,
            CONF_MOTOR_COUNT: 3,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id=address,
        entry_id="adjustable_lite_setup_entry",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)

    def exists(platform: str, key: str) -> bool:
        return registry.async_get_entity_id(platform, DOMAIN, f"{address}_{key}") is not None

    for key in ("head", "feet"):
        assert exists("cover", key)
    assert not exists("cover", "lumbar")
    for key in (
        "preset_flat",
        "preset_zero_g",
        "preset_anti_snore",
        "preset_memory_1",
        "preset_memory_2",
        "preset_memory_3",
        "toggle_light",
        "massage_head_up",
        "massage_head_down",
        "massage_foot_up",
        "massage_foot_down",
        "massage_mode_step",
    ):
        assert exists("button", key), key
    for key in (
        "preset_lounge",
        "preset_tv",
        "preset_memory_4",
        "program_memory_1",
        "massage_all_toggle",
        "massage_all_up",
        "massage_head_toggle",
        "massage_all_off",
    ):
        assert not exists("button", key), key
    assert exists("binary_sensor", STATE_ADJUSTABLE_LITE_LIGHT)
    assert exists("sensor", STATE_ADJUSTABLE_LITE_MASSAGE_TIMER)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def _keeson_entry(
    hass: HomeAssistant, address: str, name: str, variant: str, motor_count: int
) -> MockConfigEntry:
    from custom_components.adjustable_bed.const import CONF_PROTOCOL_VARIANT

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: name,
            CONF_BED_TYPE: BED_TYPE_KEESON,
            CONF_PROTOCOL_VARIANT: variant,
            CONF_MOTOR_COUNT: motor_count,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id=address,
        entry_id=f"keeson_{address.replace(':', '')}",
    )
    entry.add_to_hass(hass)
    return entry


async def _switch_variant(hass: HomeAssistant, entry: MockConfigEntry, variant: str) -> None:
    from custom_components.adjustable_bed.const import CONF_PROTOCOL_VARIANT

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_PROTOCOL_VARIANT: variant}
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


def _exists(hass: HomeAssistant, address: str, platform: str, key: str) -> bool:
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    return registry.async_get_entity_id(platform, DOMAIN, f"{address}_{key}") is not None


async def test_switching_to_the_profile_removes_generic_ksbt_entities(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_async_ble_device_from_address: MagicMock,
    enable_custom_integrations,
):
    mock_async_ble_device_from_address.return_value.name = KSBT01C
    address = "AA:BB:CC:DD:EE:53"
    entry = _keeson_entry(hass, address, KSBT01C, KEESON_VARIANT_KSBT, 4)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for platform, key in (
        ("cover", "tilt"),
        ("cover", "lumbar"),
        ("button", "preset_lounge"),
        ("button", "preset_tv"),
    ):
        assert _exists(hass, address, platform, key), key

    await _switch_variant(hass, entry, KEESON_VARIANT_ADJUSTABLE_LITE)

    for platform, key in (
        ("cover", "tilt"),
        ("cover", "lumbar"),
        ("button", "preset_lounge"),
        ("button", "preset_tv"),
    ):
        assert not _exists(hass, address, platform, key), key
    assert _exists(hass, address, "binary_sensor", STATE_ADJUSTABLE_LITE_LIGHT)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_switching_to_lite_retains_configured_massage_entity_identities(
    hass, mock_coordinator_connected, mock_async_ble_device_from_address,
    enable_custom_integrations,
):
    from homeassistant.helpers import entity_registry as er

    name = "KSSF05C201000322"
    mock_async_ble_device_from_address.return_value.name = name
    address = "AA:BB:CC:DD:EE:69"
    entry = _keeson_entry(hass, address, name, KEESON_VARIANT_KSBT, 2)
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_HAS_MASSAGE: True})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    keys = ("massage_head_up", "massage_head_down", "massage_foot_up", "massage_foot_down", "massage_mode_step")
    before = {}
    for key in keys:
        entity_id = registry.async_get_entity_id("button", DOMAIN, f"{address}_{key}")
        assert entity_id is not None
        entity = registry.async_get(entity_id)
        assert entity is not None
        before[key] = (entity.id, entity.entity_id, entity.device_id)
    await _switch_variant(hass, entry, KEESON_VARIANT_ADJUSTABLE_LITE)
    for key in keys:
        entity_id = registry.async_get_entity_id("button", DOMAIN, f"{address}_{key}")
        assert entity_id is not None
        entity = registry.async_get(entity_id)
        assert entity is not None
        assert (entity.id, entity.entity_id, entity.device_id) == before[key]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_switching_away_from_the_profile_removes_its_state_entities(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_async_ble_device_from_address: MagicMock,
    enable_custom_integrations,
):
    mock_async_ble_device_from_address.return_value.name = KSBT03C
    address = "AA:BB:CC:DD:EE:54"
    entry = _keeson_entry(hass, address, KSBT03C, KEESON_VARIANT_ADJUSTABLE_LITE, 2)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _exists(hass, address, "binary_sensor", STATE_ADJUSTABLE_LITE_LIGHT)
    assert _exists(hass, address, "sensor", STATE_ADJUSTABLE_LITE_MASSAGE_TIMER)

    await _switch_variant(hass, entry, KEESON_VARIANT_KSBT)

    assert not _exists(hass, address, "binary_sensor", STATE_ADJUSTABLE_LITE_LIGHT)
    assert not _exists(hass, address, "sensor", STATE_ADJUSTABLE_LITE_MASSAGE_TIMER)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_other_bed_types_remove_adjustable_lite_state_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_coordinator_connected,
    enable_custom_integrations,
):
    """Changing bed type off Keeson must not strand the profile's state entities."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    address = mock_config_entry.data[CONF_ADDRESS]
    for platform, key in (
        ("binary_sensor", STATE_ADJUSTABLE_LITE_LIGHT),
        ("sensor", STATE_ADJUSTABLE_LITE_MASSAGE_TIMER),
    ):
        registry.async_get_or_create(
            platform, DOMAIN, f"{address}_{key}", config_entry=mock_config_entry
        )

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert not _exists(hass, address, "binary_sensor", STATE_ADJUSTABLE_LITE_LIGHT)
    assert not _exists(hass, address, "sensor", STATE_ADJUSTABLE_LITE_MASSAGE_TIMER)
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
