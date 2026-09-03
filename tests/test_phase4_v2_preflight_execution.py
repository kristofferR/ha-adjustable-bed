from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

import tools.phase4_v2.preflight.core as preflight_core
import tools.phase4_v2.preflight.registry as registry_module
from tests.phase4_v2_static_tool import build_static_tool
from tools.phase4_v2.preflight import (
    CANDIDATE_INDEX_SCHEMA,
    EXECUTION_CACHE_SCHEMA,
    EXECUTION_SCHEMA,
    REQUIRED_PREPARATION_ROUTES,
    ApprovedRoute,
    ApprovedToolRegistry,
    ExecutionLimits,
    OutputSufficiencyContract,
    PreparationCacheError,
    PreparationError,
    PreparationExecutionSigner,
    ToolQualification,
    ToolSpec,
    execute_preparation,
    execute_registered_preparation,
    load_activated_preparation_authority,
    load_preparation_receipt,
    preflight_delivery,
    preparation_authority_payload,
)
from tools.phase4_v2.preflight.execution import build_execution_profile, qualify_tool

_SIGNER = PreparationExecutionSigner._from_private_bytes(b"p" * 32)
_TEST_ACTIVATION_DIGEST = "0" * 64


@pytest.fixture(autouse=True)
def _protected_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        registry_module,
        "_read_protected_activation_digest",
        lambda: _TEST_ACTIVATION_DIGEST,
    )


def _ready_preflight(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    artifact = tmp_path / "base.apk"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", b"dex")

    def identity(arguments: tuple[str, ...], **_kwargs: object) -> tuple[str, None]:
        if arguments[0] == "aapt2":
            return "package: name='org.example.bed' versionCode='42' versionName='4.2'\n", None
        return f"Signer #1 certificate SHA-256 digest: {'a' * 64}\n", None

    monkeypatch.setattr(preflight_core, "_run_identity_tool", identity)
    sealing_directory = tmp_path / "seal"
    sealing_directory.mkdir()
    return preflight_delivery([artifact], sealing_directory=sealing_directory)


def _tool(
    tmp_path: Path,
    *,
    outputs: dict[str, dict[str, str]] | None = None,
    modes: dict[str, str] | None = None,
    diagnostics: dict[str, str] | None = None,
    counter: Path | None = None,
    version_mode: str = "normal",
) -> Path:
    del counter
    return build_static_tool(
        tmp_path,
        outputs=outputs
        or {
            "apktool": {"smali/App.smali": "Landroid/bluetooth/BluetoothGatt;"},
            "jadx": {
                "sources/App.java": (
                    "android.bluetooth.BluetoothGatt g; g.writeCharacteristic(value);"
                )
            },
        },
        modes=modes,
        diagnostics=diagnostics,
        version_mode=version_mode,
    )


def _specs(tool: Path, *, extra_flag: str | None = None) -> dict[str, ToolSpec]:
    flags = ("--deterministic",) + ((extra_flag,) if extra_flag is not None else ())
    return {
        route: ToolSpec(
            str(tool),
            ("--version",),
            (*flags, route, "{input}", "{output}"),
            flags,
            str(tool.parent),
        )
        for route in ("apktool", "jadx")
    }


def _registry(
    tool: Path,
    *,
    qualification_sha256: str | None = None,
    extra_flag: str | None = None,
) -> ApprovedToolRegistry:
    flags = ("--deterministic",) + ((extra_flag,) if extra_flag is not None else ())
    spec = ToolSpec(
        str(tool),
        ("--version",),
        (*flags, "apktool", "{input}", "{output}"),
        flags,
        str(tool.parent),
    )
    record = qualify_tool(spec, build_execution_profile())
    assert record.binary_sha256 is not None
    assert record.version is not None
    assert record.runtime_sha256 is not None
    assert record.runtime_files is not None
    qualification = ToolQualification(
        qualification_sha256 or record.binary_sha256,
        record.version,
        record.runtime_sha256,
        record.runtime_files,
    )
    return ApprovedToolRegistry(
        "fixture-registry-v1",
        "pipeline-v1",
        tuple(
            ApprovedRoute(
                route,
                ToolSpec(
                    str(tool),
                    ("--version",),
                    (*flags, route, "{input}", "{output}"),
                    flags,
                    str(tool.parent),
                ),
                (qualification,),
                OutputSufficiencyContract(
                    required_suffixes=(
                        (".smali",) if route == "apktool" else (".java",) if route == "jadx" else ()
                    )
                ),
            )
            for route in REQUIRED_PREPARATION_ROUTES
        ),
    )


def _activated(registry: ApprovedToolRegistry):
    global _TEST_ACTIVATION_DIGEST
    profile = build_execution_profile()
    payload = preparation_authority_payload(registry, profile, _SIGNER.public_key)
    _TEST_ACTIVATION_DIGEST = hashlib.sha256(payload).hexdigest()
    authority = load_activated_preparation_authority(payload)
    return profile, authority


def test_registered_preparation_binds_the_complete_approved_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(
        tmp_path,
        outputs={
            "apktool": {"smali/App.smali": "Landroid/bluetooth/BluetoothGatt;"},
            "jadx": {
                "sources/App.java": (
                    "BluetoothLE ByteArray BluetoothCharacteristic Guid( "
                    "flutter_reactive_ble flutter_blue bt_gatt bluetooth_gatt "
                    "sd_ble_gattc_write uuid_parse BleManager react-native-ble-plx "
                    "writeCharacteristicWithResponseForDevice characteristicUUID "
                    "connectToDevice monitorCharacteristic startNotification "
                    "startDeviceScan serviceUUIDs writeWithoutResponse"
                )
            },
        },
    )
    registry = _registry(tool)
    profile, authority = _activated(registry)

    receipt = execute_registered_preparation(
        preflight,
        registry=registry,
        authority=authority,
        execution_profile=profile,
        execution_signer=_SIGNER,
        cache_directory=tmp_path / "cache",
        output_directory=tmp_path / "result",
    )

    assert receipt.tool_registry_sha256 == registry.sha256
    assert receipt.pipeline_revision == "pipeline-v1"
    assert {candidate.signal for candidate in receipt.candidates} >= {
        "air.bluetooth-le",
        "flutter.characteristic",
        "native.nordic-write",
        "react-native.ble-plx",
        "react-native.write",
    }
    reloaded = load_preparation_receipt(
        tmp_path / "result",
        preflight=preflight,
        registry=registry,
        authority=authority,
        execution_profile=profile,
        cache_directory=tmp_path / "cache",
    )
    assert reloaded.content_id == receipt.content_id
    assert receipt.executor_public_key == _SIGNER.public_key
    assert len(receipt.execution_signature) == 128


def test_authenticated_cache_survives_process_trust_reset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path)
    registry = _registry(tool)
    profile, authority = _activated(registry)
    cache = tmp_path / "cache"
    first = execute_registered_preparation(
        preflight,
        registry=registry,
        authority=authority,
        execution_profile=profile,
        execution_signer=_SIGNER,
        cache_directory=cache,
        output_directory=tmp_path / "first",
    )
    objects = tuple((cache / "objects" / EXECUTION_CACHE_SCHEMA).iterdir())
    identities = tuple((item.name, item.stat().st_ino) for item in objects)
    import tools.phase4_v2.preflight.execution as execution_module

    execution_module._TRUSTED_CACHE_OBJECTS.clear()
    second = execute_registered_preparation(
        preflight,
        registry=registry,
        authority=authority,
        execution_profile=profile,
        execution_signer=_SIGNER,
        cache_directory=cache,
        output_directory=tmp_path / "second",
    )

    assert second.manifest_sha256 == first.manifest_sha256
    assert (
        tuple(
            (item.name, item.stat().st_ino)
            for item in (cache / "objects" / EXECUTION_CACHE_SCHEMA).iterdir()
        )
        == identities
    )


def test_registered_preparation_rejects_untrusted_registry_and_tool_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path)
    registry = _registry(tool)
    changed = _registry(tool, extra_flag="--changed")
    profile, authority = _activated(registry)

    with pytest.raises(PreparationError, match="activated authority"):
        execute_registered_preparation(
            preflight,
            registry=changed,
            authority=authority,
            execution_profile=profile,
            execution_signer=_SIGNER,
            cache_directory=tmp_path / "cache-a",
            output_directory=tmp_path / "result-a",
        )
    assert not (tmp_path / "result-a").exists()

    unqualified = _registry(tool, qualification_sha256="f" * 64)
    unqualified_profile, unqualified_authority = _activated(unqualified)
    with pytest.raises(PreparationError, match="tool build is not approved"):
        execute_registered_preparation(
            preflight,
            registry=unqualified,
            authority=unqualified_authority,
            execution_profile=unqualified_profile,
            execution_signer=_SIGNER,
            cache_directory=tmp_path / "cache-b",
            output_directory=tmp_path / "result-b",
        )
    assert not (tmp_path / "result-b" / "PREPARATION.COMPLETE").exists()
    assert (tmp_path / "result-b" / "PREPARATION.BLOCKED").is_file()


def test_frozen_preparation_requires_external_payload_pins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path)
    registry = _registry(tool)
    profile, authority = _activated(registry)
    execute_registered_preparation(
        preflight,
        registry=registry,
        authority=authority,
        execution_profile=profile,
        execution_signer=_SIGNER,
        cache_directory=tmp_path / "cache",
        output_directory=tmp_path / "result",
    )
    candidate_index = tmp_path / "result" / "candidate-index.json"
    candidate_index.write_bytes(candidate_index.read_bytes() + b" ")

    with pytest.raises(PreparationError, match="canonical|externally trusted digest"):
        load_preparation_receipt(
            tmp_path / "result",
            preflight=preflight,
            registry=registry,
            authority=authority,
            execution_profile=profile,
            cache_directory=tmp_path / "cache",
        )


def test_registered_preparation_accepts_only_authoritative_jadx_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(
        tmp_path,
        outputs={
            "apktool": {"smali/App.smali": "Landroid/bluetooth/BluetoothGatt;"},
            "jadx": {"resources/notice.txt": "no source recovered"},
        },
    )
    registry = _registry(tool)
    profile, authority = _activated(registry)

    receipt = execute_registered_preparation(
        preflight,
        registry=registry,
        authority=authority,
        execution_profile=profile,
        execution_signer=_SIGNER,
        cache_directory=tmp_path / "cache",
        output_directory=tmp_path / "result",
    )

    jadx = next(item for item in receipt.invocations if item.route == "jadx")
    assert jadx.status == "FALLBACK"
    assert (jadx.fallback_route, jadx.fallback_reason) == (
        "apktool",
        "JADX_OUTPUT_SUSPICIOUS",
    )


def test_execution_manifest_is_complete_content_bound_and_deterministic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path)

    first = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=tmp_path / "cache-a",
        output_directory=tmp_path / "result-a",
        pipeline_revision="pipeline-v1",
    )
    second = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=tmp_path / "cache-b",
        output_directory=tmp_path / "result-b",
        pipeline_revision="pipeline-v1",
    )

    assert first.status == "COMPLETE", [item.to_data() for item in first.invocations]
    assert [item.route for item in first.invocations] == ["apktool", "jadx"]
    assert all(item.status == "COMPLETE" for item in first.invocations)
    assert all(item.tool.version == "fixture-tool 1.2.3" for item in first.invocations)
    assert all(
        item.tool.binary_sha256 == hashlib.sha256(tool.read_bytes()).hexdigest()
        for item in first.invocations
    )
    assert all(item.arguments[-2:] == ("input.apk", "output") for item in first.invocations)
    assert all(item.flags == ("--deterministic",) for item in first.invocations)
    assert {candidate.signal for candidate in first.candidates} >= {
        "android.bluetooth.descriptor",
        "android.bluetooth.namespace",
        "bluetooth.write",
    }
    assert (tmp_path / "result-a" / "PREPARATION.COMPLETE").is_file()
    manifest = json.loads((tmp_path / "result-a" / "manifest.json").read_bytes())
    candidates = json.loads((tmp_path / "result-a" / "candidate-index.json").read_bytes())
    assert manifest["schema"] == EXECUTION_SCHEMA
    assert candidates["schema"] == CANDIDATE_INDEX_SCHEMA
    assert (tmp_path / "result-a" / "manifest.json").read_bytes() == (
        tmp_path / "result-b" / "manifest.json"
    ).read_bytes()
    assert (tmp_path / "result-a" / "candidate-index.json").read_bytes() == (
        tmp_path / "result-b" / "candidate-index.json"
    ).read_bytes()
    assert first.manifest_sha256 == second.manifest_sha256


def test_complete_invocations_are_cached_and_pipeline_and_flags_invalidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path)
    cache = tmp_path / "cache"
    objects = cache / "objects" / EXECUTION_CACHE_SCHEMA

    for destination in ("one", "two"):
        execute_preparation(
            preflight,
            tool_specs=_specs(tool),
            cache_directory=cache,
            output_directory=tmp_path / destination,
            pipeline_revision="pipeline-v1",
        )
    assert len(list(objects.iterdir())) == 2

    execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=cache,
        output_directory=tmp_path / "three",
        pipeline_revision="pipeline-v2",
    )
    execute_preparation(
        preflight,
        tool_specs=_specs(tool, extra_flag="--stable-output"),
        cache_directory=cache,
        output_directory=tmp_path / "four",
        pipeline_revision="pipeline-v2",
    )
    assert len(list(objects.iterdir())) == 6


def test_approved_registry_digest_invalidates_preparation_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path)
    cache = tmp_path / "cache"

    for name, registry_sha256 in (("one", "a" * 64), ("two", "a" * 64), ("three", "b" * 64)):
        execute_preparation(
            preflight,
            tool_specs=_specs(tool),
            cache_directory=cache,
            output_directory=tmp_path / name,
            pipeline_revision="pipeline-v1",
            tool_registry_sha256=registry_sha256,
        )

    objects = cache / "objects" / EXECUTION_CACHE_SCHEMA
    assert len(list(objects.iterdir())) == 4


def test_warning_is_exactly_recorded_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path, diagnostics={"jadx": "WARNING: incomplete decompilation"})

    result = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=tmp_path / "cache",
        output_directory=tmp_path / "result",
        pipeline_revision="pipeline-v1",
    )

    assert result.status == "BLOCKED"
    jadx = next(item for item in result.invocations if item.route == "jadx")
    assert jadx.failures == ("TOOL_DIAGNOSTIC",)
    assert [warning.text for warning in jadx.warnings] == ["WARNING: incomplete decompilation"]
    assert (tmp_path / "result" / "PREPARATION.BLOCKED").is_file()
    assert len(list((tmp_path / "cache" / "objects" / EXECUTION_CACHE_SCHEMA).iterdir())) == 1


@pytest.mark.parametrize(
    ("version_mode", "failure"),
    [("non-utf8", "TOOL_VERSION_NON_UTF8"), ("empty", "TOOL_VERSION_EMPTY")],
)
def test_invalid_tool_versions_retain_the_exact_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    version_mode: str,
    failure: str,
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path, version_mode=version_mode)

    result = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=tmp_path / "cache",
        output_directory=tmp_path / "result",
        pipeline_revision="pipeline-v1",
    )

    assert result.status == "BLOCKED"
    assert {item.tool.failure for item in result.invocations} == {failure}
    assert all(item.tool.version is None for item in result.invocations)


@pytest.mark.parametrize(
    ("mode", "failure"),
    [
        ("crash", "TOOL_EXIT_NONZERO"),
        ("partial", "OUTPUT_EMPTY"),
        ("symlink", "OUTPUT_UNSAFE_NODE"),
    ],
)
def test_crash_partial_and_unsafe_outputs_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str, failure: str
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path, modes={"jadx": mode})

    result = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=tmp_path / "cache",
        output_directory=tmp_path / "result",
        pipeline_revision="pipeline-v1",
    )

    assert result.status == "BLOCKED"
    assert failure in next(item for item in result.invocations if item.route == "jadx").failures


@pytest.mark.parametrize(
    ("mode", "limits", "failure"),
    [
        ("noisy", ExecutionLimits(max_tool_stream_bytes=128), "TOOL_OUTPUT_LIMIT"),
        ("timeout", ExecutionLimits(tool_timeout_seconds=0.05), "TOOL_TIMEOUT"),
    ],
)
def test_stream_and_timeout_limits_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
    limits: ExecutionLimits,
    failure: str,
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path, modes={"jadx": mode})

    result = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=tmp_path / "cache",
        output_directory=tmp_path / "result",
        pipeline_revision="pipeline-v1",
        limits=limits,
    )

    assert result.status == "BLOCKED"
    assert failure in next(item for item in result.invocations if item.route == "jadx").failures


def test_sandbox_input_is_read_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    artifact_digest = hashlib.sha256((tmp_path / "base.apk").read_bytes()).hexdigest()
    tool = _tool(tmp_path, modes={"jadx": "mutate-input"})

    result = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=tmp_path / "cache",
        output_directory=tmp_path / "result",
        pipeline_revision="pipeline-v1",
    )

    assert result.status == "COMPLETE"
    assert hashlib.sha256((tmp_path / "base.apk").read_bytes()).hexdigest() == artifact_digest


def test_suspicious_jadx_requires_nonempty_smali_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    accepted_tool = _tool(
        tmp_path,
        outputs={
            "apktool": {"smali/App.smali": "smali"},
            "jadx": {"resources/table.txt": "not source"},
        },
    )

    accepted = execute_preparation(
        preflight,
        tool_specs=_specs(accepted_tool),
        cache_directory=tmp_path / "accepted-cache",
        output_directory=tmp_path / "accepted",
        pipeline_revision="pipeline-v1",
    )

    assert accepted.status == "COMPLETE"
    jadx = next(item for item in accepted.invocations if item.route == "jadx")
    assert jadx.status == "FALLBACK"
    assert jadx.fallback_reason == "JADX_OUTPUT_SUSPICIOUS"
    assert jadx.fallback_route == "apktool"

    rejected_tool = _tool(
        tmp_path,
        outputs={
            "apktool": {"res/table.xml": "resource"},
            "jadx": {"resources/table.txt": "not source"},
        },
    )
    rejected = execute_preparation(
        preflight,
        tool_specs=_specs(rejected_tool),
        cache_directory=tmp_path / "rejected-cache",
        output_directory=tmp_path / "rejected",
        pipeline_revision="pipeline-v1",
    )
    assert rejected.status == "BLOCKED"
    assert next(item for item in rejected.invocations if item.route == "jadx").failures == (
        "JADX_OUTPUT_SUSPICIOUS",
        "AUTHORITATIVE_SMALI_FALLBACK_MISSING",
    )


def test_missing_route_and_candidate_limit_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path)
    missing = execute_preparation(
        preflight,
        tool_specs={"apktool": _specs(tool)["apktool"]},
        cache_directory=tmp_path / "missing-cache",
        output_directory=tmp_path / "missing",
        pipeline_revision="pipeline-v1",
    )
    assert missing.status == "BLOCKED"
    assert next(item for item in missing.invocations if item.route == "jadx").failures == (
        "TOOL_ROUTE_UNCONFIGURED",
    )

    limited = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=tmp_path / "limited-cache",
        output_directory=tmp_path / "limited",
        pipeline_revision="pipeline-v1",
        limits=ExecutionLimits(max_candidates=1),
    )
    assert limited.status == "BLOCKED"
    assert limited.failures == ("CANDIDATE_RECORD_LIMIT",)


def test_cache_tampering_is_rejected_instead_of_reused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path)
    cache = tmp_path / "cache"
    first = execute_preparation(
        preflight,
        tool_specs=_specs(tool),
        cache_directory=cache,
        output_directory=tmp_path / "first",
        pipeline_revision="pipeline-v1",
    )
    invocation = first.invocations[0]
    assert invocation.cache_key is not None
    output = cache / "objects" / EXECUTION_CACHE_SCHEMA / invocation.cache_key / "outputs"
    target = next(path for path in output.rglob("*") if path.is_file())
    target.write_text("tampered", encoding="utf-8")

    with pytest.raises(PreparationCacheError, match="cache invocation identity mismatch"):
        execute_preparation(
            preflight,
            tool_specs=_specs(tool),
            cache_directory=cache,
            output_directory=tmp_path / "second",
            pipeline_revision="pipeline-v1",
        )
