"""Snapshots do poe.ninja: decodificação do protobuf e do dicionário NDIC, e gravação por marco (sem rede)."""
import json
import struct
import tempfile
import unittest
from pathlib import Path

from src import ninja_snapshots as ns


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(num: int, payload) -> bytes:
    if isinstance(payload, int):
        return _varint(num << 3) + _varint(payload)
    return _varint(num << 3 | 2) + _varint(len(payload)) + payload


def _ndic(names: list[str]) -> bytes:
    head = b"NDIC" + struct.pack("<I", 2) + b"\x00" * 4 + struct.pack("<I", len(names)) + b"\x00" * 8
    return head + b"".join(_varint(len(n.encode())) for n in names) + b"".join(n.encode() for n in names)


def _search(total: int, classes: list[tuple[int, int]], dict_hash: str = "abc") -> bytes:
    entries = b"".join(_field(3, (_field(1, i) if i else b"") + _field(2, c)) for i, c in classes)
    dim = _field(1, b"class") + _field(2, b"class") + entries
    dic = _field(1, b"class") + _field(2, dict_hash.encode())
    return _field(1, _field(1, total) + _field(2, dim) + _field(6, dic))


class DecodeTest(unittest.TestCase):
    def test_dictionary_names_in_index_order(self):
        names = ["Abyssal Lich", "Martial Artist", "Spirit Walker", "x" * 200]  # nome longo: tamanho em 2 bytes
        self.assertEqual(ns.parse_dictionary(_ndic(names)), names)

    def test_dictionary_rejects_other_formats(self):
        with self.assertRaises(ValueError):
            ns.parse_dictionary(b"{}")

    def test_search_counts_and_omitted_zero_index(self):
        r = ns.parse_search(_search(100, [(0, 10), (1, 60), (2, 30)]))
        self.assertEqual(r["total"], 100)
        self.assertEqual(r["dims"]["class"]["entradas"], [(0, 10), (1, 60), (2, 30)])
        self.assertEqual(r["dicts"], {"class": "abc"})


class FakeClient(ns.Client):
    def __init__(self):
        super().__init__(pause=0)
        self.calls = []

    def search(self, version, overview, label, ascendancy=None):
        self.calls.append(ascendancy)
        if ascendancy is None:
            return ns.parse_search(_search(100, [(0, 10), (1, 60), (2, 30)]))
        return ns.parse_search(_search(60 if ascendancy == "Martial Artist" else 10, [(1, 5)]))

    def dictionary(self, h):
        return ["Abyssal Lich", "Martial Artist", "Spirit Walker"]


class CaptureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.league = {"name": "Liga X", "url": "ligax", "version": "v1", "snapshotName": "liga-x",
                       "timeMachineLabels": ["day-1", "day-3"]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_capture_writes_once_and_skips_missing_labels(self):
        client = FakeClient()
        path = ns.capture(self.league, "day-3", client, self.root)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(list(data["ascendencias"]), ["Martial Artist", "Spirit Walker", "Abyssal Lich"])
        self.assertEqual(data["por_ascendencia"]["Martial Artist"]["total"], 60)
        self.assertEqual(ns.shares(path, 2), [("Martial Artist", 60.0), ("Spirit Walker", 30.0)])
        calls = len(client.calls)
        self.assertIsNone(ns.capture(self.league, "day-3", client, self.root))  # já salvo: não baixa de novo
        self.assertIsNone(ns.capture(self.league, "week-4", client, self.root))  # marco que ainda não existe
        self.assertEqual(len(client.calls), calls)

    def test_leagues_filter(self):
        idx = {"snapshotVersions": [{"name": n, "url": u} for n, u in (
            ("Forbidden Rites", "fr"), ("SSF Forbidden Rites", "frssf"), ("HC Forbidden Rites", "frhc"),
            ("HC SSF Forbidden Rites", "frhcssf"), ("Standard", "standard"), ("Privada", "pl123"))]}
        self.assertEqual([l["url"] for l in ns.leagues(idx)], ["fr", "frssf"])
        self.assertEqual(len(ns.leagues(idx, "all")), 5)


if __name__ == "__main__":
    unittest.main()
