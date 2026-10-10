import unittest
from pathlib import Path
from src import pob_engine

BUILDOPS_FIXTURE = """
local M = {}
function M.calc_with(params)
  local calcFunc, baseOut = build.calcsTab:GetMiscCalculator()
  local out = calcFunc({}, false)
  return out, baseOut
end

-- Get basic config values.
function M.get_config()
  return {}
end
"""

HANDLERS_FIXTURE = """
handlers.calc_with = function(params)
  local out, base = BuildOps.calc_with(params or {})
  if not out then return { ok = false, error = base } end
  return { ok = true, output = out }
end

handlers.get_config = function(params)
  return { ok = true, config = {} }
end
"""

class NativeWhatIfTests(unittest.TestCase):
    def test_buildops_patch_uses_native_misc_calculator(self):
        out = pob_engine._patch_buildops_native_support_whatif(BUILDOPS_FIXTURE)
        self.assertIn("SYNERGY_FINDER_NATIVE_GEM_WHATIF_V0125", out)
        self.assertIn("GetMiscCalculator", out)
        self.assertIn("calcFunc(nil, false, nil)", out)
        self.assertIn("CALCULATOR", out)
        self.assertIn("effectList", out)
        self.assertIn("AreaOfEffect", out)

    def test_buildops_patch_is_idempotent(self):
        once = pob_engine._patch_buildops_native_support_whatif(BUILDOPS_FIXTURE)
        twice = pob_engine._patch_buildops_native_support_whatif(once)
        self.assertEqual(once, twice)
        self.assertEqual(
            twice.count("SYNERGY_FINDER_NATIVE_GEM_WHATIF_V0125"),
            1,
        )

    def test_handler_patch(self):
        out = pob_engine._patch_handlers_native_support_whatif(HANDLERS_FIXTURE)
        self.assertIn("compare_support_setup_native", out)
        self.assertIn("SYNERGY_FINDER_NATIVE_GEM_HANDLER_V0125", out)

    def test_python_comparison_uses_native_action(self):
        src = Path(pob_engine.__file__).read_text(encoding="utf-8")
        start = src.index("    def compare_support_setup(")
        end = src.index("\n    def stop(", start)
        block = src[start:end]
        self.assertIn('"compare_support_setup_native"', block)
        self.assertNotIn('self.request("remove_gem"', block)
        self.assertNotIn('self.request("add_gem"', block)
        self.assertIn('"baseline_skill_probe"', block)
        self.assertIn('"variant_skill_probe"', block)

    def test_native_metric_rows_detect_unknown_metric(self):
        rows = pob_engine._native_metric_rows(
            {"FutureMetric": 10},
            {"FutureMetric": 15},
        )
        row = next(r for r in rows if r["key"] == "FutureMetric")
        self.assertTrue(row["changed"])
        self.assertEqual(row["scope"], "native")
        self.assertAlmostEqual(row["pct"], 50.0)

if __name__ == "__main__":
    unittest.main()
