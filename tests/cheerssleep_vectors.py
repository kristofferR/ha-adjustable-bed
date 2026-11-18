"""CheersSleep 2.7.0 literal frames and independent numeric catalog expansions.

Numeric fixtures expand the app's signed stores and side selector without
importing the production encoder.
"""

import json
from pathlib import Path

from custom_components.adjustable_bed.codec import cheerssleep as codec

ROOT = Path(__file__).parent / "fixtures/cheerssleep"
VECTORS = json.loads((ROOT / "vectors.json").read_text())
NUMERIC = json.loads((ROOT / "numeric.json").read_text())
AUXILIARY = json.loads((ROOT / "auxiliary.json").read_text())
MODELS = json.loads((ROOT / "models.json").read_text())


def encode(row: dict) -> bytes:
    return {"p1": codec.p1, "normal": codec.normal, "setting": codec.setting, "query": codec.query}[
        row["builder"]
    ](**row["inputs"])
