"""Contract tests for controller capabilities and factory completeness."""

from __future__ import annotations

import asyncio
import inspect
from importlib import import_module
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.bed_traits import bed_traits
from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.entity_specs import (
    POSITION_UNIT_DEGREES,
    POSITION_UNIT_PERCENT,
)
from custom_components.adjustable_bed.beds.leggett.lp_legacy_profiles import LP_LEGACY_PROFILE_CODES
from custom_components.adjustable_bed.const import (
    BED_TYPE_COOLBASE,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_LP_LEGACY,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_OCTO,
    BED_TYPE_RICHMAT,
    BED_TYPE_SBI,
    CONF_LP_LEGACY_MODE,
    CONF_LP_LEGACY_MODEL,
    CONF_LP_LEGACY_WRITE_UUID,
    KEESON_JSON_SERVICE_UUID,
    KEESON_VARIANT_JSON,
    KEESON_VARIANT_OKIN,
    KEESON_VARIANT_SINO,
    LEGGETT_VARIANT_OKIN,
    MALOUF_LAYOUT_AUTO,
    MALOUF_MEMORY_SLOTS_AUTO,
    OCTO_VARIANT_STANDARD,
    RICHMAT_VARIANT_NORDIC,
    RICHMAT_VARIANT_WILINKE,
    SBI_VARIANT_BOTH,
    SUPPORTED_BED_TYPES,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.controller_factory import (
    _BUILDERS,
    _SIMPLE_CONTROLLERS,
    _create_from_registry,
    create_controller,
)
from custom_components.adjustable_bed.controller_state import StateKey, StateUpdate
from custom_components.adjustable_bed.validators import get_variants_for_bed_type

SHARED_CAPABILITY_FLAGS: tuple[str, ...] = (
    "supports_memory_presets",
    "supports_memory_programming",
    "supports_lights",
    "supports_light",
    "supports_under_bed_lights",
    "supports_discrete_light_control",
    "supports_light_color_control",
    "supports_light_cycle",
    "supports_position_feedback",
    "reports_percentage_position",
    "supports_massage",
    "supports_motor_control",
    "supports_stop_all",
    "supports_fan_control",
    "supports_control_mode_configuration",
)


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
    if bed_type == const.BED_TYPE_ADJUSTABLE_BED:
        return "adjustable_bed_okin"
    if bed_type == BED_TYPE_RICHMAT:
        return RICHMAT_VARIANT_NORDIC
    if bed_type == BED_TYPE_LEGGETT_PLATT:
        return LEGGETT_VARIANT_OKIN
    if bed_type == BED_TYPE_SBI:
        return SBI_VARIANT_BOTH
    if bed_type == BED_TYPE_OCTO:
        return OCTO_VARIANT_STANDARD
    if bed_type == const.BED_TYPE_CASPER_BASE:
        return "casperpro"
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
    if bed_type == const.BED_TYPE_JALON:
        coordinator.entry.data.update({const.CONF_PRODUCT_TYPE: "0", const.CONF_BLE_DEVICE_NAME: "smartbed123"})
    if bed_type == const.BED_TYPE_ERGOMOTION_4:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "H"
    if bed_type == const.BED_TYPE_JALON_BED:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "40"
    if bed_type in const.KEESON_LAYOUT_APP_BED_TYPES:
        from custom_components.adjustable_bed.profiles.keeson import DEFAULT_LAYOUTS
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = DEFAULT_LAYOUTS[bed_type]
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

    if bed_type == const.BED_TYPE_MOTION_BED:
        # The app's identity is the exact advertised name.
        coordinator.entry.data = {**coordinator.entry.data, const.CONF_BLE_DEVICE_NAME: "QMS-IQ"}

    if bed_type == const.BED_TYPE_FSM_RELAX:
        coordinator.entry.options = {}
        coordinator.entry.entry_id = "contract-fsm-relax"
        return await create_controller(coordinator, bed_type, variant, client)
    if bed_type == const.BED_TYPE_MLILY:
        return await create_controller(coordinator, bed_type, variant or "6brm", client)
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
    variant = variant or _protocol_variant_for_bed_type(bed_type)
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


# Overrides that narrow position feedback once discovery or the advertised model
# shows which axes report. They may only withhold what the record declares.
_RUNTIME_NARROWED_FEEDBACK = frozenset(
    {"LinakController", "ParamountController", "ReveriePairlinkController", "SleepNumberMcrController"}
)
# Automatic routes the factory can only resolve from a live advertisement.
_LIVE_ONLY_ROUTES = frozenset({(const.BED_TYPE_DOUBLESLEEP, VARIANT_AUTO)})


def _contract_routes(bed_type: str) -> list[str | None]:
    """Return every variant of a bed type, or None for its single route."""
    variants = get_variants_for_bed_type(bed_type)
    if not variants:
        return [None]
    return [v for v in variants if (bed_type, v) not in _LIVE_ONLY_ROUTES]


@pytest.mark.parametrize("bed_type", SUPPORTED_BED_TYPES)
async def test_controller_traits_match_bed_type_record(bed_type: str) -> None:
    """Every route's controller starts from its bed type's static traits.

    The record decides setup defaults and entities before any controller
    exists, so a controller must not contradict it once built.
    """
    for variant in _contract_routes(bed_type):
        controller = await _create_controller_for_bed_type(bed_type, variant)
        traits = bed_traits(bed_type, variant or _protocol_variant_for_bed_type(bed_type))
        route = f"{bed_type} ({variant}): {type(controller).__name__}"

        assert controller.reports_percentage_position is traits.percentage_positions, route
        assert controller.requires_persistent_connection is traits.persistent_connection, route
        if type(controller).__name__ in _RUNTIME_NARROWED_FEEDBACK:
            assert traits.position_feedback or not controller.supports_position_feedback, route
        else:
            assert controller.supports_position_feedback is traits.position_feedback, route
        if traits.position_feedback:
            assert _is_overridden(controller, "start_notify") or _is_overridden(
                controller, "read_positions"
            ), f"{route} declares position feedback but never reads positions"
        assert not (traits.position_feedback and traits.no_angle_feedback), route


@pytest.mark.parametrize("bed_type", SUPPORTED_BED_TYPES)
async def test_position_slider_units_match_reported_position_units(bed_type: str) -> None:
    """Position sliders must use the controller's declared feedback unit."""
    controller = await _create_controller_for_bed_type(bed_type)
    if not controller.supports_position_feedback:
        return

    expected_unit = (
        POSITION_UNIT_PERCENT if controller.reports_percentage_position else POSITION_UNIT_DEGREES
    )
    specs = controller.position_number_specs

    assert specs, f"{bed_type} reports positions but exposes no position sliders"
    assert {spec.native_unit_of_measurement for spec in specs} == {expected_unit}


@pytest.mark.parametrize("bed_type", sorted(_SIMPLE_CONTROLLERS))
async def test_registry_entries_resolve_to_controller_classes(bed_type: str) -> None:
    """Every _SIMPLE_CONTROLLERS entry must name a real module and class.

    The registry addresses controller classes by string, so this is what turns a
    typo into a failing test instead of a ValueError on a user's bed. Covers
    entries like BED_TYPE_DIAGNOSTIC that are absent from SUPPORTED_BED_TYPES.
    """
    coordinator = _FactoryCoordinator()
    if bed_type in (const.BED_TYPE_ISLEEP, const.BED_TYPE_RIZE, const.BED_TYPE_KOMFYD, const.BED_TYPE_COMFYDS):
        coordinator.entry.data.update({const.CONF_BED_TYPE: bed_type, const.CONF_PRODUCT_TYPE: 129, const.CONF_KAIDI_ROOM_ID: 10000})
    if bed_type == const.BED_TYPE_ERGOMOTION_4:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "H"
    if bed_type == const.BED_TYPE_JALON_BED:
        coordinator.entry.data[const.CONF_PRODUCT_TYPE] = "40"
    controller = await _create_from_registry(coordinator, bed_type)

    assert isinstance(controller, BedController)
    # The lazy module import must go through the import executor, not the loop.
    executor = coordinator.hass.async_add_import_executor_job
    assert [call[0] for call in executor.calls] == [import_module]


@pytest.mark.parametrize("bed_type", sorted(_BUILDERS))
async def test_builder_entries_resolve_to_builders(bed_type: str) -> None:
    """Every _BUILDERS entry must name a real module and async builder function."""
    spec = _BUILDERS[bed_type]
    builder = getattr(import_module(f"custom_components.adjustable_bed.beds.{spec.module}"), spec.function)

    assert inspect.iscoroutinefunction(builder)
    assert list(inspect.signature(builder).parameters) == ["ctx"]


def test_class_and_builder_registries_are_disjoint() -> None:
    """A bed type has exactly one way to be built; the builder would shadow the class."""
    assert not set(_SIMPLE_CONTROLLERS) & set(_BUILDERS)


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

    if controller.supports_light_color_control:
        assert _is_overridden(controller, "set_light_color") or _is_overridden(
            controller, "set_light_color_rgbw"
        )

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

    if controller.supports_massage_wave_direction_control:
        assert _is_overridden(controller, "massage_wave_next")
        assert _is_overridden(controller, "massage_wave_previous")

    if controller.supports_massage_intensity_preset_control:
        assert _is_overridden(controller, "set_massage_intensity_preset")

    if controller.supports_fan_control:
        for method_name in ("fan_left_cycle", "fan_right_cycle", "fan_sync_cycle"):
            assert _is_overridden(controller, method_name)
        assert controller.fan_level_max > 0

    if controller.supports_control_mode_configuration:
        assert _is_overridden(controller, "set_control_mode_press_and_hold")
        assert _is_overridden(controller, "set_control_mode_press_and_release")


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


async def test_overridden_stop_helpers_keep_finally_cleanup() -> None:
    """Controllers overriding stop helpers should preserve finally-based cleanup."""
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
            assert "finally" in source, (
                f"{controller_cls.__name__}._preset_with_stop missing finally"
            )
