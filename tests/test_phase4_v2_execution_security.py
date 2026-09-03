from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import zipfile
from pathlib import Path

import pytest

import tools.phase4_v2.preflight.core as preflight_core
import tools.phase4_v2.preflight.execution as execution
from tests.phase4_v2_static_tool import build_static_tool
from tools.phase4_v2.preflight.execution import (
    ExecutionLimits,
    PreparationCacheError,
    PreparationError,
    ToolSpec,
    build_execution_profile,
    execute_preparation,
)


def _preflight(monkeypatch: pytest.MonkeyPatch, root: Path):
    artifact = root / "base.apk"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", b"dex")

    def identity(arguments: tuple[str, ...], **_kwargs: object) -> tuple[str, None]:
        if arguments[0] == "aapt2":
            return "package: name='org.example.secure' versionCode='1' versionName='1.0'\n", None
        return f"Signer #1 certificate SHA-256 digest: {'a' * 64}\n", None

    monkeypatch.setattr(preflight_core, "_run_identity_tool", identity)
    seal = root / "seal"
    seal.mkdir()
    return preflight_core.preflight_delivery([artifact], sealing_directory=seal)


def _tool(root: Path, body: str) -> Path:
    if "with_name('helper.txt')" in body:
        return build_static_tool(
            root,
            outputs={},
            extra_source=(
                'char payload[256] = {0}; int fd=open("/helper.txt",O_RDONLY); '
                "int n=read(fd,payload,255); close(fd); if(n<0)return 93; payload[n]=0; "
                'write_member(output, strcmp(route,"apktool")==0 ? "App.smali" : "App.java", payload);'
            ),
        )
    if "socket.create_connection" in body:
        return build_static_tool(
            root,
            outputs={},
            extra_source=(
                'int fd=open("/etc/hostname",O_RDONLY); '
                'write_member(output, strcmp(route,"apktool")==0 ? "App.smali" : "App.java", '
                'fd < 0 ? "read,network,process,write" : "HOST_READ_ESCAPE"); if(fd>=0)close(fd);'
            ),
        )
    return build_static_tool(
        root,
        outputs={
            "apktool": {"App.smali": "android.bluetooth.BluetoothGatt"},
            "jadx": {"App.java": "android.bluetooth.BluetoothGatt"},
        },
    )


def _specs(tool: Path) -> dict[str, ToolSpec]:
    return {
        route: ToolSpec(
            str(tool),
            ("--version",),
            (route, "{input}", "{output}"),
            (),
            str(tool.parent),
        )
        for route in ("apktool", "jadx")
    }


def _execute(
    preflight: object,
    tool: Path,
    root: Path,
    name: str,
    *,
    cache: Path | None = None,
):
    return execute_preparation(
        preflight,  # type: ignore[arg-type]
        tool_specs=_specs(tool),
        cache_directory=cache or root / f"cache-{name}",
        output_directory=root / f"result-{name}",
        pipeline_revision="pipeline-security-v1",
    )


_OUTPUT_BODY = (
    "suffix = 'smali' if route == 'apktool' else 'java'\n"
    "target = pathlib.Path(output_name, f'App.{suffix}')\n"
    "target.write_text('android.bluetooth.BluetoothGatt', encoding='utf-8')"
)


def test_profile_is_canonical_bounded_and_manifest_bound(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path, _OUTPUT_BODY)
    profile = build_execution_profile(ExecutionLimits(tool_timeout_seconds=1.25))

    result = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=tmp_path / "cache",
        output_directory=tmp_path / "result",
        pipeline_revision="pipeline-security-v1",
        execution_profile=profile,
    )

    manifest = json.loads((tmp_path / "result" / "manifest.json").read_bytes())
    assert result.execution_profile_sha256 == profile.sha256
    assert manifest["execution_profile"] == {
        "revision": profile.revision,
        "sha256": profile.sha256,
    }
    assert profile.to_data()["limits"]["tool_timeout_seconds"] == 1_250  # type: ignore[index]
    assert all(item.tool.runtime_sha256 for item in result.invocations)

    for hostile in (
        ExecutionLimits(tool_timeout_seconds=float("nan")),
        ExecutionLimits(tool_timeout_seconds=0.0001),
        ExecutionLimits(max_processes=True),
        ExecutionLimits(max_open_files=ExecutionLimits().max_open_files + 1),
    ):
        with pytest.raises(PreparationError, match="execution"):
            hostile.validate()

    with pytest.raises(PreparationError, match="Unicode"):
        ToolSpec(
            "tool",
            ("--version",),
            ("{input}", "\ud800", "{output}"),
            (),
            "/opt/phase4-runtime",
        ).validate()
    with pytest.raises(PreparationError, match="non-host-root"):
        ToolSpec("tool", ("--version",), ("{input}", "{output}"), (), "/").validate()


def test_missing_sandbox_support_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(execution.shutil, "which", lambda _name: None)
    with pytest.raises(PreparationError, match="bubblewrap is required"):
        build_execution_profile()


def test_self_consistent_caller_preseed_is_never_trusted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path, _OUTPUT_BODY)
    trusted_cache = tmp_path / "trusted-cache"
    _execute(preflight, tool, tmp_path, "first", cache=trusted_cache)
    object_root = trusted_cache / "objects" / execution.EXECUTION_CACHE_SCHEMA
    original = next(object_root.iterdir())
    hostile_cache = tmp_path / "hostile-cache"
    hostile_objects = hostile_cache / "objects" / execution.EXECUTION_CACHE_SCHEMA
    hostile_objects.mkdir(parents=True)
    shutil.copytree(original, hostile_objects / original.name)

    with pytest.raises(PreparationCacheError, match="untrusted cache object"):
        _execute(preflight, tool, tmp_path, "second", cache=hostile_cache)
    assert not (tmp_path / "result-second").exists()


def test_execution_uses_sealed_launcher_and_adjacent_helper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _preflight(monkeypatch, tmp_path)
    tool = _tool(
        tmp_path,
        "value = pathlib.Path(pathlib.Path(__file__).with_name('helper.txt')).read_text()\n"
        "suffix = 'smali' if route == 'apktool' else 'java'\n"
        "pathlib.Path(output_name, f'App.{suffix}').write_text(value)",
    )
    helper = tool.parent / "helper.txt"
    helper.write_text("android.bluetooth.BluetoothGatt", encoding="utf-8")
    original_runner = execution._run_sandboxed
    calls = 0

    def swap_before_execution(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        if calls == 3:
            helper.write_text("MALICIOUS", encoding="utf-8")
            tool.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            tool.chmod(0o700)
        return original_runner(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(execution, "_run_sandboxed", swap_before_execution)
    result = _execute(preflight, tool, tmp_path, "sealed")

    assert result.status == "COMPLETE"
    expected = hashlib.sha256(b"android.bluetooth.BluetoothGatt").hexdigest()
    assert {output.sha256 for item in result.invocations for output in item.outputs} == {expected}


def test_sandbox_denies_host_write_network_and_host_process_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _preflight(monkeypatch, tmp_path)
    outside = tmp_path / "outside"
    host_pid = os.getpid()
    body = (
        "denied = []\n"
        f"\ntry:\n    pathlib.Path({str(outside)!r}).write_text('escaped')\n"
        "except OSError:\n    denied.append('write')\n"
        "try:\n    socket.create_connection(('127.0.0.1', 9), timeout=0.1)\n"
        "except OSError:\n    denied.append('network')\n"
        f"try:\n    os.kill({host_pid}, 0)\n"
        "except OSError:\n    denied.append('process')\n"
        "suffix = 'smali' if route == 'apktool' else 'java'\n"
        "pathlib.Path(output_name, f'App.{suffix}').write_text(','.join(sorted(denied)))"
    )
    tool = _tool(tmp_path, body)

    result = _execute(preflight, tool, tmp_path, "sandbox")

    assert result.status == "COMPLETE"
    assert not outside.exists()
    cache_root = tmp_path / "cache-sandbox" / "objects" / execution.EXECUTION_CACHE_SCHEMA
    payloads = [path.read_text() for path in cache_root.glob("*/outputs/*")]
    assert payloads == ["read,network,process,write", "read,network,process,write"]


def test_workspace_and_cache_symlink_swaps_fail_closed(tmp_path: Path) -> None:
    real_cache = tmp_path / "real-cache"
    real_cache.mkdir()
    cache_link = tmp_path / "cache-link"
    cache_link.symlink_to(real_cache, target_is_directory=True)
    with pytest.raises(PreparationError, match="symlink ancestor"):
        execution.PreparationCache(cache_link)

    tool = _tool(tmp_path, _OUTPUT_BODY)
    profile = build_execution_profile()
    runtime_link = tmp_path / "runtime-link"
    runtime_link.symlink_to(tool.parent, target_is_directory=True)
    with pytest.raises(PreparationError, match="runtime root contains a symlink ancestor"):
        execution._seal_executable(tool, str(runtime_link), profile.limits)
    runtime_link.unlink()

    sealed = execution._seal_executable(tool, str(tool.parent), profile.limits)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in ("home", "tmp", "output"):
        (workspace / name).mkdir()
    try:
        with pytest.raises(PreparationError, match="workspace identity changed"):
            execution._run_sandboxed(
                sealed,
                ("apktool", "input.apk", "output"),
                workspace=workspace,
                profile=profile,
                timeout=1,
                stream_limit=1_024,
                workspace_identity=(0, 0),
            )
    finally:
        sealed.close()


def test_live_aggregate_quota_stops_writer_before_tool_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _preflight(monkeypatch, tmp_path)
    tool = build_static_tool(
        tmp_path,
        outputs={},
        extra_source=(
            "char bytes[800]; memset(bytes, 1, sizeof(bytes)); char path[128]; "
            'for(int i=0;i<2;i++){snprintf(path,sizeof(path),"%s/chunk-%d",output,i); '
            "int fd=open(path,O_WRONLY|O_CREAT|O_TRUNC,0600); write(fd,bytes,sizeof(bytes)); close(fd);} "
            "sleep(2);"
        ),
    )
    limits = ExecutionLimits(
        tool_timeout_seconds=3,
        max_output_file_bytes=1_024,
        max_output_bytes=1_024,
    )
    started = time.monotonic()
    result = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=tmp_path / "quota-cache",
        output_directory=tmp_path / "quota-result",
        pipeline_revision="pipeline-security-v1",
        execution_profile=build_execution_profile(limits),
    )

    assert time.monotonic() - started < 1.5
    assert result.status == "BLOCKED"
    assert all("OUTPUT_AGGREGATE_BYTE_LIMIT" in item.failures for item in result.invocations), [
        item.failures for item in result.invocations
    ]
