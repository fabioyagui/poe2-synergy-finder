import inspect
import unittest
from src import pob_engine

class VirtualLinkerHotfixTests(unittest.TestCase):
    def test_remove_loop_regression_is_gone(self):
        src = inspect.getsource(pob_engine.EngineClient.compare_support_setup)
        self.assertNotIn('int(g["index"])', src)
        # v0.12.4 no longer mutates the build with remove_gem at all.
        self.assertNotIn('self.request("remove_gem"', src)

    def test_restore_baseline_still_present(self):
        src = inspect.getsource(pob_engine.EngineClient.compare_support_setup)
        self.assertIn("finally:", src)
        self.assertIn("restored baseline", src)

if __name__ == "__main__":
    unittest.main()
