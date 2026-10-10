from src import VERSION
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class UiV14Tests(unittest.TestCase):
    def test_ggg_tab_and_routes(self):
        html=(ROOT/"web"/"index.html").read_text(encoding="utf-8")
        js=(ROOT/"web"/"app.js").read_text(encoding="utf-8")
        app=(ROOT/"app.py").read_text(encoding="utf-8")
        self.assertIn('data-library-tab="ggg"',html)
        self.assertIn('Minha conta GGG',html)
        self.assertIn('/api/ggg/oauth/start',app)
        self.assertIn('/api/ggg/import-character',app)
        self.assertIn('renderGggAccount',js)
        self.assertIn('Usar no Finder',js)
    def test_version(self):
        html=(ROOT/"web"/"index.html").read_text(encoding="utf-8")
        self.assertIn(f'>{VERSION}</span>',html)
if __name__=='__main__':unittest.main()
