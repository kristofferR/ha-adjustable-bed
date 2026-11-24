"""The five apps' finite scan-name admission, offered only as an app hint."""

from ...codec.richmat import TRANSPORTS
from ...profiles import dreamlab
from ...profiles.lp2 import scan_matches as lp2_matches
from ...profiles.richmat import CLASSIC_TRANSPORTS
from ...profiles.richmat_resource_apps import APPS, scan_matches
from .models import MODEL_CHOICES

_PREFIXES = (
    "200IV2", "208A14", "209A05", "200U&I", "FC200", "MPE_HJ001", "MPE_HJ002",
    "MPE_HJ003", "MPE_HJ005", "MPE_HJ006", "MPE_HJ008", "MPE_HJ010", "MPE_HJ011",
    "MPE_HJ012", "200I", "400I", "800I", "COOL TOUCH",
)


def matching_apps(name: str | None, service_uuids: tuple[str, ...] = ()) -> tuple[str, ...]:
    if not isinstance(name, str) or len(name.strip()) < 4:
        return ()
    upper = name.upper()
    matches = tuple(
        app for app, layouts in MODEL_CHOICES.items()
        if app != dreamlab.APP and (
            lp2_matches(name) if app == "lp2"
            else scan_matches(name) if app in APPS
            else upper.startswith(_PREFIXES) or upper[:4] in layouts
        )
    )
    if dreamlab.scan_matches(name) and any(
        TRANSPORTS[route].service_uuid in service_uuids for route in CLASSIC_TRANSPORTS
    ):
        return (*matches, dreamlab.APP)
    return matches
