# Current HA aliases voluptuous to Probatio at startup. Mirror that alias for Pyright,
# which otherwise resolves the separate Voluptuous package installed by tests.
from probatio import *  # noqa: F403
