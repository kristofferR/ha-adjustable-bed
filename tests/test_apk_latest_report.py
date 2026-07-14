"""Tests for the APK latest-version report."""

from tools.apk_latest_report import classify, discovery_relevance


def test_classify_outdated_from_version_code() -> None:
    classification, cross_check, blocker = classify(
        "1.0",
        "10",
        {"status": "available", "version": "2.0"},
        {"status": "available", "version_name": "2.0", "version_code": "20"},
    )

    assert classification == "outdated"
    assert cross_check == "matched"
    assert blocker == ""


def test_classify_conflicting_sources_as_unverifiable() -> None:
    classification, cross_check, blocker = classify(
        "1.0",
        "10",
        {"status": "available", "version": "3.0"},
        {"status": "available", "version_name": "2.0", "version_code": "20"},
    )

    assert classification == "unverifiable"
    assert cross_check == "version_mismatch"
    assert "Google Play reports 3.0" in blocker


def test_discovery_relevance_excludes_non_bed_apps() -> None:
    assert discovery_relevance("com.jiecang.wheelchair", "iwheel") == (
        "not_bed_app",
        "wheelchair controller",
    )
    assert discovery_relevance("com.sbi.markbase", "Member's Mark Base WiFi")[0] == (
        "likely_bed_app"
    )


def test_discovery_relevance_preserves_user_corrections() -> None:
    assert discovery_relevance("at.logicdata.motionatwork", "MOTION@work") == (
        "not_bed_app",
        "user-confirmed non-bed app",
    )
    assert discovery_relevance("com.keeson.smartbed", "Ergo WiFi") == (
        "not_bed_app",
        "user-confirmed non-bed app",
    )
    assert discovery_relevance("com.ly.homekobo", "HOME KOBO") == (
        "likely_bed_app",
        "user-confirmed bed app",
    )
