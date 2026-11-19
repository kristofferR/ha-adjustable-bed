"""Tables from the two shipped app catalogs, without merging capabilities."""

from custom_components.adjustable_bed.beds.richmat_mh.app_catalog import catalog, mode_groups
from custom_components.adjustable_bed.codec import richmat
from custom_components.adjustable_bed.profiles.richmat_mh_apps import APPS, models

from ._common import _block, _table


def render() -> str:
    lines = []
    for app, profile in APPS.items():
        lines.append(f"**{profile.label}**")
        records = catalog(app)
        permitted = set(models(app))
        groups: dict[tuple[str, str, str, int, int], list[str]] = {}
        for model, record in records.items():
            if model not in permitted:
                continue
            for control in record.controls:
                key = (control.route, control.kind, control.label, control.code, control.keep_ms)
                groups.setdefault(key, []).append(model.upper())
        lines.append(_table(
            ("Models", "Page", "Control", "Gesture", "Mode 0 bytes", "Refresh ms"),
            [(", ".join(identifiers), "Entity" if route == "C" else "Legacy",
              label, kind, richmat.command(code).hex(" ").upper(), str(interval) if interval else "once")
             for (route, kind, label, code, interval), identifiers in groups.items()],
        ))
        lines.append(_table(
            ("Model", "Alarm operands", "Snore operands", "Angle targets", "Motor modes"),
            [(model.upper(), ", ".join(f"{code:02X}" for code in record.features.alarm),
              ", ".join(f"{code:02X}" for code in record.features.snore_list),
              ", ".join(f"{name} {low}..{high}" for _bits, name, low, high, _offset in record.features.angles),
              "; ".join(f"{group}: {', '.join(values)}" for group, values in mode_groups(app, model).items()))
             for model, record in records.items() if model in permitted],
        ))
    return _block(*lines)


BLOCKS = [("docs/beds/richmat.md", "richmat-mh-apps", render)]
