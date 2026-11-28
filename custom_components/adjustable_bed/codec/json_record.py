"""Unwrapped compact UTF-8 JSON records shared by proven app encoders."""

import json
from collections.abc import Mapping


def compact_json(payload: Mapping[str, object]) -> bytes:
    return json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=False).encode()
