"""Tests for Leggett & Platt Gen2 (LP Comfort Connect) capability profiles."""

from __future__ import annotations

from custom_components.adjustable_bed.beds.leggett_gen2_profiles import (
    GEN2_FALLBACK,
    GEN2_PROFILES,
    capabilities_for_product,
    compute_product_id,
)


class TestComputeProductId:
    """Reproduce the app's productId(ScanResult) algorithm."""

    def test_real_device_payload(self):
        # Reporter's bed: company 0x092D payload "XP" + 05 00 00 00 -> productId 5.
        assert compute_product_id({0x092D: bytes.fromhex("585005000000")}) == 5

    def test_cp_prefix_accepted(self):
        # "CP" (0x43 0x50) + 07 00 00 00 -> reversed first 4 -> 0x00000007 -> 7.
        assert compute_product_id({0x092D: bytes.fromhex("435007000000")}) == 7

    def test_non_gen2_prefix_returns_none(self):
        assert compute_product_id({0x092D: b"ZZ\x00\x00"}) is None

    def test_empty_returns_none(self):
        assert compute_product_id({}) is None
        assert compute_product_id(None) is None

    def test_picks_the_gen2_entry_among_several(self):
        data = {0x004C: b"\x10\x20", 0x092D: bytes.fromhex("585005000000")}
        assert compute_product_id(data) == 5


class TestCapabilityLookup:
    """Capability gating differs per product (the whole point of the table)."""

    def test_rgb_bed_with_pillow_and_lumbar(self):
        caps = capabilities_for_product(5)
        assert caps.light == "rgb"
        assert caps.has_pillow and caps.has_lumbar
        assert caps.has_massage and caps.memory_slots == 3

    def test_toggle_light_bed_without_pillow_lumbar(self):
        caps = capabilities_for_product(8)
        assert caps.light == "toggle"
        assert not caps.has_pillow and not caps.has_lumbar

    def test_bed_with_no_light(self):
        assert capabilities_for_product(10011).light == "none"

    def test_chair_profile(self):
        caps = capabilities_for_product(10030)
        assert caps.is_chair
        assert caps.light == "none" and not caps.has_massage and caps.memory_slots == 0

    def test_unknown_product_uses_generous_fallback(self):
        # Unknown ids keep a full entity set (the app's default ID_7 profile).
        caps = capabilities_for_product(999999)
        assert caps is GEN2_FALLBACK
        assert caps.light == "rgb" and caps.has_pillow and caps.has_lumbar

    def test_none_product_uses_fallback(self):
        assert capabilities_for_product(None) is GEN2_FALLBACK


def test_profile_table_is_well_formed():
    """Every profile has a valid light style and non-negative memory count."""
    for product_id, caps in GEN2_PROFILES.items():
        assert isinstance(product_id, int)
        assert caps.light in ("none", "toggle", "single", "rgb")
        assert caps.memory_slots >= 0
        # Chairs carry no under-bed light, massage, or memory in the profiles.
        if caps.is_chair:
            assert caps.light == "none" and not caps.has_massage and caps.memory_slots == 0
