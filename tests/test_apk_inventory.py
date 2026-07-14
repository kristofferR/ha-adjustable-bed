"""Tests for the local APK inventory generator."""

from tools.apk_inventory import (
    ArchiveRecord,
    _architectures_from_names,
    _select_base_apk,
    annotate_groups,
    parse_aapt_badging,
)


def test_parse_aapt_badging() -> None:
    metadata = parse_aapt_badging(
        "\n".join(
            (
                "package: name='com.example.bed' versionCode='42' versionName='1.2.3'",
                "sdkVersion:'23'",
                "targetSdkVersion:'35'",
                "application-label:'Member's Mark Base Remote'",
                "native-code: 'arm64-v8a' 'armeabi-v7a'",
            )
        )
    )

    assert metadata.application_name == "Member's Mark Base Remote"
    assert metadata.package_id == "com.example.bed"
    assert metadata.version_name == "1.2.3"
    assert metadata.version_code == "42"
    assert metadata.min_sdk_version == "23"
    assert metadata.target_sdk_version == "35"
    assert metadata.architectures == {"arm64-v8a", "armeabi-v7a"}


def test_select_base_apk_prefers_manifest_base_split() -> None:
    manifest = {
        "package_name": "com.example.bed",
        "split_apks": [
            {"id": "base", "file": "nested/application.apk"},
            {"id": "config.arm64_v8a", "file": "config.arm64_v8a.apk"},
        ],
    }

    assert (
        _select_base_apk(
            manifest,
            ["nested/application.apk", "config.arm64_v8a.apk"],
        )
        == "nested/application.apk"
    )


def test_select_base_apk_falls_back_to_package_name() -> None:
    assert (
        _select_base_apk(
            {"package_name": "com.example.bed"},
            ["com.example.bed.apk", "config.en.apk"],
        )
        == "com.example.bed.apk"
    )


def test_architectures_from_split_names() -> None:
    assert _architectures_from_names(
        [
            "base=com.example.apk",
            "config.arm64_v8a=config.arm64_v8a.apk",
            "config.armeabi_v7a.apk",
            "config.en.apk",
        ]
    ) == {"arm64-v8a", "armeabi-v7a"}


def test_annotate_groups_distinguishes_metadata_and_file_duplicates() -> None:
    first = _record("a.apk", "hash-a", "1.0", "1")
    identical = _record("copy.apk", "hash-a", "1.0", "1")
    rebuilt = _record("rebuilt.apk", "hash-b", "1.0", "1")
    newer = _record("newer.apk", "hash-c", "2.0", "2")

    annotate_groups([first, identical, rebuilt, newer])

    assert first.identical_file_count == 2
    assert first.package_version_record_count == 3
    assert first.package_version_distinct_file_count == 2
    assert first.package_has_multiple_versions is True
    assert newer.identical_file_count == 1
    assert newer.package_version_record_count == 1
    assert newer.package_has_multiple_versions is True


def _record(path: str, sha256: str, version_name: str, version_code: str) -> ArchiveRecord:
    return ArchiveRecord(
        source_path=path,
        archive_type="apk",
        file_size_bytes=1,
        sha256=sha256,
        package_id="com.example.bed",
        version_name=version_name,
        version_code=version_code,
    )
