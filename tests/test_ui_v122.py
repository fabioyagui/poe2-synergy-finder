from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class UiV122Tests(unittest.TestCase):
    def test_compatible_route(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        bridge = (ROOT / "src" / "pob_bridge.py").read_text(encoding="utf-8")
        self.assertIn("/api/pob/engine/compatible-supports", app)
        self.assertIn("stdio_compatible_supports", bridge)

    def test_ui_explains_exact_filter(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Lista filtrada pelo motor real do PoB", js)
        self.assertIn("PoB rejeitou", js)
        self.assertIn("refreshCompatibleSupports", js)

if __name__ == "__main__":
    unittest.main()
