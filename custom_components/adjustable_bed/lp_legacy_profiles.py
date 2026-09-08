"""Explicit control surfaces from the frozen legacy L&P 2.2.1 app report.

Labels describe the app's controls, not verified physical motor semantics.
The catalog deliberately does not share newer Richmat remote-code mappings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Literal, TypedDict, cast

LpLegacyState = Literal[1, 2, 3, 4, 5]
LpLegacyConfidence = Literal["INFERRED", "TENTATIVE", "UNKNOWN"]

LP_LEGACY_PROFILE_CODES = (
    "6BRM",
    "A2RM",
    "A3RM",
    "A6RM",
    "A7RM",
    "B1RM",
    "B2RM",
    "B6RM",
    "B6RU",
    "B7RM",
    "B8RM",
    "B8TT",
    "B9TT",
    "BERM",
    "BZRM",
    "D2RM",
    "D4RM",
    "GMRM",
    "GVRM",
    "I0RM",
    "I1RM",
    "I2RM",
    "I3RM",
    "I4RM",
    "I5RM",
    "I6RM",
    "I7RM",
    "I8RM",
    "I9RM",
    "IARM",
    "IBRM",
    "ICRM",
    "IDRM",
    "IERM",
    "IFRM",
    "M3RM",
    "M5RM",
    "M9RM",
    "MLRM",
    "MMRM",
    "MRRM",
    "O1RM",
    "O2RM",
    "O3RM",
    "O4RM",
    "OMRM",
    "ONRM",
    "OORM",
    "OPRM",
    "P9RM",
    "R2RM",
    "R5RM",
    "R6RM",
    "S9RM",
    "SARM",
    "T1RM",
    "THRM",
    "TLRM",
    "TWRM",
    "TZRM",
    "U1RM",
    "U2RM",
    "U3RM",
    "U4RM",
    "U5RM",
    "U7RM",
    "U8RM",
    "U9RM",
    "UARM",
    "UBRM",
    "UCRM",
    "UERM",
    "UFRM",
    "UGRM",
    "UHRM",
    "UIRM",
    "UJRM",
    "UKRM",
    "ULRM",
    "UMRM",
    "UNRM",
    "UORM",
    "UPRM",
    "V1RM",
    "V2RM",
    "V3RM",
    "V4RM",
    "V5RM",
    "V6RM",
    "V7RM",
    "V8RM",
    "V9RM",
    "VARM",
    "VBRM",
    "VCRM",
    "VDRM",
    "VERM",
    "VFRM",
    "VGRM",
    "VHRM",
    "VIRM",
    "VJRM",
    "VKRM",
    "VLRM",
    "VMRM",
    "VNRM",
    "W2RM",
    "X1RM",
    "Y2RM",
    "Y3RM",
    "ZR00",
    "ZR01",
    "ZR10",
    "ZR11",
    "ZR20",
    "ZR30",
    "ZR40",
    "ZR50",
    "ZR60",
    "ZR70",
    "ZR80",
    "ZRI0",
)


@dataclass(frozen=True, slots=True)
class LpLegacyAction:
    """One compiled event: None means undefined mode; empty bytes mean no write."""

    source_id: str
    token: str
    legacy: bytes | None
    framed: bytes | None
    state: LpLegacyState


@dataclass(frozen=True, slots=True)
class LpLegacyControl:
    """One app button, including its distinct press and completion events."""

    key: str
    label: str
    confidence: LpLegacyConfidence
    press: LpLegacyAction
    release: LpLegacyAction
    label_basis: str | None = None


@dataclass(frozen=True, slots=True)
class LpLegacyProfile:
    """An exact four-character form code selected explicitly by the user."""

    code: str
    controls: tuple[LpLegacyControl, ...]


class _ActionData(TypedDict):
    source_id: str
    token: str
    legacy: str | None
    framed: str | None
    state: LpLegacyState


class _ControlData(TypedDict):
    key: str
    label: str
    confidence: LpLegacyConfidence
    label_basis: str | None
    press: _ActionData
    release: _ActionData


class _ProfileData(TypedDict):
    code: str
    controls: list[_ControlData]


class _CatalogData(TypedDict):
    profiles: list[_ProfileData]


def _load_action(data: _ActionData) -> LpLegacyAction:
    return LpLegacyAction(
        source_id=data["source_id"],
        token=data["token"],
        legacy=bytes.fromhex(data["legacy"]) if data["legacy"] is not None else None,
        framed=bytes.fromhex(data["framed"]) if data["framed"] is not None else None,
        state=data["state"],
    )


@cache
def _load_profiles() -> MappingProxyType[str, LpLegacyProfile]:
    data = cast(
        _CatalogData,
        json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8")),
    )
    return MappingProxyType(
        {
            profile["code"]: LpLegacyProfile(
                code=profile["code"],
                controls=tuple(
                    LpLegacyControl(
                        key=control["key"],
                        label=control["label"],
                        confidence=control["confidence"],
                        label_basis=control["label_basis"],
                        press=_load_action(control["press"]),
                        release=_load_action(control["release"]),
                    )
                    for control in profile["controls"]
                ),
            )
            for profile in data["profiles"]
        }
    )


def get_lp_legacy_profile(code: str) -> LpLegacyProfile:
    """Return the selected surface without falling back to another remote."""
    normalized = code.strip().upper()
    if normalized not in LP_LEGACY_PROFILE_CODES:
        raise ValueError(f"Unknown legacy L&P profile: {code}")
    return _load_profiles()[normalized]
