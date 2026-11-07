"""Where each entity sits in the Lovelace card.

Every entity publishes its placement as state attributes, and the card's
discovery buckets entities by them instead of by translation key. An entity's
domain picks its control within a section; ``role`` names it only where the
domain does not (see ``frontend/src/discovery.ts``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

ATTR_CARD_SECTION: Final = "card_section"
ATTR_CARD_ROLE: Final = "card_role"
ATTR_CARD_MOTOR: Final = "card_motor"
ATTR_CARD_SLOT: Final = "card_slot"
CARD_ATTRIBUTES: Final = frozenset({ATTR_CARD_SECTION, ATTR_CARD_ROLE, ATTR_CARD_MOTOR, ATTR_CARD_SLOT})


class CardSection(StrEnum):
    """The card section an entity belongs to."""

    MOTORS = "motors"
    FIRMNESS = "firmness"
    PRESETS = "presets"
    MEMORY = "memory"
    SAVED_POSITIONS = "saved_positions"
    LIGHTING = "lighting"
    MASSAGE = "massage"
    UTILITY = "utility"
    CLIMATE = "climate"
    CONNECTION = "connection"
    # Not shown in the card.
    HIDDEN = "hidden"


class CardRole(StrEnum):
    """An entity's control within its section, where its domain does not say."""

    # Motors: buttons and numbers beside a motor's cover.
    UP = "up"
    DOWN = "down"
    REFERENCE = "reference"
    ESTIMATE = "estimate"
    # A read-only position that is not an angle.
    POSITION = "position"
    STOP = "stop"
    # Memory.
    RECALL = "recall"
    SAVE = "save"
    # Connection.
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    # Massage and lighting timers.
    TIMER = "timer"
    # Lighting.
    STATE = "state"
    LEVEL = "level"
    TOGGLE = "toggle"
    CYCLE = "cycle"
    # A duration that applies as soon as it is set.
    TIMER_MINUTES = "timer_minutes"
    # A duration that applies when TIMER_TOGGLE is pressed.
    PENDING_TIMER_MINUTES = "pending_timer_minutes"
    TIMER_TOGGLE = "timer_toggle"
    MOOD = "mood"
    MOOD_TOGGLE = "mood_toggle"


@dataclass(frozen=True, slots=True)
class CardPlacement:
    """An entity's section, its control there, and the motor or memory slot it serves."""

    section: CardSection
    role: CardRole | None = None
    motor: str | None = None
    slot: int | None = None

    @property
    def attributes(self) -> dict[str, str | int]:
        """Return the state attributes the card reads."""
        attributes: dict[str, str | int] = {ATTR_CARD_SECTION: self.section.value}
        if self.role is not None:
            attributes[ATTR_CARD_ROLE] = self.role.value
        if self.motor is not None:
            attributes[ATTR_CARD_MOTOR] = self.motor
        if self.slot is not None:
            attributes[ATTR_CARD_SLOT] = self.slot
        return attributes


def motor_card(motor: str, role: CardRole | None = None) -> CardPlacement:
    """Place an entity with one motor's controls."""
    return CardPlacement(CardSection.MOTORS, role, motor=motor)


def memory_card(slot: int, *, save: bool = False) -> CardPlacement:
    """Place a memory slot's recall or save button."""
    return CardPlacement(CardSection.MEMORY, CardRole.SAVE if save else CardRole.RECALL, slot=slot)


CARD_HIDDEN: Final = CardPlacement(CardSection.HIDDEN)
# A STOP for the whole side, shown with the motors.
CARD_STOP: Final = CardPlacement(CardSection.MOTORS, CardRole.STOP)
CARD_UTILITY: Final = CardPlacement(CardSection.UTILITY)
CARD_PRESETS: Final = CardPlacement(CardSection.PRESETS)
CARD_MASSAGE: Final = CardPlacement(CardSection.MASSAGE)
CARD_MASSAGE_TIMER: Final = CardPlacement(CardSection.MASSAGE, CardRole.TIMER)
CARD_LIGHTING: Final = CardPlacement(CardSection.LIGHTING)
CARD_LIGHT_LEVEL: Final = CardPlacement(CardSection.LIGHTING, CardRole.LEVEL)
CARD_LIGHT_STATE: Final = CardPlacement(CardSection.LIGHTING, CardRole.STATE)
CARD_LIGHT_TOGGLE: Final = CardPlacement(CardSection.LIGHTING, CardRole.TOGGLE)
CARD_LIGHT_MOOD: Final = CardPlacement(CardSection.LIGHTING, CardRole.MOOD)
CARD_CLIMATE: Final = CardPlacement(CardSection.CLIMATE)
CARD_FIRMNESS: Final = CardPlacement(CardSection.FIRMNESS)
CARD_SAVED_POSITIONS: Final = CardPlacement(CardSection.SAVED_POSITIONS)
