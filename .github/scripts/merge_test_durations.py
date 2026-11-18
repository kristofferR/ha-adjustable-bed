"""Merge per-shard pytest-split duration files into ``.test_durations``.

The Validate workflow's scheduled and manual runs store each shard's durations
with ``--clean-durations``, so every file holds exactly the tests its shard ran
and their union is the whole suite. Durations are rounded to milliseconds and
written one per line, which keeps the committed file small and its diffs
readable.

    python .github/scripts/merge_test_durations.py durations-*.json > .test_durations
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def merge(paths: list[Path]) -> dict[str, float]:
    durations: dict[str, float] = {}
    for path in paths:
        for test, seconds in json.loads(path.read_text()).items():
            durations[test] = round(seconds, 3)
    return dict(sorted(durations.items()))


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(merge([Path(arg) for arg in argv]), indent=0) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
