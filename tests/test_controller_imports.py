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
            assert JensenController.__module__ == prefix + "jensen"
            assert prefix + "reverie" not in sys.modules
        ''')],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_factory_first_use_imports_run_off_event_loop():
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent('''
            import asyncio
            import importlib.abc
            import sys
            import threading
            from tests.test_controller_contract import (
                _create_controller_for_bed_type, _RecordingImportExecutor,
            )
            from custom_components.adjustable_bed.const import SUPPORTED_BED_TYPES

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

            async def main():
                for bed_type in SUPPORTED_BED_TYPES:
                    await _create_controller_for_bed_type(bed_type)

            asyncio.run(main())
        ''')],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
