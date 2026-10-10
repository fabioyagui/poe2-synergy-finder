import tempfile
from pathlib import Path
from unittest import TestCase,mock
import atualizar_instalacao as updater

class UpdaterTests(TestCase):
    def fixture(self,p,ver):
        (p/'src').mkdir(parents=True);(p/'src/__init__.py').write_text(f"VERSION = '{ver}'\n")
        (p/'app.py').write_text('old' if ver=='0.15.0' else 'new')
        (p/'data/pob').mkdir(parents=True);(p/'data/pob/current.xml').write_text('MY BUILD')
        (p/'engine').mkdir();(p/'engine/do-not-change').write_text('MY ENGINE')
    def test_upgrade_preserves_data_engine_and_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Path(tmp)/'src';t=Path(tmp)/'old';self.fixture(s,updater.PACKAGE_VERSION);self.fixture(t,'0.15.0')
            backup=updater.update(s,t)
            self.assertEqual(updater.version(t),updater.PACKAGE_VERSION)
            self.assertEqual((t/'data/pob/current.xml').read_text(),'MY BUILD')
            self.assertEqual((t/'engine/do-not-change').read_text(),'MY ENGINE')
            self.assertEqual((backup/'app.py').read_text(),'old')
    def test_rollback_program_files_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Path(tmp)/'src';t=Path(tmp)/'old';self.fixture(s,updater.PACKAGE_VERSION);self.fixture(t,'0.15.0')
            original=updater.atomic_copy
            def copy(src,dst):
                if src==s/'src/__init__.py':raise OSError('test failure')
                return original(src,dst)
            with mock.patch.object(updater,'atomic_copy',copy),self.assertRaises(OSError):updater.update(s,t)
            self.assertEqual((t/'app.py').read_text(),'old');self.assertEqual(updater.version(t),'0.15.0')
    def test_self_target_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Path(tmp);self.fixture(s,updater.PACKAGE_VERSION)
            with self.assertRaises(ValueError):updater.update(s,s)
    def test_managed_files_exclude_userdata(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.fixture(p,'0.16.0')
            self.assertFalse(any(x.parts[0] in {'engine','data'} for x in updater.files(p)))
