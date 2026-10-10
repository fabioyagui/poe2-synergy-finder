from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class UiV11Tests(unittest.TestCase):
    def test_stdio_setup_ui(self):
        js=(ROOT/"web"/"app.js").read_text(encoding="utf-8")
        self.assertIn("Motor real do Path of Building",js)
        self.assertIn("engineDetect",js)
        self.assertIn("engineInstallBridge",js)
        self.assertIn("/api/pob/engine/start",js)
        self.assertIn("/api/pob/engine/load",js)
        self.assertNotIn("buildTestEngine",js)

    def test_backend_routes(self):
        app=(ROOT/"app.py").read_text(encoding="utf-8")
        self.assertIn("/api/pob/engine/setup",app)
        self.assertIn("/api/pob/engine/install-bridge",app)
        self.assertIn("/api/pob/engine/start",app)
        self.assertIn("/api/pob/engine/stop",app)

if __name__=="__main__":
    unittest.main()
