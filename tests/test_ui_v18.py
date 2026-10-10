from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

class UiV18Tests(unittest.TestCase):
    def test_codex_button_and_dialog(self):
        html=(ROOT/"web"/"index.html").read_text(encoding="utf-8")
        js=(ROOT/"web"/"app.js").read_text(encoding="utf-8")
        self.assertIn('id="openCodex"',html)
        self.assertIn('id="codexDialog"',html)
        self.assertIn("INSTALAR_CODEX_MCP.bat",html)
        self.assertIn("openCodex",js)

    def test_codex_files(self):
        for name in ["mcp_server.py","INSTALAR_CODEX_MCP.bat","TESTAR_CODEX_MCP.bat","CODEX_MCP.md","AGENTS.md"]:
            self.assertTrue((ROOT/name).is_file(),name)

    def test_version(self):
        html=(ROOT/"web"/"index.html").read_text(encoding="utf-8")
        self.assertIn(">0.19.3</span>",html)

if __name__=="__main__":
    unittest.main()
