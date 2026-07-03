"""Tests for the DewertOkin DOT PROTOCOL controller (okin_dot)."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_dot import OkinDotController
from custom_components.adjustable_bed.beds.okin_uuid import (
    OKIN_UUID_REMOTES,
    OkinUuidComplexCommand,
    OkinUuidController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_DOT,
    BED_TYPE_OKIN_UUID,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
    OKIMAT_SERVICE_UUID,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_DOT_VARIANTS,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import refine_okin_dot_protocol_from_gatt

# The six DOT PROTOCOL remote codes (RF1058 / RF34 / RF6707 handsets).
DOT_RF1058_4MEM = "90167"
DOT_RF1058_SNORE_A = "91983"
DOT_RF1058_SNORE_B = "93558"
DOT_RF34_WHITE = "97450"
DOT_RF34_BLACK = "97544"
DOT_RF6707 = "98035"

_AFFIRM = b"affirm"


@dataclass
class _FakeCharacteristic:
    uuid: str
    properties: list[str]


class _FakeService:
    def __init__(self, uuid: str, characteristics: list[_FakeCharacteristic]) -> None:
        self.uuid = uuid
        self.characteristics = characteristics

    def get_characteristic(self, uuid: str) -> _FakeCharacteristic | None:
        uuid_lower = uuid.lower()
        for characteristic in self.characteristics:
            if characteristic.uuid.lower() == uuid_lower:
                return characteristic
        return None


def _nordic_uart_services() -> list[_FakeService]:
    return [
        _FakeService(
            NORDIC_UART_SERVICE_UUID,
            [_FakeCharacteristic(NORDIC_UART_WRITE_CHAR_UUID, ["write", "write-without-response"])],
        )
    ]


def _okimat_services() -> list[_FakeService]:
    return [
        _FakeService(
            OKIMAT_SERVICE_UUID,
            [_FakeCharacteristic(OKIMAT_WRITE_CHAR_UUID, ["write"])],
        ),
        *_nordic_uart_services(),
    ]


def _make_entry(
    hass: HomeAssistant,
    variant: str = DOT_RF34_WHITE,
    bed_type: str = BED_TYPE_OKIN_DOT,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin DOT Test Bed",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Okin DOT Test Bed",
            CONF_BED_TYPE: bed_type,
            CONF_PROTOCOL_VARIANT: variant,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id=f"okin_dot_test_entry_{variant}_{bed_type}",
    )
    entry.add_to_hass(hass)
    return entry


def _data_writes(mock_bleak_client: MagicMock) -> list:
    """Return write calls excluding the affirm handshake."""
    return [
        call
        for call in mock_bleak_client.write_gatt_char.call_args_list
        if call[0][1] != _AFFIRM
    ]


class TestOkinDotRemoteTable:
    """The generated DOT entries carry the authoritative backend keycodes."""

    @pytest.mark.parametrize("variant", list(OKIN_DOT_VARIANTS))
    def test_all_dot_variants_resolve(self, variant):
        """Every DOT dropdown code has a dot-flagged remote config."""
        if variant == VARIANT_AUTO:
            return
        remote = OKIN_UUID_REMOTES[variant]
        assert remote.dot is True
        assert remote.flat == 0x8000000
        # DOT light keys are hold-style per the backend (5s @ 100ms).
        assert remote.toggle_lights == OkinUuidComplexCommand(0x20000, 50, 100)

    @pytest.mark.parametrize(
        ("variant", "motors"),
        [
            # DOT motor bits are renumbered per handset (first pair 0x1/0x2,
            # second 0x4/0x8) but keep their section meaning.
            (DOT_RF1058_4MEM, {"head": (0x1, 0x2), "feet": (0x4, 0x8)}),
            (DOT_RF1058_SNORE_A, {"head": (0x1, 0x2), "feet": (0x4, 0x8)}),
            (DOT_RF1058_SNORE_B, {"head": (0x1, 0x2), "feet": (0x4, 0x8)}),
            (DOT_RF34_WHITE, {"back": (0x1, 0x2), "legs": (0x4, 0x8)}),
            (DOT_RF34_BLACK, {"back": (0x1, 0x2), "legs": (0x4, 0x8)}),
            (DOT_RF6707, {"head": (0x1, 0x2), "back": (0x4, 0x8)}),
        ],
    )
    def test_dot_motor_channels_are_section_mapped(self, variant, motors):
        """Each DOT code stores its motor keycodes under the real section fields."""
        remote = OKIN_UUID_REMOTES[variant]
        for axis in ("back", "legs", "head", "feet"):
            up = getattr(remote, f"{axis}_up")
            down = getattr(remote, f"{axis}_down")
            if axis in motors:
                assert (up, down) == motors[axis]
            else:
                assert up is None
                assert down is None

    def test_rf1058_4mem_extras(self):
        """RF1058 code 90167: 4 memories, quiet sleep, zero-g, massage, 5s save."""
        remote = OKIN_UUID_REMOTES[DOT_RF1058_4MEM]
        assert remote.memory_1 == 0x3000
        assert remote.memory_2 == 0x5000
        assert remote.memory_3 == 0x6000
        assert remote.memory_4 == 0x7000
        assert remote.memory_save == OkinUuidComplexCommand(0x10000, 25, 200)
        assert remote.zero_gravity == 0x1000
        assert remote.quiet_sleep == 0x4000
        assert remote.anti_snore is None
        assert remote.massage == {
            "head_up": 0x800,
            "head_down": 0x800000,
            "foot_up": 0x400,
            "foot_down": 0x1000000,
            "stop": 0x100,
            "wave": 0x10000000,
        }

    @pytest.mark.parametrize("variant", [DOT_RF1058_SNORE_A, DOT_RF1058_SNORE_B])
    def test_rf1058_snore_variants(self, variant):
        """RF1058 codes 91983/93558: 3 memories with anti-snore."""
        remote = OKIN_UUID_REMOTES[variant]
        assert remote.memory_1 == 0x2000
        assert remote.memory_2 == 0x8000
        assert remote.memory_3 == 0x3000
        assert remote.memory_4 is None
        assert remote.anti_snore == 0x4000
        assert remote.zero_gravity == 0x1000

    def test_rf34_memory_layout(self):
        """RF34 codes use the renumbered memory keycodes with a 2s save hold."""
        white = OKIN_UUID_REMOTES[DOT_RF34_WHITE]
        assert white.memory_1 == 0x10000
        assert white.memory_2 == 0x40000
        assert white.memory_save == OkinUuidComplexCommand(0x1F000, 10, 200)
        black = OKIN_UUID_REMOTES[DOT_RF34_BLACK]
        assert black.memory_save == OkinUuidComplexCommand(0x10000, 10, 200)

    def test_rf6707_is_motors_and_light_only(self):
        """RF6707 code 98035 exposes no memory or extras."""
        remote = OKIN_UUID_REMOTES[DOT_RF6707]
        assert remote.memory_1 is None
        assert remote.memory_save is None
        assert remote.zero_gravity is None
        assert remote.massage is None


class TestOkinDotController:
    """Test DOT transport behavior (framing, handshake, characteristic)."""

    async def test_control_characteristic_and_framing(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
    ):
        """DOT frames are 7 bytes: [0x05, 0x02, keycode BE, 0x00] on Nordic UART."""
        coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
        await coordinator.async_connect()

        controller = coordinator.controller
        assert isinstance(controller, OkinDotController)
        assert controller.control_characteristic_uuid == NORDIC_UART_WRITE_CHAR_UUID

        command = controller._build_command(0x8000000)
        assert command == bytes([0x05, 0x02, 0x08, 0x00, 0x00, 0x00, 0x00])

    async def test_variant_auto_defaults_to_97450(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
    ):
        """Auto variant defaults to the plain RF34 layout."""
        coordinator = AdjustableBedCoordinator(hass, _make_entry(hass, variant=VARIANT_AUTO))
        await coordinator.async_connect()

        assert coordinator.controller._variant == DOT_RF34_WHITE

    async def test_non_dot_variant_coerced_to_default(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
    ):
        """A rescued entry with a standard Okimat variant never drives DOT frames
        with Okimat keycodes; it falls back to the default DOT remote."""
        coordinator = AdjustableBedCoordinator(hass, _make_entry(hass, variant="82417"))
        await coordinator.async_connect()

        controller = coordinator.controller
        assert isinstance(controller, OkinDotController)
        assert controller._variant == DOT_RF34_WHITE
        assert controller._remote.dot is True

    async def test_memory_recall_is_short_press(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Memory recall is tap-to-recall: one frame + STOP, never a save-length
        stream (on 97544 recall and save even share keycode 0x10000)."""
        coordinator = AdjustableBedCoordinator(hass, _make_entry(hass, variant=DOT_RF34_BLACK))
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(1)

        writes = _data_writes(mock_bleak_client)
        assert [w[0][1] for w in writes] == [
            bytes([0x05, 0x02, 0x00, 0x01, 0x00, 0x00, 0x00]),
            bytes([0x05, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00]),
        ]

    async def test_quiet_sleep_drives_anti_snore_preset(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """90167's QuietSleep key (same 0x4000 slot as Snore) is exposed."""
        coordinator = AdjustableBedCoordinator(
            hass, _make_entry(hass, variant=DOT_RF1058_4MEM)
        )
        await coordinator.async_connect()

        controller = coordinator.controller
        assert controller.supports_preset_anti_snore is True
        await controller.preset_anti_snore()

        writes = _data_writes(mock_bleak_client)
        assert writes[0][0][1] == bytes([0x05, 0x02, 0x00, 0x00, 0x40, 0x00, 0x00])

    async def test_affirm_handshake_sent_once_per_connection(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """The FurniMove "affirm" marker precedes the first command only."""
        coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
        await coordinator.async_connect()

        controller = coordinator.controller
        await controller.write_command(controller._build_command(0x1))
        await controller.write_command(controller._build_command(0x2))

        calls = mock_bleak_client.write_gatt_char.call_args_list
        affirm_calls = [call for call in calls if call[0][1] == _AFFIRM]
        assert len(affirm_calls) == 1
        assert calls[0][0] == (NORDIC_UART_WRITE_CHAR_UUID, _AFFIRM)
        assert calls[0][1] == {"response": False}

    async def test_write_command_uses_nordic_uart_without_response(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Commands go to 6E400002 as write-without-response."""
        coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
        await coordinator.async_connect()

        controller = coordinator.controller
        command = controller._build_command(0)
        await controller.write_command(command)

        data_write = _data_writes(mock_bleak_client)[-1]
        assert data_write[0] == (NORDIC_UART_WRITE_CHAR_UUID, command)
        assert data_write[1] == {"response": False}

    async def test_move_back_up_frames_and_stop(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Motor moves stream DOT frames and end with the keycode-0 stop."""
        coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
        await coordinator.async_connect()

        await coordinator.controller.move_back_up()

        writes = _data_writes(mock_bleak_client)
        assert writes, "expected motor frames"
        assert writes[0][0][1] == bytes([0x05, 0x02, 0x00, 0x00, 0x00, 0x01, 0x00])
        assert writes[-1][0][1] == bytes([0x05, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00])

    async def test_rf1058_exposes_head_and_feet_covers(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """RF1058 handsets get Head and Feet controls driving 0x1/0x2 and 0x4/0x8."""
        coordinator = AdjustableBedCoordinator(
            hass, _make_entry(hass, variant=DOT_RF1058_4MEM)
        )
        await coordinator.async_connect()

        controller = coordinator.controller
        assert [spec.key for spec in controller.motor_control_specs] == ["head", "feet"]

        await controller.move_head_up()
        writes = _data_writes(mock_bleak_client)
        assert writes[0][0][1] == bytes([0x05, 0x02, 0x00, 0x00, 0x00, 0x01, 0x00])

    async def test_rf34_exposes_back_and_legs_covers(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
    ):
        """RF34 handsets keep the standard Back and Legs controls."""
        coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
        await coordinator.async_connect()

        specs = coordinator.controller.motor_control_specs
        assert [spec.key for spec in specs] == ["back", "legs"]

    async def test_preset_flat_uses_dot_flat_keycode(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Flat preset streams the DOT Flat keycode 0x08000000."""
        coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        writes = _data_writes(mock_bleak_client)
        assert writes[0][0][1] == bytes([0x05, 0x02, 0x08, 0x00, 0x00, 0x00, 0x00])
        # Stop follows the stream.
        assert writes[-1][0][1] == bytes([0x05, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00])

    async def test_anti_snore_preset(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """RF1058 snore codes expose and stream the anti-snore preset."""
        coordinator = AdjustableBedCoordinator(
            hass, _make_entry(hass, variant=DOT_RF1058_SNORE_B)
        )
        await coordinator.async_connect()

        controller = coordinator.controller
        assert controller.supports_preset_anti_snore is True
        await controller.preset_anti_snore()

        writes = _data_writes(mock_bleak_client)
        assert writes[0][0][1] == bytes([0x05, 0x02, 0x00, 0x00, 0x40, 0x00, 0x00])

    async def test_anti_snore_not_advertised_on_rf34(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
    ):
        """RF34 codes have no anti-snore key."""
        coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_anti_snore is False

    async def test_massage_uses_backend_keycodes(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """RF1058 massage keys are sent as DOT frames."""
        coordinator = AdjustableBedCoordinator(
            hass, _make_entry(hass, variant=DOT_RF1058_4MEM)
        )
        await coordinator.async_connect()

        controller = coordinator.controller
        assert controller.supports_massage is True
        await controller.massage_head_up()

        writes = _data_writes(mock_bleak_client)
        assert writes[-1][0][1] == bytes([0x05, 0x02, 0x00, 0x00, 0x08, 0x00, 0x00])

    async def test_memory_preset_uses_renumbered_keycodes(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """RF34 memory 2 uses keycode 0x40000, not the Okimat 0x2000."""
        coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(2)

        writes = _data_writes(mock_bleak_client)
        assert writes[0][0][1] == bytes([0x05, 0x02, 0x00, 0x04, 0x00, 0x00, 0x00])

    async def test_no_position_feedback(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """DOT boxes never subscribe to the Okimat position characteristic."""
        coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
        await coordinator.async_connect()

        await coordinator.controller.start_notify(None)
        await coordinator.controller.read_positions()
        await coordinator.controller.stop_notify()

        mock_bleak_client.start_notify.assert_not_called()
        mock_bleak_client.read_gatt_char.assert_not_called()


class TestOkinDotFactorySelection:
    """Test controller_factory routing for DOT boxes."""

    async def test_okin_dot_bed_type_selects_dot_controller(
        self,
        hass: HomeAssistant,
        mock_bleak_client: MagicMock,
    ):
        """The okin_dot bed type always builds the DOT controller."""
        coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
        mock_bleak_client.services = []

        controller = await create_controller(
            coordinator,
            BED_TYPE_OKIN_DOT,
            DOT_RF1058_4MEM,
            mock_bleak_client,
        )

        assert isinstance(controller, OkinDotController)
        assert controller._variant == DOT_RF1058_4MEM

    async def test_okin_uuid_entry_on_dot_box_is_rescued(
        self,
        hass: HomeAssistant,
        mock_bleak_client: MagicMock,
    ):
        """An Okimat entry whose box only has Nordic UART gets the DOT transport."""
        coordinator = AdjustableBedCoordinator(
            hass, _make_entry(hass, variant=DOT_RF34_WHITE, bed_type=BED_TYPE_OKIN_UUID)
        )
        mock_bleak_client.services = _nordic_uart_services()

        controller = await create_controller(
            coordinator,
            BED_TYPE_OKIN_UUID,
            DOT_RF34_WHITE,
            mock_bleak_client,
        )

        assert isinstance(controller, OkinDotController)
        assert controller._variant == DOT_RF34_WHITE

    async def test_okin_uuid_entry_on_okimat_box_keeps_uuid_controller(
        self,
        hass: HomeAssistant,
        mock_bleak_client: MagicMock,
    ):
        """A box with the Okin 62741525 characteristic keeps the standard controller."""
        coordinator = AdjustableBedCoordinator(
            hass, _make_entry(hass, variant="82417", bed_type=BED_TYPE_OKIN_UUID)
        )
        mock_bleak_client.services = _okimat_services()

        controller = await create_controller(
            coordinator,
            BED_TYPE_OKIN_UUID,
            "82417",
            mock_bleak_client,
        )

        assert isinstance(controller, OkinUuidController)
        assert not isinstance(controller, OkinDotController)


class TestOkinDotRefinement:
    """Runtime bed-type promotion for Okimat entries on DOT boxes."""

    def test_okimat_entry_promoted_on_dot_gatt(self):
        """Okimat/Okin UUID entries on a Nordic-UART-only box become okin_dot."""
        assert (
            refine_okin_dot_protocol_from_gatt(BED_TYPE_OKIN_UUID, _nordic_uart_services())
            == BED_TYPE_OKIN_DOT
        )

    def test_real_okimat_box_is_not_demoted(self):
        """A box with the Okin 62741525 characteristic keeps its bed type."""
        assert (
            refine_okin_dot_protocol_from_gatt(BED_TYPE_OKIN_UUID, _okimat_services())
            == BED_TYPE_OKIN_UUID
        )

    def test_empty_services_are_ignored(self):
        """No GATT snapshot means no promotion."""
        assert refine_okin_dot_protocol_from_gatt(BED_TYPE_OKIN_UUID, []) == BED_TYPE_OKIN_UUID

    def test_unrelated_bed_types_are_untouched(self):
        """Only Okimat-family entries are eligible for DOT promotion."""
        assert (
            refine_okin_dot_protocol_from_gatt("richmat", _nordic_uart_services()) == "richmat"
        )
