"""Selectable models of the Richmat MH and RUF app profiles, from their catalogs."""

from __future__ import annotations

from typing import Final

from ...const import VARIANT_AUTO
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
}
RICHMAT_MH_VARIANTS_BY_APP: Final[dict[str, dict[str, str]]] = {
    app: {
        VARIANT_AUTO: "Model from the Bluetooth name (first four characters)",
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
