"""Saatva 1.1.0's live command literals, tested through the shipped codec/controller."""

VECTORS = (
    ("head_up", "$", "6e01002493"),
    ("head_down", "%", "6e01002594"),
    ("right_head_up", "_$", "6e01012494"),
    ("right_head_down", "_%", "6e01012595"),
    ("foot_up", "&", "6e01002695"),
    ("foot_down", "'", "6e01002796"),
    ("flat", "1", "6e010031a0"),
    ("zero_g", "E", "6e010045b4"),
    ("anti_snore", "F", "6e010046b5"),
    ("tv", "X", "6e010058c7"),
    ("memory1_save", "+", "6e01002b9a"),
    ("memory2_save", ",", "6e01002c9b"),
    ("memory1_recall", ".", "6e01002e9d"),
    ("memory2_recall", "/", "6e01002f9e"),
    ("head_massage_up", "L", "6e01004cbb"),
    ("head_massage_down", "M", "6e01004dbc"),
    ("right_head_massage_up", "_L", "6e01014cbc"),
    ("right_head_massage_down", "_M", "6e01014dbd"),
    ("foot_massage_up", "N", "6e01004ebd"),
    ("foot_massage_down", "O", "6e01004fbe"),
    ("massage_toggle", "]", "6e01005dcc"),
    ("massage_mode", "H", "6e010048b7"),
    ("massage_timer10", "_", "6e01005fce"),
    ("massage_timer20", "c", "6e010063d2"),
    ("light_toggle", "<", "6e01003cab"),
)

BASE_ACTIONS = frozenset(
    {
        "head_up",
        "head_down",
        "foot_up",
        "foot_down",
        "flat",
        "zero_g",
        "anti_snore",
        "memory1_recall",
        "memory1_save",
        "memory2_recall",
        "memory2_save",
    }
)
PRODUCTS = (
    "bt2000_standard",
    "bt2000_split",
    "bt3000_standard",
    "bt3000_split",
    "bt3000fh_split_top",
)
CASES = tuple(
    (product, action, token, literal)
    for product in PRODUCTS
    for action, token, literal in VECTORS
    if (not product.startswith("bt2000") or action in BASE_ACTIONS)
    and (not action.startswith("right_") or product.endswith("split_top"))
)
FROZEN_FRAMES = {
    f"saatva_{product}": frozenset(literal for key, _, _, literal in CASES if key == product)
    for product in PRODUCTS
}
