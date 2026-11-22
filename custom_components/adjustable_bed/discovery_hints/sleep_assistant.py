"""The app lists case-sensitive KSBT names of exactly thirteen characters.

The manifest admits the prefix. Detection applies the exact length and offers
this app alongside other receivers sharing that prefix.
"""

from ._hints import names

HINTS = (names("KSBT", bed_types={"sleep_assistant"}, connectable=True),)
