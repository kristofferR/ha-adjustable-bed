"""Shared scan services and substring names, never proof of a remote variant."""

from ._hints import Case, NameHint, ServiceHint

_TYPES = frozenset({"intellibed"})
HINTS = (
    NameHint(patterns=("base-i4", "hhc"), bed_types=_TYPES, case=Case.IGNORE_CASE, anywhere=True),
    ServiceHint(uuid="0000fff0-0000-1000-8000-00805f9b34fb", bed_types=_TYPES),
    ServiceHint(uuid="0000180a-0000-1000-8000-00805f9b34fb", bed_types=_TYPES),
)
