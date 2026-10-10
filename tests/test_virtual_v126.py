import unittest
from pathlib import Path
from src import pob_engine

class SupportPipelineTests(unittest.TestCase):
    def test_lua_pipeline_instrumentation_exists(self):
        src=Path(pob_engine.__file__).read_text(encoding="utf-8")
        self.assertIn("sf_support_pipeline",src)
        self.assertIn("calcLib.buildSkillInstanceStats",src)
        self.assertIn("calcs.mergeSkillInstanceMods",src)
        self.assertIn("constantStats",src)
        self.assertIn("statMapKeys",src)
        self.assertIn("mergedMods",src)

    def test_snapshot_passes_calcs(self):
        src=Path(pob_engine.__file__).read_text(encoding="utf-8")
        self.assertIn("sf_skill_snapshot(baseEnv, calcs)",src)
        self.assertIn("sf_skill_snapshot(variantEnv, calcs)",src)

    def test_versioned_overlay(self):
        self.assertIn("pob-api-v0126",str(pob_engine.BRIDGE_OVERLAY_DIR))

if __name__=="__main__":
    unittest.main()
