"""Sven & Son tables from shipped models and Richmat encoders."""

from custom_components.adjustable_bed.codec.richmat import command
from custom_components.adjustable_bed.profiles import sven as p
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    models = _table(
        ("Model", "Actuators", "Bed light", "Memory positions"),
        (
            (
                model.label,
                ", ".join(model.axes),
                "Toggle" if "light_toggle" in (model.profile.codes or {}) else "None",
                str(len(model.profile.memory)),
            )
            for model in p.MODELS.values()
        ),
    )
    transport = _table(
        ("Priority", "Service", "Writable characteristic"),
        ((str(i), service, char) for i, (service, char) in enumerate(p.TARGETS, 1)),
    )
    timing = _table(
        ("Operation", "Timing"),
        (
            ("Tap", f"One command; End after {p.TAP_MS} ms"),
            (
                "Hold",
                f"Immediate command; {p.REFRESH_MS} ms refresh; End on release; {p.HOLD_LIMIT_MS} ms maximum",
            ),
            (
                "Memory save",
                f"One confirmed Save action (app hold threshold {p.SAVE_THRESHOLD_MS} ms)",
            ),
            (
                "Massage off",
                f"Head then foot; each required step, {p.TAP_MS} ms, End, {p.TAP_MS} ms",
            ),
            ("Optional massage duration", ", ".join(map(str, p.TIMER_OPTIONS)) + " minutes, selected while active; fixed deadline"),
            (
                "Massage allowance / rest",
                f"{p.MASSAGE_LIMIT_S // 60} / {p.MASSAGE_REST_S // 60} minutes",
            ),
        ),
    )
    rows = []
    for model in p.MODELS.values():
        for name, code in (model.profile.codes or {}).items():
            rows.append((model.label, name, _hex(model.profile.frame(code))))
        for slot, (recall, save) in enumerate(model.profile.memory, 1):
            rows.extend(
                (
                    (model.label, f"Memory {slot} recall", _hex(command(recall))),
                    (model.label, f"Memory {slot} save", _hex(command(save))),
                )
            )
    rows.append(("All", "End", _hex(command(0x6E))))
    return _block(models, transport, timing, _table(("Model", "Control", "Frame"), rows))


BLOCKS = [("docs/beds/richmat.md", "sven-controls", render)]
