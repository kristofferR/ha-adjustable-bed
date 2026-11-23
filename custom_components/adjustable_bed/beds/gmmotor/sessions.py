"""GM app intentions that outlive one HA Bluetooth controller instance."""

from dataclasses import dataclass
from typing import Final

from homeassistant.core import HomeAssistant

from ...app_session import app_session
from ...controller_state import StateKey

# Whether live sleep data is requested; the switch shows it.
LIVE_ENABLED: Final = StateKey[bool | None]("gmmotor_sleep_live_enabled")


def product_ui_states(hass: HomeAssistant, address: str, profile: str) -> dict[int, int]:
    """Keep each app side's gesture flags within the selected product session."""
    return app_session(hass, address, ("gmmotor", profile), dict[int, int])


@dataclass
class SleepIntent:
    """A local monitoring request, cleared by intentional connection teardown."""

    live_enabled: bool = False


def sleep_intent(hass: HomeAssistant, address: str, *, sxb: bool) -> SleepIntent:
    """Keep MM/SXB monitoring intent separate from connection-owned work."""
    return app_session(hass, address, ("gmmotor_sleep", sxb), SleepIntent)
