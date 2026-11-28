"""Carpe Diem profile tables over the shared Linak codec."""

from itertools import combinations

from custom_components.adjustable_bed.codec.linak import control_frame, selected_sections_frame
from custom_components.adjustable_bed.profiles.linak import CARPE_DIEM

from . import _ar_connect
from ._common import Block, _block, _hex, _table


def carpe_controls() -> str:
    rows = []
    axes = ("back", "legs", "head", "feet")
    for size in range(1, 5):
        for selected in combinations(axes, size):
            for up in (False, True):
                rows.append(
                    (
                        ", ".join(selected) + (" up" if up else " down"),
                        _hex(selected_sections_frame(frozenset(selected), up)),
                    )
                )
    rows.append(("STOP / release", _hex(control_frame(0xFF))))
    for slot, (recall, save) in enumerate(
        zip(CARPE_DIEM.memory_opcodes, CARPE_DIEM.save_opcodes, strict=True), 1
    ):
        rows.extend(
            (
                (f"Recall {slot}", _hex(control_frame(recall))),
                (f"Save {slot}", _hex(control_frame(save))),
            )
        )
    return _block(_table(("Control", "Bytes"), rows))


def carpe_timing() -> str:
    return _block(
        _table(
            ("Operation", "Schedule"),
            [
                ("Normal held movement", f"Immediate, then {CARPE_DIEM.hold_interval_ms} ms"),
                (
                    "Favorite recall",
                    f"Immediate, {CARPE_DIEM.favorite_initial_delay_ms} ms initial delay, then {CARPE_DIEM.favorite_interval_ms} ms",
                ),
                (
                    "Massage zone selection",
                    f"Motor 1, {CARPE_DIEM.massage_zone_gap_s * 1000:g} ms gap, motor 2",
                ),
            ],
        )
    )


BLOCKS: list[Block] = [
    *_ar_connect.BLOCKS,
    ("docs/beds/linak.md", "linak-carpe-controls", carpe_controls),
    ("docs/beds/linak.md", "linak-carpe-timing", carpe_timing),
]


def tempur_controls() -> str:
    from custom_components.adjustable_bed.beds.linak.controller import LinakCommands
    from custom_components.adjustable_bed.codec.linak import (
        build_simultaneous_command,
        configuration_frame,
        control_frame,
        massage_selection_frames,
        selected_directions_frame,
    )
    from custom_components.adjustable_bed.profiles.linak import TEMPUR_RELAX

    def literal(frame: bytes) -> str:
        return f"`{frame.hex(' ').upper()}`"

    rows = []
    for axis in ("back", "legs", "head", "feet", "base"):
        for up in (False, True):
            rows.append((f"{axis.title()} {'up' if up else 'down'}", literal(selected_directions_frame({axis: up}))))
    for label, frame in (
        ("All down (Standard / Advanced)", control_frame(0)),
        ("All up (Standard / Advanced)", control_frame(1)),
        ("All down (TD3)", build_simultaneous_command("back", False, "legs", False)),
        ("All up (TD3)", build_simultaneous_command("back", True, "legs", True)),
        ("Direct STOP API (see release table)", LinakCommands.MOVE_STOP),
        ("Wake", LinakCommands.WAKE), ("Light toggle", LinakCommands.LIGHTS_TOGGLE),
        ("Reset defaults", LinakCommands.RESET_DEFAULTS),
        ("Massage off", LinakCommands.MASSAGE_ALL_OFF),
        ("Next massage mode", LinakCommands.MASSAGE_MODE_STEP),
        ("Back intensity up", LinakCommands.MASSAGE_HEAD_UP),
        ("Back intensity down", LinakCommands.MASSAGE_HEAD_DOWN),
        ("Leg intensity up", LinakCommands.MASSAGE_FOOT_UP),
        ("Leg intensity down", LinakCommands.MASSAGE_FOOT_DOWN),
        ("Both intensity up", LinakCommands.MASSAGE_ALL_UP),
        ("Both intensity down", LinakCommands.MASSAGE_ALL_DOWN),
    ):
        rows.append((label, literal(frame)))
    for slot, (recall, save) in enumerate(zip(TEMPUR_RELAX.memory_opcodes, TEMPUR_RELAX.save_opcodes, strict=True), 1):
        rows.extend(((f"Recall {slot}", literal(control_frame(recall))), (f"Save {slot}", literal(control_frame(save)))))
    for label, sections in (("Back massage", {"back"}), ("Leg massage", {"legs"}), ("Both massage zones", {"back", "legs"})):
        rows.append((label, ", wait 100 ms, ".join(literal(frame) for frame in massage_selection_frames(frozenset(sections)))))
    for enabled in (True, False):
        rows.append((f"Automatic drive {'on' if enabled else 'off'}", literal(configuration_frame(0x3B, bytes((enabled,)), write=True, prefix=0x89))))
    return _block(_table(("Control", "Bytes"), rows))


def tempur_timing() -> str:
    from custom_components.adjustable_bed.profiles.linak import TEMPUR_RELAX

    return _block(_table(("Operation", "Schedule"), [
        ("Movement and recall", f"Immediate, then {TEMPUR_RELAX.hold_interval_ms} ms after each completed write"),
        ("Massage zone selection", f"First write, {TEMPUR_RELAX.massage_zone_gap_s * 1000:g} ms delay, second write"),
        ("Store, light, wake, configuration, name", "One write per action"),
        ("Alarm", "Event, recurrence, query: ordered completed writes, no app ACK wait"),
        ("Reset", "Clear alarm when supported, then reset"),
    ]))


BLOCKS.extend([
    ("docs/beds/linak.md", "linak-tempur-controls", tempur_controls),
    ("docs/beds/linak.md", "linak-tempur-timing", tempur_timing),
])


def tempur_release() -> str:
    from custom_components.adjustable_bed.profiles.linak import tempur_release_frame

    rows = []
    for alarm in (False, True):
        for td3 in (False, True):
            for favorite, automatic in ((False, False), (True, False), (True, True)):
                frame = tempur_release_frame(alarm=alarm, td3=td3, favorite=favorite, automatic=automatic)
                rows.append((str(alarm), str(td3), "Recall" if favorite else "Movement",
                             str(automatic) if favorite else "n/a", _hex(frame) if frame else "End refresh, no frame"))
    return _block(_table(("Primary alarm", "Primary TD3", "Gesture", "Automatic drive", "Cleanup"), rows))


BLOCKS.append(("docs/beds/linak.md", "linak-tempur-release", tempur_release))
