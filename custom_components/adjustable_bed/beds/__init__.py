"""Bed controller implementations.

This module exports all bed controllers. Controllers are organized by protocol:

Protocol-based controllers (new naming):
- OkinHandleController: Okin 6-byte via BLE handle (formerly DewertOkin)
- OkinUuidController: Okin 6-byte via UUID, requires pairing (formerly Okimat)
- Okin7ByteController: 7-byte via Okin service UUID (formerly Nectar)
- OkinNordicController: 7-byte via Nordic UART (formerly MattressFirm)
- LeggettGen2Controller: Leggett & Platt Gen2 ASCII protocol
- LeggettOkinController: Leggett & Platt Okin binary protocol
- LeggettWilinkeController: Leggett & Platt WiLinke 5-byte protocol (formerly MlRM)

Brand-specific controllers (unchanged):
- RichmatController, KeesonController, SertaController, LinakController,
  ReverieController, JiecangController, SolaceController, MotoSleepController, OctoController

Legacy aliases (for backwards compatibility):
- DewertOkinController -> OkinHandleController
- OkimatController -> OkinUuidController
- NectarController -> Okin7ByteController
- MattressFirmController -> OkinNordicController
- LeggettPlattMlrmController -> LeggettWilinkeController
"""

from .base import BedController

# New protocol-based controllers
from .okin_handle import OkinHandleController
from .okin_uuid import OkinUuidController
from .okin_7byte import Okin7ByteController
from .okin_nordic import OkinNordicController
from .leggett_gen2 import LeggettGen2Controller
from .leggett_okin import LeggettOkinController
from .leggett_wilinke import LeggettWilinkeController

# Brand-specific controllers (unchanged)
from .jiecang import JiecangController
from .keeson import KeesonController
from .linak import LinakController
from .motosleep import MotoSleepController
from .octo import OctoController
from .reverie import ReverieController
from .richmat import RichmatController
from .serta import SertaController
from .solace import SolaceController

# Legacy aliases - import from wrapper modules for backwards compatibility
from .dewertokin import DewertOkinController
from .okimat import OkimatController
from .nectar import NectarController
from .mattressfirm import MattressFirmController
from .leggett_platt import LeggettPlattController
from .leggett_platt_mlrm import LeggettPlattMlrmController

__all__ = [
    # Base class
    "BedController",
    # New protocol-based controllers
    "OkinHandleController",
    "OkinUuidController",
    "Okin7ByteController",
    "OkinNordicController",
    "LeggettGen2Controller",
    "LeggettOkinController",
    "LeggettWilinkeController",
    # Brand-specific controllers
    "JiecangController",
    "KeesonController",
    "LinakController",
    "MotoSleepController",
    "OctoController",
    "ReverieController",
    "RichmatController",
    "SertaController",
    "SolaceController",
    # Legacy aliases (backwards compatibility)
    "DewertOkinController",
    "OkimatController",
    "NectarController",
    "MattressFirmController",
    "LeggettPlattController",
    "LeggettPlattMlrmController",
]
