"""Constants for the Smart Bed integration."""

from typing import Final

DOMAIN: Final = "smartbed"

# Configuration keys
CONF_BED_TYPE: Final = "bed_type"
CONF_MOTOR_COUNT: Final = "motor_count"
CONF_HAS_MASSAGE: Final = "has_massage"
CONF_DISABLE_ANGLE_SENSING: Final = "disable_angle_sensing"
CONF_PREFERRED_ADAPTER: Final = "preferred_adapter"

# Special value for auto adapter selection
ADAPTER_AUTO: Final = "auto"

# Bed types
BED_TYPE_LINAK: Final = "linak"
BED_TYPE_RICHMAT: Final = "richmat"
BED_TYPE_SOLACE: Final = "solace"
BED_TYPE_MOTOSLEEP: Final = "motosleep"
BED_TYPE_REVERIE: Final = "reverie"
BED_TYPE_LEGGETT_PLATT: Final = "leggett_platt"
BED_TYPE_OKIMAT: Final = "okimat"
BED_TYPE_KEESON: Final = "keeson"
BED_TYPE_OCTO: Final = "octo"

SUPPORTED_BED_TYPES: Final = [
    BED_TYPE_LINAK,
    # BED_TYPE_RICHMAT,  # TODO: implement
    # BED_TYPE_SOLACE,  # TODO: implement
    # BED_TYPE_MOTOSLEEP,  # TODO: implement
    # BED_TYPE_REVERIE,  # TODO: implement
    # BED_TYPE_LEGGETT_PLATT,  # TODO: implement
    # BED_TYPE_OKIMAT,  # TODO: implement
    # BED_TYPE_KEESON,  # TODO: implement
    # BED_TYPE_OCTO,  # TODO: implement
]

# Linak specific UUIDs
LINAK_CONTROL_SERVICE_UUID: Final = "99fa0001-338a-1024-8a49-009c0215f78a"
LINAK_CONTROL_CHAR_UUID: Final = "99fa0002-338a-1024-8a49-009c0215f78a"

LINAK_POSITION_SERVICE_UUID: Final = "99fa0020-338a-1024-8a49-009c0215f78a"
LINAK_POSITION_BACK_UUID: Final = "99fa0028-338a-1024-8a49-009c0215f78a"
LINAK_POSITION_LEG_UUID: Final = "99fa0027-338a-1024-8a49-009c0215f78a"
LINAK_POSITION_HEAD_UUID: Final = "99fa0026-338a-1024-8a49-009c0215f78a"
LINAK_POSITION_FEET_UUID: Final = "99fa0025-338a-1024-8a49-009c0215f78a"

# Linak position calibration
LINAK_BACK_MAX_POSITION: Final = 820
LINAK_BACK_MAX_ANGLE: Final = 68
LINAK_LEG_MAX_POSITION: Final = 548
LINAK_LEG_MAX_ANGLE: Final = 45
LINAK_HEAD_MAX_POSITION: Final = 820
LINAK_HEAD_MAX_ANGLE: Final = 68
LINAK_FEET_MAX_POSITION: Final = 548
LINAK_FEET_MAX_ANGLE: Final = 45

# Default values
DEFAULT_MOTOR_COUNT: Final = 2
DEFAULT_HAS_MASSAGE: Final = False
DEFAULT_DISABLE_ANGLE_SENSING: Final = True

