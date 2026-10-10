import unittest
from src import pob_engine

BUILDOPS_FIXTURE = """
local M = {}
function M.export_stats(fields)
  local output, err = M.get_main_output()
  if not output then
    return nil, err
  end
  local wanted = fields or {
    "Life", "TotalDPS"
  }
  local result = {}
  for _, k in ipairs(wanted) do
    if type(output[k]) ~= 'nil' then
      result[k] = output[k]
    end
  end
  result._meta = result._meta or {}
  return result
end
-- Read current tree allocation and metadata
function M.get_skills()
  local result = { groups = {} }
  return result
end
function M.set_main_selection(params)
  local g = build.skillsTab.socketGroupList[build.mainSocketGroup]
  if params.mainActiveSkill ~= nil then
    g.mainActiveSkill = tonumber(params.mainActiveSkill) or g.mainActiveSkill
  end
  build.calcsTab.input.skill_number = build.mainSocketGroup
  M.get_main_output()
  return true
end
"""

HANDLERS_FIXTURE = """
handlers.get_stats = function(params)
  local fields = params and params.fields or nil
  local stats, err = BuildOps.export_stats(fields)
  if not stats then
    return { ok = false, error = err }
  end
  return { ok = true, stats = stats }
end
"""

class CalcsOutputTests(unittest.TestCase):
    def test_buildops_patch_adds_scope_and_calcs(self):
        out = pob_engine._patch_buildops_calcs_output(BUILDOPS_FIXTURE)
        self.assertIn("SYNERGY_FINDER_CALCS_OUTPUT_V0123", out)
        self.assertIn("build.calcsTab.calcsOutput", out)
        self.assertIn("options.allScalars", out)
        self.assertIn("g.mainActiveSkillCalcs", out)

    def test_handlers_patch_passes_scope(self):
        out = pob_engine._patch_handlers_calcs_output(HANDLERS_FIXTURE)
        self.assertIn("SYNERGY_FINDER_CALCS_HANDLER_V0123", out)
        self.assertIn("scope = params and params.scope", out)
        self.assertIn("allScalars", out)

    def test_skill_changes_win_over_main_duplicates(self):
        rows = pob_engine._comparison_rows(
            {"ManaRegen":100, "AreaOfEffectMod":1.0},
            {"ManaRegen":104, "AreaOfEffectMod":1.45},
            {"AreaOfEffectMod":1.0, "AreaOfEffectRadiusMetres":2.0},
            {"AreaOfEffectMod":1.45, "AreaOfEffectRadiusMetres":2.4},
        )
        changed = [r for r in rows if r["changed"]]
        by_key = {r["key"]: r for r in changed}
        self.assertEqual(by_key["AreaOfEffectMod"]["scope"], "skill")
        self.assertEqual(by_key["AreaOfEffectRadiusMetres"]["scope"], "skill")
        self.assertEqual(by_key["ManaRegen"]["scope"], "character")
        self.assertEqual(sum(1 for r in changed if r["key"]=="AreaOfEffectMod"), 1)

    def test_unknown_scalar_skill_metric_is_not_lost(self):
        rows = pob_engine._comparison_rows(
            {}, {},
            {"SomeFuturePoBMetric":10},
            {"SomeFuturePoBMetric":12},
        )
        row = next(r for r in rows if r["key"]=="SomeFuturePoBMetric")
        self.assertTrue(row["changed"])
        self.assertEqual(row["scope"], "skill")
        self.assertAlmostEqual(row["pct"],20.0)

if __name__ == "__main__":
    unittest.main()
