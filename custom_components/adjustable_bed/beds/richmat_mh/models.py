"""Selectable models of the Richmat MH and RUF app profiles, from their catalogs."""

from __future__ import annotations

from typing import Final

from ...const import AUTOMATIC_LABEL, VARIANT_AUTO
from ...profiles.richmat_mh_apps import APPS as MH_APP_POLICIES
from ...profiles.richmat_mh_apps import models as mh_app_models
from ...profiles.richmat_mh_apps import variants as mh_app_variants
from ..ruf_richmat.models import MODEL_IDS as _RUF_MODEL_IDS
from . import catalog as _catalog


# Richmat MH app model choices, from the generated catalog: each app's picker dialog
# and setup wizard, Revive's six short manual identifiers, and every model for
# Idealbed, whose manual dialog accepts any valid identifier. "auto" applies the
# app's name rule: the first four characters of the raw Bluetooth name, lowercased,
# name the model; QRRM asks for a choice.
def _richmat_mh_model_choices(app: str) -> tuple[tuple[str, str], ...]:
    choices: dict[str, str] = dict(_catalog.PICKERS.get(app, ()))
    manual = _catalog.MANUAL_SHORT_IDS.get(app, ())
    if app in _catalog.MANUAL_ANY_MODEL:
        manual = sorted(_catalog.MODELS[app])
    for model in manual:
        choices.setdefault(model, model.upper())
    return tuple(choices.items())


RICHMAT_MH_MODEL_CHOICES: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    **{app: _richmat_mh_model_choices(app) for app in _catalog.MODELS},
    **{app: tuple((model, model.upper()) for model in models)
       for app, models in _RUF_MODEL_IDS.items()},
    **{app: tuple((model, model.upper()) for model in mh_app_models(app))
       for app in MH_APP_POLICIES},
}
RICHMAT_MH_VARIANTS_BY_APP: Final[dict[str, dict[str, str]]] = {
    app: {
        VARIANT_AUTO: AUTOMATIC_LABEL,
        **{
            f"model_{model}": label if label == model.upper() else f"{label} ({model.upper()})"
            for model, label in choices
        },
    }
    for app, choices in RICHMAT_MH_MODEL_CHOICES.items()
}
for _app in ("wsilver2", "americanstar", "tx"):
    RICHMAT_MH_VARIANTS_BY_APP[_app].update({
        f"model_{model}_mattress": f"{model.upper()} with normal mattress (explicit opt-in)"
        for model in _RUF_MODEL_IDS[_app]
    })
for _app in MH_APP_POLICIES:
    RICHMAT_MH_VARIANTS_BY_APP[_app] = {
        **mh_app_variants(_app),
        "sleep": (
            "Separate sleep and intervention receiver" if _app == "bedtech_classic"
            else "Separate HJ_Bed sleep and intervention receiver"
        ),
    }
