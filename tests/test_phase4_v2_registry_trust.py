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
    PreparationError,
    PreparationExecutionSigner,
    ToolSpec,
    execute_registered_preparation,
    preflight_delivery,
)
from tools.phase4_v2.preflight.execution import (
    ExecutionProfile,
    build_execution_profile,
    qualify_tool,
)
from tools.phase4_v2.preflight.registry import (
    REQUIRED_PREPARATION_ROUTES,
    ActivatedPreparationAuthority,
    ApprovedRoute,
    ApprovedToolRegistry,
    OutputSufficiencyContract,
    ToolQualification,
    load_preparation_receipt,
    preparation_authority_payload,
)

_SIGNER = PreparationExecutionSigner._from_private_bytes(b"r" * 32)
_TEST_ACTIVATION_DIGEST = "0" * 64


@pytest.fixture(autouse=True)
def _protected_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        registry_module,
        "_read_protected_activation_digest",
        lambda: _TEST_ACTIVATION_DIGEST,
    )


def _ready_preflight(monkeypatch: pytest.MonkeyPatch, root: Path):
    artifact = root / "base.apk"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", b"dex")

    def identity(arguments: tuple[str, ...], **_kwargs: object) -> tuple[str, None]:
        if arguments[0] == "aapt2":
            return "package: name='org.example.bed' versionCode='42' versionName='4.2'\n", None
        return f"Signer #1 certificate SHA-256 digest: {'a' * 64}\n", None

    monkeypatch.setattr(preflight_core, "_run_identity_tool", identity)
    (root / "seal").mkdir()
    return preflight_delivery([artifact], sealing_directory=root / "seal")


def _tool(root: Path) -> Path:
    return build_static_tool(
        root,
        outputs={
            "apktool": {"smali/App.smali": "Landroid/bluetooth/BluetoothGatt;"},
            "jadx": {"sources/App.java": "Landroid/bluetooth/BluetoothGatt;"},
        },
    )


def _registry(
    tool: Path,
    *,
    flag: str = "--deterministic",
    runtime_sha256: str | None = None,
) -> ApprovedToolRegistry:
    spec = ToolSpec(
        str(tool),
        ("--version",),
        (flag, "apktool", "{input}", "{output}"),
        (flag,),
        str(tool.parent),
    )
    record = qualify_tool(spec, build_execution_profile())
    assert record.binary_sha256 is not None
    assert record.version is not None
    assert record.runtime_sha256 is not None
    assert record.runtime_files is not None
    qualification = ToolQualification(
        record.binary_sha256,
        record.version,
        runtime_sha256 or record.runtime_sha256,
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
                    (flag, route, "{input}", "{output}"),
                    (flag,),
                    str(tool.parent),
                ),
                (qualification,),
                OutputSufficiencyContract(
                    required_suffixes=((".smali",) if route == "apktool" else (".java",))
                ),
            )
            for route in REQUIRED_PREPARATION_ROUTES
        ),
    )


def _authority(
    registry: ApprovedToolRegistry, profile: ExecutionProfile
) -> ActivatedPreparationAuthority:
    global _TEST_ACTIVATION_DIGEST
    payload = preparation_authority_payload(registry, profile, _SIGNER.public_key)
    _TEST_ACTIVATION_DIGEST = hashlib.sha256(payload).hexdigest()
    return registry_module.load_activated_preparation_authority(payload)


def _completed(monkeypatch: pytest.MonkeyPatch, root: Path):
    preflight = _ready_preflight(monkeypatch, root)
    registry = _registry(_tool(root))
    profile = build_execution_profile()
    authority = _authority(registry, profile)
    cache = root / "cache"
    result = root / "result"
    receipt = execute_registered_preparation(
        preflight,
        registry=registry,
        authority=authority,
        execution_profile=profile,
        execution_signer=_SIGNER,
        cache_directory=cache,
        output_directory=result,
    )
    return preflight, registry, profile, authority, cache, result, receipt


def _write_payloads(
    result: Path, manifest: dict[str, object], candidates: dict[str, object]
) -> tuple[str, str]:
    candidate_bytes = (
        json.dumps(candidates, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        + b"\n"
    )
    candidate_digest = hashlib.sha256(candidate_bytes).hexdigest()
    candidate_pin = manifest["candidate_index"]
    assert isinstance(candidate_pin, dict)
    candidate_pin["sha256"] = candidate_digest
    candidate_items = candidates["candidates"]
    assert isinstance(candidate_items, list)
    candidate_pin["candidates"] = len(candidate_items)
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        + b"\n"
    )
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    (result / "candidate-index.json").write_bytes(candidate_bytes)
    (result / "manifest.json").write_bytes(manifest_bytes)
    (result / "PREPARATION.COMPLETE").write_text(
        f"{manifest_digest} manifest.json\n{candidate_digest} candidate-index.json\n",
        encoding="ascii",
    )
    return manifest_digest, candidate_digest


def test_malicious_self_pinned_registry_cannot_replace_activated_registry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path)
    approved = _registry(tool)
    malicious = _registry(tool, flag="--malicious")
    profile = build_execution_profile()

    with pytest.raises(PreparationError, match="activated authority"):
        execute_registered_preparation(
            preflight,
            registry=malicious,
            authority=_authority(approved, profile),
            execution_profile=profile,
            execution_signer=_SIGNER,
            cache_directory=tmp_path / "cache",
            output_directory=tmp_path / "result",
        )


def test_registered_preparation_requires_exact_authority_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    registry = _registry(_tool(tmp_path))
    profile = build_execution_profile()

    with pytest.raises(PreparationError, match="externally activated authority"):
        execute_registered_preparation(
            preflight,
            registry=registry,
            authority=object(),  # type: ignore[arg-type]
            execution_profile=profile,
            execution_signer=_SIGNER,
            cache_directory=tmp_path / "cache",
            output_directory=tmp_path / "result",
        )


def test_registered_preparation_rejects_unapproved_runtime_closure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    registry = _registry(_tool(tmp_path), runtime_sha256="f" * 64)
    profile = build_execution_profile()

    with pytest.raises(PreparationError, match="tool build is not approved"):
        execute_registered_preparation(
            preflight,
            registry=registry,
            authority=_authority(registry, profile),
            execution_profile=profile,
            execution_signer=_SIGNER,
            cache_directory=tmp_path / "cache",
            output_directory=tmp_path / "result",
        )


def test_frozen_loader_rejects_candidate_omission_even_with_resealed_payloads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight, registry, profile, authority, cache, result, _receipt = _completed(
        monkeypatch, tmp_path
    )
    manifest = json.loads((result / "manifest.json").read_bytes())
    candidates = json.loads((result / "candidate-index.json").read_bytes())
    candidates["candidates"] = []
    _write_payloads(result, manifest, candidates)

    with pytest.raises(PreparationError, match="attestation is invalid"):
        load_preparation_receipt(
            result,
            preflight=preflight,
            registry=registry,
            authority=authority,
            execution_profile=profile,
            cache_directory=cache,
        )


def test_frozen_loader_rejects_false_jadx_fallback_with_resealed_payloads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight, registry, profile, authority, cache, result, _receipt = _completed(
        monkeypatch, tmp_path
    )
    manifest = json.loads((result / "manifest.json").read_bytes())
    candidates = json.loads((result / "candidate-index.json").read_bytes())
    jadx = next(item for item in manifest["invocations"] if item["route"] == "jadx")
    jadx["status"] = "FALLBACK"
    jadx["fallback_route"] = "apktool"
    jadx["fallback_reason"] = "JADX_OUTPUT_SUSPICIOUS"
    _write_payloads(result, manifest, candidates)

    with pytest.raises(PreparationError, match="attestation is invalid"):
        load_preparation_receipt(
            result,
            preflight=preflight,
            registry=registry,
            authority=authority,
            execution_profile=profile,
            cache_directory=cache,
        )


@pytest.mark.parametrize("mutation", ["warning", "duplicate-output"])
def test_frozen_loader_rejects_executor_impossible_success_payloads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mutation: str
) -> None:
    preflight, registry, profile, authority, cache, result, _receipt = _completed(
        monkeypatch, tmp_path
    )
    manifest = json.loads((result / "manifest.json").read_bytes())
    candidates = json.loads((result / "candidate-index.json").read_bytes())
    invocation = manifest["invocations"][0]
    if mutation == "warning":
        invocation["warnings"] = [
            {
                "line": 1,
                "sha256": hashlib.sha256(b"warning: partial").hexdigest(),
                "stream": "stderr",
                "text": "warning: partial",
            }
        ]
    else:
        invocation["outputs"].append(dict(invocation["outputs"][0]))
    _write_payloads(result, manifest, candidates)

    with pytest.raises(PreparationError, match="attestation is invalid"):
        load_preparation_receipt(
            result,
            preflight=preflight,
            registry=registry,
            authority=authority,
            execution_profile=profile,
            cache_directory=cache,
        )


def test_authority_rejects_execution_profile_transplant(tmp_path: Path) -> None:
    registry = _registry(_tool(tmp_path))
    profile = build_execution_profile()
    authority = _authority(registry, profile)
    changed = build_execution_profile(
        type(profile.limits)(tool_timeout_seconds=profile.limits.tool_timeout_seconds - 1)
    )

    with pytest.raises(PreparationError, match="activated authority"):
        registry_module._validate_authority(authority, registry, changed)


def test_authority_json_depth_is_bounded() -> None:
    global _TEST_ACTIVATION_DIGEST
    payload = (b"[" * 65) + b"0" + (b"]" * 65)
    _TEST_ACTIVATION_DIGEST = hashlib.sha256(payload).hexdigest()
    with pytest.raises(PreparationError, match="nesting limit"):
        registry_module.load_activated_preparation_authority(payload)


def test_public_authority_loader_rejects_self_issued_digest_argument() -> None:
    with pytest.raises(TypeError, match="unexpected keyword"):
        registry_module.load_activated_preparation_authority(
            b"caller authority\n",
            expected_activation_sha256=hashlib.sha256(b"caller authority\n").hexdigest(),  # pyright: ignore[reportCallIssue]
        )


def test_registered_execution_rejects_signer_outside_protected_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    registry = _registry(_tool(tmp_path))
    profile = build_execution_profile()
    authority = _authority(registry, profile)
    wrong_signer = PreparationExecutionSigner._from_private_bytes(b"x" * 32)

    with pytest.raises(PreparationError, match="signer does not match"):
        execute_registered_preparation(
            preflight,
            registry=registry,
            authority=authority,
            execution_profile=profile,
            execution_signer=wrong_signer,
            cache_directory=tmp_path / "cache",
            output_directory=tmp_path / "result",
        )


def test_runtime_tree_mutation_invalidates_registered_qualification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = _ready_preflight(monkeypatch, tmp_path)
    tool = _tool(tmp_path)
    helper = tool.parent / "runtime.data"
    helper.write_text("approved", encoding="utf-8")
    registry = _registry(tool)
    profile = build_execution_profile()
    authority = _authority(registry, profile)
    helper.write_text("changed", encoding="utf-8")

    with pytest.raises(PreparationError, match="tool build is not approved"):
        execute_registered_preparation(
            preflight,
            registry=registry,
            authority=authority,
            execution_profile=profile,
            execution_signer=_SIGNER,
            cache_directory=tmp_path / "cache",
            output_directory=tmp_path / "result",
        )
