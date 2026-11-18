"""Frozen Rize Beds 1.4.2 (57) vectors from the accepted app report.

Artifact 4a774ab1a19a618bfdfbbc2591eaabc5852198ca63c0c0dfb6b26481bbcde0b7;
manifest f1138b823b30bb37708a652c2065ddd3326590298446b3e32d7b8cae130feb44.
Static artifact outputs, not hardware captures. No integration-built expectations.
"""

import json
from pathlib import Path

VECTORS = json.loads((Path(__file__).parent / "fixtures/rize_vectors.json").read_text())
COMMANDS = json.loads((Path(__file__).parent / "fixtures/rize_commands.json").read_text())
FROZEN_PAYLOADS = frozenset(
    row["expected_bytes"][20:] for row in VECTORS if row["builder"] == "bed_frame"
)
