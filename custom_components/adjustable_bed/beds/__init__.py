"""Bed controllers, loaded on demand.

The factory imports selected modules through Home Assistant's import executor.
Legacy package-level class exports remain available for synchronous callers.
"""

from importlib import import_module
from typing import TYPE_CHECKING

from .base import BedController

if TYPE_CHECKING:
    from .adjustable_lumbar import AdjustableLumbarController as AdjustableLumbarController
    from .adjustamattress.controller import AdjustaMattressController as AdjustaMattressController
    from .bedjet_powerlayer import BedJetPowerLayerController as BedJetPowerLayerController
    from .bedsense import BedSenseController as BedSenseController
    from .bf_cherish.controller import BfCherishController as BfCherishController
    from .casper_base.controller import CasperBaseController as CasperBaseController
    from .casper_sleep.controller import CasperSleepController as CasperSleepController
    from .comfort_enhancements.controller import (
        ComfortEnhancementsController as ComfortEnhancementsController,
    )
    from .comfort_motion import ComfortMotionController as ComfortMotionController
    from .coolbase import CoolBaseController as CoolBaseController
    from .customatic.controller import CustomaticController as CustomaticController
    from .dewertokin_rf_gateway import (
        DewertOkinRfGatewayController as DewertOkinRfGatewayController,
    )
    from .dewertokin_rf_gateway import (
        DewertOkinUuidRfGatewayController as DewertOkinUuidRfGatewayController,
    )
    from .doublesleep.controller import DoubleSleepController as DoubleSleepController
    from .ergo_slim import ErgoSlimController as ErgoSlimController
    from .ergomotion4.controller import Ergomotion4Controller as Ergomotion4Controller
    from .ergomotion_app import ErgomotionAppController as ErgomotionAppController
    from .eshine.controller import EshineController as EshineController
    from .eshine_okin.controller import EshineOkinController as EshineOkinController
    from .fsm_relax.controller import FsmRelaxController as FsmRelaxController
    from .furnimove.controller import FurniMoveController as FurniMoveController
    from .glideaway_motion.controller import GlideawayMotionController as GlideawayMotionController
    from .gmmotor.controller import GmmotorController as GmmotorController
    from .gmmotor.desk import GmmotorDeskController as GmmotorDeskController
    from .gmmotor.sleep import GmmotorSleepController as GmmotorSleepController
    from .goodvibe.controller import GoodVibeController as GoodVibeController
    from .hjbed.controller import HJBedController as HJBedController
    from .innova import InnovaController as InnovaController
    from .isleep import IsleepController as IsleepController
    from .jensen.controller import JensenController as JensenController
    from .jensen.linon import JensenLinonController as JensenLinonController
    from .jiecang.app import JiecangAppController as JiecangAppController
    from .jiecang.controller import JiecangController as JiecangController
    from .kaidi.controller import KaidiController as KaidiController
    from .keeson.controller import KeesonController as KeesonController
    from .leggett.gen2 import LeggettGen2Controller as LeggettGen2Controller
    from .leggett.lp_legacy import LeggettLpLegacyController as LeggettLpLegacyController
    from .leggett.okin import LeggettOkinController as LeggettOkinController
    from .leggett.wilinke import LeggettWilinkeController as LeggettWilinkeController
    from .limoss.controller import LimossController as LimossController
    from .limoss.remote import LimossRemoteController as LimossRemoteController
    from .linak.controller import LinakController as LinakController
    from .logicdata.air_pump import LogicdataAirPumpController as LogicdataAirPumpController
    from .logicdata.app import LogicdataAppController as LogicdataAppController
    from .logicdata.controller import LogicdataController as LogicdataController
    from .malouf.app import MaloufAppController as MaloufAppController
    from .motion_bed.controller import MotionBedController as MotionBedController
    from .motomotion.controller import MotoMotionController as MotoMotionController
    from .motosleep import MotoSleepController as MotoSleepController
    from .octo.controller import OctoController as OctoController
    from .okin_7byte import Okin7ByteController as Okin7ByteController
    from .okin_cb24 import OkinCB24Controller as OkinCB24Controller
    from .okin_cb35 import OkinCB35Controller as OkinCB35Controller
    from .okin_cst import OkinCstController as OkinCstController
    from .okin_dot import OkinDotController as OkinDotController
    from .okin_handle import OkinHandleController as OkinHandleController
    from .okin_nordic import OkinNordicController as OkinNordicController
    from .okin_ore import OkinOreController as OkinOreController
    from .okin_rf_eco_bt import OkinRfEcoBtController as OkinRfEcoBtController
    from .okin_uuid.controller import OkinUuidController as OkinUuidController
    from .omazz_adjusto_iii import OmazzAdjustoIIIController as OmazzAdjustoIIIController
    from .ore_comfort_bed import OreComfortBedController as OreComfortBedController
    from .remacro.controller import RemacroController as RemacroController
    from .resident.controller import ResidentController as ResidentController
    from .reverie.controller import ReverieController as ReverieController
    from .reverie.nightstand import ReverieNightstandController as ReverieNightstandController
    from .richmat.controller import RichmatController as RichmatController
    from .richmat_classic.controller import RichmatClassicController as RichmatClassicController
    from .richmat_mh.controller import RichmatMhController as RichmatMhController
    from .rondure import RondureController as RondureController
    from .row_control import RowControlController as RowControlController
    from .ruf_richmat.controller import RufRichmatController as RufRichmatController
    from .ruf_richmat.sleep import RufRichmatSleepController as RufRichmatSleepController
    from .sbi import QPlusAppController as QPlusAppController
    from .sbi import SBIController as SBIController
    from .scott_living import ScottLivingController as ScottLivingController
    from .serenity.controller import SerenityController as SerenityController
    from .serenity.controller import TranquilController as TranquilController
    from .serenity.controller import ZSeriesController as ZSeriesController
    from .serta_mp_remote import SertaMPRemoteController as SertaMPRemoteController
    from .simmons.controller import SimmonsController as SimmonsController
    from .sleep_number.controller import SleepNumberController as SleepNumberController
    from .sleep_number.mcr import SleepNumberMcrController as SleepNumberMcrController
    from .sleepstar import SleepStarController as SleepStarController
    from .sleeptracker.controller import SleeptrackerController as SleeptrackerController
    from .sleepys.box25 import SleepysBox25Controller as SleepysBox25Controller
    from .sleepys.box25 import SleepysBox25LegacyController as SleepysBox25LegacyController
    from .solace.controller import SolaceController as SolaceController
    from .starcode.abm5_4 import StarcodeAbm5_4Controller as StarcodeAbm5_4Controller
    from .starcode.m5x5 import StarcodeM5X5Controller as StarcodeM5X5Controller
    from .starcode.star_elevate import StarElevateController as StarElevateController
    from .suta import SutaController as SutaController
    from .svane.controller import SvaneController as SvaneController
    from .tempur_au import TempurAUController as TempurAUController
    from .tempur_curve import TempurCurveController as TempurCurveController
    from .timotion_ahf import TiMOTIONAhfController as TiMOTIONAhfController
    from .vibradorm.app import VibradormAppController as VibradormAppController
    from .vibradorm.controller import VibradormController as VibradormController
    from .vmatbasic.controller import VMatBasicController as VMatBasicController
    from .woosa import WoosaController as WoosaController

_EXPORT_MODULES = {
    "ResidentController": "resident.controller",
    "GoodVibeController": "goodvibe.controller",
    "MotoMotionController": "motomotion.controller",
    "HJBedController": "hjbed.controller",
    "DoubleSleepController": "doublesleep.controller",
    "GmmotorController": "gmmotor.controller",
    "GmmotorDeskController": "gmmotor.desk",
    "GmmotorSleepController": "gmmotor.sleep",
    'TempurCurveController': 'tempur_curve',
    'QPlusAppController': 'sbi',
    'SertaMPRemoteController': 'serta_mp_remote',
    'OmazzAdjustoIIIController': 'omazz_adjusto_iii',
    'ErgomotionAppController': 'ergomotion_app',
    'RichmatClassicController': 'richmat_classic.controller',
    'Ergomotion4Controller': 'ergomotion4.controller',
    'RowControlController': 'row_control',
    'ErgoSlimController': 'ergo_slim',
    'TempurAUController': 'tempur_au',
    "CasperBaseController": "casper_base.controller",
    "HushBaseController": "hush_base.controller",
    "HushSleepController": "hush_sleep.controller",
    "CasperSleepController": "casper_sleep.controller",
    "ComfortEnhancementsController": "comfort_enhancements.controller",
    "EshineController": "eshine.controller",
    "EshineOkinController": "eshine_okin.controller",
    "GlideawayMotionController": "glideaway_motion.controller",
    "BedSenseController": "bedsense",
    "InnovaController": "innova",
    "StarcodeM5X5Controller": "starcode.m5x5",
    "FurniMoveController": "furnimove.controller",
    "FsmRelaxController": "fsm_relax.controller",
    "SerenityController": "serenity.controller",
    "TranquilController": "serenity.controller",
    "ZSeriesController": "serenity.controller",
    "SimmonsController": "simmons.controller",
    "AdjustaMattressController": "adjustamattress.controller",
    "AdjustableLumbarController": "adjustable_lumbar",
    "BedJetPowerLayerController": "bedjet_powerlayer",
    "RufRichmatController": "ruf_richmat.controller",
    "RufRichmatSleepController": "ruf_richmat.sleep",
    "RichmatMhController": "richmat_mh.controller",
    "CustomaticController": "customatic.controller",
    "CoolBaseController": "coolbase",
    "DewertOkinRfGatewayController": "dewertokin_rf_gateway",
    "DewertOkinUuidRfGatewayController": "dewertokin_rf_gateway",
    "JensenController": "jensen.controller",
    "JensenLinonController": "jensen.linon",
    "ComfortMotionController": "comfort_motion",
    "JiecangController": "jiecang.controller",
    "JiecangAppController": "jiecang.app",
    "IsleepController": "isleep",
    "KaidiController": "kaidi.controller",
    "KeesonController": "keeson.controller",
    "LeggettGen2Controller": "leggett.gen2",
    "LeggettLpLegacyController": "leggett.lp_legacy",
    "LeggettOkinController": "leggett.okin",
    "LeggettWilinkeController": "leggett.wilinke",
    "LimossController": "limoss.controller",
    "LimossRemoteController": "limoss.remote",
    "LinakController": "linak.controller",
    "LogicdataController": "logicdata.controller",
    "LogicdataAppController": "logicdata.app",
    "LogicdataAirPumpController": "logicdata.air_pump",
    "MaloufAppController": "malouf.app",
    "MotionBedController": "motion_bed.controller",
    "MotoSleepController": "motosleep",
    "OctoController": "octo.controller",
    "Okin7ByteController": "okin_7byte",
    "OkinCB24Controller": "okin_cb24",
    "OkinCB35Controller": "okin_cb35",
    "OkinCstController": "okin_cst",
    "OkinDotController": "okin_dot",
    "OkinHandleController": "okin_handle",
    "OkinNordicController": "okin_nordic",
    "BfCherishController": "bf_cherish.controller",
    "OkinOreController": "okin_ore",
    "OkinRfEcoBtController": "okin_rf_eco_bt",
    "OkinUuidController": "okin_uuid.controller",
    "OreComfortBedController": "ore_comfort_bed",
    "RemacroController": "remacro.controller",
    "ReverieController": "reverie.controller",
    "ReverieNightstandController": "reverie.nightstand",
    "RichmatController": "richmat.controller",
    "RondureController": "rondure",
    "SBIController": "sbi",
    "ScottLivingController": "scott_living",
    "SleepNumberController": "sleep_number.controller",
    "SleepNumberMcrController": "sleep_number.mcr",
    "SleeptrackerController": ("sleeptracker.controller", "SleeptrackerController"),
    "SleepStarController": "sleepstar",
    "SleepysBox25Controller": "sleepys.box25",
    "SleepysBox25LegacyController": "sleepys.box25",
    "SolaceController": "solace.controller",
    "StarElevateController": "starcode.star_elevate",
    "SutaController": "suta",
    "SvaneController": "svane.controller",
    "TiMOTIONAhfController": "timotion_ahf",
    "VibradormController": "vibradorm.controller",
    "VibradormAppController": "vibradorm.app",
    "VMatBasicController": "vmatbasic.controller",
    "StarcodeAbm5_4Controller": "starcode.abm5_4",
    "WoosaController": "woosa",
}

__all__ = [
    "DoubleSleepController",
    'TempurCurveController',
    'QPlusAppController',
    'SertaMPRemoteController',
    'OmazzAdjustoIIIController',
    'ErgomotionAppController',
    'RichmatClassicController',
    'Ergomotion4Controller',
    'RowControlController',
    'ErgoSlimController',
    'TempurAUController',

    # Base class
    "BedController",
    # Protocol-based controllers
    "BedJetPowerLayerController",
    "DewertOkinRfGatewayController",
    "DewertOkinUuidRfGatewayController",
    "OkinCB24Controller",
    "OkinCB35Controller",
    "OkinCstController",
    "OkinDotController",
    "OkinHandleController",
    "BfCherishController",
    "OkinOreController",
    "OkinRfEcoBtController",
    "OkinUuidController",
    "Okin7ByteController",
    "OreComfortBedController",
    "InnovaController",
    "OkinNordicController",
    "LeggettGen2Controller",
    "LeggettLpLegacyController",
    "LeggettOkinController",
    "LeggettWilinkeController",
    # Brand-specific controllers
    "CoolBaseController",
    "ComfortMotionController",
    "JiecangController",
    "JiecangAppController",
    "JensenController",
    "JensenLinonController",
    "KaidiController",
    "KeesonController",
    "LimossController",
    "LinakController",
    "LogicdataController",
    "LogicdataAppController",
    "LogicdataAirPumpController",
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
    "VibradormAppController",
    "WoosaController",
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
