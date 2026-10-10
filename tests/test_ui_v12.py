from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class UiV12Tests(unittest.TestCase):
    def test_virtual_tab(self):
        html=(ROOT/"web"/"index.html").read_text(encoding="utf-8")
        self.assertIn('data-build-tab="virtual"',html)
    def test_routes(self):
        app=(ROOT/"app.py").read_text(encoding="utf-8")
        js=(ROOT/"web"/"app.js").read_text(encoding="utf-8")
        self.assertIn("/api/pob/engine/virtual",app)
        self.assertIn("/api/pob/engine/compare-supports",app)
        self.assertIn("renderVirtualLinker",js)
        self.assertIn("até 5 supports",js)
if __name__=="__main__":unittest.main()
