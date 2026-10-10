from src import VERSION
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class UiV124Tests(unittest.TestCase):
    def test_native_calculator_labels(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("POB · CALCULATOR", js)
        self.assertIn("Diagnóstico do cálculo nativo do PoB", js)
        self.assertIn("Área primária INC", js)
        self.assertIn("Supports aplicados pelo effectList", js)

    def test_version(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn(f">{VERSION}</span>", html)

if __name__ == "__main__":
    unittest.main()
