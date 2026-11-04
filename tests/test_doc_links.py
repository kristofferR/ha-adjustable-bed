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
