"""Limpeza das cópias descartáveis do bridge (pob-api-v0126-<pid>-<ns>)."""
from pathlib import Path
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from src import pob_engine


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


class OverlayCleanupTests(unittest.TestCase):
    def test_pid_alive(self):
        self.assertTrue(pob_engine._pid_alive(os.getpid()))
        self.assertFalse(pob_engine._pid_alive(_dead_pid()))
        self.assertFalse(pob_engine._pid_alive(0))

    @unittest.skipUnless(os.name == "nt", "start time read only on Windows")
    def test_reused_pid_counts_as_dead(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            time.sleep(0.2)
            # Pasta criada antes do processo existir: o pid foi reutilizado, o dono original morreu.
            self.assertFalse(pob_engine._pid_alive(proc.pid, time.time_ns() - 3600 * 10**9))
            self.assertTrue(pob_engine._pid_alive(proc.pid, time.time_ns()))
            self.assertTrue(pob_engine._pid_alive(proc.pid))
        finally:
            proc.kill()
            proc.wait()

    def test_orphans_removed_live_and_protected_kept(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dead = _dead_pid()
            orphan = root / f"pob-api-v0126-{dead}-123"
            mine = root / f"pob-api-v0126-{os.getpid()}-456"
            keep = ["pob-api-v0126", "PathOfBuilding-PoE2", "pob-layer", "pob-layer-src", "pob-api-v0126-x-1"]
            for d in [orphan, mine, *(root / k for k in keep)]:
                (d / "API").mkdir(parents=True)
                (d / "API" / "Handlers.lua").write_text("--", encoding="utf-8")
            removed = pob_engine._cleanup_orphan_overlays(root)
            self.assertEqual(removed, [orphan.name])
            self.assertFalse(orphan.exists())
            self.assertTrue(mine.exists())
            for k in keep:
                self.assertTrue((root / k).exists(), k)

    def test_readonly_folders_are_removed(self):
        # Pastas copiadas de um bridge no OneDrive vêm com READONLY; RemoveDirectoryW as recusa.
        with tempfile.TemporaryDirectory() as td:
            orphan = Path(td) / f"pob-api-v0126-{_dead_pid()}-7"
            (orphan / "API").mkdir(parents=True)
            (orphan / "API" / "Handlers.lua").write_text("--", encoding="utf-8")
            for d in (orphan / "API", orphan):
                os.chmod(d, stat.S_IREAD)
            self.assertEqual(pob_engine._cleanup_orphan_overlays(Path(td)), [orphan.name])
            self.assertFalse(orphan.exists())

    def test_copy_drops_readonly(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "x" / "API"
            d.mkdir(parents=True)
            os.chmod(d, stat.S_IREAD)
            pob_engine._make_tree_writable(Path(td) / "x")
            self.assertTrue(os.stat(d).st_mode & stat.S_IWRITE)
            if os.name == "nt":
                self.assertFalse(os.stat(d).st_file_attributes & stat.FILE_ATTRIBUTE_READONLY)

    def test_remove_failure_is_tolerated(self):
        with tempfile.TemporaryDirectory() as td:
            orphan = Path(td) / f"pob-api-v0126-{_dead_pid()}-1"
            orphan.mkdir()
            with mock.patch.object(pob_engine.shutil, "rmtree", lambda *a, **k: None):
                self.assertEqual(pob_engine._cleanup_orphan_overlays(Path(td)), [])
            self.assertTrue(orphan.exists())

    def test_remove_overlay_never_touches_stable_dir(self):
        with tempfile.TemporaryDirectory() as td:
            stable = Path(td) / "pob-api-v0126"
            stable.mkdir()
            self.assertFalse(pob_engine._remove_overlay(stable))
            self.assertFalse(pob_engine._remove_overlay(None))
            self.assertTrue(stable.exists())

    def test_stop_deletes_own_copy(self):
        with tempfile.TemporaryDirectory() as td:
            copy = Path(td) / f"pob-api-v0126-{os.getpid()}-9"
            (copy / "API").mkdir(parents=True)
            client = pob_engine.EngineClient()
            client.proc = subprocess.Popen([sys.executable, "-c", "pass"])
            client.proc.wait()
            client.runtime_bridge = copy
            client.stop()
            self.assertFalse(copy.exists())


if __name__ == "__main__":
    unittest.main()
