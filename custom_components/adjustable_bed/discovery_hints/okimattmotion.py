"""OkimattMotion is an explicit app selection.

The app's OKIN, Comfort and BLE prefixes admit unrelated receivers. Its
write service is shared and does not identify the app either.
"""

from ._hints import Hint

HINTS: tuple[Hint, ...] = ()
