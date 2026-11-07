"""Fresh-interpreter checks for selective, executor-owned controller imports."""

import subprocess
import sys
import textwrap


def test_base_and_factory_do_not_import_concrete_controllers():
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent('''
            import sys
            from custom_components.adjustable_bed import controller_factory
            from custom_components.adjustable_bed.beds.base import BedController
            prefix = "custom_components.adjustable_bed.beds."
            concrete = [name for name, module in list(sys.modules.items())
                        if name.startswith(prefix) and name != prefix + "base"
                        and any(isinstance(value, type) and issubclass(value, BedController)
                                and value is not BedController for value in vars(module).values())]
            assert not concrete, concrete
            # Legacy exports still resolve the selected class on demand.
            from custom_components.adjustable_bed.beds import JensenController
            assert JensenController.__module__ == prefix + "jensen.controller"
            assert prefix + "reverie.controller" not in sys.modules
        ''')],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


# Fails any bed-module import on the main (event loop) thread; the recording
# import executor runs its jobs on a worker thread.
_LOOP_IMPORT_GUARD = textwrap.dedent('''
    import asyncio
    import importlib.abc
    import sys
    import threading
    from tests.test_controller_contract import _RecordingImportExecutor

    def install_loop_import_guard():
        main_thread = threading.get_ident()
        class ImportGuard(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.startswith("custom_components.adjustable_bed.beds."):
                    assert threading.get_ident() != main_thread, fullname
                return None

        async def executor(self, func, *args):
            self.calls.append((func, *args))
            return await asyncio.to_thread(func, *args)

        _RecordingImportExecutor.__call__ = executor
        sys.meta_path.insert(0, ImportGuard())
''')


def test_factory_first_use_imports_run_off_event_loop():
    result = subprocess.run(
        [sys.executable, "-c", _LOOP_IMPORT_GUARD + textwrap.dedent('''
            from tests.test_controller_contract import _create_controller_for_bed_type
            from types import SimpleNamespace
            from custom_components.adjustable_bed.const import (
                BED_TYPE_RICHMAT, CONF_BED_TYPE, CONF_RICHMAT_REMOTE, SUPPORTED_BED_TYPES,
            )
            from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
            from custom_components.adjustable_bed.profile_id import with_profile_ids

            features = "custom_components.adjustable_bed.beds.richmat.features"
            assert features not in sys.modules

            install_loop_import_guard()

            async def main():
                # Entry setup resolves the Richmat motor count from the feature table.
                recorder = _RecordingImportExecutor()
                hass = SimpleNamespace(
                    data={}, async_add_import_executor_job=recorder,
                    config=SimpleNamespace(path=lambda *parts: "/".join(parts), config_dir="/"),
                )
                entry = SimpleNamespace(entry_id="richmat", title="Richmat", options={}, data=with_profile_ids({
                    "address": "AA:BB:CC:DD:EE:FF",
                    CONF_BED_TYPE: BED_TYPE_RICHMAT,
                    CONF_RICHMAT_REMOTE: "a0rm",
                }))
                await AdjustableBedCoordinator.async_create(hass, entry)
                assert features in sys.modules

                for bed_type in SUPPORTED_BED_TYPES:
                    await _create_controller_for_bed_type(bed_type)

            asyncio.run(main())
        ''')],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_new_richmat_bed_settings_import_feature_table_off_event_loop():
    result = subprocess.run(
        [sys.executable, "-c", _LOOP_IMPORT_GUARD + textwrap.dedent('''
            from types import SimpleNamespace
            from unittest.mock import AsyncMock, patch
            from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
            from custom_components.adjustable_bed import config_flow
            from custom_components.adjustable_bed.const import BED_TYPE_RICHMAT, CONF_BED_TYPE
            from custom_components.adjustable_bed.detection import detect_bed_type_detailed

            features = "custom_components.adjustable_bed.beds.richmat.features"
            # The name shows the remote, whose features set the default motor count.
            info = BluetoothServiceInfoBleak(
                name="QRRM157052", address="AA:BB:CC:DD:EE:FF", rssi=-60,
                manufacturer_data={}, service_data={}, service_uuids=[], source="local",
                device=None, advertisement=None, connectable=True, time=0, tx_power=None,
            )
            # Detection's own lazy imports are not under test here.
            detect_bed_type_detailed(info)
            assert features not in sys.modules
            install_loop_import_guard()

            async def main():
                flow = config_flow.AdjustableBedConfigFlow()
                flow.hass = SimpleNamespace(async_add_import_executor_job=_RecordingImportExecutor())
                flow._discovery_info = info
                flow._manual_data = {"address": info.address, CONF_BED_TYPE: BED_TYPE_RICHMAT}
                with (
                    patch.object(config_flow, "get_available_adapters", return_value={}),
                    patch.object(flow, "_new_bed_settings_notes", AsyncMock(return_value={})),
                ):
                    result = await flow.async_step_finish_settings()
                assert result["step_id"] == "finish_settings"
                assert features in sys.modules

            asyncio.run(main())
        ''')],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
