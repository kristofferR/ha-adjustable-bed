"""Tests for APK corpus acquisition planning and verification helpers."""

from tools.apk_acquisition import (
    AcquisitionPlan,
    ArtifactInspection,
    build_plans,
    choose_apkpure_architecture,
    choose_apkpure_variant_url,
    select_local_archive,
    validate_inspection,
)


def test_choose_apkpure_architecture_prefers_arm64() -> None:
    assert choose_apkpure_architecture({"architectures": "armeabi-v7a; arm64-v8a"}) == "arm64-v8a"
    assert choose_apkpure_architecture({"architectures": "armeabi-v7a"}) == "armeabi-v7a"
    assert choose_apkpure_architecture({"architectures": "universal"}) == ""


def test_choose_apkpure_variant_url_matches_exact_architecture() -> None:
    record = {
        "variants": [
            {"architecture": "armeabi-v7a", "url": "https://example.test/armv7"},
            {"architecture": "arm64-v8a", "url": "https://example.test/arm64"},
        ]
    }

    assert choose_apkpure_variant_url(record, "arm64-v8a") == "https://example.test/arm64"
    assert choose_apkpure_variant_url(record, "x86") == ""


def test_build_plans_uses_play_for_version_mismatch_discovery() -> None:
    discoveries = [
        {
            "package_id": "com.example.bed",
            "relevance": "likely_bed_app",
            "apkpure_status": "available",
            "cross_check": "version_mismatch",
            "play_status": "available",
            "latest_version_name": "2.0",
            "latest_version_code": "",
            "apkpure_version_name": "1.0",
            "apkpure_version_code": "1",
            "apkpure_url": "https://apkpure.example/app",
            "play_url": "https://play.example/app",
            "blocker": "versions differ",
        }
    ]

    plans = build_plans([], discoveries, {}, {})

    assert plans[0].selection == "download_google_play"
    assert plans[0].expected_version_name == "2.0"


def test_select_local_archive_prefers_arm64_xapk() -> None:
    plan = AcquisitionPlan(
        package_id="com.example.bed",
        scope="baseline",
        selection="reuse_local",
        expected_version_name="1.0",
        expected_version_code="10",
        source="APKPure",
        source_url="https://example.test",
    )
    rows = [
        _archive("plain.apk", "apk", "armeabi-v7a"),
        _archive("arm64.apk", "apk", "arm64-v8a"),
        _archive("bundle.xapk", "xapk", "arm64-v8a"),
    ]

    assert select_local_archive(plan, rows)["source_path"] == "bundle.xapk"


def test_validate_inspection_checks_package_version_and_signature() -> None:
    plan = AcquisitionPlan(
        package_id="com.example.bed",
        scope="baseline",
        selection="download_apkpure",
        expected_version_name="2.0",
        expected_version_code="20",
        source="APKPure",
        source_url="https://example.test",
    )
    inspection = ArtifactInspection(
        artifact_path="bed.apk",
        artifact_type="apk",
        file_size_bytes=1,
        sha256="hash",
        package_id="com.other",
        version_name="1.0",
        version_code="10",
        signature_status="failed",
    )

    errors = validate_inspection(plan, inspection)

    assert len(errors) == 4
    assert "package ID" in errors[0]


def _archive(path: str, archive_type: str, architectures: str) -> dict[str, str]:
    return {
        "package_id": "com.example.bed",
        "version_name": "1.0",
        "version_code": "10",
        "status": "ok",
        "archive_type": archive_type,
        "architectures": architectures,
        "source_path": path,
    }
