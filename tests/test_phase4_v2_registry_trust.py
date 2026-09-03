from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

import tools.phase4_v2.preflight.core as preflight_core
import tools.phase4_v2.preflight.registry as registry_module
from tools.phase4_v2.preflight import (
    PreparationError,
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
    load_activated_preparation_authority,
    load_preparation_receipt,
    preparation_authority_payload,
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
    tool = root / "fixture-tool"
    tool.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('fixture-tool 1.2.3')\n"
        "    raise SystemExit(0)\n"
        "route, _input, output = sys.argv[-3:]\n"
        "target = pathlib.Path(output, 'smali/App.smali' if route == 'apktool' "
        "else 'sources/App.java')\n"
        "target.parent.mkdir(parents=True, exist_ok=True)\n"
        "target.write_text('Landroid/bluetooth/BluetoothGatt;', encoding='utf-8')\n",
        encoding="utf-8",
    )
    tool.chmod(0o700)
    return tool


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
    payload = preparation_authority_payload(registry, profile)
    return load_activated_preparation_authority(
        payload, expected_activation_sha256=hashlib.sha256(payload).hexdigest()
    )


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
    manifest_digest, candidate_digest = _write_payloads(result, manifest, candidates)

    with pytest.raises(PreparationError, match="exhaustively reproduce"):
        load_preparation_receipt(
            result,
            preflight=preflight,
            registry=registry,
            authority=authority,
            execution_profile=profile,
            cache_directory=cache,
            expected_manifest_sha256=manifest_digest,
            expected_candidate_index_sha256=candidate_digest,
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
    manifest_digest, candidate_digest = _write_payloads(result, manifest, candidates)

    with pytest.raises(PreparationError, match="authoritative jadx-to-apktool fallback"):
        load_preparation_receipt(
            result,
            preflight=preflight,
            registry=registry,
            authority=authority,
            execution_profile=profile,
            cache_directory=cache,
            expected_manifest_sha256=manifest_digest,
            expected_candidate_index_sha256=candidate_digest,
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
        expected = "blocking diagnostic"
    else:
        invocation["outputs"].append(dict(invocation["outputs"][0]))
        expected = "ambiguous paths"
    manifest_digest, candidate_digest = _write_payloads(result, manifest, candidates)

    with pytest.raises(PreparationError, match=expected):
        load_preparation_receipt(
            result,
            preflight=preflight,
            registry=registry,
            authority=authority,
            execution_profile=profile,
            cache_directory=cache,
            expected_manifest_sha256=manifest_digest,
            expected_candidate_index_sha256=candidate_digest,
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
    payload = (b"[" * 65) + b"0" + (b"]" * 65)
    with pytest.raises(PreparationError, match="nesting limit"):
        load_activated_preparation_authority(
            payload, expected_activation_sha256=hashlib.sha256(payload).hexdigest()
        )
