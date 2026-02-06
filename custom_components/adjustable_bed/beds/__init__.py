"""Bed controller implementations.

This module exports all bed controllers. Controllers are organized by protocol:

Protocol-based controllers:
- OkinCB24Controller: CB24 7-byte via Nordic UART (SmartBed by Okin)
- OkinHandleController: Okin 6-byte via BLE handle
- OkinUuidController: Okin 6-byte via UUID, requires pairing
- Okin7ByteController: 7-byte via Okin service UUID
- OkinNordicController: 7-byte via Nordic UART (Mattress Firm 900)
- LeggettGen2Controller: Leggett & Platt Gen2 ASCII protocol
- LeggettOkinController: Leggett & Platt Okin binary protocol
- LeggettWilinkeController: Leggett & Platt WiLinke 5-byte protocol

Brand-specific controllers:
- RichmatController, KeesonController, LinakController,
  ReverieController, JiecangController, LimossController, SolaceController, MotoSleepController, OctoController,
  RemacroController, RondureController, CoolBaseController, ScottLivingController, SBIController,
  SutaController, TiMOTIONAhfController
"""

from .base import BedController
from .coolbase import CoolBaseController
from .jensen import JensenController

# Brand-specific controllers (unchanged)
from .jiecang import JiecangController
from .keeson import KeesonController
from .leggett_gen2 import LeggettGen2Controller
from .leggett_okin import LeggettOkinController
from .leggett_wilinke import LeggettWilinkeController
from .linak import LinakController
from .limoss import LimossController
from .motosleep import MotoSleepController
from .octo import OctoController
from .okin_7byte import Okin7ByteController

# Protocol-based controllers
from .okin_cb24 import OkinCB24Controller
from .okin_handle import OkinHandleController
from .okin_nordic import OkinNordicController
from .okin_ore import OkinOreController
from .okin_uuid import OkinUuidController
from .remacro import RemacroController
from .reverie import ReverieController
from .reverie_nightstand import ReverieNightstandController
from .richmat import RichmatController
from .rondure import RondureController
from .sbi import SBIController
from .scott_living import ScottLivingController
from .solace import SolaceController
from .svane import SvaneController
from .suta import SutaController
from .timotion_ahf import TiMOTIONAhfController
from .vibradorm import VibradormController

__all__ = [
    # Base class
    "BedController",
    # Protocol-based controllers
    "OkinCB24Controller",
    "OkinHandleController",
    "OkinOreController",
    "OkinUuidController",
    "Okin7ByteController",
    "OkinNordicController",
    "LeggettGen2Controller",
    "LeggettOkinController",
    "LeggettWilinkeController",
    # Brand-specific controllers
    "CoolBaseController",
    "JiecangController",
    "JensenController",
    "KeesonController",
    "LimossController",
    "LinakController",
    "MotoSleepController",
    "OctoController",
    "RemacroController",
    "ReverieController",
    "ReverieNightstandController",
    "RichmatController",
    "RondureController",
    "SBIController",
    "ScottLivingController",
    "SolaceController",
    "SvaneController",
    "SutaController",
    "TiMOTIONAhfController",
    "VibradormController",
]
