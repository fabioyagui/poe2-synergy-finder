from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]

class UiHotfixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    def test_current_pob_functions_exist(self):
        for name in (
            "renderCurrentBuild",
            "refreshCurrentPob",
            "openCurrentBuild",
            "openPobSkillInFinder",
        ):
            self.assertRegex(
                self.js,
                rf"(?:async\s+)?function\s+{name}\s*\(",
                msg=f"{name} must exist"
            )

    def test_refresh_status_can_call_defined_function(self):
        self.assertIn("await refreshCurrentPob()", self.js)
        self.assertIn("async function refreshCurrentPob()", self.js)

    def test_import_modal_no_longer_calls_old_http_engine(self):
        match = re.search(
            r"async function openPob\(\)\{(.*?)\n\}",
            self.js,
            re.S,
        )
        self.assertIsNotNone(match)
        self.assertNotIn("testPobEngine", match.group(1))
        self.assertNotIn("pobEngineUrl", self.js)
        self.assertNotIn("loadPobEngine", self.js)

    def test_build_tabs_have_renderer(self):
        self.assertIn("else renderBuildEngine(d);", self.js)

if __name__ == "__main__":
    unittest.main()
