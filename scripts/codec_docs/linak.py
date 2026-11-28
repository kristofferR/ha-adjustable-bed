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
