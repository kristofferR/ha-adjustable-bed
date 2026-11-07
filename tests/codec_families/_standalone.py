"""Bed types that stay standalone controllers, each with its reason (#745).

A standalone bed type has no wire format shared with another bed type, no bed
commands at all, or frames built by a codec under a runtime catalog that has no
fixed per-key vectors. It is not a profile over a codec family.
"""

from __future__ import annotations

STANDALONE: dict[str, str] = {
    "casper_remote": "remote without bed commands",
    "casper_sleep_mm": "sleep sensor without bed commands",
    "casper_sleep_sxb": "sleep sensor without bed commands",
    "eshine": "own wire format",
    "eshine_okin": "command words and requests use codec/okin_nframe.py's 40-bit and"
    " request forms; its 07 04 clock and 07 05 alarm frames have no codec builder",
    "furnimove": "frames use codec/keeson.py; the per-handset FurniMove key catalog"
    " and its combined-key frames stay controller code",
    "gmmotor": "frames use codec/richmat.py; the GM Control product catalog, its P1"
    " service selection and its menu session stay controller code",
    "gmmotor_sleep_mm": "sleep sensor without bed commands",
    "gmmotor_sleep_sxb": "sleep sensor without bed commands",
    "hush_remote": "remote without bed commands",
    "hush_sleep_mm": "sleep sensor without bed commands",
    "hush_sleep_sxb": "sleep sensor without bed commands",
    "isleep": "Kaidi mesh frames",
    "jensen": "own wire format",
    "kaidi": "Kaidi mesh frames",
    "leggett_gen2": "own wire format",
    "leggett_lp_legacy": "own wire format",
    "linak": "own wire format",
    "logicdata": "own wire format",
    "logicdata_air_pump": "own wire format",
    "motosleep": "own wire format",
    "octo": "own wire format",
    "okin_ore": "own wire format",
    "remacro": "own wire format",
    "reverie": "own wire format",
    "reverie_nightstand": "own wire format",
    "reverie_pairlink": "own wire format behind a Pairlink session",
    "sleep_number": "own wire format",
    "sleep_number_mcr": "own wire format",
    "sleepstar": "own wire format",
    "sleeptracker": "own wire format",
    "sleepys_box24": "own wire format",
    "sleepys_elite_app": "own wire format",
    "starcode_m1x12": "own wire format",
    "starcode_m5x5": "own wire format",
    "suta": "own wire format",
    "svane": "own wire format",
    "timotion_ahf": "own wire format",
    "vibradorm": "own wire format",
    "vibradorm_app": "own wire format",
    "vmatbasic": "own wire format",
}
