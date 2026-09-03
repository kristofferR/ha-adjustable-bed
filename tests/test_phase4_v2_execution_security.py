from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
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
    sandbox = profile.to_data()["sandbox"]
    assert isinstance(sandbox, dict)
    assert sandbox["seccomp"] == {
        "revision": execution.SECCOMP_POLICY_REVISION,
        "sha256": execution.SECCOMP_POLICY_SHA256,
    }
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


def test_seccomp_policy_fails_closed_on_unsupported_architecture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = build_execution_profile()
    current = os.uname()
    monkeypatch.setattr(
        execution.os,
        "uname",
        lambda: os.uname_result((*current[:4], "aarch64")),
    )
    with pytest.raises(PreparationError, match="does not support this architecture"):
        execution._open_seccomp_policy(profile)


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
    quota = execution._create_quota_filesystem(profile.limits)
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
                quota_output_descriptor=quota.descriptor,
                quota_setup_userns_descriptor=quota.setup_userns_descriptor,
                quota_mountns_descriptor=quota.mountns_descriptor,
            )
    finally:
        quota.close()
        sealed.close()


def test_kernel_aggregate_quota_stops_writer_before_tool_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _preflight(monkeypatch, tmp_path)
    tool = build_static_tool(
        tmp_path,
        outputs={},
        extra_source=(
            "char bytes[6000]; memset(bytes, 1, sizeof(bytes)); char path[128]; "
            'for(int i=0;i<2;i++){snprintf(path,sizeof(path),"%s/chunk-%d",output,i); '
            "int fd=open(path,O_WRONLY|O_CREAT|O_TRUNC,0600); "
            "if(fd<0 || write(fd,bytes,sizeof(bytes))!=(ssize_t)sizeof(bytes))return 17; close(fd);} "
            "sleep(2);"
        ),
    )
    limits = ExecutionLimits(
        tool_timeout_seconds=3,
        max_output_file_bytes=8_192,
        max_output_bytes=8_192,
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
    assert all("TOOL_EXIT_NONZERO" in item.failures for item in result.invocations), [
        item.failures for item in result.invocations
    ]


def test_kernel_quota_counts_open_unlinked_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _preflight(monkeypatch, tmp_path)
    tool = build_static_tool(
        tmp_path,
        outputs={},
        extra_source=(
            "int exhausted=0; int held[64]; char path[256]; char bytes[65536]; "
            "memset(bytes,1,sizeof(bytes)); "
            'for(int i=0;i<64;i++){snprintf(path,sizeof(path),"%s/hidden-%d",output,i); '
            "held[i]=open(path,O_WRONLY|O_CREAT|O_EXCL,0600); if(held[i]<0){exhausted=1;break;} "
            "unlink(path); if(write(held[i],bytes,sizeof(bytes))!=(ssize_t)sizeof(bytes)){exhausted=1;break;}} "
            "if(!exhausted)sleep(2);"
        ),
    )
    limits = ExecutionLimits(tool_timeout_seconds=3, max_output_bytes=1024 * 1024)
    started = time.monotonic()
    result = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=tmp_path / "unlink-cache",
        output_directory=tmp_path / "unlink-result",
        pipeline_revision="pipeline-security-v1",
        execution_profile=build_execution_profile(limits),
    )

    assert time.monotonic() - started < 1.5
    assert result.status == "BLOCKED"
    assert all("OUTPUT_EMPTY" in item.failures for item in result.invocations)


def test_kernel_quota_is_shared_by_output_writer_processes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _preflight(monkeypatch, tmp_path)
    tool = build_static_tool(
        tmp_path,
        outputs={},
        extra_source=(
            "pid_t children[4]; char bytes[524288]; memset(bytes,1,sizeof(bytes)); "
            "for(int i=0;i<4;i++){children[i]=fork(); if(children[i]==0){char path[256]; "
            'snprintf(path,sizeof(path),"%s/child-%d",output,i); int fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600); '
            "unlink(path); _exit(fd<0 || write(fd,bytes,sizeof(bytes))!=(ssize_t)sizeof(bytes) ? 42 : 0);}} "
            "int exhausted=0,status=0; for(int i=0;i<4;i++){waitpid(children[i],&status,0); "
            "if(!WIFEXITED(status)||WEXITSTATUS(status)!=0)exhausted=1;} if(!exhausted)sleep(2);"
        ),
    )
    limits = ExecutionLimits(tool_timeout_seconds=3, max_output_bytes=1024 * 1024)
    started = time.monotonic()
    result = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=tmp_path / "multiprocess-cache",
        output_directory=tmp_path / "multiprocess-result",
        pipeline_revision="pipeline-security-v1",
        execution_profile=build_execution_profile(limits),
    )

    assert time.monotonic() - started < 1.5
    assert result.status == "BLOCKED"
    assert all("OUTPUT_EMPTY" in item.failures for item in result.invocations)


@pytest.mark.parametrize("mutation", ["add", "remove", "rename"])
def test_runtime_seal_rejects_nested_directory_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
) -> None:
    tool = _tool(tmp_path, _OUTPUT_BODY)
    nested = tool.parent / "nested"
    nested.mkdir()
    victim = nested / "aa-victim"
    victim.write_text("stable", encoding="utf-8")
    trigger = nested / "zz-trigger"
    trigger.write_text("trigger", encoding="utf-8")
    original_copy = execution._copy_runtime_file_at

    def mutate_after_copy(*args: object, **kwargs: object):
        result = original_copy(*args, **kwargs)  # type: ignore[arg-type]
        if args[1] == "zz-trigger":

            def mutate() -> None:
                if mutation == "add":
                    (nested / "added").write_text("new", encoding="utf-8")
                elif mutation == "remove":
                    victim.unlink()
                else:
                    victim.rename(nested / "renamed")

            actor = threading.Thread(target=mutate)
            actor.start()
            actor.join()
        return result

    monkeypatch.setattr(execution, "_copy_runtime_file_at", mutate_after_copy)
    with pytest.raises(PreparationError, match="directory changed"):
        execution._seal_executable(tool, str(tool.parent), ExecutionLimits())


def test_kernel_quota_covers_all_private_workspace_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _preflight(monkeypatch, tmp_path)
    tool = build_static_tool(
        tmp_path,
        outputs={},
        extra_source=(
            'const char *roots[]={"/run/tmp","/run/home","/run/output"}; '
            "int held[64],exhausted=0; "
            "char bytes[65536],path[256]; memset(bytes,1,sizeof(bytes)); "
            'for(int i=0;i<64;i++){snprintf(path,sizeof(path),"%s/hidden-%d",roots[i%3],i); '
            "held[i]=open(path,O_WRONLY|O_CREAT|O_EXCL,0600); if(held[i]<0){exhausted=1;break;} "
            "unlink(path); if(write(held[i],bytes,sizeof(bytes))!=(ssize_t)sizeof(bytes)){exhausted=1;break;}} "
            "if(!exhausted)sleep(2);"
        ),
    )
    limits = ExecutionLimits(tool_timeout_seconds=3, max_output_bytes=1024 * 1024)
    started = time.monotonic()
    result = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=tmp_path / "private-path-cache",
        output_directory=tmp_path / "private-path-result",
        pipeline_revision="pipeline-security-v1",
        execution_profile=build_execution_profile(limits),
    )

    assert time.monotonic() - started < 1.5
    assert result.status == "BLOCKED"
    assert all("OUTPUT_EMPTY" in item.failures for item in result.invocations)


def test_run_root_denies_writes_outside_private_subdirectories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _preflight(monkeypatch, tmp_path)
    tool = build_static_tool(
        tmp_path,
        outputs={
            "apktool": {"App.smali": "android.bluetooth.BluetoothGatt"},
            "jadx": {"App.java": "android.bluetooth.BluetoothGatt"},
        },
        extra_source=(
            'int fd=open("/run/escape",O_WRONLY|O_CREAT,0600); '
            'if(fd>=0){write(fd,"x",1);close(fd);return 17;}'
        ),
    )
    result = _execute(preflight, tool, tmp_path, "run-escape")

    assert result.status == "COMPLETE"


def test_seccomp_denies_multiprocess_and_unlinked_fd_xattrs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _preflight(monkeypatch, tmp_path)
    tool = build_static_tool(
        tmp_path,
        outputs={},
        extra_source=(
            "pid_t children[4]; for(int i=0;i<4;i++){children[i]=fork(); if(children[i]==0){"
            'char path[128]; snprintf(path,sizeof(path),"/run/tmp/xattr-%d",i); '
            "int fd=open(path,O_RDWR|O_CREAT|O_EXCL,0600); if(fd<0)_exit(40); "
            'if(fsetxattr(fd,"user.attack","x",1,0)!=-1||errno!=EPERM)_exit(41); '
            'if(setxattr(path,"user.attack","x",1,0)!=-1||errno!=EPERM)_exit(42); '
            'if(lsetxattr(path,"user.attack","x",1,0)!=-1||errno!=EPERM)_exit(43); '
            'if(removexattr(path,"user.attack")!=-1||errno!=EPERM)_exit(44); '
            'if(lremovexattr(path,"user.attack")!=-1||errno!=EPERM)_exit(45); '
            'unlink(path); if(fremovexattr(fd,"user.attack")!=-1||errno!=EPERM)_exit(46); '
            "if(syscall(463,-1,0,0,0,0)!=-1||errno!=EPERM)_exit(47); "
            "if(syscall(466,-1,0,0)!=-1||errno!=EPERM)_exit(48); close(fd); _exit(0);}} "
            "if(syscall(425,1,0)!=-1||errno!=EPERM)_exit(49); "
            "int failed=0,status=0; for(int i=0;i<4;i++){waitpid(children[i],&status,0); "
            "if(!WIFEXITED(status)||WEXITSTATUS(status)!=0)failed=1;} if(failed)sleep(2); "
            'write_member(output,strcmp(route,"apktool")==0?"App.smali":"App.java",'
            '"android.bluetooth.BluetoothGatt");'
        ),
    )
    started = time.monotonic()
    result = _execute(preflight, tool, tmp_path, "xattr-seccomp")

    assert time.monotonic() - started < 1.5
    assert result.status == "COMPLETE"


def test_second_runtime_walk_rejects_earlier_file_content_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tool = _tool(tmp_path, _OUTPUT_BODY)
    earlier = tool.parent / "aa-earlier"
    earlier.write_text("original", encoding="utf-8")
    later = tool.parent / "zz-later"
    later.write_text("later", encoding="utf-8")
    original_copy = execution._copy_runtime_file_at

    def mutate_after_later_copy(*args: object, **kwargs: object):
        result = original_copy(*args, **kwargs)  # type: ignore[arg-type]
        if args[1] == "zz-later":
            earlier.write_text("mutated!", encoding="utf-8")
        return result

    monkeypatch.setattr(execution, "_copy_runtime_file_at", mutate_after_later_copy)
    with pytest.raises(PreparationError, match="between sealing passes"):
        execution._seal_executable(tool, str(tool.parent), ExecutionLimits())
