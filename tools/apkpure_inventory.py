#!/usr/bin/env python3
"""Record current APKPure metadata for a local package inventory."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "Mozilla/5.0 (compatible; ha-adjustable-bed APK inventory)"
PAGE_DATA_MARKER = "window.apkpure = {pageData: "
JSON_LD_PATTERN = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
CPU_INFO_PATTERN = re.compile(
    r'data-dt-type="CpuInfo".*?<div class="value[^"]*">\s*([^<]+?)\s*</div>',
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class APKPureVariant:
    """One architecture-specific APKPure download variant."""

    version_name: str = ""
    version_code: str = ""
    architecture: str = ""
    file_size_bytes: str = ""
    url: str = ""


@dataclass
class APKPureRecord:
    """APKPure evidence for one package ID."""

    package_id: str
    lookup_date: str
    status: str = ""
    error: str = ""
    title: str = ""
    version_name: str = ""
    version_code: str = ""
    release_date: str = ""
    architectures: str = ""
    url: str = ""
    download_url: str = ""
    variants: list[APKPureVariant] = field(default_factory=list)


class DownloadVariantParser(HTMLParser):
    """Collect APKPure download links and their machine-readable attributes."""

    def __init__(self) -> None:
        super().__init__()
        self.variants: list[APKPureVariant] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attributes = {key: value or "" for key, value in attrs}
        if "download-btn" not in attributes.get("class", "").split():
            return
        href = unescape(attributes.get("href", ""))
        architecture = parse_qs(urlparse(href).query).get("nc", [""])[0]
        version_name = attributes.get("data-dt-version", "")
        version_code = attributes.get("data-dt-version_code", "")
        if not version_name and not version_code:
            return
        self.variants.append(
            APKPureVariant(
                version_name=version_name,
                version_code=version_code,
                architecture=architecture,
                file_size_bytes=attributes.get("data-dt-file_size", ""),
                url=href,
            )
        )


def parse_detail_html(document: str) -> dict[str, str]:
    """Extract stable app metadata from an APKPure detail page."""
    marker_index = document.find(PAGE_DATA_MARKER)
    if marker_index < 0:
        raise ValueError("APKPure pageData was absent")
    json_start = marker_index + len(PAGE_DATA_MARKER)
    page_data, _ = json.JSONDecoder().raw_decode(document[json_start:])

    application: dict[str, Any] = {}
    for match in JSON_LD_PATTERN.finditer(document):
        try:
            candidate = json.loads(unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        candidates = candidate if isinstance(candidate, list) else [candidate]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") in {
                "MobileApplication",
                "SoftwareApplication",
            }:
                application = item
                break
        if application:
            break

    return {
        "package_id": str(page_data.get("packageName", "")),
        "title": str(application.get("name", "")),
        "version_name": str(page_data.get("versionName", "")),
        "version_code": str(page_data.get("versionCode", "")),
        "release_date": str(application.get("datePublished", "")),
    }


def parse_download_html(
    document: str,
    version_name: str,
    version_code: str,
) -> tuple[list[APKPureVariant], str]:
    """Extract the variants matching the latest APKPure release."""
    parser = DownloadVariantParser()
    parser.feed(document)
    variants = [
        variant
        for variant in parser.variants
        if (not version_code or variant.version_code == version_code)
        and (not version_name or variant.version_name == version_name)
    ]
    unique: dict[tuple[str, str], APKPureVariant] = {}
    for variant in variants:
        unique[(variant.architecture, variant.url)] = variant
    variants = sorted(unique.values(), key=lambda item: (item.architecture, item.url))
    architecture_values = {item.architecture for item in variants if item.architecture}
    for match in CPU_INFO_PATTERN.finditer(document):
        architecture_values.update(
            value.strip() for value in re.split(r"[,;]", unescape(match.group(1)))
        )
    architectures = "; ".join(sorted(value for value in architecture_values if value))
    return variants, architectures


def fetch(package_id: str, timeout: float, retries: int, throttle: float) -> APKPureRecord:
    """Fetch detail and architecture metadata for one package ID."""
    record = APKPureRecord(package_id=package_id, lookup_date=date.today().isoformat())
    try:
        document, record.url = fetch_text(
            f"https://apkpure.com/app/{package_id}", timeout, retries
        )
    except HTTPError as err:
        if err.code == 404:
            record.status = "not_found"
        elif err.code == 410:
            record.status = "removed"
        else:
            record.status = "fetch_error"
        record.error = f"HTTP {err.code}: {err.reason}"
        return record
    except (URLError, TimeoutError) as err:
        record.status = "fetch_error"
        record.error = str(err)
        return record

    try:
        metadata = parse_detail_html(document)
    except (json.JSONDecodeError, ValueError) as err:
        record.status = "parse_error"
        record.error = str(err)
        return record
    if metadata["package_id"] != package_id:
        record.status = "package_mismatch"
        record.error = f"page reported {metadata['package_id']!r}"
        return record
    record.title = metadata["title"]
    record.version_name = metadata["version_name"]
    record.version_code = metadata["version_code"]
    record.release_date = metadata["release_date"]
    if not record.version_name and not record.version_code:
        record.status = "unavailable"
        record.error = "detail page has no current downloadable version"
        return record
    record.status = "available"

    time.sleep(throttle)
    try:
        download_document, record.download_url = fetch_text(
            f"https://apkpure.net/app/{package_id}/download", timeout, retries
        )
        record.variants, record.architectures = parse_download_html(
            download_document,
            record.version_name,
            record.version_code,
        )
    except (HTTPError, URLError, TimeoutError) as err:
        record.error = f"download metadata: {err}"
    return record


def fetch_text(url: str, timeout: float, retries: int) -> tuple[str, str]:
    """Fetch UTF-8 HTML with bounded retry handling and return the final URL."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS hosts
                return response.read().decode("utf-8", errors="replace"), response.geturl()
        except HTTPError as err:
            if err.code < 500 and err.code != 429:
                raise
            last_error = err
        except (URLError, TimeoutError) as err:
            last_error = err
        if attempt < retries:
            time.sleep(2**attempt)
    if last_error is None:
        raise RuntimeError("request failed without an error")
    raise last_error


def load_package_ids(path: Path) -> list[str]:
    """Load sorted unique package IDs from an inventory CSV."""
    with path.open(newline="", encoding="utf-8") as file:
        package_ids = {row["package_id"].strip() for row in csv.DictReader(file)}
    return sorted(package_id for package_id in package_ids if package_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="inventory packages.csv")
    parser.add_argument("--output", type=Path, required=True, help="JSON evidence output")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--throttle", type=float, default=0.2)
    parser.add_argument("--limit", type=int, default=0, help="smoke-test only")
    args = parser.parse_args()

    package_ids = load_package_ids(args.input)
    if args.limit:
        package_ids = package_ids[: args.limit]
    records: list[APKPureRecord] = []
    for index, package_id in enumerate(package_ids, start=1):
        print(f"[{index}/{len(package_ids)}] {package_id}", file=sys.stderr)
        records.append(fetch(package_id, args.timeout, args.retries, args.throttle))
        time.sleep(args.throttle)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps([asdict(record) for record in records], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
