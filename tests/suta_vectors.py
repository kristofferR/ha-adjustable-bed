"""Frozen production codec literals from accepted SUTA 3.20.0, unit128.

This harness builds through production codecs. It does not invoke the artifact
audit oracle, import APK tooling, or require the private acquisition corpus.
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent / "fixtures/suta"
VECTORS = json.loads((ROOT / "vectors.json").read_text())
BINARY_LITERALS = json.loads((ROOT / "binary_literals.json").read_text())
