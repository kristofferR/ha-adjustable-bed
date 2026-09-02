"""Tests for Adjustable Bed config flow."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from copy import copy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import (
    SOURCE_BLUETOOTH,
    SOURCE_IGNORE,
    SOURCE_USER,
    ConfigEntryState,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.address_lock import async_get_connect_lock
from custom_components.adjustable_bed.bluetooth_bond import (
    BluezReadStatus,
    BondRemovalResult,
    BondRemovalStatus,
    LocalBondInventory,
    LocalBondRecord,
)
from custom_components.adjustable_bed.bluetooth_freshness import (
    AdvertisementEvidence,
    FreshnessStatus,
)
from custom_components.adjustable_bed.bluetooth_freshness import (
    _monotonic as freshness_monotonic,
)
from custom_components.adjustable_bed.bluetooth_transport import (
    ConnectionPath,
    PathPrediction,
    TransportClass,
)
from custom_components.adjustable_bed.bond_verification import (
    CONF_BLE_BOND_CONTEXT,
    BondEvidence,
    BondOwner,
    BondVerificationStatus,
)
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    NotAdvertisingError,
    _default_motor_count,
    _is_valid_motor_count,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_COOLBASE,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JIECANG,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LINAK,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REVERIE,
    BED_TYPE_RICHMAT,
    BED_TYPE_RONDURE,
    BED_TYPE_SBI,
    BED_TYPE_SERTA,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SOLACE,
    BED_TYPE_SUTA,
    BED_TYPE_TIMOTION_AHF,
    BED_TYPE_VIBRADORM,
    BEDS_WITH_POSITION_FEEDBACK,
    BEDS_WITHOUT_ANGLE_FEEDBACK,
    CONF_BACK_MAX_ANGLE,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ATTEMPTED_SOURCE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_BLE_BOND_MARKER_UNRELIABLE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISABLE_DISCOVERY,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_KAIDI_ADV_TYPE,
    CONF_KAIDI_PRODUCT_ID,
    CONF_KAIDI_RESOLVED_VARIANT,
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_KAIDI_TARGET_VADDR,
    CONF_KAIDI_VARIANT_SOURCE,
    CONF_MALOUF_LAYOUT,
    CONF_MALOUF_MEMORY_SLOTS,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_MOTOR_PULSE_USER_SET,
    CONF_OCTO_PIN,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MEMBER_ADDRESSES,
    CONF_PAIR_MODE,
    CONF_PASSIVE_POSITION_RECONCILIATION,
    CONF_POSITION_MODE,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    CONF_SIDE,
    DOMAIN,
    KAIDI_VARIANT_SEAT_1,
    KEESON_VARIANT_ERGOMOTION,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_OKIN,
    MALOUF_LAYOUT_HILO,
    OCTO_VARIANT_STANDARD,
    OCTO_VARIANT_STAR2,
    PAIR_MODE_SEPARATE_ADDRESS,
    RICHMAT_REMOTE_LP_QRRM,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    RONDURE_VARIANT_SIDE_A,
    SBI_VARIANT_SIDE_B,
    SIDE_LEFT,
    SIDE_RIGHT,
    SUTA_SERVICE_UUID,
    TIMOTION_AHF_SERVICE_UUID,
    VARIANT_AUTO,
    get_motor_pulse_defaults,
    requires_pairing,
)
from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES, detect_bed_type
from custom_components.adjustable_bed.discovery_settings import (
    async_is_discovery_disabled,
    async_set_discovery_disabled,
)
from custom_components.adjustable_bed.kaidi_protocol import (
    KAIDI_ADV_TYPE_BROADCAST,
    KaidiAdvertisement,
)
from custom_components.adjustable_bed.pairing import get_child
from custom_components.adjustable_bed.setup_operation import (
    OperationOutcome,
    OperationResult,
    SetupAction,
)


def test_skips_setup_connection_probe_for_pairing_window_beds() -> None:
    """LP Comfort Connect (Gen2) must skip the disconnecting setup probe so its
    single pairing-window connection is left for setup (issue #385 review)."""
    from custom_components.adjustable_bed.config_flow import _skips_setup_connection_probe

    assert _skips_setup_connection_probe(BED_TYPE_LEGGETT_GEN2, "auto") is True
    assert _skips_setup_connection_probe(BED_TYPE_LEGGETT_PLATT, "auto") is True
    assert _skips_setup_connection_probe(BED_TYPE_LEGGETT_PLATT, "gen2") is True
    assert _skips_setup_connection_probe(BED_TYPE_LEGGETT_PLATT, None) is True
    # MlRM/Okin Leggett beds reconnect normally, so the probe is fine.
    assert _skips_setup_connection_probe(BED_TYPE_LEGGETT_PLATT, "mlrm") is False
    assert _skips_setup_connection_probe(BED_TYPE_LEGGETT_PLATT, "okin") is False
    # Unrelated beds are unaffected.
    assert _skips_setup_connection_probe(BED_TYPE_KEESON, "auto") is False
    assert _skips_setup_connection_probe(None, None) is False


def test_octo_one_motor_count_is_limited_to_standard_tv_lifts() -> None:
    """Only Standard OCTO supports the one-motor TV lift layout."""
    assert _default_motor_count(BED_TYPE_OCTO, "RTV") == 1
    assert _default_motor_count(BED_TYPE_OCTO, "RTV-1234") == 1
    assert _default_motor_count(BED_TYPE_OCTO, "RC2") == 2
    assert _is_valid_motor_count(BED_TYPE_OCTO, OCTO_VARIANT_STANDARD, 1)
    assert _is_valid_motor_count(BED_TYPE_OCTO, "auto", 1)
    assert not _is_valid_motor_count(BED_TYPE_OCTO, OCTO_VARIANT_STAR2, 1)
    assert not _is_valid_motor_count(BED_TYPE_LINAK, "auto", 1)


@pytest.fixture(autouse=True)
def _no_advertisement_wait():
    """Do not spend the real advertisement wait in tests.

    The probe waits a few seconds for a bed that is between advertising
    intervals. Every test here runs against a Bluetooth manager that has no
    history at all, so the wait can only ever time out - it would add seconds
    per test and prove nothing. The wait itself is covered in
    tests/test_bluetooth_freshness.py.
    """
    with (
        patch(
            "custom_components.adjustable_bed.config_flow._PROBE_ADVERTISEMENT_WAIT_SECONDS",
            0.0,
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.ADVERTISEMENT_WAIT_SECONDS",
            0.0,
        ),
    ):
        yield


async def _advance_only_progress(hass: HomeAssistant, result: Any) -> Any:
    """Poll one background operation without crossing another form."""
    for _ in range(20):
        if result["type"] != FlowResultType.SHOW_PROGRESS:
            return result
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
    raise AssertionError("the progress step never completed")


async def _complete_setup_pairing(hass: HomeAssistant, result: Any) -> Any:
    """Model a successful bond and return the setup step that follows it."""
    if not (
        result["type"] == FlowResultType.FORM
        and result.get("step_id") in {"bluetooth_pairing", "manual_pairing"}
    ):
        return result

    # Pairing behavior itself has dedicated tests below. General setup tests
    # need a deterministic positive bond before they exercise their own step.
    with (
        patch.object(
            AdjustableBedConfigFlow,
            "_attempt_pairing",
            new=AsyncMock(return_value=_verified_evidence()),
        ),
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK)),
    ):
        action_marker = next(
            marker for marker in result["data_schema"].schema if str(marker) == "action"
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"action": action_marker.default()}
        )
        result = await _advance_only_progress(hass, result)
        assert result["step_id"] == "pairing_result"
        finish_input = (
            {"action": "finish"}
            if any(str(marker) == "action" for marker in result["data_schema"].schema)
            else {}
        )
        return await hass.config_entries.flow.async_configure(result["flow_id"], finish_input)


async def _advance_progress(hass: HomeAssistant, result: Any) -> Any:
    """Drive pairing and background work through to the next stable form."""
    for _ in range(20):
        result = await _complete_setup_pairing(hass, result)
        if result["type"] != FlowResultType.SHOW_PROGRESS:
            return result
        result = await _advance_only_progress(hass, result)
    raise AssertionError("the setup flow never reached a stable step")


class TestPairingInstructions:
    """Test bed-specific pairing guidance."""

    async def test_sleep_number_pairing_instructions_use_side_button(
        self, hass: HomeAssistant
    ) -> None:
        """Sleep Number should show its side-button pairing guidance."""
        flow = AdjustableBedConfigFlow()
        flow.hass = hass

        with patch(
            "custom_components.adjustable_bed.config_flow.async_get_translations",
            new=AsyncMock(
                return_value={
                    (
                        "component.adjustable_bed.config.step.bluetooth_pairing."
                        "data_description.pairing_instructions_sleep_number"
                    ): (
                        "1. Put your bed in pairing mode (hold the side pairing button until the blue light blinks)\n"
                        "2. Click 'Pair Now'"
                    )
                }
            ),
        ):
            instructions = await flow._get_pairing_instructions(BED_TYPE_SLEEP_NUMBER)

        assert "side pairing button" in instructions
        assert "blue light blinks" in instructions

    async def test_default_pairing_instructions_remain_generic(self, hass: HomeAssistant) -> None:
        """Other pairing-required beds should keep the generic fallback guidance."""
        flow = AdjustableBedConfigFlow()
        flow.hass = hass

        with patch(
            "custom_components.adjustable_bed.config_flow.async_get_translations",
            new=AsyncMock(
                return_value={
                    (
                        "component.adjustable_bed.config.step.bluetooth_pairing."
                        "data_description.pairing_instructions_generic"
                    ): (
                        "1. Put your bed in pairing mode (hold lamp button until blue light blinks, or unplug for 30+ seconds)\n"
                        "2. Click 'Pair Now'"
                    )
                }
            ),
        ):
            instructions = await flow._get_pairing_instructions(BED_TYPE_VIBRADORM)

        assert "lamp button" in instructions
        assert "unplug for 30+ seconds" in instructions

    @pytest.mark.parametrize(
        "bed_type",
        [BED_TYPE_OKIN_UUID, BED_TYPE_OKIN_CST, BED_TYPE_OKIN_RF_ECO_BT],
    )
    async def test_okin_pairing_instructions_use_power_cycle_guidance(
        self, hass: HomeAssistant, bed_type: str
    ) -> None:
        """Okin UUID/CST/RF ECO BT beds should not suggest the RF pairing button."""
        flow = AdjustableBedConfigFlow()
        flow.hass = hass

        with patch(
            "custom_components.adjustable_bed.config_flow.async_get_translations",
            new=AsyncMock(
                return_value={
                    (
                        "component.adjustable_bed.config.step.bluetooth_pairing."
                        "data_description.pairing_instructions_okin"
                    ): (
                        "1. Power-cycle the OKIN control box, or hold the under-bed lamp button "
                        "until its light blinks. The Pair/Learn button only syncs the RF remote.\n"
                        "2. While the light is active, click 'Pair Now'."
                    )
                }
            ),
        ):
            instructions = await flow._get_pairing_instructions(bed_type)

        assert "Power-cycle the OKIN control box" in instructions
        assert "under-bed lamp button" in instructions
        assert "Pair/Learn button only syncs the RF remote" in instructions

    async def test_okin_rf_eco_bt_requires_pairing(self) -> None:
        """RF ECO BT should request BLE pairing before authenticated OKIN writes."""
        assert requires_pairing(BED_TYPE_OKIN_RF_ECO_BT)

    async def test_okin_cst_uses_fixed_three_motor_layout_without_position_feedback(
        self,
    ) -> None:
        """The MFirm profile has three motors but no decoded position state."""
        assert _default_motor_count(BED_TYPE_OKIN_CST) == 3
        assert _is_valid_motor_count(BED_TYPE_OKIN_CST, "auto", 3)
        assert not _is_valid_motor_count(BED_TYPE_OKIN_CST, "auto", 2)
        assert not _is_valid_motor_count(BED_TYPE_OKIN_CST, "auto", 4)
        assert BED_TYPE_OKIN_CST not in BEDS_WITH_POSITION_FEEDBACK
        assert BED_TYPE_OKIN_CST in BEDS_WITHOUT_ANGLE_FEEDBACK


class TestPairingPersistence:
    """Test that successful pairing is persisted on the created entry."""

    @staticmethod
    def _new_pairing_flow(hass: HomeAssistant) -> AdjustableBedConfigFlow:
        """Create a pairing flow with representative entry data."""
        flow = AdjustableBedConfigFlow()
        flow.hass = hass
        flow._manual_data = {
            CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
            CONF_NAME: "Paired Okimat",
            CONF_BED_TYPE: BED_TYPE_OKIMAT,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        }
        flow.context = {"source": SOURCE_USER}
        return flow

    @pytest.mark.parametrize("step", ["async_step_bluetooth_pairing", "async_step_manual_pairing"])
    async def test_pairing_step_recomputes_transport_warning(
        self, hass: HomeAssistant, step: str
    ) -> None:
        """The warning must reflect the adapter and protocol the user submitted."""
        flow = self._new_pairing_flow(hass)
        flow._manual_data[CONF_PREFERRED_ADAPTER] = "bedroom_proxy"
        describe = AsyncMock(return_value="Pairing over the selected proxy")

        with patch.object(flow, "_async_transport_note", new=describe):
            result = await getattr(flow, step)()

        assert result["description_placeholders"]["transport"] == (
            "Pairing over the selected proxy"
        )
        describe.assert_awaited_once_with(
            "AA:BB:CC:DD:EE:01",
            "bedroom_proxy",
            BED_TYPE_OKIMAT,
            None,
        )

    async def test_bluetooth_pairing_marks_bond_as_established(self, hass: HomeAssistant) -> None:
        """Pair Now should persist that the bed is already bonded."""
        flow = self._new_pairing_flow(hass)

        with (
            patch.object(
                flow, "_attempt_pairing", new=AsyncMock(return_value=_verified_evidence())
            ),
            _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK)),
        ):
            progress = await flow.async_step_bluetooth_pairing({"action": "pair_now"})
            assert progress["type"] is FlowResultType.SHOW_PROGRESS
            result = await _finish_pairing(hass, flow)

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_BLE_BOND_ESTABLISHED] is True
        # The marker records which transport owns the bond, so a later unpair
        # knows where to look.
        assert result["data"][CONF_BLE_BOND_CONTEXT]["transport"] == "local"

    @pytest.mark.parametrize("step", ["async_step_bluetooth_pairing", "async_step_manual_pairing"])
    async def test_gen2_pair_now_defers_the_bond_to_setup(
        self, hass: HomeAssistant, step: str
    ) -> None:
        """Pair Now must not spend LP Comfort Connect's one connection (#385).

        Pairing here would connect, bond and then disconnect, leaving
        async_setup_entry with a box that refuses every reconnect until it is
        power-cycled. Create the entry and let the coordinator's first
        connection carry the bond instead.
        """
        flow = self._new_pairing_flow(hass)
        flow._manual_data[CONF_BED_TYPE] = BED_TYPE_LEGGETT_GEN2

        attempt_pairing = AsyncMock(return_value=_verified_evidence())
        with (
            patch.object(flow, "_attempt_pairing", new=attempt_pairing),
            _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK)),
        ):
            result = await getattr(flow, step)({"action": "pair_now"})

        assert result["type"] is FlowResultType.CREATE_ENTRY
        attempt_pairing.assert_not_awaited()
        # No bond marker: the coordinator must still request the bond.
        assert result["data"].get(CONF_BLE_BOND_ESTABLISHED) is not True

    @pytest.mark.parametrize("step", ["async_step_bluetooth_pairing", "async_step_manual_pairing"])
    async def test_an_existing_host_bond_is_proven_before_it_is_used(
        self, hass: HomeAssistant, step: str
    ) -> None:
        """BlueZ saying "paired" is not the bed accepting an authenticated write.

        A stale record looks identical to a good one, so this has to be proven
        over the air before setup claims the bond is usable (#461).
        """
        flow = self._new_pairing_flow(hass)
        inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
        attempt = AsyncMock(return_value=_verified_evidence())
        # The bond is only offerable when the path is provably local; an unknown
        # path cannot show that BlueZ's record is the one this bed will use.
        with (
            _patch_inventory(inventory),
            _patch_local_prediction(),
            patch.object(flow, "_attempt_pairing", attempt),
        ):
            progress = await getattr(flow, step)({"action": "use_existing_bond"})
            assert progress["type"] is FlowResultType.SHOW_PROGRESS
            result = await _finish_pairing(hass, flow)

        # Verified over the air, and without asking for a new bond.
        assert attempt.await_args.kwargs["request_bond"] is False
        assert flow._pairing_origin_step == step.removeprefix("async_step_")
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_BLE_BOND_ESTABLISHED] is True
        assert result["data"][CONF_BLE_BOND_CONTEXT]["source"] == "hci0"
        assert result["data"][CONF_BLE_BOND_CONTEXT]["adapter"] == "hci0"

    @pytest.mark.parametrize("step", ["async_step_bluetooth_pairing", "async_step_manual_pairing"])
    async def test_an_unprovable_existing_bond_is_not_accepted(
        self, hass: HomeAssistant, step: str
    ) -> None:
        """Without proof, fall back to pairing rather than record a bond."""
        flow = self._new_pairing_flow(hass)
        inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
        inconclusive = BondEvidence(
            status=BondVerificationStatus.INCONCLUSIVE,
            owner=BondOwner(transport=TransportClass.LOCAL, source="hci0"),
            operation="verify_existing_bond",
            observed_at="2026-07-27T00:00:00+00:00",
            error="timeout",
        )
        with (
            _patch_inventory(inventory),
            _patch_local_prediction(),
            patch.object(flow, "_attempt_pairing", AsyncMock(return_value=inconclusive)),
        ):
            await getattr(flow, step)({"action": "use_existing_bond"})
            await hass.async_block_till_done()
            await flow.async_step_pairing_progress()
            result = await flow.async_step_pairing_result()

        assert flow.operation.result is not None
        # Inconclusive, not failed: a timed-out check proves nothing either way,
        # and calling it a failure would push the user into replacing a bond
        # that may be working.
        assert flow.operation.result.outcome is OperationOutcome.BOND_VERIFICATION_INCONCLUSIVE
        assert result["type"] is FlowResultType.FORM
        assert "either way" in result["description_placeholders"]["outcome"]

    @pytest.mark.parametrize("step", ["async_step_bluetooth_pairing", "async_step_manual_pairing"])
    async def test_an_existing_host_bond_is_the_default_action(
        self, hass: HomeAssistant, step: str
    ) -> None:
        """Submitting the unchanged form must not pair over a proven bond."""
        flow = self._new_pairing_flow(hass)
        inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
        with _patch_inventory(inventory), _patch_local_prediction():
            result = await getattr(flow, step)(None)

        action_field = next(iter(result["data_schema"].schema))
        assert action_field.default() == "use_existing_bond"

    @pytest.mark.parametrize("step", ["async_step_bluetooth_pairing", "async_step_manual_pairing"])
    async def test_a_bond_on_another_local_adapter_is_not_offered(
        self, hass: HomeAssistant, step: str
    ) -> None:
        """A BlueZ bond is usable only through the adapter that owns it."""
        flow = self._new_pairing_flow(hass)
        inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
        with (
            _patch_inventory(inventory),
            _patch_local_prediction("22:33:44:55:66:77", "hci1"),
        ):
            result = await getattr(flow, step)(None)

        options = (
            result["data_schema"].schema[next(iter(result["data_schema"].schema))].config["options"]
        )
        assert options == ["pair_now"]

    @pytest.mark.parametrize("step", ["async_step_bluetooth_pairing", "async_step_manual_pairing"])
    async def test_a_bond_is_not_certified_when_another_route_could_win(
        self, hass: HomeAssistant, step: str
    ) -> None:
        """Certifying a bond persists a marker without ever connecting.

        Home Assistant re-ranks every connectable scanner inside connect(), so a
        proxy in range can take the connection the prediction gave to the bonded
        adapter. That transport holds no bond, and the marker then suppresses
        pairing.

        A bed that can be verified is safe either way, because the check connects
        and records the route it really took, so the action stays available and
        simply has to prove itself.
        """
        flow = self._new_pairing_flow(hass)
        inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
        contested = _patch_contested_prediction()

        with _patch_inventory(inventory), contested:
            result = await getattr(flow, step)(None)

        options = (
            result["data_schema"].schema[next(iter(result["data_schema"].schema))].config["options"]
        )
        # Both actions connect, so neither is asserting anything about a route.
        assert "use_existing_bond" in options
        assert "remove_bond_and_pair" in options

        # Choosing it starts the verification rather than creating an entry, so
        # no marker exists until something proved the bond over the air.
        with _patch_inventory(inventory), contested, patch.object(flow, "_attempt_pairing"):
            started = await getattr(flow, step)({"action": "use_existing_bond"})
        assert started["type"] is FlowResultType.SHOW_PROGRESS
        assert flow._pairing_mode == "verify_existing"
        assert flow._pairing_route_certain is False

    @pytest.mark.parametrize("step", ["async_step_bluetooth_pairing", "async_step_manual_pairing"])
    async def test_a_one_connection_bed_will_not_use_a_bond_it_cannot_prove(
        self, hass: HomeAssistant, step: str
    ) -> None:
        """The bed that cannot verify is the one that can least afford a wrong bet.

        It grants roughly one connection per pairing window, so setup must not
        spend it checking the bond, which leaves asserting the record from the
        prediction. If the connection then goes out over the proxy instead, that
        transport holds no bond and the marker suppresses pairing on the only
        link the bed will give: it stays dead until someone power-cycles it.
        """
        flow = self._new_pairing_flow(hass)
        flow._manual_data[CONF_BED_TYPE] = BED_TYPE_LEGGETT_GEN2
        inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
        contested = _patch_contested_prediction()

        with _patch_inventory(inventory), contested:
            result = await getattr(flow, step)(None)

        options = (
            result["data_schema"].schema[next(iter(result["data_schema"].schema))].config["options"]
        )
        assert "use_existing_bond" not in options
        assert next(iter(result["data_schema"].schema)).default() == "pair_now"
        # The form has to say why the action is missing. "No usable bond" would
        # be false: the bond is there, on a route that may well be the one used.
        assert "chooses which when it connects" in result["description_placeholders"]["bond_state"]

        # And it cannot be forced through by submitting it directly.
        with _patch_inventory(inventory), contested:
            refused = await getattr(flow, step)({"action": "use_existing_bond"})
        assert refused["type"] is not FlowResultType.CREATE_ENTRY

    async def test_a_deferred_bond_is_asserted_only_over_a_certain_route(
        self, hass: HomeAssistant
    ) -> None:
        """The certifying short-circuit is where a wrong prediction is persisted."""
        flow = self._new_pairing_flow(hass)
        flow._manual_data[CONF_BED_TYPE] = BED_TYPE_LEGGETT_GEN2
        flow._pairing_mode = "verify_existing"
        flow._pairing_verify_record = _bond_record()
        prediction = PathPrediction(chosen=None, paths=())

        flow._pairing_route_certain = True
        certified = await flow._async_start_pairing_operation("AA:BB:CC:DD:EE:01", prediction)
        assert certified["type"] is FlowResultType.CREATE_ENTRY
        assert certified["data"][CONF_BLE_BOND_ESTABLISHED] is True

        flow._pairing_route_certain = False
        deferred = await flow._async_start_pairing_operation("AA:BB:CC:DD:EE:01", prediction)
        # Still no connection spent, but nothing is claimed either: the
        # coordinator asks to pair, which costs nothing if the bond is there.
        assert deferred["type"] is FlowResultType.CREATE_ENTRY
        assert deferred["data"].get(CONF_BLE_BOND_ESTABLISHED) is not True
        assert CONF_BLE_BOND_CONTEXT not in deferred["data"]

    @pytest.mark.parametrize("step", ["async_step_bluetooth_pairing", "async_step_manual_pairing"])
    async def test_a_bond_is_not_certified_against_a_momentarily_busy_route(
        self, hass: HomeAssistant, step: str
    ) -> None:
        """A proxy with no free slot right now is still a possible bond owner.

        ``can_connect`` is free-slot state and nothing else, so a proxy that is
        out of slots while the form is drawn can have one free by the time the
        entry makes its first connection. Certifying against that snapshot bets
        on a value that changes, which is the whole reason the predicted path
        cannot be trusted either.

        On this branch the certifying short-circuit is the only path that
        asserts a bond without connecting, so that is where the busy route has
        to be counted. The ordinary action still connects and proves itself.
        """
        flow = self._new_pairing_flow(hass)
        flow._manual_data[CONF_BED_TYPE] = BED_TYPE_LEGGETT_GEN2
        inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
        bonded = ConnectionPath(
            source="11:22:33:44:55:66", transport=TransportClass.LOCAL, adapter="hci0"
        )
        busy_proxy = ConnectionPath(
            source="bedroom-proxy",
            transport=TransportClass.PROXY,
            can_connect=False,
        )
        contested = patch(
            "custom_components.adjustable_bed.config_flow.async_predict_path",
            return_value=PathPrediction(chosen=bonded, paths=(bonded, busy_proxy)),
        )

        # A bed that defers pairing cannot prove anything, so the action is
        # withheld rather than offered as a duplicate of Pair now.
        with _patch_inventory(inventory), contested:
            result = await getattr(flow, step)(None)

        options = (
            result["data_schema"].schema[next(iter(result["data_schema"].schema))].config["options"]
        )
        assert "use_existing_bond" not in options
        assert "route" in result["description_placeholders"]["bond_state"].lower()

        # And submitting it anyway certifies nothing: the action matches no
        # branch, so the form is redrawn rather than an entry created.
        with _patch_inventory(inventory), contested, patch.object(flow, "_attempt_pairing"):
            refused = await getattr(flow, step)({"action": "use_existing_bond"})
        assert refused["type"] is FlowResultType.FORM

    @pytest.mark.parametrize("step", ["async_step_bluetooth_pairing", "async_step_manual_pairing"])
    async def test_a_one_connection_bed_cannot_replace_an_existing_bond(
        self, hass: HomeAssistant, step: str
    ) -> None:
        """Replacement cannot run when setup must preserve the first link."""
        flow = self._new_pairing_flow(hass)
        flow._manual_data[CONF_BED_TYPE] = BED_TYPE_LEGGETT_GEN2
        inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
        with _patch_inventory(inventory), _patch_local_prediction():
            result = await getattr(flow, step)(None)

        options = (
            result["data_schema"].schema[next(iter(result["data_schema"].schema))].config["options"]
        )
        assert options == ["pair_now", "use_existing_bond"]

        with _patch_inventory(inventory), _patch_local_prediction():
            rejected = await getattr(flow, step)({"action": "remove_bond_and_pair"})
        assert rejected["type"] is FlowResultType.FORM
        assert flow._pairing_remove_record is None

    @pytest.mark.parametrize("step", ["async_step_bluetooth_pairing", "async_step_manual_pairing"])
    async def test_an_existing_bond_is_not_offered_without_a_proven_local_path(
        self, hass: HomeAssistant, step: str
    ) -> None:
        """Not-a-proxy is not the same as provably the host."""
        flow = self._new_pairing_flow(hass)
        inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
        with _patch_inventory(inventory):
            result = await getattr(flow, step)(None)

        options = (
            result["data_schema"].schema[next(iter(result["data_schema"].schema))].config["options"]
        )
        assert options == ["pair_now"]

    @pytest.mark.parametrize("step", ["async_step_bluetooth_pairing", "async_step_manual_pairing"])
    async def test_using_an_existing_bond_is_not_offered_without_one(
        self, hass: HomeAssistant, step: str
    ) -> None:
        """The old Skip button asserted a bond nothing had checked for."""
        flow = self._new_pairing_flow(hass)
        inventory = LocalBondInventory(status=BluezReadStatus.OK, records=())
        with _patch_inventory(inventory):
            result = await getattr(flow, step)(None)

        assert result["type"] is FlowResultType.FORM
        options = (
            result["data_schema"].schema[next(iter(result["data_schema"].schema))].config["options"]
        )
        assert options == ["pair_now"]

    async def test_a_proxy_path_never_claims_an_existing_bond(self, hass: HomeAssistant) -> None:
        """Host BlueZ state says nothing about a bond stored on a proxy."""
        flow = self._new_pairing_flow(hass)
        inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
        proxy = ConnectionPath(source="proxy", transport=TransportClass.PROXY)
        with (
            _patch_inventory(inventory),
            patch(
                "custom_components.adjustable_bed.config_flow.async_predict_path",
                return_value=PathPrediction(chosen=proxy, paths=(proxy,)),
            ),
        ):
            result = await flow.async_step_bluetooth_pairing(None)

        options = (
            result["data_schema"].schema[next(iter(result["data_schema"].schema))].config["options"]
        )
        assert options == ["pair_now"]
        assert (
            "cannot read or remove a bond stored on a proxy"
            in (result["description_placeholders"]["bond_state"])
        )

    async def test_a_proxy_winning_prediction_does_not_hide_a_visible_host_bond(
        self, hass: HomeAssistant
    ) -> None:
        """Verification pins the bonded host route and checks the actual route.

        A proxy with the strongest signal may win the advisory prediction while
        the bonded local adapter remains in range. That is enough to offer a
        verification attempt, not enough to certify anything without connecting.
        """
        flow = self._new_pairing_flow(hass)
        inventory = LocalBondInventory(
            status=BluezReadStatus.OK,
            records=(_bond_record(adapter_address=None),),
        )
        proxy = ConnectionPath(
            source="bedroom-proxy",
            transport=TransportClass.PROXY,
        )
        bonded = ConnectionPath(
            source="11:22:33:44:55:66",
            transport=TransportClass.LOCAL,
            adapter="hci0",
        )
        prediction = patch(
            "custom_components.adjustable_bed.config_flow.async_predict_path",
            return_value=PathPrediction(
                chosen=proxy,
                paths=(proxy, bonded),
            ),
        )

        with _patch_inventory(inventory), prediction:
            result = await flow.async_step_bluetooth_pairing()

        field = next(iter(result["data_schema"].schema))
        options = result["data_schema"].schema[field].config["options"]
        assert "use_existing_bond" in options
        # Replacement still follows the selected route's separate safety gate.
        assert "remove_bond_and_pair" not in options

        with (
            _patch_inventory(inventory),
            prediction,
            patch.object(flow, "_async_start_pairing_operation", AsyncMock()),
        ):
            await flow.async_step_bluetooth_pairing({"action": "use_existing_bond"})

        assert flow._pairing_verify_source == "11:22:33:44:55:66"
        assert flow._pairing_route_certain is False

    async def test_leggett_gen2_pairs_after_service_discovery(self, hass: HomeAssistant) -> None:
        """LP Comfort Connect must connect and discover GATT before bonding."""
        flow = self._new_pairing_flow(hass)
        flow._manual_data[CONF_BED_TYPE] = BED_TYPE_LEGGETT_GEN2

        service_info = MagicMock()
        service_info.address = flow._manual_data[CONF_ADDRESS]
        service_info.source = "local"
        service_info.connectable = True
        service_info.device = MagicMock()

        events: list[str] = []
        client = MagicMock()

        async def pair() -> None:
            events.append("pair")

        async def disconnect() -> None:
            events.append("disconnect")

        client.pair = AsyncMock(side_effect=pair)
        client.disconnect = AsyncMock(side_effect=disconnect)

        async def establish(*_args: object, **_kwargs: object) -> MagicMock:
            events.append("connect")
            return client

        with (
            _patch_pairing_gate(),
            patch(
                "bleak_retry_connector.establish_connection",
                new=AsyncMock(side_effect=establish),
            ) as mock_establish,
        ):
            evidence = await flow._attempt_pairing(flow._manual_data[CONF_ADDRESS])
        # This protocol has no evidence-backed Device Information verifier.
        # Pairing still runs after service discovery, but an unrelated read
        # must not be presented as proof that the resulting bond works.
        assert evidence.status is BondVerificationStatus.UNSUPPORTED

        assert events == ["connect", "pair", "disconnect"]
        # The keyword is omitted rather than passed False: this bed bonds after
        # service discovery, so the backend is never asked to bond on connect,
        # and older connectors without the keyword must not raise here.
        assert "pair" not in mock_establish.await_args.kwargs
        assert mock_establish.await_args.kwargs["use_services_cache"] is False

    async def test_leggett_gen2_pair_failure_disconnects(self, hass: HomeAssistant) -> None:
        """A failed post-discovery bond must not leave the GATT link open."""
        flow = self._new_pairing_flow(hass)
        flow._manual_data[CONF_BED_TYPE] = BED_TYPE_LEGGETT_GEN2

        service_info = MagicMock()
        service_info.address = flow._manual_data[CONF_ADDRESS]
        service_info.source = "local"
        service_info.connectable = True
        service_info.device = MagicMock()

        client = MagicMock()
        client.pair = AsyncMock(side_effect=BleakError("pairing rejected"))
        client.disconnect = AsyncMock()

        with (
            _patch_pairing_gate(),
            patch(
                "bleak_retry_connector.establish_connection",
                new=AsyncMock(return_value=client),
            ),
            pytest.raises(BleakError, match="pairing rejected"),
        ):
            await flow._attempt_pairing(flow._manual_data[CONF_ADDRESS])

        client.disconnect.assert_awaited_once_with()

    async def test_other_beds_keep_pair_during_connection(self, hass: HomeAssistant) -> None:
        """Existing pairing-required protocols keep the standard Bleak path."""
        flow = self._new_pairing_flow(hass)

        service_info = MagicMock()
        service_info.address = flow._manual_data[CONF_ADDRESS]
        service_info.source = "local"
        service_info.connectable = True
        service_info.device = MagicMock()

        client = MagicMock()
        client.pair = AsyncMock()
        client.disconnect = AsyncMock()

        with (
            _patch_pairing_gate(),
            patch(
                "bleak_retry_connector.establish_connection",
                new=AsyncMock(return_value=client),
            ) as mock_establish,
        ):
            evidence = await flow._attempt_pairing(flow._manual_data[CONF_ADDRESS])
        # A MagicMock client makes the auth-gated read non-awaitable, so
        # verification lands in its generic-error branch. Pin that rather than
        # "not AUTH_FAILED", which would keep passing if verification broke.
        assert evidence.status is BondVerificationStatus.INCONCLUSIVE

        assert mock_establish.await_args.kwargs["pair"] is True
        assert mock_establish.await_args.kwargs["use_services_cache"] is True
        client.pair.assert_not_awaited()
        client.disconnect.assert_awaited_once()


class TestDetectBedType:
    """Test bed type detection."""

    def test_detect_linak_bed(self, mock_bluetooth_service_info: BluetoothServiceInfoBleak):
        """Test detection of Linak bed."""
        bed_type = detect_bed_type(mock_bluetooth_service_info)
        assert bed_type == BED_TYPE_LINAK

    def test_detect_linak_bed_by_name(self, mock_bluetooth_service_info: BluetoothServiceInfoBleak):
        """Test detection of Linak bed by name pattern when no service UUIDs advertised."""
        # Some Linak beds don't advertise service UUIDs in their BLE beacon
        mock_bluetooth_service_info.name = "Bed 1696"
        mock_bluetooth_service_info.service_uuids = []
        bed_type = detect_bed_type(mock_bluetooth_service_info)
        assert bed_type == BED_TYPE_LINAK

    def test_detect_richmat_nordic_bed(self, mock_bluetooth_service_info_richmat):
        """Test detection of Richmat bed (Nordic variant)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_richmat)
        assert bed_type == BED_TYPE_RICHMAT

    def test_detect_richmat_wilinke_bed(self, mock_bluetooth_service_info_richmat_wilinke):
        """Test detection of Richmat bed (WiLinke variant)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_richmat_wilinke)
        assert bed_type == BED_TYPE_RICHMAT

    def test_detect_keeson_bed(self, mock_bluetooth_service_info_keeson):
        """Test detection of Keeson bed."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_keeson)
        assert bed_type == BED_TYPE_KEESON

    def test_detect_motosleep_bed(self, mock_bluetooth_service_info_motosleep):
        """Test detection of MotoSleep bed (by HHC name prefix)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_motosleep)
        assert bed_type == BED_TYPE_MOTOSLEEP

    def test_detect_suta_bed(self):
        """Test detection of SUTA bed by name + FFF0 service."""
        service_info = MagicMock()
        service_info.name = "SUTA-B803"
        service_info.address = "AA:11:22:33:44:55"
        service_info.service_uuids = [SUTA_SERVICE_UUID]
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_SUTA

    def test_detect_timotion_ahf_bed(self):
        """Test detection of TiMOTION AHF bed by name + Nordic UART service."""
        service_info = MagicMock()
        service_info.name = "AHF-1234"
        service_info.address = "AA:11:22:33:44:56"
        service_info.service_uuids = [TIMOTION_AHF_SERVICE_UUID]
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_TIMOTION_AHF

    def test_detect_leggett_platt_bed(self, mock_bluetooth_service_info_leggett):
        """Test detection of Leggett & Platt bed (Gen2)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_leggett)
        assert bed_type == BED_TYPE_LEGGETT_GEN2

    def test_detect_reverie_bed(self, mock_bluetooth_service_info_reverie):
        """Test detection of Reverie bed."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_reverie)
        assert bed_type == BED_TYPE_REVERIE

    def test_detect_okimat_bed(self, mock_bluetooth_service_info_okimat):
        """Test detection of Okimat bed."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_okimat)
        assert bed_type == BED_TYPE_OKIMAT

    def test_detect_unknown_device(
        self, mock_bluetooth_service_info_unknown: BluetoothServiceInfoBleak
    ):
        """Test detection returns None for unknown device."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_unknown)
        assert bed_type is None

    def test_detect_motosleep_lowercase_name(self):
        """Test MotoSleep detection with lowercase HHC prefix."""
        service_info = MagicMock()
        service_info.name = "hhc1234567890"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_MOTOSLEEP

    def test_detect_ergomotion_bed(self, mock_bluetooth_service_info_ergomotion):
        """Test detection of Ergomotion bed by name."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_ergomotion)
        assert bed_type == BED_TYPE_ERGOMOTION

    def test_detect_ergomotion_ergo_name(self):
        """Test Ergomotion detection with 'ergo' in name."""
        service_info = MagicMock()
        service_info.name = "Ergo Adjust Pro"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_ERGOMOTION

    def test_detect_ergomotion_serta_i_name(self):
        """Test Ergomotion detection with 'serta-i' prefix (e.g., Serta-i490350)."""
        service_info = MagicMock()
        service_info.name = "Serta-i490350"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_ERGOMOTION

    def test_detect_keeson_base_i4_name(self):
        """Test Keeson detection with 'base-i4.' prefix (e.g., base-i4.00002574)."""
        service_info = MagicMock()
        service_info.name = "base-i4.00002574"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_KEESON

    def test_detect_coolbase_base_i5_name(self):
        """Test Cool Base detection with 'base-i5.' prefix (e.g., base-i5.00000682).

        Cool Base is a Keeson BaseI5 variant with additional fan control.
        """
        service_info = MagicMock()
        service_info.name = "base-i5.00000682"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_COOLBASE

    def test_detect_keeson_ksbt_name(self):
        """Test Keeson detection with 'KSBT' prefix (e.g., KSBT03C000015046)."""
        service_info = MagicMock()
        service_info.name = "KSBT03C000015046"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_KEESON

    def test_detect_richmat_qrrm_name(self):
        """Test Richmat detection with 'QRRM' prefix (e.g., QRRM157052)."""
        service_info = MagicMock()
        service_info.name = "QRRM157052"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_RICHMAT

    def test_detect_richmat_sleep_function_name(self):
        """Test Richmat detection with 'Sleep Function' prefix (I7RM remote)."""
        service_info = MagicMock()
        service_info.name = "Sleep Function 2.0"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_RICHMAT

    def test_detect_okimat_okin_prefix_name(self):
        """Test Okimat detection with 'OKIN-' prefix (e.g., OKIN-346311)."""
        from custom_components.adjustable_bed.const import OKIMAT_SERVICE_UUID

        service_info = MagicMock()
        service_info.name = "OKIN-346311"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = [OKIMAT_SERVICE_UUID]
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_OKIMAT

    def test_detect_jiecang_bed(self, mock_bluetooth_service_info_jiecang):
        """Test detection of Jiecang bed by name (JC- prefix)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_jiecang)
        assert bed_type == BED_TYPE_JIECANG

    def test_detect_jiecang_glide_name(self):
        """Test Jiecang detection with 'glide' in name."""
        service_info = MagicMock()
        service_info.name = "Glide Smart Base"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_JIECANG

    def test_detect_jiecang_dream_motion_name(self):
        """Test Jiecang detection with 'dream motion' in name."""
        service_info = MagicMock()
        service_info.name = "Dream Motion Base"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_JIECANG

    def test_detect_dewertokin_bed(self, mock_bluetooth_service_info_dewertokin):
        """Test detection of DewertOkin bed by name (A H Beard)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_dewertokin)
        assert bed_type == BED_TYPE_DEWERTOKIN

    def test_detect_dewertokin_dewert_name(self):
        """Test DewertOkin detection with 'dewert' in name."""
        service_info = MagicMock()
        service_info.name = "Dewert Base"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_DEWERTOKIN

    def test_detect_dewertokin_hankook_name(self):
        """Test DewertOkin detection with 'hankook' in name."""
        service_info = MagicMock()
        service_info.name = "HankookGallery Bed"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_DEWERTOKIN

    def test_detect_serta_bed(self, mock_bluetooth_service_info_serta):
        """Test detection of Serta bed by name - now returns BED_TYPE_SERTA."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_serta)
        assert bed_type == BED_TYPE_SERTA

    def test_detect_serta_motion_perfect_name(self):
        """Test Serta detection with 'motion perfect' in name - returns BED_TYPE_SERTA."""
        service_info = MagicMock()
        service_info.name = "Motion Perfect III"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_SERTA

    def test_detect_octo_bed(self, mock_bluetooth_service_info_octo):
        """Test detection of Octo bed by name containing 'octo'."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_octo)
        assert bed_type == BED_TYPE_OCTO

    def test_detect_octo_rc2_receiver(self, mock_bluetooth_service_info_octo_rc2):
        """Test detection of Octo RC2 receiver - defaults to Octo for shared UUID.

        Issue #73: Devices like RC2 that share the Solace UUID but don't have
        'solace' in the name should default to Octo since it's more common.
        """
        bed_type = detect_bed_type(mock_bluetooth_service_info_octo_rc2)
        assert bed_type == BED_TYPE_OCTO

    def test_unproven_solace_name_defaults_to_octo(
        self, mock_bluetooth_service_info_unproven_solace_name
    ):
        """Do not treat an unproven marketing-name substring as protocol evidence."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_unproven_solace_name)
        assert bed_type == BED_TYPE_OCTO

    def test_detect_solace_bed_pattern(self, mock_bluetooth_service_info_solace_pattern):
        """Test detection of Solace bed by naming pattern like S4-Y-192-461000AD."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_solace_pattern)
        assert bed_type == BED_TYPE_SOLACE

    def test_detect_octo_star2_bed(self, mock_bluetooth_service_info_octo_star2):
        """Test detection of Octo Star2 bed by service UUID (not by name)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_octo_star2)
        assert bed_type == BED_TYPE_OCTO

    def test_detect_leggett_platt_mlrm_bed(self, mock_bluetooth_service_info_leggett_platt_richmat):
        """Test detection of Leggett & Platt MlRM variant bed (MlRM prefix).

        MlRM beds are now detected as BED_TYPE_LEGGETT_WILINKE.
        """
        bed_type = detect_bed_type(mock_bluetooth_service_info_leggett_platt_richmat)
        assert bed_type == BED_TYPE_LEGGETT_WILINKE

    def test_detect_leggett_platt_mlrm_case_insensitive(self):
        """Test L&P MlRM detection is case-insensitive (name is lowercased)."""
        # Test with uppercase MLRM
        service_info = MagicMock()
        service_info.name = "MLRM123456"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = [RICHMAT_WILINKE_SERVICE_UUIDS[1]]
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_LEGGETT_WILINKE

    def test_detect_leggett_mlrm_vs_generic_richmat(self):
        """Test L&P MlRM takes precedence over generic Richmat for mlrm prefix.

        Both L&P MlRM and generic Richmat use WiLinke UUIDs, but beds with
        'mlrm' prefix should be detected as L&P.
        """
        # Same UUID as generic Richmat WiLinke, but with mlrm prefix
        service_info = MagicMock()
        service_info.name = "mlrm157052"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = [RICHMAT_WILINKE_SERVICE_UUIDS[0]]  # First WiLinke UUID
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_LEGGETT_WILINKE

        # Verify generic Richmat still works for non-mlrm names
        service_info.name = "Generic WiLinke Bed"
        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_RICHMAT

    def test_detect_leggett_mlrm_without_service_uuid(self):
        """Test L&P MlRM needs both name pattern AND WiLinke service UUID.

        If the name matches but UUID doesn't, it should not be detected as L&P MlRM.
        """
        service_info = MagicMock()
        service_info.name = "MlRM157052"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []  # No service UUIDs
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        # Should NOT detect as L&P MlRM without UUID
        assert bed_type is None


class TestPinValidation:
    """Test PIN validation for Octo beds."""

    def test_valid_4_digit_pin(self):
        """Test that 4-digit PIN is accepted."""
        import voluptuous as vol

        validator = vol.All(str, vol.Match(r"^(\d{4})?$", msg="PIN must be exactly 4 digits"))
        assert validator("1234") == "1234"
        assert validator("0000") == "0000"
        assert validator("9999") == "9999"

    def test_empty_pin_allowed(self):
        """Test that empty PIN (no PIN) is allowed."""
        import voluptuous as vol

        validator = vol.All(str, vol.Match(r"^(\d{4})?$", msg="PIN must be exactly 4 digits"))
        assert validator("") == ""

    def test_invalid_pin_too_short(self):
        """Test that PIN shorter than 4 digits is rejected."""
        import voluptuous as vol

        validator = vol.All(str, vol.Match(r"^(\d{4})?$", msg="PIN must be exactly 4 digits"))
        with pytest.raises(vol.Invalid):
            validator("123")
        with pytest.raises(vol.Invalid):
            validator("1")

    def test_invalid_pin_too_long(self):
        """Test that PIN longer than 4 digits is rejected."""
        import voluptuous as vol

        validator = vol.All(str, vol.Match(r"^(\d{4})?$", msg="PIN must be exactly 4 digits"))
        with pytest.raises(vol.Invalid):
            validator("12345")
        with pytest.raises(vol.Invalid):
            validator("123456")

    def test_invalid_pin_non_digits(self):
        """Test that PIN with non-digit characters is rejected."""
        import voluptuous as vol

        validator = vol.All(str, vol.Match(r"^(\d{4})?$", msg="PIN must be exactly 4 digits"))
        with pytest.raises(vol.Invalid):
            validator("abcd")
        with pytest.raises(vol.Invalid):
            validator("12ab")


def _patch_pairing_gate(source: str = "hci0", rssi: int = -55):
    """Make the pairing attempt see a bed that is advertising right now."""
    path = ConnectionPath(source=source, transport=TransportClass.LOCAL, rssi=rssi)
    evidence = AdvertisementEvidence(
        status=FreshnessStatus.FRESH, age_seconds=1.0, rssi=rssi, source=source, path=path
    )
    return patch(
        "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
        AsyncMock(return_value=(evidence, MagicMock())),
    )


def _verified_evidence(
    transport: TransportClass = TransportClass.LOCAL,
) -> BondEvidence:
    """Return the evidence a positively verified bond produces."""
    return BondEvidence(
        status=BondVerificationStatus.VERIFIED,
        owner=BondOwner(transport=transport, source="hci0", adapter="hci0"),
        operation="setup_pairing",
        observed_at="2026-07-27T00:00:00+00:00",
    )


async def _open_options_form(hass: HomeAssistant, entry_id: str) -> Any:
    """Open the options settings form.

    The options flow starts on a menu now, because removing a Bluetooth bond
    needs somewhere discoverable to live that is clearly not "delete the device"
    (issue #455). Settings are one menu choice in.
    """
    result = await hass.config_entries.options.async_init(entry_id)
    assert result["type"] == FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "settings"}
    )


class TestBluetoothDiscoveryFlow:
    """Test Bluetooth discovery flow."""

    async def test_bluetooth_discovery_identical_names_include_address(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """Discovery cards and confirmation distinguish beds with identical names."""
        raw_addresses = ("aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02")
        discovered_titles: list[dict[str, str]] = []

        for raw_address in raw_addresses:
            service_info = copy(mock_bluetooth_service_info)
            service_info.name = "LP BED CONTROL"
            service_info.address = raw_address

            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_BLUETOOTH},
                data=service_info,
            )

            address = raw_address.upper()
            progress = hass.config_entries.flow.async_get(result["flow_id"])
            title_placeholders = progress["context"]["title_placeholders"]
            discovered_titles.append(title_placeholders)
            assert title_placeholders == {
                "name": "LP BED CONTROL",
                "address": address,
            }
            assert result["description_placeholders"]["name"] == "LP BED CONTROL"
            assert result["description_placeholders"]["address"] == address

        assert discovered_titles[0] != discovered_titles[1]

    async def test_bluetooth_discovery_creates_entry(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """Test Bluetooth discovery initiates config flow."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"

    async def test_octo_rtv_discovery_defaults_to_one_motor(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_octo_rc2: MagicMock,
        enable_custom_integrations,
    ):
        """The official RTV name should select the safe one-motor lift layout."""
        mock_bluetooth_service_info_octo_rc2.name = "RTV"
        mock_bluetooth_service_info_octo_rc2.address = "EC:4E:1A:B5:39:98"

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_octo_rc2,
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"
        motor_count_marker = next(
            marker for marker in result["data_schema"].schema if marker.schema == CONF_MOTOR_COUNT
        )
        assert motor_count_marker.default() == 1

    async def test_octo_star2_discovery_uses_field_verified_pulse_defaults(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_octo_star2: MagicMock,
        enable_custom_integrations,
    ) -> None:
        """The dedicated Star2 UUID selects 3 pulses at a 50 ms cadence."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_octo_star2,
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"
        markers = {marker.schema: marker for marker in result["data_schema"].schema}
        assert markers[CONF_MOTOR_PULSE_COUNT].default() == "3"
        assert markers[CONF_MOTOR_PULSE_DELAY_MS].default() == "50"

    def test_disconnect_after_command_default_per_bed_type(self):
        """Beds that must hold the link open keep the option off; others get it on."""
        from custom_components.adjustable_bed.const import (
            BED_TYPE_COMFORT_MOTION,
            BED_TYPE_JENSEN,
            BED_TYPE_JIECANG,
            BED_TYPE_KAIDI,
            BED_TYPE_KEESON,
            BED_TYPE_LEGGETT_GEN2,
            BED_TYPE_LEGGETT_PLATT,
            BED_TYPE_LEGGETT_WILINKE,
            BED_TYPE_LIMOSS,
            BED_TYPE_LINAK,
            BED_TYPE_OCTO,
            BED_TYPE_OKIN_CB24,
            BED_TYPE_OKIN_CST,
            BED_TYPE_OKIN_ORE,
            BED_TYPE_OKIN_UUID,
            BED_TYPE_REVERIE,
            BED_TYPE_REVERIE_NIGHTSTAND,
            BED_TYPE_SLEEP_NUMBER,
            BED_TYPE_SLEEP_NUMBER_MCR,
            BED_TYPE_SLEEPSTAR,
            BED_TYPE_SLEEPYS_BOX25,
            BED_TYPE_SUTA,
            BED_TYPE_SVANE,
            BED_TYPE_VIBRADORM,
            KEESON_VARIANT_SINO,
            LEGGETT_VARIANT_GEN2,
            LEGGETT_VARIANT_MLRM,
            VARIANT_AUTO,
            disconnect_after_command_default_enabled,
        )

        assert disconnect_after_command_default_enabled(BED_TYPE_LINAK, VARIANT_AUTO) is True
        assert disconnect_after_command_default_enabled(BED_TYPE_ERGOMOTION, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_LEGGETT_GEN2, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_SLEEP_NUMBER_MCR, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_COMFORT_MOTION, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_JENSEN, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_JIECANG, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_KAIDI, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_KEESON, VARIANT_AUTO) is False
        assert (
            disconnect_after_command_default_enabled(BED_TYPE_KEESON, KEESON_VARIANT_SINO) is False
        )
        assert (
            disconnect_after_command_default_enabled(BED_TYPE_KEESON, KEESON_VARIANT_ERGOMOTION)
            is False
        )
        assert disconnect_after_command_default_enabled(BED_TYPE_LIMOSS, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_OCTO, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_OKIN_CB24, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_OKIN_CST, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_OKIMAT, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_OKIN_ORE, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_OKIN_UUID, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_REVERIE, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_REVERIE_NIGHTSTAND, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_SLEEP_NUMBER, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_SLEEPSTAR, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_SLEEPYS_BOX25, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_SUTA, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_SVANE, None) is False
        assert disconnect_after_command_default_enabled(BED_TYPE_VIBRADORM, None) is False
        # An umbrella type resolves through its explicit variant.
        assert (
            disconnect_after_command_default_enabled(BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_GEN2)
            is False
        )
        assert (
            disconnect_after_command_default_enabled(BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_MLRM)
            is False
        )
        assert (
            disconnect_after_command_default_enabled(BED_TYPE_LEGGETT_PLATT, VARIANT_AUTO) is False
        )
        assert disconnect_after_command_default_enabled(BED_TYPE_LEGGETT_WILINKE, None) is False
        # No bed type chosen yet (auto-detect): keep the conservative default.
        assert disconnect_after_command_default_enabled(None, None) is False

    async def test_discovery_defaults_to_freeing_the_link_after_each_command(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """A Linak bed accepts one BLE link, so hand it back after each command."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )

        assert result["step_id"] == "bluetooth_confirm"
        marker = next(
            marker
            for marker in result["data_schema"].schema
            if marker.schema == CONF_DISCONNECT_AFTER_COMMAND
        )
        assert marker.default() is True

    def test_ambiguous_disconnect_choice_is_confirmed_after_bed_type_change(self):
        """A second form distinguishes the old default from an explicit choice."""
        from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

        flow = AdjustableBedConfigFlow()

        assert (
            flow._disconnect_after_command_choice(
                {CONF_DISCONNECT_AFTER_COMMAND: True},
                BED_TYPE_LEGGETT_GEN2,
                None,
                True,
            )
            is None
        )
        assert (
            flow._disconnect_after_command_choice(
                {CONF_DISCONNECT_AFTER_COMMAND: False},
                BED_TYPE_LINAK,
                VARIANT_AUTO,
                False,
            )
            is None
        )

        # Once the follow-up form has rendered the selected protocol's default,
        # either old-default value is an unambiguous explicit choice.
        flow._disconnect_choice_confirmed = True
        assert (
            flow._disconnect_after_command_choice(
                {CONF_DISCONNECT_AFTER_COMMAND: True},
                BED_TYPE_LEGGETT_GEN2,
                None,
                True,
            )
            is True
        )
        assert (
            flow._disconnect_after_command_choice(
                {CONF_DISCONNECT_AFTER_COMMAND: False},
                BED_TYPE_LINAK,
                VARIANT_AUTO,
                False,
            )
            is False
        )
        flow._disconnect_choice_confirmed = False

        # A value differing from the rendered default remains an explicit choice.
        assert (
            flow._disconnect_after_command_choice(
                {CONF_DISCONNECT_AFTER_COMMAND: False},
                BED_TYPE_LINAK,
                VARIANT_AUTO,
                True,
            )
            is False
        )
        # An absent value from direct callers follows the chosen bed type.
        assert (
            flow._disconnect_after_command_choice(
                {},
                BED_TYPE_LINAK,
                VARIANT_AUTO,
                False,
            )
            is True
        )

    async def test_manual_entry_without_preselected_type_confirms_ambiguous_choice(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """Raw manual entry keeps the option and confirms it for the selected bed."""
        flow = AdjustableBedConfigFlow()
        flow.hass = hass
        flow.context = {"source": SOURCE_USER}

        result = await flow.async_step_manual_entry()
        disconnect_marker = next(
            marker
            for marker in result["data_schema"].schema
            if marker.schema == CONF_DISCONNECT_AFTER_COMMAND
        )
        assert disconnect_marker.default() is False

        result = await flow.async_step_manual_entry(
            {
                CONF_ADDRESS: "11:22:33:44:55:66",
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_NAME: "Manual Bed",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_DISCONNECT_AFTER_COMMAND: False,
            }
        )
        assert result["step_id"] == "disconnect_after_command"
        confirm_marker = next(iter(result["data_schema"].schema))
        assert confirm_marker.default() is True

        with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
            result = await flow.async_step_disconnect_after_command(
                {CONF_DISCONNECT_AFTER_COMMAND: False}
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_DISCONNECT_AFTER_COMMAND] is False

    async def test_explicitly_unchecking_disconnect_after_command_is_kept(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """A value that differs from the rendered default is the user's choice."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "My Bed",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_DISCONNECT_AFTER_COMMAND: False,
            },
        )
        result = await _advance_progress(hass, result)
        assert result["step_id"] == "verify_connection"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_DISCONNECT_AFTER_COMMAND] is False

    async def test_bluetooth_discovery_confirm(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """Test confirming Bluetooth discovery creates entry."""
        # Start the flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )

        # Confirm with user input
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "My Bed",
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        # Linak setup verifies reachability without requiring an OS bond.
        result = await _advance_progress(hass, result)
        assert result["step_id"] == "verify_connection"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "My Bed"
        assert result["data"][CONF_ADDRESS] == mock_bluetooth_service_info.address
        assert result["data"][CONF_BED_TYPE] == BED_TYPE_LINAK
        assert result["data"][CONF_MOTOR_COUNT] == 4
        assert result["data"][CONF_HAS_MASSAGE] is True
        # Creating an entry is also a user choice of cadence, so the provenance
        # marker must be set here and not only in the options flow: otherwise a
        # protocol migration would treat a deliberate value as legacy data.
        assert result["data"][CONF_MOTOR_PULSE_USER_SET] is True
        assert result["data"][CONF_DISABLE_ANGLE_SENSING] is False

    async def test_bluetooth_confirm_bed_type_dropdown_uses_display_names(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """Regression for #385: the confirm dropdown showed raw type slugs from
        SUPPORTED_BED_TYPES, with no "Diagnostic (unknown bed)" entry. It must use
        the same display-name options as the other selection paths."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )
        assert result["step_id"] == "bluetooth_confirm"

        bed_type_marker = next(
            marker for marker in result["data_schema"].schema if marker.schema == CONF_BED_TYPE
        )
        selector = result["data_schema"].schema[bed_type_marker]
        options = selector.config["options"]
        options_by_value = {option["value"]: option["label"] for option in options}

        assert bed_type_marker.default() == BED_TYPE_LINAK
        assert options_by_value[BED_TYPE_LINAK] == BED_TYPE_DISPLAY_NAMES[BED_TYPE_LINAK]
        assert options_by_value[BED_TYPE_DIAGNOSTIC] == "Diagnostic (unknown bed)"

    async def test_bluetooth_confirm_legacy_alias_default_stays_selectable(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_ambiguous_okin: MagicMock,
        enable_custom_integrations,
    ):
        """A legacy-alias bed type (absent from the display-name list) chosen via
        disambiguation must be prepended so the dropdown default stays valid."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_ambiguous_okin,
        )
        assert result["step_id"] == "bluetooth_disambiguate"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bed_type_choice": BED_TYPE_OKIMAT},
        )
        assert result["step_id"] == "bluetooth_confirm"

        bed_type_marker = next(
            marker for marker in result["data_schema"].schema if marker.schema == CONF_BED_TYPE
        )
        selector = result["data_schema"].schema[bed_type_marker]
        option_values = [option["value"] for option in selector.config["options"]]

        assert bed_type_marker.default() == BED_TYPE_OKIMAT
        assert option_values[0] == BED_TYPE_OKIMAT
        assert option_values.count(BED_TYPE_OKIMAT) == 1

    async def test_bluetooth_confirm_diagnostic_bed_type_creates_entry(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """Selecting "Diagnostic (unknown bed)" on the confirm step must create
        an entry so users can capture a support bundle (#385)."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )
        assert result["step_id"] == "bluetooth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_BED_TYPE: BED_TYPE_DIAGNOSTIC,
                CONF_NAME: "Mystery Bed",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        # A connectable scanner is mocked, so setup runs the probe behind a
        # progress view and then shows the verify_connection result step.
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        result = await _advance_progress(hass, result)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "verify_connection"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={},
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_BED_TYPE] == BED_TYPE_DIAGNOSTIC

    async def test_bluetooth_confirm_diagnostic_entry_created_when_probe_fails(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """A failed connection probe must not block a diagnostic entry: the
        whole point is capturing bundles for beds we cannot reach (#385)."""
        from custom_components.adjustable_bed.config_flow import CapabilityReport

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )
        assert result["step_id"] == "bluetooth_confirm"

        with patch.object(
            AdjustableBedConfigFlow,
            "_probe_capabilities",
            AsyncMock(return_value=CapabilityReport(device_found=False)),
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_BED_TYPE: BED_TYPE_DIAGNOSTIC,
                    CONF_NAME: "Unreachable Bed",
                    CONF_MOTOR_COUNT: 2,
                    CONF_HAS_MASSAGE: False,
                    CONF_DISABLE_ANGLE_SENSING: True,
                    CONF_PREFERRED_ADAPTER: "auto",
                },
            )

            # The probe failed, but the verify step is informational only.
            assert result["type"] == FlowResultType.SHOW_PROGRESS
            result = await _advance_progress(hass, result)
            assert result["type"] == FlowResultType.FORM
            assert result["step_id"] == "verify_connection"
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={},
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_BED_TYPE] == BED_TYPE_DIAGNOSTIC

    async def test_bluetooth_discovery_confirm_coerces_string_motor_count(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """Regression for #361: HA frontend submits the dropdown value as a string.

        ``vol.In([2, 3, 4])`` rejected ``"3"`` with "value must be one of [2, 3, 4]",
        blocking the config flow. The schema must coerce the string to an int.
        """
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "My Bed",
                # Frontend sends select-dropdown values as strings, not ints.
                CONF_MOTOR_COUNT: "3",
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        # Accepted input proceeds through the ordinary unbonded reachability check.
        result = await _advance_progress(hass, result)
        assert result["step_id"] == "verify_connection"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_MOTOR_COUNT] == 3

    async def test_bluetooth_discovery_duplicate_octo_names_warn_about_split_setup(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_octo_rc2: MagicMock,
        enable_custom_integrations,
    ):
        """Bluetooth discovery should warn when another Octo side is visible."""
        del enable_custom_integrations

        other_side = MagicMock()
        other_side.name = "RC2"
        other_side.address = "EE:00:11:22:33:99"
        other_side.rssi = -58
        other_side.manufacturer_data = {}
        other_side.service_data = {}
        other_side.service_uuids = list(mock_bluetooth_service_info_octo_rc2.service_uuids)
        other_side.source = "local"
        other_side.device = MagicMock()
        other_side.advertisement = MagicMock()
        other_side.connectable = True
        other_side.time = 0
        other_side.tx_power = None

        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[mock_bluetooth_service_info_octo_rc2, other_side],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_BLUETOOTH},
                data=mock_bluetooth_service_info_octo_rc2,
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"
        note = result["description_placeholders"]["detection_note"]
        assert "Split Octo beds often expose one BLE address per side" in note
        assert "Back + Legs Up" in note

    async def test_bluetooth_discovery_not_supported(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_unknown: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """Test Bluetooth discovery aborts for unsupported devices."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_unknown,
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "not_supported"

    async def test_bluetooth_discovery_disabled_aborts(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """Discovery is suppressed entirely when the user has disabled it."""
        await async_set_discovery_disabled(hass, True)

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "discovery_disabled"

    async def test_bluetooth_discovery_confirm_offers_misidentified_report(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,  # noqa: ARG002
    ):
        """The confirm step exposes a pre-filled 'report misidentified device' link."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )

        assert result["type"] == FlowResultType.FORM
        report_note = result["description_placeholders"]["report_note"]
        assert "issues/new?template=misidentified-bed.yml" in report_note

    async def test_bluetooth_discovery_log_failure_does_not_abort(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        caplog: pytest.LogCaptureFixture,
        enable_custom_integrations,  # noqa: ARG002
    ):
        """Discovery confirmation should still load if discovery-log storage fails."""
        mock_log = MagicMock()
        mock_log.async_record = AsyncMock(side_effect=RuntimeError("store unavailable"))

        with (
            patch(
                "custom_components.adjustable_bed.config_flow.async_get_discovery_log",
                return_value=mock_log,
            ),
            caplog.at_level(
                logging.WARNING,
                logger="custom_components.adjustable_bed.config_flow",
            ),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_BLUETOOTH},
                data=mock_bluetooth_service_info,
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"
        assert "Failed to record auto-detection" in caplog.text
        mock_log.async_record.assert_awaited_once()

    async def test_bluetooth_discovery_already_configured(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """Test Bluetooth discovery aborts if already configured."""
        # Use the same address as the existing entry
        mock_bluetooth_service_info.address = mock_config_entry.data[CONF_ADDRESS]

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"

    async def test_user_flow_duplicate_octo_names_warn_about_split_setup(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_octo_rc2: MagicMock,
        enable_custom_integrations,
    ):
        """Duplicate Octo names should surface split-bed guidance in setup."""
        del enable_custom_integrations

        other_side = MagicMock()
        other_side.name = "RC2"
        other_side.address = "EE:00:11:22:33:99"
        other_side.rssi = -58
        other_side.manufacturer_data = {}
        other_side.service_data = {}
        other_side.service_uuids = list(mock_bluetooth_service_info_octo_rc2.service_uuids)
        other_side.source = "local"
        other_side.device = MagicMock()
        other_side.advertisement = MagicMock()
        other_side.connectable = True
        other_side.time = 0
        other_side.tx_power = None

        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[mock_bluetooth_service_info_octo_rc2, other_side],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: mock_bluetooth_service_info_octo_rc2.address},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"
        note = result["description_placeholders"]["detection_note"]
        assert "Split Octo beds often expose one BLE address per side" in note
        assert "Back + Legs Up" in note

    async def test_bluetooth_discovery_ambiguous_shows_disambiguation(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_ambiguous_okin: MagicMock,
        enable_custom_integrations,
    ):
        """Test that ambiguous BLE detection shows disambiguation step."""
        raw_address = mock_bluetooth_service_info_ambiguous_okin.address.lower()
        mock_bluetooth_service_info_ambiguous_okin.address = raw_address
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_ambiguous_okin,
        )

        # Should show disambiguation form instead of confirm
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_disambiguate"
        assert result["description_placeholders"]["address"] == raw_address.upper()

    async def test_bluetooth_discovery_name_only_okin_receiver_shows_disambiguation(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """A pre-pairing OKIN receiver advertisement should not be dropped as unknown."""
        del enable_custom_integrations

        service_info = MagicMock()
        service_info.name = "OKIN - Receiver"
        service_info.address = "F1:8A:7F:61:EE:8B"
        service_info.rssi = -75
        service_info.manufacturer_data = {}
        service_info.service_data = {}
        service_info.service_uuids = []
        service_info.source = "local"
        service_info.device = MagicMock()
        service_info.advertisement = MagicMock()
        service_info.connectable = True
        service_info.time = 0
        service_info.tx_power = None

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=service_info,
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_disambiguate"

    async def test_bluetooth_disambiguate_selects_type(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_ambiguous_okin: MagicMock,
        enable_custom_integrations,
    ):
        """Test selecting a bed type from disambiguation proceeds to confirm."""
        # Start the flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_ambiguous_okin,
        )
        assert result["step_id"] == "bluetooth_disambiguate"

        # Select a specific bed type from disambiguation
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bed_type_choice": BED_TYPE_OKIMAT},
        )

        # Should proceed to confirm step
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"

    async def test_bluetooth_disambiguate_show_all_option(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_ambiguous_okin: MagicMock,
        enable_custom_integrations,
    ):
        """Test selecting 'show all' from disambiguation proceeds to confirm."""
        # Start the flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_ambiguous_okin,
        )
        assert result["step_id"] == "bluetooth_disambiguate"

        # Select "show all bed types" option
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bed_type_choice": "show_all"},
        )

        # Should proceed to confirm step with full bed type list available
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"
        disconnect_marker = next(
            marker
            for marker in result["data_schema"].schema
            if marker.schema == CONF_DISCONNECT_AFTER_COMMAND
        )
        # The low-confidence candidate would default this to True, but the form
        # actually defaults to Auto-detect, whose conservative default is False.
        assert disconnect_marker.default() is False

    async def test_bluetooth_disambiguate_creates_entry_with_selected_type(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_ambiguous_okin: MagicMock,
        enable_custom_integrations,
    ):
        """Test that disambiguation selection results in correct bed type in entry."""
        from custom_components.adjustable_bed.const import BED_TYPE_OKIN_64BIT

        # Start the flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_ambiguous_okin,
        )
        assert result["step_id"] == "bluetooth_disambiguate"

        # Select OKIN 64-bit from disambiguation options (doesn't require pairing)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bed_type_choice": BED_TYPE_OKIN_64BIT},
        )
        assert result["step_id"] == "bluetooth_confirm"

        # Confirm with minimal input
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "My Bed",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        # A connectable scanner is mocked, so setup runs the probe behind a
        # progress view and then shows the verify_connection result step.
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        result = await _advance_progress(hass, result)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "verify_connection"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={},
        )

        # Should create entry with the disambiguated type
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_BED_TYPE] == BED_TYPE_OKIN_64BIT

    async def test_bluetooth_confirm_auto_detect_ambiguous_reprompts(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_ambiguous_okin: MagicMock,
        enable_custom_integrations,
    ):
        """In the disambiguate -> show-all -> confirm path, 'Auto-detect' must not
        silently resolve an ambiguous detection (issue #385, Codex round 3)."""
        del enable_custom_integrations
        from custom_components.adjustable_bed.config_flow import BED_TYPE_AUTO_DETECT
        from custom_components.adjustable_bed.detection import detect_bed_type_detailed

        # Sanity: the fixture is an ambiguous detection.
        assert detect_bed_type_detailed(mock_bluetooth_service_info_ambiguous_okin).ambiguous_types

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_ambiguous_okin,
        )
        assert result["step_id"] == "bluetooth_disambiguate"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bed_type_choice": "show_all"},
        )
        assert result["step_id"] == "bluetooth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_BED_TYPE: BED_TYPE_AUTO_DETECT,
                CONF_NAME: "Auto Bed",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        # Ambiguous → re-prompt on the confirm form rather than guessing.
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"
        assert result["errors"] == {"base": "auto_detect_failed"}

    async def test_bluetooth_confirm_auto_detect_failure_reprompts(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_unknown: MagicMock,
    ):
        """'Auto-detect' on an unidentifiable device re-shows the form with an error."""
        from custom_components.adjustable_bed.config_flow import BED_TYPE_AUTO_DETECT

        flow = AdjustableBedConfigFlow()
        flow.hass = hass
        flow._discovery_info = mock_bluetooth_service_info_unknown
        flow._show_full_bed_type_list = True

        result = await flow.async_step_bluetooth_confirm(
            user_input={
                CONF_BED_TYPE: BED_TYPE_AUTO_DETECT,
                CONF_NAME: "Mystery Bed",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"
        assert result["errors"] == {"base": "auto_detect_failed"}

    async def test_manual_config_auto_detect_failure_reprompts(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_unknown: MagicMock,
    ):
        """'Auto-detect' in the 'Show all BLE devices' manual path re-prompts on
        failure rather than guessing (issue #385, Codex review)."""
        from custom_components.adjustable_bed.config_flow import BED_TYPE_AUTO_DETECT

        flow = AdjustableBedConfigFlow()
        flow.hass = hass
        flow._discovery_info = mock_bluetooth_service_info_unknown

        result = await flow.async_step_manual_config(
            user_input={
                CONF_BED_TYPE: BED_TYPE_AUTO_DETECT,
                CONF_NAME: "Mystery Bed",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual_config"
        assert result["errors"] == {"base": "auto_detect_failed"}

    async def test_manual_config_auto_detect_resolves(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_leggett: MagicMock,
    ):
        """'Auto-detect' resolves to the detected type and leaves the manual form."""
        from custom_components.adjustable_bed.config_flow import BED_TYPE_AUTO_DETECT
        from custom_components.adjustable_bed.detection import detect_bed_type

        assert detect_bed_type(mock_bluetooth_service_info_leggett)  # fixture is detectable

        flow = AdjustableBedConfigFlow()
        flow.hass = hass
        flow._discovery_info = mock_bluetooth_service_info_leggett

        result = await flow.async_step_manual_config(
            user_input={
                CONF_BED_TYPE: BED_TYPE_AUTO_DETECT,
                CONF_NAME: "Leggett Bed",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        # Resolved to a real type and progressed past manual_config (no error).
        assert not (result["type"] == FlowResultType.FORM and result["step_id"] == "manual_config")

    async def test_manual_config_auto_detect_ambiguous_reprompts(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_ambiguous_okin: MagicMock,
    ):
        """Auto-detect must not silently resolve an ambiguous (shared-UUID)
        detection to a guessed protocol (issue #385, Codex round 2)."""
        from custom_components.adjustable_bed.config_flow import BED_TYPE_AUTO_DETECT
        from custom_components.adjustable_bed.detection import detect_bed_type_detailed

        # Sanity: the fixture is an ambiguous detection.
        assert detect_bed_type_detailed(mock_bluetooth_service_info_ambiguous_okin).ambiguous_types

        flow = AdjustableBedConfigFlow()
        flow.hass = hass
        flow._discovery_info = mock_bluetooth_service_info_ambiguous_okin

        result = await flow.async_step_manual_config(
            user_input={
                CONF_BED_TYPE: BED_TYPE_AUTO_DETECT,
                CONF_NAME: "Ambiguous Bed",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual_config"
        assert result["errors"] == {"base": "auto_detect_failed"}

    async def test_bluetooth_disambiguate_okin_cst_requires_pairing(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_ambiguous_okin: MagicMock,
        enable_custom_integrations,
    ):
        """Selecting Okin CST from an ambiguous receiver should continue to pairing."""
        del enable_custom_integrations

        assert requires_pairing(BED_TYPE_OKIN_CST)

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_ambiguous_okin,
        )
        assert result["step_id"] == "bluetooth_disambiguate"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bed_type_choice": BED_TYPE_OKIN_CST},
        )
        assert result["step_id"] == "bluetooth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "My CST Bed",
                CONF_MOTOR_COUNT: 3,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_pairing"


class TestManualFlow:
    """Test manual configuration flow."""

    async def test_manual_select_shows_devices(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """Test manual select step shows all BLE devices."""
        # First go to user step and select manual
        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[mock_bluetooth_service_info],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

            # Select manual from user step
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual"

    async def test_manual_no_devices_goes_to_entry(
        self, hass: HomeAssistant, enable_custom_integrations
    ):
        """Test manual step goes to manual_entry when no devices are found."""
        # First go to user step (no beds discovered, but form still shown)
        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

            # Select manual from user step
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
            )

        # When no BLE devices, manual step redirects to manual_entry
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual_entry"

    async def test_manual_non_connectable_device_still_shows_selection(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """Manual flow should include non-connectable fallback records."""
        non_connectable_info = MagicMock()
        non_connectable_info.address = "11:22:33:44:55:66"
        non_connectable_info.name = "Mouselet Test"
        non_connectable_info.connectable = False
        non_connectable_info.service_uuids = []
        non_connectable_info.manufacturer_data = {}
        non_connectable_info.source = "proxy_1"
        non_connectable_info.device = MagicMock()

        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            side_effect=([], [non_connectable_info]),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual"

    async def test_manual_config_duplicate_octo_names_warn_about_split_setup(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_octo_rc2: MagicMock,
        enable_custom_integrations,
    ):
        """Manual Octo setup should surface split-bed guidance for duplicate names."""
        del enable_custom_integrations

        other_side = MagicMock()
        other_side.name = "RC2"
        other_side.address = "EE:00:11:22:33:99"
        other_side.rssi = -58
        other_side.manufacturer_data = {}
        other_side.service_data = {}
        other_side.service_uuids = list(mock_bluetooth_service_info_octo_rc2.service_uuids)
        other_side.source = "local"
        other_side.device = MagicMock()
        other_side.advertisement = MagicMock()
        other_side.connectable = True
        other_side.time = 0
        other_side.tx_power = None

        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[mock_bluetooth_service_info_octo_rc2, other_side],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: mock_bluetooth_service_info_octo_rc2.address},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual_config"
        assert (
            "Split Octo beds often expose one BLE address per side"
            in result["description_placeholders"]["setup_note"]
        )

    async def test_manual_entry_creates_entry(
        self, hass: HomeAssistant, enable_custom_integrations
    ):
        """Test manual entry creates a config entry."""
        # First go to user step
        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

            # Select manual from user step - goes to manual_entry since no devices
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
            )

        # The raw form starts with the conservative False default. Linak recommends
        # True, so confirm the bed-specific value before the entry is created.
        with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_ADDRESS: "11:22:33:44:55:66",
                    CONF_BED_TYPE: BED_TYPE_LINAK,
                    CONF_NAME: "Manual Bed",
                    CONF_MOTOR_COUNT: 3,
                    CONF_HAS_MASSAGE: False,
                    CONF_DISABLE_ANGLE_SENSING: True,
                    CONF_PREFERRED_ADAPTER: "auto",
                },
            )
            assert result["step_id"] == "disconnect_after_command"
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_DISCONNECT_AFTER_COMMAND: True},
            )
            result = await _advance_progress(hass, result)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Manual Bed"
        assert result["data"][CONF_ADDRESS] == "11:22:33:44:55:66"
        assert result["data"][CONF_BED_TYPE] == BED_TYPE_LINAK
        assert result["data"][CONF_MOTOR_COUNT] == 3
        # The follow-up displayed Linak's recommendation and kept it enabled.
        assert result["data"][CONF_DISCONNECT_AFTER_COMMAND] is True

    async def test_manual_entry_malouf_collects_layout(
        self, hass: HomeAssistant, enable_custom_integrations
    ):
        """Picking a Malouf protocol from the dropdown collects layout/memory slots.

        The manual-MAC form is built without a pre-selected bed type, so the Malouf
        layout/memory fields aren't shown inline. Selecting a Malouf protocol must
        route to a follow-up step that collects them instead of silently persisting
        the default layout (regression: Hi-Lo / four-motor users lost those controls).
        """
        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
            )

        # Submit the manual-entry form with a Malouf protocol but no layout fields
        # (they were never rendered because the bed type wasn't pre-selected).
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_ADDRESS: "11:22:33:44:55:66",
                CONF_BED_TYPE: BED_TYPE_MALOUF_LEGACY_OKIN,
                CONF_NAME: "Malouf Bed",
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        # Confirm the selected protocol's connection default before collecting
        # the protocol-specific layout.
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "disconnect_after_command"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_DISCONNECT_AFTER_COMMAND: True},
        )
        assert result["step_id"] == "manual_malouf"

        with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_MALOUF_LAYOUT: MALOUF_LAYOUT_HILO,
                    CONF_MALOUF_MEMORY_SLOTS: 2,
                },
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_BED_TYPE] == BED_TYPE_MALOUF_LEGACY_OKIN
        assert result["data"][CONF_MALOUF_LAYOUT] == MALOUF_LAYOUT_HILO
        assert result["data"][CONF_MALOUF_MEMORY_SLOTS] == 2

    async def test_manual_entry_caches_kaidi_metadata(
        self, hass: HomeAssistant, enable_custom_integrations
    ):
        """Manual Kaidi setup should cache Kaidi metadata when available."""
        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
            )

        with (
            patch(
                "custom_components.adjustable_bed.config_flow.resolve_kaidi_advertisement",
                return_value=KaidiAdvertisement(
                    adv_type=KAIDI_ADV_TYPE_BROADCAST,
                    room_id=0x12345678,
                    vaddr=0x01020304,
                    product_id=136,
                    sofa_acu_no=0x2004,
                ),
            ),
            patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False),
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_ADDRESS: "11:22:33:44:55:66",
                    CONF_BED_TYPE: BED_TYPE_KAIDI,
                    CONF_NAME: "Kaidi Bed",
                    CONF_MOTOR_COUNT: 2,
                    CONF_HAS_MASSAGE: False,
                    CONF_DISABLE_ANGLE_SENSING: True,
                    CONF_PREFERRED_ADAPTER: "auto",
                },
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_KAIDI_ROOM_ID] == 0x12345678
        assert result["data"][CONF_KAIDI_TARGET_VADDR] == 0x01020304
        assert result["data"][CONF_KAIDI_PRODUCT_ID] == 136
        assert result["data"][CONF_KAIDI_SOFA_ACU_NO] == 0x2004
        assert result["data"][CONF_KAIDI_ADV_TYPE] == KAIDI_ADV_TYPE_BROADCAST
        assert result["data"][CONF_KAIDI_RESOLVED_VARIANT] == KAIDI_VARIANT_SEAT_1
        assert result["data"][CONF_KAIDI_VARIANT_SOURCE] == "product_id"

    async def test_manual_entry_invalid_mac(self, hass: HomeAssistant, enable_custom_integrations):
        """Test manual entry with invalid MAC address shows error."""
        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

            # Select manual from user step
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
            )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_ADDRESS: "invalid-mac",
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_NAME: "Manual Bed",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] is not None
        assert result["errors"]["base"] == "invalid_mac_address"

    async def test_manual_entry_normalizes_mac(
        self, hass: HomeAssistant, enable_custom_integrations
    ):
        """Test manual entry normalizes MAC address format."""
        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

            # Select manual from user step
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
            )

        with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_ADDRESS: "aa-bb-cc-dd-ee-ff",  # lowercase with dashes
                    CONF_BED_TYPE: BED_TYPE_LINAK,
                    CONF_NAME: "Manual Bed",
                    CONF_MOTOR_COUNT: 2,
                    CONF_HAS_MASSAGE: False,
                    CONF_DISABLE_ANGLE_SENSING: True,
                    CONF_PREFERRED_ADAPTER: "auto",
                },
            )
            assert result["step_id"] == "disconnect_after_command"
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_DISCONNECT_AFTER_COMMAND: True},
            )
            result = await _advance_progress(hass, result)

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_ADDRESS] == "AA:BB:CC:DD:EE:FF"  # Normalized


class TestUserFlow:
    """Test user-initiated flow with device selection."""

    async def test_user_flow_select_diagnostic_browser(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """Selecting the unsupported-device browser should show all BLE devices."""
        unknown_info = MagicMock()
        unknown_info.address = "11:22:33:44:55:66"
        unknown_info.name = "Unknown Device"
        unknown_info.connectable = False
        unknown_info.service_uuids = []
        unknown_info.manufacturer_data = {}
        unknown_info.source = "proxy_1"
        unknown_info.device = MagicMock()

        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            side_effect=[[], [unknown_info]],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "diagnostic"},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "diagnostic"

    async def test_diagnostic_browser_returns_mac_details_instead_of_creating_entry(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """Selecting an unsupported device should abort with support-bundle instructions."""
        unknown_info = MagicMock()
        unknown_info.address = "11:22:33:44:55:66"
        unknown_info.name = "Unknown Device"
        unknown_info.connectable = False
        unknown_info.service_uuids = []
        unknown_info.manufacturer_data = {}
        unknown_info.source = "proxy_1"
        unknown_info.device = MagicMock()

        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            side_effect=[[], [unknown_info]],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "diagnostic"},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: unknown_info.address},
            )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "diagnostic_browser_ready"
        assert result["description_placeholders"]["address"] == unknown_info.address
        assert result["description_placeholders"]["source"] == "proxy_1"

    async def test_diagnostic_manual_returns_bundle_instructions(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """Manual unsupported-device lookup should finish without creating an entry."""
        with (
            patch(
                "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
                side_effect=[[], []],
            ),
            patch(
                "custom_components.adjustable_bed.config_flow.find_service_info_by_address",
                return_value=(None, False),
            ),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "diagnostic"},
            )

            assert result["type"] == FlowResultType.FORM
            assert result["step_id"] == "diagnostic_manual"

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_ADDRESS: "11:22:33:44:55:66",
                    CONF_NAME: "Mystery Bed",
                },
            )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "diagnostic_browser_ready"
        assert result["description_placeholders"]["address"] == "11:22:33:44:55:66"
        assert result["description_placeholders"]["name"] == "Mystery Bed"

    async def test_user_flow_shows_discovered_devices(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """Test user flow shows discovered devices."""
        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[mock_bluetooth_service_info],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

    async def test_user_flow_can_readd_previously_ignored_device(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """An ignored discovery must be visible and selectable in a manual user flow."""
        ignored_entry = MockConfigEntry(
            domain=DOMAIN,
            title=mock_bluetooth_service_info.name,
            data={},
            source=SOURCE_IGNORE,
            unique_id=mock_bluetooth_service_info.address.upper(),
        )
        ignored_entry.add_to_hass(hass)

        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[mock_bluetooth_service_info],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )
            selector_options = next(iter(result["data_schema"].schema.values())).container
            assert mock_bluetooth_service_info.address in selector_options

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: mock_bluetooth_service_info.address},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"

    async def test_user_flow_select_manual(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """Test user can select manual entry from device list."""
        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[mock_bluetooth_service_info],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

            # Keep the patch active so manual step finds devices
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual"

    async def test_user_flow_select_ambiguous_okin_device_shows_disambiguation(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_ambiguous_okin: MagicMock,
        enable_custom_integrations,
    ):
        """Selecting an ambiguous discovered device should use the focused chooser."""
        del enable_custom_integrations

        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[mock_bluetooth_service_info_ambiguous_okin],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: mock_bluetooth_service_info_ambiguous_okin.address},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_disambiguate"

    async def test_user_flow_retrying_device_aborts_with_support_bundle_instructions(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        mock_bluetooth_adapters,
        enable_custom_integrations,
    ):
        """Retrying entries should surface recovery instructions instead of disappearing."""
        del mock_bluetooth_adapters, enable_custom_integrations
        existing_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Retrying Bed",
            data={
                CONF_ADDRESS: mock_bluetooth_service_info.address.upper(),
                CONF_NAME: "Retrying Bed",
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id=mock_bluetooth_service_info.address.upper(),
            entry_id="retrying_entry_id",
        )
        existing_entry.add_to_hass(hass)

        with patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ):
            await hass.config_entries.async_setup(existing_entry.entry_id)
            await hass.async_block_till_done()

        assert existing_entry.state == ConfigEntryState.SETUP_RETRY

        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[mock_bluetooth_service_info],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )
            retrying_option = f"configured_retry::{mock_bluetooth_service_info.address.upper()}"
            assert result["type"] == FlowResultType.FORM
            selector_options = next(iter(result["data_schema"].schema.values())).container
            assert retrying_option in selector_options
            assert selector_options[retrying_option].startswith("Retrying Bed")

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: retrying_option},
            )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "configured_retrying"
        assert (
            result["description_placeholders"]["address"]
            == mock_bluetooth_service_info.address.upper()
        )
        assert result["description_placeholders"]["name"] == "Retrying Bed"


class TestOptionsFlow:
    """Test options flow."""

    async def test_richmat_options_can_replace_detected_qrrm_with_lp_profile(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ) -> None:
        """Existing QRRM entries should be able to select the L&P preset surface."""
        del enable_custom_integrations
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="QRRM106475",
            data={
                CONF_ADDRESS: "57:4C:54:00:2D:BE",
                CONF_NAME: "QRRM106475",
                CONF_BED_TYPE: BED_TYPE_RICHMAT,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: "auto",
                CONF_RICHMAT_REMOTE: "qrrm",
            },
            unique_id="57:4C:54:00:2D:BE",
        )
        entry.add_to_hass(hass)
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        initial = await _open_options_form(hass, entry.entry_id)
        markers = {marker.schema: marker for marker in initial["data_schema"].schema}
        remote_marker = markers[CONF_RICHMAT_REMOTE]
        remote_validator = initial["data_schema"].schema[remote_marker]

        assert remote_marker.default() == "qrrm"
        assert "qrrm" in remote_validator.container
        assert RICHMAT_REMOTE_LP_QRRM in remote_validator.container

        saved = await hass.config_entries.options.async_configure(
            initial["flow_id"],
            user_input={CONF_RICHMAT_REMOTE: RICHMAT_REMOTE_LP_QRRM},
        )

        assert saved["type"] == FlowResultType.CREATE_ENTRY
        assert entry.data[CONF_RICHMAT_REMOTE] == RICHMAT_REMOTE_LP_QRRM

    async def test_options_flow_records_pulse_settings_as_user_owned(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ) -> None:
        """Saving the form marks the cadence as the user's, so migrations skip it.

        Issue #368: a Leggett Okin user who set (10, 100) had it reverted to the
        protocol defaults on every connect, because the runtime migration matches
        on exactly those values and had no way to tell them from legacy defaults.
        """
        del enable_custom_integrations
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Leggett Okin Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:97",
                CONF_NAME: "Leggett Okin Bed",
                CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
                CONF_MOTOR_COUNT: 4,
                CONF_MOTOR_PULSE_COUNT: 5,
                CONF_MOTOR_PULSE_DELAY_MS: 200,
                CONF_DISABLE_ANGLE_SENSING: True,
            },
            unique_id="AA:BB:CC:DD:EE:97",
        )
        entry.add_to_hass(hass)
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        assert CONF_MOTOR_PULSE_USER_SET not in entry.data

        initial = await _open_options_form(hass, entry.entry_id)
        saved = await hass.config_entries.options.async_configure(
            initial["flow_id"],
            user_input={
                CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
                CONF_MOTOR_COUNT: 4,
                CONF_MOTOR_PULSE_COUNT: "10",
                CONF_MOTOR_PULSE_DELAY_MS: "100",
            },
        )

        assert saved["type"] == FlowResultType.CREATE_ENTRY
        assert entry.data[CONF_MOTOR_PULSE_COUNT] == 10
        assert entry.data[CONF_MOTOR_PULSE_DELAY_MS] == 100
        assert entry.data[CONF_MOTOR_PULSE_USER_SET] is True

    async def test_leggett_okin_options_restore_motor_count_and_hide_positions(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
        mock_coordinator_connected,
    ) -> None:
        """Legacy string defaults render correctly and irrelevant fields stay hidden."""
        del enable_custom_integrations, mock_coordinator_connected
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Leggett Okin Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:98",
                CONF_NAME: "Leggett Okin Bed",
                CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
                CONF_MOTOR_COUNT: "4",
                CONF_DISABLE_ANGLE_SENSING: True,
            },
            unique_id="AA:BB:CC:DD:EE:98",
        )
        entry.add_to_hass(hass)
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        initial = await _open_options_form(hass, entry.entry_id)
        markers = {marker.schema: marker for marker in initial["data_schema"].schema}

        assert markers[CONF_MOTOR_COUNT].default() == 4
        assert CONF_DISABLE_ANGLE_SENSING not in markers
        assert CONF_POSITION_MODE not in markers
        assert CONF_BACK_MAX_ANGLE not in markers

    async def test_options_flow_can_change_bed_type_and_rebuild_dependent_fields(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ) -> None:
        """Changing type rebuilds the form, then saves type-specific settings."""
        del enable_custom_integrations
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Okin CST Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:96",
                CONF_NAME: "Okin CST Bed",
                CONF_BED_TYPE: BED_TYPE_OKIN_CST,
                CONF_MOTOR_COUNT: 3,
                CONF_BLE_BOND_ESTABLISHED: True,
                CONF_BLE_BOND_MARKER_UNRELIABLE: True,
                CONF_BACK_MAX_ANGLE: 68.0,
                CONF_DISABLE_ANGLE_SENSING: False,
            },
            unique_id="AA:BB:CC:DD:EE:96",
        )
        entry.add_to_hass(hass)
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        initial = await _open_options_form(hass, entry.entry_id)
        bed_type_marker = next(
            marker for marker in initial["data_schema"].schema if marker.schema == CONF_BED_TYPE
        )
        bed_type_selector = initial["data_schema"].schema[bed_type_marker]
        option_values = {option["value"] for option in bed_type_selector.config["options"]}
        assert bed_type_marker.default() == BED_TYPE_OKIN_CST
        assert BED_TYPE_OCTO in option_values

        rebuilt = await hass.config_entries.options.async_configure(
            initial["flow_id"],
            user_input={
                CONF_BED_TYPE: BED_TYPE_OCTO,
                CONF_MOTOR_COUNT: 3,
            },
        )

        assert rebuilt["type"] == FlowResultType.FORM
        rebuilt_markers = {marker.schema: marker for marker in rebuilt["data_schema"].schema}
        assert rebuilt_markers[CONF_BED_TYPE].default() == BED_TYPE_OCTO
        assert CONF_PROTOCOL_VARIANT in rebuilt_markers
        assert CONF_OCTO_PIN in rebuilt_markers
        assert CONF_BACK_MAX_ANGLE not in rebuilt_markers
        assert CONF_DISABLE_ANGLE_SENSING not in rebuilt_markers

        saved = await hass.config_entries.options.async_configure(
            rebuilt["flow_id"],
            user_input={
                CONF_BED_TYPE: BED_TYPE_OCTO,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STANDARD,
                CONF_OCTO_PIN: "1234",
            },
        )

        assert saved["type"] == FlowResultType.CREATE_ENTRY
        assert entry.data[CONF_BED_TYPE] == BED_TYPE_OCTO
        assert entry.data[CONF_PROTOCOL_VARIANT] == OCTO_VARIANT_STANDARD
        assert entry.data[CONF_OCTO_PIN] == "1234"
        assert CONF_BLE_BOND_ESTABLISHED not in entry.data
        # Both pairing markers describe the old protocol's requirements.
        assert CONF_BLE_BOND_MARKER_UNRELIABLE not in entry.data
        assert CONF_BACK_MAX_ANGLE not in entry.data
        assert entry.data[CONF_DISABLE_ANGLE_SENSING] is True

    async def test_options_flow_normalizes_fields_after_bed_type_change(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ) -> None:
        """A new type cannot inherit an invalid motor count or stale variant."""
        del enable_custom_integrations
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="OCTO Lift",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:95",
                CONF_NAME: "OCTO Lift",
                CONF_BED_TYPE: BED_TYPE_OCTO,
                CONF_MOTOR_COUNT: 1,
                CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STANDARD,
                CONF_OCTO_PIN: "3060",
                CONF_DISABLE_ANGLE_SENSING: True,
            },
            unique_id="AA:BB:CC:DD:EE:95",
        )
        entry.add_to_hass(hass)
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        initial = await _open_options_form(hass, entry.entry_id)
        rebuilt = await hass.config_entries.options.async_configure(
            initial["flow_id"],
            user_input={
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_MOTOR_COUNT: 1,
                CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STANDARD,
            },
        )

        rebuilt_markers = {marker.schema: marker for marker in rebuilt["data_schema"].schema}
        assert rebuilt_markers[CONF_MOTOR_COUNT].default() == 2
        assert rebuilt_markers[CONF_DISABLE_ANGLE_SENSING].default() is False
        assert rebuilt_markers[CONF_PROTOCOL_VARIANT].default() == VARIANT_AUTO
        assert CONF_OCTO_PIN not in rebuilt_markers

        saved = await hass.config_entries.options.async_configure(
            rebuilt["flow_id"],
            user_input={
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
            },
        )

        assert saved["type"] == FlowResultType.CREATE_ENTRY
        assert entry.data[CONF_BED_TYPE] == BED_TYPE_LINAK
        assert entry.data[CONF_MOTOR_COUNT] == 2
        assert entry.data[CONF_DISABLE_ANGLE_SENSING] is False
        assert entry.data[CONF_PROTOCOL_VARIANT] == VARIANT_AUTO
        assert CONF_OCTO_PIN not in entry.data

    async def test_options_flow_keeps_current_legacy_bed_type_selectable(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ) -> None:
        """An existing legacy alias remains valid while editing other options."""
        del enable_custom_integrations
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Legacy Okimat",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:91",
                CONF_NAME: "Legacy Okimat",
                CONF_BED_TYPE: BED_TYPE_OKIMAT,
                CONF_MOTOR_COUNT: 2,
            },
            unique_id="AA:BB:CC:DD:EE:91",
        )
        entry.add_to_hass(hass)
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        initial = await _open_options_form(hass, entry.entry_id)
        marker = next(
            marker for marker in initial["data_schema"].schema if marker.schema == CONF_BED_TYPE
        )
        selector = initial["data_schema"].schema[marker]
        option_values = {option["value"] for option in selector.config["options"]}

        assert marker.default() == BED_TYPE_OKIMAT
        assert BED_TYPE_OKIMAT in option_values

        saved = await hass.config_entries.options.async_configure(
            initial["flow_id"],
            user_input={CONF_HAS_MASSAGE: True},
        )

        assert saved["type"] == FlowResultType.CREATE_ENTRY
        assert entry.data[CONF_HAS_MASSAGE] is True
        assert entry.data[CONF_BED_TYPE] == BED_TYPE_OKIMAT

    async def test_options_flow_resets_variant_and_timing_for_new_protocol(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ) -> None:
        """A new protocol starts with its own dialect and command timing defaults."""
        del enable_custom_integrations
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Leggett Okin",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:94",
                CONF_NAME: "Leggett Okin",
                CONF_BED_TYPE: BED_TYPE_LEGGETT_PLATT,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: LEGGETT_VARIANT_OKIN,
                CONF_MOTOR_PULSE_COUNT: 25,
                CONF_MOTOR_PULSE_DELAY_MS: 50,
            },
            unique_id="AA:BB:CC:DD:EE:94",
        )
        entry.add_to_hass(hass)
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        initial = await _open_options_form(hass, entry.entry_id)
        rebuilt = await hass.config_entries.options.async_configure(
            initial["flow_id"],
            user_input={
                CONF_BED_TYPE: BED_TYPE_KEESON,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: LEGGETT_VARIANT_OKIN,
                CONF_MOTOR_PULSE_COUNT: "25",
                CONF_MOTOR_PULSE_DELAY_MS: "50",
            },
        )

        rebuilt_markers = {marker.schema: marker for marker in rebuilt["data_schema"].schema}
        assert rebuilt_markers[CONF_PROTOCOL_VARIANT].default() == VARIANT_AUTO
        assert rebuilt_markers[CONF_MOTOR_PULSE_COUNT].default() == "10"
        assert rebuilt_markers[CONF_MOTOR_PULSE_DELAY_MS].default() == "100"

        variant_rebuilt = await hass.config_entries.options.async_configure(
            rebuilt["flow_id"],
            user_input={
                CONF_BED_TYPE: BED_TYPE_KEESON,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: KEESON_VARIANT_ERGOMOTION,
            },
        )

        variant_markers = {
            marker.schema: marker for marker in variant_rebuilt["data_schema"].schema
        }
        assert variant_rebuilt["type"] == FlowResultType.FORM
        assert variant_markers[CONF_PROTOCOL_VARIANT].default() == KEESON_VARIANT_ERGOMOTION
        assert variant_markers[CONF_DISABLE_ANGLE_SENSING].default() is False

        saved = await hass.config_entries.options.async_configure(
            variant_rebuilt["flow_id"],
            user_input={
                CONF_BED_TYPE: BED_TYPE_KEESON,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: KEESON_VARIANT_ERGOMOTION,
                CONF_DISABLE_ANGLE_SENSING: True,
            },
        )

        assert saved["type"] == FlowResultType.CREATE_ENTRY
        assert entry.data[CONF_PROTOCOL_VARIANT] == KEESON_VARIANT_ERGOMOTION
        assert entry.data[CONF_DISABLE_ANGLE_SENSING] is True
        assert entry.data[CONF_MOTOR_PULSE_COUNT] == 10
        assert entry.data[CONF_MOTOR_PULSE_DELAY_MS] == 100

    async def test_options_flow_rebuilds_position_fields_for_variant_change(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
        mock_coordinator_connected,
    ) -> None:
        """Changing only the variant rebuilds fields when position support changes."""
        del enable_custom_integrations, mock_coordinator_connected
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Keeson Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:95",
                CONF_NAME: "Keeson Bed",
                CONF_BED_TYPE: BED_TYPE_KEESON,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
            },
            unique_id="AA:BB:CC:DD:EE:95",
        )
        entry.add_to_hass(hass)
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        initial = await _open_options_form(hass, entry.entry_id)
        initial_markers = {marker.schema for marker in initial["data_schema"].schema}
        assert CONF_DISABLE_ANGLE_SENSING not in initial_markers

        rebuilt = await hass.config_entries.options.async_configure(
            initial["flow_id"],
            user_input={
                CONF_BED_TYPE: BED_TYPE_KEESON,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: KEESON_VARIANT_ERGOMOTION,
                CONF_DISABLE_DISCOVERY: True,
            },
        )

        rebuilt_markers = {marker.schema: marker for marker in rebuilt["data_schema"].schema}
        assert rebuilt["type"] == FlowResultType.FORM
        assert rebuilt_markers[CONF_DISABLE_ANGLE_SENSING].default() is False
        assert rebuilt_markers[CONF_DISABLE_DISCOVERY].default() is True
        assert CONF_POSITION_MODE in rebuilt_markers

        saved = await hass.config_entries.options.async_configure(
            rebuilt["flow_id"],
            user_input={
                CONF_BED_TYPE: BED_TYPE_KEESON,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: KEESON_VARIANT_ERGOMOTION,
                CONF_DISABLE_DISCOVERY: True,
            },
        )

        assert saved["type"] == FlowResultType.CREATE_ENTRY
        assert entry.data[CONF_PROTOCOL_VARIANT] == KEESON_VARIANT_ERGOMOTION
        assert await async_is_discovery_disabled(hass) is True

    async def test_paired_options_preserve_variant_change_across_rebuild(
        self,
        hass: HomeAssistant,
    ) -> None:
        """A rebuild must not lose a variant edit before paired children are saved."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Paired Keeson Bed",
            data={
                CONF_NAME: "Paired Keeson Bed",
                CONF_BED_TYPE: BED_TYPE_KEESON,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
                CONF_PAIR_ID: "pair_keeson_variant",
                CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
                CONF_PAIR_MEMBER_ADDRESSES: [
                    "AA:BB:CC:DD:EE:95",
                    "AA:BB:CC:DD:EE:96",
                ],
                CONF_PAIR_CHILDREN: [
                    {
                        CONF_SIDE: SIDE_LEFT,
                        CONF_ADDRESS: "AA:BB:CC:DD:EE:95",
                        CONF_NAME: "Left Keeson",
                        CONF_BED_TYPE: BED_TYPE_KEESON,
                        CONF_MOTOR_COUNT: 2,
                        CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
                    },
                    {
                        CONF_SIDE: SIDE_RIGHT,
                        CONF_ADDRESS: "AA:BB:CC:DD:EE:96",
                        CONF_NAME: "Right Keeson",
                        CONF_BED_TYPE: BED_TYPE_KEESON,
                        CONF_MOTOR_COUNT: 2,
                        CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
                    },
                ],
            },
            unique_id="pair_keeson_variant",
            entry_id="pair_keeson_variant",
        )
        entry.add_to_hass(hass)
        flow = AdjustableBedOptionsFlow(entry)
        flow.hass = hass
        flow.handler = entry.entry_id

        initial = await flow._async_options_form(None, step_id="settings")
        rebuilt = await flow._async_options_form(
            {
                CONF_BED_TYPE: BED_TYPE_KEESON,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: KEESON_VARIANT_ERGOMOTION,
            },
            step_id="settings",
        )
        saved = await flow._async_options_form(
            {
                CONF_BED_TYPE: BED_TYPE_KEESON,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: KEESON_VARIANT_ERGOMOTION,
            },
            step_id="settings",
        )

        assert initial["type"] == FlowResultType.FORM
        assert rebuilt["type"] == FlowResultType.FORM
        assert saved["type"] == FlowResultType.CREATE_ENTRY
        for child in entry.data[CONF_PAIR_CHILDREN]:
            assert child[CONF_PROTOCOL_VARIANT] == KEESON_VARIANT_ERGOMOTION
            assert child[CONF_DISABLE_ANGLE_SENSING] is False

    async def test_paired_bed_type_change_uses_new_protocol_defaults(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Derived timing and motor defaults survive the paired form rebuild."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Paired Keeson Bed",
            data={
                CONF_NAME: "Paired Keeson Bed",
                CONF_BED_TYPE: BED_TYPE_KEESON,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
                CONF_MOTOR_PULSE_COUNT: 10,
                CONF_MOTOR_PULSE_DELAY_MS: 100,
                CONF_PAIR_ID: "pair_keeson_to_octo",
                CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
                CONF_PAIR_MEMBER_ADDRESSES: [
                    "AA:BB:CC:DD:EE:97",
                    "AA:BB:CC:DD:EE:98",
                ],
                CONF_PAIR_CHILDREN: [
                    {
                        CONF_SIDE: side,
                        CONF_ADDRESS: address,
                        CONF_NAME: f"{side.title()} Keeson",
                        CONF_BED_TYPE: BED_TYPE_KEESON,
                        CONF_MOTOR_COUNT: 2,
                        CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
                        CONF_MOTOR_PULSE_COUNT: 10,
                        CONF_MOTOR_PULSE_DELAY_MS: 100,
                    }
                    for side, address in (
                        (SIDE_LEFT, "AA:BB:CC:DD:EE:97"),
                        (SIDE_RIGHT, "AA:BB:CC:DD:EE:98"),
                    )
                ],
            },
            unique_id="pair_keeson_to_octo",
            entry_id="pair_keeson_to_octo",
        )
        entry.add_to_hass(hass)
        flow = AdjustableBedOptionsFlow(entry)
        flow.hass = hass
        flow.handler = entry.entry_id

        rebuilt = await flow._async_options_form(
            {
                CONF_BED_TYPE: BED_TYPE_OCTO,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
                CONF_MOTOR_PULSE_COUNT: "10",
                CONF_MOTOR_PULSE_DELAY_MS: "100",
            },
            step_id="settings",
        )
        defaults = get_motor_pulse_defaults(BED_TYPE_OCTO, VARIANT_AUTO)
        saved = await flow._async_options_form(
            {
                CONF_BED_TYPE: BED_TYPE_OCTO,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
            },
            step_id="settings",
        )

        assert rebuilt["type"] == FlowResultType.FORM
        assert saved["type"] == FlowResultType.CREATE_ENTRY
        for child in entry.data[CONF_PAIR_CHILDREN]:
            assert child[CONF_BED_TYPE] == BED_TYPE_OCTO
            assert child[CONF_MOTOR_COUNT] == 2
            assert (
                child[CONF_MOTOR_PULSE_COUNT],
                child[CONF_MOTOR_PULSE_DELAY_MS],
            ) == defaults

    @pytest.mark.parametrize(
        ("bed_type", "variant"),
        [
            (BED_TYPE_RONDURE, RONDURE_VARIANT_SIDE_A),
            (BED_TYPE_SBI, SBI_VARIANT_SIDE_B),
        ],
    )
    async def test_options_flow_preserves_split_bed_side_variant(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
        bed_type: str,
        variant: str,
    ) -> None:
        """Saving unrelated options must keep a split bed's selected side."""
        del enable_custom_integrations
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Split Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:93",
                CONF_NAME: "Split Bed",
                CONF_BED_TYPE: bed_type,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: variant,
            },
            unique_id="AA:BB:CC:DD:EE:93",
        )
        entry.add_to_hass(hass)
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        initial = await _open_options_form(hass, entry.entry_id)
        markers = {marker.schema: marker for marker in initial["data_schema"].schema}
        assert markers[CONF_PROTOCOL_VARIANT].default() == variant

        saved = await hass.config_entries.options.async_configure(
            initial["flow_id"],
            user_input={
                CONF_BED_TYPE: bed_type,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: variant,
                CONF_HAS_MASSAGE: True,
            },
        )

        assert saved["type"] == FlowResultType.CREATE_ENTRY
        assert entry.data[CONF_PROTOCOL_VARIANT] == variant

    async def test_octo_options_can_switch_variant_and_one_motor_together(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """A Star2 entry can switch to Standard and one motor in one save."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="OCTO Star2",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:97",
                CONF_NAME: "OCTO Star2",
                CONF_BED_TYPE: BED_TYPE_OCTO,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STAR2,
            },
            unique_id="AA:BB:CC:DD:EE:97",
        )
        entry.add_to_hass(hass)
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        result = await _open_options_form(hass, entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_MOTOR_COUNT: 1,
                CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STANDARD,
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert entry.data[CONF_MOTOR_COUNT] == 1
        assert entry.data[CONF_PROTOCOL_VARIANT] == OCTO_VARIANT_STANDARD

    async def test_options_flow(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Test options flow allows changing settings."""
        # Set up the integration first so the options flow handler is registered
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[],
        ):
            result = await _open_options_form(hass, mock_config_entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "settings"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PASSIVE_POSITION_RECONCILIATION: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY

        # Verify the config entry was updated
        assert mock_config_entry.data[CONF_MOTOR_COUNT] == 4
        assert mock_config_entry.data[CONF_HAS_MASSAGE] is True
        assert mock_config_entry.data[CONF_DISABLE_ANGLE_SENSING] is False
        assert mock_config_entry.data[CONF_PASSIVE_POSITION_RECONCILIATION] is False

    async def test_options_flow_toggles_discovery(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """The discovery toggle persists globally and never lands in entry data."""
        # Legacy releases could leave this global preference in entry data. It
        # must neither override the global value nor survive the next save.
        hass.config_entries.async_update_entry(
            mock_config_entry,
            data={**mock_config_entry.data, CONF_DISABLE_DISCOVERY: True},
        )
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        assert await async_is_discovery_disabled(hass) is False

        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[],
        ):
            result = await _open_options_form(hass, mock_config_entry.entry_id)
            discovery_marker = next(
                marker
                for marker in result["data_schema"].schema
                if marker.schema == CONF_DISABLE_DISCOVERY
            )
            assert discovery_marker.default() is False
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={
                    CONF_MOTOR_COUNT: 2,
                    CONF_DISABLE_DISCOVERY: True,
                },
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Stored globally, not as per-entry data.
        assert await async_is_discovery_disabled(hass) is True
        assert CONF_DISABLE_DISCOVERY not in mock_config_entry.data

    async def test_malouf_options_keep_layout_separate_from_protocol(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """A Malouf protocol entry must expose independent hardware settings."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Lucid L600",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:58",
                CONF_NAME: "OKIN-BLE00017786",
                CONF_BED_TYPE: BED_TYPE_MALOUF_LEGACY_OKIN,
                CONF_MOTOR_COUNT: 2,
            },
            unique_id="AA:BB:CC:DD:EE:58",
        )
        entry.add_to_hass(hass)
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        result = await _open_options_form(hass, entry.entry_id)
        schema_keys = {marker.schema for marker in result["data_schema"].schema}
        assert CONF_MALOUF_LAYOUT in schema_keys
        assert CONF_MALOUF_MEMORY_SLOTS in schema_keys

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_MALOUF_LAYOUT: MALOUF_LAYOUT_HILO,
                CONF_MALOUF_MEMORY_SLOTS: 2,
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert entry.data[CONF_BED_TYPE] == BED_TYPE_MALOUF_LEGACY_OKIN
        assert entry.data[CONF_MALOUF_LAYOUT] == MALOUF_LAYOUT_HILO
        assert entry.data[CONF_MALOUF_MEMORY_SLOTS] == 2

    async def test_options_flow_toggle_not_applied_on_validation_error(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """A rejected form must not partially apply the global discovery toggle."""
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        assert await async_is_discovery_disabled(hass) is False

        with patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[],
        ):
            result = await _open_options_form(hass, mock_config_entry.entry_id)
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={
                    CONF_MOTOR_COUNT: 2,
                    CONF_DISABLE_DISCOVERY: True,
                    CONF_MOTOR_PULSE_COUNT: "not-a-number",
                },
            )

        # Form is rejected for the invalid number...
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]
        # ...and the discovery toggle was NOT persisted.
        assert await async_is_discovery_disabled(hass) is False


# ---------------------------------------------------------------------------
# verify_connection step (issue #357)
# ---------------------------------------------------------------------------


def _fresh_gate(
    source: str,
    rssi: int,
    transport: TransportClass = TransportClass.LOCAL,
) -> tuple[AdvertisementEvidence, MagicMock]:
    """Return a passing freshness gate result over a given transport.

    The probe no longer picks an adapter itself: it asks the freshness gate
    whether the bed has actually advertised recently, and only then resolves a
    device to connect to (issue #458).
    """
    path = ConnectionPath(source=source, transport=transport, scanner_name=source, rssi=rssi)
    evidence = AdvertisementEvidence(
        status=FreshnessStatus.FRESH,
        age_seconds=1.0,
        rssi=rssi,
        source=source,
        path=path,
    )
    return evidence, MagicMock()


class _PatchGate:
    """Make the capability probe see a bed that is advertising right now.

    The probe reaches the gate by two routes: directly when it runs inline, and
    through the wait helper when it runs behind a progress view. Both are
    patched so a test does not have to know which one it took.
    """

    def __init__(
        self, source: str, rssi: int, transport: TransportClass = TransportClass.LOCAL
    ) -> None:
        self._result = _fresh_gate(source, rssi, transport)
        self._patches = [
            patch(
                "custom_components.adjustable_bed.config_flow.async_gate_connection",
                return_value=self._result,
            ),
            patch(
                "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
                AsyncMock(return_value=self._result),
            ),
        ]

    def __enter__(self) -> None:
        for item in self._patches:
            item.start()

    def __exit__(self, *exc: object) -> None:
        for item in reversed(self._patches):
            item.stop()


def _patch_gate(source: str, rssi: int, transport: TransportClass = TransportClass.LOCAL):
    """Patch the freshness gate used by the capability probe."""
    return _PatchGate(source, rssi, transport)


def _fake_connected_client() -> MagicMock:
    """Fake BleakClient with one service and a writable characteristic."""
    char = MagicMock()
    char.uuid = "0000ffe1-0000-1000-8000-00805f9b34fb"
    char.properties = ["write", "notify"]
    service = MagicMock()
    service.uuid = "0000ffe0-0000-1000-8000-00805f9b34fb"
    service.characteristics = [char]
    client = MagicMock()
    client.is_connected = True
    client.services = [service]
    client.disconnect = AsyncMock()
    return client


async def test_verify_connection_success_then_creates_entry(
    hass: HomeAssistant,
    mock_bluetooth_service_info_jiecang: BluetoothServiceInfoBleak,
    enable_custom_integrations,
) -> None:
    """A successful probe shows the checklist, then submit creates the entry."""
    mock_bluetooth_service_info = mock_bluetooth_service_info_jiecang
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    assert result["step_id"] == "bluetooth_confirm"

    client = _fake_connected_client()
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("esphome_bedroom", -60, TransportClass.PROXY),
        patch(
            "bleak_retry_connector.establish_connection",
            AsyncMock(return_value=client),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.discover_services",
            AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.read_ble_device_info",
            AsyncMock(return_value=("OKIN", None)),
        ),
    ):
        verify = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_PREFERRED_ADAPTER: "auto"}
        )
        verify = await _advance_progress(hass, verify)
        assert verify["type"] == FlowResultType.FORM
        assert verify["step_id"] == "verify_connection"
        caps = verify["description_placeholders"]["capabilities"]
        assert "Connected" in caps
        assert "esphome_bedroom" in caps
        assert "Bluetooth proxy" in caps
        # GATT + device-info details surface in the checklist.
        assert "writable characteristic" in caps
        assert "OKIN" in caps
        # The probe must release the bed's single BLE connection.
        client.disconnect.assert_awaited()

        created = await hass.config_entries.flow.async_configure(verify["flow_id"], user_input={})

    assert created["type"] == FlowResultType.CREATE_ENTRY
    assert created["data"][CONF_BED_TYPE] == BED_TYPE_JIECANG


async def test_verify_connection_warns_when_no_writable_characteristic(
    hass: HomeAssistant,
    mock_bluetooth_service_info_jiecang: BluetoothServiceInfoBleak,
    enable_custom_integrations,
) -> None:
    """Connecting to a device with no writable characteristic must not show a pass."""
    mock_bluetooth_service_info = mock_bluetooth_service_info_jiecang
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    assert result["step_id"] == "bluetooth_confirm"

    # Service present, but only read/notify - nothing the integration can write to.
    char = MagicMock()
    char.uuid = "0000ffe1-0000-1000-8000-00805f9b34fb"
    char.properties = ["read", "notify"]
    service = MagicMock()
    service.uuid = "0000ffe0-0000-1000-8000-00805f9b34fb"
    service.characteristics = [char]
    client = MagicMock()
    client.is_connected = True
    client.services = [service]
    client.disconnect = AsyncMock()

    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("hci0", -55),
        patch(
            "bleak_retry_connector.establish_connection",
            AsyncMock(return_value=client),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.discover_services",
            AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.read_ble_device_info",
            AsyncMock(return_value=(None, None)),
        ),
    ):
        verify = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_PREFERRED_ADAPTER: "auto"}
        )
        verify = await _advance_progress(hass, verify)
        assert verify["step_id"] == "verify_connection"
        caps = verify["description_placeholders"]["capabilities"]
        assert "No writable characteristic found" in caps
        assert "⚠️" in caps

        created = await hass.config_entries.flow.async_configure(verify["flow_id"], user_input={})

    assert created["type"] == FlowResultType.CREATE_ENTRY
    assert created["data"][CONF_BED_TYPE] == BED_TYPE_JIECANG


async def test_verify_connection_failure_still_creates_entry(
    hass: HomeAssistant,
    mock_bluetooth_service_info_jiecang: BluetoothServiceInfoBleak,
    enable_custom_integrations,
) -> None:
    """A failed probe shows the error note but the user can still finish setup."""
    mock_bluetooth_service_info = mock_bluetooth_service_info_jiecang
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    assert result["step_id"] == "bluetooth_confirm"

    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("hci0", -72),
        patch(
            "bleak_retry_connector.establish_connection",
            AsyncMock(side_effect=Exception("device busy")),
        ),
    ):
        verify = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_PREFERRED_ADAPTER: "auto"}
        )
        verify = await _advance_progress(hass, verify)
        assert verify["step_id"] == "verify_connection"
        assert "Could not connect" in verify["description_placeholders"]["capabilities"]

        created = await hass.config_entries.flow.async_configure(verify["flow_id"], user_input={})

    assert created["type"] == FlowResultType.CREATE_ENTRY
    assert created["data"][CONF_BED_TYPE] == BED_TYPE_JIECANG


async def test_verify_connection_skipped_without_scanner(
    hass: HomeAssistant,
    mock_bluetooth_service_info_jiecang: BluetoothServiceInfoBleak,
    enable_custom_integrations,
) -> None:
    """With no connectable scanner the verify step is skipped, entry created directly."""
    mock_bluetooth_service_info = mock_bluetooth_service_info_jiecang
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    assert result["step_id"] == "bluetooth_confirm"

    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        created = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_PREFERRED_ADAPTER: "auto"}
        )
        created = await _advance_progress(hass, created)

    assert created["type"] == FlowResultType.CREATE_ENTRY
    assert created["data"][CONF_BED_TYPE] == BED_TYPE_JIECANG


# ---------------------------------------------------------------------------
# setup_progress step, driven through the real flow manager (issues #457, #460)
# ---------------------------------------------------------------------------


async def test_setup_shows_a_progress_view_before_the_result(
    hass: HomeAssistant,
    mock_bluetooth_service_info_jiecang: BluetoothServiceInfoBleak,
    enable_custom_integrations,
) -> None:
    """Submitting setup must render an active progress view, not a frozen form."""
    mock_bluetooth_service_info = mock_bluetooth_service_info_jiecang
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("hci0", -55),
        patch(
            "bleak_retry_connector.establish_connection",
            AsyncMock(return_value=_fake_connected_client()),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.discover_services",
            AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.read_ble_device_info",
            AsyncMock(return_value=(None, None)),
        ),
    ):
        progress = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_PREFERRED_ADAPTER: "auto"}
        )
        assert progress["type"] == FlowResultType.SHOW_PROGRESS
        assert progress["step_id"] == "setup_progress"
        # The view names the bed and the Bluetooth action under way.
        assert progress["progress_action"] in {
            "locating",
            "connecting",
            "discovering_services",
            "reading_capabilities",
            "disconnecting",
        }
        assert progress["description_placeholders"]["name"] == "JC-35TK1WT"

        done = await _advance_progress(hass, progress)
        assert done["step_id"] == "verify_connection"

        created = await hass.config_entries.flow.async_configure(done["flow_id"], user_input={})
    assert created["type"] == FlowResultType.CREATE_ENTRY


async def test_the_probe_runs_once_even_if_the_progress_step_is_re_entered(
    hass: HomeAssistant,
    mock_bluetooth_service_info_jiecang: BluetoothServiceInfoBleak,
    enable_custom_integrations,
) -> None:
    """A refresh or a double submit must not open a second BLE connection."""
    mock_bluetooth_service_info = mock_bluetooth_service_info_jiecang
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    connects = AsyncMock(return_value=_fake_connected_client())
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("hci0", -55),
        patch("bleak_retry_connector.establish_connection", connects),
        patch(
            "custom_components.adjustable_bed.config_flow.discover_services",
            AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.read_ble_device_info",
            AsyncMock(return_value=(None, None)),
        ),
    ):
        progress = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_PREFERRED_ADAPTER: "auto"}
        )
        # Poll the running step the way a reconnecting frontend would.
        again = await hass.config_entries.flow.async_configure(progress["flow_id"])
        assert again["type"] in (FlowResultType.SHOW_PROGRESS, FlowResultType.FORM)
        await _advance_progress(hass, again)

    assert connects.await_count == 1


async def test_consumed_setup_progress_does_not_start_another_probe(
    hass: HomeAssistant,
) -> None:
    """A late completion callback must keep returning progress-done."""
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._pending_entry = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
        CONF_NAME: "Test Bed",
    }
    flow.async_begin_operation()
    flow.operation.terminal_consumed = True

    with (
        patch.object(flow, "_async_start_probe_operation") as start_probe,
        patch.object(
            flow,
            "async_run_operation_step",
            new=AsyncMock(return_value={"type": FlowResultType.SHOW_PROGRESS_DONE}),
        ),
    ):
        result = await flow.async_step_setup_progress()

    assert result["type"] == FlowResultType.SHOW_PROGRESS_DONE
    start_probe.assert_not_called()


async def test_a_not_advertising_bed_offers_retry_and_still_allows_finishing(
    hass: HomeAssistant,
    mock_bluetooth_service_info_jiecang: BluetoothServiceInfoBleak,
    enable_custom_integrations,
) -> None:
    """The gate refusal is explained, retryable, and never blocks setup (#458)."""
    mock_bluetooth_service_info = mock_bluetooth_service_info_jiecang
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        patch("bleak_retry_connector.establish_connection") as connects,
    ):
        progress = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_PREFERRED_ADAPTER: "auto"}
        )
        verify = await _advance_progress(hass, progress)
        assert verify["step_id"] == "verify_connection"
        caps = verify["description_placeholders"]["capabilities"]
        assert "not currently advertising" in caps
        assert "select **Check again**" in caps
        # Nothing may reach the BLE stack once the gate has refused.
        connects.assert_not_called()

        # Retry re-runs the check in place rather than restarting the flow.
        retried = await hass.config_entries.flow.async_configure(
            verify["flow_id"], user_input={"action": "retry"}
        )
        assert retried["type"] == FlowResultType.SHOW_PROGRESS
        retried = await _advance_progress(hass, retried)
        assert retried["step_id"] == "verify_connection"

        created = await hass.config_entries.flow.async_configure(
            retried["flow_id"], user_input={"action": "finish"}
        )
    assert created["type"] == FlowResultType.CREATE_ENTRY
    assert created["data"][CONF_ADDRESS] == mock_bluetooth_service_info.address


async def test_an_advertising_bed_that_cannot_be_resolved_offers_retry(
    hass: HomeAssistant,
    mock_bluetooth_service_info_jiecang: BluetoothServiceInfoBleak,
    enable_custom_integrations,
) -> None:
    """A resolution gap must be retryable, not reported as "device not found".

    The bed is advertising, but Home Assistant's scanner view changes between
    the freshness check and the device lookup, so no BLEDevice comes back. That
    is the case that most deserves a Check again, and it used to be the one case
    that did not get one: the report stayed FRESH with no device, which fell
    through to the plain "device not found" branch and offered no retry action.

    The real gate and wait helper run here (only the device resolution is
    faked), so the assertions cover the whole path rather than a hand-built
    report. The advertisement is timestamped against the gate's own clock, which
    is left running so the bounded wait below can actually expire.
    """
    mock_bluetooth_service_info = mock_bluetooth_service_info_jiecang
    _freshness = "custom_components.adjustable_bed.bluetooth_freshness"
    advertising = SimpleNamespace(
        source="hci0",
        rssi=-60,
        time=freshness_monotonic() - 1.0,
        address=mock_bluetooth_service_info.address,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        patch("bleak_retry_connector.establish_connection") as connects,
        patch(f"{_freshness}.async_path_for_source", return_value=None),
        patch(f"{_freshness}.bluetooth.async_last_service_info", return_value=advertising),
        # The bed is advertising; only the handle to it is missing.
        patch(f"{_freshness}.async_resolve_ble_device", return_value=None),
        # Keep the built-in wait from holding the test for its full duration.
        patch(
            "custom_components.adjustable_bed.config_flow._PROBE_ADVERTISEMENT_WAIT_SECONDS",
            0.01,
        ),
    ):
        progress = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_PREFERRED_ADAPTER: "auto"}
        )
        verify = await _advance_progress(hass, progress)
        assert verify["step_id"] == "verify_connection"

        caps = verify["description_placeholders"]["capabilities"]
        assert "could not open a connection" in caps
        assert "**Check again**" in caps
        # The bed answered a scan, so neither of the old messages applies.
        assert "not currently advertising" not in caps
        assert "Device not found" not in caps
        # Nothing may reach the BLE stack without a resolved device.
        connects.assert_not_called()

        # The retry affordance must actually be on the form.
        assert "action" in {str(key) for key in verify["data_schema"].schema}

        created = await hass.config_entries.flow.async_configure(
            verify["flow_id"], user_input={"action": "finish"}
        )
    assert created["type"] == FlowResultType.CREATE_ENTRY


async def test_abandoning_the_flow_mid_probe_leaves_no_connected_client(
    hass: HomeAssistant,
    mock_bluetooth_service_info_jiecang: BluetoothServiceInfoBleak,
    enable_custom_integrations,
) -> None:
    """Cancellation must not leak the bed's single BLE connection."""
    mock_bluetooth_service_info = mock_bluetooth_service_info_jiecang
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    client = _fake_connected_client()
    release = asyncio.Event()
    reached_gatt = asyncio.Event()

    async def _slow_discover(*_args, **_kwargs):
        reached_gatt.set()
        await release.wait()
        return True

    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("hci0", -55),
        patch("bleak_retry_connector.establish_connection", AsyncMock(return_value=client)),
        patch(
            "custom_components.adjustable_bed.config_flow.discover_services",
            _slow_discover,
        ),
    ):
        progress = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_PREFERRED_ADAPTER: "auto"}
        )
        assert progress["type"] == FlowResultType.SHOW_PROGRESS

        # Abort only once the worker is genuinely holding an open client.
        async with asyncio.timeout(5):
            await reached_gatt.wait()

        hass.config_entries.flow.async_abort(progress["flow_id"])
        release.set()
        await hass.async_block_till_done()

    client.disconnect.assert_awaited()


# ---------------------------------------------------------------------------
# Unpair action in the options flow (issue #455)
# ---------------------------------------------------------------------------


# Matches the address the shared mock config entry is built with.
_BONDED_ADDRESS = "AA:BB:CC:DD:EE:FF"


def _bond_record(
    adapter_address: str | None = "11:22:33:44:55:66",
) -> LocalBondRecord:
    return LocalBondRecord(
        address=_BONDED_ADDRESS,
        device_path="/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",
        adapter_path="/org/bluez/hci0",
        adapter_address=adapter_address,
        paired=True,
        bonded=True,
    )


def _patch_local_prediction(source: str = "11:22:33:44:55:66", adapter: str = "hci0"):
    """Make the predicted path a proven local adapter."""
    path = ConnectionPath(source=source, transport=TransportClass.LOCAL, adapter=adapter)
    return patch(
        "custom_components.adjustable_bed.config_flow.async_predict_path",
        return_value=PathPrediction(chosen=path, paths=(path,)),
    )


def _patch_contested_prediction():
    """Predict the bonded adapter while a proxy could still take the connection."""
    bonded = ConnectionPath(
        source="11:22:33:44:55:66", transport=TransportClass.LOCAL, adapter="hci0"
    )
    proxy = ConnectionPath(source="bedroom-proxy", transport=TransportClass.PROXY)
    return patch(
        "custom_components.adjustable_bed.config_flow.async_predict_path",
        return_value=PathPrediction(chosen=bonded, paths=(bonded, proxy)),
    )


def _patch_inventory(inventory: LocalBondInventory):
    return patch(
        "custom_components.adjustable_bed.config_flow.async_read_local_bonds",
        AsyncMock(return_value=inventory),
    )


@contextlib.contextmanager
def _stubbed_coordinator(hass: HomeAssistant, entry_id: str, coordinator: Any):
    """Install a stand-in coordinator and take it out again afterwards.

    Scoped to the tests that actually stub one. An autouse fixture here would
    reach every test in the file, including the many that set the integration up
    for real and rely on hass.data during Home Assistant's own teardown.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    previous = domain_data.get(entry_id, _MISSING)
    domain_data[entry_id] = coordinator
    try:
        yield
    finally:
        if previous is _MISSING:
            domain_data.pop(entry_id, None)
        else:
            domain_data[entry_id] = previous


_MISSING = object()


def _transport_coordinator(error: Exception | None = None) -> tuple[Any, list[str]]:
    """Return a coordinator stub whose transport gate records its use."""
    entered: list[str] = []

    @contextlib.asynccontextmanager
    async def _gate(operation: str):
        if error is not None:
            raise error
        entered.append(operation)
        yield

    coordinator = MagicMock()
    coordinator.async_transport_operation = _gate
    return coordinator, entered


async def _open_remove_bond(hass: HomeAssistant, entry_id: str) -> Any:
    result = await hass.config_entries.options.async_init(entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "remove_bond"}
    )


async def test_unpair_requires_confirmation_and_names_the_transport(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """The confirmation has to say what is being removed and from where."""
    mock_config_entry.add_to_hass(hass)
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    with _patch_inventory(inventory):
        result = await _open_remove_bond(hass, mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "remove_bond"
    placeholders = result["description_placeholders"]
    assert placeholders["address"] == _BONDED_ADDRESS
    assert placeholders["transport"] == "11:22:33:44:55:66"


async def test_combined_bond_removal_targets_the_selected_child(
    hass: HomeAssistant,
    enable_custom_integrations,
) -> None:
    """The confirmation reads address and ownership from one child descriptor."""
    stored_left_address = f"  {_BONDED_ADDRESS.lower()}  "
    right_address = "AA:BB:CC:DD:EE:01"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Combined bed",
        data={
            CONF_NAME: "Combined bed",
            CONF_BED_TYPE: BED_TYPE_OKIMAT,
            CONF_PAIR_ID: "pair_bond_removal",
            CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
            CONF_PAIR_MEMBER_ADDRESSES: [stored_left_address, right_address],
            CONF_PAIR_CHILDREN: [
                {
                    CONF_SIDE: SIDE_LEFT,
                    CONF_ADDRESS: stored_left_address,
                    CONF_NAME: "Left side",
                    CONF_BED_TYPE: BED_TYPE_OKIMAT,
                    CONF_BLE_BOND_ESTABLISHED: True,
                    CONF_BLE_BOND_CONTEXT: {
                        "version": 1,
                        "transport": "local",
                        "source": "11:22:33:44:55:66",
                        "adapter": "hci0",
                    },
                },
                {
                    CONF_SIDE: SIDE_RIGHT,
                    CONF_ADDRESS: right_address,
                    CONF_NAME: "Right side",
                    CONF_BED_TYPE: BED_TYPE_OKIMAT,
                    CONF_BLE_BOND_ESTABLISHED: True,
                    CONF_BLE_BOND_CONTEXT: {
                        "version": 1,
                        "transport": "proxy",
                        "source": "bedroom-proxy",
                    },
                },
            ],
        },
        unique_id="pair_bond_removal",
        entry_id="pair_bond_removal",
    )
    entry.add_to_hass(hass)
    inventory = LocalBondInventory(
        status=BluezReadStatus.OK,
        records=(_bond_record(),),
    )

    menu = await hass.config_entries.options.async_init(entry.entry_id)
    side_form = await hass.config_entries.options.async_configure(
        menu["flow_id"],
        {"next_step_id": "remove_bond"},
    )
    with _patch_inventory(inventory) as read_bonds:
        result = await hass.config_entries.options.async_configure(
            side_form["flow_id"],
            {"side": SIDE_LEFT},
        )

    read_bonds.assert_awaited_once_with(_BONDED_ADDRESS)
    assert result["step_id"] == "remove_bond"
    assert result["description_placeholders"]["name"] == "Left side"
    assert result["description_placeholders"]["address"] == _BONDED_ADDRESS
    assert result["description_placeholders"]["transport"] == "11:22:33:44:55:66"

    removed = BondRemovalResult(
        status=BondRemovalStatus.REMOVED,
        record=_bond_record(),
    )
    child_coordinator, entered = _transport_coordinator()

    def apply_child_removal() -> None:
        children = []
        for child in entry.data[CONF_PAIR_CHILDREN]:
            child_data = dict(child)
            if child_data.get(CONF_SIDE) == SIDE_LEFT:
                child_data.pop(CONF_BLE_BOND_ESTABLISHED, None)
                child_data.pop(CONF_BLE_BOND_CONTEXT, None)
            children.append(child_data)
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_PAIR_CHILDREN: children},
        )

    child_coordinator.apply_confirmed_bond_removal.side_effect = apply_child_removal
    parent_coordinator = MagicMock()
    parent_coordinator.child_for_side.return_value = child_coordinator
    with (
        _stubbed_coordinator(hass, entry.entry_id, parent_coordinator),
        _patch_inventory(inventory),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=removed),
        ),
    ):
        progress = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {},
        )
        while progress["type"] == FlowResultType.SHOW_PROGRESS:
            await hass.async_block_till_done()
            progress = await hass.config_entries.options.async_configure(progress["flow_id"])

    assert entered == ["unpair"]
    parent_coordinator.child_for_side.assert_any_call(SIDE_LEFT)
    child_coordinator.apply_confirmed_bond_removal.assert_called_once_with()
    left = get_child(entry.data, SIDE_LEFT)
    right = get_child(entry.data, SIDE_RIGHT)
    assert left is not None and right is not None
    assert CONF_BLE_BOND_ESTABLISHED not in left
    assert CONF_BLE_BOND_CONTEXT not in left
    assert right[CONF_BLE_BOND_ESTABLISHED] is True
    assert right[CONF_BLE_BOND_CONTEXT]["source"] == "bedroom-proxy"


async def test_combined_bond_removal_does_not_fall_back_to_parent_coordinator(
    hass: HomeAssistant,
) -> None:
    """A missing child must not make a side-specific removal lock the whole pair."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Combined bed",
        data={
            CONF_NAME: "Combined bed",
            CONF_BED_TYPE: BED_TYPE_OKIMAT,
            CONF_PAIR_ID: "pair_missing_child_coordinator",
            CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
            CONF_PAIR_MEMBER_ADDRESSES: [
                _BONDED_ADDRESS,
                "AA:BB:CC:DD:EE:01",
            ],
            CONF_PAIR_CHILDREN: [
                {
                    CONF_SIDE: SIDE_LEFT,
                    CONF_ADDRESS: _BONDED_ADDRESS,
                    CONF_BED_TYPE: BED_TYPE_OKIMAT,
                },
                {
                    CONF_SIDE: SIDE_RIGHT,
                    CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
                    CONF_BED_TYPE: BED_TYPE_OKIMAT,
                },
            ],
        },
        unique_id="pair_missing_child_coordinator",
        entry_id="pair_missing_child_coordinator",
        version=4,
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    flow._bond_removal_side = SIDE_LEFT
    parent_coordinator = MagicMock()
    parent_coordinator.child_for_side.return_value = None

    with _stubbed_coordinator(hass, entry.entry_id, parent_coordinator):
        assert flow._bond_target_coordinator() is None

    parent_coordinator.child_for_side.assert_called_once_with(SIDE_LEFT)


async def test_cancelling_unpair_removes_nothing(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """Reaching the confirmation is not consent; only submitting it is."""
    mock_config_entry.add_to_hass(hass)
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    with (
        _patch_inventory(inventory),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
    ):
        await _open_remove_bond(hass, mock_config_entry.entry_id)
    removal.assert_not_called()


async def test_a_proxy_owned_bond_offers_no_host_side_removal(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """Home Assistant cannot clear a proxy's bond, so it must not pretend to."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={
            **mock_config_entry.data,
            CONF_BLE_BOND_CONTEXT: {
                "version": 1,
                "transport": "proxy",
                "source": "esphome_bedroom",
                "adapter": None,
            },
        },
    )
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    with (
        _patch_inventory(inventory),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
    ):
        result = await _open_remove_bond(hass, mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "remove_bond_proxy_owned"
    removal.assert_not_called()


async def test_an_unreadable_bluez_refuses_to_unpair(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """ "I could not ask" must never be treated as "there is nothing there"."""
    mock_config_entry.add_to_hass(hass)
    inventory = LocalBondInventory(status=BluezReadStatus.UNAVAILABLE)
    with (
        _patch_inventory(inventory),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
    ):
        result = await _open_remove_bond(hass, mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "remove_bond_bluez_unavailable"
    removal.assert_not_called()


async def test_no_bond_reports_nothing_to_do(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    mock_config_entry.add_to_hass(hass)
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=())
    with _patch_inventory(inventory):
        result = await _open_remove_bond(hass, mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "remove_bond_no_bond"


async def test_a_confirmed_unpair_clears_the_bond_marker(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """The marker is cleared only after a removal that was actually confirmed."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_BLE_BOND_ESTABLISHED: True},
    )
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    removed = BondRemovalResult(status=BondRemovalStatus.REMOVED, record=_bond_record())
    with (
        _patch_inventory(inventory),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=removed),
        ),
    ):
        confirm = await _open_remove_bond(hass, mock_config_entry.entry_id)
        progress = await hass.config_entries.options.async_configure(
            confirm["flow_id"], user_input={}
        )
        assert progress["type"] == FlowResultType.SHOW_PROGRESS
        assert progress["progress_action"] == "unpairing"
        await hass.async_block_till_done()
        # The worker owns this update. Closing the flow before the result screen
        # must not leave a removed bond recorded as present.
        assert CONF_BLE_BOND_ESTABLISHED not in mock_config_entry.data
        while progress["type"] == FlowResultType.SHOW_PROGRESS:
            progress = await hass.config_entries.options.async_configure(progress["flow_id"])

    assert progress["step_id"] == "remove_bond_result"
    assert "removed" in progress["description_placeholders"]["outcome"]
    assert CONF_BLE_BOND_ESTABLISHED not in mock_config_entry.data


async def test_a_confirmed_unpair_does_not_reload_and_recreate_the_bond(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """Persisting an explicit unpair must not reconnect with pairing enabled."""
    from custom_components.adjustable_bed.__init__ import _async_update_listener
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_BLE_BOND_ESTABLISHED: True},
    )
    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    remove_listener = mock_config_entry.add_update_listener(_async_update_listener)
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    removed = BondRemovalResult(status=BondRemovalStatus.REMOVED, record=_bond_record())

    try:
        with (
            _stubbed_coordinator(hass, mock_config_entry.entry_id, coordinator),
            _patch_inventory(inventory),
            patch(
                "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
                AsyncMock(return_value=removed),
            ),
            patch.object(
                hass.config_entries, "async_reload", new_callable=AsyncMock
            ) as reload_entry,
        ):
            confirm = await _open_remove_bond(hass, mock_config_entry.entry_id)
            progress = await hass.config_entries.options.async_configure(
                confirm["flow_id"], user_input={}
            )
            while progress["type"] == FlowResultType.SHOW_PROGRESS:
                await hass.async_block_till_done()
                progress = await hass.config_entries.options.async_configure(progress["flow_id"])

            reload_entry.assert_not_awaited()
    finally:
        remove_listener()

    assert CONF_BLE_BOND_ESTABLISHED not in mock_config_entry.data
    assert coordinator._ble_bond_established is False


async def test_an_unconfirmed_removal_keeps_the_bond_marker(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """A backend that could not confirm is a failure, not a quiet success."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_BLE_BOND_ESTABLISHED: True},
    )
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    failed = BondRemovalResult(
        status=BondRemovalStatus.VERIFICATION_FAILED,
        record=_bond_record(),
        error="bond_still_present",
    )
    with (
        _patch_inventory(inventory),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=failed),
        ),
    ):
        confirm = await _open_remove_bond(hass, mock_config_entry.entry_id)
        progress = await hass.config_entries.options.async_configure(
            confirm["flow_id"], user_input={}
        )
        while progress["type"] == FlowResultType.SHOW_PROGRESS:
            await hass.async_block_till_done()
            progress = await hass.config_entries.options.async_configure(progress["flow_id"])

    assert progress["step_id"] == "remove_bond_result"
    assert "not removed" in progress["description_placeholders"]["outcome"]
    assert mock_config_entry.data[CONF_BLE_BOND_ESTABLISHED] is True


async def test_unpair_releases_the_bed_before_touching_the_bond(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """A live coordinator must be quiesced through its own locking order."""
    mock_config_entry.add_to_hass(hass)
    coordinator, entered = _transport_coordinator()
    stub = _stubbed_coordinator(hass, mock_config_entry.entry_id, coordinator)

    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    removed = BondRemovalResult(status=BondRemovalStatus.REMOVED, record=_bond_record())
    with (
        stub,
        _patch_inventory(inventory),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=removed),
        ),
    ):
        confirm = await _open_remove_bond(hass, mock_config_entry.entry_id)
        progress = await hass.config_entries.options.async_configure(
            confirm["flow_id"], user_input={}
        )
        while progress["type"] == FlowResultType.SHOW_PROGRESS:
            await hass.async_block_till_done()
            progress = await hass.config_entries.options.async_configure(progress["flow_id"])

    assert entered == ["unpair"]


async def test_a_bed_that_cannot_be_released_is_not_unpaired(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """Better to leave the bond alone than to remove it mid-command."""
    mock_config_entry.add_to_hass(hass)
    coordinator, _entered = _transport_coordinator(error=RuntimeError("still connected"))
    stub = _stubbed_coordinator(hass, mock_config_entry.entry_id, coordinator)

    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    with (
        stub,
        _patch_inventory(inventory),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
    ):
        confirm = await _open_remove_bond(hass, mock_config_entry.entry_id)
        progress = await hass.config_entries.options.async_configure(
            confirm["flow_id"], user_input={}
        )
        while progress["type"] == FlowResultType.SHOW_PROGRESS:
            await hass.async_block_till_done()
            progress = await hass.config_entries.options.async_configure(progress["flow_id"])

    removal.assert_not_called()
    assert "not removed" in progress["description_placeholders"]["outcome"]


# ---------------------------------------------------------------------------
# Pairing must be gated on a real advertisement, and verified (issues #458, #461)
# ---------------------------------------------------------------------------


async def _finish_pairing(hass: HomeAssistant, flow: Any) -> Any:
    """Drive a started pairing operation through to its result form and submit."""
    await hass.async_block_till_done()
    await flow.async_step_pairing_progress()
    result = await flow.async_step_pairing_result()
    assert result["type"] is FlowResultType.FORM
    return await flow.async_step_pairing_result({"action": "finish"})


async def _run_pairing(hass: HomeAssistant, flow: Any) -> Any:
    """Start pairing from the form and drive it to the created entry."""
    with _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK)):
        progress = await flow.async_step_bluetooth_pairing({"action": "pair_now"})
        assert progress["type"] is FlowResultType.SHOW_PROGRESS
        return await _finish_pairing(hass, flow)


def _pairing_flow(hass: HomeAssistant) -> AdjustableBedConfigFlow:
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._manual_data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
        CONF_NAME: "Paired Okimat",
        CONF_BED_TYPE: BED_TYPE_OKIMAT,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }
    flow.context = {"source": SOURCE_USER}
    return flow


async def test_pairing_never_connects_to_a_bed_that_is_not_advertising(
    hass: HomeAssistant,
) -> None:
    """The whole point of #458 is that this never reaches the BLE stack."""
    flow = _pairing_flow(hass)
    stale = AdvertisementEvidence(status=FreshnessStatus.STALE, age_seconds=600.0)
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            AsyncMock(return_value=(stale, None)),
        ),
        patch("bleak_retry_connector.establish_connection") as connects,
    ):
        result = await flow._async_pairing_worker()

    connects.assert_not_called()
    # Not a pairing failure: saying so would send the user after the wrong thing.
    assert result.outcome is OperationOutcome.NOT_ADVERTISING


async def test_an_unauthenticated_link_is_not_recorded_as_a_bond(
    hass: HomeAssistant,
) -> None:
    """GATT error 5 after pairing means the bond did not form."""
    flow = _pairing_flow(hass)
    failed = BondEvidence(
        status=BondVerificationStatus.AUTH_FAILED,
        owner=BondOwner(transport=TransportClass.LOCAL, source="hci0"),
        operation="setup_pairing",
        observed_at="2026-07-27T00:00:00+00:00",
        error="Insufficient authentication",
    )
    with patch.object(flow, "_attempt_pairing", AsyncMock(return_value=failed)):
        result = await flow._async_pairing_worker()

    assert result.outcome is OperationOutcome.BOND_VERIFICATION_FAILED


async def test_an_unprovable_bond_records_pairing_without_ownership(
    hass: HomeAssistant,
) -> None:
    """Most pairing-required protocols have no bond-gated read to prove this.

    The marker still has to be written, or the coordinator pairs again on its
    first connection - and re-pairing an already-bonded proxy device can return
    auth error 82 and wedge the link. The provenance is what stays absent: an
    unproven owner must never authorize removing a host bond.
    """
    flow = _pairing_flow(hass)
    unsupported = BondEvidence(
        status=BondVerificationStatus.UNSUPPORTED,
        owner=BondOwner(transport=TransportClass.LOCAL, source="hci0"),
        operation="setup_pairing",
        observed_at="2026-07-27T00:00:00+00:00",
    )
    with patch.object(flow, "_attempt_pairing", AsyncMock(return_value=unsupported)):
        result = await _run_pairing(hass, flow)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BLE_BOND_ESTABLISHED] is True
    assert CONF_BLE_BOND_CONTEXT not in result["data"]


async def test_an_inconclusive_probe_records_pairing_without_ownership(
    hass: HomeAssistant,
) -> None:
    """A timeout or a missing characteristic proves nothing either way.

    Nothing contradicted the pairing, so the same rule applies as for a protocol
    with no verifier at all: record that it happened, claim no owner.
    """
    flow = _pairing_flow(hass)
    inconclusive = BondEvidence(
        status=BondVerificationStatus.INCONCLUSIVE,
        owner=BondOwner(transport=TransportClass.LOCAL, source="hci0"),
        operation="setup_pairing",
        observed_at="2026-07-27T00:00:00+00:00",
        error="timeout",
    )
    with patch.object(flow, "_attempt_pairing", AsyncMock(return_value=inconclusive)):
        result = await _run_pairing(hass, flow)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BLE_BOND_ESTABLISHED] is True
    assert CONF_BLE_BOND_CONTEXT not in result["data"]


async def test_a_verified_bond_over_a_proxy_records_the_proxy_as_owner(
    hass: HomeAssistant,
) -> None:
    """Ownership decides whether a later unpair may touch host BlueZ at all."""
    flow = _pairing_flow(hass)
    with patch.object(
        flow,
        "_attempt_pairing",
        AsyncMock(return_value=_verified_evidence(TransportClass.PROXY)),
    ):
        result = await _run_pairing(hass, flow)

    assert result["data"][CONF_BLE_BOND_ESTABLISHED] is True
    assert result["data"][CONF_BLE_BOND_CONTEXT]["transport"] == "proxy"


async def test_replacing_a_bond_that_cannot_be_removed_does_not_pair(
    hass: HomeAssistant,
) -> None:
    """Pairing on top of a bond the user asked to replace would hide the failure."""
    flow = _pairing_flow(hass)
    flow._pairing_remove_record = _bond_record()
    flow._pairing_mode = "replace_local"
    fresh = AdvertisementEvidence(
        status=FreshnessStatus.FRESH, age_seconds=1.0, rssi=-55, source="hci0"
    )
    failed = BondRemovalResult(
        status=BondRemovalStatus.VERIFICATION_FAILED, error="bond_still_present"
    )
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            AsyncMock(return_value=(fresh, MagicMock())),
        ),
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=failed),
        ),
        patch.object(flow, "_attempt_pairing") as attempt,
    ):
        result = await flow._async_pairing_worker()

    attempt.assert_not_called()
    assert result.outcome is OperationOutcome.UNPAIR_FAILED


async def test_unverified_bond_removal_does_not_claim_the_bond_remains(
    hass: HomeAssistant,
) -> None:
    """An unreadable post-removal inventory leaves the bond state unknown."""
    flow = _pairing_flow(hass)
    flow._pairing_remove_record = _bond_record()
    flow._pairing_mode = "replace_local"
    fresh = AdvertisementEvidence(
        status=FreshnessStatus.FRESH, age_seconds=1.0, rssi=-55, source="hci0"
    )
    unconfirmed = BondRemovalResult(
        status=BondRemovalStatus.VERIFICATION_FAILED,
        error="bluez_unreadable_after_removal",
    )
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            AsyncMock(return_value=(fresh, MagicMock())),
        ),
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=unconfirmed),
        ),
        patch.object(flow, "_attempt_pairing") as attempt,
    ):
        result = await flow._async_pairing_worker()

    attempt.assert_not_called()
    assert result.outcome is OperationOutcome.UNPAIR_UNCONFIRMED
    outcome = await flow._async_pairing_outcome_note(result, None)
    assert "could not confirm what happened to the existing bond" in outcome


async def test_a_sleeping_bed_never_loses_its_bond_to_a_replacement(
    hass: HomeAssistant,
) -> None:
    """Removing first would leave a sleeping bed with no bond and no way back."""
    flow = _pairing_flow(hass)
    flow._pairing_remove_record = _bond_record()
    flow._pairing_mode = "replace_local"
    flow._manual_data[CONF_PREFERRED_ADAPTER] = "11:22:33:44:55:66"
    stale = AdvertisementEvidence(status=FreshnessStatus.STALE, age_seconds=600.0)
    wait = AsyncMock(return_value=(stale, None))
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            wait,
        ),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
        patch.object(flow, "_attempt_pairing") as attempt,
    ):
        result = await flow._async_pairing_worker()

    removal.assert_not_called()
    attempt.assert_not_called()
    assert wait.await_args.kwargs["source"] == "11:22:33:44:55:66"
    assert result.outcome is OperationOutcome.NOT_ADVERTISING


async def test_replacement_requires_a_resolved_device_before_removing_the_bond(
    hass: HomeAssistant,
) -> None:
    """Fresh history alone is not enough to safely destroy the old bond."""
    flow = _pairing_flow(hass)
    flow._pairing_remove_record = _bond_record()
    flow._pairing_mode = "replace_local"
    fresh = AdvertisementEvidence(
        status=FreshnessStatus.FRESH, age_seconds=1.0, rssi=-55, source="hci0"
    )
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            AsyncMock(return_value=(fresh, None)),
        ),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
        patch.object(flow, "_attempt_pairing") as attempt,
    ):
        result = await flow._async_pairing_worker()

    removal.assert_not_called()
    attempt.assert_not_called()
    assert result.outcome is OperationOutcome.NOT_ADVERTISING


@pytest.mark.parametrize(
    ("step", "origin"),
    [
        ("async_step_bluetooth_pairing", "bluetooth_pairing"),
        ("async_step_manual_pairing", "manual_pairing"),
    ],
)
async def test_replacing_a_bond_requires_its_own_confirmation(
    hass: HomeAssistant, step: str, origin: str
) -> None:
    """#461 routes the replace action through confirmation, not a list choice."""
    flow = _pairing_flow(hass)
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    with (
        _patch_inventory(inventory),
        _patch_local_prediction(),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
    ):
        result = await getattr(flow, step)({"action": "remove_bond_and_pair"})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pairing_replace_confirm"
    assert flow._pairing_origin_step == origin
    # Naming the adapter matters on a host with more than one.
    assert result["description_placeholders"]["transport"] == "11:22:33:44:55:66"
    removal.assert_not_called()


async def test_bond_replacement_holds_the_address_lock_through_pairing(
    hass: HomeAssistant,
) -> None:
    """No competing connector may enter between removal and replacement."""
    flow = _pairing_flow(hass)
    flow._pairing_remove_record = _bond_record()
    flow._pairing_mode = "replace_local"
    lock = async_get_connect_lock(hass, flow._manual_data[CONF_ADDRESS])
    fresh = AdvertisementEvidence(
        status=FreshnessStatus.FRESH, age_seconds=1.0, rssi=-55, source="hci0"
    )

    async def remove(_record: LocalBondRecord) -> BondRemovalResult:
        assert lock.locked()
        return BondRemovalResult(status=BondRemovalStatus.REMOVED)

    async def pair(*_args: Any, **_kwargs: Any) -> BondEvidence:
        assert lock.locked()
        return _verified_evidence()

    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            AsyncMock(return_value=(fresh, MagicMock())),
        ),
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(side_effect=remove),
        ),
        patch.object(flow, "_attempt_pairing", AsyncMock(side_effect=pair)),
    ):
        result = await flow._async_pairing_worker()

    assert result.outcome is OperationOutcome.SUCCESS
    assert not lock.locked()


async def test_a_one_connection_bed_defers_pairing_without_removing_a_bond(
    hass: HomeAssistant,
) -> None:
    """Gen2 must not spend its single connection, even to replace a bond.

    Removing the bond here would leave the box refusing every reconnect until it
    is power-cycled, with nothing to show for it (#385).
    """
    flow = _pairing_flow(hass)
    flow._manual_data[CONF_BED_TYPE] = BED_TYPE_LEGGETT_GEN2
    flow._pairing_remove_record = _bond_record()

    with (
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
        patch.object(flow, "_attempt_pairing") as attempt,
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK)),
    ):
        result = await flow.async_step_bluetooth_pairing({"action": "pair_now"})

    removal.assert_not_called()
    attempt.assert_not_called()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"].get(CONF_BLE_BOND_ESTABLISHED) is not True


async def test_pair_now_immediately_shows_a_progress_view(
    hass: HomeAssistant,
) -> None:
    """Pairing is the slowest thing setup does, so it must not freeze the form."""
    flow = _pairing_flow(hass)
    with (
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK)),
        patch.object(flow, "_attempt_pairing", AsyncMock(return_value=_verified_evidence())),
    ):
        result = await flow.async_step_bluetooth_pairing({"action": "pair_now"})

        assert result["type"] is FlowResultType.SHOW_PROGRESS
        assert result["step_id"] == "pairing_progress"
        await hass.async_block_till_done()


async def test_a_verified_pairing_result_names_the_transport(
    hass: HomeAssistant,
) -> None:
    """#461 wants a visible confirmation, and it has to say where the bond went."""
    flow = _pairing_flow(hass)
    with (
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK)),
        patch.object(
            flow,
            "_attempt_pairing",
            AsyncMock(return_value=_verified_evidence(TransportClass.PROXY)),
        ),
    ):
        await flow.async_step_bluetooth_pairing({"action": "pair_now"})
        await hass.async_block_till_done()
        await flow.async_step_pairing_progress()
        result = await flow.async_step_pairing_result()

    outcome = result["description_placeholders"]["outcome"]
    assert "confirmed" in outcome
    assert "proxy" in outcome.lower()
    assert "hci0" in outcome


async def test_existing_bond_result_does_not_claim_a_new_pairing(
    hass: HomeAssistant,
) -> None:
    """Verifying an existing bond is not the same operation as creating one."""
    flow = _pairing_flow(hass)
    flow._pairing_mode = "verify_existing"
    outcome = await flow._async_pairing_outcome_note(
        OperationResult(outcome=OperationOutcome.SUCCESS, payload=_verified_evidence()),
        _verified_evidence(),
    )

    assert "existing bond works" in outcome
    assert "Paired, and" not in outcome


async def test_verified_bond_with_unknown_owner_does_not_claim_host_storage(
    hass: HomeAssistant,
) -> None:
    """A successful authenticated read does not always identify its route."""
    flow = _pairing_flow(hass)
    evidence = BondEvidence(
        status=BondVerificationStatus.VERIFIED,
        owner=BondOwner(),
        operation="setup_pairing",
        observed_at="2026-07-27T00:00:00+00:00",
    )
    outcome = await flow._async_pairing_outcome_note(
        OperationResult(outcome=OperationOutcome.SUCCESS, payload=evidence),
        evidence,
    )

    assert "does not know where the bond is stored" in outcome
    assert "stored on this Home Assistant host" not in outcome


async def test_pairing_outcome_uses_the_active_language(
    hass: HomeAssistant,
) -> None:
    """The result placeholder must not remain English in a localized flow."""
    flow = _pairing_flow(hass)
    key = "component.adjustable_bed.config.step.pairing_result.data_description.outcome_cancelled"
    with patch(
        "custom_components.adjustable_bed.config_flow.async_get_translations",
        AsyncMock(return_value={key: "❌ Paringen ble avbrutt."}),
    ):
        outcome = await flow._async_pairing_outcome_note(
            OperationResult(outcome=OperationOutcome.CANCELLED),
            None,
        )

    assert outcome == "❌ Paringen ble avbrutt."


async def test_each_pairing_failure_gets_its_own_advice(
    hass: HomeAssistant,
) -> None:
    """A bed that never answered a scan needs different advice from a failed bond."""
    flow = _pairing_flow(hass)
    stale = AdvertisementEvidence(status=FreshnessStatus.STALE, age_seconds=600.0)
    with (
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK)),
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            AsyncMock(return_value=(stale, None)),
        ),
    ):
        await flow.async_step_bluetooth_pairing({"action": "pair_now"})
        await hass.async_block_till_done()
        await flow.async_step_pairing_progress()
        result = await flow.async_step_pairing_result()

    assert "not advertising" in result["description_placeholders"]["outcome"]
    # A failure offers a way forward rather than a dead end.
    assert result["data_schema"].schema


async def test_a_replayed_submission_cannot_confirm_a_pairing_result(
    hass: HomeAssistant,
) -> None:
    """The flow manager replays the caller's input through its progress-done loop."""
    flow = _pairing_flow(hass)
    with (
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK)),
        patch.object(flow, "_attempt_pairing", AsyncMock(return_value=_verified_evidence())),
    ):
        await flow.async_step_bluetooth_pairing({"action": "pair_now"})
        await hass.async_block_till_done()
        await flow.async_step_pairing_progress()
        # The original submission arriving before the result form was drawn.
        replayed = await flow.async_step_pairing_result({"action": "pair_now"})

    assert replayed["type"] is FlowResultType.FORM
    assert replayed["step_id"] == "pairing_result"


# ---------------------------------------------------------------------------
# Unpair target safety (issue #455)
# ---------------------------------------------------------------------------


def _record_on(adapter_path: str, adapter_address: str) -> LocalBondRecord:
    return LocalBondRecord(
        address=_BONDED_ADDRESS,
        device_path=f"{adapter_path}/dev_AA_BB_CC_DD_EE_FF",
        adapter_path=adapter_path,
        adapter_address=adapter_address,
        paired=True,
        bonded=True,
    )


def _with_provenance(
    hass: HomeAssistant, entry: MockConfigEntry, *, source: str, adapter: str | None = None
) -> None:
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_BLE_BOND_CONTEXT: {
                "version": 1,
                "transport": "local",
                "source": source,
                "adapter": adapter,
            },
        },
    )


async def test_unpair_removes_the_adapter_provenance_names_not_the_first(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """A local scanner's source is its adapter MAC; adapter is the interface name.

    Comparing the interface name against BlueZ's adapter MAC matches nothing, and
    silently fell through to "whichever record came first" - the wrong bond on a
    two-adapter host.
    """
    first = _record_on("/org/bluez/hci0", "11:22:33:44:55:66")
    second = _record_on("/org/bluez/hci1", "AA:AA:AA:AA:AA:AA")
    _with_provenance(hass, mock_config_entry, source="AA:AA:AA:AA:AA:AA", adapter="hci1")

    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(first, second))
    removed = BondRemovalResult(status=BondRemovalStatus.REMOVED, record=second)
    with (
        _patch_inventory(inventory),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=removed),
        ) as removal,
    ):
        confirm = await _open_remove_bond(hass, mock_config_entry.entry_id)
        assert confirm["description_placeholders"]["transport"] == "AA:AA:AA:AA:AA:AA"
        progress = await hass.config_entries.options.async_configure(
            confirm["flow_id"], user_input={}
        )
        while progress["type"] == FlowResultType.SHOW_PROGRESS:
            await hass.async_block_till_done()
            progress = await hass.config_entries.options.async_configure(progress["flow_id"])

    removal.assert_awaited_once()
    assert removal.await_args[0][0].adapter_path == "/org/bluez/hci1"


async def test_unpair_refuses_when_provenance_names_an_adapter_with_no_bond(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """Removing "the only one left" would delete a bond nothing pointed at."""
    only = _record_on("/org/bluez/hci0", "11:22:33:44:55:66")
    _with_provenance(hass, mock_config_entry, source="AA:AA:AA:AA:AA:AA")

    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(only,))
    with (
        _patch_inventory(inventory),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
    ):
        result = await _open_remove_bond(hass, mock_config_entry.entry_id)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "remove_bond_ambiguous"
    removal.assert_not_called()


async def test_unpair_refuses_two_bonds_with_no_provenance(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    mock_config_entry.add_to_hass(hass)
    first = _record_on("/org/bluez/hci0", "11:22:33:44:55:66")
    second = _record_on("/org/bluez/hci1", "AA:AA:AA:AA:AA:AA")
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(first, second))
    with (
        _patch_inventory(inventory),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
    ):
        result = await _open_remove_bond(hass, mock_config_entry.entry_id)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "remove_bond_ambiguous"
    removal.assert_not_called()


async def test_a_legacy_entry_uses_its_predicted_local_adapter_to_unpair(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """A selected local path disambiguates legacy entries with two host bonds."""
    first = _record_on("/org/bluez/hci0", "11:22:33:44:55:66")
    second = _record_on("/org/bluez/hci1", "AA:AA:AA:AA:AA:AA")
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={
            **mock_config_entry.data,
            CONF_PREFERRED_ADAPTER: "AA:AA:AA:AA:AA:AA",
        },
    )
    mock_config_entry.add_to_hass(hass)
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(first, second))
    with (
        _patch_inventory(inventory),
        _patch_local_prediction("AA:AA:AA:AA:AA:AA", "hci1"),
    ):
        result = await _open_remove_bond(hass, mock_config_entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["description_placeholders"]["transport"] == "AA:AA:AA:AA:AA:AA"


async def test_a_legacy_entry_with_one_bond_can_still_unpair_but_says_so(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """Entries paired before provenance existed must not lose the action entirely.

    There is exactly one host bond for this exact address, so there is nothing to
    choose between - but the confirmation says the transport is unknown rather
    than implying it was verified.
    """
    mock_config_entry.add_to_hass(hass)
    only = _record_on("/org/bluez/hci0", "11:22:33:44:55:66")
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(only,))
    with _patch_inventory(inventory):
        result = await _open_remove_bond(hass, mock_config_entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert (
        "no record of which transport created" in (result["description_placeholders"]["provenance"])
    )


async def test_unpair_refuses_when_the_bond_state_changed_after_confirmation(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """The bond shown and the bond removed have to be the same object."""
    mock_config_entry.add_to_hass(hass)
    shown = _record_on("/org/bluez/hci0", "11:22:33:44:55:66")
    moved = _record_on("/org/bluez/hci1", "AA:AA:AA:AA:AA:AA")

    inventories = [
        LocalBondInventory(status=BluezReadStatus.OK, records=(shown,)),
        LocalBondInventory(status=BluezReadStatus.OK, records=(moved,)),
    ]
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_read_local_bonds",
            AsyncMock(side_effect=inventories),
        ),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
    ):
        confirm = await _open_remove_bond(hass, mock_config_entry.entry_id)
        assert confirm["description_placeholders"]["transport"] == "11:22:33:44:55:66"
        result = await hass.config_entries.options.async_configure(
            confirm["flow_id"], user_input={}
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "remove_bond_changed"
    removal.assert_not_called()


async def test_the_preview_follows_the_adapter_the_user_actually_picked(
    hass: HomeAssistant,
    mock_bluetooth_service_info: BluetoothServiceInfoBleak,
    enable_custom_integrations,
) -> None:
    """Previewing the defaults can omit the warning for the chosen combination."""
    seen: list[tuple] = []

    async def _note(_self, address, adapter, bed_type=None, variant=None):
        # Patched onto the class, so the bound instance arrives positionally.
        seen.append((address, adapter, bed_type, variant))
        return "preview"

    with (
        patch.object(AdjustableBedConfigFlow, "_async_transport_note", _note),
        # The adapter has to be offered by the form before it can be submitted,
        # and the schema is built on the first render.
        patch(
            "custom_components.adjustable_bed.config_flow.get_available_adapters",
            return_value={"auto": "Automatic", "esphome_bedroom": "Bedroom proxy"},
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )
        # A variant that does not belong to the chosen bed type re-renders the
        # form with everything the user submitted still in hand.
        rendered = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                # A pairing-required type, so the proxy warning is relevant.
                CONF_BED_TYPE: BED_TYPE_VIBRADORM,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: LEGGETT_VARIANT_GEN2,
                CONF_PREFERRED_ADAPTER: "esphome_bedroom",
            },
        )
        assert rendered["type"] is FlowResultType.FORM

    assert seen, "the form should have been re-rendered with a preview"
    _address, adapter, bed_type, _variant = seen[-1]
    assert adapter == "esphome_bedroom"
    assert bed_type == BED_TYPE_VIBRADORM


async def test_typed_address_setup_previews_the_transport_once_it_is_valid(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """Raw manual entry had no preview at all before connecting."""
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {"source": SOURCE_USER}

    with patch.object(
        AdjustableBedConfigFlow,
        "_async_transport_note",
        AsyncMock(return_value="Likely connection: Direct Bluetooth"),
    ):
        # An invalid motor count keeps us on the form, with the address known.
        result = await flow.async_step_manual_entry(
            {
                CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
                CONF_BED_TYPE: BED_TYPE_OKIMAT,
                CONF_MOTOR_COUNT: 99,
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert "Direct Bluetooth" in result["description_placeholders"]["transport"]


async def test_typed_address_setup_previews_nothing_before_an_address_exists(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """There is nothing to predict until the user has typed a real address."""
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {"source": SOURCE_USER}

    result = await flow.async_step_manual_entry(None)

    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"]["transport"] == ""


async def test_a_replayed_confirmation_cannot_leave_a_removed_bond_marked(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """The progress-done loop replays the confirmation's input into the result.

    If that were treated as acknowledgement before the result form had been
    drawn, BlueZ would have removed the bond while the entry still claimed to be
    bonded, and the coordinator would skip pairing and retry an unauthenticated
    connection forever.
    """
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_BLE_BOND_ESTABLISHED: True},
    )
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    removed = BondRemovalResult(status=BondRemovalStatus.REMOVED, record=_bond_record())
    with (
        _patch_inventory(inventory),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=removed),
        ),
    ):
        confirm = await _open_remove_bond(hass, mock_config_entry.entry_id)
        progress = await hass.config_entries.options.async_configure(
            confirm["flow_id"], user_input={}
        )
        while progress["type"] == FlowResultType.SHOW_PROGRESS:
            await hass.async_block_till_done()
            progress = await hass.config_entries.options.async_configure(progress["flow_id"])

    # However the result step was reached, the removal is reflected in the entry.
    assert CONF_BLE_BOND_ESTABLISHED not in mock_config_entry.data
    assert CONF_BLE_BOND_CONTEXT not in mock_config_entry.data


async def test_pairing_refuses_rather_than_bonding_through_another_adapter(
    hass: HomeAssistant,
) -> None:
    """A bond belongs to whichever transport made it.

    Falling back to some other adapter would store it somewhere the user did not
    choose, while the marker claimed pairing was done. The refusal comes from
    the freshness lookup rather than the prediction: only the lookup checks the
    non-connectable bucket, which is where some proxies file a bed they can
    connect to perfectly well.
    """
    flow = _pairing_flow(hass)
    flow._manual_data[CONF_PREFERRED_ADAPTER] = "hci0"
    elsewhere = ConnectionPath(source="proxy", transport=TransportClass.PROXY)
    unavailable = AdvertisementEvidence(status=FreshnessStatus.SOURCE_UNAVAILABLE)
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_predict_path",
            return_value=PathPrediction(
                chosen=elsewhere,
                paths=(elsewhere,),
                preferred_adapter="hci0",
                preferred_available=False,
            ),
        ),
        patch("bleak_retry_connector.establish_connection") as connects,
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            AsyncMock(return_value=(unavailable, None)),
        ) as wait,
        pytest.raises(NotAdvertisingError),
    ):
        await flow._attempt_pairing("AA:BB:CC:DD:EE:01")

    # The pinned adapter is what was asked about, and nothing connected.
    assert wait.await_args.kwargs["source"] == "hci0"
    connects.assert_not_called()


async def test_a_pinned_proxy_seen_only_as_non_connectable_can_still_pair(
    hass: HomeAssistant,
) -> None:
    """Some ESPHome proxies file a connectable bed in the non-connectable bucket.

    The prediction only enumerates connectable scanners, so deciding there would
    block pairing over exactly the proxy that Automatic mode uses happily.
    """
    flow = _pairing_flow(hass)
    flow._manual_data[CONF_PREFERRED_ADAPTER] = "bedroom_proxy"
    fresh = AdvertisementEvidence(
        status=FreshnessStatus.FRESH, age_seconds=1.0, rssi=-60, source="bedroom_proxy"
    )
    device = MagicMock()
    client = MagicMock()
    client.pair = AsyncMock()
    client.disconnect = AsyncMock()
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_predict_path",
            return_value=PathPrediction(
                chosen=None,
                paths=(),
                preferred_adapter="bedroom_proxy",
                preferred_available=False,
            ),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            AsyncMock(return_value=(fresh, device)),
        ) as wait,
        patch(
            "bleak_retry_connector.establish_connection",
            new=AsyncMock(return_value=client),
        ) as connects,
    ):
        await flow._attempt_pairing("AA:BB:CC:DD:EE:01")

    # Asked about the pinned proxy, and connected through it rather than
    # refusing on the prediction's say-so.
    assert wait.await_args.kwargs["source"] == "bedroom_proxy"
    assert connects.await_args.args[1] is device


async def test_a_legacy_entry_now_routing_through_a_proxy_cannot_unpair(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """No provenance plus a proxy route means the host record is a leftover.

    The bond that matters to the user lives on the proxy, so acting on the
    host's copy would be guessing which one they meant.
    """
    mock_config_entry.add_to_hass(hass)
    proxy = ConnectionPath(source="proxy", transport=TransportClass.PROXY)
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    with (
        _patch_inventory(inventory),
        patch(
            "custom_components.adjustable_bed.config_flow.async_predict_path",
            return_value=PathPrediction(chosen=proxy, paths=(proxy,)),
        ),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
    ):
        result = await _open_remove_bond(hass, mock_config_entry.entry_id)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "remove_bond_proxy_owned"
    removal.assert_not_called()


async def test_verifying_an_existing_bond_probes_its_owning_adapter(
    hass: HomeAssistant,
) -> None:
    """Verification over a stronger unbonded adapter would fail for no reason."""
    flow = _pairing_flow(hass)
    inventory = LocalBondInventory(
        status=BluezReadStatus.OK, records=(_bond_record(adapter_address="11:22:33:44:55:66"),)
    )

    with (
        _patch_inventory(inventory),
        _patch_local_prediction(),
        patch.object(flow, "_async_start_pairing_operation", AsyncMock()),
    ):
        await flow.async_step_manual_pairing({"action": "use_existing_bond"})

    assert flow._pairing_mode == "verify_existing"
    assert flow._pairing_verify_source == "11:22:33:44:55:66"

    wait = AsyncMock(return_value=(AdvertisementEvidence(status=FreshnessStatus.MISSING), None))
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            wait,
        ),
        pytest.raises(NotAdvertisingError),
    ):
        await flow._attempt_pairing(flow._manual_data[CONF_ADDRESS], request_bond=False)

    assert wait.await_args.kwargs["source"] == "11:22:33:44:55:66"


async def test_bond_replacement_completes_even_if_the_flow_goes_away(
    hass: HomeAssistant,
) -> None:
    """A cancelled progress dialog must not strand the bed between bonds."""
    flow = _pairing_flow(hass)
    flow._pairing_remove_record = _bond_record()
    flow._pairing_mode = "replace_local"
    fresh = AdvertisementEvidence(
        status=FreshnessStatus.FRESH, age_seconds=1.0, rssi=-55, source="hci0"
    )
    removed = BondRemovalResult(status=BondRemovalStatus.REMOVED, record=_bond_record())
    paired = asyncio.Event()

    async def _slow_pairing(*_args: Any, **_kwargs: Any) -> BondEvidence:
        await asyncio.sleep(0)
        paired.set()
        return _verified_evidence()

    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            AsyncMock(return_value=(fresh, MagicMock())),
        ),
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=removed),
        ),
        patch.object(flow, "_attempt_pairing", _slow_pairing),
    ):
        worker = hass.async_create_task(flow._async_pairing_worker())
        await asyncio.sleep(0)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker
        # The shielded replacement keeps running even though its caller is gone.
        await asyncio.wait_for(paired.wait(), timeout=1)

    assert paired.is_set()


async def test_flow_cleanup_does_not_disconnect_a_running_bond_replacement(
    hass: HomeAssistant,
) -> None:
    """The detached replacement task owns its client until verification ends."""
    flow = _pairing_flow(hass)
    flow._pairing_remove_record = _bond_record()
    flow._pairing_mode = "replace_local"
    client = MagicMock()
    client.disconnect = AsyncMock()
    verification_started = asyncio.Event()
    finish_verification = asyncio.Event()

    async def verify(*_args: Any, **_kwargs: Any) -> BondEvidence:
        verification_started.set()
        await finish_verification.wait()
        return _verified_evidence()

    with (
        _patch_pairing_gate(),
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=BondRemovalResult(status=BondRemovalStatus.REMOVED)),
        ),
        patch(
            "bleak_retry_connector.establish_connection",
            AsyncMock(return_value=client),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.client_source",
            return_value="hci0",
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.async_verify_authenticated_access",
            side_effect=verify,
        ),
    ):
        worker = hass.async_create_task(flow._async_pairing_worker())
        await asyncio.wait_for(verification_started.wait(), timeout=1)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

        flow.async_remove()
        await asyncio.sleep(0)
        client.disconnect.assert_not_awaited()

        finish_verification.set()
        await hass.async_block_till_done()

    client.disconnect.assert_awaited_once()


async def test_a_confirmed_unpair_persists_without_the_result_screen(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """Closing the dialog must not leave the entry claiming a bond BlueZ deleted."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_BLE_BOND_ESTABLISHED: True},
    )
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    removed = BondRemovalResult(status=BondRemovalStatus.REMOVED, record=_bond_record())
    with (
        _patch_inventory(inventory),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=removed),
        ),
    ):
        confirm = await _open_remove_bond(hass, mock_config_entry.entry_id)
        progress = await hass.config_entries.options.async_configure(
            confirm["flow_id"], user_input={}
        )
        assert progress["type"] == FlowResultType.SHOW_PROGRESS
        # Let the worker finish, then walk away rather than advancing to the
        # result step that used to own this update.
        await hass.async_block_till_done()
        hass.config_entries.options.async_abort(progress["flow_id"])

    assert CONF_BLE_BOND_ESTABLISHED not in mock_config_entry.data


async def test_replacement_confirmation_revalidates_the_exact_bond(
    hass: HomeAssistant,
) -> None:
    """A stale confirmation must not authorize removing a changed record."""
    flow = _pairing_flow(hass)
    flow._pairing_origin_step = "manual_pairing"
    flow._pairing_remove_record = _bond_record()
    changed = LocalBondInventory(status=BluezReadStatus.OK)

    with (
        _patch_inventory(changed),
        _patch_local_prediction(),
        patch.object(flow, "_async_start_pairing_operation") as start,
    ):
        result = await flow.async_step_pairing_replace_confirm({})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual_pairing"
    assert flow._pairing_remove_record is None
    start.assert_not_called()


async def test_replacement_revalidates_the_bond_under_the_address_lock(
    hass: HomeAssistant,
) -> None:
    """A changed BlueZ record must never inherit an earlier confirmation."""
    flow = _pairing_flow(hass)
    address = flow._manual_data[CONF_ADDRESS]
    lock = async_get_connect_lock(hass, address)

    async def changed_inventory(_address: str) -> LocalBondInventory:
        assert lock.locked()
        # A bond is still there, it is simply not the one that was confirmed.
        return LocalBondInventory(
            status=BluezReadStatus.OK,
            records=(_bond_record(adapter_address="AA:AA:AA:AA:AA:AA"),),
        )

    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_read_local_bonds",
            AsyncMock(side_effect=changed_inventory),
        ),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
        patch.object(flow, "_attempt_pairing") as attempt,
    ):
        result = await flow._async_replace_bond(address, _bond_record())

    removal.assert_not_called()
    attempt.assert_not_called()
    assert result.outcome is OperationOutcome.UNPAIR_FAILED
    assert result.detail == "bond_changed_before_removal"


async def test_an_unreadable_revalidation_does_not_claim_the_bond_survived(
    hass: HomeAssistant,
) -> None:
    """A failed BlueZ read proves nothing, so it must not be reported as a failure.

    "The old bond is still in place" is a claim about BlueZ that a read which
    never answered cannot support, and it sends the user looking for a bond that
    may not be there.
    """
    flow = _pairing_flow(hass)
    address = flow._manual_data[CONF_ADDRESS]

    with (
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.UNAVAILABLE)),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
        patch.object(flow, "_attempt_pairing") as attempt,
    ):
        result = await flow._async_replace_bond(address, _bond_record())

    # Nothing was removed and nothing was paired, so neither may be claimed.
    removal.assert_not_called()
    attempt.assert_not_called()
    assert result.outcome is OperationOutcome.UNPAIR_UNCONFIRMED
    assert result.detail == "bond_unreadable_before_removal"


async def test_a_bond_already_gone_pairs_instead_of_refusing(
    hass: HomeAssistant,
) -> None:
    """Nothing destructive is left to do, and the user still asked to pair."""
    flow = _pairing_flow(hass)
    address = flow._manual_data[CONF_ADDRESS]

    with (
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK)),
        patch("custom_components.adjustable_bed.config_flow.async_remove_local_bond") as removal,
        patch.object(
            flow, "_attempt_pairing", AsyncMock(return_value=_verified_evidence())
        ) as attempt,
    ):
        result = await flow._async_replace_bond(address, _bond_record())

    # Removing a record that is not there would be the only thing that could
    # fail here, so it is skipped rather than attempted and reported.
    removal.assert_not_called()
    attempt.assert_awaited_once()
    assert result.outcome is OperationOutcome.SUCCESS


async def test_replacement_holds_the_address_lock_until_pairing_finishes(
    hass: HomeAssistant,
) -> None:
    """No other connector may enter after removal and before the new bond."""
    flow = _pairing_flow(hass)
    locked = False

    @contextlib.asynccontextmanager
    async def address_lock(_hass: HomeAssistant, _address: str):
        nonlocal locked
        locked = True
        try:
            yield
        finally:
            locked = False

    async def remove(_record: LocalBondRecord) -> BondRemovalResult:
        assert locked
        return BondRemovalResult(status=BondRemovalStatus.REMOVED)

    async def pair(*_args: Any, **_kwargs: Any) -> BondEvidence:
        assert locked
        return _verified_evidence()

    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_get_connect_lock",
            address_lock,
        ),
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            side_effect=remove,
        ),
        patch.object(flow, "_attempt_pairing", side_effect=pair),
    ):
        result = await flow._async_replace_bond(flow._manual_data[CONF_ADDRESS], _bond_record())

    assert result.outcome is OperationOutcome.SUCCESS
    assert not locked


async def test_rpc_failure_leaves_bond_removal_unconfirmed(
    hass: HomeAssistant,
) -> None:
    """A lost D-Bus reply cannot prove whether RemoveDevice took effect."""
    flow = _pairing_flow(hass)
    uncertain = BondRemovalResult(
        status=BondRemovalStatus.RPC_FAILED,
        error="timed out",
    )
    with (
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=uncertain),
        ),
        patch.object(flow, "_attempt_pairing") as attempt,
    ):
        result = await flow._async_replace_bond(flow._manual_data[CONF_ADDRESS], _bond_record())

    assert result.outcome is OperationOutcome.UNPAIR_UNCONFIRMED
    attempt.assert_not_called()


async def test_existing_bond_verification_rejects_a_rerouted_connection(
    hass: HomeAssistant,
) -> None:
    """Advertisement selection alone cannot pin HA's eventual connection route."""
    flow = _pairing_flow(hass)
    flow._pairing_verify_source = "11:22:33:44:55:66"
    client = MagicMock()
    client.disconnect = AsyncMock()
    verifier = AsyncMock()

    with (
        _patch_pairing_gate(),
        patch(
            "bleak_retry_connector.establish_connection",
            AsyncMock(return_value=client),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.client_source",
            return_value="22:33:44:55:66:77",
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.async_path_for_source",
            return_value=None,
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.async_verify_authenticated_access",
            verifier,
        ),
    ):
        result = await flow._async_pair_and_classify(
            flow._manual_data[CONF_ADDRESS], "verify_existing"
        )

    assert result.outcome is OperationOutcome.BOND_VERIFICATION_INCONCLUSIVE
    verifier.assert_not_awaited()
    client.disconnect.assert_awaited_once()


async def test_verifying_an_existing_bond_never_invents_a_marker(
    hass: HomeAssistant,
) -> None:
    """Verification mode asks for no bond, so an unproven result claims nothing.

    Only a mode that actually requested a bond may record that one happened.
    """
    flow = _pairing_flow(hass)
    flow._pairing_mode = "verify_existing"
    unsupported = BondEvidence(
        status=BondVerificationStatus.UNSUPPORTED,
        owner=BondOwner(transport=TransportClass.LOCAL, source="hci0"),
        operation="verify_existing_bond",
        observed_at="2026-07-27T00:00:00+00:00",
    )

    flow.async_begin_operation(
        name="Paired Okimat",
        address=flow._manual_data[CONF_ADDRESS],
        prediction=PathPrediction(chosen=None, paths=()),
        action=SetupAction.LOCATING,
        placeholders={},
    )
    flow.operation.result = OperationResult(outcome=OperationOutcome.SUCCESS, payload=unsupported)
    flow._pairing_result_shown = True
    result = await flow.async_step_pairing_result({})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"].get(CONF_BLE_BOND_ESTABLISHED) is not True
    assert CONF_BLE_BOND_CONTEXT not in result["data"]


async def test_verification_falls_back_to_the_matched_route_source(
    hass: HomeAssistant,
) -> None:
    """BlueZ does not always publish an adapter address for a bond it holds."""
    flow = _pairing_flow(hass)
    record = LocalBondRecord(
        address=_BONDED_ADDRESS,
        device_path="/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",
        adapter_path="/org/bluez/hci0",
        adapter_address=None,
        paired=True,
        bonded=True,
    )
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(record,))

    with (
        _patch_inventory(inventory),
        _patch_local_prediction("11:22:33:44:55:66", "hci0"),
        patch.object(flow, "_async_start_pairing_operation", AsyncMock()),
    ):
        await flow.async_step_manual_pairing({"action": "use_existing_bond"})

    # The route was matched to this exact record, so its source names the same
    # adapter the missing address would have.
    assert flow._pairing_verify_source == "11:22:33:44:55:66"


async def test_a_one_connection_bed_keeps_the_bond_it_was_told_to_use(
    hass: HomeAssistant,
) -> None:
    """Deferring without the markers would ask the coordinator to pair anyway.

    That spends the single connection the user avoided spending by picking the
    existing bond in the first place.
    """
    flow = _pairing_flow(hass)
    flow._manual_data[CONF_BED_TYPE] = BED_TYPE_LEGGETT_GEN2
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))

    with (
        _patch_inventory(inventory),
        _patch_local_prediction(),
        patch.object(flow, "_attempt_pairing") as attempt,
    ):
        result = await flow.async_step_manual_pairing({"action": "use_existing_bond"})

    attempt.assert_not_called()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BLE_BOND_ESTABLISHED] is True
    assert result["data"][CONF_BLE_BOND_CONTEXT]["source"] == "11:22:33:44:55:66"


async def test_bond_replacement_reuses_the_device_it_already_resolved(
    hass: HomeAssistant,
) -> None:
    """A second lookup can return None to scanner churn, after the bond is gone."""
    flow = _pairing_flow(hass)
    flow._pairing_remove_record = _bond_record()
    flow._pairing_mode = "replace_local"
    fresh = AdvertisementEvidence(
        status=FreshnessStatus.FRESH, age_seconds=1.0, rssi=-55, source="hci0"
    )
    device = MagicMock()
    removed = BondRemovalResult(status=BondRemovalStatus.REMOVED, record=_bond_record())
    wait = AsyncMock(return_value=(fresh, device))
    attempt = AsyncMock(return_value=_verified_evidence())

    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            wait,
        ),
        _patch_inventory(LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=removed),
        ),
        patch.object(flow, "_attempt_pairing", attempt),
    ):
        result = await flow._async_pairing_worker()

    assert result.outcome is OperationOutcome.SUCCESS
    # Resolved once, before the removal, and carried into the replacement.
    assert wait.await_count == 1
    assert attempt.await_args.kwargs["device"] is device


async def test_a_detected_usable_bond_is_the_default_action(hass: HomeAssistant) -> None:
    """Submitting the form unchanged must not re-pair on top of a good bond."""
    flow = _pairing_flow(hass)
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))

    with _patch_inventory(inventory), _patch_local_prediction():
        result = await flow.async_step_manual_pairing(None)

    key = next(iter(result["data_schema"].schema))
    assert key.default() == "use_existing_bond"


async def test_a_legacy_entry_can_unpair_the_adapter_it_is_pinned_to(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """Without provenance, the route the bed will use answers "which adapter"."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={
            **mock_config_entry.data,
            CONF_BLE_BOND_ESTABLISHED: True,
            CONF_PREFERRED_ADAPTER: "11:22:33:44:55:66",
        },
    )
    # Two bonded adapters and no recorded owner: ambiguous unless the chosen
    # route is allowed to pick.
    inventory = LocalBondInventory(
        status=BluezReadStatus.OK,
        records=(
            _bond_record(adapter_address="11:22:33:44:55:66"),
            LocalBondRecord(
                address=_BONDED_ADDRESS,
                device_path="/org/bluez/hci1/dev_AA_BB_CC_DD_EE_FF",
                adapter_path="/org/bluez/hci1",
                adapter_address="22:33:44:55:66:77",
                paired=True,
                bonded=True,
            ),
        ),
    )
    with _patch_inventory(inventory), _patch_local_prediction("11:22:33:44:55:66", "hci0"):
        result = await _open_remove_bond(hass, mock_config_entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "remove_bond"
    assert result["description_placeholders"]["transport"] == "11:22:33:44:55:66"


async def test_a_confirmed_removal_survives_a_cancelled_dialog(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """Cancelling mid-removal must not strand the entry's bond markers.

    BlueZ may already have accepted RemoveDevice when the user closes the
    dialog, and an entry that still claims a bond makes every later connection
    skip pairing.
    """
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_BLE_BOND_ESTABLISHED: True},
    )
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    removed = BondRemovalResult(status=BondRemovalStatus.REMOVED, record=_bond_record())
    inside = asyncio.Event()
    release = asyncio.Event()

    async def _slow_removal(_record: LocalBondRecord) -> BondRemovalResult:
        inside.set()
        await release.wait()
        return removed

    with (
        _patch_inventory(inventory),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            _slow_removal,
        ),
    ):
        confirm = await _open_remove_bond(hass, mock_config_entry.entry_id)
        progress = await hass.config_entries.options.async_configure(
            confirm["flow_id"], user_input={}
        )
        assert progress["type"] == FlowResultType.SHOW_PROGRESS
        await inside.wait()
        # The user closes the dialog while BlueZ is mid-removal.
        hass.config_entries.options.async_abort(progress["flow_id"])
        release.set()


async def test_cancelling_after_removal_starts_still_applies_the_confirmed_result(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """Closing progress cannot strand state after BlueZ may have removed the bond."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_BLE_BOND_ESTABLISHED: True},
    )
    inventory = LocalBondInventory(status=BluezReadStatus.OK, records=(_bond_record(),))
    removed = BondRemovalResult(status=BondRemovalStatus.REMOVED, record=_bond_record())
    removal_started = asyncio.Event()
    finish_removal = asyncio.Event()

    async def _slow_confirmed_removal(_record: LocalBondRecord) -> BondRemovalResult:
        removal_started.set()
        await finish_removal.wait()
        return removed

    with (
        _patch_inventory(inventory),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            side_effect=_slow_confirmed_removal,
        ),
    ):
        confirm = await _open_remove_bond(hass, mock_config_entry.entry_id)
        progress = await hass.config_entries.options.async_configure(
            confirm["flow_id"], user_input={}
        )
        async with asyncio.timeout(5):
            await removal_started.wait()

        hass.config_entries.options.async_abort(progress["flow_id"])
        finish_removal.set()
        await hass.async_block_till_done()

    assert CONF_BLE_BOND_ESTABLISHED not in mock_config_entry.data


def test_shown_option_values_coerces_defaults():
    """String schema defaults are coerced like user_input, so an unchanged
    numeric field is not mistaken for a change in the paired-options save."""
    import voluptuous as vol

    from custom_components.adjustable_bed.config_flow import _shown_option_values

    schema = {
        vol.Optional("pulse", default="10"): vol.Coerce(int),
        vol.Optional("angle", default="68.0"): vol.Coerce(float),
    }
    assert _shown_option_values(schema) == {"pulse": 10, "angle": 68.0}


async def test_the_probe_hands_its_client_to_the_operation_cleanup(
    hass: HomeAssistant,
) -> None:
    """A cancelled flow must still have something to close.

    The probe's own disconnect is an ordinary await and can be interrupted, so
    the operation has to own the client from the moment it exists or the bed's
    single connection stays open until the transport gives up on it.
    """
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    client = _fake_connected_client()
    tracked: list[Any] = []

    with (
        _patch_gate("hci0", -55),
        patch("bleak_retry_connector.establish_connection", AsyncMock(return_value=client)),
        patch(
            "custom_components.adjustable_bed.config_flow.discover_services",
            AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.read_ble_device_info",
            AsyncMock(return_value=(None, None)),
        ),
    ):
        await flow._probe_capabilities(
            "AA:BB:CC:DD:EE:01",
            "auto",
            BED_TYPE_OKIMAT,
            client_tracker=tracked.append,
        )

    # Registered while live, cleared only after the disconnect completed.
    assert tracked == [client, None]


async def test_an_interrupted_disconnect_leaves_the_probe_client_tracked(
    hass: HomeAssistant,
) -> None:
    """Clearing the tracker before the link is really closed would orphan it."""
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    client = _fake_connected_client()
    client.disconnect = AsyncMock(side_effect=asyncio.CancelledError)
    tracked: list[Any] = []

    with (
        _patch_gate("hci0", -55),
        patch("bleak_retry_connector.establish_connection", AsyncMock(return_value=client)),
        patch(
            "custom_components.adjustable_bed.config_flow.discover_services",
            AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.read_ble_device_info",
            AsyncMock(return_value=(None, None)),
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await flow._probe_capabilities(
            "AA:BB:CC:DD:EE:01",
            "auto",
            BED_TYPE_OKIMAT,
            client_tracker=tracked.append,
        )

    assert tracked == [client]


async def test_a_reconnect_while_confirming_still_authorizes_the_replacement(
    hass: HomeAssistant,
) -> None:
    """``connected``/``trusted`` flip on their own while the dialog is open.

    Whole-record equality read that as "a different bond", threw away the
    approval the user had just given and bounced them back to the pairing form.
    Identity is the device object and its adapter, not the bed's link state.
    """
    flow = _pairing_flow(hass)
    flow._pairing_origin_step = "manual_pairing"
    record = _bond_record()
    flow._pairing_remove_record = record
    reconnected = LocalBondInventory(
        status=BluezReadStatus.OK,
        records=(replace(record, connected=True, trusted=True),),
    )

    with (
        _patch_inventory(reconnected),
        _patch_local_prediction(),
        patch.object(flow, "_async_start_pairing_operation") as start,
    ):
        await flow.async_step_pairing_replace_confirm({})

    start.assert_called_once()
    assert flow._pairing_remove_record == record


async def test_a_reconnect_before_removal_still_replaces_the_bond(
    hass: HomeAssistant,
) -> None:
    """The worker re-reads under the lock and must reach the same verdict."""
    flow = _pairing_flow(hass)
    address = flow._manual_data[CONF_ADDRESS]
    record = _bond_record()
    reconnected = LocalBondInventory(
        status=BluezReadStatus.OK,
        records=(replace(record, connected=True, trusted=True),),
    )

    with (
        _patch_inventory(reconnected),
        patch(
            "custom_components.adjustable_bed.config_flow.async_remove_local_bond",
            AsyncMock(return_value=BondRemovalResult(status=BondRemovalStatus.REMOVED)),
        ) as removal,
        patch.object(flow, "_attempt_pairing", AsyncMock(return_value=_verified_evidence())),
    ):
        result = await flow._async_replace_bond(address, record)

    removal.assert_awaited_once()
    assert result.outcome is OperationOutcome.SUCCESS


async def _unproven_pairing_entry(hass: HomeAssistant, *, source: str | None) -> dict[str, Any]:
    """Finish setup after a successful pair that nothing could verify."""
    flow = _pairing_flow(hass)
    flow._pairing_mode = "new"
    unsupported = BondEvidence(
        status=BondVerificationStatus.UNSUPPORTED,
        owner=BondOwner(transport=TransportClass.LOCAL, source=source),
        operation="pair_and_verify",
        observed_at="2026-07-27T00:00:00+00:00",
    )

    flow.async_begin_operation(
        name="Okimat",
        address=flow._manual_data[CONF_ADDRESS],
        prediction=PathPrediction(chosen=None, paths=()),
        action=SetupAction.LOCATING,
        placeholders={},
    )
    flow.operation.result = OperationResult(outcome=OperationOutcome.SUCCESS, payload=unsupported)
    flow._pairing_result_shown = True
    result = await flow.async_step_pairing_result({})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    return dict(result["data"])


async def test_an_unproven_bond_marker_is_scoped_to_the_route_that_paired(
    hass: HomeAssistant,
) -> None:
    """The marker suppresses pair=True, so it may not speak for other routes.

    With automatic routing the first real connection can be re-ranked onto an
    adapter or proxy that was never bonded. A global marker would skip pairing
    there and fail authentication on a link that only needed pairing.
    """
    data = await _unproven_pairing_entry(hass, source="11:22:33:44:55:66")

    assert data[CONF_BLE_BOND_ESTABLISHED] is True
    assert data[CONF_BLE_BOND_ATTEMPTED_SOURCE] == "11:22:33:44:55:66"
    # Unproven state must never look like the provenance that authorizes
    # removing a host bond.
    assert CONF_BLE_BOND_CONTEXT not in data


async def test_an_unproven_bond_with_no_known_route_records_no_marker(
    hass: HomeAssistant,
) -> None:
    """Nothing to scope it to, so the bed simply pairs again on first connect."""
    data = await _unproven_pairing_entry(hass, source=None)

    assert data.get(CONF_BLE_BOND_ESTABLISHED) is not True
    assert CONF_BLE_BOND_ATTEMPTED_SOURCE not in data
    assert CONF_BLE_BOND_CONTEXT not in data


async def test_a_proven_bond_records_provenance_and_no_route_scope(
    hass: HomeAssistant,
) -> None:
    """Provenance names its own owner, so there is nothing left to scope."""
    flow = _pairing_flow(hass)
    flow._pairing_mode = "new"
    flow._manual_data[CONF_BLE_BOND_ATTEMPTED_SOURCE] = "stale-source"

    flow.async_begin_operation(
        name="Okimat",
        address=flow._manual_data[CONF_ADDRESS],
        prediction=PathPrediction(chosen=None, paths=()),
        action=SetupAction.LOCATING,
        placeholders={},
    )
    flow.operation.result = OperationResult(
        outcome=OperationOutcome.SUCCESS, payload=_verified_evidence()
    )
    flow._pairing_result_shown = True
    result = await flow.async_step_pairing_result({})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BLE_BOND_ESTABLISHED] is True
    assert CONF_BLE_BOND_CONTEXT in result["data"]
    assert CONF_BLE_BOND_ATTEMPTED_SOURCE not in result["data"]
