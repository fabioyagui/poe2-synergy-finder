from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

class UiV19Tests(unittest.TestCase):
    def test_gear_market_and_visual_assets_are_wired(self):
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        css=(ROOT/'web'/'style.css').read_text(encoding='utf-8')
        app=(ROOT/'app.py').read_text(encoding='utf-8')
        self.assertIn("/api/trade/prepare",js)
        self.assertIn("/api/trade/search",js)
        self.assertIn("data-gear-slot",js)
        self.assertIn("gear-market-layout",css)
        self.assertIn("game-socket-chain",css)
        self.assertIn("/api/assets/resolve",app)
        self.assertIn("image.ggpk.exposed",app)

if __name__=='__main__':unittest.main()
