"""Galaxy's case-sensitive scan names, retaining HA's shared-service guards.

The APK scans by name keywords, not by GATT UUID. In particular W5 is shared
with non-bed products and is only selected after connecting to a bed candidate.
Substring admission is retained in beds.galaxy.discovery; HA's prefix gate
cannot express it, so manual setup covers names matching only in the middle.
"""

from ..beds.galaxy.discovery import SCAN_CODES
from ..beds.goodvibe.discovery import KEYWORDS
from ._hints import Case, names

HINTS = (
    names(*SCAN_CODES, *KEYWORDS, bed_types={"galaxy"}, case=Case.EXACT, anywhere=True),
)
