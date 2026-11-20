"""Literal Instant Comfort 2.6.1 frames, independently frozen for this app."""

MALOUF = {
    "pillow_up": "6e01003fae",
    "pillow_down": "6e010040af",
    "head_up": "6e01002493",
    "head_down": "6e01002594",
    "feet_up": "6e01002695",
    "feet_down": "6e01002796",
    "zero_g": "6e010045b4",
    "flat": "6e010031a0",
    "anti_snore": "6e010046b5",
    "memory_1": "6e01002e9d",
    "save_1": "6e01002b9a",
    "memory_2": "6e01002f9e",
    "save_2": "6e01002c9b",
    "light_toggle": "6e01003cab",
    "massage_head": "6e01004cbb",
    "massage_head_down": "6e01004dbc",
    "massage_mode": "6e010048b7",
    "massage_foot": "6e01004ebd",
    "massage_foot_down": "6e01004fbe",
    "massage_off": "6e010047b6",
}
REVERIE = {
    "head_up": "550154",
    "head_down": "550356",
    "feet_up": "550257",
    "feet_down": "550451",
    "flat": "550550",
    "zero_g": "551540",
    "anti_snore": "551643",
    "massage_head": "553164",
    "massage_foot": "553267",
    "massage_off": "553560",
    "light_toggle": "555b",
    "stop": "55ffaa",
}
ANM3 = (
    ((0x83, 0, 0, 3), "5504830000000003dfaa"),
    ((0x85, 0, 0, 0), "5504850000000000deaa"),
    ((0x69, 5, 5, 3), "5504690505000003cfaa"),
    ((1, 5, 5, 3), "550401050500000367aa"),
    ((2, 0, 5, 2), "550402000500000262aa"),
)
WAVES = ("5541ccd8", "5542ccdb", "5543ccda", "5544ccdd", "5545ccdc")
V2 = {
    "pillow_up": ("db801020", "01"),
    "pillow_down": ("db801020", "02"),
    "head_up": ("db801021", "01"),
    "head_down": ("db801021", "02"),
    "feet_up": ("db801022", "01"),
    "feet_down": ("db801022", "02"),
    "zero_g": ("db8010d0", "01"),
    "anti_snore": ("db8010d0", "02"),
    "flat": ("db8010d0", "03"),
    "memory_1": ("db8010d0", "04"),
    "memory_2": ("db8010d0", "05"),
    "save_1": ("db8010d0", "84"),
    "save_2": ("db8010d0", "85"),
    "massage_head": ("db801061", "32"),
    "massage_foot": ("db801060", "32"),
    "massage_off": ("db801080", "00"),
}
FROZEN_FRAMES = {
    "anm3": frozenset(frame for _args, frame in ANM3),
    "anm5": frozenset(
        {
            "433e534554503e303e300a",
            "433e534554503e333e36360a",
            "433e53544f504e0a",
            "433e545043483e300a",
            "523e53500a",
            "433e534554503e303e36360a",
            "433e534554503e313e300a",
            "433e534554503e313e36360a",
            "433e534554503e323e300a",
            "433e534554503e323e36360a",
            "433e534554503e333e300a",
        }
    ),
    "ra": frozenset({"0a0f0f", "640f0f"}),
    "malouf": frozenset(MALOUF.values()),
    "reverie_v1": frozenset((*REVERIE.values(), *WAVES)),
    "reverie_v2": frozenset(
        {*(frame for _prefix, frame in V2.values()), "00", "64", "01", "02", "03", "04", "05"}
    ),
}
