"""Relative links and anchors in the README and docs resolve (#747)."""

from __future__ import annotations

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
