#!/usr/bin/env python3
"""Acquire and verify the APK corpus selected by the latest-version audit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from zipfile import BadZipFile, ZipFile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.apk_inventory import (
    AaptError,
    _architectures_from_names,
    file_sha256,
    inspect_apk,
    inspect_xapk,
    run_aapt,
    source_path,
)

APKEEP_VERSION = "1.0.0"
APKEEP_RELEASE_URL = "https://github.com/EFForg/apkeep/releases/tag/1.0.0"
APKEEP_ASSET_SHA256 = "a23579a3ba366d25a6d69848189b983d65662f4ecf4b9e11e16510811659de4e"
APKEEP_SIGNING_FINGERPRINT = "1073E74EB38BD6D19476CBF8EA9DBF9FB761A677"

ACQUISITION_FIELDS = [
    "package_id",
    "scope",
    "selection",
    "status",
    "expected_version_name",
    "expected_version_code",
    "actual_version_name",
    "actual_version_code",
    "source",
    "source_url",
    "download_locator",
    "requested_architecture",
    "artifact_path",
    "artifact_type",
    "file_size_bytes",
    "sha256",
    "split_count",
    "splits",
    "architectures",
    "signature_status",
    "signer_certificate_sha256",
    "technology",
    "flutter_architectures",
    "flutter_arm64_status",
    "fallback_artifact_path",
    "fallback_version_name",
    "fallback_version_code",
    "fallback_architectures",
    "fallback_sha256",
    "detail",
    "cutoff_date",
]

FILE_FIELDS = [
    "package_id",
    "artifact_path",
    "member_path",
    "file_size_bytes",
    "sha256",
    "embedded_package_id",
    "package_version_name",
    "package_version_code",
    "architectures",
    "signature_status",
    "signer_certificate_sha256",
    "resource_entry_count",
    "native_library_count",
    "flutter_architectures",
    "error",
]

CERT_DIGEST_PATTERN = re.compile(r"certificate SHA-256 digest:\s*([0-9a-f:]+)", re.I)
FLUTTER_LIBRARY_PATTERN = re.compile(r"^lib/([^/]+)/libapp\.so$", re.I)


@dataclass(frozen=True)
class AcquisitionPlan:
    """One package selected for reuse, download, or a documented blocker."""

    package_id: str
    scope: str
    selection: str
    expected_version_name: str
    expected_version_code: str
    source: str
    source_url: str
    requested_architecture: str = ""
    variant_url: str = ""
    detail: str = ""


@dataclass
class MemberRecord:
    """Verification evidence for an APK or one embedded split APK."""

    package_id: str
    artifact_path: str
    member_path: str
    file_size_bytes: int
    sha256: str
    embedded_package_id: str = ""
    package_version_name: str = ""
    package_version_code: str = ""
    architectures: str = ""
    signature_status: str = ""
    signer_certificate_sha256: str = ""
    resource_entry_count: int = 0
    native_library_count: int = 0
    flutter_architectures: str = ""
    error: str = ""


@dataclass
class ArtifactInspection:
    """Normalized metadata and verification results for one selected artifact."""

    artifact_path: str
    artifact_type: str
    file_size_bytes: int
    sha256: str
    package_id: str = ""
    version_name: str = ""
    version_code: str = ""
    split_count: int = 0
    splits: str = ""
    architectures: str = ""
    signature_status: str = ""
    signer_certificate_sha256: str = ""
    technology: str = "native_or_managed"
    flutter_architectures: str = ""
    error: str = ""
    members: list[MemberRecord] = field(default_factory=list)


@dataclass
class AcquisitionRecord:
    """One row in the durable acquisition manifest."""

    package_id: str
    scope: str
    selection: str
    status: str
    expected_version_name: str
    expected_version_code: str
    source: str
    source_url: str
    cutoff_date: str
    actual_version_name: str = ""
    actual_version_code: str = ""
    download_locator: str = ""
    requested_architecture: str = ""
    artifact_path: str = ""
    artifact_type: str = ""
    file_size_bytes: int | str = ""
    sha256: str = ""
    split_count: int | str = ""
    splits: str = ""
    architectures: str = ""
    signature_status: str = ""
    signer_certificate_sha256: str = ""
    technology: str = ""
    flutter_architectures: str = ""
    flutter_arm64_status: str = ""
    fallback_artifact_path: str = ""
    fallback_version_name: str = ""
    fallback_version_code: str = ""
    fallback_architectures: str = ""
    fallback_sha256: str = ""
    detail: str = ""


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV into string dictionaries."""
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def load_apkpure(path: Path) -> dict[str, dict[str, object]]:
    """Load APKPure JSON records keyed by package ID."""
    records = json.loads(path.read_text(encoding="utf-8"))
    return {str(record["package_id"]): record for record in records}


def choose_apkpure_architecture(record: dict[str, object] | None) -> str:
    """Prefer arm64 when APKPure exposes a matching build."""
    if not record:
        return ""
    architectures = str(record.get("architectures") or "").lower()
    if "arm64-v8a" in architectures:
        return "arm64-v8a"
    values = [item.strip() for item in re.split(r"[;,]", architectures) if item.strip()]
    concrete = [item for item in values if item in {"armeabi-v7a", "armeabi", "x86", "x86_64"}]
    return concrete[0] if len(concrete) == 1 else ""


def choose_apkpure_variant_url(
    record: dict[str, object] | None, architecture: str
) -> str:
    """Return the exact APKPure artifact URL for an advertised architecture."""
    if not record or not architecture:
        return ""
    variants = record.get("variants") or []
    for variant in variants:
        if isinstance(variant, dict) and variant.get("architecture") == architecture:
            return str(variant.get("url") or "")
    return ""


def build_plans(
    latest_rows: list[dict[str, str]],
    discovery_rows: list[dict[str, str]],
    baseline_apkpure: dict[str, dict[str, object]],
    discovered_apkpure: dict[str, dict[str, object]],
) -> list[AcquisitionPlan]:
    """Select the newest source for every in-scope baseline and discovery package."""
    plans: list[AcquisitionPlan] = []
    for row in latest_rows:
        package_id = row["package_id"]
        if row["classification"] == "current":
            plans.append(
                AcquisitionPlan(
                    package_id=package_id,
                    scope="baseline",
                    selection="reuse_local",
                    expected_version_name=row["latest_version_name"],
                    expected_version_code=row["latest_version_code"],
                    source=row["latest_source"],
                    source_url=row["apkpure_url"] or row["play_url"],
                )
            )
        elif row["latest_source"].startswith("Google Play"):
            plans.append(
                AcquisitionPlan(
                    package_id=package_id,
                    scope="baseline",
                    selection="download_google_play",
                    expected_version_name=row["latest_version_name"],
                    expected_version_code="",
                    source="Google Play",
                    source_url=row["play_url"],
                    detail=row["blocker"],
                )
            )
        elif row["apkpure_status"] == "available":
            apk_record = baseline_apkpure.get(package_id)
            architecture = choose_apkpure_architecture(apk_record)
            plans.append(
                AcquisitionPlan(
                    package_id=package_id,
                    scope="baseline",
                    selection="download_apkpure",
                    expected_version_name=row["apkpure_version_name"],
                    expected_version_code=row["apkpure_version_code"],
                    source="APKPure",
                    source_url=row["apkpure_url"],
                    requested_architecture=architecture,
                    variant_url=choose_apkpure_variant_url(apk_record, architecture),
                )
            )
        else:
            plans.append(
                AcquisitionPlan(
                    package_id=package_id,
                    scope="baseline",
                    selection="blocked",
                    expected_version_name=row["latest_version_name"],
                    expected_version_code=row["latest_version_code"],
                    source=row["latest_source"],
                    source_url=row["apkpure_url"] or row["play_url"],
                    detail=row["blocker"] or "no downloadable current source",
                )
            )

    for row in discovery_rows:
        if row["relevance"] != "likely_bed_app":
            continue
        package_id = row["package_id"]
        use_apkpure = row["apkpure_status"] == "available" and row["cross_check"] != "version_mismatch"
        if use_apkpure:
            apk_record = discovered_apkpure.get(package_id)
            architecture = choose_apkpure_architecture(apk_record)
            plans.append(
                AcquisitionPlan(
                    package_id=package_id,
                    scope="discovered_likely_ble",
                    selection="download_apkpure",
                    expected_version_name=row["apkpure_version_name"],
                    expected_version_code=row["apkpure_version_code"],
                    source="APKPure",
                    source_url=row["apkpure_url"],
                    requested_architecture=architecture,
                    variant_url=choose_apkpure_variant_url(apk_record, architecture),
                )
            )
        elif row["play_status"] == "available":
            plans.append(
                AcquisitionPlan(
                    package_id=package_id,
                    scope="discovered_likely_ble",
                    selection="download_google_play",
                    expected_version_name=row["latest_version_name"],
                    expected_version_code="",
                    source="Google Play",
                    source_url=row["play_url"],
                    detail=row["blocker"],
                )
            )
        else:
            plans.append(
                AcquisitionPlan(
                    package_id=package_id,
                    scope="discovered_likely_ble",
                    selection="blocked",
                    expected_version_name=row["latest_version_name"],
                    expected_version_code=row["latest_version_code"],
                    source="unavailable",
                    source_url=row["apkpure_url"] or row["play_url"],
                    detail=row["blocker"] or "no downloadable current source",
                )
            )
    return sorted(plans, key=lambda item: item.package_id.casefold())


def select_local_archive(
    plan: AcquisitionPlan, archive_rows: list[dict[str, str]]
) -> dict[str, str] | None:
    """Select the strongest local archive matching the expected current version."""
    candidates = [
        row
        for row in archive_rows
        if row["package_id"] == plan.package_id
        and row["version_name"] == plan.expected_version_name
        and (not plan.expected_version_code or row["version_code"] == plan.expected_version_code)
    ]
    if not candidates:
        return None

    def rank(row: dict[str, str]) -> tuple[bool, bool, bool, str]:
        return (
            row["status"] != "ok",
            "arm64-v8a" not in row["architectures"],
            row["archive_type"] != "xapk",
            row["source_path"].casefold(),
        )

    return min(candidates, key=rank)


def verify_signature(path: Path, apksigner: str) -> tuple[str, str, str]:
    """Verify an APK signature and return status, certificate digests, and error."""
    result = subprocess.run(
        [apksigner, "verify", "--print-certs", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    output = "\n".join((result.stdout, result.stderr))
    digests = sorted({value.lower().replace(":", "") for value in CERT_DIGEST_PATTERN.findall(output)})
    if result.returncode == 0:
        return "verified", "; ".join(digests), ""
    detail = result.stderr.strip() or result.stdout.strip() or "apksigner returned an error"
    return "failed", "; ".join(digests), detail.replace("\n", " | ")


def inspect_member(
    path: Path,
    package_id: str,
    artifact_path: str,
    member_path: str,
    aapt: str,
    apksigner: str,
    sha256: str | None = None,
) -> MemberRecord:
    """Inspect one APK file or extracted split."""
    record = MemberRecord(
        package_id=package_id,
        artifact_path=artifact_path,
        member_path=member_path,
        file_size_bytes=path.stat().st_size,
        sha256=sha256 or file_sha256(path),
    )
    errors: list[str] = []
    try:
        metadata = run_aapt(aapt, path)
        record.embedded_package_id = metadata.package_id
        record.package_version_name = metadata.version_name
        record.package_version_code = metadata.version_code
        architectures = set(metadata.architectures)
        architectures.update(_architectures_from_names([member_path]))
        record.architectures = "; ".join(sorted(architectures))
    except AaptError as err:
        metadata = err.metadata
        record.embedded_package_id = metadata.package_id
        record.package_version_name = metadata.version_name
        record.package_version_code = metadata.version_code
        architectures = set(metadata.architectures)
        architectures.update(_architectures_from_names([member_path]))
        record.architectures = "; ".join(sorted(architectures))
        if not metadata.package_id:
            errors.append(f"aapt: {err}")
    except Exception as err:  # keep split-level failures in the manifest
        errors.append(f"aapt: {err}")

    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            record.resource_entry_count = sum(
                name == "resources.arsc" or name.startswith("res/") for name in names
            )
            native_libraries = [name for name in names if name.startswith("lib/") and name.endswith(".so")]
            record.native_library_count = len(native_libraries)
            flutter_architectures = {
                match.group(1)
                for name in names
                if (match := FLUTTER_LIBRARY_PATTERN.match(name))
            }
            record.flutter_architectures = "; ".join(sorted(flutter_architectures))
    except (BadZipFile, OSError) as err:
        errors.append(f"zip: {err}")

    status, digests, signature_error = verify_signature(path, apksigner)
    record.signature_status = status
    record.signer_certificate_sha256 = digests
    if signature_error:
        errors.append(f"signature: {signature_error}")
    record.error = "; ".join(errors)
    return record


def _set_sha256(members: list[MemberRecord]) -> str:
    digest = hashlib.sha256()
    for member in sorted(members, key=lambda item: item.member_path):
        digest.update(member.member_path.encode())
        digest.update(b"\0")
        digest.update(member.sha256.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def inspect_artifact(
    path: Path,
    expected_package_id: str,
    aapt: str,
    apksigner: str,
    working_directory: Path,
) -> ArtifactInspection:
    """Inspect an APK, XAPK, or Google Play split directory without modifying it."""
    display_path = source_path(path, working_directory)
    if path.is_file() and path.suffix.lower() in {".apk", ".xapk"}:
        archive_record = (
            inspect_xapk(path, aapt, working_directory)
            if path.suffix.lower() == ".xapk"
            else inspect_apk(path, aapt, working_directory)
        )
        inspection = ArtifactInspection(
            artifact_path=display_path,
            artifact_type=archive_record.archive_type,
            file_size_bytes=archive_record.file_size_bytes,
            sha256=archive_record.sha256,
            package_id=archive_record.package_id,
            version_name=archive_record.version_name,
            version_code=archive_record.version_code,
            split_count=archive_record.split_count or 1,
            splits=archive_record.splits or path.name,
            architectures=archive_record.architectures,
            error=archive_record.error,
        )
        if path.suffix.lower() == ".apk":
            inspection.members.append(
                inspect_member(path, expected_package_id, display_path, path.name, aapt, apksigner)
            )
        else:
            try:
                with ZipFile(path) as archive, tempfile.TemporaryDirectory(
                    prefix="apk-acquisition-splits-"
                ) as temporary_directory:
                    for index, member_name in enumerate(
                        sorted(name for name in archive.namelist() if name.lower().endswith(".apk"))
                    ):
                        temporary_path = Path(temporary_directory) / f"{index}.apk"
                        digest = hashlib.sha256()
                        with archive.open(member_name) as source, temporary_path.open("wb") as destination:
                            while chunk := source.read(1024 * 1024):
                                digest.update(chunk)
                                destination.write(chunk)
                        inspection.members.append(
                            inspect_member(
                                temporary_path,
                                expected_package_id,
                                display_path,
                                member_name,
                                aapt,
                                apksigner,
                                digest.hexdigest(),
                            )
                        )
            except (BadZipFile, OSError) as err:
                inspection.error = "; ".join(filter(None, (inspection.error, str(err))))
    elif path.is_dir():
        apk_files = sorted(path.rglob("*.apk"), key=lambda item: item.as_posix().casefold())
        if not apk_files:
            return ArtifactInspection(
                artifact_path=display_path,
                artifact_type="split_apk_set",
                file_size_bytes=0,
                sha256="",
                error="download directory contains no APK files",
            )
        members = [
            inspect_member(
                apk,
                expected_package_id,
                display_path,
                apk.relative_to(path).as_posix(),
                aapt,
                apksigner,
            )
            for apk in apk_files
        ]
        base = min(
            members,
            key=lambda item: (
                Path(item.member_path).name.lower() != "base.apk",
                Path(item.member_path).name.lower() != f"{expected_package_id.lower()}.apk",
                Path(item.member_path).name.lower().startswith(("config.", "split_config.")),
                -item.file_size_bytes,
            ),
        )
        architectures = {
            architecture
            for member in members
            for architecture in member.architectures.split("; ")
            if architecture
        }
        inspection = ArtifactInspection(
            artifact_path=display_path,
            artifact_type="split_apk_set" if len(members) > 1 else "apk",
            file_size_bytes=sum(member.file_size_bytes for member in members),
            sha256=_set_sha256(members),
            package_id=base.embedded_package_id,
            version_name=base.package_version_name,
            version_code=base.package_version_code,
            split_count=len(members),
            splits="; ".join(member.member_path for member in members),
            architectures="; ".join(sorted(architectures)),
            error="; ".join(member.error for member in members if member.error),
            members=members,
        )
    else:
        return ArtifactInspection(
            artifact_path=display_path,
            artifact_type="unknown",
            file_size_bytes=0,
            sha256="",
            error="artifact is not an APK, XAPK, or directory",
        )

    signatures = {member.signature_status for member in inspection.members}
    inspection.signature_status = "verified" if signatures == {"verified"} else "; ".join(sorted(signatures))
    inspection.signer_certificate_sha256 = "; ".join(
        sorted(
            {
                digest
                for member in inspection.members
                for digest in member.signer_certificate_sha256.split("; ")
                if digest
            }
        )
    )
    flutter_architectures = {
        architecture
        for member in inspection.members
        for architecture in member.flutter_architectures.split("; ")
        if architecture
    }
    if flutter_architectures:
        inspection.technology = "flutter"
        inspection.flutter_architectures = "; ".join(sorted(flutter_architectures))
    return inspection


def locate_download(path: Path) -> Path | None:
    """Return a single archive or the directory containing a Play split set."""
    xapks = sorted(path.rglob("*.xapk"))
    apks = sorted(path.rglob("*.apk"))
    if len(xapks) == 1 and not apks:
        return xapks[0]
    if len(apks) == 1 and not xapks:
        return apks[0]
    if apks or xapks:
        return path
    return None


def download_with_apkeep(
    plan: AcquisitionPlan,
    destination: Path,
    apkeep: str,
    google_play_ini: Path | None,
) -> tuple[Path | None, str, str]:
    """Download one package atomically with pinned apkeep."""
    source_directory = destination / ("apkpure" if plan.selection == "download_apkpure" else "google-play")
    suffix = f"-{plan.requested_architecture}" if plan.variant_url else ""
    final_directory = source_directory / f"{plan.package_id}{suffix}"
    existing = locate_download(final_directory) if final_directory.is_dir() else None
    if existing:
        locator = f"apkeep {APKEEP_VERSION}; existing {plan.source} acquisition"
        return existing, locator, ""
    if plan.selection == "download_google_play" and not google_play_ini:
        return None, "", "Google Play authentication is not configured (pass --google-play-ini)"

    source_directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{plan.package_id}-", dir=source_directory) as temporary:
        temporary_path = Path(temporary)
        if plan.variant_url:
            extension = ".xapk" if "/XAPK/" in plan.variant_url else ".apk"
            artifact_name = (
                f"{plan.package_id}@{plan.expected_version_name}@"
                f"{plan.requested_architecture}{extension}"
            )
            command = [
                shutil.which("curl") or "curl",
                "--fail",
                "--location",
                "--retry",
                "3",
                "--retry-all-errors",
                "--continue-at",
                "-",
                "--output",
                str(temporary_path / artifact_name),
                plan.variant_url,
            ]
            locator = f"APKPure exact variant; {plan.variant_url}"
        elif plan.selection == "download_apkpure":
            app = f"{plan.package_id}@{plan.expected_version_name}"
            command = [
                apkeep,
                "-a",
                app,
                "-d",
                "apk-pure",
                "-r",
                "1",
                "-s",
                "500",
            ]
            if plan.requested_architecture:
                command.extend(["-o", f"arch={plan.requested_architecture}"])
            locator = f"apkeep {APKEEP_VERSION}; {app}"
            if plan.requested_architecture:
                locator += f"; arch={plan.requested_architecture}"
        else:
            command = [
                apkeep,
                "-a",
                plan.package_id,
                "-d",
                "google-play",
                "-i",
                str(google_play_ini),
                "-o",
                "split_apk=true",
                "-r",
                "1",
                "-s",
                "500",
            ]
            locator = f"apkeep {APKEEP_VERSION}; {plan.package_id}; google-play; split_apk=true"
        if not plan.variant_url:
            command.append(str(temporary_path))
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        artifact = locate_download(temporary_path)
        if not artifact and plan.selection == "download_google_play":
            profiles = (
                ("px_tablet", "mi_a1", "sm_s20_plus")
                if ".pad." in plan.package_id
                else ("mi_a1", "sm_s20_plus")
            )
            for profile in profiles:
                alternate_path = temporary_path / profile
                alternate_path.mkdir()
                alternate_command = [
                    apkeep,
                    "-a",
                    plan.package_id,
                    "-d",
                    "google-play",
                    "-i",
                    str(google_play_ini),
                    "-o",
                    f"device={profile},split_apk=true",
                    "-r",
                    "1",
                    "-s",
                    "500",
                    str(alternate_path),
                ]
                result = subprocess.run(
                    alternate_command, check=False, capture_output=True, text=True
                )
                artifact = locate_download(temporary_path)
                if artifact:
                    locator = (
                        f"apkeep {APKEEP_VERSION}; {plan.package_id}; google-play; "
                        f"device={profile}; split_apk=true"
                    )
                    break
        elif not artifact and plan.selection == "download_apkpure":
            fallback_url = f"https://d.apkpure.net/b/XAPK/{plan.package_id}?version=latest"
            fallback_path = temporary_path / f"{plan.package_id}@latest.xapk"
            fallback_command = [
                shutil.which("curl") or "curl",
                "--fail",
                "--location",
                "--retry",
                "3",
                "--retry-all-errors",
                "--continue-at",
                "-",
                "--output",
                str(fallback_path),
                fallback_url,
            ]
            fallback_result = subprocess.run(
                fallback_command, check=False, capture_output=True, text=True
            )
            if fallback_result.returncode != 0:
                fallback_path.unlink(missing_ok=True)
            artifact = locate_download(temporary_path)
            if artifact:
                locator = f"APKPure latest XAPK fallback; {fallback_url}"
            else:
                result = fallback_result
        if not artifact:
            output = "\n".join((result.stdout, result.stderr)).strip().splitlines()
            detail = " | ".join(output[-4:])
            if not detail or all(line.startswith("Downloading ") for line in output):
                detail = (
                    f"{plan.source} returned no APK/XAPK for the requested latest build "
                    "and emitted no diagnostic"
                )
            return None, locator, detail

        os.replace(temporary_path, final_directory)
        return locate_download(final_directory), locator, ""


def _apply_inspection(record: AcquisitionRecord, inspection: ArtifactInspection) -> None:
    record.actual_version_name = inspection.version_name
    record.actual_version_code = inspection.version_code
    record.artifact_path = inspection.artifact_path
    record.artifact_type = inspection.artifact_type
    record.file_size_bytes = inspection.file_size_bytes
    record.sha256 = inspection.sha256
    record.split_count = inspection.split_count
    record.splits = inspection.splits
    record.architectures = inspection.architectures
    record.signature_status = inspection.signature_status
    record.signer_certificate_sha256 = inspection.signer_certificate_sha256
    record.technology = inspection.technology
    record.flutter_architectures = inspection.flutter_architectures
    if inspection.technology == "flutter":
        record.flutter_arm64_status = (
            "present" if "arm64-v8a" in inspection.flutter_architectures else "missing"
        )
    else:
        record.flutter_arm64_status = "not_flutter"


def validate_inspection(plan: AcquisitionPlan, inspection: ArtifactInspection) -> list[str]:
    """Return every integrity or metadata mismatch for an artifact."""
    errors: list[str] = []
    if inspection.error:
        errors.append(inspection.error)
    if inspection.package_id != plan.package_id:
        errors.append(f"package ID {inspection.package_id!r} does not match {plan.package_id!r}")
    if inspection.version_name != plan.expected_version_name:
        errors.append(
            f"versionName {inspection.version_name!r} does not match {plan.expected_version_name!r}"
        )
    if plan.expected_version_code and inspection.version_code != plan.expected_version_code:
        errors.append(
            f"versionCode {inspection.version_code!r} does not match {plan.expected_version_code!r}"
        )
    if inspection.signature_status != "verified":
        errors.append(f"signature status is {inspection.signature_status or 'unknown'}")
    return errors


def find_flutter_fallback(
    package_id: str,
    archive_rows: list[dict[str, str]],
    aapt: str,
    apksigner: str,
    working_directory: Path,
) -> ArtifactInspection | None:
    """Find an explicitly recorded older local Flutter arm64 artifact."""
    candidates = sorted(
        (
            row
            for row in archive_rows
            if row["package_id"] == package_id and "arm64-v8a" in row["architectures"]
        ),
        key=lambda row: (row["version_code"].isdigit(), row["version_code"]),
        reverse=True,
    )
    for row in candidates:
        path = working_directory / row["source_path"]
        inspection = inspect_artifact(path, package_id, aapt, apksigner, working_directory)
        if inspection.technology == "flutter" and "arm64-v8a" in inspection.flutter_architectures:
            return inspection
    return None


def run_acquisition(
    plans: list[AcquisitionPlan],
    archive_rows: list[dict[str, str]],
    destination: Path,
    cutoff_date: str,
    apkeep: str,
    aapt: str,
    apksigner: str,
    google_play_ini: Path | None,
    previous_records: dict[str, AcquisitionRecord] | None = None,
    previous_members: list[MemberRecord] | None = None,
) -> tuple[list[AcquisitionRecord], list[MemberRecord]]:
    """Execute the selection plan and return package and split evidence."""
    working_directory = Path.cwd()
    records: list[AcquisitionRecord] = []
    member_records: list[MemberRecord] = []
    previous_records = previous_records or {}
    members_by_package: dict[str, list[MemberRecord]] = defaultdict(list)
    for member in previous_members or []:
        members_by_package[member.package_id].append(member)
    for index, plan in enumerate(plans, start=1):
        previous = previous_records.get(plan.package_id)
        if previous and previous.status in {"downloaded", "reused_current"}:
            print(f"[{index}/{len(plans)}] {plan.package_id}: preserve verified result", flush=True)
            records.append(previous)
            member_records.extend(members_by_package[plan.package_id])
            continue
        print(f"[{index}/{len(plans)}] {plan.package_id}: {plan.selection}", flush=True)
        record = AcquisitionRecord(
            package_id=plan.package_id,
            scope=plan.scope,
            selection=plan.selection,
            status="blocked",
            expected_version_name=plan.expected_version_name,
            expected_version_code=plan.expected_version_code,
            source=plan.source,
            source_url=plan.source_url,
            requested_architecture=plan.requested_architecture,
            detail=plan.detail,
            cutoff_date=cutoff_date,
        )
        artifact: Path | None = None
        if plan.selection == "reuse_local":
            local = select_local_archive(plan, archive_rows)
            if local:
                artifact = working_directory / local["source_path"]
            else:
                record.detail = "; ".join(
                    filter(None, (record.detail, "no local archive matches the selected current version"))
                )
        elif plan.selection.startswith("download_"):
            artifact, record.download_locator, error = download_with_apkeep(
                plan, destination, apkeep, google_play_ini
            )
            if error:
                record.detail = "; ".join(filter(None, (record.detail, error)))

        if artifact:
            inspection = inspect_artifact(
                artifact, plan.package_id, aapt, apksigner, working_directory
            )
            _apply_inspection(record, inspection)
            member_records.extend(inspection.members)
            errors = validate_inspection(plan, inspection)
            if errors:
                record.status = "validation_error"
                record.detail = "; ".join(filter(None, (record.detail, *errors)))
            elif inspection.technology == "flutter" and "arm64-v8a" not in inspection.flutter_architectures:
                play_selected = False
                play_detail = ""
                if google_play_ini and plan.selection != "download_google_play":
                    play_plan = replace(
                        plan,
                        selection="download_google_play",
                        source="Google Play",
                        source_url=(
                            "https://play.google.com/store/apps/details?id="
                            f"{plan.package_id}"
                        ),
                        requested_architecture="",
                        variant_url="",
                        detail="",
                    )
                    play_artifact, play_locator, play_error = download_with_apkeep(
                        play_plan, destination, apkeep, google_play_ini
                    )
                    if play_artifact:
                        play_inspection = inspect_artifact(
                            play_artifact,
                            plan.package_id,
                            aapt,
                            apksigner,
                            working_directory,
                        )
                        play_errors = validate_inspection(play_plan, play_inspection)
                        if (
                            not play_errors
                            and play_inspection.technology == "flutter"
                            and "arm64-v8a" in play_inspection.flutter_architectures
                        ):
                            if inspection.members:
                                del member_records[-len(inspection.members) :]
                            member_records.extend(play_inspection.members)
                            _apply_inspection(record, play_inspection)
                            record.selection = "download_google_play_flutter_arm64"
                            record.source = "Google Play"
                            record.source_url = play_plan.source_url
                            record.download_locator = play_locator
                            record.requested_architecture = "arm64-v8a"
                            record.status = "downloaded"
                            record.detail = "; ".join(
                                filter(
                                    None,
                                    (
                                        record.detail,
                                        "selected Google Play arm64 build because APKPure/local latest was armv7-only",
                                    ),
                                )
                            )
                            play_selected = True
                        else:
                            play_detail = "; ".join(
                                play_errors
                                or [
                                    "Google Play artifact does not contain arm64-v8a libapp.so"
                                ]
                            )
                    else:
                        play_detail = play_error

                if not play_selected:
                    record.status = "blocked_flutter_arm64"
                    record.detail = "; ".join(
                        filter(
                            None,
                            (
                                record.detail,
                                "latest Flutter artifact has no arm64-v8a libapp.so",
                                f"Google Play arm64 fallback: {play_detail}"
                                if play_detail
                                else "",
                            ),
                        )
                    )
                    fallback = find_flutter_fallback(
                        plan.package_id, archive_rows, aapt, apksigner, working_directory
                    )
                    if fallback:
                        record.fallback_artifact_path = fallback.artifact_path
                        record.fallback_version_name = fallback.version_name
                        record.fallback_version_code = fallback.version_code
                        record.fallback_architectures = fallback.architectures
                        record.fallback_sha256 = fallback.sha256
            else:
                record.status = "reused_current" if plan.selection == "reuse_local" else "downloaded"
        records.append(record)
    return records, member_records


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_readme(
    path: Path,
    cutoff_date: str,
    destination: Path,
    records: list[AcquisitionRecord],
    members: list[MemberRecord],
) -> None:
    """Write the human-readable phase 3 acquisition summary."""
    statuses = Counter(record.status for record in records)
    selections = Counter(record.selection for record in records)
    flutter = [record for record in records if record.technology == "flutter"]
    blockers = [record for record in records if record.status not in {"downloaded", "reused_current"}]
    lines = [
        f"# APK acquisition and verification ({cutoff_date})",
        "",
        "This is the phase 3 analysis-corpus manifest for issue #436. It selects one latest",
        "artifact for every baseline package and every newly discovered likely BLE bed app.",
        "Wi-Fi-only and unrelated discoveries remain excluded by the phase 2 classification.",
        "",
        "## Artifacts",
        "",
        "- `acquisition.csv`: one selected artifact or exact blocker per package.",
        "- `files.csv`: one row per APK or embedded split, with hashes, signatures, resource",
        "  counts, native-library counts, ABIs, and Flutter `libapp.so` ABIs.",
        "- Selected raw downloads remain byte-for-byte untouched under the gitignored",
        "  acquisition directory; redundant non-arm64 acquisition attempts are not retained.",
        "",
        "## Acquisition tool",
        "",
        f"Downloads use [`apkeep` {APKEEP_VERSION}]({APKEEP_RELEASE_URL}), pinned to the",
        f"x86_64 Linux asset SHA-256 `{APKEEP_ASSET_SHA256}`. Its release signature was",
        f"verified against PGP fingerprint `{APKEEP_SIGNING_FINGERPRINT}` before use.",
        "APKPure requests pin the expected version and prefer arm64-v8a when advertised.",
        "When APKPure exposes an exact architecture variant, its recorded artifact URL is",
        "downloaded directly with retry/resume support because apkeep 1.0.0 can return the",
        "armv7 artifact for an arm64 request. The resulting archive receives the same checks.",
        "Google Play requests ask for all split APKs and use a local credential file; no",
        "credential or token is written to these reports.",
        "",
        "## Verification",
        "",
        "- Package ID, `versionName`, and APKPure `versionCode` are read from the APK itself.",
        "- Google Play does not expose `versionCode` in its web metadata, so Play downloads",
        "  verify the expected `versionName` and record the embedded `versionCode` afterward.",
        "- SHA-256 is recorded for the original APK/XAPK and every embedded split. Google Play",
        "  split sets use a deterministic set hash over sorted member paths and member hashes.",
        "- Every APK signature is checked with `apksigner`; signer certificate SHA-256 digests",
        "  are recorded without modifying the files.",
        "- Every XAPK or Play split is opened and counted for resources and native libraries.",
        "- Flutter is detected only from `lib/<abi>/libapp.so`. A latest Flutter artifact without",
        "  arm64-v8a is blocked explicitly, with any older local arm64 fallback recorded separately.",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| In-scope packages | {len(records)} |",
        f"| Baseline packages | {sum(record.scope == 'baseline' for record in records)} |",
        f"| Newly discovered likely BLE apps | {sum(record.scope != 'baseline' for record in records)} |",
        f"| Reused current local artifacts | {statuses['reused_current']} |",
        f"| Downloaded and verified artifacts | {statuses['downloaded']} |",
        f"| Validation errors | {statuses['validation_error']} |",
        f"| Flutter arm64 blockers | {statuses['blocked_flutter_arm64']} |",
        f"| Source/delivery blockers | {statuses['blocked']} |",
        f"| APKPure downloads selected | {selections['download_apkpure']} |",
        f"| Google Play primary selections | {selections['download_google_play']} |",
        f"| Flutter arm64 Play fallbacks selected | {selections['download_google_play_flutter_arm64']} |",
        f"| Flutter artifacts detected | {len(flutter)} |",
        f"| APK/split file rows | {len(members)} |",
        "",
        "## Remaining blockers",
        "",
    ]
    if blockers:
        lines.extend(["| Package | Status | Detail |", "|---|---|---|"])
        for record in blockers:
            detail = record.detail.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `{record.package_id}` | {record.status} | {detail} |")
    else:
        lines.append("None.")

    lines.extend(
        [
            "",
            "## Reproduce",
            "",
            "Run from the repository root after installing `aapt`, `apksigner`, and the pinned",
            "`apkeep` release. Google Play is optional until a local `apkeep.ini` is configured:",
            "",
            "```bash",
            "python3 tools/apk_acquisition.py \\",
            "  --google-play-ini ~/.config/apkeep/apkeep.ini",
            "```",
            "",
            f"Raw download directory: `{source_path(destination, Path.cwd())}`.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    root = Path("docs/reanalysis")
    latest = root / "2026-07-14-apk-latest-versions"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archives", type=Path, default=root / "2026-07-14-apk-inventory/archives.csv"
    )
    parser.add_argument("--latest", type=Path, default=latest / "latest_versions.csv")
    parser.add_argument("--discoveries", type=Path, default=latest / "discovered_packages.csv")
    parser.add_argument("--apkpure", type=Path, default=latest / "apkpure.json")
    parser.add_argument(
        "--discovered-apkpure", type=Path, default=latest / "discovered_apkpure.json"
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("disassembly/apk/not-analyzed/acquired-2026-07-14"),
    )
    parser.add_argument(
        "--output", type=Path, default=root / "2026-07-14-apk-acquisition"
    )
    parser.add_argument("--cutoff-date", default="2026-07-14")
    parser.add_argument("--apkeep", default=shutil.which("apkeep"))
    parser.add_argument("--aapt", default=shutil.which("aapt"))
    parser.add_argument("--apksigner", default=shutil.which("apksigner"))
    parser.add_argument("--google-play-ini", type=Path)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument(
        "--retry-failures",
        action="store_true",
        help="preserve successful rows from the existing output and retry only exceptions",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for tool_name in ("apkeep", "aapt", "apksigner"):
        if not getattr(args, tool_name):
            raise SystemExit(f"{tool_name} is required")
    version = subprocess.run(
        [args.apkeep, "--version"], check=False, capture_output=True, text=True
    ).stdout.strip()
    if version != f"apkeep {APKEEP_VERSION}":
        raise SystemExit(f"expected apkeep {APKEEP_VERSION}, got {version!r}")
    if args.google_play_ini and not args.google_play_ini.is_file():
        raise SystemExit(f"Google Play config does not exist: {args.google_play_ini}")

    archive_rows = read_csv(args.archives)
    plans = build_plans(
        read_csv(args.latest),
        read_csv(args.discoveries),
        load_apkpure(args.apkpure),
        load_apkpure(args.discovered_apkpure),
    )
    if args.plan_only:
        counts = Counter(plan.selection for plan in plans)
        print(f"Planned {len(plans)} packages: {dict(sorted(counts.items()))}")
        return 0

    previous_records: dict[str, AcquisitionRecord] = {}
    previous_members: list[MemberRecord] = []
    if args.retry_failures:
        acquisition_path = args.output / "acquisition.csv"
        files_path = args.output / "files.csv"
        if not acquisition_path.is_file() or not files_path.is_file():
            raise SystemExit("--retry-failures requires an existing acquisition.csv and files.csv")
        previous_records = {
            row["package_id"]: AcquisitionRecord(**row) for row in read_csv(acquisition_path)
        }
        previous_members = [MemberRecord(**row) for row in read_csv(files_path)]

    records, members = run_acquisition(
        plans,
        archive_rows,
        args.destination,
        args.cutoff_date,
        args.apkeep,
        args.aapt,
        args.apksigner,
        args.google_play_ini,
        previous_records,
        previous_members,
    )
    write_csv(args.output / "acquisition.csv", ACQUISITION_FIELDS, [asdict(row) for row in records])
    write_csv(args.output / "files.csv", FILE_FIELDS, [asdict(row) for row in members])
    write_readme(args.output / "README.md", args.cutoff_date, args.destination, records, members)
    counts = Counter(record.status for record in records)
    print(f"Recorded {len(records)} packages: {dict(sorted(counts.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
