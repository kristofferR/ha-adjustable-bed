"""The five apps' finite scan-name admission, offered only as an app hint."""

from .models import MODEL_CHOICES

_PREFIXES = (
    "200IV2", "208A14", "209A05", "200U&I", "FC200", "MPE_HJ001", "MPE_HJ002",
    "MPE_HJ003", "MPE_HJ005", "MPE_HJ006", "MPE_HJ008", "MPE_HJ010", "MPE_HJ011",
    "MPE_HJ012", "200I", "400I", "800I", "COOL TOUCH",
)


def matching_apps(name: str | None) -> tuple[str, ...]:
    if not isinstance(name, str) or len(name.strip()) < 4:
        return ()
    upper = name.upper()
    return tuple(
        app for app, layouts in MODEL_CHOICES.items()
        if upper.startswith(_PREFIXES) or upper[:4] in layouts
    )
