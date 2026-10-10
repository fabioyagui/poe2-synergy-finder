from src import VERSION
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class UiV13Tests(unittest.TestCase):
    def test_library_workspace(self):
        html=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        self.assertIn('id="openBuildLibrary"',html)
        self.assertIn('id="buildLibraryWorkspace"',html)
        self.assertIn('openBuildLibrary',js)
        self.assertIn('Usar no Finder',js)
    def test_routes(self):
        app=(ROOT/'app.py').read_text(encoding='utf-8')
        self.assertIn("p.path=='/api/builds'",app)
        self.assertIn("path=='/api/builds/use'",app)
    def test_version(self):
        html=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
        self.assertIn(f'>{VERSION}</span>',html)
if __name__=='__main__':unittest.main()
