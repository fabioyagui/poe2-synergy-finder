from pathlib import Path
import tempfile
import unittest
from unittest import mock

from src import build_library

SAMPLE_SUMMARY={
    "source":"https://pobb.in/test",
    "class_name":"Mercenary","ascendancy":"Gemling Legionnaire","level":93,
    "main_skill":"Oil Grenade","skill_group_count":2,
    "tree":{"allocated_nodes":100},"items":{"count":3,"slots":[]},
    "player_stats":{"Life":2500,"CombinedDPS":6500},
    "skills":[{"label":"Oil","main_gem":"Oil Grenade","gems":[{"name":"Oil Grenade"},{"name":"Magnified Area II"}]}],
}

class BuildLibraryTests(unittest.TestCase):
    def test_compact_and_search_blob(self):
        row=build_library._compact(SAMPLE_SUMMARY,"a"*16,"b"*64,"2026-01-01T00:00:00+00:00")
        self.assertEqual(row["main_skill"],"Oil Grenade")
        self.assertIn("magnified area ii",build_library._blob(row))
        self.assertEqual(row["source_kind"],"pobb.in")

    def test_bad_id_is_rejected(self):
        with self.assertRaises(ValueError):build_library.get_xml("../bad")

    def test_source_status_keeps_poENinja_restricted(self):
        rows={x["id"]:x for x in build_library.source_status()}
        self.assertEqual(rows["local"]["status"],"ready")
        self.assertEqual(rows["poeninja"]["status"],"restricted")
        self.assertEqual(rows["ggg"]["status"],"planned")

if __name__=="__main__":unittest.main()
