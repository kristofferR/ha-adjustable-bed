"""Sleep Assistant's binary AA and ASCII setting codec."""

from custom_components.adjustable_bed.profiles.sleep_assistant import SleepAssistantProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.test_sleep_assistant_vectors import BUILDERS

FROZEN = frozenset(row["expected_bytes"] for row in BUILDERS)
FAMILY = CodecFamily(
    profiles={SleepAssistantProfile: {"sleep_assistant": FROZEN}},
    bed_types=frozenset({"sleep_assistant"}),
    guide=CodecGuide(
        path="docs/beds/sleep-assistant.md",
        frozen=FROZEN,
        spelled=spelled_frames(r"`((?:[0-9A-Fa-f]{2} ){1,}[0-9A-Fa-f]{2})`"),
    ),
)
