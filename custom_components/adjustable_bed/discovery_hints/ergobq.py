"""ErgoBQ uses product service data, not a unique service UUID or name gate.

The Nordic UART service is shared. Detection refines existing scan candidates
by their exact 16-byte product ID; manual setup is always available. The
unreconciled native initial scan filters do not establish a broader matcher.
"""

from ._hints import Hint

HINTS: tuple[Hint, ...] = ()
