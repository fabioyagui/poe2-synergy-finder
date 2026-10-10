from pathlib import Path
import hashlib, json, tempfile, unittest
from unittest import mock

from src import build_library, pob_bridge

XML='<PathOfBuilding2><Build level="93" className="Mercenary" ascendClassName="Gemling Legionnaire"/><Skills/><Tree><Spec nodes="1,2"/></Tree></PathOfBuilding2>'
SUMMARY={"source":"manual","class_name":"Mercenary","ascendancy":"Gemling Legionnaire","level":93,"main_skill":"Oil Grenade","skills":[],"tree":{"allocated_nodes":2},"items":{"slots":[]},"player_stats":{}}

class BuildLifecycle187(unittest.TestCase):
    def test_delete_records_tombstone_and_manual_reimport_restores(self):
        with tempfile.TemporaryDirectory() as td:
            lib=Path(td)/"builds"
            with mock.patch.object(build_library,"LIB_DIR",lib), mock.patch.object(build_library,"INDEX_FILE",lib/"index.json"), mock.patch.object(build_library,"DELETED_FILE",lib/"deleted.json"):
                r=build_library.save_build(XML,SUMMARY)
                self.assertTrue(build_library.delete_build(r["id"]))
                self.assertIn(r["id"],build_library._load_deleted())
                build_library.save_build(XML,SUMMARY)
                self.assertNotIn(r["id"],build_library._load_deleted())
                self.assertIsNotNone(build_library.get_record(r["id"]))

    def test_sync_does_not_resurrect_deleted_build(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            current=base/"poe2-synergy-finder-v0.18.7"/"poe2-synergy-finder"
            sibling=base/"poe2-synergy-finder-v0.18.6"/"poe2-synergy-finder"
            lib=current/"data"/"builds"; oldp=sibling/"data"/"pob"; oldp.mkdir(parents=True)
            (oldp/"current.xml").write_text(XML,encoding="utf-8")
            (oldp/"current.json").write_text(json.dumps(SUMMARY),encoding="utf-8")
            bid=hashlib.sha256(XML.encode()).hexdigest()[:16]
            lib.mkdir(parents=True)
            (lib/"deleted.json").write_text(json.dumps([bid]),encoding="utf-8")
            with mock.patch.object(build_library,"PROJECT_ROOT",current), mock.patch.object(build_library,"LIB_DIR",lib), mock.patch.object(build_library,"INDEX_FILE",lib/"index.json"), mock.patch.object(build_library,"DELETED_FILE",lib/"deleted.json"):
                out=build_library.sync_siblings(lambda xml,src: dict(SUMMARY,source=src))
                self.assertEqual(out["imported"],0)
                self.assertIsNone(build_library.get_record(bid))

    def test_delete_active_clears_current_files(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); lib=base/"builds"; pob=base/"pob"
            with mock.patch.object(build_library,"LIB_DIR",lib), mock.patch.object(build_library,"INDEX_FILE",lib/"index.json"), mock.patch.object(build_library,"DELETED_FILE",lib/"deleted.json"), mock.patch.object(pob_bridge,"POB_DIR",pob), mock.patch.object(pob_bridge,"CURRENT_XML",pob/"current.xml"), mock.patch.object(pob_bridge,"CURRENT_JSON",pob/"current.json"):
                r=build_library.save_build(XML,SUMMARY)
                pob_bridge.save_current(XML,dict(SUMMARY,library_id=r["id"]))
                with mock.patch("src.pob_engine.ENGINE") as engine:
                    engine.is_running.return_value=False
                    out=pob_bridge.library_delete(r["id"])
                self.assertTrue(out["was_current"])
                self.assertFalse((pob/"current.xml").exists())
                self.assertFalse((pob/"current.json").exists())

if __name__=='__main__': unittest.main()
