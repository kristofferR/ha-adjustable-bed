"""Resolve saved SmartBed receiver routes before any Bluetooth retry."""

from collections.abc import Mapping

from ...const import CONF_CB24_BED_SELECTION, CONF_PAIR_MODE, PAIR_MODE_SINGLE_ADDRESS
from ...errors import setup_stopped


def verified_ab(capabilities: object) -> bool:
    """Only the persisted receiver profile proves an automatic AB route."""
    if not isinstance(capabilities, Mapping):
        return False
    snapshot = capabilities.get("okin_cb24")
    return isinstance(snapshot, Mapping) and snapshot.get("profile") == "cb24_ab"


def receiver_variant(data: Mapping[str, object], variant: str | None = None) -> str:
    selected = variant if variant not in (None, "auto") else data.get("protocol_variant", "auto")
    if selected in (None, "auto"):
        if verified_ab(data.get("capabilities")):
            return "cb24_ab"
        if data.get(CONF_CB24_BED_SELECTION, 0) != 0 or data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS:
            raise setup_stopped("smartbed_choose_receiver")
    return selected if isinstance(selected, str) else "auto"


def validate_entry(data: Mapping[str, object]) -> None:
    receiver_variant(data)
