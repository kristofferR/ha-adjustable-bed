"""Focused tests for deterministic Phase 4 v2 delivery preflight."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import zipfile
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

import pytest

if sys.platform != "linux":
    pytest.skip("Phase 4 v2 preflight requires Linux", allow_module_level=True)

import tools.phase4_v2.preflight.core as legacy_preflight
from tools.phase4_v2.preflight import (
    ArtifactCache,
    CacheIntegrityError,
    PreflightError,
    PreflightLimits,
    SafetyError,
    StackDecision,
    preflight_delivery,
)


def _apk(path: Path, *markers: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in markers:
            archive.writestr(name, f"fixture:{name}")


def _native_apk(path: Path, *extra: str) -> None:
    _apk(path, "AndroidManifest.xml", "classes.dex", *extra)


def _snapshot(paths: list[Path]) -> dict[str, tuple[int, int, int, str]]:
    return {
        path.name: (
            stat.S_IMODE(path.stat().st_mode),
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in paths
    }


def _mock_identity_tools(
    monkeypatch: pytest.MonkeyPatch,
    identities: Mapping[str, tuple[str, str, str, str | None, tuple[str, ...], str]],
    *,
    split_as_package_attribute: bool = False,
    config_for_splits: Mapping[str, str] | None = None,
) -> None:
    def run(arguments: Sequence[str], *, label: str) -> tuple[str | None, str | None]:
        package, code, version, split, required, signer = identities[label]
        if arguments[0] == "apksigner":
            return f"Signer #1 certificate SHA-256 digest: {signer}\n", None
        package_line = f"package: name='{package}' versionCode='{code}' versionName='{version}'"
        if split is not None and split_as_package_attribute:
            package_line += f" split='{split}'"
        if config_for_splits is not None and label in config_for_splits:
            package_line += f" configForSplit='{config_for_splits[label]}'"
        lines = [package_line]
        if split is not None and not split_as_package_attribute:
            lines.append(f"split='{split}'")
        lines.extend(f"uses-split:'{name}'" for name in required)
        return "\n".join(lines) + "\n", None

    monkeypatch.setattr(legacy_preflight, "_run_identity_tool", run)


def test_identity_tool_output_is_bounded_while_streaming(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tool = tmp_path / "noisy-tool"
    tool.write_text(
        f"#!{sys.executable}\n"
        "import os\n"
        "chunk = b'x' * (64 * 1024)\n"
        "for _ in range(100):\n"
        "    os.write(1, chunk)\n",
        encoding="utf-8",
    )
    tool.chmod(0o700)
    monkeypatch.setattr(legacy_preflight.shutil, "which", lambda _name: str(tool))

    output, error = legacy_preflight._run_identity_tool(("noisy-tool",), label="base.apk")

    assert output is None
    assert error == "identity_tool_output_limit:noisy-tool:base.apk"


def test_authoritative_identity_is_deterministic_for_coherent_complete_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / "base.apk"
    split = tmp_path / "config.apk"
    _native_apk(base)
    _native_apk(split)
    signer = "a" * 64
    _mock_identity_tools(
        monkeypatch,
        {
            "base.apk": ("org.example.bed", "42", "4.2", None, ("config.arm64",), signer),
            "config.apk": ("org.example.bed", "42", "4.2", "config.arm64", (), signer),
        },
        split_as_package_attribute=True,
    )

    result = preflight_delivery([split, base])

    assert result.package_identity is not None
    assert result.package_identity.package_name == "org.example.bed"
    assert result.package_identity.split_members == (("config.arm64", "config.apk"),)
    assert result.manifest()["schema"] == "phase4-v2-preflight-v3"
    assert not {
        "package_identity_not_verified",
        "version_identity_not_verified",
        "signer_coherence_not_verified",
        "split_coherence_not_verified",
    }.intersection(result.decision.blockers)
    assert result.decision.status == "READY"
    assert result.decision.blockers == ()
    assert tuple(member.name for member in result.decision.members) == ("base.apk", "config.apk")
    assert all(member.status == "READY" for member in result.decision.members)


def test_ready_classifies_every_apk_once_and_routes_resource_only_split(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / "base.apk"
    resources = tmp_path / "resources.apk"
    _native_apk(base)
    _apk(resources, "AndroidManifest.xml", "res/drawable/icon.png")
    _mock_identity_tools(
        monkeypatch,
        {
            "base.apk": ("org.example.bed", "42", "4.2", None, (), "a" * 64),
            "resources.apk": (
                "org.example.bed",
                "42",
                "4.2",
                "config.resources",
                (),
                "a" * 64,
            ),
        },
    )

    result = preflight_delivery([resources, base])

    assert result.decision.status == "READY"
    assert result.decision.stacks == ("android", "android_dex")
    assert result.decision.routes == ("apktool", "jadx")
    assert tuple(member.name for member in result.decision.members) == (
        "base.apk",
        "resources.apk",
    )
    assert result.decision.members[0].stacks == ("android", "android_dex")
    assert result.decision.members[0].routes == ("apktool", "jadx")
    assert result.decision.members[1].stacks == ("android",)
    assert result.decision.members[1].routes == ("apktool",)
    assert {
        member.name for member in result.decision.members
    } == {member.name for member in result.artifact_members}


def test_ready_routes_all_protocol_neutral_application_substrates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / "base.apk"
    _native_apk(
        base,
        "lib/arm64-v8a/libbed.so",
        "assets/runtime.js",
        "assets/embedded.zip",
    )
    _mock_identity_tools(
        monkeypatch,
        {"base.apk": ("org.example.bed", "42", "4.2", None, (), "a" * 64)},
    )

    result = preflight_delivery([base])

    assert result.decision.status == "READY"
    assert result.decision.stacks == (
        "android",
        "android_dex",
        "embedded_archive",
        "native",
        "shipped_bundle",
    )
    assert result.decision.routes == (
        "apktool",
        "embedded-archive-inventory",
        "jadx",
        "native-library-inventory",
        "shipped-bundle",
    )


def test_verified_identity_cannot_make_unclassified_member_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / "base.apk"
    _apk(base, "classes.dex")
    _mock_identity_tools(
        monkeypatch,
        {"base.apk": ("org.example.bed", "42", "4.2", None, (), "a" * 64)},
    )

    result = preflight_delivery([base])

    assert result.package_identity is not None
    assert result.decision.status == "BLOCKED"
    assert result.decision.members[0].status == "BLOCKED"
    assert result.decision.members[0].blockers == ("android_manifest_missing:base.apk",)
    assert "android_manifest_missing:base.apk" in result.decision.blockers


@pytest.mark.parametrize(
    ("package", "code", "version"),
    [
        ("single", "42", "4.2"),
        ("org.example.bed", "", "4.2"),
        ("org.example.bed", "42", ""),
    ],
)
def test_invalid_authoritative_identity_cannot_reach_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    package: str,
    code: str,
    version: str,
) -> None:
    base = tmp_path / "base.apk"
    _native_apk(base)
    _mock_identity_tools(
        monkeypatch,
        {"base.apk": (package, code, version, None, (), "a" * 64)},
    )

    result = preflight_delivery([base])

    assert result.package_identity is None
    assert result.decision.status == "BLOCKED"
    assert "package_identity_invalid:base.apk" in result.decision.blockers


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        (("org.other", "42", "4.2", "config.arm64", (), "a" * 64), "package_identity_mismatch"),
        (
            ("org.example.bed", "43", "4.3", "config.arm64", (), "a" * 64),
            "version_identity_mismatch",
        ),
        (
            ("org.example.bed", "42", "4.2", "config.arm64", (), "b" * 64),
            "signer_identity_mismatch",
        ),
    ],
)
def test_identity_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    changed: tuple[str, str, str, str | None, tuple[str, ...], str],
    expected: str,
) -> None:
    base = tmp_path / "base.apk"
    split = tmp_path / "config.apk"
    _native_apk(base)
    _native_apk(split)
    _mock_identity_tools(
        monkeypatch,
        {
            "base.apk": ("org.example.bed", "42", "4.2", None, (), "a" * 64),
            "config.apk": changed,
        },
    )

    result = preflight_delivery([base, split])

    assert result.package_identity is None
    assert expected in result.decision.blockers
    assert result.decision.status == "BLOCKED"


def test_missing_declared_split_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / "base.apk"
    _native_apk(base)
    _mock_identity_tools(
        monkeypatch,
        {"base.apk": ("org.example.bed", "42", "4.2", None, ("feature",), "a" * 64)},
    )

    result = preflight_delivery([base])

    assert result.package_identity is None
    assert "required_split_missing:feature" in result.decision.blockers


def test_missing_config_for_split_target_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / "base.apk"
    config = tmp_path / "config.apk"
    _native_apk(base)
    _apk(config, "AndroidManifest.xml", "res/drawable/icon.png")
    signer = "a" * 64
    _mock_identity_tools(
        monkeypatch,
        {
            "base.apk": ("org.example.bed", "42", "4.2", None, (), signer),
            "config.apk": (
                "org.example.bed",
                "42",
                "4.2",
                "config.feature.arm64",
                (),
                signer,
            ),
        },
        config_for_splits={"config.apk": "feature"},
    )

    result = preflight_delivery([base, config])

    assert result.package_identity is None
    assert "config_for_split_missing:feature" in result.decision.blockers


def test_ambiguous_base_and_duplicate_split_identities_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = tmp_path / "first.apk"
    second = tmp_path / "second.apk"
    _native_apk(first)
    _native_apk(second)
    common = ("org.example.bed", "42", "4.2")
    _mock_identity_tools(
        monkeypatch,
        {
            "first.apk": (*common, "config.arm64", (), "a" * 64),
            "second.apk": (*common, "config.arm64", (), "a" * 64),
        },
    )

    result = preflight_delivery([first, second])

    assert result.package_identity is None
    assert "split_base_ambiguous" in result.decision.blockers
    assert "split_identity_duplicate" in result.decision.blockers


def test_split_delivery_identity_is_order_independent_and_read_only(tmp_path: Path) -> None:
    base = tmp_path / "base.apk"
    split = tmp_path / "split_config.arm64_v8a.apk"
    _native_apk(base)
    _native_apk(split)
    before = _snapshot([base, split])

    first = preflight_delivery([base, split])
    second = preflight_delivery([split, base])

    assert first.manifest() == second.manifest()
    assert first.delivery_digest == second.delivery_digest
    assert first.artifact_digest == second.artifact_digest
    assert first.decision.status == "BLOCKED"
    assert first.decision.routes == ("apktool", "jadx")
    assert "split_coherence_not_verified" in first.decision.blockers
    assert {
        "package_identity_not_verified",
        "version_identity_not_verified",
        "signer_coherence_not_verified",
    }.issubset(first.decision.blockers)
    assert _snapshot([base, split]) == before


def test_delivery_digest_changes_across_packaging_but_artifact_digest_does_not(
    tmp_path: Path,
) -> None:
    direct = tmp_path / "base.apk"
    _native_apk(direct)
    container = tmp_path / "delivery.xapk"
    with zipfile.ZipFile(container, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("metadata.json", "{}")
        archive.writestr("nested/base.apk", direct.read_bytes())

    direct_result = preflight_delivery([direct])
    container_result = preflight_delivery([container])

    assert direct_result.delivery_digest != container_result.delivery_digest
    assert direct_result.artifact_digest == container_result.artifact_digest
    assert container_result.artifact_members[0].name == "base.apk"


def test_explicit_sealing_directory_and_result_cleanup(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    sealing_root = tmp_path / "persistent-sealing"
    sealing_root.mkdir()

    with preflight_delivery([artifact], sealing_directory=sealing_root) as result:
        sealed = result.artifact_members[0]._sealed_path
        assert sealing_root in sealed.parents
        assert sealed.is_file()

    assert not sealed.exists()


@pytest.mark.parametrize(
    "unsafe_name",
    ["../escape.apk", "/absolute.apk", "bad\\name.apk", "bad\rname.apk", "bad\nname.apk"],
)
def test_container_rejects_unsafe_member_names(tmp_path: Path, unsafe_name: str) -> None:
    inner = tmp_path / "inner.apk"
    _native_apk(inner)
    delivery = tmp_path / "unsafe.xapk"
    with zipfile.ZipFile(delivery, "w") as archive:
        archive.writestr(unsafe_name, inner.read_bytes())

    with pytest.raises(SafetyError, match="unsafe archive member"):
        preflight_delivery([delivery])


def test_container_rejects_symlink_and_duplicate_members(tmp_path: Path) -> None:
    symlink_delivery = tmp_path / "symlink.xapk"
    link = zipfile.ZipInfo("base.apk")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(symlink_delivery, "w") as archive:
        archive.writestr(link, "target")
    with pytest.raises(SafetyError, match="non-regular"):
        preflight_delivery([symlink_delivery])

    duplicate_delivery = tmp_path / "duplicate.xapk"
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(duplicate_delivery, "w") as archive,
    ):
        archive.writestr("base.apk", b"one")
        archive.writestr("base.apk", b"two")
    with pytest.raises(SafetyError, match="duplicate archive member"):
        preflight_delivery([duplicate_delivery])


def test_apk_rejects_case_ambiguous_members(tmp_path: Path) -> None:
    artifact = tmp_path / "ambiguous.apk"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"first")
        archive.writestr("androidmanifest.xml", b"second")

    with pytest.raises(SafetyError, match="invalid APK member"):
        preflight_delivery([artifact])


@pytest.mark.parametrize(
    ("marker", "stack", "route"),
    [
        ("lib/arm64-v8a/libapp.so", "flutter", "blutter"),
        ("assets/index.android.bundle.hbc", "hermes", "hermes-bundle"),
        ("assets/index.android.bundle", "react_native", "react-native-bundle"),
        ("assets/META-INF/AIR/application.xml", "air", "ffdec"),
    ],
)
def test_specialized_stack_routes_are_canonical_while_identity_fails_closed(
    tmp_path: Path,
    marker: str,
    stack: str,
    route: str,
) -> None:
    artifact = tmp_path / f"{stack}.apk"
    _native_apk(artifact, marker)

    result = preflight_delivery([artifact])

    assert {"android", stack}.issubset(result.decision.stacks)
    assert {"apktool", "jadx", route}.issubset(result.decision.routes)
    assert result.decision.status == "BLOCKED"
    assert result.decision.members[0].status == "READY"
    assert "package_identity_not_verified" in result.decision.blockers


def test_standard_react_native_bundle_uses_hermes_header_for_routing(tmp_path: Path) -> None:
    artifact = tmp_path / "hermes.apk"
    with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", b"dex")
        archive.writestr(
            "assets/index.android.bundle",
            legacy_preflight._HERMES_BYTECODE_MAGIC + b"fixture",
        )

    result = preflight_delivery([artifact])

    assert {"react_native", "hermes"}.issubset(result.decision.stacks)
    assert {"react-native-bundle", "hermes-bundle"}.issubset(result.decision.routes)


def test_unknown_stack_blocks_pipeline_but_not_byte_cache(tmp_path: Path) -> None:
    artifact = tmp_path / "unknown.apk"
    _apk(artifact, "assets/unidentified.payload")

    result = preflight_delivery([artifact])

    assert result.decision.status == "BLOCKED"
    assert "unknown_application_stack:unknown.apk" in result.decision.blockers
    cache = ArtifactCache(tmp_path / "cache")
    object_dir = cache.store(result)
    assert object_dir.is_dir()
    assert "classification" not in cache.verify(result.artifact_digest)


def test_cache_uses_bounded_names_for_long_logical_apk_members(tmp_path: Path) -> None:
    inner = tmp_path / "base.apk"
    _native_apk(inner)
    logical_name = f"{'a' * 300}.apk"
    delivery = tmp_path / "delivery.xapk"
    with zipfile.ZipFile(delivery, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(logical_name, inner.read_bytes())

    result = preflight_delivery([delivery])
    cache = ArtifactCache(tmp_path / "cache")
    object_dir = cache.store(result)
    manifest = cache.verify(result.artifact_digest)
    member = manifest["members"][0]

    assert member["name"] == logical_name
    assert len(member["stored_name"]) <= 255
    assert (object_dir / "members" / member["stored_name"]).is_file()


def test_archive_without_apk_members_has_a_dedicated_blocker(tmp_path: Path) -> None:
    delivery = tmp_path / "empty.xapk"
    with zipfile.ZipFile(delivery, "w") as archive:
        archive.writestr("manifest.json", "{}")

    result = preflight_delivery([delivery])

    assert "delivery_contains_no_apk_members" in result.decision.blockers
    assert not any(
        blocker.startswith("unknown_application_stack:") for blocker in result.decision.blockers
    )


def test_delivery_rejects_non_regular_input_without_opening_it(tmp_path: Path) -> None:
    fifo = tmp_path / "delivery.apk"
    os.mkfifo(fifo)

    with pytest.raises(SafetyError, match="regular file"):
        preflight_delivery([fifo])


def test_delivery_rejects_symlink_input(tmp_path: Path) -> None:
    artifact = tmp_path / "real.apk"
    _native_apk(artifact)
    alias = tmp_path / "alias.apk"
    alias.symlink_to(artifact)

    with pytest.raises(SafetyError, match="regular file"):
        preflight_delivery([alias])


def test_delivery_rejects_unsafe_direct_apk_name(tmp_path: Path) -> None:
    artifact = tmp_path / "unsafe\\name.apk"
    _native_apk(artifact)

    with pytest.raises(SafetyError, match="unsafe archive member name"):
        preflight_delivery([artifact])


@pytest.mark.parametrize("control", ["\r", "\n"])
def test_delivery_rejects_control_characters_in_direct_apk_name(
    tmp_path: Path, control: str
) -> None:
    artifact = tmp_path / f"unsafe{control}name.apk"
    _native_apk(artifact)

    with pytest.raises(SafetyError, match="unsafe archive member name"):
        preflight_delivery([artifact])


def test_one_unknown_member_blocks_an_otherwise_known_split_set(tmp_path: Path) -> None:
    known = tmp_path / "base.apk"
    unknown = tmp_path / "opaque.apk"
    _native_apk(known)
    _apk(unknown, "assets/unidentified.payload")

    result = preflight_delivery([known, unknown])

    assert result.decision.status == "BLOCKED"
    assert "unknown_application_stack:opaque.apk" in result.decision.blockers
    assert "split_coherence_not_verified" in result.decision.blockers


def test_cache_integrity_status_separation_and_copy_materialization(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")

    object_dir = cache.store(result)
    manifest = cache.verify(result.artifact_digest)
    object_manifest_before = (object_dir / "manifest.json").read_bytes()
    status_path = cache.write_status(
        result.artifact_digest,
        "READY",
        pipeline_revision="pipeline-v1",
        detail="queued",
    )
    cache.write_status(result.artifact_digest, "COMPLETE", pipeline_revision="pipeline-v1")

    assert status_path.parent == cache.root / "status" / "pipeline-v1"
    assert json.loads(status_path.read_text(encoding="utf-8"))["status"] == "COMPLETE"
    assert (object_dir / "manifest.json").read_bytes() == object_manifest_before
    assert "status" not in manifest

    materialized = cache.materialize(result.artifact_digest, tmp_path / "materialized")
    stored_name = manifest["members"][0]["stored_name"]
    cached_member = object_dir / "members" / stored_name
    copied_member = materialized / stored_name
    assert copied_member.read_bytes() == cached_member.read_bytes()
    assert (cached_member.stat().st_dev, cached_member.stat().st_ino) != (
        copied_member.stat().st_dev,
        copied_member.stat().st_ino,
    )
    assert (materialized / "MATERIALIZED.COMPLETE").is_file()


def test_cache_detects_member_corruption(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")
    object_dir = cache.store(result)
    manifest = cache.verify(result.artifact_digest)
    stored_name = manifest["members"][0]["stored_name"]
    (object_dir / "members" / stored_name).write_bytes(b"corrupt")

    with pytest.raises(CacheIntegrityError, match="size or type mismatch"):
        cache.verify(result.artifact_digest)


def test_cache_rejects_sealed_manifest_without_apk_members(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")
    object_dir = cache.store(result)
    manifest = json.loads((object_dir / "manifest.json").read_bytes())
    manifest["members"] = []
    manifest_bytes = legacy_preflight._canonical_json(manifest)
    (object_dir / "manifest.json").write_bytes(manifest_bytes)
    (object_dir / "OBJECT.COMPLETE").write_text(
        f"{hashlib.sha256(manifest_bytes).hexdigest()}  manifest.json\n",
        encoding="utf-8",
    )
    for member in (object_dir / "members").iterdir():
        member.unlink()

    with pytest.raises(CacheIntegrityError, match="member manifest"):
        cache.verify(result.artifact_digest)


def test_cache_verify_bounds_manifest_member_count_before_hashing(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")
    object_dir = cache.store(result)
    manifest = json.loads((object_dir / "manifest.json").read_bytes())
    duplicate = dict(manifest["members"][0])
    duplicate["name"] = "second.apk"
    duplicate["stored_name"] = "second.apk"
    manifest["members"].append(duplicate)
    manifest_bytes = legacy_preflight._canonical_json(manifest)
    (object_dir / "manifest.json").write_bytes(manifest_bytes)
    (object_dir / "OBJECT.COMPLETE").write_text(
        f"{hashlib.sha256(manifest_bytes).hexdigest()}  manifest.json\n",
        encoding="utf-8",
    )
    limited = ArtifactCache(tmp_path / "cache", limits=PreflightLimits(max_archive_members=1))

    with pytest.raises(CacheIntegrityError, match="member count"):
        limited.verify(result.artifact_digest)


def test_cache_verify_bounds_aggregate_member_bytes_before_hashing(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")
    cache.store(result)
    limited = ArtifactCache(
        tmp_path / "cache",
        limits=PreflightLimits(max_archive_bytes=result.artifact_members[0].size - 1),
    )

    with pytest.raises(CacheIntegrityError, match="aggregate size"):
        limited.verify(result.artifact_digest)


def test_cache_object_is_published_by_atomic_directory_rename(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")
    original_rename = legacy_preflight._rename_noreplace_at
    publications: list[tuple[int, bytes, int, bytes]] = []

    def record_rename(
        source_dir_fd: int,
        source: bytes,
        destination_dir_fd: int,
        destination: bytes,
    ) -> None:
        publications.append((source_dir_fd, source, destination_dir_fd, destination))
        original_rename(source_dir_fd, source, destination_dir_fd, destination)

    monkeypatch.setattr(legacy_preflight, "_rename_noreplace_at", record_rename)

    object_dir = cache.store(result)

    [(source_fd, temporary, destination_fd, published)] = publications
    assert source_fd == destination_fd
    assert source_fd != legacy_preflight._AT_FDCWD
    assert os.fsdecode(temporary).startswith(f".{result.artifact_digest}.tmp-")
    assert os.fsdecode(published) == result.artifact_digest
    assert (object_dir / "OBJECT.COMPLETE").is_file()


def test_cache_store_rejects_replaced_object_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")
    schema_objects = cache.root / "objects" / legacy_preflight.CACHE_SCHEMA
    displaced = cache.root / "objects" / "displaced"
    outside = tmp_path / "outside"
    outside.mkdir()
    original_create = legacy_preflight._make_private_directory_at

    def replace_parent(directory_fd: int, prefix: str) -> str:
        schema_objects.rename(displaced)
        schema_objects.symlink_to(outside, target_is_directory=True)
        return original_create(directory_fd, prefix)

    monkeypatch.setattr(legacy_preflight, "_make_private_directory_at", replace_parent)

    with pytest.raises(SafetyError, match="cache object directory changed"):
        cache.store(result)

    assert not (outside / result.artifact_digest).exists()
    assert list(displaced.iterdir()) == []


def test_cache_rejects_inconsistent_artifact_identity_before_publication(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    inconsistent = replace(result, artifact_digest="0" * 64)
    cache = ArtifactCache(tmp_path / "cache")

    with pytest.raises(PreflightError, match="artifact digest does not match"):
        cache.store(inconsistent)

    assert not cache.root.exists()


def test_preflight_derives_everything_from_one_sealed_source_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    original_open = legacy_preflight.os.open
    source_opens = 0

    def count_source_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal source_opens
        if os.fsdecode(path) == os.fspath(artifact):
            source_opens += 1
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(legacy_preflight.os, "open", count_source_open)

    result = preflight_delivery([artifact])

    assert source_opens == 1
    assert result.delivery_files[0].sha256 == result.artifact_members[0].sha256


def test_cache_object_is_independent_of_classification(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    altered = replace(
        result,
        decision=StackDecision(
            stacks=("future_stack",),
            routes=("future-route",),
            status="BLOCKED",
            blockers=("future_gate",),
            members=result.decision.members,
        ),
    )
    cache = ArtifactCache(tmp_path / "cache")

    first = cache.store(result)
    manifest_before = (first / "manifest.json").read_bytes()
    second = cache.store(altered)

    assert second == first
    assert (first / "manifest.json").read_bytes() == manifest_before
    assert "classification" not in cache.verify(result.artifact_digest)
    assert first.parent.name == legacy_preflight.CACHE_SCHEMA


def test_status_requires_object_and_enforces_terminal_transitions(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")

    with pytest.raises(CacheIntegrityError, match="missing"):
        cache.write_status(result.artifact_digest, "READY", pipeline_revision="pipeline-v1")

    cache.store(result)
    with pytest.raises(PreflightError, match="transition"):
        cache.write_status(result.artifact_digest, "COMPLETE", pipeline_revision="pipeline-v1")
    cache.write_status(result.artifact_digest, "READY", pipeline_revision="pipeline-v1")
    cache.write_status(result.artifact_digest, "COMPLETE", pipeline_revision="pipeline-v1")
    with pytest.raises(PreflightError, match="transition"):
        cache.write_status(result.artifact_digest, "READY", pipeline_revision="pipeline-v1")
    with pytest.raises(PreflightError, match="transition"):
        cache.write_status(result.artifact_digest, "COMPLETE", pipeline_revision="pipeline-v1")

    second = cache.write_status(result.artifact_digest, "READY", pipeline_revision="pipeline-v2")
    assert second.parent.name == "pipeline-v2"

    cache.write_status(result.artifact_digest, "BLOCKED", pipeline_revision="pipeline-v3")
    cache.write_status(result.artifact_digest, "READY", pipeline_revision="pipeline-v3")
    cache.write_status(result.artifact_digest, "FAILED", pipeline_revision="pipeline-v3")
    with pytest.raises(PreflightError, match="transition"):
        cache.write_status(result.artifact_digest, "READY", pipeline_revision="pipeline-v3")


def test_status_write_stays_in_pinned_root_during_path_replacement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")
    cache.store(result)
    status_root = cache.root / "status"
    displaced_root = cache.root / "status-displaced"
    outside_root = tmp_path / "outside-status"
    revision = "pipeline-v1"
    (outside_root / revision).mkdir(parents=True)
    original_open = legacy_preflight.os.open
    replaced = False

    def replace_after_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        descriptor = original_open(path, flags, mode, dir_fd=dir_fd)
        if not replaced and dir_fd is None and Path(path) == status_root:
            replaced = True
            status_root.rename(displaced_root)
            status_root.symlink_to(outside_root, target_is_directory=True)
        return descriptor

    monkeypatch.setattr(legacy_preflight.os, "open", replace_after_open)

    cache.write_status(result.artifact_digest, "READY", pipeline_revision=revision)

    target_name = f"{result.artifact_digest}.json"
    assert (displaced_root / revision / target_name).is_file()
    assert not (outside_root / revision / target_name).exists()


def test_preflight_rejects_delivery_compressed_size_before_read(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)

    with pytest.raises(SafetyError, match="compressed delivery size limit"):
        preflight_delivery(
            [artifact],
            limits=PreflightLimits(max_delivery_file_bytes=artifact.stat().st_size - 1),
        )


def test_preflight_applies_artifact_member_limit_to_direct_apk(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)

    with pytest.raises(SafetyError, match="artifact member size limit"):
        preflight_delivery(
            [artifact],
            limits=PreflightLimits(max_member_bytes=artifact.stat().st_size - 1),
        )


def test_preflight_rejects_archive_compressed_total_before_expansion(tmp_path: Path) -> None:
    inner = tmp_path / "base.apk"
    _native_apk(inner)
    delivery = tmp_path / "delivery.xapk"
    with zipfile.ZipFile(delivery, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("base.apk", inner.read_bytes())

    with pytest.raises(SafetyError, match="archive compressed-size limit"):
        preflight_delivery(
            [delivery],
            limits=PreflightLimits(max_archive_compressed_bytes=1),
        )


def test_zip_member_limit_is_checked_before_zipfile_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)

    def reject_constructor(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ZipFile constructor must not run")

    monkeypatch.setattr(legacy_preflight.zipfile, "ZipFile", reject_constructor)

    with pytest.raises(SafetyError, match="invalid APK member"):
        preflight_delivery([artifact], limits=PreflightLimits(max_archive_members=0))


def test_zip_preflight_rejects_an_understated_central_directory_entry_count(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    payload = bytearray(artifact.read_bytes())
    eocd = payload.rfind(b"PK\x05\x06")
    assert eocd >= 0
    payload[eocd + 8 : eocd + 12] = (0).to_bytes(4, "little")
    artifact.write_bytes(payload)

    with (
        pytest.raises(SafetyError, match="central-directory entry count"),
        legacy_preflight._open_zip_path(artifact),
    ):
        pass


def test_preflight_does_not_change_source_access_time(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    node = artifact.stat()
    old_atime = 1_600_000_000_000_000_000
    os.utime(artifact, ns=(old_atime, node.st_mtime_ns))

    result = preflight_delivery([artifact])

    assert result.decision.status == "BLOCKED"
    assert artifact.stat().st_atime_ns == old_atime


def test_cache_verify_rejects_symlink_member_without_following(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")
    object_dir = cache.store(result)
    manifest = cache.verify(result.artifact_digest)
    member = object_dir / "members" / manifest["members"][0]["stored_name"]
    external = tmp_path / "external.apk"
    external.write_bytes(member.read_bytes())
    member.unlink()
    member.symlink_to(external)

    with pytest.raises(CacheIntegrityError, match="missing or unsafe"):
        cache.verify(result.artifact_digest)


def test_cache_verify_rechecks_exact_membership_after_hashing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")
    object_dir = cache.store(result)
    original_hash = legacy_preflight._hash_fd_exact
    injected = False

    def inject_member(descriptor: int, expected_size: int) -> tuple[str, int]:
        nonlocal injected
        if not injected:
            injected = True
            (object_dir / "members" / "unexpected.apk").write_bytes(b"unexpected")
        return original_hash(descriptor, expected_size)

    monkeypatch.setattr(legacy_preflight, "_hash_fd_exact", inject_member)

    with pytest.raises(CacheIntegrityError, match="changed while verifying"):
        cache.verify(result.artifact_digest)


def test_cache_directory_enumeration_stops_after_first_unexpected_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = iter(
        type("Entry", (), {"name": name})()
        for name in ("OBJECT.COMPLETE", "manifest.json", "members", "unexpected", "unread")
    )
    monkeypatch.setattr(legacy_preflight.os, "scandir", lambda _fd: nullcontext(entries))

    assert not legacy_preflight._directory_names_match(
        1, {"OBJECT.COMPLETE", "manifest.json", "members"}
    )
    assert next(entries).name == "unread"


def test_cache_verify_rechecks_membership_after_logical_digest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")
    object_dir = cache.store(result)
    original_digest = legacy_preflight._digest_manifest

    def inject_after_digest(domain: str, items: Sequence[Mapping[str, object]]) -> str:
        digest = original_digest(domain, items)
        if domain == "artifact":
            (object_dir / "members" / "late-extra.apk").write_bytes(b"late")
        return digest

    monkeypatch.setattr(legacy_preflight, "_digest_manifest", inject_after_digest)

    with pytest.raises(CacheIntegrityError, match="changed while verifying"):
        cache.verify(result.artifact_digest)


def test_deep_cache_manifest_is_rejected_without_recursion_crash(tmp_path: Path) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")
    object_dir = cache.store(result)
    hostile = b"[" * 100_000 + b"0" + b"]" * 100_000
    (object_dir / "manifest.json").write_bytes(hostile)
    digest = hashlib.sha256(hostile).hexdigest()
    (object_dir / "OBJECT.COMPLETE").write_text(f"{digest}  manifest.json\n", encoding="utf-8")

    with pytest.raises(CacheIntegrityError, match="manifest is invalid"):
        cache.verify(result.artifact_digest)


def test_materialization_is_built_privately_then_atomically_published(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")
    cache.store(result)
    destination = tmp_path / "materialized"
    original_publish = legacy_preflight._rename_noreplace_at
    observations: list[tuple[bool, bool]] = []

    def inspect_publish(
        source_dir_fd: int,
        source: bytes,
        destination_dir_fd: int,
        target: bytes,
    ) -> None:
        try:
            os.stat(target, dir_fd=destination_dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            target_exists = False
        else:
            target_exists = True
        source_fd = os.open(source, legacy_preflight._DIRECTORY_FLAGS, dir_fd=source_dir_fd)
        try:
            marker = os.stat("MATERIALIZED.COMPLETE", dir_fd=source_fd)
        finally:
            os.close(source_fd)
        observations.append((target_exists, stat.S_ISREG(marker.st_mode)))
        original_publish(source_dir_fd, source, destination_dir_fd, target)

    monkeypatch.setattr(legacy_preflight, "_rename_noreplace_at", inspect_publish)

    cache.materialize(result.artifact_digest, destination)

    assert observations == [(False, True)]
    assert (destination / "MATERIALIZED.COMPLETE").is_file()


def test_materialization_stays_in_pinned_parent_after_path_is_replaced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "base.apk"
    _native_apk(artifact)
    result = preflight_delivery([artifact])
    cache = ArtifactCache(tmp_path / "cache")
    cache.store(result)
    parent = tmp_path / "output"
    parent.mkdir()
    moved_parent = tmp_path / "moved-output"
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    destination = parent / "materialized"
    original_create = legacy_preflight._make_private_directory_at

    def replace_parent(directory_fd: int, prefix: str) -> str:
        parent.rename(moved_parent)
        parent.symlink_to(replacement, target_is_directory=True)
        return original_create(directory_fd, prefix)

    monkeypatch.setattr(legacy_preflight, "_make_private_directory_at", replace_parent)

    cache.materialize(result.artifact_digest, destination)

    assert (moved_parent / "materialized" / "MATERIALIZED.COMPLETE").is_file()
    assert not (replacement / "materialized").exists()
