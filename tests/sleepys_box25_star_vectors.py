"""Frozen Sleepy's Elite BOX25_STAR motor literals (#483).

From ``COMMAND_FINAL_VECTORS.v2.tsv`` of the accepted com.okin.bedding.sleepy
1.1.5 report (``-2026-10-26-39bdcafa-repair-005``), selector ``BOX25_STAR``:
every held motor frame and the STOP its release sends.
"""

BOX25_STAR_FRAMES: frozenset[str] = frozenset(
    {
        "5a0103103000a5",  # headUp
        "5a0103103001a5",  # headDown
        "5a0103103002a5",  # footUp
        "5a0103103003a5",  # footDown
        "5a0103103006a5",  # lumbarUp
        "5a0103103007a5",  # lumbarDown
        "5a010310300aa5",  # neckTiltUp
        "5a010310300ba5",  # neckTiltDown
        "5a010310300fa5",  # stop
    }
)
