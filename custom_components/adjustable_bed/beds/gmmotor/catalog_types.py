"""Compact generated GM Control runtime table contracts."""

from __future__ import annotations

from typing import Literal

type Phase = Literal["normal", "long", "release"]
type MaterialRow = tuple[str, int, int | None, int | None, int | None, int | None, int]
# Before state, phase, after state, emits, uses long opcode, effective material.
type TransitionRow = tuple[int, Phase, int, bool, bool, int]
type ActionRow = tuple[int, tuple[TransitionRow, ...]]
# Controls, initial flags, light, eight-color palette, repeat, sleep kind,
# sides, alarm name/opcode choices, bottom massage countdown.
type ProfileRow = tuple[
    tuple[int, ...],
    int,
    bool,
    bool,
    bool,
    str,
    tuple[int, ...],
    tuple[tuple[str, int], ...],
    bool,
]
type RouteRow = tuple[str, tuple[str, ...]]
