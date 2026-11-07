"""HJBed 2.1.2 exact selectable profiles and static details.

Source identity, exclusions and complete bindings: APK Protocol Audit row 121.
Generated outside this repository from the accepted report (SHA-256
88ce24aebae03a2a83fb0527d5b679329aaedc6624fd9a5c7efeb10fdf45d3f0);
no generator is checked in, so edits are by hand. Hardware unverified.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Action:
    """A selected static detail, including its own gesture contract."""

    object: str
    enum: str
    code: int
    save_code: int | None
    sustain: bool
    release: bool
    kind: str

    @property
    def key(self) -> str:
        return self.enum.removeprefix("deviceFunctionItem").removeprefix("deviceFunctionSofa")


# fmt: off
ACTIONS: dict[str, Action] = {
    "9738e1": Action("9738e1", "deviceFunctionItemAntiSnoring", 70, 105, False, False, "preset"),
    "975961": Action("975961", "deviceFunctionItemAntiSnoring", 70, 105, True, False, "preset"),
    "974961": Action("974961", "deviceFunctionItemBedLight", 60, None, False, True, "press"),
    "9759e1": Action("9759e1", "deviceFunctionItemBedLightClose", 117, None, False, False, "press"),
    "9744e1": Action("9744e1", "deviceFunctionItemCoaxingSleepMode", 134, 137, False, False, "preset"),
    "973761": Action("973761", "deviceFunctionItemExitLimit", 0, None, False, False, "press"),
    "975861": Action("975861", "deviceFunctionItemFootBoxDown", 37, None, True, True, "motor"),
    "9758e1": Action("9758e1", "deviceFunctionItemFootBoxUp", 36, None, True, True, "motor"),
    "9740e1": Action("9740e1", "deviceFunctionItemFootDown", 39, None, True, True, "motor"),
    "974161": Action("974161", "deviceFunctionItemFootUp", 38, None, True, True, "motor"),
    "9743e1": Action("9743e1", "deviceFunctionItemHeadAndFootDown", 42, None, True, True, "motor"),
    "974461": Action("974461", "deviceFunctionItemHeadAndFootUp", 41, None, True, True, "motor"),
    "9741e1": Action("9741e1", "deviceFunctionItemHeadDown", 37, None, True, True, "motor"),
    "974261": Action("974261", "deviceFunctionItemHeadUp", 36, None, True, True, "motor"),
    "9749e1": Action("9749e1", "deviceFunctionItemLightBoard", 80, None, False, True, "press"),
    "973961": Action("973961", "deviceFunctionItemLoungePosition", 89, 101, False, False, "preset"),
    "973fe1": Action("973fe1", "deviceFunctionItemLumberDown", 64, None, True, True, "motor"),
    "974be1": Action("974be1", "deviceFunctionItemLumberDown", 66, None, True, True, "motor"),
    "974061": Action("974061", "deviceFunctionItemLumberUp", 63, None, True, True, "motor"),
    "974c61": Action("974c61", "deviceFunctionItemLumberUp", 65, None, True, True, "motor"),
    "973be1": Action("973be1", "deviceFunctionItemMassage10MinuteTimer", 95, None, False, True, "press"),
    "973b61": Action("973b61", "deviceFunctionItemMassage20MinuteTimer", 99, None, False, True, "press"),
    "973ae1": Action("973ae1", "deviceFunctionItemMassage30MinuteTimer", 97, None, False, True, "press"),
    "973d61": Action("973d61", "deviceFunctionItemMassageFootInstensityStrengthen", 78, None, False, True, "press"),
    "973de1": Action("973de1", "deviceFunctionItemMassageHeadInstensityStrengthen", 76, None, False, True, "press"),
    "974361": Action("974361", "deviceFunctionItemMassageInstensityStrengthen", 52, None, False, True, "press"),
    "973c61": Action("973c61", "deviceFunctionItemMassageModeAllOff", 94, None, False, True, "press"),
    "973ce1": Action("973ce1", "deviceFunctionItemMassageModeChange", 72, None, False, True, "press"),
    "9742e1": Action("9742e1", "deviceFunctionItemMassageSwitch", 111, None, False, True, "press"),
    "973861": Action("973861", "deviceFunctionItemMemoryPosition1", 46, 43, False, False, "preset"),
    "974e61": Action("974e61", "deviceFunctionItemMemoryPosition1", 46, 43, True, False, "preset"),
    "9737e1": Action("9737e1", "deviceFunctionItemMemoryPosition2", 47, 44, False, False, "preset"),
    "974de1": Action("974de1", "deviceFunctionItemMemoryPosition2", 47, 44, True, False, "preset"),
    "9751e1": Action("9751e1", "deviceFunctionItemMemoryPosition3", 48, 45, True, False, "preset"),
    "975261": Action("975261", "deviceFunctionItemMemoryPosition4", 178, 179, True, False, "preset"),
    "973e61": Action("973e61", "deviceFunctionItemMotorReset", 49, None, False, True, "reset"),
    "974f61": Action("974f61", "deviceFunctionItemMotorReset", 49, None, True, True, "reset"),
    "9748e1": Action("9748e1", "deviceFunctionItemMusicBlueToothSwitch", 216, None, False, False, "music"),
    "974661": Action("974661", "deviceFunctionItemMusicNextSong", 211, None, False, False, "music"),
    "9745e1": Action("9745e1", "deviceFunctionItemMusicPausePlay", 215, None, False, False, "music"),
    "9746e1": Action("9746e1", "deviceFunctionItemMusicPreviousSong", 210, None, False, False, "music"),
    "974861": Action("974861", "deviceFunctionItemMusicShakeMode", 214, None, False, False, "music"),
    "975ae1": Action("975ae1", "deviceFunctionItemMusicSwitchSoundTrack", 196, None, False, False, "music"),
    "974761": Action("974761", "deviceFunctionItemMusicVolumuDown", 213, None, False, False, "music"),
    "9747e1": Action("9747e1", "deviceFunctionItemMusicVolumuUp", 212, None, False, False, "music"),
    "973ee1": Action("973ee1", "deviceFunctionItemPillowDown", 66, None, True, True, "motor"),
    "974a61": Action("974a61", "deviceFunctionItemPillowDown", 64, None, True, True, "motor"),
    "973f61": Action("973f61", "deviceFunctionItemPillowUp", 65, None, True, True, "motor"),
    "974ae1": Action("974ae1", "deviceFunctionItemPillowUp", 63, None, True, True, "motor"),
    "975a61": Action("975a61", "deviceFunctionItemStop", 110, None, False, False, "press"),
    "9752e1": Action("9752e1", "deviceFunctionItemSyncOff", 189, None, False, False, "press"),
    "974b61": Action("974b61", "deviceFunctionItemSyncOn", 188, None, False, False, "press"),
    "973a61": Action("973a61", "deviceFunctionItemTVPosition", 88, 100, False, False, "preset"),
    "974d61": Action("974d61", "deviceFunctionItemTVPosition", 88, 100, True, False, "preset"),
    "975161": Action("975161", "deviceFunctionItemTVPosition", 88, 100, True, False, "preset"),
    "974fe1": Action("974fe1", "deviceFunctionItemTileDown", 92, None, True, True, "motor"),
    "975061": Action("975061", "deviceFunctionItemTileUp", 91, None, True, True, "motor"),
    "9739e1": Action("9739e1", "deviceFunctionItemZeroGravity", 69, 102, False, False, "preset"),
    "974ce1": Action("974ce1", "deviceFunctionItemZeroGravity", 69, 102, True, False, "preset"),
    "9750e1": Action("9750e1", "deviceFunctionItemZeroGravity", 69, 102, True, False, "preset"),
    "975461": Action("975461", "deviceFunctionSofaBackward", 92, None, True, True, "motor"),
    "9754e1": Action("9754e1", "deviceFunctionSofaForword", 91, None, True, True, "motor"),
    "975561": Action("975561", "deviceFunctionSofaHeadDown", 37, None, True, True, "motor"),
    "9755e1": Action("9755e1", "deviceFunctionSofaHeadUp", 36, None, True, True, "motor"),
    "975361": Action("975361", "deviceFunctionSofaLight", 60, None, False, False, "press"),
    "975661": Action("975661", "deviceFunctionSofaLumbarDown", 64, None, True, True, "motor"),
    "9756e1": Action("9756e1", "deviceFunctionSofaLumbarUp", 63, None, True, True, "motor"),
    "975761": Action("975761", "deviceFunctionSofaPillowDown", 66, None, True, True, "motor"),
    "9757e1": Action("9757e1", "deviceFunctionSofaPillowUp", 65, None, True, True, "motor"),
    "9753e1": Action("9753e1", "deviceFunctionSofaSitPosition", 229, None, True, False, "sofa_reset"),
}
# fmt: on


@dataclass(frozen=True, slots=True)
class Product:
    """A first-match selectable product, never inferred from shared transport."""

    object: str
    label: str
    remote: str
    current: bool
    motor: tuple[str, ...]
    massage: tuple[str, ...]
    preset: tuple[str, ...]
    alarm: tuple[str, ...]
    music: bool
    alarms: bool
    repeat: bool
    light: bool
    coupled: bool
    sofa: bool


# fmt: off
PRODUCTS: dict[str, Product] = {
    "aw_motionhc800": Product("990c31", "HC800", "LTRM", False, ("974261", "9741e1", "974161", "9740e1", "974061", "973fe1", "9749e1", "974961", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("9738e1", "9739e1", "973861"), ("9738e1", "9739e1", "973861"), True, True, False, True, False, False),
    "aw_motionsn300": Product("990cf1", "SN300", "B3RN", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "9749e1", "974961", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("9739e1", "9738e1", "973a61", "973861"), ("9739e1", "9738e1", "973a61", "973861"), False, True, False, True, False, False),
    "aw_motionsn500": Product("990c91", "SN500", "LTRM", False, ("974261", "9741e1", "974161", "9740e1", "974061", "973fe1", "973f61", "973ee1", "9749e1", "974961", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("9738e1", "9739e1"), ("9738e1", "9739e1"), False, True, False, True, False, False),
    "dream_blue": Product("98fcd1", "blue", "LTRM", False, ("974261", "9741e1", "974161", "9740e1", "974061", "973fe1", "973f61", "973ee1", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("973a61", "9739e1", "973961", "9738e1", "973861", "9737e1"), ("973a61", "9739e1", "973961", "9738e1", "973861", "9737e1"), True, True, False, True, False, False),
    "dream_green": Product("98fd91", "green", "HARM", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "973e61"), ("974361", "973ce1", "9742e1", "973be1", "973b61", "973ae1"), ("9739e1", "973a61", "973861", "9738e1"), ("9739e1", "973a61", "973861", "9738e1"), False, True, False, True, False, False),
    "dream_orange": Product("98fd31", "orange", "JMRM", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "973e61"), ("974361", "973ce1", "9742e1", "973be1", "973b61", "973ae1"), ("9739e1", "973a61", "973861", "9738e1"), ("9739e1", "973a61", "973861", "9738e1"), False, True, False, True, True, False),
    "dream_yellow": Product("990d51", "yellow", "HBRM", False, ("974261", "9741e1", "974161", "9740e1", "974ae1", "974a61", "973e61"), ("973de1", "973d61", "973ce1", "9742e1", "973be1", "973b61", "973ae1"), ("9739e1", "973a61", "973861", "9737e1", "9738e1"), ("9739e1", "973a61", "973861", "9737e1", "9738e1"), False, True, False, True, False, False),
    "flexxafeg300": Product("990211", "AFEG300", "L5RN", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "973e61", "974961"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("973961", "9739e1", "973a61", "973861", "9744e1"), ("973961", "9739e1", "973a61", "973861"), False, True, True, False, False, False),
    "flexxafeg300sh": Product("9901b1", "AFEG300-SH", "LPRN", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "973e61", "974961", "974b61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("973961", "9739e1", "973a61", "973861", "9744e1"), (), False, False, False, False, True, False),
    "flexx_linkrfrn": Product("98feb1", "FlexxLink", "RFRN", False, ("974261", "9741e1", "974161", "9740e1", "974061", "973fe1", "973e61", "974961"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("9738e1", "9739e1", "973861", "9744e1"), ("9738e1", "9739e1", "973861"), False, True, True, False, False, False),
    "flexxpb250": Product("990391", "PB250", "VJRM", False, ("974261", "9741e1", "974161", "9740e1", "973e61"), (), ("973861",), (), False, False, False, False, False, False),
    "flexxpb300": Product("990331", "PB300", "FARM", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "974961", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("973a61", "973961", "9739e1", "973861", "9737e1"), (), False, False, False, False, False, False),
    "flexxpb325": Product("9902d1", "PB325", "FARM", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "974961", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("973a61", "9738e1", "9739e1", "973861"), ("973a61", "9738e1", "9739e1", "973861"), False, True, True, True, False, False),
    "flexxpb450": Product("990271", "PB450", "MPRM", False, ("974261", "9741e1", "974161", "9740e1", "974c61", "974be1", "9749e1", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("9739e1", "9738e1", "973861"), ("9739e1", "9738e1", "973861"), True, True, False, True, False, False),
    "flexxpb450sh": Product("990151", "PB450-SH", "LVRN", False, ("974261", "9741e1", "974161", "9740e1", "974061", "973fe1", "973e61", "9749e1"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("9738e1", "9739e1", "973861"), (), True, False, False, True, True, False),
    "hj_bedbjrn": Product("990871", "BJRN", "BJRN", True, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "974061", "973fe1", "973f61", "973ee1", "974961", "974f61"), (), ("974e61", "974de1", "9751e1"), (), False, False, False, False, False, False),
    "hj_bedbyrn": Product("990811", "BYRN", "BYRN", True, ("9758e1", "975861"), (), (), (), False, False, False, False, False, False),
    "hj_bedd4rn": Product("9907b1", "D4RN", "D4RN", True, ("9757e1", "975761", "9755e1", "975561", "9756e1", "975661", "9754e1", "975461", "9753e1"), (), (), (), False, False, False, False, False, True),
    "hj_bedd5rn": Product("990751", "D5RN", "D5RN", True, ("9757e1", "975761", "9755e1", "975561", "9756e1", "975661", "9754e1", "975461", "9753e1", "975361"), (), (), (), False, False, False, False, False, True),
    "hj_bedd6rn": Product("9906f1", "D6RN", "D6RN", True, ("9755e1", "975561", "9754e1", "975461", "9753e1", "975361"), (), (), (), False, False, False, False, False, True),
    "hj_bedd7rn": Product("990691", "D7RN", "D7RN", True, ("9754e1", "975461", "9753e1", "975361"), (), (), (), False, False, False, False, False, True),
    "hj_bede3rm": Product("990631", "E3RM", "E3RM", True, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "975061", "974fe1", "974961", "974b61", "9752e1"), (), ("974e61", "974de1", "9751e1", "975261"), (), False, False, False, False, False, False),
    "hj_bedfarm": Product("990b71", "FARM", "FARM", True, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "974961", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("973a61", "973961", "9739e1", "973861", "9737e1"), (), False, False, False, False, False, False),
    "hj_bedhzrm": Product("990b11", "HZRM", "HZRM", True, ("974261", "9741e1", "974161", "9740e1", "974961", "974f61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("975161", "9750e1", "974e61", "974de1", "9751e1"), (), False, False, False, False, False, False),
    "hj_bedjgrm": Product("990ab1", "JGRM", "JGRM", True, ("974261", "9741e1", "974161", "9740e1", "974961", "974f61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("975161", "9750e1", "975961", "974e61", "974de1"), (), False, False, False, False, False, False),
    "hj_bedjhrm": Product("990a51", "JHRM", "JHRM", True, ("974261", "9741e1", "974161", "9740e1", "974f61"), (), ("975161", "9750e1", "975961"), (), False, False, False, False, False, False),
    "hj_bedjjrm": Product("9909f1", "JJRM", "JJRM", True, ("974261", "9741e1", "974f61"), (), ("975161",), (), False, False, False, False, False, False),
    "hj_bedkzrm": Product("990991", "KZRM", "KZRM", True, ("974261", "9741e1", "974161", "9740e1", "974961", "974f61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("975161", "9750e1", "974e61", "974de1", "9751e1"), (), False, False, False, False, False, False),
    "hj_bedl2rm": Product("990931", "L2RM", "L2RM", True, ("974261", "9741e1", "974161", "9740e1", "974461", "974f61"), (), ("975161", "9750e1"), (), False, False, False, False, False, False),
    "hj_bedrern": Product("990511", "RERN", "RERN", True, ("974261", "9741e1", "974161", "9740e1", "973f61", "973ee1", "974f61", "974961"), ("973de1", "973d61", "973ce1", "973be1", "973b61", "973ae1"), ("974e61", "975161", "9750e1"), (), False, False, False, False, False, False),
    "hj_bedtyrn": Product("9905d1", "TYRN", "TYRN", True, ("974261", "9741e1", "974161", "9740e1", "974f61"), (), ("975161", "9750e1"), (), False, False, False, False, False, False),
    "hj_bedtzrn": Product("990571", "TZRN", "TZRN", True, ("974261", "9741e1", "974161", "9740e1", "974961", "974f61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("975161", "9750e1", "974e61", "974de1", "9751e1"), (), False, False, False, False, False, False),
    "hj_beduurn": Product("9904b1", "UURN", "UURN", True, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "975061", "974fe1", "974f61", "974961"), (), ("974e61", "974de1", "974d61", "974ce1"), (), False, False, False, False, False, False),
    "hj_bedvjrm": Product("9908d1", "VJRM", "VJRM", True, ("974261", "9741e1", "974161", "9740e1", "973e61"), (), ("973861",), (), False, False, False, False, False, False),
    "likomioabm10": Product("990bd1", "ABM10", "UTRM", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "974961", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("9739e1", "9738e1", "973861", "9737e1"), (), False, False, False, True, False, False),
    "motionnxca200": Product("98ffd1", "Series 1", "GURN", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "973e61"), (), ("9739e1", "9738e1", "973a61", "973961", "973861"), (), False, False, False, False, False, False),
    "motionnxca300": Product("98ff71", "Series 2", "GVRN", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "973e61", "974961"), ("973de1", "973d61", "973c61", "973ce1", "973be1", "973b61", "973ae1"), ("9739e1", "9738e1", "973861", "9737e1"), (), False, False, False, False, False, False),
    "motion_opus": Product("98ff11", "Series 3", "GWRN", False, ("974261", "9741e1", "974161", "9740e1", "974061", "973fe1", "973f61", "973ee1", "973e61"), ("973de1", "973d61", "973c61", "973ce1", "973be1", "973b61", "973ae1"), ("9739e1", "9738e1", "973861"), ("9739e1", "9738e1", "973861"), True, True, True, True, False, False),
    "muuegmabf03": Product("990091", "ABF03", "BNRN", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "974961", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("9739e1", "9738e1", "973a61", "973961", "973861"), ("9739e1", "9738e1", "973a61", "973961", "973861"), False, True, False, True, False, False),
    "muuegmabf07": Product("990031", "ABF07", "DNRN", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("9739e1", "9738e1", "973a61", "973961", "973861"), ("9739e1", "9738e1", "973a61", "973961", "973861"), False, True, True, True, False, False),
    "muuegmnupg400": Product("9900f1", "NUPG400", "BVRN", False, ("974261", "9741e1", "974161", "9740e1", "974ae1", "974a61", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("9739e1", "9738e1", "973a61", "973861", "9737e1"), (), False, False, False, False, False, False),
    "velocityvip3": Product("990451", "VIP 3.0", "", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "974961", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("973a61", "973961", "9739e1", "973861", "9737e1"), ("973a61", "973961", "9739e1", "973861", "9737e1"), False, True, True, True, False, False),
    "velocityvip3sh": Product("9903f1", "VIP 3.0-SH", "", False, ("974261", "9741e1", "974161", "9740e1", "974461", "9743e1", "974961", "973e61"), ("973de1", "973d61", "973ce1", "973c61", "973be1", "973b61", "973ae1"), ("973a61", "973961", "9739e1", "973861", "9737e1"), ("973a61", "973961", "9739e1", "973861", "9737e1"), False, True, True, True, True, False),
}
# fmt: on

PROFILE_CHOICES = {
    key: f"{p.label} ({p.remote})" if p.remote and p.remote != p.label else p.label
    for key, p in PRODUCTS.items()
}
MUSIC_ACTIONS = tuple(a for a in ACTIONS.values() if a.kind == "music")
