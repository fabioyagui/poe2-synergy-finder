from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class UiV113Tests(unittest.TestCase):
    def test_download_checkout_ui_and_route(self):
        js=(ROOT/"web"/"app.js").read_text(encoding="utf-8")
        app=(ROOT/"app.py").read_text(encoding="utf-8")
        self.assertIn("Baixar PoB2 headless",js)
        self.assertIn("engineInstallPob",js)
        self.assertIn("/api/pob/engine/install-pob",app)

if __name__=="__main__":
    unittest.main()
