"""Bed controllers, loaded on demand.

The factory imports selected modules through Home Assistant's import executor.
Legacy package-level class exports remain available for synchronous callers.
"""

from importlib import import_module
from typing import TYPE_CHECKING

from .base import BedController

if TYPE_CHECKING:
    from .coolbase import CoolBaseController as CoolBaseController
    from .dewertokin_rf_gateway import (
        DewertOkinRfGatewayController as DewertOkinRfGatewayController,
    )
    from .dewertokin_rf_gateway import (
        DewertOkinUuidRfGatewayController as DewertOkinUuidRfGatewayController,
    )
    from .jensen import JensenController as JensenController
    from .jiecang import JiecangController as JiecangController
    from .jiecang_app import JiecangAppController as JiecangAppController
    from .kaidi import KaidiController as KaidiController
    from .keeson import KeesonController as KeesonController
    from .leggett_gen2 import LeggettGen2Controller as LeggettGen2Controller
    from .leggett_lp_legacy import LeggettLpLegacyController as LeggettLpLegacyController
    from .leggett_okin import LeggettOkinController as LeggettOkinController
    from .leggett_wilinke import LeggettWilinkeController as LeggettWilinkeController
    from .limoss import LimossController as LimossController
    from .linak import LinakController as LinakController
    from .logicdata import LogicdataController as LogicdataController
    from .logicdata_app import LogicdataAppController as LogicdataAppController
    from .motosleep import MotoSleepController as MotoSleepController
    from .octo import OctoController as OctoController
    from .okin_7byte import Okin7ByteController as Okin7ByteController
    from .okin_cb24 import OkinCB24Controller as OkinCB24Controller
    from .okin_cb35 import OkinCB35Controller as OkinCB35Controller
    from .okin_cst import OkinCstController as OkinCstController
    from .okin_dot import OkinDotController as OkinDotController
    from .okin_handle import OkinHandleController as OkinHandleController
    from .okin_nordic import OkinNordicController as OkinNordicController
    from .okin_ore import OkinOreController as OkinOreController
    from .okin_rf_eco_bt import OkinRfEcoBtController as OkinRfEcoBtController
    from .okin_uuid import OkinUuidController as OkinUuidController
    from .remacro import RemacroController as RemacroController
    from .reverie import ReverieController as ReverieController
    from .reverie_nightstand import ReverieNightstandController as ReverieNightstandController
    from .richmat import RichmatController as RichmatController
    from .rondure import RondureController as RondureController
    from .sbi import SBIController as SBIController
    from .scott_living import ScottLivingController as ScottLivingController
    from .sleep_number import SleepNumberController as SleepNumberController
    from .sleep_number_mcr import SleepNumberMcrController as SleepNumberMcrController
    from .sleepstar import SleepStarController as SleepStarController
    from .sleepys_box25 import SleepysBox25Controller as SleepysBox25Controller
    from .sleepys_box25 import SleepysBox25LegacyController as SleepysBox25LegacyController
    from .solace import SolaceController as SolaceController
    from .star_elevate import StarElevateController as StarElevateController
    from .suta import SutaController as SutaController
    from .svane import SvaneController as SvaneController
    from .timotion_ahf import TiMOTIONAhfController as TiMOTIONAhfController
    from .vibradorm import VibradormController as VibradormController

_EXPORT_MODULES = {
    "CoolBaseController": "coolbase",
    "DewertOkinRfGatewayController": "dewertokin_rf_gateway",
    "DewertOkinUuidRfGatewayController": "dewertokin_rf_gateway",
    "JensenController": "jensen",
    "JiecangController": "jiecang",
    "JiecangAppController": "jiecang_app",
    "KaidiController": "kaidi",
    "KeesonController": "keeson",
    "LeggettGen2Controller": "leggett_gen2",
    "LeggettLpLegacyController": "leggett_lp_legacy",
    "LeggettOkinController": "leggett_okin",
    "LeggettWilinkeController": "leggett_wilinke",
    "LimossController": "limoss",
    "LinakController": "linak",
    "LogicdataController": "logicdata",
    "LogicdataAppController": "logicdata_app",
    "MotoSleepController": "motosleep",
    "OctoController": "octo",
    "Okin7ByteController": "okin_7byte",
    "OkinCB24Controller": "okin_cb24",
    "OkinCB35Controller": "okin_cb35",
    "OkinCstController": "okin_cst",
    "OkinDotController": "okin_dot",
    "OkinHandleController": "okin_handle",
    "OkinNordicController": "okin_nordic",
    "OkinOreController": "okin_ore",
    "OkinRfEcoBtController": "okin_rf_eco_bt",
    "OkinUuidController": "okin_uuid",
    "RemacroController": "remacro",
    "ReverieController": "reverie",
    "ReverieNightstandController": "reverie_nightstand",
    "RichmatController": "richmat",
    "RondureController": "rondure",
    "SBIController": "sbi",
    "ScottLivingController": "scott_living",
    "SleepNumberController": "sleep_number",
    "SleepNumberMcrController": "sleep_number_mcr",
    "SleepStarController": "sleepstar",
    "SleepysBox25Controller": "sleepys_box25",
    "SleepysBox25LegacyController": "sleepys_box25",
    "SolaceController": "solace",
    "StarElevateController": "star_elevate",
    "SutaController": "suta",
    "SvaneController": "svane",
    "TiMOTIONAhfController": "timotion_ahf",
    "VibradormController": "vibradorm",
}

__all__ = [
    # Base class
    "BedController",
    # Protocol-based controllers
    "DewertOkinRfGatewayController",
    "DewertOkinUuidRfGatewayController",
    "OkinCB24Controller",
    "OkinCB35Controller",
    "OkinCstController",
    "OkinDotController",
    "OkinHandleController",
    "OkinOreController",
    "OkinRfEcoBtController",
    "OkinUuidController",
    "Okin7ByteController",
    "OkinNordicController",
    "LeggettGen2Controller",
    "LeggettLpLegacyController",
    "LeggettOkinController",
    "LeggettWilinkeController",
    # Brand-specific controllers
    "CoolBaseController",
    "JiecangController",
    "JiecangAppController",
    "JensenController",
    "KaidiController",
    "KeesonController",
    "LimossController",
    "LinakController",
    "LogicdataController",
    "LogicdataAppController",
    "MotoSleepController",
    "OctoController",
    "RemacroController",
    "ReverieController",
    "ReverieNightstandController",
    "RichmatController",
    "RondureController",
    "SBIController",
    "ScottLivingController",
    "SleepNumberController",
    "SleepNumberMcrController",
    "SleepStarController",
    "SleepysBox25Controller",
    "SleepysBox25LegacyController",
    "StarElevateController",
    "SolaceController",
    "SvaneController",
    "SutaController",
    "TiMOTIONAhfController",
    "VibradormController",
]


def __getattr__(name: str) -> type[BedController]:
    """Resolve compatibility exports without importing unrelated controllers."""
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f".{module_name}", __name__)
    controller: type[BedController] = getattr(module, name)
    globals()[name] = controller
    return controller
