#!/usr/bin/env python3
"""Build a reproducible metadata inventory for local APK and XAPK archives."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, cast
from zipfile import BadZipFile, ZipFile

ARCHITECTURE_ALIASES = {
    "arm64_v8a": "arm64-v8a",
    "armeabi_v7a": "armeabi-v7a",
    "armeabi": "armeabi",
    "x86_64": "x86_64",
    "x86": "x86",
    "mips64": "mips64",
    "mips": "mips",
}

ARCHIVE_FIELDS = [
    "source_path",
    "archive_type",
    "file_size_bytes",
    "sha256",
    "status",
    "error",
    "warnings",
    "application_name",
    "package_id",
    "version_name",
    "version_code",
    "min_sdk_version",
    "target_sdk_version",
    "split_count",
    "splits",
    "architectures",
    "identical_file_count",
    "package_version_record_count",
    "package_version_distinct_file_count",
    "package_has_multiple_versions",
]

PACKAGE_FIELDS = [
    "package_id",
    "application_names",
    "archive_count",
    "distinct_file_count",
    "local_version_count",
    "versions",
    "latest_local_version_name",
    "latest_local_version_code",
    "archive_types",
    "architectures",
    "source_paths",
]


@dataclass
class AaptMetadata:
    """Metadata parsed from ``aapt dump badging``."""

    application_name: str = ""
    package_id: str = ""
    version_name: str = ""
    version_code: str = ""
    min_sdk_version: str = ""
    target_sdk_version: str = ""
    architectures: set[str] = field(default_factory=set)


class AaptError(RuntimeError):
    """An aapt failure that may still contain useful parsed metadata."""

    def __init__(self, detail: str, metadata: AaptMetadata) -> None:
        super().__init__(detail)
        self.metadata = metadata


@dataclass
class ArchiveRecord:
    """One row in the per-archive inventory."""

    source_path: str
    archive_type: str
    file_size_bytes: int
    sha256: str
    status: str = "ok"
    error: str = ""
    warnings: str = ""
    application_name: str = ""
    package_id: str = ""
    version_name: str = ""
    version_code: str = ""
    min_sdk_version: str = ""
    target_sdk_version: str = ""
    split_count: int = 0
    splits: str = ""
    architectures: str = ""
    identical_file_count: int = 1
    package_version_record_count: int = 0
    package_version_distinct_file_count: int = 0
    package_has_multiple_versions: bool = False


def parse_aapt_badging(output: str) -> AaptMetadata:
    """Parse the stable metadata fields from ``aapt dump badging`` output."""
    metadata = AaptMetadata()
    for line in output.splitlines():
        if line.startswith("package: "):
            attributes = dict(re.findall(r"([A-Za-z][A-Za-z0-9]*)='([^']*)'", line))
            metadata.package_id = attributes.get("name", "")
            metadata.version_name = attributes.get("versionName", "")
            metadata.version_code = attributes.get("versionCode", "")
        elif line.startswith("sdkVersion:"):
            metadata.min_sdk_version = _single_quoted_value(line)
        elif line.startswith("targetSdkVersion:"):
            metadata.target_sdk_version = _single_quoted_value(line)
        elif line.startswith("application-label:"):
            metadata.application_name = _single_quoted_value(line)
        elif line.startswith("native-code:"):
            metadata.architectures.update(re.findall(r"'([^']+)'", line))
    return metadata


def _single_quoted_value(line: str) -> str:
    _, separator, value = line.partition(":'")
    if not separator:
        return ""
    return value[:-1] if value.endswith("'") else value


def run_aapt(aapt: str, apk_path: Path) -> AaptMetadata:
    """Run aapt against an APK and return parsed metadata."""
    result = subprocess.run(
        [aapt, "dump", "badging", str(apk_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    metadata = parse_aapt_badging(result.stdout)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown aapt error"
        raise AaptError(f"aapt failed: {detail}", metadata)
    return metadata


def file_sha256(path: Path) -> str:
    """Hash an archive without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def source_path(path: Path, working_directory: Path) -> str:
    """Return a stable POSIX path, relative to the working directory when possible."""
    try:
        return path.resolve().relative_to(working_directory.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def inspect_apk(path: Path, aapt: str, working_directory: Path) -> ArchiveRecord:
    """Inspect a monolithic APK."""
    record = _base_record(path, "apk", working_directory)
    try:
        metadata = run_aapt(aapt, path)
        _apply_metadata(record, metadata)
        _finalize_status(record)
    except AaptError as err:
        _apply_metadata(record, err.metadata)
        record.status = "partial" if record.package_id else "error"
        if record.status == "partial":
            record.warnings = str(err)
            _finalize_status(record)
        else:
            record.error = str(err)
    except OSError as err:
        record.status = "error"
        record.error = str(err)
    return record


def inspect_xapk(path: Path, aapt: str, working_directory: Path) -> ArchiveRecord:
    """Inspect an XAPK container and its base split."""
    record = _base_record(path, "xapk", working_directory)
    warnings: list[str] = []
    try:
        with ZipFile(path) as archive:
            manifest = _read_xapk_manifest(archive, warnings)
            apk_members = sorted(
                name for name in archive.namelist() if name.lower().endswith(".apk")
            )
            split_entries = _split_entries(manifest, apk_members)
            record.split_count = len(apk_members)
            record.splits = "; ".join(split_entries)

            manifest_metadata = _manifest_metadata(manifest)
            architectures = set(manifest_metadata.architectures)
            architectures.update(_architectures_from_names(split_entries))

            base_member = _select_base_apk(manifest, apk_members)
            if not base_member:
                raise RuntimeError("XAPK contains no APK members")

            with tempfile.TemporaryDirectory(prefix="apk-inventory-") as temporary_directory:
                temporary_apk = Path(temporary_directory) / Path(base_member).name
                with archive.open(base_member) as source, temporary_apk.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                try:
                    apk_metadata = run_aapt(aapt, temporary_apk)
                except AaptError as err:
                    apk_metadata = err.metadata
                    record.status = "partial"
                    warnings.append(str(err))

            _compare_xapk_metadata(manifest_metadata, apk_metadata, warnings)
            _apply_metadata(record, _merge_metadata(apk_metadata, manifest_metadata))
            architectures.update(apk_metadata.architectures)
            record.architectures = "; ".join(sorted(architectures))
            record.warnings = "; ".join(warnings)
            _finalize_status(record)
    except BadZipFile:
        record.status = "error"
        record.error = "invalid ZIP container (missing or corrupt central directory)"
    except (OSError, RuntimeError, json.JSONDecodeError, KeyError) as err:
        record.status = "error"
        record.error = str(err)
    return record


def _base_record(path: Path, archive_type: str, working_directory: Path) -> ArchiveRecord:
    return ArchiveRecord(
        source_path=source_path(path, working_directory),
        archive_type=archive_type,
        file_size_bytes=path.stat().st_size,
        sha256=file_sha256(path),
    )


def _read_xapk_manifest(archive: ZipFile, warnings: list[str]) -> dict[str, Any]:
    manifest_members = [
        name for name in archive.namelist() if Path(name).name.lower() == "manifest.json"
    ]
    if not manifest_members:
        warnings.append("XAPK has no manifest.json")
        return {}
    manifest = json.loads(archive.read(manifest_members[0]).decode("utf-8-sig"))
    if not isinstance(manifest, dict):
        raise RuntimeError("XAPK manifest.json is not a JSON object")
    return cast(dict[str, Any], manifest)


def _split_entries(manifest: dict[str, Any], apk_members: list[str]) -> list[str]:
    entries: list[str] = []
    split_apks = manifest.get("split_apks") or []
    for split in split_apks:
        if isinstance(split, dict):
            split_id = str(split.get("id") or "")
            split_file = str(split.get("file") or "")
            entries.append(f"{split_id}={split_file}" if split_id else split_file)
        elif split:
            entries.append(str(split))
    return entries or apk_members


def _select_base_apk(manifest: dict[str, Any], apk_members: list[str]) -> str:
    by_name = {Path(name).name: name for name in apk_members}
    for split in manifest.get("split_apks") or []:
        if isinstance(split, dict) and str(split.get("id", "")).lower() == "base":
            candidate = str(split.get("file") or "")
            if candidate in apk_members:
                return candidate
            if candidate in by_name:
                return by_name[candidate]

    package_id = str(manifest.get("package_name") or "")
    candidates = ["base.apk", f"{package_id}.apk" if package_id else ""]
    for candidate in candidates:
        if candidate in by_name:
            return by_name[candidate]

    non_config = [
        name
        for name in apk_members
        if not Path(name).name.lower().startswith(("config.", "split_config."))
    ]
    if len(non_config) == 1:
        return non_config[0]
    if len(apk_members) == 1:
        return apk_members[0]
    return ""


def _manifest_metadata(manifest: dict[str, Any]) -> AaptMetadata:
    architectures = _architectures_from_names(
        [str(value) for value in manifest.get("split_configs") or []]
    )
    return AaptMetadata(
        application_name=str(manifest.get("name") or ""),
        package_id=str(manifest.get("package_name") or ""),
        version_name=str(manifest.get("version_name") or ""),
        version_code=str(manifest.get("version_code") or ""),
        min_sdk_version=str(manifest.get("min_sdk_version") or ""),
        target_sdk_version=str(manifest.get("target_sdk_version") or ""),
        architectures=architectures,
    )


def _architectures_from_names(values: list[str]) -> set[str]:
    architectures: set[str] = set()
    for value in values:
        normalized = value.lower().replace("-", "_")
        components = set(re.split(r"[.=/]", normalized))
        for token, architecture in ARCHITECTURE_ALIASES.items():
            if token in components:
                architectures.add(architecture)
    return architectures


def _compare_xapk_metadata(
    manifest: AaptMetadata, apk: AaptMetadata, warnings: list[str]
) -> None:
    comparisons = (
        ("package ID", manifest.package_id, apk.package_id),
        ("version name", manifest.version_name, apk.version_name),
        ("version code", manifest.version_code, apk.version_code),
    )
    for label, manifest_value, apk_value in comparisons:
        if manifest_value and apk_value and manifest_value != apk_value:
            warnings.append(
                f"manifest {label} {manifest_value!r} differs from base APK {apk_value!r}"
            )


def _merge_metadata(primary: AaptMetadata, fallback: AaptMetadata) -> AaptMetadata:
    return AaptMetadata(
        application_name=primary.application_name or fallback.application_name,
        package_id=primary.package_id or fallback.package_id,
        version_name=primary.version_name or fallback.version_name,
        version_code=primary.version_code or fallback.version_code,
        min_sdk_version=primary.min_sdk_version or fallback.min_sdk_version,
        target_sdk_version=primary.target_sdk_version or fallback.target_sdk_version,
        architectures=primary.architectures | fallback.architectures,
    )


def _apply_metadata(record: ArchiveRecord, metadata: AaptMetadata) -> None:
    record.application_name = metadata.application_name
    record.package_id = metadata.package_id
    record.version_name = metadata.version_name
    record.version_code = metadata.version_code
    record.min_sdk_version = metadata.min_sdk_version
    record.target_sdk_version = metadata.target_sdk_version
    record.architectures = "; ".join(sorted(metadata.architectures))


def _finalize_status(record: ArchiveRecord) -> None:
    if not record.min_sdk_version:
        record.min_sdk_version = "not declared"
    if not record.target_sdk_version:
        record.target_sdk_version = "not declared"
    missing = [
        label
        for label, value in (
            ("application name", record.application_name),
            ("package ID", record.package_id),
            ("version name", record.version_name),
            ("version code", record.version_code),
        )
        if not value
    ]
    if missing:
        record.status = "partial"
        detail = f"missing {', '.join(missing)}"
        record.warnings = "; ".join(filter(None, (record.warnings, detail)))


def discover_archives(root: Path) -> list[Path]:
    """Discover every APK/XAPK under root in stable path order."""
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".apk", ".xapk"}
        ),
        key=lambda path: path.as_posix().lower(),
    )


def annotate_groups(records: list[ArchiveRecord]) -> None:
    """Annotate exact duplicates and repeated package/version metadata."""
    by_hash: dict[str, list[ArchiveRecord]] = defaultdict(list)
    by_package_version: dict[tuple[str, str, str], list[ArchiveRecord]] = defaultdict(list)
    package_versions: dict[str, set[tuple[str, str]]] = defaultdict(set)

    for record in records:
        by_hash[record.sha256].append(record)
        if record.package_id and record.version_name and record.version_code:
            key = (record.package_id, record.version_name, record.version_code)
            by_package_version[key].append(record)
            package_versions[record.package_id].add((record.version_name, record.version_code))

    for record in records:
        record.identical_file_count = len(by_hash[record.sha256])
        if record.package_id and record.version_name and record.version_code:
            key = (record.package_id, record.version_name, record.version_code)
            group = by_package_version[key]
            record.package_version_record_count = len(group)
            record.package_version_distinct_file_count = len({item.sha256 for item in group})
            record.package_has_multiple_versions = len(package_versions[record.package_id]) > 1


def package_rows(records: list[ArchiveRecord]) -> list[dict[str, object]]:
    """Collapse archive rows into one normalized row per resolved package."""
    by_package: dict[str, list[ArchiveRecord]] = defaultdict(list)
    for record in records:
        if record.package_id:
            by_package[record.package_id].append(record)

    rows: list[dict[str, object]] = []
    for package_id, group in sorted(by_package.items()):
        versions = sorted(
            {(record.version_name, record.version_code) for record in group},
            key=lambda item: _version_code_sort_key(item[1]),
        )
        latest_name, latest_code = versions[-1]
        rows.append(
            {
                "package_id": package_id,
                "application_names": "; ".join(
                    sorted({record.application_name for record in group if record.application_name})
                ),
                "archive_count": len(group),
                "distinct_file_count": len({record.sha256 for record in group}),
                "local_version_count": len(versions),
                "versions": "; ".join(f"{name} ({code})" for name, code in versions),
                "latest_local_version_name": latest_name,
                "latest_local_version_code": latest_code,
                "archive_types": "; ".join(sorted({record.archive_type for record in group})),
                "architectures": "; ".join(
                    sorted(
                        {
                            architecture
                            for record in group
                            for architecture in record.architectures.split("; ")
                            if architecture
                        }
                    )
                ),
                "source_paths": "; ".join(record.source_path for record in group),
            }
        )
    return rows


def _version_code_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value.casefold())


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_readme(
    path: Path,
    inventory_date: str,
    apk_root: Path,
    records: list[ArchiveRecord],
    packages: list[dict[str, object]],
) -> None:
    """Write the human-readable audit summary."""
    by_hash: dict[str, list[ArchiveRecord]] = defaultdict(list)
    by_package_version: dict[tuple[str, str, str], list[ArchiveRecord]] = defaultdict(list)
    by_package: dict[str, list[ArchiveRecord]] = defaultdict(list)
    for record in records:
        by_hash[record.sha256].append(record)
        if record.package_id:
            by_package[record.package_id].append(record)
        if record.package_id and record.version_name and record.version_code:
            by_package_version[
                (record.package_id, record.version_name, record.version_code)
            ].append(record)

    duplicate_hashes = [group for group in by_hash.values() if len(group) > 1]
    repeated_versions = [group for group in by_package_version.values() if len(group) > 1]
    multiple_versions = {
        package_id: group
        for package_id, group in by_package.items()
        if len({(record.version_name, record.version_code) for record in group}) > 1
    }
    failures = [record for record in records if record.status != "ok"]
    distinct_package_versions = len(by_package_version)

    lines = [
        f"# Local APK inventory ({inventory_date})",
        "",
        "This is the step 1 baseline for the clean-room APK re-analysis in issue #436.",
        "It inventories the local corpus only; upstream latest-version discovery is step 2.",
        "",
        "## Artifacts",
        "",
        "- `archives.csv`: one row per local APK/XAPK archive, including embedded metadata, "
        "hashes, splits, architectures, duplicate annotations, warnings, and failures.",
        "- `packages.csv`: one normalized row per resolved package ID, including every local "
        "version and source path.",
        "",
        "## Method",
        "",
        "- APK package/version/SDK/application metadata comes from `aapt dump badging`.",
        "- XAPK container metadata comes from `manifest.json` and is cross-checked against "
        "the embedded base APK with `aapt`.",
        "- CPU architectures come from APK native-code metadata and XAPK split identifiers.",
        "  A blank architecture field means no native-code ABI or ABI split was declared.",
        "- An SDK value of `not declared` means the archive does not declare that field.",
        "- SHA-256 is calculated over each original archive.",
        "- Filenames are retained only as source paths and are never treated as metadata.",
        "- No archives were moved or deleted. All older versions remain preserved.",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Local archives accounted for | {len(records)} |",
        f"| APK archives | {sum(record.archive_type == 'apk' for record in records)} |",
        f"| XAPK archives | {sum(record.archive_type == 'xapk' for record in records)} |",
        f"| Resolved package IDs | {len(packages)} |",
        f"| Distinct package/version records | {distinct_package_versions} |",
        f"| Packages with multiple local versions | {len(multiple_versions)} |",
        f"| Exact duplicate SHA-256 groups | {len(duplicate_hashes)} |",
        f"| Repeated package/version groups | {len(repeated_versions)} |",
        f"| Complete metadata rows | {sum(record.status == 'ok' for record in records)} |",
        f"| Partial metadata rows | {sum(record.status == 'partial' for record in records)} |",
        f"| Extraction failures | {sum(record.status == 'error' for record in records)} |",
        "",
        "## Incomplete or failed extraction",
        "",
    ]
    if failures:
        lines.extend(["| Status | Source path | Detail |", "|---|---|---|"])
        for record in failures:
            detail = record.error or record.warnings
            lines.append(
                f"| {record.status} | `{_markdown(record.source_path)}` | "
                f"{_markdown(detail)} |"
            )
    else:
        lines.append("None.")

    lines.extend(["", "## Packages with multiple local versions", ""])
    if multiple_versions:
        lines.extend(["| Package | Versions |", "|---|---|"])
        for package_id, group in sorted(multiple_versions.items()):
            versions = sorted(
                {(record.version_name, record.version_code) for record in group},
                key=lambda item: _version_code_sort_key(item[1]),
            )
            text = "; ".join(f"{name} ({code})" for name, code in versions)
            lines.append(f"| `{_markdown(package_id)}` | {_markdown(text)} |")
    else:
        lines.append("None.")

    lines.extend(["", "## Exact duplicate files", ""])
    if duplicate_hashes:
        lines.extend(["| SHA-256 | Source paths |", "|---|---|"])
        for group in sorted(duplicate_hashes, key=lambda items: items[0].source_path):
            paths = "<br>".join(f"`{_markdown(item.source_path)}`" for item in group)
            lines.append(f"| `{group[0].sha256}` | {paths} |")
    else:
        lines.append("None.")

    lines.extend(["", "## Repeated package/version metadata", ""])
    if repeated_versions:
        lines.extend(["| Package/version | Archives | Distinct files |", "|---|---:|---:|"])
        for group in sorted(
            repeated_versions,
            key=lambda items: (
                items[0].package_id,
                _version_code_sort_key(items[0].version_code),
            ),
        ):
            identity = (
                f"`{_markdown(group[0].package_id)}` "
                f"{_markdown(group[0].version_name)} ({_markdown(group[0].version_code)})"
            )
            lines.append(f"| {identity} | {len(group)} | {len({item.sha256 for item in group})} |")
    else:
        lines.append("None.")

    root_display = source_path(apk_root, Path.cwd())
    lines.extend(
        [
            "",
            "## Reproduce",
            "",
            "Run from the repository root in WSL with `aapt` installed:",
            "",
            "```bash",
            f"python3 tools/apk_inventory.py {root_display} {path.parent.as_posix()} \\",
            f"  --inventory-date {inventory_date}",
            "```",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def build_inventory(
    apk_root: Path,
    output_directory: Path,
    inventory_date: str,
    aapt: str,
) -> list[ArchiveRecord]:
    """Inspect the corpus and write all inventory artifacts."""
    working_directory = Path.cwd()
    archives = discover_archives(apk_root)
    records = [
        inspect_xapk(path, aapt, working_directory)
        if path.suffix.lower() == ".xapk"
        else inspect_apk(path, aapt, working_directory)
        for path in archives
    ]
    if len(records) != len(archives):
        raise RuntimeError("inventory row count does not match discovered archive count")

    annotate_groups(records)
    packages = package_rows(records)
    archive_rows = [asdict(record) for record in records]
    write_csv(output_directory / "archives.csv", ARCHIVE_FIELDS, archive_rows)
    write_csv(output_directory / "packages.csv", PACKAGE_FIELDS, packages)
    write_readme(
        output_directory / "README.md",
        inventory_date,
        apk_root,
        records,
        packages,
    )
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk_root", type=Path, help="directory containing APK/XAPK files")
    parser.add_argument("output_directory", type=Path, help="directory for generated reports")
    parser.add_argument(
        "--inventory-date",
        default=date.today().isoformat(),
        help="date recorded in the report (default: today)",
    )
    parser.add_argument(
        "--aapt",
        default=shutil.which("aapt"),
        help="path to Android aapt (default: resolve from PATH)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.apk_root.is_dir():
        raise SystemExit(f"APK root does not exist: {args.apk_root}")
    if not args.aapt:
        raise SystemExit("aapt was not found; install it or pass --aapt")

    records = build_inventory(
        args.apk_root,
        args.output_directory,
        args.inventory_date,
        args.aapt,
    )
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        counts[record.status] += 1
    print(
        f"Inventoried {len(records)} archives: "
        f"{counts['ok']} complete, {counts['partial']} partial, {counts['error']} failed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
