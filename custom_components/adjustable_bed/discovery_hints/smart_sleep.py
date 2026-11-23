"""Smart Sleep scans require company89 AND a case-sensitive name substring."""
from ._hints import manufacturer

HINTS = (manufacturer(89, bed_types={"smart_sleep"}),)
