"""Factory helpers other tests share, factory auto-detection and base controller cleanup."""

from __future__ import annotations

import asyncio
from importlib import import_module
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.leggett.lp_legacy_profiles import LP_LEGACY_PROFILE_CODES
from custom_components.adjustable_bed.const import (
    BED_TYPE_COOLBASE,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_LP_LEGACY,
    BED_TYPE_OCTO,
    BED_TYPE_RICHMAT,
    CONF_LP_LEGACY_MODE,
    CONF_LP_LEGACY_MODEL,
    CONF_LP_LEGACY_WRITE_UUID,
    KEESON_JSON_SERVICE_UUID,
    KEESON_VARIANT_JSON,
    KEESON_VARIANT_OKIN,
    KEESON_VARIANT_SINO,
    MALOUF_LAYOUT_AUTO,
    MALOUF_MEMORY_SLOTS_AUTO,
    OCTO_VARIANT_STANDARD,
    RICHMAT_VARIANT_NORDIC,
    RICHMAT_VARIANT_WILINKE,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.controller_factory import (
    _create_from_registry,
    create_controller,
)
from custom_components.adjustable_bed.controller_state import StateKey, StateUpdate


class _RecordingImportExecutor:
    """Stand in for hass.async_add_import_executor_job, recording each call.

    The registry imports controller modules lazily, so the import has to be
    handed to the import executor rather than run on the event loop. Recording
    the calls is what makes a regression to a direct import_module fail here
    instead of only showing up as a runtime warning from HA (issue #368).
    """

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def __call__(self, func: Any, *args: Any) -> Any:
        self.calls.append((func, *args))
        return func(*args)


class _FactoryCoordinator(SimpleNamespace):
    """Minimal coordinator stub used for controller factory tests."""

    def __init__(self) -> None:
        super().__init__(
            capability_controller=None,
            starcode_app_retained_state=None,
            furnimove_widget_state=(False, None, None),
            rize_home_source="button",
            hass=SimpleNamespace(
                data={},
                async_add_import_executor_job=_RecordingImportExecutor(),
                async_add_executor_job=_RecordingImportExecutor(),
            ),
            client=None,
            controller_state={},
            _pairlink_runtime=None,
            entry=SimpleNamespace(
                title="Contract Test Bed",
                async_on_unload=lambda callback: None,
                options={},
                data={
                    const.CONF_FURNIMOVE_REMOTE: "00000",
                    const.CONF_LOGICDATA_APP_PROFILE: "phone",
                    const.CONF_LOGICDATA_APP_FAMILY: "p1",
                    const.CONF_LOGICDATA_APP_LAYOUT: "standard_2",
                    const.CONF_LOGICDATA_APP_TRANSPORT: "t1",
                    const.CONF_JIECANG_APP_PROFILE: "dreamask",
                    const.CONF_JIECANG_APP_LAYOUT: "standard_2",
                    const.CONF_JIECANG_APP_TRANSPORT: "g1",
                    const.CONF_MALOUF_APP_PROFILE: "malouf",
                    const.CONF_MALOUF_APP_MODEL: "L600",
                    const.CONF_MALOUF_APP_TRANSPORT: "okin_new",
                    const.CONF_STARCODE_M5X5_PROFILE: "cb25",
                    const.CONF_STARCODE_M1X12_PROFILE: "cb25",
                    const.CONF_BLE_DEVICE_NAME: "STAR252201123456",
                    const.CONF_PRODUCT_TYPE: "bed",
                    const.CONF_VIBRADORM_APP_PROFILE: "caresse",
                    const.CONF_VIBRADORM_CONTROL_TYPE: "2",
                    const.CONF_VMATBASIC_PROFILE: "basic",
                    const.CONF_REMACRO_MODEL: 50,
                    const.CONF_STARCODE_COMMAND_SELECTOR: "none",
                    const.CONF_STARCODE_UI_SELECTOR: "none",
                    const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX3633",
                }
            ),
            cancel_command=asyncio.Event(),
            motor_pulse_count=10,
            motor_pulse_delay_ms=100,
            address="AA:BB:CC:DD:EE:FF",
            name="Contract Test Bed",
            ble_device_name="Contract Test Bed",
            ble_model=None,
            motor_count=2,
            has_massage=False,
            disable_angle_sensing=True,
            remember_vmatbasic_settings=lambda settings: None,
            malouf_layout=MALOUF_LAYOUT_AUTO,
            malouf_memory_slots=MALOUF_MEMORY_SLOTS_AUTO,
        )

    async def async_execute_controller_command(self, *args: Any, **kwargs: Any) -> None:
        """Stub command executor used by keepalive-capable controllers."""
        return None

    _ble_bond_established = False

    def remember_sleep_number_mcr_client_id(self, identifier: int) -> None:
        """Retain the builder's local identity for later factory calls."""
        self.entry.data = {**self.entry.data, const.CONF_SLEEP_NUMBER_MCR_CLIENT_ID: identifier}

    def _begin_internal_entry_update(self, bond_established: bool) -> None:
        """Accept the internal-update marker a builder sets before persisting."""
        del bond_established

    def _async_persist_config(self, data: dict[str, Any], *, keys: set[str]) -> None:
        """Persist builder-written entry data onto the stub entry."""
        del keys
        self.entry.data = data

    def get_max_angle(self, position_key: str) -> float:
        """Return the integration's default calibration for a position axis."""
        return 45.0 if position_key in {"legs", "feet"} else 68.0

    def handle_controller_state_updates(self, *updates: StateUpdate) -> None:
        """Accept controller-published diagnostic state during construction."""
        del updates

    def handle_controller_state_update(self, key: StateKey[Any], value: Any) -> None:
        """Accept one controller-published state value during construction."""
        del key, value


def _protocol_variant_for_bed_type(bed_type: str) -> str | None:
    """Return a deterministic protocol variant for factory-completeness tests."""
    if bed_type == "meisemobell":
        return "15_22_15a"
    if bed_type in {"personal_comfort", "instant_comfort"}:
        return "anm3"
    if bed_type == const.BED_TYPE_ADJUSTABLE_BED:
        return "adjustable_bed_okin"
    if bed_type == BED_TYPE_RICHMAT:
        return RICHMAT_VARIANT_NORDIC
    if bed_type == BED_TYPE_OCTO:
        return OCTO_VARIANT_STANDARD
    if bed_type == "awmotion":
        return "SN300"
    if bed_type == "muuegm":
        return "ABF03"
    if bed_type == "dreamsense":
        return "blue"
    if bed_type == "saatva":
        return "bt2000_standard"
    if bed_type == "silksnow":
        return "slikpremier"
    if bed_type == "motionflex":
        return "sn300"
    if bed_type == const.BED_TYPE_MLILY0:
        return "bedc"
    if bed_type == const.BED_TYPE_CASPER_BASE:
        return "casperpro"
    if bed_type == const.BED_TYPE_JEROME_ADJUSTABLE_BASE:
        return "JERN"
    if bed_type == const.BED_TYPE_RESTONIC:
        return "box15"
    if bed_type == "kingkoil":
        return "KSBT03CK"
    if bed_type == const.BED_TYPE_SOMOS:
        return "a"
    if bed_type == const.BED_TYPE_YAMADA:
        return "p1"
    if bed_type == const.BED_TYPE_AMBIENT:
        return "one_piece"
    if bed_type == const.BED_TYPE_BETTERLIVING2:
        return "p1"
    if bed_type == const.BED_TYPE_COMFORTBASE:
        return "accord"
    if bed_type == const.BED_TYPE_COMFORT_ENHANCEMENTS:
        return "mc2"
    if bed_type == const.BED_TYPE_GLIDEAWAY_MOTION:
        return "motion_400"
    if bed_type == const.BED_TYPE_ZSERIES:
        return const.ZSERIES_VARIANT_Z230
    return None


def _make_connected_client() -> SimpleNamespace:
    """Create a minimal connected BLE client for factory calls that need one."""
    return SimpleNamespace(
        is_connected=True,
        services=[SimpleNamespace(uuid="0000")],
        address="AA:BB:CC:DD:EE:FF",
    )


async def _create_controller_for_bed_type(
    bed_type: str, variant: str | None = None
) -> BedController:
    """Create a controller through the factory for a bed type and optional variant."""
    coordinator = _FactoryCoordinator()
    client = _make_connected_client()
    if bed_type == "amada":
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "ab"
    if bed_type == const.BED_TYPE_BETTERLIVING2:
        coordinator.entry.data.update({const.CONF_PRODUCT_TYPE: "2", const.CONF_PROTOCOL_VARIANT: variant or "p1"})
        return await create_controller(coordinator, bed_type, variant or "p1", client)
    if bed_type == const.BED_TYPE_ORMATEK:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "new"
        variant = "okin15" if not variant or variant == VARIANT_AUTO else variant
    if bed_type in {"personal_comfort", "instant_comfort"}:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "two" if bed_type == "instant_comfort" and variant == "anm5" else "other"
    if bed_type == const.BED_TYPE_LEVA:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "ascent"
        return await create_controller(coordinator, bed_type, variant or "nordic", client)
    if bed_type == const.BED_TYPE_SLEEP_ASSIST_PRO:
        coordinator.entry.data.update({
            const.CONF_BLE_DEVICE_NAME: "KSBT012345678",
            const.CONF_HAS_LIGHT: True,
            "sleep_assist_pro_controls": ["head", "feet", "side_b", "rgb", "massage_timer", "tv"],
        })
    if bed_type == const.BED_TYPE_LINX:
        coordinator.entry.data.update({const.CONF_PRODUCT_TYPE: "quest", const.CONF_PROTOCOL_VARIANT: "a00a", const.CONF_BLE_DEVICE_NAME: "KSWF07D00000000"})
        return await create_controller(coordinator, bed_type, variant or "a00a", client)
    if bed_type == const.BED_TYPE_SYMPHONY_SLEEP:
        coordinator.entry.data.update({const.CONF_PRODUCT_TYPE: "600E", const.CONF_PROTOCOL_VARIANT: variant or "box1"})
        return await create_controller(coordinator, bed_type, variant or "box1", client)
    if bed_type == const.BED_TYPE_SYMPHONY:
        coordinator.entry.data.update({const.CONF_PRODUCT_TYPE: "0", const.CONF_PROTOCOL_VARIANT: "0"})
    if bed_type in (
        const.BED_TYPE_BEDGEAR, const.BED_TYPE_L2MOTION, const.BED_TYPE_MOODBASE,
        const.BED_TYPE_ERGOBED,
    ):
        coordinator.entry.data[const.CONF_BLE_DEVICE_NAME] = "HHC0000001D00X"
    if bed_type == const.BED_TYPE_RESTONIC:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "prime"
    if bed_type == "cheerssleep":
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "45"
    if bed_type in ("sleep_evolution", "wsilver_legacy"):
        coordinator.entry.data.update({const.CONF_BED_TYPE: bed_type, const.CONF_PROTOCOL_VARIANT: variant or "A1"})
        variant = variant or "A1"
    if bed_type == const.BED_TYPE_SILVERMOTION:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "queen"
    if bed_type == const.BED_TYPE_SONICSLEEP:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "one"
    if bed_type == const.BED_TYPE_JALON:
        coordinator.entry.data.update({const.CONF_PRODUCT_TYPE: "0", const.CONF_BLE_DEVICE_NAME: "smartbed123"})
    if bed_type == const.BED_TYPE_ERGOMOTION_4:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "H"
    if bed_type == "scott_living":
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "A"
    if bed_type == "smart_sleep":
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "0"
    if bed_type == "onlysnore":
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "unKnow"

    if bed_type == "flexispot":
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "eb632"

    if bed_type == "mline":
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "two"
    if bed_type == "berun":
        variant = "v6"
        coordinator.entry.data[const.CONF_PROTOCOL_VARIANT] = variant
    if bed_type == "nerum":
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "nerum"

    if bed_type == "sealy_posturematic":
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "0"

    if bed_type == const.BED_TYPE_ENSO2:
        variant = variant or "E3RM"
        coordinator.entry.data[const.CONF_PROTOCOL_VARIANT] = variant

    if bed_type == "askona":
        variant = variant or "633"
        coordinator.entry.data[const.CONF_PROTOCOL_VARIANT] = variant

    if bed_type == "enso":
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "2"

    if bed_type == const.BED_TYPE_JALON_BED:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "40"
    if bed_type in const.KEESON_LAYOUT_APP_BED_TYPES:
        from custom_components.adjustable_bed.profiles.keeson import DEFAULT_LAYOUTS
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = DEFAULT_LAYOUTS[bed_type]
    if bed_type == const.BED_TYPE_SYMPHONY_SLEEP:
        coordinator.entry.data.update({const.CONF_PRODUCT_TYPE: "600E", const.CONF_PROTOCOL_VARIANT: "box1"})
    if bed_type in (const.BED_TYPE_ISLEEP, const.BED_TYPE_RIZE, const.BED_TYPE_KOMFYD, const.BED_TYPE_COMFYDS):
        coordinator.entry.data.update({const.CONF_BED_TYPE: bed_type, const.CONF_PRODUCT_TYPE: 129, const.CONF_KAIDI_ROOM_ID: 10000})
    if bed_type == const.BED_TYPE_SLEEPTRACKER:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "unknown"
    if bed_type == const.BED_TYPE_SLEEPYS_ELITE_APP:
        coordinator.entry.data[const.CONF_SLEEPYS_ELITE_SELECTOR] = "BOX24"

    if bed_type == const.BED_TYPE_STARCODE_M1X12:
        coordinator.entry.data.update(
            {
                const.CONF_STARCODE_M1X12_PROFILE: "cb25",
                const.CONF_BLE_DEVICE_NAME: "STAR252201123456",
            }
        )

    if bed_type == BED_TYPE_RICHMAT:
        coordinator.entry.data[const.CONF_RICHMAT_REMOTE] = "qrrm"
        return await create_controller(
            coordinator,
            bed_type,
            variant or RICHMAT_VARIANT_WILINKE,
            client,
            device_name="Casper QRRM Bed",
        )

    if bed_type == BED_TYPE_LEGGETT_LP_LEGACY:
        coordinator.entry = SimpleNamespace(
            data={
                CONF_LP_LEGACY_MODEL: LP_LEGACY_PROFILE_CODES[0],
                CONF_LP_LEGACY_MODE: "legacy",
                CONF_LP_LEGACY_WRITE_UUID: "11111111-2222-3333-4444-555555555555",
            }
        )

    if bed_type == const.BED_TYPE_JALON_BED:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "40"

    if bed_type == const.BED_TYPE_MOTOMOTION:
        # Include the source-declared side-state specs in translation reachability.
        coordinator.entry.data = {**coordinator.entry.data, const.CONF_BLE_DEVICE_NAME: "SOFA000001SC00M"}

    if bed_type == const.BED_TYPE_TRUEMOTION:
        coordinator.entry.data[const.CONF_BLE_DEVICE_NAME] = "SUTA-B202"

    if bed_type == const.BED_TYPE_MOTION_BED:
        # The app's identity is the exact advertised name.
        coordinator.entry.data = {**coordinator.entry.data, const.CONF_BLE_DEVICE_NAME: "QMS-IQ"}

    if bed_type == const.BED_TYPE_FSM_RELAX:
        coordinator.entry.options = {}
        coordinator.entry.entry_id = "contract-fsm-relax"
        return await create_controller(coordinator, bed_type, variant, client)
    if bed_type == const.BED_TYPE_MLILY_REMOTE:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "single"
        return await create_controller(coordinator, bed_type, variant or "ms200", client)
    if bed_type == const.BED_TYPE_MLILY:
        return await create_controller(coordinator, bed_type, variant or "6brm", client)
    if bed_type == "majestichome":
        return await create_controller(coordinator, bed_type, variant or "FARM", client)
    if bed_type == const.BED_TYPE_OKIMIKI:
        return await create_controller(coordinator, bed_type, variant or "HCRN", client)
    if bed_type == const.BED_TYPE_BOBPOWERBASE:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "standard"
        return await create_controller(coordinator, bed_type, variant or "elite", client)
    if bed_type == const.BED_TYPE_GALAXY:
        selected = variant or "6BRM"
        return await create_controller(coordinator, bed_type, selected, client)
    if bed_type == const.BED_TYPE_GOODVIBE:
        return await create_controller(coordinator, bed_type, variant or "selector-0001", client)
    if bed_type == const.BED_TYPE_ESHINE_OKIN:
        return await create_controller(coordinator, bed_type, variant or "eshine_e5000", client)
    if bed_type == const.BED_TYPE_RICHMAT_CLASSIC_APPS:
        variant = variant or "avocadoecobase"
        coordinator.entry.data.update({const.CONF_PRODUCT_TYPE: "6BRM", const.CONF_PROTOCOL_VARIANT: variant})
        return await create_controller(coordinator, bed_type, variant, client)

    if bed_type == "richmat_sleep_receiver":
        return await create_controller(coordinator, bed_type, variant or "wsilver2", client)
    if bed_type == const.BED_TYPE_RICHMAT_APP_SLEEP:
        return await create_controller(coordinator, bed_type, variant or "hj", client)
    if bed_type == const.BED_TYPE_MYSIDE:
        return await create_controller(coordinator, bed_type, variant or "76", client)
    if bed_type == const.BED_TYPE_RICHMAT_APP:
        return await create_controller(coordinator, bed_type, variant or "6BRM", client)
    if bed_type == const.BED_TYPE_HJBED:
        return await create_controller(coordinator, bed_type, variant or "hj_bedbjrn", client)
    if bed_type == const.BED_TYPE_DOUBLESLEEP:
        coordinator.entry.options = {}
        coordinator.entry.data = {**coordinator.entry.data, const.CONF_PRODUCT_TYPE: "3"}
        return await create_controller(coordinator, bed_type, variant or "p1", client)
    if bed_type == const.BED_TYPE_LUUNA:
        return await create_controller(coordinator, bed_type, variant or "rise", client)
    if bed_type == const.BED_TYPE_HUSH_BASE:
        return await create_controller(coordinator, bed_type, variant or "hushl400", client)
    if bed_type == const.BED_TYPE_SLEEPTIME:
        variant = variant or "205"
    variant = variant or _protocol_variant_for_bed_type(bed_type)
    return await create_controller(coordinator, bed_type, variant, client)


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


async def test_diagnostic_bed_type_builds_through_the_registry() -> None:
    """The wire snapshot builds every supported bed type; this one is not among them."""
    coordinator = _FactoryCoordinator()
    controller = await _create_from_registry(coordinator, const.BED_TYPE_DIAGNOSTIC)

    assert isinstance(controller, BedController)
    # The lazy module import must go through the import executor, not the loop.
    executor = coordinator.hass.async_add_import_executor_job
    assert [call[0] for call in executor.calls] == [import_module]


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
    assert getattr(getattr(controller, "profile", None), "key", None) == "betterliving"


async def test_factory_auto_detects_keeson_json_variant_for_a00a_service() -> None:
    """Keeson auto mode should select the JSON/A00A protocol family on A00A UUID."""
    coordinator = _FactoryCoordinator()
    client = SimpleNamespace(
        is_connected=True,
        services=[SimpleNamespace(uuid=KEESON_JSON_SERVICE_UUID)],
        address="AA:BB:CC:DD:EE:FF",
    )

    controller = await create_controller(
        coordinator=coordinator,
        bed_type=BED_TYPE_KEESON,
        protocol_variant=VARIANT_AUTO,
        client=client,
        device_name="Juna Sleep Bed",
    )

    assert isinstance(controller, BedController)
    assert getattr(controller, "_variant", None) == KEESON_VARIANT_JSON


async def test_factory_keeps_keeson_json_variant_when_fallback_uuids_are_also_present() -> None:
    """A00A should take precedence over overlapping fallback UUID heuristics."""
    coordinator = _FactoryCoordinator()
    client = SimpleNamespace(
        is_connected=True,
        services=[
            SimpleNamespace(uuid=KEESON_JSON_SERVICE_UUID),
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
        ble_manufacturer="BLE-4.0 Module",
    )

    assert isinstance(controller, BedController)
    assert getattr(controller, "_variant", None) == KEESON_VARIANT_JSON
    assert getattr(getattr(controller, "profile", None), "key", None) != "betterliving"
    assert getattr(getattr(controller, "profile", None), "key", None) != "cb1322"


async def test_factory_auto_detects_keeson_sino_for_okin_ble_name_single_uuid() -> None:
    """OKIN-BLE name + single fallback UUID should select Sino with betterliving presets."""
    coordinator = _FactoryCoordinator()
    client = SimpleNamespace(
        is_connected=True,
        services=[
            SimpleNamespace(uuid="0000fff0-0000-1000-8000-00805f9b34fb"),
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
    assert getattr(getattr(controller, "profile", None), "key", None) == "betterliving"


async def test_factory_auto_detects_cb1322_variant() -> None:
    """OKIN-BLE name + fallback UUIDs + CB1322 manufacturer should select OKIN with cb1322."""
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
        ble_manufacturer="BLE-4.0 Module",
    )

    assert isinstance(controller, BedController)
    assert getattr(controller, "_variant", None) == KEESON_VARIANT_OKIN
    assert getattr(getattr(controller, "profile", None), "key", None) == "cb1322"


async def test_factory_auto_detects_cb1322_dewertokin_manufacturer() -> None:
    """DewertOKIN manufacturer string should also trigger CB1322 detection."""
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
        ble_manufacturer="DewertOKIN",
    )

    assert isinstance(controller, BedController)
    assert getattr(controller, "_variant", None) == KEESON_VARIANT_OKIN
    assert getattr(getattr(controller, "profile", None), "key", None) == "cb1322"


async def test_factory_enables_coolbase_dewert_okin_profile() -> None:
    """OKIN-BLE/DewertOKIN devices using Cool Base expose Memory 2, not fan sync."""
    coordinator = _FactoryCoordinator()

    controller = await create_controller(
        coordinator=coordinator,
        bed_type=BED_TYPE_COOLBASE,
        protocol_variant=VARIANT_AUTO,
        client=None,
        device_name="OKIN-BLE00016084",
        ble_manufacturer="DewertOKIN",
    )

    assert isinstance(controller, BedController)
    assert getattr(controller, "_dewert_okin_profile", None) is True
    assert controller.memory_slot_count == 2
    assert controller.supports_fan_control is False


async def test_factory_enables_coolbase_dewert_okin_profile_for_btcb_name() -> None:
    """BTCB-named Cool Base entries should select the DewertOKIN profile by name."""
    coordinator = _FactoryCoordinator()

    controller = await create_controller(
        coordinator=coordinator,
        bed_type=BED_TYPE_COOLBASE,
        protocol_variant=VARIANT_AUTO,
        client=None,
        device_name="BTCB.03",
        ble_manufacturer=None,
    )

    assert isinstance(controller, BedController)
    assert getattr(controller, "_dewert_okin_profile", None) is True
    assert controller.memory_slot_count == 2


async def test_betterliving_preset_commands() -> None:
    """BetterLiving presets use the BED_DEFAULT words on the big-endian E5 frame."""
    from custom_components.adjustable_bed.beds.keeson.controller import KeesonController
    from custom_components.adjustable_bed.profiles.keeson import BETTERLIVING

    controller = KeesonController(_FactoryCoordinator(), variant="sino", betterliving_presets=True)

    assert controller.profile is BETTERLIVING
    assert controller._build_command(BETTERLIVING.presets["flat"]).hex() == "e5fe160100000203"
    assert controller.memory_slot_count == 2
    assert controller.supports_memory_programming is True


async def test_cb1322_preset_commands() -> None:
    """CB1322 memory words use the little-endian OKIN (E6) frame."""
    from custom_components.adjustable_bed.beds.keeson.controller import KeesonController
    from custom_components.adjustable_bed.profiles.keeson import CB1322

    controller = KeesonController(_FactoryCoordinator(), variant="okin", cb1322_presets=True)

    assert controller.profile is CB1322
    assert controller._build_command(CB1322.memory[1]).hex() == "e6fe160000010004"
    assert controller.memory_slot_count == 2
    assert controller.supports_memory_programming is True


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


@pytest.mark.parametrize("helper", ["_move_with_stop", "_preset_with_stop"])
@pytest.mark.parametrize("outcome", ["success", "cancel", "failure"])
async def test_base_cleanup_failure_is_reported(helper: str, outcome: str) -> None:
    """A failed release is observable even when the movement completed or was cancelled."""
    controller = _ContractController(_FactoryCoordinator())
    primary_error = {
        "success": None,
        "cancel": asyncio.CancelledError(),
        "failure": RuntimeError("movement failed"),
    }[outcome]
    controller.write_command = AsyncMock(side_effect=primary_error)
    controller._send_stop = AsyncMock(side_effect=BleakError("release failed"))
    with pytest.raises(BleakError, match="release failed") as caught:
        await getattr(controller, helper)(b"\x01")
    assert caught.value.__context__ is primary_error
    controller._send_stop.assert_awaited_once()


async def test_base_wall_clock_pacing_absorbs_write_latency() -> None:
    """A paced stream subtracts BLE write time from the repeat interval."""
    events: list[str] = []

    class ObservedLock:
        async def __aenter__(self) -> None:
            events.append("lock")

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    def read_time() -> float:
        events.append("time")
        return next(time_values)

    coordinator = _FactoryCoordinator()
    client = SimpleNamespace(
        is_connected=True,
        services=(),
        write_gatt_char=AsyncMock(side_effect=lambda *args, **kwargs: events.append("write")),
    )
    coordinator.client = client
    coordinator.record_command_trace = MagicMock()
    controller = _ContractController(coordinator)
    controller._ble_lock = ObservedLock()
    time_values = iter([10.0, 10.03, 10.1])
    loop = SimpleNamespace(
        time=MagicMock(side_effect=read_time),
    )
    sleep = AsyncMock()

    with (
        patch(
            "custom_components.adjustable_bed.beds.base.asyncio.get_running_loop",
            return_value=loop,
        ),
        patch(
            "custom_components.adjustable_bed.beds.base.asyncio.sleep",
            sleep,
        ),
    ):
        await controller._write_gatt_with_retry(
            controller.control_characteristic_uuid,
            b"\x01",
            repeat_count=2,
            repeat_delay_ms=100,
            response=False,
            wall_clock_pacing=True,
        )

    assert client.write_gatt_char.await_count == 2
    assert events[:3] == ["lock", "time", "write"]
    sleep.assert_awaited_once()
    assert sleep.await_args.args[0] == pytest.approx(0.07)


async def test_base_write_cancelled_while_waiting_for_ble_lock_is_not_sent() -> None:
    """A queued write must recheck cancellation after a concurrent read releases GATT."""
    coordinator = _FactoryCoordinator()
    client = SimpleNamespace(is_connected=True, services=(), write_gatt_char=AsyncMock())
    coordinator.client = client
    coordinator.record_command_trace = MagicMock()
    controller = _ContractController(coordinator)
    cancelled = asyncio.Event()
    acknowledged = MagicMock()
    async with controller._ble_lock:
        write = asyncio.create_task(controller._write_gatt_with_retry(
            controller.control_characteristic_uuid, b"\x01",
            cancel_event=cancelled, on_write=acknowledged,
        ))
        await asyncio.sleep(0)
        cancelled.set()
    await write
    client.write_gatt_char.assert_not_awaited()
    acknowledged.assert_not_called()

    # An explicit fresh cleanup event must still allow the release write.
    await controller._write_gatt_with_retry(
        controller.control_characteristic_uuid, b"\x00", cancel_event=asyncio.Event(),
        on_write=acknowledged,
    )
    client.write_gatt_char.assert_awaited_once()
    acknowledged.assert_called_once()


