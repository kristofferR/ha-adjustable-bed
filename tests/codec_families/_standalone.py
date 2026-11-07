"""Bed types that stay standalone controllers, each with its reason (#745).

A standalone bed type has no wire format shared with another bed type, no bed
commands at all, or frames built by a codec under a runtime catalog that has no
fixed per-key vectors. It is not a profile over a codec family.
"""

from __future__ import annotations

STANDALONE: dict[str, str] = {
    "casper_remote": "remote without bed commands",
    "casper_sleep_mm": "sleep sensor without bed commands; frames use codec/sleep_envelope.py",
    "casper_sleep_sxb": "sleep sensor without bed commands; frames use codec/sleep_envelope.py",
    "furnimove": "frames use codec/keeson.py; the per-handset FurniMove key catalog"
    " and its combined-key frames stay controller code",
    "gmmotor": "frames use codec/richmat.py; the GM Control product catalog, its P1"
    " service selection and its menu session stay controller code",
    "gmmotor_sleep_mm": "sleep sensor without bed commands; frames use codec/sleep_envelope.py",
    "gmmotor_sleep_sxb": "sleep sensor without bed commands; frames use codec/sleep_envelope.py",
    "hush_remote": "remote without bed commands",
    "hush_sleep_mm": "sleep sensor without bed commands; frames use codec/sleep_envelope.py",
    "hush_sleep_sxb": "sleep sensor without bed commands; frames use codec/sleep_envelope.py",
    "leggett_gen2": "own wire format",
    "linak": "own wire format",
    "logicdata": "own wire format",
    "logicdata_air_pump": "own wire format",
    "octo": "own wire format",
    "okin_ore": "one fixed command table over codec/okin_ore.py, which the BOX1220 routes of"
    " sleepys_elite_app and starcode_abm5_4 also send; no app profile",
    "remacro": "own wire format",
    "richmat_sleep_receiver": "sleep receiver without bed commands; own FA crc8 frames",
    "reverie": "own wire format",
    "reverie_nightstand": "own wire format",
    "reverie_pairlink": "own wire format behind a Pairlink session",
    "sleep_number": "own wire format",
    "sleep_number_mcr": "own wire format",
    "sleepstar": "a CB37 sleep-monitor session that carries codec/okin_5a.py StarCode frames"
    " in its AA 00 00 09 02 envelope; the envelope, sleep-monitor and MODBUS environment"
    " frames have no codec",
    "sleeptracker": "own wire format",
    "sleepys_box24": "own wire format",
    "sleepys_elite_app": "a frozen per-selector route table whose payloads codec/okin_nframe.py,"
    " codec/okin_5a.py, codec/okin_ore.py and codec/keeson.py build, so no one family's"
    " profile class fits it",
    "starcode_m1x12": "each connection picks codec/okin_5a.py StarCode or codec/okin_nframe.py"
    " legacy frames from the Device Information manufacturer; the app's key catalog, sender"
    " session and notification parsers stay controller code",
    "starcode_m5x5": "each connection picks codec/okin_5a.py StarCode or codec/okin_nframe.py"
    " legacy frames from the Device Information manufacturer; the app's key catalog, sender"
    " session and notification parsers stay controller code",
    "suta": "own wire format",
    "svane": "the default Svane Remote route writes LinonPI multi-service frames and the"
    " jensen_linon route the Jensen app's one-byte frames; the JMC400 route and the lamp"
    " frames are built by codec/jmc.py from the SVANE_REMOTE profile",
    "timotion_ahf": "own wire format",
}
