import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class McpPortabilityV193Tests(unittest.TestCase):
    def test_installer_uses_stable_localappdata_copy(self):
        text=(ROOT/'INSTALAR_CODEX_MCP.bat').read_text(encoding='utf-8')
        self.assertIn('%LOCALAPPDATA%\\PoE2 Synergy Finder\\mcp', text)
        self.assertIn('copy /y "%~dp0mcp_server.py"', text)
        self.assertIn('codex mcp add synergy-build-engine', text)
        self.assertNotIn('codex mcp add synergy-build --', text)
        self.assertNotIn('codex mcp add synergy-calcs --', text)

    def test_installer_removes_legacy_absolute_path_entries(self):
        text=(ROOT/'INSTALAR_CODEX_MCP.bat').read_text(encoding='utf-8')
        for name in ('synergy-build','synergy-calcs','synergy-passives','synergy-tree-suggest','synergy-tree-preview','synergy-tree-compare','synergy-catalog','synergy-synergies','synergy-inspect'):
            self.assertIn(name, text)

    def test_package_versions_are_0193(self):
        self.assertIn("VERSION = '0.19.3'", (ROOT/'src/__init__.py').read_text(encoding='utf-8'))
        self.assertIn('SERVER_VERSION = "0.19.3"', (ROOT/'mcp_server.py').read_text(encoding='utf-8'))
        self.assertIn('>0.19.3</span>', (ROOT/'web/index.html').read_text(encoding='utf-8'))

    def test_updater_accepts_0192_and_manages_repair_script(self):
        text=(ROOT/'atualizar_instalacao.py').read_text(encoding='utf-8')
        self.assertIn("PACKAGE_VERSION='0.19.3'", text)
        self.assertIn("'0.19.2'", text)
        self.assertIn("'REPARAR_CODEX_MCP.bat'", text)

if __name__=='__main__':
    unittest.main()
