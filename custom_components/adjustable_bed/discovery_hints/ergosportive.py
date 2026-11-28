"""A100 has only a saved substring and a DFU name, neither identifies a new bed.

Manual app setup is supported. No universal prefix or exclusive UART identity
can be inferred from the accepted PARTIAL evidence.
"""

from ._hints import Hint

HINTS: tuple[Hint, ...] = ()
