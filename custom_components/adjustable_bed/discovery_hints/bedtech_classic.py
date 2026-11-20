"""Bed Tech's concrete names admit discovery, without choosing an app or layout."""

from ..profiles.bedtech_classic import SURFACE_IDS
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (
    names(
        *(model.upper() for model in SURFACE_IDS if len(model) == 4),
        bed_types={"richmat", "bedtech_classic"},
    ),
    names("Cool Touch", bed_types={"richmat", "bedtech_classic"}),
    names("HJ_Bed", bed_types={"richmat", "bedtech_classic"}, anywhere=True),
)
