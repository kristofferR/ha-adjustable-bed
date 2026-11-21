"""What the diagnostics download and the support bundle may publish.

Users attach both files to public GitHub issues.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers.storage import Store
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import async_remove_entry
from custom_components.adjustable_bed.app_state_store import jensen_memory_store_key
from custom_components.adjustable_bed.beds.jensen.controller import JensenController
from custom_components.adjustable_bed.beds.reverie.pairlink_sdk_storage import sdk_store_key
from custom_components.adjustable_bed.ble_diagnostics import (
    BLEDiagnosticRunner,
    CharacteristicInfo,
    DiagnosticReport,
)
from custom_components.adjustable_bed.codec import jmc
from custom_components.adjustable_bed.const import BED_TYPE_JENSEN, CONF_BED_TYPE, DOMAIN
from custom_components.adjustable_bed.redaction import redact_bundle, redact_data
from custom_components.adjustable_bed.services import (
    SERVICE_GENERATE_SUPPORT_BUNDLE,
    async_register_services,
)
from custom_components.adjustable_bed.support_bundle import (
    MAX_SAVED_BUNDLES,
    generate_support_bundle,
    save_support_bundle,
)
from custom_components.adjustable_bed.support_logs import async_setup_support_logs

TARGET = "AA:BB:CC:DD:EE:FF"


@pytest.mark.parametrize("redact", (redact_data, redact_bundle))
def test_both_files_follow_one_address_policy(redact) -> None:
    """Every address keeps only its prefix, in every form it appears (PRIV-8)."""
    data = {
        "address": TARGET,
        "advertised": "QRRM-DDEEFF",
        "manufacturer_data": "0102ffeedd03",
        "ascii": b"DDEEFF".hex(),
        "log": "seen aa_bb_cc_dd_ee_ff next to 11-22-33-44-55-66",
        TARGET: "keyed by address",
        "title": "Kris",
        "ble_device_name": "Kris bed",
        "fsm_relax_memory_names": {"1": "Reading"},
    }

    redacted = redact(data, addresses=[TARGET])

    assert redacted["address"] == "AA:BB:CC:**:**:**"
    assert redacted["advertised"] == "QRRM-******"
    assert redacted["manufacturer_data"] == "0102******03"
    assert redacted["ascii"] == "*" * 12
    assert redacted["log"] == "seen AA_BB_CC_**_**_** next to 11-22-33-**-**-**"
    assert "AA:BB:CC:**:**:**" in redacted
    dumped = json.dumps(redacted)
    for typed in ("Kris", "Reading"):
        assert typed not in dumped


def test_health_readings_keep_only_their_type() -> None:
    """Vital signs and presence keep the key, never the value (PRIV-2)."""
    state = {
        "left_heart_rate": 61,
        "breathingRate": 14.5,
        "bed_presence": True,
        "inbedDuration": 420,
        "sleep_report": {"score": 80},
        # Settings that only look similar stay readable.
        "anti_snore": 2,
        "rgb_breathe": True,
        "motion_bed_variant": "hub",
    }

    assert redact_bundle({"protocol_state": state}, addresses=[])["protocol_state"] == {
        "left_heart_rate": "<int>",
        "breathingRate": "<float>",
        "bed_presence": "<bool>",
        "inbedDuration": "<int>",
        "sleep_report": "<dict>",
        "anti_snore": 2,
        "rgb_breathe": True,
        "motion_bed_variant": "hub",
    }


def _capture(address: str) -> DiagnosticReport:
    return DiagnosticReport(
        metadata={},
        device={"address": address},
        advertisement=None,
        advertisements_by_source=[],
        detection={},
        gatt_services=[],
        gatt_summary={},
        device_information={},
        notifications=[],
        notification_summary={},
        adapter_details={},
        connection_history={},
        connection_attempt_details=[],
        command_trace=[],
        errors=[],
    )


async def test_bundle_logs_leave_out_other_devices(hass: HomeAssistant) -> None:
    """Log lines about a neighbour's or a household member's device are withheld (PRIV-3)."""
    logs = async_setup_support_logs(hass)
    logger = logging.getLogger("homeassistant.components.bluetooth.manager")
    with logs.capture_debug():
        logger.debug("%s: connecting", TARGET)
        logger.debug("11:22:33:44:55:66 (Anna's watch) switching scanner")
    with (
        patch.object(
            BLEDiagnosticRunner, "run_diagnostics", new=AsyncMock(return_value=_capture(TARGET))
        ),
        patch(
            "custom_components.adjustable_bed.support_bundle.bluetooth.async_current_scanners",
            return_value=[],
        ),
    ):
        report = await generate_support_bundle(
            hass, address=TARGET, capture_duration=0, include_logs=True
        )

    messages = [log["message"] for log in report["recent_logs"]]
    assert "AA:BB:CC:**:**:**: connecting" in messages
    assert "Anna" not in json.dumps(report)
    assert report["metadata"]["withheld_log_entries"] == 1


async def test_support_bundle_action_is_admin_only(
    hass: HomeAssistant, hass_read_only_user
) -> None:
    """A capture of any address, downloadable by anyone, needs an admin (PRIV-4)."""
    await async_register_services(hass)

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GENERATE_SUPPORT_BUNDLE,
            {"target_address": TARGET},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )


def test_saving_a_bundle_keeps_only_the_newest(hass: HomeAssistant, tmp_path: Path) -> None:
    """Old bundles do not pile up in the config folder and every backup (PRIV-9)."""
    hass.config.config_dir = str(tmp_path)
    old = [tmp_path / f"adjustable_bed_support_bundle_aabbcc_2026010{i}_120000.json" for i in range(6)]
    for age, path in enumerate(reversed(old), start=1):
        path.write_text("{}")
        os.utime(path, (1_000_000 - age, 1_000_000 - age))
    unrelated = tmp_path / "configuration.yaml"
    unrelated.write_text("")

    saved = save_support_bundle(hass, {}, TARGET)

    kept = sorted(path.name for path in tmp_path.glob("adjustable_bed_support_*.json"))
    assert len(kept) == MAX_SAVED_BUNDLES
    assert saved.name in kept
    assert old[0].name not in kept
    assert unrelated.exists()


async def test_removing_a_bed_deletes_its_stored_files(hass: HomeAssistant) -> None:
    """Per-bed files do not outlive the bed (PRIV-9)."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ADDRESS: TARGET, CONF_BED_TYPE: BED_TYPE_JENSEN}
    )
    entry.add_to_hass(hass)
    memory = Store(hass, 1, jensen_memory_store_key(TARGET))
    pairlink = Store(hass, 1, sdk_store_key(entry.entry_id))
    await memory.async_save({"1": [10, 20]})
    await pairlink.async_save({"pl_finger_print": {}})

    await async_remove_entry(hass, entry)

    assert not Path(memory.path).exists()
    assert not Path(pairlink.path).exists()


async def test_reading_the_command_characteristic_back_redacts_a_pin(hass: HomeAssistant) -> None:
    """A characteristic read never shows a frame the command trace hides."""
    coordinator = MagicMock()
    coordinator.address = TARGET
    coordinator.controller = JensenController(coordinator, pin="8264")
    runner = BLEDiagnosticRunner(hass, TARGET, capture_duration=0, coordinator=coordinator)
    runner._client = MagicMock()
    char_info = CharacteristicInfo(uuid=jmc.CHAR_UUID, handle=3, properties=["read", "write"])

    with (
        patch.object(runner, "_ensure_connected", new=AsyncMock(return_value=True)),
        patch.object(
            runner, "_read_gatt_char", new=AsyncMock(return_value=bytearray(jmc.pin("8264")))
        ),
    ):
        await runner._read_characteristic(MagicMock(), char_info, runner._client)

    assert char_info.read_result is not None
    assert char_info.read_result["hex"] == "**REDACTED**"
