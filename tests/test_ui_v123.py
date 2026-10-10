from src import VERSION
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

class UiV123Tests(unittest.TestCase):
    def test_scope_labels_are_visible(self):
        js=(ROOT/"web"/"app.js").read_text(encoding="utf-8")
        self.assertIn("SKILL · CALCS",js)
        self.assertIn("PERSONAGEM · MAIN",js)
        self.assertTrue("Diagnóstico dos outputs do PoB" in js or "Diagnóstico do cálculo nativo do PoB" in js)

    def test_version_visible(self):
        html=(ROOT/"web"/"index.html").read_text(encoding="utf-8")
        self.assertIn(f">{VERSION}</span>", html)

if __name__=="__main__":
    unittest.main()
