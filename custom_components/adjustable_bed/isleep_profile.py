"""ISleep 1.6.3 product selection, validated against accepted row064 evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .const import CONF_KAIDI_ROOM_ID, CONF_KAIDI_SOFA_ACU_NO, CONF_PRODUCT_TYPE
from .kaidi_protocol import KaidiAdvertisement, parse_kaidi_manufacturer_payload

ISLEEP_PRODUCTS = (129, 130, 131, 132, 133, 134, 142, 143)
ISLEEP_CONFIG_KEYS = frozenset({CONF_PRODUCT_TYPE, CONF_KAIDI_ROOM_ID, CONF_KAIDI_SOFA_ACU_NO})


@dataclass(frozen=True)
class IsleepProfile:
    """Only rendered controls, rather than the numeric product's implied motors."""

    product: int
    room: int
    actuators: int

    @property
    def split(self) -> bool:
        """Only role1 uses one-address left/both/right opcodes."""
        return self.product in (130, 143) and self.actuators != 2

    @property
    def axes(self) -> tuple[str, ...]:
        if self.product in (132, 134):
            return ("back", "legs", "head", "lumbar")
        if self.product in (131, 133):
            return ("back", "legs", "head")
        return ("back", "legs")


def validate_isleep_profile(data: Mapping[str, object]) -> IsleepProfile:
    """Reject unknown products and invalid explicit session identities before writing."""
    product = data.get(CONF_PRODUCT_TYPE)
    room = data.get(CONF_KAIDI_ROOM_ID)
    actuators = data.get(CONF_KAIDI_SOFA_ACU_NO, 2)
    if type(product) is not int or product not in ISLEEP_PRODUCTS:
        raise ValueError("Select one of the eight ISleep products")
    if type(room) is not int or not -(2**31) <= room < 2**31:
        raise ValueError("ISleep requires the selected signed 32-bit room ID")
    if type(actuators) is not int or not 0 <= actuators <= 65535:
        raise ValueError("Invalid ISleep actuator descriptor")
    return IsleepProfile(product, room, actuators)


def isleep_advertisement(manufacturer_data: Mapping[int, bytes]) -> KaidiAdvertisement | None:
    """Apply the live inventory's company/product/actuator gates, with safe bounds."""
    for company, payload in manufacturer_data.items():
        if company != 0xFFFF:
            continue
        ad = parse_kaidi_manufacturer_payload(payload)
        if ad is None or ad.adv_type not in (1, 2, 9) or ad.product_id not in ISLEEP_PRODUCTS:
            continue
        if ad.adv_type == 9 and ad.company_id != 0x4B44:
            continue
        acu = ad.sofa_acu_no
        if acu is None or (acu >> 8 & 7) > 5 or (acu & 15) > 5 or (acu & 240) > 5:
            continue
        return ad
    return None


def add_isleep_metadata(data: Mapping[str, object], manufacturer_data: Mapping[int, bytes]) -> dict:
    """Seed the explicit app form; never replace an already selected room."""
    result = dict(data)
    ad = isleep_advertisement(manufacturer_data)
    if ad is not None:
        result.setdefault(CONF_PRODUCT_TYPE, ad.product_id)
        result.setdefault(CONF_KAIDI_SOFA_ACU_NO, ad.sofa_acu_no)
        if ad.room_id is not None:
            room = ad.room_id if ad.room_id < 2**31 else ad.room_id - 2**32
            result.setdefault(CONF_KAIDI_ROOM_ID, room)
    return result
