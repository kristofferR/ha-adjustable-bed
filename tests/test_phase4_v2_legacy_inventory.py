"""Tests for the non-destructive Phase 4 legacy inventory."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pytest

import tools.phase4_v2.legacy_inventory as legacy_inventory
from tools.phase4_v2.legacy_inventory import (
    InventoryError,
    SourceTreeChangedError,
    build_inventory,
    capture_tree_snapshot,
    verify_unchanged,
)


@dataclass(frozen=True, slots=True)
class _Node:
    path: str
    kind: str
    mode: int
    size: int
    mtime_ns: int
    digest_or_target: str | None


def _walk_without_following(root: Path) -> Iterator[Path]:
    yield root
    for directory, names, filenames in os.walk(root, followlinks=False):
        names.sort()
        filenames.sort()
        base = Path(directory)
        yield from (base / name for name in names)
        yield from (base / name for name in filenames)


def _snapshot(root: Path) -> tuple[_Node, ...]:
    nodes: list[_Node] = []
    for path in _walk_without_following(root):
        node_stat = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        if stat.S_ISREG(node_stat.st_mode):
            detail = hashlib.sha256(path.read_bytes()).hexdigest()
            kind = "file"
        elif stat.S_ISLNK(node_stat.st_mode):
            detail = os.readlink(path)
            kind = "symlink"
        elif stat.S_ISDIR(node_stat.st_mode):
            detail = None
            kind = "directory"
        elif stat.S_ISFIFO(node_stat.st_mode):
            detail = None
            kind = "fifo"
        else:
            detail = None
            kind = "other"
        nodes.append(
            _Node(
                path=relative,
                kind=kind,
                mode=stat.S_IMODE(node_stat.st_mode),
                size=node_stat.st_size,
                mtime_ns=node_stat.st_mtime_ns,
                digest_or_target=detail,
            )
        )
    return tuple(sorted(nodes, key=lambda node: node.path))


def _write_report(
    path: Path,
    *,
    status: str = "COMPLETE",
    package_id: str = "example.fixture",
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_revision": "fixture-v1",
                "status": status,
                "artifact": {
                    "package_id": package_id,
                    "version_name": "1.0",
                    "version_code": "1",
                    "artifact_set_sha256": "a" * 64,
                },
            }
        ),
        encoding="utf-8",
    )


def _fixture_tree(root: Path) -> None:
    report = root / "example.fixture-1.0-20260831" / "report"
    work = report.parent / "work"
    active = root / "phase4b-odd-clusters-2026-08-30" / "cluster-011"
    report.mkdir(parents=True)
    work.mkdir()
    active.mkdir(parents=True)
    _write_report(report / "analysis.json")
    report_digest = hashlib.sha256((report / "analysis.json").read_bytes()).hexdigest()
    (report / "REPORT.SHA256").write_text(
        f"{report_digest}  report/analysis.json\nmalformed legacy line\n", encoding="utf-8"
    )
    (work / "empty").write_bytes(b"")
    (work / ".hidden").write_text("preserved", encoding="utf-8")
    (active / "draft.txt").write_text("still active", encoding="utf-8")
    (root / "z-last").mkdir()
    (root / "MixedCase").mkdir()
    (root / "unicodé").mkdir()
    os.symlink("missing-target", work / "broken-link")


def _ndjson(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_inventory_is_deterministic_and_read_only(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    _fixture_tree(source)
    before = _snapshot(source)

    first = tmp_path / "inventory-a"
    second = tmp_path / "inventory-b"
    active = Path("phase4b-odd-clusters-2026-08-30/cluster-011")
    build_inventory(source, first, active_paths=[active])
    assert _snapshot(source) == before
    build_inventory(source, second, active_paths=[active])
    assert _snapshot(source) == before

    for name in (
        "manifest.json",
        "entries.ndjson",
        "declared_hashes.ndjson",
        "reports.ndjson",
        "diagnostics.ndjson",
        "SUMMARY.md",
    ):
        assert (first / name).read_bytes() == (second / name).read_bytes()

    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["non_mutation_audit"]["stable_unchanged"] is True
    assert manifest["counts"]["report_statuses"] == {"COMPLETE": 1}
    assert manifest["counts"]["declared_hashes"] == 1
    assert manifest["counts"]["diagnostics"] == 1
    assert (first / "INVENTORY.COMPLETE").is_file()
    for name, integrity in manifest["payload_integrity"].items():
        payload = first / name
        assert payload.stat().st_size == integrity["bytes"]
        assert hashlib.sha256(payload.read_bytes()).hexdigest() == integrity["sha256"]
    workspaces = _ndjson(first / "workspaces.ndjson")
    fixture_workspace = next(
        workspace for workspace in workspaces if workspace["path"] == "example.fixture-1.0-20260831"
    )
    assert fixture_workspace["package_ids"] == ["example.fixture"]
    entries = _ndjson(first / "entries.ndjson")
    fixture_entry = next(
        entry for entry in entries if entry["path"] == "example.fixture-1.0-20260831/work/.hidden"
    )
    assert fixture_entry["package_ids"] == ["example.fixture"]


def test_inventory_has_deterministic_dfs_order_and_does_not_follow_symlinks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    _fixture_tree(source)
    external = tmp_path / "external"
    external.mkdir()
    (external / "secret").write_text("outside", encoding="utf-8")
    os.symlink(external, source / "external-directory-link")
    os.symlink(".", source / "cycle")
    (source / "a").mkdir()
    (source / "a" / "z").write_text("nested", encoding="utf-8")
    (source / "a.txt").write_text("sibling", encoding="utf-8")

    output = tmp_path / "inventory"
    build_inventory(source, output)
    entries = _ndjson(output / "entries.ndjson")
    paths = [str(entry["path"]) for entry in entries]
    assert paths.index("a") < paths.index("a/z") < paths.index("a.txt")
    assert "external-directory-link/secret" not in paths
    assert "cycle/cycle" not in paths
    external_link = next(entry for entry in entries if entry["path"] == "external-directory-link")
    assert external_link["kind"] == "symlink"
    assert external_link["link_target"] == str(external)


def test_inventory_does_not_follow_directory_replaced_after_stat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "legacy"
    victim = source / "victim"
    victim.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    (external / "secret").write_text("outside", encoding="utf-8")
    original_open = os.open
    replaced = False

    def replace_before_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if path == "victim" and dir_fd is not None and not replaced:
            replaced = True
            victim.rmdir()
            victim.symlink_to(external, target_is_directory=True)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", replace_before_open)
    diagnostics: list[legacy_inventory.Diagnostic] = []
    entries = list(
        legacy_inventory._walk(
            source,
            (legacy_inventory.PurePosixPath("victim"),),
            diagnostics,
        )
    )

    assert replaced is True
    assert "victim/secret" not in {entry.path for entry, _path in entries}
    assert any(item.path == "victim" and item.operation == "scandir" for item in diagnostics)


def test_inventory_records_fifo_without_opening_it(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    os.mkfifo(source / "unreadable-stream")

    output = tmp_path / "inventory"
    build_inventory(source, output)
    entries = _ndjson(output / "entries.ndjson")
    fifo = next(entry for entry in entries if entry["path"] == "unreadable-stream")
    assert fifo["kind"] == "fifo"


@pytest.mark.parametrize("target", ["direct", "nested", "through-link"])
def test_inventory_refuses_outputs_inside_source(tmp_path: Path, target: str) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    sentinel = source / "sentinel"
    sentinel.write_text("untouched", encoding="utf-8")
    if target == "direct":
        output = source / "inventory"
    elif target == "nested":
        (source / "nested").mkdir()
        output = source / "nested" / "inventory"
    else:
        alias = tmp_path / "alias"
        os.symlink(source, alias)
        output = alias / "inventory"

    before = _snapshot(source)
    with pytest.raises(InventoryError, match="outside the source tree"):
        build_inventory(source, output)
    assert _snapshot(source) == before
    assert sentinel.read_text(encoding="utf-8") == "untouched"


def test_inventory_records_active_status_and_malformed_history(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    _fixture_tree(source)
    rejected = source / "example.fixture-1.0-rejected" / "report"
    rejected.mkdir(parents=True)
    (rejected / "analysis.json").write_text("{not json", encoding="utf-8")
    active = Path("phase4b-odd-clusters-2026-08-30/cluster-011")

    output = tmp_path / "inventory"
    build_inventory(source, output, active_paths=[active])

    entries = _ndjson(output / "entries.ndjson")
    active_entries = [
        entry for entry in entries if str(entry["path"]).startswith(active.as_posix())
    ]
    assert active_entries
    assert all(entry["active_protected"] is True for entry in active_entries)
    rejected_report = next(
        entry
        for entry in entries
        if entry["path"] == "example.fixture-1.0-rejected/report/analysis.json"
    )
    assert "rejected" in rejected_report["roles"]
    diagnostics = _ndjson(output / "diagnostics.ndjson")
    assert any(item["operation"] == "parse_analysis_json" for item in diagnostics)
    assert (rejected / "analysis.json").read_text(encoding="utf-8") == "{not json"


def test_inventory_bounds_analysis_report_metadata_parsing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "legacy"
    report = source / "example.fixture-1.0" / "report"
    report.mkdir(parents=True)
    (report / "analysis.json").write_text('{"status":"COMPLETE"}', encoding="utf-8")
    monkeypatch.setattr(legacy_inventory, "_MAX_ANALYSIS_JSON_BYTES", 1)

    output = tmp_path / "inventory"
    build_inventory(source, output)

    diagnostics = _ndjson(output / "diagnostics.ndjson")
    assert any(item["operation"] == "parse_analysis_json" for item in diagnostics)


def test_inventory_rejects_duplicate_analysis_metadata_keys(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    (source / "analysis.json").write_text(
        '{"status":"COMPLETE","status":"BLOCKED"}', encoding="utf-8"
    )

    output = tmp_path / "inventory"
    build_inventory(source, output)

    assert _ndjson(output / "reports.ndjson") == []
    diagnostics = _ndjson(output / "diagnostics.ndjson")
    assert any(
        item["operation"] == "parse_analysis_json" and item["error"] == "ValueError"
        for item in diagnostics
    )


def test_inventory_retains_analysis_metadata_on_parser_recursion_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    _write_report(source / "analysis.json")

    def excessively_nested(*_args: object) -> legacy_inventory.ReportRecord:
        raise RecursionError

    monkeypatch.setattr(legacy_inventory, "_report_record", excessively_nested)

    output = tmp_path / "inventory"
    build_inventory(source, output)

    assert _ndjson(output / "reports.ndjson") == []
    diagnostics = _ndjson(output / "diagnostics.ndjson")
    assert any(
        item["operation"] == "parse_analysis_json" and item["error"] == "RecursionError"
        for item in diagnostics
    )


def test_inventory_bounds_tree_entries_before_sorting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    for name in ("one", "two", "three"):
        (source / name).write_text(name, encoding="utf-8")
    monkeypatch.setattr(legacy_inventory, "_MAX_TREE_ENTRIES", 2)

    output = tmp_path / "inventory"
    build_inventory(source, output)

    assert (output / "INVENTORY.PARTIAL").is_file()
    assert len(_ndjson(output / "entries.ndjson")) == 2
    diagnostics = _ndjson(output / "diagnostics.ndjson")
    assert any(item["error"] == "entry_limit_exceeded" for item in diagnostics)


def test_inventory_rejects_oversized_hash_manifests_before_reading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "legacy"
    report = source / "example.fixture-1.0" / "report"
    report.mkdir(parents=True)
    (report / "REPORT.SHA256").write_text(f"{'0' * 64}  evidence.bin\n", encoding="utf-8")
    monkeypatch.setattr(legacy_inventory, "_MAX_HASH_MANIFEST_BYTES", 1)

    output = tmp_path / "inventory"
    build_inventory(source, output)

    diagnostics = _ndjson(output / "diagnostics.ndjson")
    assert any(
        item["operation"] == "read_declared_hashes" and item["error"] == "manifest_too_large"
        for item in diagnostics
    )


def test_inventory_bounds_hash_manifest_diagnostics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    (source / "REPORT.SHA256").write_text("invalid\n" * 10, encoding="utf-8")
    monkeypatch.setattr(legacy_inventory, "_MAX_HASH_MANIFEST_DIAGNOSTICS", 3)

    output = tmp_path / "inventory"
    build_inventory(source, output)

    diagnostics = _ndjson(output / "diagnostics.ndjson")
    hash_diagnostics = [
        item for item in diagnostics if item["operation"].startswith("parse_declared_hash")
    ]
    assert [item["error"] for item in hash_diagnostics] == [
        "unrecognised_format",
        "unrecognised_format",
        "diagnostic_limit_exceeded",
    ]


def test_inventory_bounds_hash_manifest_declarations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    (source / "REPORT.SHA256").write_text(f"{'0' * 64}\n" * 10, encoding="utf-8")
    monkeypatch.setattr(legacy_inventory, "_MAX_HASH_MANIFEST_DECLARATIONS", 3)

    output = tmp_path / "inventory"
    build_inventory(source, output)

    assert len(_ndjson(output / "declared_hashes.ndjson")) == 3
    diagnostics = _ndjson(output / "diagnostics.ndjson")
    assert any(item["error"] == "declaration_limit_exceeded" for item in diagnostics)


def test_inventory_marks_unreadable_metadata_as_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    _write_report(source / "analysis.json")

    def unreadable(*_args: object) -> legacy_inventory.ReportRecord:
        raise PermissionError

    monkeypatch.setattr(legacy_inventory, "_report_record", unreadable)

    output = tmp_path / "inventory"
    build_inventory(source, output)

    assert (output / "INVENTORY.PARTIAL").is_file()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["coverage"]["opaque_path_list"] == ["analysis.json"]


def test_inventory_marks_disappeared_metadata_as_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    _write_report(source / "analysis.json")

    def disappeared(*_args: object) -> legacy_inventory.ReportRecord:
        raise FileNotFoundError

    monkeypatch.setattr(legacy_inventory, "_report_record", disappeared)

    output = tmp_path / "inventory"
    build_inventory(source, output)

    assert (output / "INVENTORY.PARTIAL").is_file()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["coverage"]["opaque_path_list"] == ["analysis.json"]


def test_inventory_syncs_payloads_before_completion_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    (temporary / "payload.json").write_text("payload", encoding="utf-8")
    (temporary / "INVENTORY.COMPLETE").write_text("complete", encoding="utf-8")
    destination = tmp_path / "destination"
    synced: list[str] = []

    monkeypatch.setattr(
        legacy_inventory,
        "_fsync_path",
        lambda path: synced.append(f"file:{path.name}"),
    )
    monkeypatch.setattr(
        legacy_inventory,
        "_fsync_directory",
        lambda path: synced.append(f"directory:{path.name}"),
    )
    monkeypatch.setattr(
        legacy_inventory.os,
        "fsync",
        lambda _descriptor: synced.append("directory:destination"),
    )

    legacy_inventory._publish_without_replace(temporary, destination)

    assert synced == [
        "file:payload.json",
        "directory:destination",
        "file:INVENTORY.COMPLETE",
        "directory:destination",
        f"directory:{tmp_path.name}",
    ]


def test_inventory_publication_does_not_follow_replaced_destination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    (temporary / "payload.json").write_text("payload", encoding="utf-8")
    (temporary / "INVENTORY.COMPLETE").write_text("complete", encoding="utf-8")
    destination = tmp_path / "destination"
    displaced = tmp_path / "displaced"
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    original_rename = os.rename
    replaced = False

    def replace_before_rename(
        source: os.PathLike[str] | str,
        target: os.PathLike[str] | str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal replaced
        if not replaced:
            replaced = True
            original_rename(destination, displaced)
            destination.symlink_to(unrelated, target_is_directory=True)
        original_rename(
            source,
            target,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(legacy_inventory.os, "rename", replace_before_rename)

    with pytest.raises(InventoryError, match="changed during publication"):
        legacy_inventory._publish_without_replace(temporary, destination)

    assert list(unrelated.iterdir()) == []
    assert (displaced / "payload.json").is_file()
    assert not (displaced / "INVENTORY.COMPLETE").exists()


def test_hash_manifest_metadata_is_rechecked_after_parsing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    manifest = source / "REPORT.SHA256"
    manifest.write_text("invalid\n", encoding="utf-8")
    entry = legacy_inventory._entry_from_stat(
        PurePosixPath("REPORT.SHA256"), manifest.lstat(), None, ()
    )
    original_parse = legacy_inventory._parse_declared_hash_lines

    def mutate_after_parse(
        text: str,
        parsed_entry: legacy_inventory.Entry,
        parsed_path: Path,
        parsed_source_root: Path,
        digest_cache: dict[tuple[int, int, int, int, int], str],
    ) -> tuple[list[legacy_inventory.DeclaredHash], list[legacy_inventory.Diagnostic]]:
        result = original_parse(
            text,
            parsed_entry,
            parsed_path,
            parsed_source_root,
            digest_cache,
        )
        manifest.write_text("changed\n", encoding="utf-8")
        changed = manifest.stat()
        os.utime(manifest, ns=(changed.st_atime_ns, entry.mtime_ns + 1_000_000_000))
        return result

    monkeypatch.setattr(legacy_inventory, "_parse_declared_hash_lines", mutate_after_parse)

    declarations, diagnostics = legacy_inventory._declared_hashes(entry, manifest, source, {})

    assert declarations == []
    assert [item.error for item in diagnostics] == ["ObservedFileChangedError"]


def test_inventory_content_reads_preserve_source_access_times(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    report = source / "example.fixture-1.0" / "report"
    report.mkdir(parents=True)
    analysis = report / "analysis.json"
    _write_report(analysis)
    evidence = report / "evidence.bin"
    evidence.write_bytes(b"evidence")
    manifest = report / "REPORT.SHA256"
    manifest.write_text(
        f"{hashlib.sha256(evidence.read_bytes()).hexdigest()}  evidence.bin\n",
        encoding="utf-8",
    )
    observed = (analysis, evidence, manifest)
    old_atime = 1_600_000_000_000_000_000
    for path in observed:
        node = path.stat()
        os.utime(path, ns=(old_atime, node.st_mtime_ns))

    build_inventory(source, tmp_path / "inventory")

    assert {path.stat().st_atime_ns for path in observed} == {old_atime}


def test_snapshot_detects_same_size_content_change_with_restored_mtime(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    artifact = source / "artifact.bin"
    artifact.write_bytes(b"first")
    before = capture_tree_snapshot(source)
    original = artifact.stat()

    artifact.write_bytes(b"other")
    os.utime(artifact, ns=(original.st_atime_ns, original.st_mtime_ns))
    after = capture_tree_snapshot(source)

    with pytest.raises(SourceTreeChangedError):
        verify_unchanged(before, after)


def test_inventory_rejects_missing_active_path(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()

    with pytest.raises(InventoryError, match="active path does not exist"):
        build_inventory(source, tmp_path / "inventory", active_paths=["cluster-011-typo"])


def test_inventory_refuses_to_replace_existing_output(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    output = tmp_path / "inventory"
    output.mkdir()
    sentinel = output / "sentinel"
    sentinel.write_text("untouched", encoding="utf-8")

    with pytest.raises(InventoryError, match="already exists"):
        build_inventory(source, output)
    assert sentinel.read_text(encoding="utf-8") == "untouched"


def test_top_level_files_are_not_workspaces(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    (source / "root-seal.txt").write_text("seal", encoding="utf-8")
    (source / "actual-workspace").mkdir()

    output = tmp_path / "inventory"
    build_inventory(source, output)
    entries = _ndjson(output / "entries.ndjson")
    root_file = next(entry for entry in entries if entry["path"] == "root-seal.txt")
    assert root_file["workspace"] is None
    workspaces = _ndjson(output / "workspaces.ndjson")
    assert [workspace["path"] for workspace in workspaces] == ["actual-workspace"]


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses directory permission checks",
)
def test_inventory_reports_opaque_paths_without_chmod(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    opaque = source / "sealed"
    opaque.mkdir(parents=True)
    (opaque / "preserved.pyc").write_bytes(b"frozen")
    opaque.chmod(0o444)
    try:
        output = tmp_path / "inventory"
        result = build_inventory(source, output)
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["coverage"]["status"] == "OPAQUE_PATHS_RECORDED"
        assert manifest["coverage"]["opaque_paths"] >= 1
        assert (output / "INVENTORY.PARTIAL").is_file()
        assert not (output / "INVENTORY.COMPLETE").exists()
        assert result.coverage_status == "OPAQUE_PATHS_RECORDED"
        assert result.completion_marker == "INVENTORY.PARTIAL"
        diagnostics = _ndjson(output / "diagnostics.ndjson")
        assert any(item["path"].startswith("sealed") for item in diagnostics)
        assert stat.S_IMODE(opaque.stat().st_mode) == 0o444
    finally:
        opaque.chmod(0o755)


def test_active_changes_are_reported_separately(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "legacy"
    active = source / "cluster-011"
    active.mkdir(parents=True)
    draft = active / "draft"
    draft.write_text("one", encoding="utf-8")
    original_capture = legacy_inventory.capture_tree_snapshot

    def mutate_then_capture(
        source_root: Path, *, active_paths: list[str]
    ) -> legacy_inventory.TreeSnapshot:
        draft.write_text("changed", encoding="utf-8")
        return original_capture(source_root, active_paths=active_paths)

    monkeypatch.setattr(legacy_inventory, "capture_tree_snapshot", mutate_then_capture)
    output = tmp_path / "inventory"
    build_inventory(source, output, active_paths=["cluster-011"])
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    audit = manifest["non_mutation_audit"]
    assert audit["stable_unchanged"] is True
    assert audit["observed_unchanged"] is False
    assert audit["observed_result"] == "ACTIVE_PATHS_CHANGED"


def test_inventory_detects_hash_mismatch_missing_target_and_duplicate_reports(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    for workspace in ("run-a", "run-b"):
        report = source / workspace / "report"
        report.mkdir(parents=True)
        _write_report(report / "analysis.json")
    (source / "run-a" / "report" / "plain").write_text("not a directory", encoding="utf-8")
    (source / "run-a" / "report" / "REPORT.SHA256").write_text(
        f"{'0' * 64}  analysis.json\n{'1' * 64}  missing.json\n{'2' * 64}  plain/child\n",
        encoding="utf-8",
    )

    output = tmp_path / "inventory"
    build_inventory(source, output, active_paths=["run-a"])
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["duplicate_report_groups"] == 1
    assert manifest["counts"]["declared_hash_verification"] == {
        "filesystem_error:NotADirectoryError": 1,
        "mismatch": 1,
        "missing_target": 1,
    }
    duplicates = _ndjson(output / "duplicate_reports.ndjson")
    assert duplicates[0]["classification"] == "duplicate_identity_possible_stale_history"
    diagnostics = _ndjson(output / "diagnostics.ndjson")
    duplicate_diagnostics = {
        item["path"]: item
        for item in diagnostics
        if item["error"] == "possible_stale_history"
    }
    assert duplicate_diagnostics["run-a/report/analysis.json"]["active_protected"] is True
    assert duplicate_diagnostics["run-b/report/analysis.json"]["active_protected"] is False


def test_inventory_marks_unreadable_declared_hash_targets_as_opaque(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    (source / "target.bin").write_bytes(b"target")
    (source / "REPORT.SHA256").write_text(
        f"{'0' * 64}  target.bin\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        legacy_inventory,
        "_verify_declared_hash",
        lambda *_args: ("unreadable_target", None, None),
    )

    output = tmp_path / "inventory"
    build_inventory(source, output)

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["coverage"]["opaque_path_list"] == ["REPORT.SHA256"]
    assert (output / "INVENTORY.PARTIAL").is_file()
    assert not (output / "INVENTORY.COMPLETE").exists()


@pytest.mark.parametrize(
    ("limit_name", "manifest_lines", "expected_error"),
    [
        (
            "_MAX_HASH_MANIFEST_DECLARATIONS",
            [f"{'0' * 64}  first.bin", f"{'1' * 64}  second.bin"],
            "declaration_limit_exceeded",
        ),
        (
            "_MAX_HASH_MANIFEST_DIAGNOSTICS",
            ["invalid first line", "invalid second line"],
            "diagnostic_limit_exceeded",
        ),
    ],
)
def test_inventory_marks_truncated_hash_manifests_as_partial(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    limit_name: str,
    manifest_lines: list[str],
    expected_error: str,
) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    (source / "REPORT.SHA256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(legacy_inventory, limit_name, 1)

    output = tmp_path / "inventory"
    result = build_inventory(source, output)

    diagnostics = _ndjson(output / "diagnostics.ndjson")
    assert any(item["error"] == expected_error for item in diagnostics)
    assert result.completion_marker == "INVENTORY.PARTIAL"
    assert (output / "INVENTORY.PARTIAL").is_file()
    assert not (output / "INVENTORY.COMPLETE").exists()


def test_inventory_uses_nearest_package_subtree_for_cluster_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    cluster = source / "batch" / "cluster-011"
    for subtree, package_id in (("member-a", "pkg.a"), ("member-b", "pkg.b")):
        member = cluster / subtree
        report = member / "report"
        report.mkdir(parents=True)
        _write_report(report / "analysis.json", package_id=package_id)
        (member / "proof.txt").write_text(package_id, encoding="utf-8")
    (cluster / "shared-audit.txt").write_text("cluster-wide", encoding="utf-8")

    output = tmp_path / "inventory"
    build_inventory(source, output)
    entries = {entry["path"]: entry for entry in _ndjson(output / "entries.ndjson")}
    assert entries["batch/cluster-011/member-a/proof.txt"]["package_ids"] == ["pkg.a"]
    assert entries["batch/cluster-011/member-b/proof.txt"]["package_ids"] == ["pkg.b"]
    assert entries["batch/cluster-011/shared-audit.txt"]["package_ids"] == ["pkg.a", "pkg.b"]
