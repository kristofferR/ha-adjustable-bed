"""Small family interfaces that entity platforms look up with ``controller_as()``.

They live apart from the controller modules so a platform can test for a
family without importing (and loading) every controller that implements it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class YogaPresetActions(ABC):
    """A bed whose app offers a yoga preset."""

    @property
    @abstractmethod
    def supports_preset_yoga(self) -> bool:
        """Return whether this bed's model offers the yoga preset."""

    @abstractmethod
    async def preset_yoga(self) -> None:
        """Move the bed to its yoga position."""


class SolaceAudioActions(ABC):
    """The Solace music and audio surface."""

    @property
    @abstractmethod
    def supports_solace_audio(self) -> bool:
        """Return whether this profile exposes music and volume controls."""

    @abstractmethod
    async def solace_music_toggle(self) -> None:
        """Toggle the music."""

    @abstractmethod
    async def solace_music_off(self) -> None:
        """Stop the music."""


class MotionBedModuleActions:
    """A Motion Bed hub, whose module controls appear as the hub reports them."""


class StarcodeGroupMember(ABC):
    """An AdjustableM5X5 main, M1X12 main or ELEVATE lift the lift group drives."""

    @property
    @abstractmethod
    def ready(self) -> bool:
        """Return whether the member is connected and ready for group motion."""

    @property
    @abstractmethod
    def session_generation(self) -> int:
        """Identify the notification session a delayed group action retains."""

    @abstractmethod
    async def interrupt(self) -> None:
        """Send the app's interrupt frame, which ends the member's current motion."""

    @abstractmethod
    async def move_both_up(self) -> None:
        """Raise both actuators."""

    @abstractmethod
    async def move_both_down(self) -> None:
        """Lower both actuators."""
