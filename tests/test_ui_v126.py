from src import VERSION
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class UiV126Tests(unittest.TestCase):
    def test_pipeline_ui(self):
        js=(ROOT/"web"/"app.js").read_text(encoding="utf-8")
        self.assertIn("Pipeline interno dos supports",js)
        self.assertIn("RAW",js)
        self.assertIn("BUILT",js)
        self.assertIn("MERGED",js)
        self.assertIn("buildSkillInstanceStats",js)
        self.assertIn("mergeSkillInstanceMods",js)

    def test_version(self):
        html=(ROOT/"web"/"index.html").read_text(encoding="utf-8")
        self.assertIn(f">{VERSION}</span>", html)

if __name__=="__main__":
    unittest.main()
