from src import VERSION
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class UiV15Tests(unittest.TestCase):
    def test_tree_analysis_route(self):
        app=(ROOT/"app.py").read_text(encoding="utf-8")
        self.assertIn("/api/build/tree-analysis",app)

    def test_tree_points_ui(self):
        js=(ROOT/"web"/"app.js").read_text(encoding="utf-8")
        html=(ROOT/"web"/"index.html").read_text(encoding="utf-8")
        self.assertIn("Árvore & pontos",html)
        self.assertIn("treeAllocatedSearch",js)
        self.assertIn("Mecânicas reforçadas pelos pontos",js)
        self.assertIn("Pontos resolvidos",js)
        self.assertIn("não calcula pontos restantes",js.lower())

    def test_version(self):
        html=(ROOT/"web"/"index.html").read_text(encoding="utf-8")
        self.assertIn(f">{VERSION}</span>", html)

if __name__=="__main__":
    unittest.main()
