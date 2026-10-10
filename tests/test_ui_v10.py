from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class UiV10Tests(unittest.TestCase):
    def test_full_build_workspace_exists(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="buildWorkspace"', html)
        self.assertIn('id="openCurrentBuild"', html)
        self.assertIn('data-build-tab="skills"', html)
        self.assertIn('data-build-tab="gear"', html)

    def test_build_can_open_skill_in_finder(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("openPobSkillInFinder", js)
        self.assertIn("data-open-skill-from-pob", js)
        self.assertIn("refreshCurrentPob", js)

if __name__ == "__main__":
    unittest.main()
