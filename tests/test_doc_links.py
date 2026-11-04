"""Relative links and anchors in the README and docs resolve (#747)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_doc_links


@pytest.mark.parametrize(
    "path",
    check_doc_links.documents(),
    ids=lambda path: str(path.relative_to(check_doc_links.ROOT)),
)
def test_relative_links_resolve(path) -> None:
    assert check_doc_links.broken_links(path) == []


@pytest.mark.parametrize(
    ("heading", "slug"),
    [
        ("_Setup_", "setup"),
        ("**Bold** and *italic*", "bold-and-italic"),
        ("Malouf &amp; Lucid", "malouf--lucid"),
        ("`ergomotion_4` alias", "ergomotion_4-alias"),
        ("Detection / Setup", "detection--setup"),
        ("[Okimat](beds/okin-nframe.md) profile", "okimat-profile"),
    ],
)
def test_anchor_slugs_follow_the_rendered_heading(heading: str, slug: str) -> None:
    assert check_doc_links._slug(heading) == slug


@pytest.mark.parametrize(
    "text",
    [
        "````\n```\n[a](missing.md)\n````\n",
        "```\n```not-a-close\n[a](missing.md)\n```\n",
    ],
    ids=["shorter-fence", "fence-with-text"],
)
def test_links_inside_code_blocks_are_ignored(tmp_path: Path, text: str) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text(text, encoding="utf-8")
    assert check_doc_links.broken_links(doc) == []


@pytest.mark.parametrize(
    "text",
    ["[a](missing.md)\n", "[a][guide]\n\n[guide]: missing.md\n"],
    ids=["inline", "reference"],
)
def test_missing_targets_are_reported(tmp_path: Path, text: str) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text(text, encoding="utf-8")
    assert check_doc_links.broken_links(doc) == ["missing.md: missing file"]


def test_repeated_heading_slugs_skip_taken_suffixes(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text("# Setup\n\n# Setup-1\n\n# Setup\n", encoding="utf-8")
    assert check_doc_links.anchors(doc) == {"setup", "setup-1", "setup-2"}
