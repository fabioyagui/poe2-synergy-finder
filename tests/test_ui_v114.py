from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class UiV114Tests(unittest.TestCase):
    def test_syntax_preflight_visible(self):
        js=(ROOT/"web"/"app.js").read_text(encoding="utf-8")
        self.assertIn("Compatibilidade LuaJIT",js)
        self.assertIn("pob_syntax",js)
        self.assertIn("Baixar PoB2 headless estável",js)

if __name__=="__main__":
    unittest.main()
