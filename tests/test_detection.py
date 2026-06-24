"""Tests for bed type detection logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.adjustable_bed.const import (
    BED_TYPE_BEDTECH,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_COOLBASE,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JENSEN,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LIMOSS,
    BED_TYPE_LINAK,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_NECTAR,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_64BIT,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_OKIN_CB35,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REMACRO,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERTA,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SOLACE,
    BED_TYPE_SUTA,
    BED_TYPE_SVANE,
    BED_TYPE_TIMOTION_AHF,
    BED_TYPE_VIBRADORM,
    BEDTECH_SERVICE_UUID,
    COMFORT_MOTION_LIERDA3_SERVICE_UUID,
    DEVICE_INFO_SERVICE_UUID,
    DEWERTOKIN_RF_GATEWAY_SERVICE_UUID,
    DEWERTOKIN_RF_GATEWAY_WRITE_CHAR_UUID,
    JENSEN_SERVICE_UUID,
    KAIDI_DISCOVERY_SERVICE_UUID,
    KAIDI_MESH_SERVICE_UUID,
    KEESON_BASE_SERVICE_UUID,
    KEESON_FALLBACK_GATT_PAIRS,
    KEESON_JSON_SERVICE_UUID,
    LEGGETT_GEN2_SERVICE_UUID,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_OKIN,
    LIMOSS_SERVICE_UUID,
    LINAK_CONTROL_SERVICE_UUID,
    MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID,
    MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID,
    MALOUF_NEW_OKIN_WRITE_CHAR_UUID,
    MANUFACTURER_ID_DEWERTOKIN,
    MANUFACTURER_ID_OKIN,
    MANUFACTURER_ID_VIBRADORM,
    NORDIC_DFU_SERVICE_UUID,
    NORDIC_UART_SERVICE_UUID,
    OCTO_STAR2_SERVICE_UUID,
    OKIMAT_SERVICE_UUID,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
    OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
    REMACRO_SERVICE_UUID,
    REVERIE_NIGHTSTAND_SERVICE_UUID,
    REVERIE_SERVICE_UUID,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    RICHMAT_WILINKE_W5_SERVICE_UUID,
    SLEEP_NUMBER_MCR_SERVICE_UUID,
    SLEEP_NUMBER_SERVICE_UUID,
    SOLACE_SERVICE_UUID,
    SUTA_SERVICE_UUID,
    SVANE_HEAD_SERVICE_UUID,
    TIMOTION_AHF_SERVICE_UUID,
    VIBRADORM_SECONDARY_SERVICE_UUID,
    VIBRADORM_SERVICE_UUID,
)
from custom_components.adjustable_bed.detection import (
    BED_TYPE_DISPLAY_NAMES,
    detect_bed_type,
    detect_bed_type_detailed,
    detect_bed_type_from_gatt_services,
    detect_richmat_remote_from_name,
    refine_malouf_protocol_from_gatt,
    refine_nordic_uart_protocol_from_device_info,
    refine_okin_shared_uuid_protocol_from_gatt,
)


def _make_service_info(
    name: str = "Test Device",
    address: str = "AA:BB:CC:DD:EE:FF",
    service_uuids: list[str] | None = None,
    manufacturer_data: dict[int, bytes] | None = None,
) -> MagicMock:
    """Create a mock BluetoothServiceInfoBleak."""
    service_info = MagicMock()
    service_info.name = name
    service_info.address = address
    service_info.service_uuids = service_uuids or []
    service_info.manufacturer_data = manufacturer_data or {}
    service_info.rssi = -60
    return service_info


class TestDetectBedTypeByServiceUUID:
    """Test detection by unique service UUIDs."""

    def test_detect_linak_by_uuid(self):
        """Test Linak detection by control service UUID."""
        service_info = _make_service_info(
            name="Linak Bed",
            service_uuids=[LINAK_CONTROL_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_LINAK

    def test_detect_jensen_by_uuid(self):
        """Test Jensen detection by unique service UUID."""
        service_info = _make_service_info(
            name="JMC400",
            service_uuids=[JENSEN_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_JENSEN

    def test_detect_keeson_json_by_uuid(self):
        """Test Keeson JSON/A00A detection by unique service UUID."""
        service_info = _make_service_info(
            name="Juna Sleep Bed",
            service_uuids=[KEESON_JSON_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_KEESON
        assert result.confidence == 1.0
        assert "uuid:keeson_json" in result.signals

    def test_detect_sleep_number_by_uuid(self):
        """Sleep Number should detect from its unique Fuzion service UUID."""
        service_info = _make_service_info(
            name="Smart bed 0074E7",
            service_uuids=[SLEEP_NUMBER_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_SLEEP_NUMBER
        assert result.confidence == 1.0
        assert "uuid:sleep_number" in result.signals

    def test_sleep_number_has_human_display_name(self):
        """Sleep Number should appear with a readable label in selectors."""
        assert BED_TYPE_DISPLAY_NAMES[BED_TYPE_SLEEP_NUMBER] == "Sleep Number Climate 360 / FlexFit"

    def test_detect_sleep_number_mcr_by_uuid(self):
        """Older Sleep Number BAM/MCR beds should detect from their UART service UUID."""
        service_info = _make_service_info(
            name="64:DB:A0:07:DD:02",
            service_uuids=[SLEEP_NUMBER_MCR_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_SLEEP_NUMBER_MCR
        assert result.confidence == 1.0
        assert "uuid:sleep_number_mcr" in result.signals

    def test_sleep_number_mcr_has_human_display_name(self):
        """Older Sleep Number BAM/MCR beds should appear with a readable label."""
        assert (
            BED_TYPE_DISPLAY_NAMES[BED_TYPE_SLEEP_NUMBER_MCR]
            == "Sleep Number 360 / i8 FlexFit (BAM/MCR)"
        )

    def test_detect_kaidi_by_manufacturer_data_only(self):
        """Test Kaidi detection by manufacturer data alone (no UUID/name needed)."""
        service_info = _make_service_info(
            name="Unknown",
            service_uuids=[],
            manufacturer_data={
                0xFFFF: bytes.fromhex("c0ff0278563412ffeeddccbbaa0000810100a004030201")
            },
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_KAIDI
        assert result.confidence == 0.9
        assert "manufacturer_payload:kaidi_type_2" in result.signals

    def test_detect_kaidi_with_ffc0_uuid(self):
        """Test Kaidi detection with FFC0 UUID gives higher confidence."""
        service_info = _make_service_info(
            name="Mouselet",
            service_uuids=[KAIDI_DISCOVERY_SERVICE_UUID],
            manufacturer_data={
                0xFFFF: bytes.fromhex("c0ff0278563412ffeeddccbbaa0000810100a004030201")
            },
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_KAIDI
        assert result.confidence == 0.95
        assert "uuid:kaidi" in result.signals
        assert "name:kaidi" in result.signals

    def test_detect_kaidi_with_mesh_uuid(self):
        """Test Kaidi detection with mesh service UUID gives higher confidence."""
        service_info = _make_service_info(
            name="Unknown",
            service_uuids=[KAIDI_MESH_SERVICE_UUID],
            manufacturer_data={
                0xFFFF: bytes.fromhex("c0ff0278563412ffeeddccbbaa0000810100a004030201")
            },
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_KAIDI
        assert result.confidence == 0.95
        assert "uuid:kaidi" in result.signals

    def test_detect_kaidi_mouselet_not_excluded_by_generic_mouse_filter(self):
        """Valid Kaidi manufacturer data should bypass the generic mouse exclusion."""
        service_info = _make_service_info(
            name="Mouselet",
            service_uuids=[],
            manufacturer_data={
                0xFFFF: bytes.fromhex("c0ff025e270000e55d547fc5ec0200882004a101000000")
            },
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_KAIDI
        assert not any(signal == "excluded:mouse" for signal in result.signals)

    def test_detect_vibradorm_by_uuid(self):
        """Test Vibradorm detection by unique service UUID."""
        service_info = _make_service_info(
            name="VMAT123",
            service_uuids=[VIBRADORM_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_VIBRADORM

    def test_detect_vibradorm_by_secondary_uuid(self):
        """Test Vibradorm detection by secondary VMAT service UUID."""
        service_info = _make_service_info(
            name="VMAT533",
            service_uuids=[VIBRADORM_SECONDARY_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_VIBRADORM

    def test_detect_svane_by_uuid(self):
        """Test Svane detection by head service UUID."""
        service_info = _make_service_info(
            name="Svane Bed",
            service_uuids=[SVANE_HEAD_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_SVANE

    def test_detect_remacro_by_uuid(self):
        """Test Remacro detection by unique service UUID."""
        service_info = _make_service_info(
            name="CheersSleep",
            service_uuids=[REMACRO_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_REMACRO

    def test_detect_malouf_new_okin_by_uuid(self):
        """Test Malouf NEW_OKIN detection by advertised UUID."""
        service_info = _make_service_info(
            name="Malouf Bed",
            service_uuids=[MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_MALOUF_NEW_OKIN

    def test_detect_lucid_l600_btcb_as_malouf_legacy(self):
        """Lucid L600 OKIN-BLE/BTCB beacons use the FFE5 Malouf protocol."""
        service_info = _make_service_info(
            name="OKIN-BLE00017786",
            service_uuids=[MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID],
            manufacturer_data={3: b"BTCB.03"},
        )

        result = detect_bed_type_detailed(service_info)

        assert result.bed_type == BED_TYPE_MALOUF_LEGACY_OKIN
        assert result.confidence == 0.9
        assert "name:okin_ble" in result.signals
        assert "manufacturer_payload:btcb" in result.signals
        assert result.ambiguous_types == [BED_TYPE_MALOUF_NEW_OKIN]

    def test_detect_leggett_gen2_by_uuid(self):
        """Test Leggett Gen2 detection by unique service UUID."""
        service_info = _make_service_info(
            name="Leggett Bed",
            service_uuids=[LEGGETT_GEN2_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_LEGGETT_GEN2

    def test_detect_leggett_gen2_by_manufacturer_data(self):
        """LP Comfort Connect advertises no UUID, only mfr data (company 0x092D,
        'XP'/'CP' payload prefix) — detect it from that (issue #385)."""
        # Real-device payload from the support bundle: "XP" + 05 00 00 00.
        service_info = _make_service_info(
            name="Smart Bed 22D8",
            service_uuids=[],
            manufacturer_data={0x092D: bytes.fromhex("585005000000")},
        )
        assert detect_bed_type(service_info) == BED_TYPE_LEGGETT_GEN2

        # "CP" prefix is also accepted.
        cp = _make_service_info(
            name="Smart Bed", manufacturer_data={0x092D: b"CP\x00\x00"}
        )
        assert detect_bed_type(cp) == BED_TYPE_LEGGETT_GEN2

        # Same company id but an unrelated payload must NOT match.
        other = _make_service_info(
            name="Smart Bed", manufacturer_data={0x092D: b"ZZ\x00\x00"}
        )
        assert detect_bed_type(other) != BED_TYPE_LEGGETT_GEN2

    def test_detect_reverie_nightstand_by_uuid(self):
        """Test Reverie Nightstand detection by unique service UUID."""
        service_info = _make_service_info(
            name="Reverie Nightstand",
            service_uuids=[REVERIE_NIGHTSTAND_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_REVERIE_NIGHTSTAND

    def test_detect_reverie_by_uuid(self):
        """Test Reverie detection by service UUID."""
        service_info = _make_service_info(
            name="Reverie Bed",
            service_uuids=[REVERIE_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_REVERIE

    def test_detect_octo_star2_by_uuid(self):
        """Test Octo Star2 detection by unique service UUID."""
        service_info = _make_service_info(
            name="Star2 Bed",
            service_uuids=[OCTO_STAR2_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_OCTO

    def test_detect_okin_cb35_by_star35_name_and_nordic_uart(self):
        """Star35* plus Nordic UART should detect as CB35 with high confidence."""
        service_info = _make_service_info(
            name="Star352201011800",
            service_uuids=[NORDIC_UART_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_OKIN_CB35
        assert result.confidence == 0.95
        assert "uuid:nordic_uart" in result.signals
        assert "star_digits:35" in result.signals
        assert not result.ambiguous_types

    def test_detect_sleepys_box25_by_star25_name_and_nordic_uart(self):
        """Star25* plus Nordic UART should detect as BOX25 with high confidence."""
        service_info = _make_service_info(
            name="Star254202079996",
            service_uuids=[NORDIC_UART_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_SLEEPYS_BOX25
        assert result.confidence == 0.95
        assert "uuid:nordic_uart" in result.signals
        assert "star_digits:25" in result.signals
        assert not result.ambiguous_types

    def test_detect_star_unknown_digits_is_ambiguous(self):
        """Star with unknown digits plus Nordic UART should be ambiguous."""
        service_info = _make_service_info(
            name="Star991234567890",
            service_uuids=[NORDIC_UART_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_OKIN_CB35
        assert result.confidence == 0.65
        assert result.ambiguous_types == [BED_TYPE_SLEEPYS_BOX25]

    def test_detect_suta_by_fff0_uuid_and_name(self):
        """Test SUTA detection by FFF0 UUID + SUTA name pattern."""
        service_info = _make_service_info(
            name="SUTA-B803",
            service_uuids=[SUTA_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_SUTA
        assert result.confidence == 0.9

    def test_detect_comfort_motion_lierda3_by_uuid(self):
        """Test Comfort Motion detection by Lierda3 FE60 service UUID."""
        service_info = _make_service_info(
            name="DreaMOTION",
            service_uuids=[COMFORT_MOTION_LIERDA3_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_COMFORT_MOTION

    def test_detect_limoss_by_ffe0_uuid_and_name(self):
        """Test Limoss detection by FFE0 UUID + Limoss name pattern."""
        service_info = _make_service_info(
            name="LIMOSS Remote",
            service_uuids=[LIMOSS_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_LIMOSS
        assert result.confidence == 0.9


class TestDetectBedTypeByNamePattern:
    """Test detection by device name patterns."""

    def test_detect_jensen_by_name_jmc(self):
        """Test Jensen detection by JMC prefix."""
        service_info = _make_service_info(name="jmc400")
        assert detect_bed_type(service_info) == BED_TYPE_JENSEN

    def test_detect_jensen_by_name_jmc_uppercase(self):
        """Test Jensen detection by JMC prefix (uppercase)."""
        service_info = _make_service_info(name="JMC300")
        assert detect_bed_type(service_info) == BED_TYPE_JENSEN

    def test_detect_vibradorm_by_name_vmat(self):
        """Test Vibradorm detection by VMAT prefix."""
        service_info = _make_service_info(name="VMAT1234")
        assert detect_bed_type(service_info) == BED_TYPE_VIBRADORM

    def test_detect_vibradorm_by_name_vmat_lowercase(self):
        """Test Vibradorm detection by vmat prefix (lowercase)."""
        service_info = _make_service_info(name="vmat5678")
        assert detect_bed_type(service_info) == BED_TYPE_VIBRADORM

    def test_detect_svane_by_name(self):
        """Test Svane detection by 'Svane Bed' name pattern."""
        service_info = _make_service_info(name="Svane Bed Living Room")
        assert detect_bed_type(service_info) == BED_TYPE_SVANE

    def test_detect_motosleep_by_name_hhc(self):
        """Test MotoSleep detection by HHC prefix."""
        service_info = _make_service_info(name="hhc1234")
        assert detect_bed_type(service_info) == BED_TYPE_MOTOSLEEP

    def test_detect_motosleep_by_name_hhc_uppercase(self):
        """Test MotoSleep detection by HHC prefix (uppercase)."""
        service_info = _make_service_info(name="HHC5678ABCD")
        assert detect_bed_type(service_info) == BED_TYPE_MOTOSLEEP

    @pytest.mark.parametrize(
        ("name", "service_uuids"),
        [
            ("OKIN-Receiver", []),
            ("OKIN - Receiver", []),
            ("OKIN - Receiver", [DEVICE_INFO_SERVICE_UUID]),
        ],
    )
    def test_detect_okin_receiver_before_pairing(self, name: str, service_uuids: list[str]):
        """OKIN receiver modules can require pairing before bed service UUIDs are visible."""
        service_info = _make_service_info(name=name, service_uuids=service_uuids)
        result = detect_bed_type_detailed(service_info)

        assert result.bed_type == BED_TYPE_OKIN_UUID
        assert result.confidence == 0.6
        assert "name:okin_receiver" in result.signals
        assert result.requires_characteristic_check is True

    def test_okin_receiver_with_okin_manufacturer_data_uses_cb24_fallback(self):
        """OKIN manufacturer ID should win over the receiver-name shortcut."""
        service_info = _make_service_info(
            name="OKIN - Receiver",
            service_uuids=[],
            manufacturer_data={MANUFACTURER_ID_OKIN: b"\x01\x02\x03"},
        )
        result = detect_bed_type_detailed(service_info)

        assert result.bed_type == BED_TYPE_OKIN_CB24
        assert result.confidence == 0.7
        assert result.manufacturer_id == MANUFACTURER_ID_OKIN
        assert f"manufacturer_id:{MANUFACTURER_ID_OKIN}" in result.signals

    def test_detect_star_name_only_is_ambiguous(self):
        """Star* without Nordic UART should remain a low-confidence ambiguous match."""
        service_info = _make_service_info(name="Star352201011800")
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_OKIN_CB35
        assert result.confidence == 0.3
        assert result.ambiguous_types == [BED_TYPE_SLEEPYS_BOX25, BED_TYPE_OCTO]

    def test_detect_star_short_name_is_ambiguous(self):
        """Short Star name (no digits to parse) should be ambiguous."""
        service_info = _make_service_info(
            name="Star",
            service_uuids=[NORDIC_UART_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_OKIN_CB35
        assert result.confidence == 0.65
        assert result.ambiguous_types == [BED_TYPE_SLEEPYS_BOX25]

    def test_detect_timotion_ahf_by_name(self):
        """Test TiMOTION AHF detection by AHF prefix."""
        service_info = _make_service_info(
            name="AHF-1234",
            service_uuids=[TIMOTION_AHF_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_TIMOTION_AHF
        assert result.confidence == 0.9

    def test_detect_suta_by_name_without_uuid(self):
        """Test SUTA fallback detection by name when UUID is missing."""
        service_info = _make_service_info(name="SUTA-B207", service_uuids=[])
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_SUTA
        assert result.confidence == 0.3

    def test_skip_suta_accessory_subtypes(self):
        """Test SUTA accessory/mattress subtypes are excluded from bed detection."""
        service_info = _make_service_info(
            name="SUTA-MOON",
            service_uuids=[SOLACE_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type is None
        assert "name:suta_accessory" in result.signals

    def test_detect_ergomotion_by_name(self):
        """Test Ergomotion detection by name pattern."""
        service_info = _make_service_info(name="Ergomotion Bed")
        assert detect_bed_type(service_info) == BED_TYPE_ERGOMOTION

    def test_detect_ergomotion_by_name_ergo(self):
        """Test Ergomotion detection by 'ergo' prefix."""
        service_info = _make_service_info(name="Ergo Smart Base")
        assert detect_bed_type(service_info) == BED_TYPE_ERGOMOTION

    def test_detect_ergomotion_by_serta_i_prefix(self):
        """Test Ergomotion detection by Serta-i prefix (Serta-branded ErgoMotion)."""
        service_info = _make_service_info(name="Serta-i490350")
        assert detect_bed_type(service_info) == BED_TYPE_ERGOMOTION

    def test_detect_keeson_by_name_base_i4(self):
        """Test Keeson detection by base-i4 prefix."""
        service_info = _make_service_info(name="base-i4.00002574")
        assert detect_bed_type(service_info) == BED_TYPE_KEESON

    def test_detect_coolbase_by_name_base_i5(self):
        """Test Cool Base detection by base-i5 prefix.

        Cool Base is a Keeson BaseI5 variant with additional fan control.
        """
        service_info = _make_service_info(name="base-i5.00000682")
        assert detect_bed_type(service_info) == BED_TYPE_COOLBASE

    def test_detect_keeson_by_name_ksbt(self):
        """Test Keeson detection by KSBT prefix."""
        service_info = _make_service_info(name="KSBT03C000015046")
        assert detect_bed_type(service_info) == BED_TYPE_KEESON

    def test_detect_keeson_by_name_ore(self):
        """Test Keeson detection by ORE- prefix (Dynasty/INNOVA beds)."""
        service_info = _make_service_info(name="ORE-ac2170000d")
        assert detect_bed_type(service_info) == BED_TYPE_KEESON

    def test_detect_keeson_sino_by_okin_ble_name_and_fallback_uuid(self):
        """Test BetterLiving-style OKIN-BLE names resolve to Keeson (Sino path)."""
        fallback_service_uuid = KEESON_FALLBACK_GATT_PAIRS[0][0]
        service_info = _make_service_info(
            name="OKIN-BLE00000",
            service_uuids=[fallback_service_uuid],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_KEESON
        assert result.confidence == 0.9

    def test_detect_serta_by_name(self):
        """Test Serta detection by name pattern."""
        service_info = _make_service_info(name="Serta Motion Perfect")
        assert detect_bed_type(service_info) == BED_TYPE_SERTA

    def test_detect_serta_by_motion_perfect(self):
        """Test Serta detection by 'motion perfect' in name."""
        service_info = _make_service_info(name="Motion Perfect III")
        assert detect_bed_type(service_info) == BED_TYPE_SERTA

    def test_detect_linak_by_name_pattern(self):
        """Test Linak detection by 'Bed XXXX' name pattern."""
        service_info = _make_service_info(name="Bed 1696")
        assert detect_bed_type(service_info) == BED_TYPE_LINAK

    def test_detect_mattressfirm_by_iflex_name(self):
        """Test Mattress Firm detection by iFlex name."""
        service_info = _make_service_info(name="iFlex Base")
        assert detect_bed_type(service_info) == BED_TYPE_MATTRESSFIRM

    def test_detect_richmat_by_name_qrrm(self):
        """Test Richmat detection by QRRM name pattern."""
        service_info = _make_service_info(name="QRRM157052")
        assert detect_bed_type(service_info) == BED_TYPE_RICHMAT

    def test_detect_richmat_by_name_sleep_function(self):
        """Test Richmat detection by Sleep Function 2.0 name."""
        service_info = _make_service_info(name="Sleep Function 2.0")
        assert detect_bed_type(service_info) == BED_TYPE_RICHMAT

    def test_detect_limoss_by_name_pattern(self):
        """Test Limoss detection by name pattern without UUID."""
        service_info = _make_service_info(name="Stawett Remote")
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_LIMOSS
        assert result.confidence == 0.3


class TestDetectBedTypeByManufacturerData:
    """Test detection by manufacturer data."""

    def test_detect_dewertokin_by_manufacturer_id(self):
        """Test DewertOkin detection by Company ID 1643."""
        service_info = _make_service_info(
            name="Unknown Device",
            manufacturer_data={MANUFACTURER_ID_DEWERTOKIN: b"\x01\x02\x03"},
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_DEWERTOKIN
        assert result.confidence == 0.95
        assert result.manufacturer_id == MANUFACTURER_ID_DEWERTOKIN

    def test_detect_vibradorm_by_manufacturer_id(self):
        """Test Vibradorm detection by Company ID 944."""
        service_info = _make_service_info(
            name="Unknown Device",
            manufacturer_data={MANUFACTURER_ID_VIBRADORM: b"\x04\x05\x06"},
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_VIBRADORM
        assert result.confidence == 0.95
        assert result.manufacturer_id == MANUFACTURER_ID_VIBRADORM

    def test_detect_okin_cb24_by_manufacturer_id(self):
        """Test OKIN CB24 detection by Company ID 89 (SmartBed by Okin).

        GitHub issue #185: Amada bed with SmartBed by Okin app advertises
        manufacturer ID 89 but no service UUIDs, so detection must use
        manufacturer data instead. Uses CB24 protocol over Nordic UART.

        Note: Manufacturer ID 89 detection is a FALLBACK (checked last) to
        allow UUID-based detection to take priority for other OKIN devices.
        """
        service_info = _make_service_info(
            name="Smartbed209008942",
            manufacturer_data={MANUFACTURER_ID_OKIN: b"\x01\x02\x03"},
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_OKIN_CB24
        assert result.confidence == 0.7  # Lower confidence as fallback
        assert result.manufacturer_id == MANUFACTURER_ID_OKIN

    def test_bare_manufacturer_id_89_without_okin_name_is_not_a_bed(self):
        """Manufacturer ID 89 alone (no OKIN/SmartBed name) must not match CB24.

        Regression test for #366: the "ABXM2" device advertises only manufacturer
        ID 89 (Nordic Semiconductor's generic company ID 0x0059) with no service
        UUIDs and a non-OKIN name, and was wrongly auto-detected as okin_cb24.
        """
        service_info = _make_service_info(
            name="ABXM2",
            manufacturer_data={MANUFACTURER_ID_OKIN: bytes.fromhex("0800864100650400000270f90300")},
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type is None

    def test_detect_okin_cb24_nordic_uart_plus_manufacturer_id(self):
        """Test CB24 detection when device has both Nordic UART UUID and OKIN mfr ID.

        GitHub issue #309: Lucid L600 ("Smartbed237004683") advertises Nordic
        UART service UUID AND OKIN manufacturer ID 89. Without this fix, the
        Nordic UART check returns Richmat before the CB24 fallback is reached.
        """
        service_info = _make_service_info(
            name="Smartbed237004683",
            service_uuids=[RICHMAT_NORDIC_SERVICE_UUID],
            manufacturer_data={MANUFACTURER_ID_OKIN: b"DOT\x00\x02"},
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_OKIN_CB24
        assert result.confidence == 0.7
        assert result.manufacturer_id == MANUFACTURER_ID_OKIN
        assert BED_TYPE_RICHMAT in result.ambiguous_types

    def test_detect_smartbed428_ab010204_as_malouf_new_okin(self):
        """Smartbed428 Malouf S755 / CB.24.42.28 uses Malouf New Okin packets.

        GitHub issue #393: this device advertises only Nordic UART plus OKIN
        manufacturer data, so the generic CB24 fallback must not claim it.
        """
        service_info = _make_service_info(
            name="Smartbed428000193",
            service_uuids=[RICHMAT_NORDIC_SERVICE_UUID],
            manufacturer_data={MANUFACTURER_ID_OKIN: bytes.fromhex("4142010204")},
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_MALOUF_NEW_OKIN
        assert result.confidence == 0.85
        assert result.manufacturer_id == MANUFACTURER_ID_OKIN
        assert "name:smartbed428" in result.signals
        assert "manufacturer_payload:ab0102" in result.signals
        assert result.ambiguous_types is None

    def test_cb24_ab_payload_still_detects_cb24(self):
        """Known CB24AB advertisements must keep the CB24 detection path."""
        service_info = _make_service_info(
            name="Smartbed209008942",
            service_uuids=[RICHMAT_NORDIC_SERVICE_UUID],
            manufacturer_data={MANUFACTURER_ID_OKIN: b"AB\x08\x01\x02"},
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_OKIN_CB24
        assert result.confidence == 0.7
        assert result.manufacturer_id == MANUFACTURER_ID_OKIN
        assert BED_TYPE_RICHMAT in result.ambiguous_types

    def test_nordic_uart_without_okin_mfr_still_detects_richmat(self):
        """Ensure Nordic UART without OKIN manufacturer ID still returns Richmat."""
        service_info = _make_service_info(
            name="SomeDevice",
            service_uuids=[RICHMAT_NORDIC_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_RICHMAT
        assert result.confidence == 0.5

    def test_nora_con_nordic_uart_detects_okin_64bit(self):
        """NORA_CON Mattress Firm controllers should not default to Richmat Nordic."""
        service_info = _make_service_info(
            name="NORA_CON",
            service_uuids=[RICHMAT_NORDIC_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)

        assert result.bed_type == BED_TYPE_OKIN_64BIT
        assert result.confidence == 0.85
        assert "name:nora_con" in result.signals
        assert "uuid:nordic_uart" in result.signals


class TestOkinUUIDDisambiguation:
    """Test disambiguation of beds sharing OKIN service UUID (62741523)."""

    def test_okin_uuid_with_nectar_name(self):
        """Test Nectar detection with OKIN UUID + 'nectar' in name."""
        service_info = _make_service_info(
            name="Nectar Bed",
            service_uuids=[OKIMAT_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_NECTAR

    def test_okin_uuid_with_sleepys_name(self):
        """Test Sleepy's BOX24 detection with OKIN UUID + sleepy in name."""
        service_info = _make_service_info(
            name="Sleepy's Elite",
            service_uuids=[OKIMAT_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_SLEEPYS_BOX24

    def test_okin_uuid_with_mfrm_name(self):
        """Test Sleepy's BOX24 detection with OKIN UUID + MFRM in name."""
        service_info = _make_service_info(
            name="MFRM Base",
            service_uuids=[OKIMAT_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_SLEEPYS_BOX24

    def test_okin_uuid_with_leggett_name(self):
        """Test Leggett Okin detection with OKIN UUID + 'leggett' in name."""
        service_info = _make_service_info(
            name="Leggett & Platt",
            service_uuids=[OKIMAT_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_LEGGETT_OKIN

    def test_okin_uuid_with_okimat_name(self):
        """Test Okimat detection with OKIN UUID + 'okimat' in name."""
        service_info = _make_service_info(
            name="Okimat Bed",
            service_uuids=[OKIMAT_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_OKIMAT

    def test_okin_uuid_with_okin_rf_name(self):
        """Test Okimat detection with OKIN UUID + 'OKIN RF' in name."""
        service_info = _make_service_info(
            name="OKIN RF TOPLINE",
            service_uuids=[OKIMAT_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_OKIMAT

    def test_okin_uuid_with_smartbed_name(self):
        """Test Okimat detection with OKIN UUID + 'Smartbed' in name."""
        service_info = _make_service_info(
            name="Smartbed 2.0",
            service_uuids=[OKIMAT_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_OKIMAT

    @pytest.mark.parametrize("name", ["OKIN-Receiver", "OKIN - Receiver"])
    def test_okin_uuid_with_receiver_name_is_ambiguous(self, name: str):
        """Receiver names should not become high-confidence Okimat after pairing."""
        service_info = _make_service_info(
            name=name,
            service_uuids=[OKIMAT_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)

        assert result.bed_type == BED_TYPE_OKIN_UUID
        assert result.confidence == 0.6
        assert result.requires_characteristic_check is True
        assert "uuid:okin" in result.signals
        assert "name:okin_receiver" in result.signals
        assert BED_TYPE_OKIN_CST in result.ambiguous_types

    def test_okin_uuid_with_generic_okin_prefix_is_ambiguous(self):
        """Generic OKIN-* names should not be hard-forced to Okimat."""
        service_info = _make_service_info(
            name="OKIN-441954",
            service_uuids=[OKIMAT_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_OKIMAT
        assert result.confidence == 0.6
        assert result.requires_characteristic_check is True
        assert "name:okin_generic" in result.signals
        assert BED_TYPE_NECTAR in result.ambiguous_types
        assert BED_TYPE_OKIN_RF_ECO_BT in result.ambiguous_types

    def test_okin_generic_name_without_advertised_uuid_is_not_auto_detected(self):
        """Generic OKIN-* advertisements without UUIDs should remain manual."""
        service_info = _make_service_info(
            name="OKIN-050226",
            service_uuids=[],
        )
        result = detect_bed_type_detailed(service_info)

        assert result.bed_type is None
        assert result.confidence == 0.0

    def test_dewertokin_rf_gateway_advertised_uuid_is_detected(self):
        """RF-Gateway advertisements should create DewertOkin discovery flows."""
        service_info = _make_service_info(
            name="Schrank",
            service_uuids=[DEWERTOKIN_RF_GATEWAY_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)

        assert result.bed_type == BED_TYPE_DEWERTOKIN
        assert result.confidence == 0.9
        assert "uuid:dewertokin_rf_gateway" in result.signals

    def test_dewertokin_rf_gateway_gatt_signature_is_detected(self):
        """Connected RF-Gateway services should identify DewertOkin."""
        gatt_services = [
            SimpleNamespace(
                uuid=DEWERTOKIN_RF_GATEWAY_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=DEWERTOKIN_RF_GATEWAY_WRITE_CHAR_UUID),
                ],
            ),
        ]

        result = detect_bed_type_from_gatt_services(gatt_services)

        assert result.bed_type == BED_TYPE_DEWERTOKIN
        assert result.confidence == 0.9
        assert "gatt_char:dewertokin_rf_gateway_write" in result.signals

    def test_okin_rf_eco_bt_gatt_signature_is_detected(self):
        """Connected GATT services should identify the OKIN RF ECO BT profile."""
        gatt_services = [
            SimpleNamespace(
                uuid=OKIMAT_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIMAT_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID),
                ],
            ),
        ]

        result = detect_bed_type_from_gatt_services(gatt_services)

        assert result.bed_type == BED_TYPE_OKIN_RF_ECO_BT
        assert result.confidence == 0.9
        assert "gatt_char:okin_smart_remote_css_write" in result.signals

    def test_okin_cst_dual_stack_gatt_signature_wins_over_rf_eco_bt(self):
        """Newer OKIN full-bed controllers can expose CSS plus Nordic DFU."""
        gatt_services = [
            SimpleNamespace(
                uuid=OKIMAT_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIMAT_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=NORDIC_DFU_SERVICE_UUID,
                characteristics=[],
            ),
        ]

        result = detect_bed_type_from_gatt_services(gatt_services)

        assert result.bed_type == BED_TYPE_OKIN_CST
        assert result.confidence == 0.8
        assert "gatt_service:nordic_dfu" in result.signals
        assert BED_TYPE_OKIN_RF_ECO_BT in result.ambiguous_types

    def test_shared_okin_gatt_refinement_corrects_leggett_okin_to_cst(self):
        """A saved Leggett/Okin entry should use CST when connected GATT proves it."""
        gatt_services = [
            SimpleNamespace(
                uuid=OKIMAT_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIMAT_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=NORDIC_DFU_SERVICE_UUID,
                characteristics=[],
            ),
        ]

        assert (
            refine_okin_shared_uuid_protocol_from_gatt(BED_TYPE_LEGGETT_OKIN, gatt_services)
            == BED_TYPE_OKIN_CST
        )

    def test_shared_okin_gatt_refinement_corrects_legacy_leggett_okin_variant_to_cst(self):
        """A legacy Leggett entry using the OKIN variant should be GATT-refinable."""
        gatt_services = [
            SimpleNamespace(
                uuid=OKIMAT_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIMAT_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=NORDIC_DFU_SERVICE_UUID,
                characteristics=[],
            ),
        ]

        assert (
            refine_okin_shared_uuid_protocol_from_gatt(
                BED_TYPE_LEGGETT_PLATT,
                gatt_services,
                LEGGETT_VARIANT_OKIN,
            )
            == BED_TYPE_OKIN_CST
        )

    def test_shared_okin_gatt_refinement_ignores_legacy_leggett_gen2_variant(self):
        """Only the legacy Leggett OKIN variant should enter the OKIN GATT refiner."""
        gatt_services = [
            SimpleNamespace(
                uuid=OKIMAT_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIMAT_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=NORDIC_DFU_SERVICE_UUID,
                characteristics=[],
            ),
        ]

        assert (
            refine_okin_shared_uuid_protocol_from_gatt(
                BED_TYPE_LEGGETT_PLATT,
                gatt_services,
                LEGGETT_VARIANT_GEN2,
            )
            == BED_TYPE_LEGGETT_PLATT
        )

    def test_shared_okin_gatt_refinement_corrects_canonical_7byte_to_cst(self):
        """A saved canonical OKIN 7-byte entry should still be GATT-refinable."""
        gatt_services = [
            SimpleNamespace(
                uuid=OKIMAT_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIMAT_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=NORDIC_DFU_SERVICE_UUID,
                characteristics=[],
            ),
        ]

        assert (
            refine_okin_shared_uuid_protocol_from_gatt(BED_TYPE_OKIN_7BYTE, gatt_services)
            == BED_TYPE_OKIN_CST
        )

    def test_shared_okin_gatt_refinement_corrects_okimat_to_rf_eco_bt(self):
        """Connected CSS without DFU identifies the RF ECO BT profile."""
        gatt_services = [
            SimpleNamespace(
                uuid=OKIMAT_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIMAT_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID),
                ],
            ),
        ]

        assert (
            refine_okin_shared_uuid_protocol_from_gatt(BED_TYPE_OKIMAT, gatt_services)
            == BED_TYPE_OKIN_RF_ECO_BT
        )

    def test_shared_okin_gatt_refinement_preserves_explicit_cst_without_dfu(self):
        """A manually selected CST entry should not require DFU to remain CST."""
        gatt_services = [
            SimpleNamespace(
                uuid=OKIMAT_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIMAT_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID),
                ],
            ),
        ]

        assert (
            refine_okin_shared_uuid_protocol_from_gatt(BED_TYPE_OKIN_CST, gatt_services)
            == BED_TYPE_OKIN_CST
        )

    def test_shared_okin_gatt_refinement_leaves_unrelated_types_unchanged(self):
        """The OKIN correction is scoped away from other shared UUID families."""
        gatt_services = [
            SimpleNamespace(
                uuid=OKIMAT_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIMAT_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
                characteristics=[
                    SimpleNamespace(uuid=OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID),
                ],
            ),
            SimpleNamespace(
                uuid=NORDIC_DFU_SERVICE_UUID,
                characteristics=[],
            ),
        ]

        assert (
            refine_okin_shared_uuid_protocol_from_gatt(BED_TYPE_KEESON, gatt_services)
            == BED_TYPE_KEESON
        )

    def test_nordic_uart_device_info_refinement_corrects_richmat_to_okin_64bit(self):
        """A saved Richmat entry should use OKIN 64-bit when Device Info proves NORA."""
        assert (
            refine_nordic_uart_protocol_from_device_info(
                BED_TYPE_RICHMAT,
                "NORA_CON",
                "IDT",
                "NORACON",
            )
            == BED_TYPE_OKIN_64BIT
        )

    def test_nordic_uart_device_info_refinement_accepts_noracon_model(self):
        """The model number alone is enough when Device Info reports NORACON."""
        assert (
            refine_nordic_uart_protocol_from_device_info(
                BED_TYPE_MATTRESSFIRM,
                "Unknown Nordic",
                None,
                "NORACON",
            )
            == BED_TYPE_OKIN_64BIT
        )

    def test_nordic_uart_device_info_refinement_corrects_canonical_okin_nordic(self):
        """A saved canonical OKIN Nordic entry should still be Device Info-refinable."""
        assert (
            refine_nordic_uart_protocol_from_device_info(
                BED_TYPE_OKIN_NORDIC,
                "NORA_CON",
                "IDT",
                "NORACON",
            )
            == BED_TYPE_OKIN_64BIT
        )

    def test_nordic_uart_device_info_refinement_leaves_generic_richmat_unchanged(self):
        """Generic Nordic UART devices must keep the existing low-confidence fallback."""
        assert (
            refine_nordic_uart_protocol_from_device_info(
                BED_TYPE_RICHMAT,
                "Unknown Nordic",
                "Unknown",
                "Unknown",
            )
            == BED_TYPE_RICHMAT
        )

    def test_malouf_new_refines_to_legacy_when_gatt_has_ffe9_only(self):
        """A saved Malouf Nordic entry should use FFE5 when connected GATT proves it."""
        gatt_services = [
            SimpleNamespace(
                uuid=KEESON_BASE_SERVICE_UUID,
                characteristics=[SimpleNamespace(uuid=MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID)],
            )
        ]

        assert (
            refine_malouf_protocol_from_gatt(BED_TYPE_MALOUF_NEW_OKIN, gatt_services)
            == BED_TYPE_MALOUF_LEGACY_OKIN
        )

    def test_malouf_legacy_refines_to_new_when_gatt_has_nordic_write_only(self):
        """The Malouf family correction should work in both protocol directions."""
        gatt_services = [
            SimpleNamespace(
                uuid=NORDIC_UART_SERVICE_UUID,
                characteristics=[SimpleNamespace(uuid=MALOUF_NEW_OKIN_WRITE_CHAR_UUID)],
            )
        ]

        assert (
            refine_malouf_protocol_from_gatt(BED_TYPE_MALOUF_LEGACY_OKIN, gatt_services)
            == BED_TYPE_MALOUF_NEW_OKIN
        )

    def test_malouf_gatt_refinement_leaves_non_malouf_types_unchanged(self):
        """GATT refinement is scoped to Malouf/Lucid entries because FFE5 is shared."""
        gatt_services = [
            SimpleNamespace(
                uuid=KEESON_BASE_SERVICE_UUID,
                characteristics=[SimpleNamespace(uuid=MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID)],
            )
        ]

        assert refine_malouf_protocol_from_gatt(BED_TYPE_KEESON, gatt_services) == BED_TYPE_KEESON

    def test_okin_uuid_defaults_to_okimat(self):
        """Test OKIN UUID defaults to Okimat with low confidence for unknown name."""
        service_info = _make_service_info(
            name="Unknown Base",
            service_uuids=[OKIMAT_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_OKIMAT
        assert result.confidence == 0.5
        assert result.requires_characteristic_check is True
        assert BED_TYPE_NECTAR in result.ambiguous_types
        assert BED_TYPE_OKIN_RF_ECO_BT in result.ambiguous_types


class TestFFE5UUIDDisambiguation:
    """Test disambiguation of beds sharing FFE5 service UUID."""

    def test_ffe5_with_serta_name(self):
        """Test Serta detection with FFE5 UUID + 'serta' in name."""
        service_info = _make_service_info(
            name="Serta Motion",
            service_uuids=[KEESON_BASE_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_SERTA

    def test_ffe5_with_malouf_name(self):
        """Test Malouf LEGACY_OKIN detection with FFE5 UUID + 'malouf' in name."""
        service_info = _make_service_info(
            name="Malouf Base",
            service_uuids=[KEESON_BASE_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_MALOUF_LEGACY_OKIN

    def test_ffe5_with_sleepys_name(self):
        """Test Sleepy's BOX15 detection with FFE5 UUID + sleepy in name."""
        service_info = _make_service_info(
            name="Sleepy's Premium",
            service_uuids=[KEESON_BASE_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_SLEEPYS_BOX15

    def test_ffe5_with_okin_name(self):
        """Test OKIN FFE detection with FFE5 UUID + 'okin' in name."""
        service_info = _make_service_info(
            name="OKIN 15 Series",
            service_uuids=[KEESON_BASE_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_OKIN_FFE

    def test_ffe5_with_cb_prefix(self):
        """Test OKIN FFE detection with FFE5 UUID + 'CB-' prefix."""
        service_info = _make_service_info(
            name="CB-1234",
            service_uuids=[KEESON_BASE_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_OKIN_FFE

    def test_ffe5_defaults_to_keeson(self):
        """Test FFE5 UUID defaults to Keeson for unknown name."""
        service_info = _make_service_info(
            name="Unknown Base",
            service_uuids=[KEESON_BASE_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_KEESON
        assert result.confidence == 0.5


class TestFFE0UUIDDisambiguation:
    """Test disambiguation of beds sharing FFE0 service UUID (Octo/Solace/MotoSleep)."""

    def test_ffe0_with_solace_name(self):
        """Test Solace detection with FFE0 UUID + 'solace' in name."""
        service_info = _make_service_info(
            name="Solace Smart Bed",
            service_uuids=[SOLACE_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_SOLACE

    def test_ffe0_with_qms_prefix(self):
        """Test Solace detection with FFE0 UUID + QMS- prefix."""
        service_info = _make_service_info(
            name="QMS-IQ",
            service_uuids=[SOLACE_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_SOLACE

    def test_ffe0_with_s4_prefix(self):
        """Test Solace detection with FFE0 UUID + S4- prefix."""
        service_info = _make_service_info(
            name="S4-Y-192-461000AD",
            service_uuids=[SOLACE_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_SOLACE

    def test_ffe0_with_legacy_solace_pattern(self):
        """Test Solace detection with FFE0 UUID + legacy S2-* naming format."""
        service_info = _make_service_info(
            name="S2-Y-192-461000AD",
            service_uuids=[SOLACE_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_SOLACE

    def test_ffe0_with_sealymf_name(self):
        """Test Solace detection with FFE0 UUID + SealyMF in name."""
        service_info = _make_service_info(
            name="SealyMF Base",
            service_uuids=[SOLACE_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_SOLACE

    def test_ffe0_defaults_to_octo(self):
        """Test FFE0 UUID defaults to Octo for unknown name."""
        service_info = _make_service_info(
            name="Unknown Base",
            service_uuids=[SOLACE_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_OCTO
        assert result.confidence == 0.5


class TestOctoNamePatterns:
    """Test Octo detection by name patterns (from blenames.json)."""

    @pytest.mark.parametrize(
        "name",
        [
            "rtv123",
            "RTV456",
            "rc2",
            "RC2",
            "mc2-base",
            "MC1",
            "l2m001",
            "cli123",
            "octoiq",
            "OCTOIQ",
            "octobrick2",
            "rc3",
            "bmb100",
            "bms200",
            "bm3300",
            "da1458x",
            "DA1458X001",
        ],
    )
    def test_detect_octo_by_name_pattern(self, name: str):
        """Test Octo detection by various name patterns from blenames.json."""
        service_info = _make_service_info(name=name)
        assert detect_bed_type(service_info) == BED_TYPE_OCTO


class TestFEE9UUIDDisambiguation:
    """Test disambiguation of beds sharing FEE9 service UUID (Richmat WiLinke / BedTech)."""

    def test_fee9_with_bedtech_name(self):
        """Test BedTech detection with FEE9 UUID + 'bedtech' in name."""
        service_info = _make_service_info(
            name="BedTech Comfort",
            service_uuids=[BEDTECH_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_BEDTECH

    def test_fee9_with_bedtech_model_name_is_ambiguous(self):
        """Test FEE9 + BT model name defaults to Richmat with ambiguity."""
        service_info = _make_service_info(
            name="BT6500",
            service_uuids=[BEDTECH_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_RICHMAT
        assert result.confidence == 0.5
        assert result.ambiguous_types == [BED_TYPE_BEDTECH]

    def test_fee9_with_richmat_remote_name_prefers_richmat(self):
        """Test FEE9 + Richmat remote code name uses high-confidence Richmat."""
        service_info = _make_service_info(
            name="QRRM141291",
            service_uuids=[BEDTECH_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_RICHMAT
        assert result.confidence == 0.9
        assert result.detected_remote == "qrrm"

    def test_fee9_with_mlrm_name(self):
        """Test Leggett WiLinke detection with FEE9 UUID + MlRM prefix."""
        service_info = _make_service_info(
            name="MlRM157052",
            service_uuids=[RICHMAT_WILINKE_SERVICE_UUIDS[1]],  # FEE9
        )
        assert detect_bed_type(service_info) == BED_TYPE_LEGGETT_WILINKE

    def test_fee9_defaults_to_richmat_with_ambiguity(self):
        """Test FEE9 UUID defaults to Richmat with ambiguity flag."""
        service_info = _make_service_info(
            name="Unknown WiLinke",
            service_uuids=[RICHMAT_WILINKE_SERVICE_UUIDS[1]],  # FEE9
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_RICHMAT
        assert result.confidence == 0.5
        assert result.requires_characteristic_check is True


class TestW5WiLinkeNameGuard:
    """W5 (E0FF) uses a shared Telink base, so it needs a Richmat name (issue #382)."""

    def test_w5_uuid_without_richmat_name_is_not_a_bed(self):
        """A non-bed device advertising only the W5 UUID must not detect as Richmat.

        Regression for #382: a "Nokia-*" headset advertised the W5 custom-base
        UUID and was misidentified as a Richmat bed at 80% confidence.
        """
        service_info = _make_service_info(
            name="Nokia-E4-F1",
            address="E0:1F:2B:7A:E4:F1",
            service_uuids=[RICHMAT_WILINKE_W5_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type != BED_TYPE_RICHMAT
        assert "uuid:wilinke" not in result.signals

    def test_w5_uuid_with_richmat_name_still_detects(self):
        """A genuine W5 bed with a Richmat name pattern still detects as Richmat."""
        service_info = _make_service_info(
            name="QRRM141291",
            service_uuids=[RICHMAT_WILINKE_W5_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_RICHMAT
        assert "uuid:wilinke" in result.signals

    def test_w5_uuid_with_dhn_name_still_detects(self):
        """Germany Motions DHN-* names corroborate a W5 advertisement."""
        service_info = _make_service_info(
            name="DHN-1234",
            service_uuids=[RICHMAT_WILINKE_W5_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_RICHMAT

    def test_w5_uuid_excluded_from_manifest_discovery(self):
        """W5 must not be a passive bluetooth discovery matcher (avoids false flows)."""
        import json
        from pathlib import Path

        manifest_path = (
            Path(__file__).parents[1]
            / "custom_components"
            / "adjustable_bed"
            / "manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        service_uuids = {
            entry.get("service_uuid", "").lower() for entry in manifest["bluetooth"]
        }
        assert RICHMAT_WILINKE_W5_SERVICE_UUID.lower() not in service_uuids


class TestNordicUARTDisambiguation:
    """Test disambiguation of beds sharing Nordic UART service UUID."""

    def test_nordic_uart_defaults_to_richmat(self):
        """Test Nordic UART UUID defaults to Richmat with ambiguity."""
        service_info = _make_service_info(
            name="Unknown Nordic",
            service_uuids=[RICHMAT_NORDIC_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_RICHMAT
        assert result.confidence == 0.5
        assert result.requires_characteristic_check is True


class TestExcludedDevicePatterns:
    """Test that non-bed devices are correctly excluded.

    These devices use generic BLE UUIDs (FFE0, FFE5, Nordic UART) that
    are also used by legitimate beds, causing false positive discovery.
    See: https://github.com/kristofferR/ha-adjustable-bed/issues/187
    """

    @pytest.mark.parametrize(
        "name",
        [
            # Mobility devices
            "scooter123",
            "Ninebot S",
            "Segway Mini",
            "eBike Controller",
            "E-Bike Plus",
            "EScooter Pro",
            "E-Scooter Mini",
            "Skateboard Electric",
            "Hoverboard Kids",
            # Scales and health monitors (issue #187)
            "Wyze Scale",
            "Wyze Scale S",
            "Withings Body+",
            "RENPHO Smart Scale",
            "eufy Smart Scale",
            "FitIndex Scale",
            "Greater Goods Scale",
            "Etekcity Scale",
            "Arboleaf Scale",
            "Weight Gurus",
            "My Scale Pro",
            # Wearables and fitness trackers (issue #187)
            "Fitbit Charge 5",
            "Garmin Forerunner",
            "Amazfit Band 7",
            "Xiaomi Mi Band",
            "Mi Band 8",
            "MiBand 7",
            "Huawei Band 8",
            "Polar H10",
            "Suunto 9",
            "COROS PACE 2",
            "WHOOP 4.0",
            "Smart Watch Pro",
            "Fitness Tracker X",
            "Activity Band",
            # Health monitors
            "Blood Pressure Monitor",
            "Pulse Ox Sensor",
            "Heart Rate Monitor",
            "Glucose Monitor",
            "Fingertip Oximeter",
            "Digital Thermometer",
            # Other common BLE devices
            "Sony Headphones",
            "AirPods Pro",
            "Wireless Earbuds",
            "Bluetooth Speaker",
            "Logitech Keyboard",
            "MX Mouse",
            "Xbox Controller",
            "PS5 Gamepad",
            "Tile Pro",
            "AirTag Wallet",
            "SmartTag Plus",
            "iBeacon",
        ],
    )
    def test_excluded_devices(self, name: str):
        """Test that non-bed devices with generic UUIDs are excluded."""
        service_info = _make_service_info(
            name=name,
            service_uuids=[SOLACE_SERVICE_UUID],  # Generic FFE0 UUID
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type is None
        assert "excluded:" in result.signals[0]

    @pytest.mark.parametrize(
        "name",
        [
            # Scales with FFE5 UUID (Keeson/Malouf/Serta)
            "Wyze Scale X",
            "Smart Scale WiFi",
            # Wearables with Nordic UART
            "Band 8 Pro",
            "Watch SE",
        ],
    )
    def test_excluded_devices_ffe5_uuid(self, name: str):
        """Test exclusion works with FFE5 UUID (used by Keeson, Malouf, etc.)."""
        service_info = _make_service_info(
            name=name,
            service_uuids=[KEESON_BASE_SERVICE_UUID],  # FFE5 UUID
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type is None
        assert "excluded:" in result.signals[0]

    @pytest.mark.parametrize(
        "name",
        [
            # Devices with Nordic UART UUID
            "Polar Heart Rate",
            "Garmin Watch 2",
        ],
    )
    def test_excluded_devices_nordic_uart(self, name: str):
        """Test exclusion works with Nordic UART UUID."""
        service_info = _make_service_info(
            name=name,
            service_uuids=[RICHMAT_NORDIC_SERVICE_UUID],  # Nordic UART
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type is None
        assert "excluded:" in result.signals[0]

    def test_exclusion_skipped_for_unique_uuid_linak(self):
        """Test that exclusion is skipped when device has unique Linak UUID.

        A hypothetical "Linak Controller" bed should be detected as Linak,
        not excluded by the "controller" pattern.
        """
        service_info = _make_service_info(
            name="Linak Controller",
            service_uuids=[LINAK_CONTROL_SERVICE_UUID],  # Unique Linak UUID
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_LINAK
        assert result.confidence == 1.0
        assert "excluded:" not in str(result.signals)

    def test_exclusion_skipped_for_unique_uuid_jensen(self):
        """Test that exclusion is skipped when device has unique Jensen UUID.

        A hypothetical "Jensen Watch" bed should be detected as Jensen,
        not excluded by the "watch" pattern.
        """
        service_info = _make_service_info(
            name="Jensen Watch",
            service_uuids=[JENSEN_SERVICE_UUID],  # Unique Jensen UUID
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_JENSEN
        assert result.confidence == 1.0
        assert "excluded:" not in str(result.signals)

    def test_exclusion_skipped_for_unique_uuid_svane(self):
        """Test that exclusion is skipped when device has unique Svane UUID.

        A hypothetical "Svane Band" bed should be detected as Svane,
        not excluded by the "band" pattern.
        """
        service_info = _make_service_info(
            name="Svane Band",
            service_uuids=[SVANE_HEAD_SERVICE_UUID],  # Unique Svane UUID
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type == BED_TYPE_SVANE
        assert result.confidence == 1.0
        assert "excluded:" not in str(result.signals)

    def test_exclusion_applied_with_no_uuids(self):
        """Test that exclusion is applied when device has no UUIDs."""
        service_info = _make_service_info(
            name="Wyze Scale",
            service_uuids=[],  # No UUIDs
        )
        result = detect_bed_type_detailed(service_info)
        assert result.bed_type is None
        # Either "wyze" or "scale" pattern can match first
        assert any("excluded:" in s for s in result.signals)


class TestUnknownDevices:
    """Test handling of unknown/unrecognized devices."""

    def test_unknown_device_no_uuids(self):
        """Test unknown device with no service UUIDs."""
        service_info = _make_service_info(
            name="Random Device",
            service_uuids=[],
        )
        assert detect_bed_type(service_info) is None

    def test_unknown_device_generic_uuid(self):
        """Test unknown device with generic BLE UUID."""
        service_info = _make_service_info(
            name="Random Device",
            service_uuids=["00001800-0000-1000-8000-00805f9b34fb"],  # Generic Access
        )
        assert detect_bed_type(service_info) is None

    def test_unknown_device_no_name(self):
        """Test device with no name but valid UUID still detected."""
        service_info = _make_service_info(
            name=None,
            service_uuids=[LINAK_CONTROL_SERVICE_UUID],
        )
        assert detect_bed_type(service_info) == BED_TYPE_LINAK


class TestDetectionConfidenceScores:
    """Test confidence scores in detection results."""

    def test_unique_uuid_high_confidence(self):
        """Test unique UUIDs return confidence of 1.0."""
        service_info = _make_service_info(
            name="Linak Bed",
            service_uuids=[LINAK_CONTROL_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert result.confidence == 1.0

    def test_manufacturer_data_high_confidence(self):
        """Test manufacturer data returns confidence of 0.95."""
        service_info = _make_service_info(
            name="Unknown",
            manufacturer_data={MANUFACTURER_ID_DEWERTOKIN: b"\x01"},
        )
        result = detect_bed_type_detailed(service_info)
        assert result.confidence == 0.95

    def test_name_pattern_medium_confidence(self):
        """Test name pattern detection returns confidence of 0.9."""
        service_info = _make_service_info(name="JMC400")
        result = detect_bed_type_detailed(service_info)
        assert result.confidence == 0.9

    def test_ambiguous_uuid_low_confidence(self):
        """Test ambiguous UUIDs return confidence of 0.5."""
        service_info = _make_service_info(
            name="Unknown",
            service_uuids=[KEESON_BASE_SERVICE_UUID],  # FFE5 - ambiguous
        )
        result = detect_bed_type_detailed(service_info)
        assert result.confidence == 0.5


class TestRichmatRemoteDetection:
    """Test Richmat remote code detection from device name."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("QRRM157052", "qrrm"),
            ("V1RM123456", "v1rm"),
            ("BURM654321", "burm"),
            ("ZR10000001", "zr10"),
            ("ZR60000002", "zr60"),
            ("X1RM789012", "x1rm"),
            ("A0RN123456", "a0rn"),  # R + N suffix
        ],
    )
    def test_extract_richmat_remote_code(self, name: str, expected: str):
        """Test extraction of remote codes from device names."""
        assert detect_richmat_remote_from_name(name) == expected

    def test_sleep_function_maps_to_i7rm(self):
        """Test 'Sleep Function' name maps to i7rm remote code."""
        assert detect_richmat_remote_from_name("Sleep Function 2.0") == "i7rm"

    def test_no_remote_code_returns_none(self):
        """Test non-Richmat names return None."""
        assert detect_richmat_remote_from_name("Random Device") is None
        assert detect_richmat_remote_from_name("") is None
        assert detect_richmat_remote_from_name(None) is None


class TestCaseInsensitivity:
    """Test that detection is case-insensitive."""

    def test_uuid_lowercase(self):
        """Test UUIDs work in lowercase."""
        service_info = _make_service_info(
            name="Test",
            service_uuids=[LINAK_CONTROL_SERVICE_UUID.lower()],
        )
        assert detect_bed_type(service_info) == BED_TYPE_LINAK

    def test_uuid_uppercase(self):
        """Test UUIDs work in uppercase."""
        service_info = _make_service_info(
            name="Test",
            service_uuids=[LINAK_CONTROL_SERVICE_UUID.upper()],
        )
        assert detect_bed_type(service_info) == BED_TYPE_LINAK

    def test_name_pattern_mixed_case(self):
        """Test name patterns work in mixed case."""
        service_info = _make_service_info(name="JmC400")
        assert detect_bed_type(service_info) == BED_TYPE_JENSEN


class TestDetectionSignals:
    """Test detection signals in result."""

    def test_uuid_signal(self):
        """Test UUID detection includes signal."""
        service_info = _make_service_info(
            name="Test",
            service_uuids=[LINAK_CONTROL_SERVICE_UUID],
        )
        result = detect_bed_type_detailed(service_info)
        assert "uuid:linak" in result.signals

    def test_name_signal(self):
        """Test name detection includes signal."""
        service_info = _make_service_info(name="JMC400")
        result = detect_bed_type_detailed(service_info)
        assert "name:jensen" in result.signals

    def test_manufacturer_signal(self):
        """Test manufacturer data detection includes signal."""
        service_info = _make_service_info(
            name="Test",
            manufacturer_data={MANUFACTURER_ID_DEWERTOKIN: b"\x01"},
        )
        result = detect_bed_type_detailed(service_info)
        assert f"manufacturer_id:{MANUFACTURER_ID_DEWERTOKIN}" in result.signals
