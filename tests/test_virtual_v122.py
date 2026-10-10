from pathlib import Path
import tempfile
import unittest
from src import pob_engine

UPSTREAM_SHAPE = """
function M.get_skills()
  local groups = {}
  local result = {
    mainSocketGroup = build.mainSocketGroup,
    groups = groups,
  }
  return result
end
function M.set_main_selection(params)
  return true
end
"""

class ExactCompatibilityTests(unittest.TestCase):
    def test_patch_adds_engine_truth_fields(self):
        out = pob_engine._patch_buildops_exact_support_compat(UPSTREAM_SHAPE)
        self.assertIn("SYNERGY_FINDER_EXACT_SUPPORT_COMPAT", out)
        self.assertIn("canGrantedEffectSupportActiveSkill", out)
        self.assertIn("compatibleSupports", out)
        self.assertIn("appliedSupports", out)

    def test_patch_is_idempotent(self):
        once = pob_engine._patch_buildops_exact_support_compat(UPSTREAM_SHAPE)
        twice = pob_engine._patch_buildops_exact_support_compat(once)
        self.assertEqual(once, twice)
        self.assertEqual(
            twice.count("SYNERGY_FINDER_EXACT_SUPPORT_COMPAT"),
            1,
        )

    def test_compare_has_rejection_guard(self):
        src = Path(pob_engine.__file__).read_text(encoding="utf-8")
        self.assertRegex(src, r'"rejected_supports"\s*:\s*rejected_names')
        self.assertRegex(src, r'"variant_valid"\s*:\s*len\(rejected_names\)\s*==\s*0')

if __name__ == "__main__":
    unittest.main()
