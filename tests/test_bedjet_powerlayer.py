"""Tests for the BedJet PowerLayer adjustable frame controller.

Status frames and the movement watchdog timings asserted here come from a
PowerLayer owner's captures in natekspencer/ha-bedjet#49.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.bedjet_powerlayer import (
    _FOOT_ANGLE_TABLE,
    _HEAD_ANGLE_TABLE,
    BedJetPowerLayerController,
    PowerLayerButton,
    raw_count_to_angle,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_BEDJET_POWERLAYER,
    BEDJET_ADVERTISED_SERVICE_UUID,
    BEDJET_POWERLAYER_COMMAND_CHAR_UUID,
    BEDJET_POWERLAYER_FOOT_MAX_ANGLE,
    BEDJET_POWERLAYER_HEAD_MAX_ANGLE,
    BEDJET_POWERLAYER_STATUS_CHAR_UUID,
    CONF_BED_TYPE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type

# Captured 20-byte status frame with the frame flat: bytes 12-13 hold the head
# count (78, which the remote showed as 1 degree) and bytes 14-15 the foot count.
FRAME_FLAT = bytes.fromhex("014716010010012a00000008004e00000001ffff")


def _frame(head_raw: int, foot_raw: int) -> bytes:
    """Return a captured status frame with the two axis counts replaced."""
    return (
        FRAME_FLAT[:12]
        + head_raw.to_bytes(2, "big")
        + foot_raw.to_bytes(2, "big")
        + FRAME_FLAT[16:]
    )


# Extremes reached in the captures: head swept 78..3362, foot swept 0..1704.
FRAME_HEAD_MAX = _frame(3362, 0)
FRAME_FOOT_MAX = _frame(104, 1704)


@pytest.fixture
def powerlayer_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a mock config entry for a PowerLayer frame."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PowerLayer Test Frame",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "BEDJET_BF",
            CONF_BED_TYPE: BED_TYPE_BEDJET_POWERLAYER,
            CONF_MOTOR_COUNT: 2,
            CONF_PREFERRED_ADAPTER: "auto",
            CONF_MOTOR_PULSE_COUNT: 10,
            CONF_MOTOR_PULSE_DELAY_MS: 0,
        },
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="powerlayer_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


def _written(client: MagicMock) -> list[bytes]:
    """Return every payload written to the command characteristic."""
    return [
        bytes(call[0][1])
        for call in client.write_gatt_char.call_args_list
        if str(call[0][0]) == BEDJET_POWERLAYER_COMMAND_CHAR_UUID
    ]


class TestPowerLayerCommandEncoding:
    """Commands are a BUTTON opcode followed by a remote key."""

    @pytest.mark.parametrize(
        ("button", "expected"),
        [
            (PowerLayerButton.HEAD_UP, b"\x01\x02"),
            (PowerLayerButton.HEAD_DOWN, b"\x01\x03"),
            (PowerLayerButton.FOOT_UP, b"\x01\x04"),
            (PowerLayerButton.FOOT_DOWN, b"\x01\x05"),
            (PowerLayerButton.FLAT, b"\x01\x10"),
            (PowerLayerButton.SNORE, b"\x01\x11"),
            (PowerLayerButton.ZERO_G, b"\x01\x12"),
            (PowerLayerButton.TV, b"\x01\x13"),
            (PowerLayerButton.M1, b"\x01\x20"),
            (PowerLayerButton.M2, b"\x01\x21"),
            (PowerLayerButton.M3, b"\x01\x22"),
        ],
    )
    def test_build_command(self, button: int, expected: bytes) -> None:
        """Every key is encoded as a two-byte BUTTON command."""
        controller = BedJetPowerLayerController(MagicMock())

        assert controller._build_command(button) == expected


class TestPowerLayerAngleCalibration:
    """Raw actuator counts map onto the remote's degree readout."""

    def test_flat_head_count_reads_one_degree(self) -> None:
        """The captured flat frame rested at raw 78, which the remote showed as 1."""
        assert raw_count_to_angle(78, _HEAD_ANGLE_TABLE) == pytest.approx(1.0, abs=0.5)

    def test_zero_foot_count_reads_zero_degrees(self) -> None:
        """The foot axis reported 0 degrees when flat."""
        assert raw_count_to_angle(0, _FOOT_ANGLE_TABLE) == 0

    def test_counts_below_the_table_clamp_to_zero(self) -> None:
        """A count under the first calibration point must not go negative."""
        assert raw_count_to_angle(0, _HEAD_ANGLE_TABLE) == 0

    def test_counts_above_the_table_clamp_to_the_maximum(self) -> None:
        """Counts past the last point stay at the frame's travel limit."""
        assert raw_count_to_angle(99999, _HEAD_ANGLE_TABLE) == BEDJET_POWERLAYER_HEAD_MAX_ANGLE
        assert raw_count_to_angle(99999, _FOOT_ANGLE_TABLE) == BEDJET_POWERLAYER_FOOT_MAX_ANGLE

    def test_interpolates_between_points(self) -> None:
        """A count halfway between two points lands between their degrees."""
        # 119 -> 1 degree and 154 -> 2 degrees, so the midpoint is about 1.5.
        assert raw_count_to_angle(136, _HEAD_ANGLE_TABLE) == pytest.approx(1.5, abs=0.1)

    def test_tables_are_monotonic(self) -> None:
        """Interpolation requires strictly increasing counts."""
        for table in (_HEAD_ANGLE_TABLE, _FOOT_ANGLE_TABLE):
            counts = [count for count, _ in table]
            assert counts == sorted(counts)
            assert len(set(counts)) == len(counts)


class TestPowerLayerStatusParsing:
    """The 20-byte status frame carries both axis positions."""

    def test_head_and_foot_are_decoded_from_their_own_offsets(self) -> None:
        """Bytes 12-13 are the head count and bytes 14-15 the foot count."""
        controller = BedJetPowerLayerController(MagicMock())
        updates: dict[str, float] = {}
        controller._notify_callback = lambda key, angle: updates.__setitem__(key, angle)

        controller._handle_status_notification(None, bytearray(FRAME_FOOT_MAX))

        # The foot capture topped out at raw 1704, which the remote showed as 46.
        assert updates["legs"] == pytest.approx(46.0, abs=0.5)
        # Its head axis sat parked at raw 104 throughout, just off flat.
        assert updates["back"] == pytest.approx(0.8, abs=0.4)

    def test_flat_frame_reports_both_axes_near_zero(self) -> None:
        """The captured flat frame is 1 degree of head and 0 of foot."""
        controller = BedJetPowerLayerController(MagicMock())
        updates: dict[str, float] = {}
        controller._notify_callback = lambda key, angle: updates.__setitem__(key, angle)

        controller._handle_status_notification(None, bytearray(FRAME_FLAT))

        assert updates["back"] == pytest.approx(1.0, abs=0.5)
        assert updates["legs"] == 0

    def test_head_max_frame_reaches_the_travel_limit(self) -> None:
        """The highest captured head count maps to the frame's top angle."""
        controller = BedJetPowerLayerController(MagicMock())
        updates: dict[str, float] = {}
        controller._notify_callback = lambda key, angle: updates.__setitem__(key, angle)

        controller._handle_status_notification(None, bytearray(FRAME_HEAD_MAX))

        assert updates["back"] == pytest.approx(72.0, abs=1.0)

    def test_short_frame_is_ignored(self) -> None:
        """A truncated frame must not emit a bogus position."""
        controller = BedJetPowerLayerController(MagicMock())
        updates: list[tuple[str, float]] = []
        controller._notify_callback = lambda key, angle: updates.append((key, angle))

        controller._handle_status_notification(None, bytearray(FRAME_FLAT[:10]))

        assert updates == []


class TestPowerLayerMovement:
    """Movement holds the key and releases by letting the refresh end."""

    async def test_movement_repeats_the_key_and_sends_no_stop(
        self,
        hass: HomeAssistant,
        powerlayer_entry: MockConfigEntry,
        mock_coordinator_connected: None,
    ) -> None:
        """The frame has no STOP frame, so only the movement key may be written."""
        coordinator = AdjustableBedCoordinator(hass, powerlayer_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_back_up()

        payloads = _written(coordinator._client)
        assert payloads == [b"\x01\x02"] * 10

    async def test_foot_movement_uses_the_foot_key(
        self,
        hass: HomeAssistant,
        powerlayer_entry: MockConfigEntry,
        mock_coordinator_connected: None,
    ) -> None:
        """Lowering the foot writes the foot-down key."""
        coordinator = AdjustableBedCoordinator(hass, powerlayer_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_down()

        assert set(_written(coordinator._client)) == {b"\x01\x05"}

    async def test_stop_writes_nothing(
        self,
        hass: HomeAssistant,
        powerlayer_entry: MockConfigEntry,
        mock_coordinator_connected: None,
    ) -> None:
        """Releasing must not invent a command the protocol does not define."""
        coordinator = AdjustableBedCoordinator(hass, powerlayer_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()
        await coordinator.controller.move_back_stop()

        assert _written(coordinator._client) == []

    async def test_auto_stops_on_idle(
        self,
        hass: HomeAssistant,
        powerlayer_entry: MockConfigEntry,
        mock_coordinator_connected: None,
    ) -> None:
        """The watchdog release is declared so shared code skips a STOP write."""
        coordinator = AdjustableBedCoordinator(hass, powerlayer_entry)
        await coordinator.async_connect()

        assert coordinator.controller.auto_stops_on_idle is True
        assert coordinator.controller.supports_stop_all is False


class TestPowerLayerPresets:
    """Presets and memory recalls latch on a single write."""

    @pytest.mark.parametrize(
        ("method", "expected"),
        [
            ("preset_flat", b"\x01\x10"),
            ("preset_zero_g", b"\x01\x12"),
            ("preset_anti_snore", b"\x01\x11"),
            ("preset_tv", b"\x01\x13"),
        ],
    )
    async def test_preset_is_sent_once(
        self,
        hass: HomeAssistant,
        powerlayer_entry: MockConfigEntry,
        mock_coordinator_connected: None,
        method: str,
        expected: bytes,
    ) -> None:
        """Repeating a latched preset would re-trigger it mid-travel."""
        coordinator = AdjustableBedCoordinator(hass, powerlayer_entry)
        await coordinator.async_connect()

        await getattr(coordinator.controller, method)()

        assert _written(coordinator._client) == [expected]

    @pytest.mark.parametrize(
        ("slot", "expected"),
        [(1, b"\x01\x20"), (2, b"\x01\x21"), (3, b"\x01\x22")],
    )
    async def test_memory_recall(
        self,
        hass: HomeAssistant,
        powerlayer_entry: MockConfigEntry,
        mock_coordinator_connected: None,
        slot: int,
        expected: bytes,
    ) -> None:
        """Each remote memory key recalls its stored position."""
        coordinator = AdjustableBedCoordinator(hass, powerlayer_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(slot)

        assert _written(coordinator._client) == [expected]

    async def test_memory_recall_rejects_unknown_slot(
        self,
        hass: HomeAssistant,
        powerlayer_entry: MockConfigEntry,
        mock_coordinator_connected: None,
    ) -> None:
        """The remote only stores three slots."""
        coordinator = AdjustableBedCoordinator(hass, powerlayer_entry)
        await coordinator.async_connect()

        with pytest.raises(ValueError, match="1-3"):
            await coordinator.controller.preset_memory(4)

    async def test_programming_is_rejected(
        self,
        hass: HomeAssistant,
        powerlayer_entry: MockConfigEntry,
        mock_coordinator_connected: None,
    ) -> None:
        """No save opcode is known, so programming must fail loudly."""
        coordinator = AdjustableBedCoordinator(hass, powerlayer_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_programming is False
        with pytest.raises(ValueError, match="physical remote"):
            await coordinator.controller.program_memory(1)


class TestPowerLayerTravelLimits:
    """Sliders and validation use the frame's own travel, not the generic default."""

    async def test_position_sliders_use_frame_travel(
        self,
        hass: HomeAssistant,
        powerlayer_entry: MockConfigEntry,
        mock_coordinator_connected: None,
    ) -> None:
        """Head reaches 73 degrees and foot 47, past the generic 68/45."""
        coordinator = AdjustableBedCoordinator(hass, powerlayer_entry)
        await coordinator.async_connect()

        specs = {spec.position_key: spec for spec in coordinator.controller.position_number_specs}

        assert specs["back"].native_max_value == BEDJET_POWERLAYER_HEAD_MAX_ANGLE
        assert specs["legs"].native_max_value == BEDJET_POWERLAYER_FOOT_MAX_ANGLE

    async def test_coordinator_validation_matches_the_sliders(
        self,
        hass: HomeAssistant,
        powerlayer_entry: MockConfigEntry,
        mock_coordinator_connected: None,
    ) -> None:
        """set_position validation must not reject a reachable angle."""
        coordinator = AdjustableBedCoordinator(hass, powerlayer_entry)

        assert coordinator.get_max_angle("back") == BEDJET_POWERLAYER_HEAD_MAX_ANGLE
        assert coordinator.get_max_angle("legs") == BEDJET_POWERLAYER_FOOT_MAX_ANGLE


class TestPowerLayerDetection:
    """Only the frame may be claimed, never the BedJet climate blower."""

    def _service_info(self, name: str, service_uuids: list[str]) -> MagicMock:
        info = MagicMock()
        info.name = name
        info.address = "AA:BB:CC:DD:EE:FF"
        info.service_uuids = service_uuids
        info.manufacturer_data = {}
        info.service_data = {}
        info.rssi = -50
        return info

    def test_frame_is_detected_by_name(self) -> None:
        """The advertised BEDJET_BF name identifies the frame."""
        detected = detect_bed_type(
            self._service_info("BEDJET_BF", [BEDJET_ADVERTISED_SERVICE_UUID])
        )

        assert detected == BED_TYPE_BEDJET_POWERLAYER

    def test_renamed_frame_is_detected_by_name(self) -> None:
        """A frame renamed from the remote still advertises a BEDFRM name."""
        detected = detect_bed_type(self._service_info("BEDFRM-1234", []))

        assert detected == BED_TYPE_BEDJET_POWERLAYER

    def test_climate_unit_is_not_claimed(self) -> None:
        """The blower shares the advertised service but is not a bed."""
        detected = detect_bed_type(
            self._service_info("BEDJET_V3", [BEDJET_ADVERTISED_SERVICE_UUID])
        )

        assert detected != BED_TYPE_BEDJET_POWERLAYER


class TestPowerLayerNotifications:
    """Position feedback is delivered over the status characteristic."""

    async def test_status_notifications_drive_position_data(
        self,
        hass: HomeAssistant,
        powerlayer_entry: MockConfigEntry,
        mock_coordinator_connected: None,
    ) -> None:
        """A captured frame pushed by the bed updates the coordinator."""
        coordinator = AdjustableBedCoordinator(hass, powerlayer_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        updates: dict[str, float] = {}
        await controller.start_notify(lambda key, angle: updates.__setitem__(key, angle))
        coordinator._client.start_notify.assert_awaited()
        handler = coordinator._client.start_notify.call_args[0][1]

        handler(None, bytearray(FRAME_FOOT_MAX))

        assert updates["legs"] == pytest.approx(46.0, abs=0.5)

    async def test_notifications_use_the_status_characteristic(
        self,
        hass: HomeAssistant,
        powerlayer_entry: MockConfigEntry,
        mock_coordinator_connected: None,
    ) -> None:
        """Subscribing to the wrong characteristic is how the upstream beta failed."""
        coordinator = AdjustableBedCoordinator(hass, powerlayer_entry)
        await coordinator.async_connect()

        await coordinator.controller.start_notify(lambda key, angle: None)

        assert (
            str(coordinator._client.start_notify.call_args[0][0])
            == BEDJET_POWERLAYER_STATUS_CHAR_UUID
        )
