"""L1 Limoss DD: the legacy route, Limoss Remote and FSM Relax."""

from __future__ import annotations

import re

from custom_components.adjustable_bed.codec.limoss import decrypt
from custom_components.adjustable_bed.profiles.limoss import LimossProfile
from tests.codec_families import CodecFamily, CodecGuide
from tests.limoss_vectors import FROZEN_BODIES, WIRE_FRAMES

_WIRES = frozenset(wire for rows in WIRE_FRAMES.values() for _, _, wire in rows)
_PLAINTEXTS = frozenset(decrypt(bytes.fromhex(wire)[1:9]).hex() for wire in _WIRES)
# Ten-byte wire frames and the eight-byte plaintext blocks they encrypt.
_SPELLED = re.compile(r"`(DD(?: [0-9A-F]{2}){9}|AA(?: [0-9A-F]{2}){7})`")


FAMILY = CodecFamily(
    profiles={LimossProfile: FROZEN_BODIES},
    bed_types=frozenset({"fsm_relax", "limoss", "limoss_remote"}),
    guide=CodecGuide(
        path="docs/beds/limoss.md",
        spelled=lambda text: {value.replace(" ", "").lower() for value in _SPELLED.findall(text)},
        frozen=_WIRES | _PLAINTEXTS,
    ),
)
