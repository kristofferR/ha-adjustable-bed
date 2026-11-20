"""SleepIQ has two independent codecs selected by the bed generation."""

from custom_components.adjustable_bed.profiles.sleepiq import SleepIQProfile
from tests.codec_families import CodecFamily
from tests.sleepiq_vectors import FUZION, MCR

FAMILY = CodecFamily(
    profiles={SleepIQProfile: {"fuzion": FUZION, "mcr": MCR}},
    bed_types=frozenset({"sleep_number", "sleep_number_mcr"}),
)
