"""Shared signals admit discovery; selecting an app remains explicit."""

from ..const import BED_TYPE_RICHMAT, RICHMAT_MH_APP_CATALOGS
from ..profiles.richmat_mh_apps import SURFACE_IDS
from ._hints import Hint, names

# No advertised UUID is required by either app's first-four-character rule.
# Shared transport UUIDs cannot distinguish these apps from existing families.
# The apps compare the ID without regard to case; beds advertise it in upper
# case, so discovery admits only that spelling.
HINTS: tuple[Hint, ...] = (
    names(
        *(model.upper() for model in SURFACE_IDS if len(model) == 4),
        bed_types={BED_TYPE_RICHMAT, *RICHMAT_MH_APP_CATALOGS},
    ),
    names("HJ_Bed", bed_types={BED_TYPE_RICHMAT, *RICHMAT_MH_APP_CATALOGS}, anywhere=True),
)
