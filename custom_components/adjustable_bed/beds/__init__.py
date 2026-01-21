"""Bed controller implementations.

This module exports all bed controllers. Controllers are organized by protocol:

Protocol-based controllers:
- OkinHandleController: Okin 6-byte via BLE handle
- OkinUuidController: Okin 6-byte via UUID, requires pairing
- Okin7ByteController: 7-byte via Okin service UUID
- OkinNordicController: 7-byte via Nordic UART
- LeggettGen2Controller: Leggett & Platt Gen2 ASCII protocol
- LeggettOkinController: Leggett & Platt Okin binary protocol
- LeggettWilinkeController: Leggett & Platt WiLinke 5-byte protocol

Brand-specific controllers:
- RichmatController, KeesonController, LinakController,
  ReverieController, JiecangController, SolaceController, MotoSleepController, OctoController
"""

from .base import BedController

# Brand-specific controllers (unchanged)
from .jiecang import JiecangController
from .keeson import KeesonController
from .leggett_gen2 import LeggettGen2Controller
from .leggett_okin import LeggettOkinController
from .leggett_wilinke import LeggettWilinkeController
from .linak import LinakController
from .motosleep import MotoSleepController
from .octo import OctoController
from .okin_7byte import Okin7ByteController

# Protocol-based controllers
from .okin_handle import OkinHandleController
from .okin_nordic import OkinNordicController
from .okin_uuid import OkinUuidController
from .reverie import ReverieController
from .richmat import RichmatController
from .solace import SolaceController

__all__ = [
    # Base class
    "BedController",
    # Protocol-based controllers
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
    "SolaceController",
]
