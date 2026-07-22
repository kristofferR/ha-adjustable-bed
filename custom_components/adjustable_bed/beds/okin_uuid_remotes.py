"""Generated Okin UUID remote-code table (DO NOT EDIT BY HAND).

Source of truth: the DewertOkin FurniMove handset backend
(``GET /mobile-data/button/{remote_id}``), supplemented by the bundled
``handsetlist.csv`` capability flags for remote codes the backend no longer
serves. Regenerate with ``tools/okin_remotes/gen_module.py`` (see the README
there for the full pipeline).

Each entry is keyword arguments for ``OkinUuidRemoteConfig`` (see
``okin_uuid.py``). Keycodes are the 32-bit Okin command values; the standard
controller wraps them as ``[0x04, 0x02, <4-byte big-endian>]``. ``memory_save``
may be a ``(keycode, count, delay_ms)`` hold tuple when the backend specifies
hold timing for that handset. UBL/light commands are always single keycodes:
FurniMove repeats them only for as long as the user keeps touching the button
and does not consult the backend UBL duration/frequency metadata.

Entries with ``"dot": True`` are "DOT PROTOCOL" handsets (RF1058/RF34/RF6707).
Their boxes expose Nordic UART instead of the Okin 62741523 service and take
CB24-style 7-byte frames ``[0x05, 0x02, <4-byte big-endian>, 0x00]`` — they are
driven by ``OkinDotController`` and listed in ``OKIN_DOT_VARIANT_LABELS``, not
in the Okimat dropdown. Their motor keycodes are renumbered per handset
(whichever channels exist start at 0x1/0x2) but keep their section meaning —
the table maps them to the standard section fields (RF1058 = head+feet,
RF6707 = head+back).

``source`` comment legend:
  backend         -> authoritative keycodes from the live handset backend
  csv-inherit:<n> -> pruned code; keycodes inherited from live sibling <n>
                     with the identical capability signature
  csv-reconstruct -> pruned code with no live sibling; keycodes rebuilt from
                     the universal/modal Okin keycode maps (Flat may be
                     approximate)
"""

from __future__ import annotations

# Default remote when variant is auto/unknown (most common basic RF-TOPLINE).
DEFAULT_OKIN_UUID_REMOTE = "82417"

# Default DOT remote (plain RF34 layout; flat/light keycodes are identical
# across all DOT codes, only motor sections and memory/massage extras differ).
DEFAULT_OKIN_DOT_REMOTE = "97450"

# code -> dropdown label
OKIN_UUID_VARIANT_LABELS: dict[str, str] = {
    "62211": "62211 - RF (Head/Back/Legs, 4 Mem)",
    "62612": "62612 - RF (Head/Back/Legs/Feet, 4 Mem)",
    "63293": "63293 - RF (Back/Legs)",
    "63338": "63338 - RF (Back/Legs)",
    "63365": "63365 - RF (Head/Back/Legs, 4 Mem)",
    "65418": "65418 - RF (Head/Back/Legs, 4 Mem)",
    "65433": "65433 - RF (Back/Legs, 4 Mem)",
    "65567": "65567 - RF (Head/Back/Legs/Feet, 4 Mem, Massage)",
    "68036": "68036 - RF-SYSTEM/SW/6/1476/2400MHZ (Back/Legs)",
    "71852": "71852 - SET (Back/Legs)",
    "71853": "71853 - REMOTE (Back/Legs)",
    "73591": "73591 - REMOTE (Back/Legs)",
    "73593": "73593 - SET (Back/Legs)",
    "74130": "74130 - REMOTE (Head)",
    "74131": "74131 - SET (Head)",
    "75225": "75225 - RF-SYSTEM/SW/ST/6/1476/2400MHZ (Back/Legs)",
    "75267": "75267 - REMOTE (Back/Legs)",
    "75268": "75268 - SET (Back/Legs)",
    "76208": "76208 - RF (Back/Legs, 4 Mem, Massage)",
    "76688": "76688 - RFS-ELLIPSE/SW-SW-06-1844/-/-/-/02 (Back/Legs)",
    "76691": "76691 - RFS-ELLIPSE/SW-SW-09-1845/-/-/M/02 (Back/Legs, 1 Mem)",
    "77008": "77008 - RF (Back/Legs)",
    "77010": "77010 - RF (Back/Legs)",
    "77011": "77011 - RF (Back/Legs)",
    "77560": "77560 - REMOTE (Back/Legs)",
    "77561": "77561 - SET (Back/Legs)",
    "77839": "77839 - RF-TOUCH/BRW/BK/16/1867/L (Back/Legs, 4 Mem)",
    "77991": "77991 - RF-TOUCH/BRW/BK/16/1867/L (Back/Legs, 4 Mem)",
    "77994": "77994 - RF-TOUCH/BRW/BK/20/1868/L (Head/Back/Legs/Feet, 4 Mem)",
    "77995": "77995 - RF-TOUCH/BRW/BK/18/1869/L (Back/Legs/Feet, 4 Mem)",
    "77996": "77996 - RF-TOUCH/BK/BRW/18/1870/03 (Head/Back/Legs, 4 Mem)",
    "78031": "78031 - REMOTE (Back/Legs)",
    "78033": "78033 - SET (Back/Legs)",
    "78080": "78080 - RF-TOUCH/BRW/BK/16/1889/L (Back/Legs, 4 Mem)",
    "78081": "78081 - RF-TOUCH/BRW/BK/16/1889/L (Back/Legs, 4 Mem)",
    "78102": "78102 - RF-TOUCH/BRW/BK/18/1892/L (Head/Back/Legs, 4 Mem)",
    "78103": "78103 - RF-TOUCH/BRW/BK/20/1890/L (Head/Back/Legs/Feet, 4 Mem)",
    "78105": "78105 - RF-TOUCH/BRW/BK/16/1893/L (Back/Legs, 4 Mem)",
    "78109": "78109 - RF-TOUCH/BRW/BK/18/1891/L (Back/Legs/Feet, 4 Mem)",
    "78110": "78110 - RF-TOUCH/BRW/BK/18/1894/L (Head/Back/Legs, 4 Mem)",
    "78111": "78111 - RF-TOUCH/BRW/BK/20/1895/L (Head/Back/Legs/Feet, 4 Mem)",
    "78237": "78237 - REMOTE (Back/Legs)",
    "78238": "78238 - SET (Back/Legs)",
    "78281": "78281 - REMOTE (Back/Legs)",
    "78283": "78283 - SET (Back/Legs)",
    "78375": "78375 - RFS-ELLIPSE/WS-SW-06-1844/-/-/-/02 (Back/Legs)",
    "78378": "78378 - RFS-ELLIPSE/WA-SW-06-1844/-/-/-/02 (Back/Legs)",
    "78379": "78379 - RFS-ELLIPSE/WS-SW-09-1845/-/-/M/02 (Back/Legs, 1 Mem)",
    "78381": "78381 - RFS-ELLIPSE/WA-SW-09-1845/-/-/M/02 (Back/Legs, 1 Mem)",
    "78386": "78386 - RFS-ELLIPSE/WA-SW-06-1902/-/-/-/02 (Back/Legs)",
    "78737": "78737 - RF-TOUCH/BRW/BK/21/1899/L (Head/Back/Legs, 4 Mem)",
    "78773": "78773 - RF-TOUCH/BRW/BK/19/1896 (Head/Back/Legs/Feet, 3 Mem)",
    "78785": "78785 - RF-TOUCH/BRW/BK/19/1897 (Head/Back/Legs/Feet, 3 Mem)",
    "78791": "78791 - RF-TOUCH/BRW/BK/19/1898/L (Head/Back/Legs/Feet, 3 Mem)",
    "78847": "78847 - RF-TOUCH/BRW/BK/14/1923 (Back/Legs, 2 Mem)",
    "78854": "78854 - RF-TOUCH/BRW/BK/14/1924/L (Back/Legs, 2 Mem)",
    "78860": "78860 - RF-TOUCH/BRW/BK/14/1925/L (Back/Legs, 2 Mem)",
    "80027": "80027 - RF-TOUCH/BK/BK/14/1923 (Back/Legs, 2 Mem)",
    "80035": "80035 - RF-TOUCH/BK/BK/19/1896 (Head/Back/Legs/Feet, 3 Mem)",
    "80036": "80036 - RF-TOUCH/BK/BK/17/1965 (Back/Legs/Feet, 3 Mem)",
    "80354": "80354 - REMOTE (Back/Legs)",
    "80355": "80355 - SET (Back/Legs)",
    "80358": "80358 - REMOTE (Head)",
    "80360": "80360 - SET (Head)",
    "80593": "80593 - RF-TOUCH/BRW/BK/8/1952/L (Back/Legs)",
    "80595": "80595 - RF-TOUCH/BRW/BK/8/1954/L (Back/Legs)",
    "80597": "80597 - RF-TOUCH/BRW/BK/8/1953/L (Back/Legs)",
    "80599": "80599 - RFS-ELLIPSE/SW-SW-06-1844/-/-/-/02 (Back/Legs)",
    "80601": "80601 - RFS-ELLIPSE/SW-SW-09-1845/-/-/M/02 (Back/Legs, 1 Mem)",
    "80602": "80602 - RFS-ELLIPSE/WA-SW-06-1902/-/-/-/02 (Back/Legs)",
    "80603": "80603 - RFS-ELLIPSE/WS-SW-09-1845/-/-/M/02 (Back/Legs, 1 Mem)",
    "80604": "80604 - RFS-ELLIPSE/WA-SW-09-1845/-/-/M/02 (Back/Legs, 1 Mem)",
    "80608": "80608 - RFS-ELLIPSE/WA-SW-06-1844/-/-/-/02 (Back/Legs)",
    "80616": "80616 - RFS-ELLIPSE/WS-SW-06-1844/-/-/-/02 (Back/Legs)",
    "80673": "80673 - REMOTE (Back/Legs)",
    "80674": "80674 - REMOTE (Back/Legs)",
    "80675": "80675 - REMOTE (Back/Legs)",
    "80676": "80676 - SET (Back/Legs)",
    "80683": "80683 - SET (Back/Legs)",
    "80685": "80685 - SET (Back/Legs)",
    "80714": "80714 - SET (Back/Legs)",
    "80716": "80716 - REMOTE (Back/Legs)",
    "80903": "80903 - RF-TOUCH/BK/BK/14/2009 (Back/Legs, 2 Mem)",
    "81183": "81183 - RF-TOUCH/BRW/BK/8/1952/L (Back/Legs)",
    "81185": "81185 - RF-TOUCH/BRW/BK/16/1867/L (Back/Legs, 4 Mem)",
    "81186": "81186 - RF-TOUCH/BRW/BK/8/1954/L (Back/Legs)",
    "81187": "81187 - RF-TOUCH/BRW/BK/18/1870/L (Head/Back/Legs, 4 Mem)",
    "81191": "81191 - RF-TOUCH/BRW/BK/20/1868/L (Head/Back/Legs/Feet, 4 Mem)",
    "81192": "81192 - RF-TOUCH/BRW/BK/18/1894/L (Head/Back/Legs, 4 Mem)",
    "81193": "81193 - RF-TOUCH/BRW/BK/18/1869/L (Back/Legs/Feet, 4 Mem)",
    "81194": "81194 - RF-TOUCH/BRW/BK/8/1953/L (Back/Legs)",
    "81196": "81196 - RF-TOUCH/BRW/BK/16/1889/L (Back/Legs, 4 Mem)",
    "81197": "81197 - RF-TOUCH/BRW/BK/20/1890/L (Head/Back/Legs/Feet, 4 Mem)",
    "81202": "81202 - RF-TOUCH/BRW/BK/18/1892/L (Head/Back/Legs, 4 Mem)",
    "81204": "81204 - RF-TOUCH/BRW/BK/18/1891/L (Back/Legs/Feet, 4 Mem)",
    "81205": "81205 - RF-TOUCH/BRW/BK/20/1895/L (Head/Back/Legs/Feet, 4 Mem)",
    "81611": "81611 - REMOTE (Back/Legs)",
    "81613": "81613 - SET (Back/Legs)",
    "81619": "81619 - REMOTE (Back)",
    "81620": "81620 - SET (Head)",
    "82292": "82292 - RF-TOUCH/BRW/BK/14/2006 (Back/Legs, 2 Mem)",
    "82295": "82295 - RF-TOUCH/BRW/BK/19/2004 (Head/Back/Legs/Feet, 3 Mem)",
    "82417": "82417 - RF-TOPLINE (Back/Legs)",
    "82418": "82418 - RF-TOPLINE (Back/Legs, 2 Mem)",
    "82620": "82620 - RF-TOPLINE (Back/Legs)",
    "82634": "82634 - RF-TOPLINE (Head/Back/Legs)",
    "82635": "82635 - RF-TOPLINE (Head/Back/Legs)",
    "82755": "82755 - RF-TOPLINE (Head)",
    "82757": "82757 - RF-TOPLINE (Back/Legs)",
    "82760": "82760 - RF-TOPLINE (Back/Legs)",
    "82764": "82764 - RF-TOPLINE (Back/Legs)",
    "82767": "82767 - RF-TOPLINE (Back/Legs)",
    "82770": "82770 - RF-TOPLINE (Back/Legs)",
    "82785": "82785 - RF-TOPLINE (Head/Back/Legs)",
    "82786": "82786 - RF-TOPLINE (Head/Back/Legs)",
    "82790": "82790 - RF-TOPLINE (Head/Back/Legs)",
    "82794": "82794 - RF-TOPLINE (Head/Back/Legs/Feet)",
    "82795": "82795 - RF-TOPLINE (Head/Back/Legs/Feet)",
    "82796": "82796 - RF-TOPLINE (Head/Back/Legs/Feet)",
    "82797": "82797 - RF-TOPLINE (Head/Back/Legs/Feet)",
    "82799": "82799 - RF-TOPLINE (Head/Back/Legs/Feet)",
    "83060": "83060 - RF-TOUCH/BRW/BK/14/2182/L (Back/Legs, 2 Mem)",
    "83126": "83126 - RF-TOUCH/BRW/BK/19/2114 (Back/Legs, 3 Mem, Massage)",
    "83219": "83219 - RF-TOUCH/BRW/BK/24/2068/- (Head/Back/Legs/Feet, 3 Mem, Massage)",
    "83358": "83358 - RF-TOPLINE (Back/Legs)",
    "83462": "83462 - SET (Back/Legs)",
    "83489": "83489 - RF-TOPLINE (Back/Legs)",
    "83603": "83603 - SET (Back/Legs)",
    "84148": "84148 - REMOTE (Back/Legs)",
    "84149": "84149 - SET (Back/Legs)",
    "84150": "84150 - REMOTE (Back/Legs)",
    "84151": "84151 - SET (Back/Legs)",
    "84173": "84173 - RF-TOUCH/BRW/BK/23/2126 (Head/Back/Legs/Feet, 3 Mem, Massage)",
    "84562": "84562 - RF-ECO (Back/Legs)",
    "84563": "84563 - RF-ECO (Back/Legs)",
    "84564": "84564 - RF-ECO (Head/Back/Legs)",
    "84582": "84582 - RF-ECO (Head)",
    "84762": "84762 - HS-IPROXX (Back/Legs)",
    "84931": "84931 - RF-TOPLINE/07/AL/BK/L (Back/Legs)",
    "84963": "84963 - RF-TOPLINE/07/BK/BK/L (Back/Legs)",
    "85057": "85057 - RF-TOPLINE/11/AL/BK/L (Head/Back/Legs/Feet, 4 Mem)",
    "85058": "85058 - RF-TOPLINE/11/AL/BK/L (Back/Legs, 2 Mem)",
    "85124": "85124 - RF-LITE/06/BK/BK (Back/Legs)",
    "85126": "85126 - SET (Back/Legs)",
    "85281": "85281 - RF-FREE-ELEC (Head/Back/Legs/Feet, 4 Mem)",
    "86432": "86432 - RF-STYLE (Back/Legs, 2 Mem)",
    "88875": "88875 - RF-LITELINE/07/ (Back/Legs)",
    "88877": "88877 - RF-LITELINE/07/ (Back/Legs)",
    "89137": "89137 - RF-LITELINE/07/ (Back/Legs)",
    "89138": "89138 - RF-LITELINE/07/ (Back/Legs)",
    "89139": "89139 - RF-LITELINE/07/ (Back/Legs)",
    "89424": "89424 - RF (Back/Legs)",
    "89441": "89441 - RF-FREE-ELEC (Back/Legs, 4 Mem)",
    "89448": "89448 - RF-FREE-ELEC (Back/Legs/Feet, 4 Mem)",
    "89476": "89476 - RF-TOPLINE/11/AL/BK (Head/Back/Legs/Feet, 4 Mem)",
    "89545": "89545 - RF-TOPLINE/11/AL/BK (Back/Legs, 2 Mem)",
    "89746": "89746 - TOPLINE-11-SL-2M (Back/Legs, 2 Mem)",
    "89803": "89803 - LITELINE-7-SL-2M (Back/Legs)",
    "89837": "89837 - RF-TOUCH/18/WH/BK/KL/L (Back/Legs, 3 Mem, Massage)",
    "90199": "90199 - TOPLINE-11-SL-3M/4M (Back/Legs, 2 Mem)",
    "90269": "90269 - RF-STYLE/07/WH/WH (Back/Legs, 4 Mem)",
    "90354": "90354 - RF-STYLE/07/WH/WH (Head/Back/Legs, 2 Mem)",
    "90392": "90392 - HS-IPROXX (Back/Legs)",
    "90658": "90658 - RF-TOUCHLINE/15/BK/BK/KL (Head/Back, 4 Mem)",
    "90675": "90675 - RF-TOUCHLINE/15/AL/BK/KL (Head/Back, 4 Mem)",
    "90678": "90678 - RF-TOUCHLINE/19/AL/BK/KL (Head/Back/Legs/Feet, 4 Mem)",
    "90679": "90679 - RF-TOUCHLINE/19/BK/BK/KL (Head/Back/Legs/Feet, 4 Mem)",
    "90882": "90882 - TOPLINE-11-BK-2M (Back/Legs, 2 Mem)",
    "90916": "90916 - RF-TOUCHLINE/21/AL/BK/KL (Head/Back/Legs/Feet, 2 Mem, Massage)",
    "90918": "90918 - RF-TOUCHLINE/21/AL/BK/KL (Back/Legs, 3 Mem, Massage)",
    "90926": "90926 - RF-ECO (Back/Feet)",
    "90928": "90928 - TOPLINE-11-SL-3M/4M (Back/Legs, 2 Mem, Massage)",
    "91050": "91050 - RF-TOUCHLINE/21/AL/BK/KL (Back/Legs, 3 Mem, Massage)",
    "91244": "91244 - RF-FLASHLINE/07/WH/GY (Back/Legs)",
    "91246": "91246 - RF-FLASHLINE/09/WH/GY (Back/Legs, 2 Mem)",
    "91334": "91334 - TOPLINE-11-BK-2M (Back/Legs, 2 Mem)",
    "91616": "91616 - HS-IPROXX (Back/Legs)",
    "91751": "91751 - LITELINE-7-BK-2M (Back/Legs)",
    "91914": "91914 - RF-TOUCH/23/WH/BK/KL (Head/Back/Legs/Feet, 3 Mem, Massage)",
    "92063": "92063 - LITELINE-7-GR-2M (Back/Legs)",
    "92113": "92113 - RF-STYLE/BK/BK/14/2009 (Back/Legs, 4 Mem)",
    "92129": "92129 - TOPLINE-11-SL-2M (Back/Legs, 2 Mem, Massage)",
    "92428": "92428 - RF (Back/Legs, 2 Mem)",
    "92461": "92461 - \n  RF-TOPLINE\n  SI (Back/Legs)",
    "92471": "92471 - RF (Back/Legs, 2 Mem)",
    "92535": "92535 - RF-LITELINE/07/ (Back/Legs)",
    "92591": "92591 - RF-FLASHLINE/09/WH/GY (Back/Legs, 2 Mem)",
    "93025": "93025 - RF-STYLE/07/WH/WH (Back/Legs)",
    "93055": "93055 - RF-TOPLINE/15/WH/BK (Back/Legs, 2 Mem)",
    "93300": "93300 - RF-STYLE/07/WH/WH (Back/Legs, 4 Mem)",
    "93305": "93305 - RF-TOPLINE (Back/Legs)",
    "93306": "93306 - RF-TOPLINE (Back/Legs, 2 Mem)",
    "93329": "93329 - RF-TOPLINE/15/AL/BK/M3/S/ST/IP20/BLI/FL/LED/M (Head/Back/Legs, 4 Mem)",
    "93332": "93332 - RF-TOPLINE/15/AL/BK/M4/S/ST/IP20/BLI/FL/LED/M (Head/Back/Legs/Feet, 2 Mem)",
    "93339": "93339 - RF-TOPLINE/15/AL/BK (Back/Legs, 2 Mem, Massage)",
    "94186": "94186 - RF-TOPLINE (Back/Legs, 2 Mem)",
    "94238": "94238 - RF (Back/Legs, 2 Mem)",
    "94239": "94239 - RF (Back/Legs)",
    "94369": "94369 - RF-TOPLINE (Head/Back/Legs/Feet, 4 Mem)",
    "94428": "94428 - RF-TOPLINE (Head/Back/Legs/Feet, 4 Mem)",
    "94429": "94429 - RF-TOPLINE (Head/Back/Legs, 4 Mem)",
    "94430": "94430 - RF-TOPLINE (Back/Legs, 2 Mem)",
    "94495": "94495 - RF-FLASHLINE/TEMPUR/07/BLACK (Back/Legs)",
    "94500": "94500 - RF-FLASHLINE/TEMPUR/09/BLACK (Back/Legs, 2 Mem)",
    "96312": "96312 - RF34/07/BK/BK (Back/Legs)",
    "96313": "96313 - RF34/07/WH/GY (Back/Legs)",
    "96314": "96314 - RF28/07/BK/BK (Back/Legs)",
    "96315": "96315 - RF28/07/WH/GY (Back/Legs)",
    "97134": "97134 - RF-TOPLINE/11/AL/BK/L (Back/Legs, 2 Mem)",
    "97135": "97135 - RF-TOPLINE/15/AL/BK/L (Head/Back/Legs/Feet, 2 Mem)",
}

# DOT-protocol code -> dropdown label (okin_dot bed type)
OKIN_DOT_VARIANT_LABELS: dict[str, str] = {
    "90167": "90167 - RF1058 (Head/Feet, 4 Mem, Massage)",
    "91983": "91983 - RF1058 (Head/Feet, 3 Mem, Massage)",
    "93558": "93558 - RF1058 (Head/Feet, 3 Mem, Massage)",
    "97450": "97450 - RF34/09/WH/GY/ (Back/Legs, 2 Mem)",
    "97544": "97544 - RF34/09/BK/BK/ (Back/Legs, 2 Mem)",
    "98035": "98035 - RF6707 (Head/Back)",
}

# code -> OkinUuidRemoteConfig kwargs
OKIN_UUID_REMOTE_DATA: dict[str, dict] = {
    "62211": {"name": "RF", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "62612": {"name": "RF", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "memory_4": 0x4000, "toggle_lights": 0x20000},  # csv-inherit:85057
    "63293": {"name": "RF", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "63338": {"name": "RF", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # csv-inherit:80599
    "63365": {"name": "RF", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "65418": {"name": "RF", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "65433": {"name": "RF", "flat": 0x10000000, "back_up": 0x4, "back_down": 0x8, "legs_up": 0x10, "legs_down": 0x20, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "memory_4": 0x4000, "toggle_lights": 0x20000},  # csv-inherit:89441
    "65567": {"name": "RF", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000, "massage": {"all": 0x200000, "foot_down": 0x1000000, "foot_toggle": 0x100000, "foot_up": 0x400000, "head_down": 0x800000, "head_toggle": 0x80000, "head_up": 0x800, "mode1": 0x20000000, "mode2": 0x40000000, "mode3": 0x80000000, "stop": 0x400}},  # csv-reconstruct
    "68036": {"name": "RF-SYSTEM/SW/6/1476/2400MHZ", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "71852": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "71853": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "73591": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "73593": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "74130": {"name": "REMOTE", "flat": 0x100000aa, "head_up": 0x10, "head_down": 0x20},  # csv-inherit:81620
    "74131": {"name": "SET", "flat": 0x100000aa, "head_up": 0x10, "head_down": 0x20},  # csv-inherit:81620
    "75225": {"name": "RF-SYSTEM/SW/ST/6/1476/2400MHZ", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "75267": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "75268": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "76208": {"name": "RF", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000, "massage": {"all": 0x200000, "foot_down": 0x1000000, "foot_toggle": 0x100000, "foot_up": 0x400000, "head_down": 0x800000, "head_toggle": 0x80000, "head_up": 0x800, "mode1": 0x20000000, "mode2": 0x40000000, "mode3": 0x80000000, "stop": 0x400}},  # csv-reconstruct
    "76688": {"name": "RFS-ELLIPSE/SW-SW-06-1844/-/-/-/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "76691": {"name": "RFS-ELLIPSE/SW-SW-09-1845/-/-/M/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "toggle_lights": 0x20000},  # csv-inherit:80601
    "77008": {"name": "RF", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "77010": {"name": "RF", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "77011": {"name": "RF", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "77560": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "77561": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "77839": {"name": "RF-TOUCH/BRW/BK/16/1867/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "77991": {"name": "RF-TOUCH/BRW/BK/16/1867/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "77994": {"name": "RF-TOUCH/BRW/BK/20/1868/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-inherit:90678
    "77995": {"name": "RF-TOUCH/BRW/BK/18/1869/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "77996": {"name": "RF-TOUCH/BK/BRW/18/1870/03", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "78031": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "78033": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "78080": {"name": "RF-TOUCH/BRW/BK/16/1889/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "78081": {"name": "RF-TOUCH/BRW/BK/16/1889/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "78102": {"name": "RF-TOUCH/BRW/BK/18/1892/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "78103": {"name": "RF-TOUCH/BRW/BK/20/1890/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-inherit:90678
    "78105": {"name": "RF-TOUCH/BRW/BK/16/1893/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "78109": {"name": "RF-TOUCH/BRW/BK/18/1891/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "78110": {"name": "RF-TOUCH/BRW/BK/18/1894/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "78111": {"name": "RF-TOUCH/BRW/BK/20/1895/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-inherit:90678
    "78237": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "78238": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "78281": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "78283": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "78375": {"name": "RFS-ELLIPSE/WS-SW-06-1844/-/-/-/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "78378": {"name": "RFS-ELLIPSE/WA-SW-06-1844/-/-/-/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "78379": {"name": "RFS-ELLIPSE/WS-SW-09-1845/-/-/M/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "toggle_lights": 0x20000},  # csv-inherit:80601
    "78381": {"name": "RFS-ELLIPSE/WA-SW-09-1845/-/-/M/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "toggle_lights": 0x20000},  # csv-inherit:80601
    "78386": {"name": "RFS-ELLIPSE/WA-SW-06-1902/-/-/-/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "78737": {"name": "RF-TOUCH/BRW/BK/21/1899/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000},  # csv-reconstruct
    "78773": {"name": "RF-TOUCH/BRW/BK/19/1896", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "toggle_lights": 0x20000},  # csv-inherit:82295
    "78785": {"name": "RF-TOUCH/BRW/BK/19/1897", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "toggle_lights": 0x20000},  # csv-inherit:82295
    "78791": {"name": "RF-TOUCH/BRW/BK/19/1898/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "toggle_lights": 0x20000},  # csv-inherit:82295
    "78847": {"name": "RF-TOUCH/BRW/BK/14/1923", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # csv-inherit:82292
    "78854": {"name": "RF-TOUCH/BRW/BK/14/1924/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # csv-inherit:82292
    "78860": {"name": "RF-TOUCH/BRW/BK/14/1925/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # csv-inherit:82292
    "80027": {"name": "RF-TOUCH/BK/BK/14/1923", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # csv-inherit:82292
    "80035": {"name": "RF-TOUCH/BK/BK/19/1896", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "toggle_lights": 0x20000},  # csv-inherit:82295
    "80036": {"name": "RF-TOUCH/BK/BK/17/1965", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "toggle_lights": 0x20000},  # csv-reconstruct
    "80354": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "80355": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "80358": {"name": "REMOTE", "flat": 0x100000aa, "head_up": 0x10, "head_down": 0x20},  # csv-inherit:81620
    "80360": {"name": "SET", "flat": 0x100000aa, "head_up": 0x10, "head_down": 0x20},  # csv-inherit:81620
    "80593": {"name": "RF-TOUCH/BRW/BK/8/1952/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # csv-inherit:80599
    "80595": {"name": "RF-TOUCH/BRW/BK/8/1954/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # csv-inherit:80599
    "80597": {"name": "RF-TOUCH/BRW/BK/8/1953/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # csv-inherit:80599
    "80599": {"name": "RFS-ELLIPSE/SW-SW-06-1844/-/-/-/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "80601": {"name": "RFS-ELLIPSE/SW-SW-09-1845/-/-/M/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "toggle_lights": 0x20000},  # backend
    "80602": {"name": "RFS-ELLIPSE/WA-SW-06-1902/-/-/-/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "80603": {"name": "RFS-ELLIPSE/WS-SW-09-1845/-/-/M/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "toggle_lights": 0x20000},  # backend
    "80604": {"name": "RFS-ELLIPSE/WA-SW-09-1845/-/-/M/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "toggle_lights": 0x20000},  # backend
    "80608": {"name": "RFS-ELLIPSE/WA-SW-06-1844/-/-/-/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "80616": {"name": "RFS-ELLIPSE/WS-SW-06-1844/-/-/-/02", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "80673": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "80674": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "80675": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "80676": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "80683": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "80685": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "80714": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "80716": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "80903": {"name": "RF-TOUCH/BK/BK/14/2009", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # csv-inherit:82292
    "81183": {"name": "RF-TOUCH/BRW/BK/8/1952/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # csv-inherit:80599
    "81185": {"name": "RF-TOUCH/BRW/BK/16/1867/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "81186": {"name": "RF-TOUCH/BRW/BK/8/1954/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # csv-inherit:80599
    "81187": {"name": "RF-TOUCH/BRW/BK/18/1870/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "81191": {"name": "RF-TOUCH/BRW/BK/20/1868/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-inherit:90678
    "81192": {"name": "RF-TOUCH/BRW/BK/18/1894/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "81193": {"name": "RF-TOUCH/BRW/BK/18/1869/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "81194": {"name": "RF-TOUCH/BRW/BK/8/1953/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # csv-inherit:80599
    "81196": {"name": "RF-TOUCH/BRW/BK/16/1889/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "81197": {"name": "RF-TOUCH/BRW/BK/20/1890/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-inherit:90678
    "81202": {"name": "RF-TOUCH/BRW/BK/18/1892/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "81204": {"name": "RF-TOUCH/BRW/BK/18/1891/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": 0x10000, "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-reconstruct
    "81205": {"name": "RF-TOUCH/BRW/BK/20/1895/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # csv-inherit:90678
    "81611": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "81613": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "81619": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "toggle_lights": 0x20000},  # backend
    "81620": {"name": "SET", "flat": 0x100000aa, "head_up": 0x10, "head_down": 0x20, "toggle_lights": 0x20000},  # backend
    "82292": {"name": "RF-TOUCH/BRW/BK/14/2006", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "82295": {"name": "RF-TOUCH/BRW/BK/19/2004", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "toggle_lights": 0x20000},  # backend
    "82417": {"name": "RF-TOPLINE", "flat": 0xaa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "82418": {"name": "RF-TOPLINE", "flat": 0xaa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "82620": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "82634": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "child_lock": 0x8000000, "toggle_lights": 0x20000},  # backend
    "82635": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "child_lock": 0x8000000, "toggle_lights": 0x20000},  # backend
    "82755": {"name": "RF-TOPLINE", "flat": 0x100000aa, "head_up": 0x10, "head_down": 0x20, "toggle_lights": 0x20000},  # backend
    "82757": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "82760": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "82764": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "82767": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "82770": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "82785": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "toggle_lights": 0x20000},  # backend
    "82786": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "toggle_lights": 0x20000},  # backend
    "82790": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "toggle_lights": 0x20000},  # backend
    "82794": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "toggle_lights": 0x20000},  # backend
    "82795": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "toggle_lights": 0x20000},  # backend
    "82796": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "toggle_lights": 0x20000},  # backend
    "82797": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "toggle_lights": 0x20000},  # backend
    "82799": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "toggle_lights": 0x20000},  # backend
    "83060": {"name": "RF-TOUCH/BRW/BK/14/2182/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "83126": {"name": "RF-TOUCH/BRW/BK/19/2114", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "toggle_lights": 0x20000, "massage": {"all": 0x200000, "foot_down": 0x1000000, "foot_toggle": 0x100000, "foot_up": 0x400000, "head_down": 0x800000, "head_toggle": 0x80000, "head_up": 0x800, "mode1": 0x20000000, "mode2": 0x40000000, "mode3": 0x80000000, "stop": 0x400, "wave": 0x4000000}},  # backend
    "83219": {"name": "RF-TOUCH/BRW/BK/24/2068/-", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "toggle_lights": 0x20000, "massage": {"all": 0x200000, "foot_down": 0x1000000, "foot_toggle": 0x100000, "foot_up": 0x400000, "head_down": 0x800000, "head_toggle": 0x80000, "head_up": 0x800, "mode1": 0x20000000, "mode2": 0x40000000, "mode3": 0x80000000, "stop": 0x400, "wave": 0x4000000}},  # backend
    "83358": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "83462": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "83489": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "83603": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8},  # csv-inherit:80599
    "84148": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "84149": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "84150": {"name": "REMOTE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "84151": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "84173": {"name": "RF-TOUCH/BRW/BK/23/2126", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "toggle_lights": 0x20000, "massage": {"all": 0x200000, "foot_down": 0x1000000, "foot_toggle": 0x100000, "foot_up": 0x400000, "head_down": 0x800000, "head_toggle": 0x80000, "head_up": 0x800, "mode1": 0x20000000, "mode2": 0x40000000, "mode3": 0x80000000, "stop": 0x400, "wave": 0x4000000}},  # csv-inherit:83219
    "84562": {"name": "RF-ECO", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "84563": {"name": "RF-ECO", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "84564": {"name": "RF-ECO", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "toggle_lights": 0x20000},  # backend
    "84582": {"name": "RF-ECO", "flat": 0x100000aa, "head_up": 0x10, "head_down": 0x20, "toggle_lights": 0x20000},  # backend
    "84762": {"name": "HS-IPROXX", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "84931": {"name": "RF-TOPLINE/07/AL/BK/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "84963": {"name": "RF-TOPLINE/07/BK/BK/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "85057": {"name": "RF-TOPLINE/11/AL/BK/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "memory_4": 0x4000, "toggle_lights": 0x20000},  # backend
    "85058": {"name": "RF-TOPLINE/11/AL/BK/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "85124": {"name": "RF-LITE/06/BK/BK", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "85126": {"name": "SET", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "85281": {"name": "RF-FREE-ELEC", "flat": 0x10000000, "back_up": 0x4, "back_down": 0x8, "legs_up": 0x10, "legs_down": 0x20, "head_up": 0x1, "head_down": 0x2, "feet_up": 0x40, "feet_down": 0x80, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "memory_4": 0x4000, "toggle_lights": 0x20000},  # backend
    "86432": {"name": "RF-STYLE", "flat": 0xa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "zero_gravity": 0x4000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "88875": {"name": "RF-LITELINE/07/", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "88877": {"name": "RF-LITELINE/07/", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "89137": {"name": "RF-LITELINE/07/", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "89138": {"name": "RF-LITELINE/07/", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "89139": {"name": "RF-LITELINE/07/", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "89424": {"name": "RF", "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "89441": {"name": "RF-FREE-ELEC", "flat": 0x10000000, "back_up": 0x4, "back_down": 0x8, "legs_up": 0x10, "legs_down": 0x20, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "memory_4": 0x4000, "toggle_lights": 0x20000},  # backend
    "89448": {"name": "RF-FREE-ELEC", "flat": 0x10000000, "back_up": 0x4, "back_down": 0x8, "legs_up": 0x10, "legs_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "memory_4": 0x4000},  # backend
    "89476": {"name": "RF-TOPLINE/11/AL/BK", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "memory_4": 0x4000, "toggle_lights": 0x20000},  # backend
    "89545": {"name": "RF-TOPLINE/11/AL/BK", "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "89746": {"name": "TOPLINE-11-SL-2M", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "zero_gravity": 0x4000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000},  # backend
    "89803": {"name": "LITELINE-7-SL-2M", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "zero_gravity": 0x4000, "toggle_lights": 0x20000},  # backend
    "89837": {"name": "RF-TOUCH/18/WH/BK/KL/L", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "toggle_lights": 0x20000, "massage": {"all": 0x200000, "foot_down": 0x1000000, "foot_toggle": 0x100000, "foot_up": 0x400000, "head_down": 0x800000, "head_toggle": 0x80000, "head_up": 0x800, "mode1": 0x20000000, "mode2": 0x40000000, "mode3": 0x80000000, "stop": 0x400}},  # backend
    "90167": {"name": "RF1058", "dot": True, "flat": 0x8000000, "head_up": 0x1, "head_down": 0x2, "feet_up": 0x4, "feet_down": 0x8, "zero_gravity": 0x1000, "quiet_sleep": 0x4000, "memory_save": (0x10000, 25, 200), "memory_1": 0x3000, "memory_2": 0x5000, "memory_3": 0x6000, "memory_4": 0x7000, "toggle_lights": 0x20000, "massage": {"foot_down": 0x1000000, "foot_up": 0x400, "head_down": 0x800000, "head_up": 0x800, "stop": 0x100, "wave": 0x10000000}},  # backend
    "90199": {"name": "TOPLINE-11-SL-3M/4M", "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "90269": {"name": "RF-STYLE/07/WH/WH", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "memory_4": 0x4000, "toggle_lights": 0x20000},  # backend
    "90354": {"name": "RF-STYLE/07/WH/WH", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "90392": {"name": "HS-IPROXX", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "90658": {"name": "RF-TOUCHLINE/15/BK/BK/KL", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "memory_4": 0x4000, "toggle_lights": 0x20000},  # backend
    "90675": {"name": "RF-TOUCHLINE/15/AL/BK/KL", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "memory_4": 0x4000, "toggle_lights": 0x20000},  # backend
    "90678": {"name": "RF-TOUCHLINE/19/AL/BK/KL", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # backend
    "90679": {"name": "RF-TOUCHLINE/19/BK/BK/KL", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "memory_4": 0x4000, "toggle_lights": 0x20000},  # backend
    "90882": {"name": "TOPLINE-11-BK-2M", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "zero_gravity": 0x4000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "90916": {"name": "RF-TOUCHLINE/21/AL/BK/KL", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000, "massage": {"all": 0x200000, "foot_down": 0x1000000, "foot_toggle": 0x100000, "foot_up": 0x400000, "head_down": 0x800000, "head_toggle": 0x80000, "head_up": 0x800, "mode1": 0x20000000, "mode2": 0x40000000, "mode3": 0x80000000, "stop": 0x400}},  # backend
    "90918": {"name": "RF-TOUCHLINE/21/AL/BK/KL", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "toggle_lights": 0x20000, "massage": {"all": 0x200000, "foot_down": 0x1000000, "foot_toggle": 0x100000, "foot_up": 0x400000, "head_down": 0x800000, "head_toggle": 0x80000, "head_up": 0x800, "mode1": 0x20000000, "mode2": 0x40000000, "mode3": 0x80000000, "stop": 0x400, "wave": 0x4000000}},  # backend
    "90926": {"name": "RF-ECO", "back_up": 0x1, "back_down": 0x2, "feet_up": 0x40, "feet_down": 0x20, "toggle_lights": 0x20000},  # backend
    "90928": {"name": "TOPLINE-11-SL-3M/4M", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000, "massage": {"all": 0x200000, "stop": 0x400}},  # backend
    "91050": {"name": "RF-TOUCHLINE/21/AL/BK/KL", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "toggle_lights": 0x20000, "massage": {"all": 0x200000, "foot_down": 0x1000000, "foot_toggle": 0x100000, "foot_up": 0x400000, "head_down": 0x800000, "head_toggle": 0x80000, "head_up": 0x800, "mode1": 0x20000000, "mode2": 0x40000000, "mode3": 0x80000000, "stop": 0x400}},  # backend
    "91244": {"name": "RF-FLASHLINE/07/WH/GY", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "91246": {"name": "RF-FLASHLINE/09/WH/GY", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "91334": {"name": "TOPLINE-11-BK-2M", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "91616": {"name": "HS-IPROXX", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "91751": {"name": "LITELINE-7-BK-2M", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "zero_gravity": 0x4000, "toggle_lights": 0x20000},  # backend
    "91914": {"name": "RF-TOUCH/23/WH/BK/KL", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "toggle_lights": 0x20000, "massage": {"all": 0x200000, "foot_down": 0x1000000, "foot_toggle": 0x100000, "foot_up": 0x400000, "head_down": 0x800000, "head_toggle": 0x80000, "head_up": 0x800, "mode1": 0x20000000, "mode2": 0x40000000, "mode3": 0x80000000, "stop": 0x400}},  # backend
    "91983": {"name": "RF1058", "dot": True, "flat": 0x8000000, "head_up": 0x1, "head_down": 0x2, "feet_up": 0x4, "feet_down": 0x8, "zero_gravity": 0x1000, "anti_snore": 0x4000, "memory_save": (0x10000, 25, 200), "memory_1": 0x2000, "memory_2": 0x8000, "memory_3": 0x3000, "toggle_lights": 0x20000, "massage": {"foot_down": 0x1000000, "foot_up": 0x400, "head_down": 0x800000, "head_up": 0x800, "stop": 0x100, "wave": 0x10000000}},  # backend
    "92063": {"name": "LITELINE-7-GR-2M", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "zero_gravity": 0x4000, "toggle_lights": 0x20000},  # backend
    "92113": {"name": "RF-STYLE/BK/BK/14/2009", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # backend
    "92129": {"name": "TOPLINE-11-SL-2M", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000, "massage": {"all": 0x200000, "foot_down": 0x1000000, "foot_toggle": 0x100000, "foot_up": 0x400000, "head_down": 0x800000, "head_toggle": 0x80000, "head_up": 0x800, "mode1": 0x20000000, "mode2": 0x40000000, "mode3": 0x80000000, "stop": 0x400, "wave": 0x4000000}},  # backend
    "92428": {"name": "RF", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "92461": {"name": "\n  RF-TOPLINE\n  SI", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "92471": {"name": "RF", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "92535": {"name": "RF-LITELINE/07/", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "92591": {"name": "RF-FLASHLINE/09/WH/GY", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "93025": {"name": "RF-STYLE/07/WH/WH", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "93055": {"name": "RF-TOPLINE/15/WH/BK", "flat": 0xa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "zero_gravity": 0x4000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "93300": {"name": "RF-STYLE/07/WH/WH", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "memory_save": (0x10000, 40, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # backend
    "93305": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "93306": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "93329": {"name": "RF-TOPLINE/15/AL/BK/M3/S/ST/IP20/BLI/FL/LED/M", "flat": 0x2a, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # backend
    "93332": {"name": "RF-TOPLINE/15/AL/BK/M4/S/ST/IP20/BLI/FL/LED/M", "flat": 0xaa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x20, "sync": 0x100, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "93339": {"name": "RF-TOPLINE/15/AL/BK", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000, "massage": {"foot_down": 0x1000000, "foot_toggle": 0x100000, "foot_up": 0x400000, "head_down": 0x800000, "head_toggle": 0x80000, "head_up": 0x800, "mode1": 0x20000000, "mode2": 0x40000000, "mode3": 0x80000000, "stop": 0x400}},  # backend
    "93558": {"name": "RF1058", "dot": True, "flat": 0x8000000, "head_up": 0x1, "head_down": 0x2, "feet_up": 0x4, "feet_down": 0x8, "zero_gravity": 0x1000, "anti_snore": 0x4000, "memory_save": (0x10000, 25, 200), "memory_1": 0x2000, "memory_2": 0x8000, "memory_3": 0x3000, "toggle_lights": 0x20000, "massage": {"foot_down": 0x1000000, "foot_up": 0x400, "head_down": 0x800000, "head_up": 0x800, "stop": 0x100, "wave": 0x10000000}},  # backend
    "94186": {"name": "RF-TOPLINE", "flat": 0x100000aa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "sync": 0x100, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "94238": {"name": "RF", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 25, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "94239": {"name": "RF", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "94369": {"name": "RF-TOPLINE", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x20, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "memory_4": 0x4000, "toggle_lights": 0x20000},  # backend
    "94428": {"name": "RF-TOPLINE", "flat": 0xaa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x80, "sync": 0x100, "child_lock": 0x8000000, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x4000, "memory_4": 0x8000, "toggle_lights": 0x20000},  # backend
    "94429": {"name": "RF-TOPLINE", "flat": 0xaa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "sync": 0x100, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "memory_3": 0x3000, "memory_4": 0x4000, "toggle_lights": 0x20000},  # backend
    "94430": {"name": "RF-TOPLINE", "flat": 0xaa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "94495": {"name": "RF-FLASHLINE/TEMPUR/07/BLACK", "flat": 0xaa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "94500": {"name": "RF-FLASHLINE/TEMPUR/09/BLACK", "flat": 0xaa, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "zero_gravity": 0x4000, "memory_save": (0x10000, 25, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "96312": {"name": "RF34/07/BK/BK", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "96313": {"name": "RF34/07/WH/GY", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "96314": {"name": "RF28/07/BK/BK", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "96315": {"name": "RF28/07/WH/GY", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "toggle_lights": 0x20000},  # backend
    "97134": {"name": "RF-TOPLINE/11/AL/BK/L", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "97135": {"name": "RF-TOPLINE/15/AL/BK/L", "flat": 0x10000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "head_up": 0x10, "head_down": 0x20, "feet_up": 0x40, "feet_down": 0x20, "memory_save": (0x10000, 10, 200), "memory_1": 0x1000, "memory_2": 0x2000, "toggle_lights": 0x20000},  # backend
    "97450": {"name": "RF34/09/WH/GY/", "dot": True, "flat": 0x8000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x1f000, 10, 200), "memory_1": 0x10000, "memory_2": 0x40000, "toggle_lights": 0x20000},  # backend
    "97544": {"name": "RF34/09/BK/BK/", "dot": True, "flat": 0x8000000, "back_up": 0x1, "back_down": 0x2, "legs_up": 0x4, "legs_down": 0x8, "memory_save": (0x10000, 10, 200), "memory_1": 0x10000, "memory_2": 0x40000, "toggle_lights": 0x20000},  # backend
    "98035": {"name": "RF6707", "dot": True, "flat": 0x8000000, "back_up": 0x4, "back_down": 0x8, "head_up": 0x1, "head_down": 0x2, "toggle_lights": 0x20000},  # backend
}
