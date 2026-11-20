"""Relax Motion 1.5.0 model data from its accepted APK Protocol Audit report.

Hand-maintained typed literals; no checked-in generator. Numeric model identity
comes from the saved advertisement, never the service UUID alone.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Model:
    number: int
    label: str
    layout: str
    presets: bool
    head_massage: bool
    foot_massage: bool
    light: bool
    initial_memory: int
    separate_massage_stop: bool
    base: bool
    cosy: bool
    rhythm: bool


# fmt: off
RELAX: Final = {
    1: Model(1, 'BG200', 'two_back_foot', False, False, False, False, 0, False, False, False, False),
    2: Model(2, 'BG200A', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    3: Model(3, 'BG200M', 'two_back_foot', True, True, True, False, 2, False, False, False, False),
    4: Model(4, 'BG200M', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    5: Model(5, 'BG200M', 'two_back_foot', True, True, True, False, 1, False, False, False, False),
    6: Model(6, '6', 'three_head_back_foot', False, False, False, False, 0, False, False, False, False),
    7: Model(7, 'BG300A', 'three_head_back_foot', True, False, False, True, 2, False, False, False, False),
    8: Model(8, 'BG300M', 'three_head_back_foot', True, True, True, False, 2, False, False, False, False),
    9: Model(9, 'BG300M', 'three_head_back_foot', True, True, True, True, 2, False, False, False, False),
    10: Model(10, 'BG300M', 'three_head_back_foot', True, True, True, False, 1, False, False, False, False),
    11: Model(11, 'BG200', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    12: Model(12, 'BG300M', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    13: Model(13, '13', 'three_twoback_foot', False, False, False, False, 0, False, False, False, False),
    14: Model(14, 'Storage Bed', 'bed_store', False, False, False, False, 0, False, False, False, False),
    15: Model(15, '15', 'bed_one', False, False, False, False, 0, False, False, False, False),
    16: Model(16, 'Storage Bed', 'bed_store', False, False, False, False, 0, False, False, False, False),
    22: Model(22, 'BH200', 'two_back_foot', False, False, False, False, 0, False, False, False, False),
    23: Model(23, 'BA200', 'two_back_foot', False, False, False, False, 0, False, False, False, False),
    24: Model(24, 'BH200', 'two_back_foot', False, False, False, False, 0, False, False, False, False),
    25: Model(25, 'BT300', 'three_twoback_foot', False, False, False, False, 0, False, False, False, False),
    26: Model(26, 'BH200', 'two_back_foot', False, False, False, False, 0, False, False, False, False),
    27: Model(27, 'BP200A', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    28: Model(28, 'BG200M', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    29: Model(29, 'BG200M', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    30: Model(30, 'BG200M', 'two_back_foot', True, True, True, False, 1, False, False, False, False),
    31: Model(31, 'BP300D', 'three_head_back_foot', True, False, False, True, 2, False, False, True, False),
    32: Model(32, 'BG200XM', 'two_back_foot', True, True, True, True, 2, True, False, False, False),
    33: Model(33, '33', 'two_back_foot', True, True, True, True, 2, True, False, False, False),
    34: Model(34, 'BH200A', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    35: Model(35, '35', 'three_head_back_foot', True, True, True, True, 2, False, False, False, False),
    36: Model(36, '36', 'three_head_back_foot', True, True, True, True, 2, False, False, False, False),
    37: Model(37, '37', 'three_head_back_foot', True, False, False, True, 2, False, False, False, False),
    39: Model(39, 'BG200', 'two_back_foot', False, False, False, False, 0, False, False, False, False),
    43: Model(43, 'BA201A', 'two_back_foot', True, False, False, False, 3, False, False, False, False),
    44: Model(44, 'BG200A', 'two_back_foot', True, False, False, True, 2, True, False, False, False),
    45: Model(45, 'BP200XM', 'two_back_foot', True, True, True, True, 2, True, False, False, False),
    127: Model(127, '127', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    128: Model(128, 'BG200M', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    129: Model(129, 'BG200M', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    130: Model(130, 'BG200M', 'two_back_foot', True, True, True, False, 1, False, False, False, False),
    131: Model(131, 'BG200A', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    132: Model(132, '132', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    134: Model(134, 'BH200A', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    135: Model(135, '135', 'three_head_back_foot', True, True, True, True, 2, False, False, False, False),
    136: Model(136, '136', 'three_head_back_foot', True, True, True, True, 2, False, False, False, False),
    137: Model(137, '137', 'three_head_back_foot', True, False, False, True, 2, False, False, False, False),
    139: Model(139, 'BG200', 'two_back_foot', False, False, False, False, 0, False, False, False, False),
    222: Model(222, 'BH200', 'two_back_foot', False, False, False, False, 0, False, False, False, False),
    224: Model(224, 'BH200', 'two_back_foot', False, False, False, False, 0, False, False, False, False),
    226: Model(226, 'BH200', 'two_back_foot', False, False, False, False, 0, False, False, False, False),
    233: Model(233, '233', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    234: Model(234, '234', 'bed_one', False, False, False, False, 0, False, False, False, False),
    500: Model(500, 'BA200', 'two_back_foot', False, False, False, False, 1, False, False, False, False),
    623: Model(623, 'BH200', 'two_back_foot', False, False, False, False, 0, False, False, False, False),
    725: Model(725, 'BT300', 'three_twoback_foot', False, False, False, False, 0, False, False, False, False),
}

CHEERS: Final = {
    1: Model(1, 'BG200', 'two_back_foot', False, False, False, False, 2, False, True, False, False),
    2: Model(2, 'BG200A', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    3: Model(3, 'BG200M', 'two_back_foot', True, True, True, False, 2, False, False, False, False),
    4: Model(4, 'BG200M', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    5: Model(5, 'BG200M', 'two_back_foot', True, True, True, False, 1, False, False, False, False),
    6: Model(6, '6', 'three_head_back_foot', False, False, False, False, 2, False, True, False, False),
    7: Model(7, 'BG300A', 'three_head_back_foot', True, False, False, True, 2, False, False, False, False),
    8: Model(8, 'BG300M', 'three_head_back_foot', True, True, True, False, 2, False, False, False, False),
    9: Model(9, 'BG300M', 'three_head_back_foot', True, True, True, True, 2, False, False, False, False),
    10: Model(10, 'BG300M', 'three_head_back_foot', True, True, True, False, 1, False, False, False, False),
    11: Model(11, 'BG200', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    12: Model(12, 'BG300M', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    13: Model(13, '13', 'three_twoback_foot', False, False, False, False, 2, False, True, False, False),
    14: Model(14, 'Storage Bed', 'bed_store', False, False, False, False, 0, False, False, False, False),
    15: Model(15, '15', 'bed_one', False, False, False, False, 2, False, True, False, False),
    16: Model(16, 'Storage Bed', 'bed_store', False, False, False, False, 0, False, False, False, False),
    22: Model(22, 'BH200', 'two_back_foot', False, False, False, False, 2, False, True, False, False),
    23: Model(23, 'BA200', 'two_back_foot', False, False, False, False, 2, False, True, False, False),
    24: Model(24, 'BH200', 'two_back_foot', False, False, False, False, 2, False, True, False, False),
    25: Model(25, 'BT300', 'three_twoback_foot', False, False, False, False, 2, False, True, False, False),
    26: Model(26, 'BH200', 'two_back_foot', False, False, False, False, 2, False, True, False, False),
    27: Model(27, 'BP200A', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    28: Model(28, 'BG200M', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    29: Model(29, 'BG200M', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    30: Model(30, 'BG200M', 'two_back_foot', True, True, True, False, 1, False, False, False, False),
    31: Model(31, 'BP300D', 'three_head_back_foot', True, False, False, True, 2, False, False, True, False),
    32: Model(32, 'BG200XM', 'two_back_foot', True, True, True, True, 2, True, False, True, True),
    33: Model(33, '33', 'two_back_foot', True, True, True, True, 2, True, False, False, False),
    34: Model(34, 'BH200A', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    35: Model(35, '35', 'three_head_back_foot', True, True, True, True, 2, False, False, False, False),
    36: Model(36, '36', 'three_head_back_foot', True, True, True, True, 2, False, False, False, False),
    37: Model(37, '37', 'three_head_back_foot', True, False, False, True, 2, False, False, False, False),
    39: Model(39, 'BG200', 'two_back_foot', False, False, False, False, 2, False, True, False, False),
    43: Model(43, 'BA201A', 'two_back_foot', True, False, False, False, 3, False, False, False, False),
    44: Model(44, 'BG200A', 'two_back_foot', True, False, False, True, 2, True, False, False, False),
    45: Model(45, 'BP200XM', 'two_back_foot', True, True, True, True, 2, True, False, False, False),
    127: Model(127, '127', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    128: Model(128, 'BG200M', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    129: Model(129, 'BG200M', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    130: Model(130, 'BG200M', 'two_back_foot', True, True, True, False, 1, False, False, False, False),
    131: Model(131, 'BG200A', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    132: Model(132, '132', 'two_back_foot', True, True, True, True, 2, False, False, False, False),
    134: Model(134, 'BH200A', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    135: Model(135, '135', 'three_head_back_foot', True, True, True, True, 2, False, False, False, False),
    136: Model(136, '136', 'three_head_back_foot', True, True, True, True, 2, False, False, False, False),
    137: Model(137, '137', 'three_head_back_foot', True, False, False, True, 2, False, False, False, False),
    139: Model(139, 'BG200', 'two_back_foot', False, False, False, False, 2, False, True, False, False),
    222: Model(222, 'BH200', 'two_back_foot', False, False, False, False, 2, False, True, False, False),
    224: Model(224, 'BH200', 'two_back_foot', False, False, False, False, 2, False, True, False, False),
    226: Model(226, 'BH200', 'two_back_foot', False, False, False, False, 2, False, True, False, False),
    233: Model(233, '233', 'two_back_foot', True, False, False, True, 2, False, False, False, False),
    234: Model(234, '234', 'bed_one', False, False, False, False, 2, False, True, False, False),
    500: Model(500, 'BA200', 'two_back_foot', False, False, False, False, 1, False, False, False, False),
    623: Model(623, 'BH200', 'two_back_foot', False, False, False, False, 2, False, True, False, False),
    725: Model(725, 'BT300', 'three_twoback_foot', False, False, False, False, 2, False, True, False, False),
}
# fmt: on
