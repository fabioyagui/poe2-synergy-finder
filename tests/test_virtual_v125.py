import unittest
from src import pob_engine

BUILDOPS_FIXTURE = """
local M = {}
function M.calc_with(params)
  return {}, {}
end

-- Get basic config values.
function M.get_config()
  return {}
end
"""

class SlotFaithfulTests(unittest.TestCase):
    def test_exact_gui_fields(self):
        out = pob_engine._patch_buildops_native_support_whatif(BUILDOPS_FIXTURE)
        self.assertIn("SYNERGY_FINDER_NATIVE_GEM_WHATIF_V0125", out)
        self.assertIn("gemInstance.level = build.skillsTab:ProcessGemLevel(gd)", out)
        self.assertIn("gemInstance.gemData = gd", out)
        self.assertIn("gemInstance.displayEffect = nil", out)
        self.assertIn("slot-faithful GemSelect preview", out)

    def test_secondary_and_tertiary_area_probes(self):
        out = pob_engine._patch_buildops_native_support_whatif(BUILDOPS_FIXTURE)
        self.assertIn("areaSecondaryInc", out)
        self.assertIn("areaTertiaryInc", out)
        self.assertIn("areaMods", out)

    def test_versioned_overlay(self):
        self.assertRegex(str(pob_engine.BRIDGE_OVERLAY_DIR), r"pob-api-v012[56]")

if __name__ == "__main__":
    unittest.main()
