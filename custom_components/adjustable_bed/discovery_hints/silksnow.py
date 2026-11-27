"""S&S Base's scan terms identify candidates, never a product or app by themselves."""
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (
    names("QRRM", "COOL", "MPE_", "209A", "BED-", bed_types={"silksnow"}, anywhere=True),
)
