from pathlib import Path
import tempfile
import unittest
from unittest import mock
from src import build_library

class NativeBuildLibraryTests(unittest.TestCase):
    def test_native_build_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with mock.patch.object(build_library,"LIB_DIR",root), mock.patch.object(build_library,"INDEX_FILE",root/"index.json"):
                payload={"name":"Demo","class":"Mercenary","level":10}
                summary={"source":"GGG API · Demo","source_type":"ggg-character","has_pob_xml":False,"character_name":"Demo","class_name":"Mercenary","ascendancy":"Mercenary","level":10,"main_skill":"","skills":[],"skill_group_count":0,"tree":{"allocated_nodes":0},"items":{"count":0,"slots":[]},"player_stats":{}}
                row=build_library.save_native_build(payload,summary)
                self.assertFalse(row["has_pob_xml"])
                self.assertEqual(row["payload_kind"],"ggg-character")
                self.assertEqual(build_library.get_native_payload(row["id"])["name"],"Demo")
                self.assertEqual(build_library.list_builds(q="Demo")["total"],1)

if __name__=="__main__":unittest.main()
