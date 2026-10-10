from pathlib import Path
import tempfile
import unittest
from unittest import mock
from src import pob_engine

class V114Tests(unittest.TestCase):
    def test_stable_channel(self):
        self.assertEqual(pob_engine.POB2_CHANNEL, "master")
        self.assertIn("master.zip", pob_engine.POB2_ARCHIVE_URL)

    def test_syntax_check_rejects_parse_error(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            src=root/"src"; (src/"Modules").mkdir(parents=True)
            (src/"Modules"/"Main.lua").write_text("local x = y ?? {}", encoding="utf-8")
            fake=root/"luajit.exe"; fake.write_text("", encoding="utf-8")
            fake_result=mock.Mock(returncode=1, stdout="", stderr="unexpected symbol near '?'")
            with mock.patch("subprocess.run", return_value=fake_result):
                result=pob_engine._check_pob_luajit_syntax(fake, src)
            self.assertFalse(result["ok"])
            self.assertIn("unexpected symbol", result["detail"])

    def test_syntax_check_accepts_clean_module(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            src=root/"src"; (src/"Modules").mkdir(parents=True)
            (src/"Modules"/"Main.lua").write_text("local x = y or {}", encoding="utf-8")
            fake=root/"luajit.exe"; fake.write_text("", encoding="utf-8")
            fake_result=mock.Mock(returncode=0, stdout="", stderr="")
            with mock.patch("subprocess.run", return_value=fake_result):
                result=pob_engine._check_pob_luajit_syntax(fake, src)
            self.assertTrue(result["ok"])

if __name__=="__main__":
    unittest.main()
