"""AR Connect headboard roles and source-owned startup order."""

from typing import Final

from ..codec.ar_connect import guid

ROLES: Final = {
    "version": ("00fa", "fa01"),
    "clock": ("00fc", "fc01"),
    "config": ("00fc", "fc02"),
    "status": ("00fc", "fc03"),
    "advertising": ("00fc", "fc04"),
    "pairing": ("00fc", "fc05"),
    "routine": ("00fd", "fd01"),
    "remove": ("00fd", "fd02"),
    "mood_state": ("00fe", "fe01"),
    "mood_values": ("00fe", "fe02"),
    "live_state": ("00ff", "ff01"),
    "live_values": ("00ff", "ff02"),
}
TRANSPORTS: Final = {key: (guid(service), guid(char)) for key, (service, char) in ROLES.items()}
NOTIFY_ORDER: Final = ("version", "live_state", "live_values", "routine", "mood_state", "status")
INITIAL_READS: Final = (
    "version",
    "live_state",
    "live_values",
    "routine",
    "mood_state",
    "mood_values",
)
