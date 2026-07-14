"""Tests for the APKPure metadata inventory generator."""

from tools.apkpure_inventory import parse_detail_html, parse_download_html


def test_parse_detail_html() -> None:
    document = """
    <script type="application/ld+json">
      {"@type":"MobileApplication","name":"RMControl","datePublished":"2026-07-05"}
    </script>
    <script>window.apkpure = {pageData: {"packageName":"com.richmat.rmcontrol2",
      "versionName":"21.3.7","versionCode":213700}}</script>
    """

    assert parse_detail_html(document) == {
        "package_id": "com.richmat.rmcontrol2",
        "title": "RMControl",
        "version_name": "21.3.7",
        "version_code": "213700",
        "release_date": "2026-07-05",
    }


def test_parse_download_html_filters_latest_variants() -> None:
    document = """
    <a class="download-btn" data-dt-version="21.3.7" data-dt-version_code="213700"
       data-dt-file_size="49217963"
       href="https://d.apkpure.net/b/XAPK/com.richmat.rmcontrol2?versionCode=213700&amp;nc=armeabi-v7a"></a>
    <a class="download-btn" data-dt-version="21.3.7" data-dt-version_code="213700"
       data-dt-file_size="41841906"
       href="https://d.apkpure.net/b/XAPK/com.richmat.rmcontrol2?versionCode=213700&amp;nc=arm64-v8a"></a>
    <a class="download-btn" data-dt-version="20.0" data-dt-version_code="200000"
       href="https://d.apkpure.net/b/APK/com.richmat.rmcontrol2?versionCode=200000&amp;nc=armeabi-v7a"></a>
    <li data-dt-type="CpuInfo"><div class="label one-line">Architecture</div>
      <div class="value one-line">universal</div></li>
    """

    variants, architectures = parse_download_html(document, "21.3.7", "213700")

    assert [variant.architecture for variant in variants] == ["arm64-v8a", "armeabi-v7a"]
    assert architectures == "arm64-v8a; armeabi-v7a; universal"
