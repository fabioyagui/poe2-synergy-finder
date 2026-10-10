from src import VERSION
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class UiV125Tests(unittest.TestCase):
    def test_area_sources(self):
        js=(ROOT/"web"/"app.js").read_text(encoding="utf-8")
        self.assertIn("Fontes dos modifiers de Area of Effect",js)
        self.assertIn("Área secundária INC",js)
        self.assertIn("Área terciária INC",js)

    def test_version(self):
        html=(ROOT/"web"/"index.html").read_text(encoding="utf-8")
        self.assertIn(f">{VERSION}</span>", html)

if __name__=="__main__":
    unittest.main()
